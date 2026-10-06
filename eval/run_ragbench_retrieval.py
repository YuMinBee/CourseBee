"""한국어 사내 문서 RAG 벤치마크(eval/ragbench)의 검색 단계 평가. LLM 없이 측정한다.

정답 근거 인용문(evidence quote)의 절반 이상을 담은 청크가 상위 k개에 들어오는지 본다.

  python eval/run_ragbench_retrieval.py
  python eval/run_ragbench_retrieval.py --retriever semantic_hybrid   # sentence-transformers 필요
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.course_pack_store import load_course_pack_chunks  # noqa: E402
from v2.course_packs import _balanced_chunks, create_course_pack  # noqa: E402
from v2.schemas import Chunk  # noqa: E402

DEFAULT_BENCH_DIR = REPO_ROOT / "eval" / "ragbench"
DEFAULT_RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest_ragbench_retrieval.md"
KS = (1, 3, 5)
MRR_DEPTH = 10
QUOTE_OVERLAP = 0.5


@dataclass
class QuestionResult:
    question_id: str
    question_type: str
    answerable: bool
    hit: dict[int, bool] = field(default_factory=dict)
    full: dict[int, bool] = field(default_factory=dict)
    reciprocal_rank: float = 0.0
    top_score: float = 0.0
    latency_ms: float = 0.0


def split_of(question_id: str) -> str:
    """질문 id 해시로 dev/test를 나눈다. 튜닝은 dev로만 하고 test는 결과 보고에만 쓴다."""
    return "dev" if int(hashlib.sha256(question_id.encode()).hexdigest(), 16) % 2 == 0 else "test"


def load_bench(bench_dir: Path, split: str = "all") -> tuple[list[Path], dict[str, str], list[dict]]:
    doc_paths = sorted((bench_dir / "docs").glob("*.md"))
    doc_texts = {path.name: path.read_text(encoding="utf-8") for path in doc_paths}
    questions = [
        json.loads(line)
        for line in (bench_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if split != "all":
        questions = [question for question in questions if split_of(question["id"]) == split]
    return doc_paths, doc_texts, questions


def evidence_spans(question: dict, doc_texts: dict[str, str]) -> list[tuple[str, int, int]]:
    spans = []
    for item in question.get("evidence", []):
        start = doc_texts[item["doc"]].find(item["quote"])
        if start < 0:
            raise ValueError(f"{question['id']}: quote not found in {item['doc']}")
        spans.append((item["doc"], start, start + len(item["quote"])))
    return spans


def supports(chunk: Chunk, span: tuple[str, int, int]) -> bool:
    doc, start, end = span
    if chunk.metadata.get("filename") != doc:
        return False
    overlap = min(end, chunk.char_end) - max(start, chunk.char_start)
    return overlap >= QUOTE_OVERLAP * (end - start)


def make_retriever(name: str):
    if name == "balanced":
        return lambda question, chunks, top_k: _balanced_chunks(query=question, chunks=chunks, top_k=top_k)
    from v2.providers.semantic import SemanticHybridRetriever

    retriever = SemanticHybridRetriever(
        include_lexical=name != "semantic",
        use_reranker=name == "semantic_rerank",
    )
    return lambda question, chunks, top_k: retriever.search(question, chunks, top_k=top_k)


def evaluate(questions: list[dict], doc_texts: dict[str, str], chunks: list[Chunk], retriever) -> list[QuestionResult]:
    results: list[QuestionResult] = []
    for question in questions:
        result = QuestionResult(
            question_id=question["id"],
            question_type=question["type"],
            answerable=bool(question.get("answerable", True)),
        )
        started = time.perf_counter()
        ranked = retriever(question["question"], chunks, MRR_DEPTH)
        result.latency_ms = (time.perf_counter() - started) * 1000
        result.top_score = float(ranked[0].metadata.get("retrieval_score") or 0.0) if ranked else 0.0

        spans = evidence_spans(question, doc_texts) if result.answerable else []
        if spans:
            for k in KS:
                top = retriever(question["question"], chunks, k)
                covered = [any(supports(chunk, span) for chunk in top) for span in spans]
                result.hit[k] = any(covered)
                result.full[k] = all(covered)
            for rank, chunk in enumerate(ranked, start=1):
                if any(supports(chunk, span) for span in spans):
                    result.reciprocal_rank = 1.0 / rank
                    break
        results.append(result)
    return results


def auc(positive: list[float], negative: list[float]) -> float:
    """답이 있는 질문의 최고 점수가 답 없는 질문보다 높을 확률(1.0이면 점수만으로 완벽히 구분)."""
    if not positive or not negative:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return wins / (len(positive) * len(negative))


def render(results: list[QuestionResult], *, retriever: str, chunk_count: int, doc_count: int, build_ms: float) -> str:
    answerable = [r for r in results if r.answerable and r.hit]
    by_type: dict[str, list[QuestionResult]] = defaultdict(list)
    for result in answerable:
        by_type[result.question_type].append(result)

    def pct(values: list[bool]) -> str:
        return f"{100 * sum(values) / len(values):.1f}%" if values else "-"

    latencies = [r.latency_ms for r in results]
    lines = [
        "# CourseBee RAG Benchmark — Retrieval",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        f"Retriever `{retriever}` over {doc_count} documents / {chunk_count} chunks. A chunk counts as evidence when it",
        f"contains at least {int(QUOTE_OVERLAP * 100)}% of a gold evidence quote. Full@k requires every evidence item",
        "(multi-hop questions need all of their documents).",
        "",
        "| Type | n | Hit@1 | Hit@3 | Hit@5 | Full@5 | MRR@10 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for question_type in sorted(by_type) + ["all"]:
        group = answerable if question_type == "all" else by_type[question_type]
        lines.append(
            f"| {question_type} | {len(group)} | {pct([r.hit[1] for r in group])} | {pct([r.hit[3] for r in group])} | "
            f"{pct([r.hit[5] for r in group])} | {pct([r.full[5] for r in group])} | "
            f"{statistics.mean(r.reciprocal_rank for r in group):.3f} |"
        )
    positive = [r.top_score for r in results if r.answerable]
    negative = [r.top_score for r in results if not r.answerable]
    lines += [
        "",
        f"- Unanswerable questions: {len(negative)}. Top-score AUC (answerable vs unanswerable): {auc(positive, negative):.3f}",
        f"- Retrieval latency p50 / p95: {statistics.median(latencies):.1f} ms / "
        f"{sorted(latencies)[int(0.95 * (len(latencies) - 1))]:.1f} ms; pack build {build_ms / 1000:.1f} s",
        "",
        "Misses at k=5 (answerable):",
        "",
    ]
    misses = [r.question_id for r in answerable if not r.hit[5]]
    lines.append(", ".join(misses) if misses else "none")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval on the CourseBee Korean RAG benchmark.")
    parser.add_argument("--bench-dir", type=Path, default=DEFAULT_BENCH_DIR)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--retriever", default="balanced", choices=["balanced", "semantic", "semantic_hybrid", "semantic_rerank"])
    parser.add_argument("--split", default="all", choices=["all", "dev", "test"])
    parser.add_argument("--json-path", type=Path, help="optional per-question results")
    parser.add_argument("--min-hit-at-5", type=float, default=0.0, help="exit 1 below this Hit@5 (CI gate)")
    args = parser.parse_args()

    doc_paths, doc_texts, questions = load_bench(args.bench_dir, args.split)
    with tempfile.TemporaryDirectory(prefix="coursebee-ragbench-") as output_root:
        started = time.perf_counter()
        create_course_pack(paths=[str(path) for path in doc_paths], output_root=output_root, pack_id="ragbench")
        build_ms = (time.perf_counter() - started) * 1000
        chunks = load_course_pack_chunks("ragbench", output_root=output_root)
        results = evaluate(questions, doc_texts, chunks, make_retriever(args.retriever))

    markdown = render(results, retriever=args.retriever, chunk_count=len(chunks), doc_count=len(doc_paths), build_ms=build_ms)
    args.results_path.parent.mkdir(parents=True, exist_ok=True)
    args.results_path.write_text(markdown, encoding="utf-8")
    if args.json_path:
        args.json_path.write_text(
            json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=1), encoding="utf-8"
        )
    print(markdown)
    answerable = [result for result in results if result.answerable and result.hit]
    hit_at_5 = sum(result.hit[5] for result in answerable) / len(answerable) if answerable else 0.0
    if hit_at_5 < args.min_hit_at_5:
        print(f"Hit@5 {hit_at_5:.3f} is below the gate {args.min_hit_at_5:.3f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
