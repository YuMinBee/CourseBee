from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.providers.semantic import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RERANKER_MODEL,
    SemanticHybridRetriever,
)
from v2.rag.retrieval import chunks_from_contexts, retrieve_contexts  # noqa: E402
from v2.schemas import Chunk  # noqa: E402

DEFAULT_SUITE_PATH = REPO_ROOT / "eval" / "semantic_retrieval_suite.json"
DEFAULT_RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest_semantic_retrieval_eval.md"


@dataclass(slots=True)
class RankingResult:
    mode: str
    filenames: list[str]
    expected_rank: int | None
    latency_ms: float
    actual_mode: str
    fallback_used: bool = False

    @property
    def reciprocal_rank(self) -> float:
        return 0.0 if self.expected_rank is None else 1.0 / self.expected_rank


@dataclass(slots=True)
class CaseResult:
    case_id: str
    question: str
    expected_source: str
    rankings: dict[str, RankingResult]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare CourseBee local, semantic hybrid, and reranked retrieval.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--skip-reranker", action="store_true")
    args = parser.parse_args()

    if importlib.util.find_spec("sentence_transformers") is None:
        print('sentence-transformers is not installed. Run: pip install -e ".[semantic]"', file=sys.stderr)
        return 2

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    chunks = _build_chunks(suite.get("documents", {}))
    retrievers = {
        "semantic_hybrid": SemanticHybridRetriever(
            embedding_model=args.embedding_model,
            include_lexical=True,
        )
    }
    if not args.skip_reranker:
        retrievers["semantic_rerank"] = SemanticHybridRetriever(
            embedding_model=args.embedding_model,
            reranker_model=args.reranker_model,
            include_lexical=True,
            use_reranker=True,
        )

    cases = suite.get("cases", [])
    if cases:
        _warm_up(retrievers, cases[0]["question"], chunks, args.top_k)

    results = [
        _run_case(case, chunks, retrievers, top_k=args.top_k)
        for case in cases
    ]
    markdown = _render_markdown(
        results,
        embedding_model=args.embedding_model,
        reranker_model=None if args.skip_reranker else args.reranker_model,
        top_k=args.top_k,
        description=suite.get("description", ""),
    )
    args.results_path.parent.mkdir(parents=True, exist_ok=True)
    args.results_path.write_text(markdown, encoding="utf-8")
    print(markdown)

    semantic_modes = [mode for mode in retrievers if mode.startswith("semantic")]
    semantic_results = [result.rankings[mode] for result in results for mode in semantic_modes]
    return 0 if semantic_results and all(item.expected_rank is not None and not item.fallback_used for item in semantic_results) else 1


def _build_chunks(documents: dict[str, str]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for index, (filename, text) in enumerate(documents.items(), start=1):
        chunks.append(
            Chunk(
                chunk_id=f"semantic_eval_{index}",
                page=1,
                text=text,
                char_start=0,
                char_end=len(text),
                metadata={"doc_id": f"semantic_eval_{index}", "filename": filename},
            )
        )
    return chunks


def _warm_up(
    retrievers: dict[str, SemanticHybridRetriever],
    question: str,
    chunks: list[Chunk],
    top_k: int,
) -> None:
    for retriever in retrievers.values():
        retriever.search_with_details(question, chunks, top_k=top_k)


def _run_case(
    case: dict[str, Any],
    chunks: list[Chunk],
    retrievers: dict[str, SemanticHybridRetriever],
    *,
    top_k: int,
) -> CaseResult:
    question = case["question"]
    expected = case["expected_source"]
    rankings = {"local_hybrid": _run_local(question, expected, chunks, top_k)}
    for mode, retriever in retrievers.items():
        started = time.perf_counter()
        run = retriever.search_with_details(question, chunks, top_k=top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        filenames = _filenames(run.chunks)
        rankings[mode] = RankingResult(
            mode=mode,
            filenames=filenames,
            expected_rank=_expected_rank(filenames, expected),
            latency_ms=latency_ms,
            actual_mode=run.retrieval_mode,
            fallback_used=run.fallback_used,
        )
    return CaseResult(
        case_id=case["id"],
        question=question,
        expected_source=expected,
        rankings=rankings,
    )


def _run_local(question: str, expected: str, chunks: list[Chunk], top_k: int) -> RankingResult:
    started = time.perf_counter()
    contexts = retrieve_contexts(question, chunks, top_k=top_k, strategy="hybrid").contexts
    latency_ms = (time.perf_counter() - started) * 1000
    filenames = _filenames(chunks_from_contexts(contexts))
    return RankingResult(
        mode="local_hybrid",
        filenames=filenames,
        expected_rank=_expected_rank(filenames, expected),
        latency_ms=latency_ms,
        actual_mode="local_hybrid",
    )


def _filenames(chunks: list[Chunk]) -> list[str]:
    return [str(chunk.metadata.get("filename") or "-") for chunk in chunks]


def _expected_rank(filenames: list[str], expected: str) -> int | None:
    try:
        return filenames.index(expected) + 1
    except ValueError:
        return None


def _render_markdown(
    results: list[CaseResult],
    *,
    embedding_model: str,
    reranker_model: str | None,
    top_k: int,
    description: str,
) -> str:
    modes = list(results[0].rankings) if results else []
    lines = [
        "# CourseBee Semantic Retrieval Evaluation",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        description,
        "",
        f"- Embedding model: `{embedding_model}`",
        f"- Reranker model: `{reranker_model or 'skipped'}`",
        f"- Evaluation depth: top-{top_k}",
        "- Latency excludes model download and uses a warm in-process model/cache.",
        "",
        "## Metrics",
        "",
        "| Mode | Recall@k | MRR | Mean warm latency | Fallbacks |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for mode in modes:
        rankings = [result.rankings[mode] for result in results]
        recall = sum(item.expected_rank is not None for item in rankings) / max(len(rankings), 1)
        mrr = mean(item.reciprocal_rank for item in rankings) if rankings else 0.0
        latency = mean(item.latency_ms for item in rankings) if rankings else 0.0
        fallbacks = sum(item.fallback_used for item in rankings)
        lines.append(f"| `{mode}` | {recall:.2f} | {mrr:.3f} | {latency:.2f} ms | {fallbacks} |")

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Expected | " + " | ".join(f"{mode} rank" for mode in modes) + " |",
            "| --- | --- | " + " | ".join("---:" for _ in modes) + " |",
        ]
    )
    for result in results:
        ranks = [str(result.rankings[mode].expected_rank or "MISS") for mode in modes]
        lines.append(f"| `{result.case_id}` | {result.expected_source} | " + " | ".join(ranks) + " |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This synthetic suite measures retrieval ranking, not generated-answer quality.",
            "- Cross-lingual and paraphrased questions reduce dependence on exact keyword overlap.",
            "- A semantic fallback is counted as a failure so missing models are not reported as AI success.",
            "- Model selection should be revisited with real, permission-safe lecture material before production use.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
