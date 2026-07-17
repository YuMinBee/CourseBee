from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.api import routes  # noqa: E402
from v2.api.schemas import CoursePackIngestRequest, CoursePackQueryRequest  # noqa: E402

PACK_ID = "pack_eval_nlp_11week"
DEFAULT_RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest_eval.md"
DEFAULT_RUNTIME_DIR = REPO_ROOT / "outputs" / "_eval_runtime"

FILENAME_LECTURE_1 = "\uc790\uc5f0\uc5b4\ucc98\ub9ac_11\uc8fc\ucc28_1\ucc28\uc2dc.txt"
FILENAME_LECTURE_2 = "\uc790\uc5f0\uc5b4\ucc98\ub9ac_11\uc8fc\ucc28_2\ucc28\uc2dc.txt"
FILENAME_LECTURE_3 = "\uc790\uc5f0\uc5b4\ucc98\ub9ac_11\uc8fc\ucc28_3\ucc28\uc2dc.txt"

FIXTURE_DOCS = {
    FILENAME_LECTURE_1: (
        "Lecture 11-1 introduces Tokenizer, subword tokenization, BPE, and OOV. "
        "Tokenizer and subword tokenization are prerequisites for BPE. "
        "BPE reduces OOV through subword tokenization and is used in the NLP pipeline."
    ),
    FILENAME_LECTURE_2: (
        "Lecture 11-2 explains RNN and LSTM for sequence data. "
        "RNN handles sequence data in the NLP pipeline. "
        "LSTM improves RNN and handles long-term dependency with gates."
    ),
    FILENAME_LECTURE_3: (
        "Lecture 11-3 explains CNN, local pattern, text classification, and GraphRAG-lite. "
        "CNN captures local pattern for text classification and is used in the NLP pipeline. "
        "GraphRAG-lite builds a concept map and augments RAG. "
        "source citation grounds RAG by preserving page and chunk evidence."
    ),
}


@dataclass
class EvalCaseResult:
    case_id: str
    question: str
    expected_route: str | None
    actual_route: str | None
    expected_question_type: str | None
    actual_question_type: str | None
    expected_retrieval_mode: str | None
    actual_retrieval_mode: str | None
    route_pass: bool
    source_required: bool
    source_pass: bool
    concept_pass: bool
    citation_present: bool
    fallback_pass: bool | None
    graph_useful: bool | None
    sources: list[str]
    concepts: list[str]
    warnings: list[str]

    @property
    def passed(self) -> bool:
        checks = [self.route_pass, self.source_pass, self.concept_pass]
        if self.source_required:
            checks.append(self.citation_present)
        if self.fallback_pass is not None:
            checks.append(self.fallback_pass)
        if self.graph_useful is not None:
            checks.append(self.graph_useful)
        return all(checks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CourseBee v2 retrieval evaluation.")
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    cases = _load_jsonl(REPO_ROOT / "eval" / "golden_questions.jsonl")
    expected_routes = _load_json(REPO_ROOT / "eval" / "expected_routes.json")
    expected_sources = _load_json(REPO_ROOT / "eval" / "expected_sources.json")

    runtime_dir = DEFAULT_RUNTIME_DIR
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    docs_dir = runtime_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    paths = _write_fixture_docs(docs_dir)
    output_root = runtime_dir / "outputs"
    routes.ingest_course_pack(
        CoursePackIngestRequest(
            paths=[str(path) for path in paths],
            output_root=str(output_root),
            max_chunk_chars=900,
            pack_id=PACK_ID,
        )
    )

    results = [
        _run_case(
            case=case,
            route_expectation=expected_routes.get(case["id"], {}),
            source_expectation=expected_sources.get(case["id"], {}),
            output_root=output_root,
            top_k=args.top_k,
        )
        for case in cases
    ]

    summary = _summarize(results)
    markdown = _render_markdown(results, summary)
    args.results_path.parent.mkdir(parents=True, exist_ok=True)
    args.results_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0 if all(result.passed for result in results) else 1


def _run_case(
    case: dict[str, Any],
    route_expectation: dict[str, Any],
    source_expectation: dict[str, Any],
    output_root: Path,
    top_k: int,
) -> EvalCaseResult:
    response = routes.ask_course_pack(
        CoursePackQueryRequest(
            pack_id=PACK_ID,
            question=case["question"],
            output_root=str(output_root),
            top_k=top_k,
            mode=case.get("mode", "auto"),
        )
    )

    expected_question_type = route_expectation.get("expected_question_type")
    expected_route = route_expectation.get("expected_route")
    expected_retrieval_mode = route_expectation.get("expected_retrieval_mode")

    actual_question_type = response.get("question_type")
    actual_route = response.get("routed_mode")
    actual_retrieval_mode = response.get("retrieval_mode")

    route_pass = all(
        [
            expected_question_type in {None, actual_question_type},
            expected_route in {None, actual_route},
            expected_retrieval_mode in {None, actual_retrieval_mode},
            route_expectation.get("expected_traversal_strategy") in {None, response.get("traversal_strategy")},
            route_expectation.get("expected_abstraction_level") in {None, response.get("abstraction_level")},
        ]
    )

    observed_sources = _collect_source_filenames(response)
    observed_concepts = _collect_concepts(response)
    required_sources = source_expectation.get("must_include_sources", [])
    required_concepts = source_expectation.get("must_include_concepts", [])
    source_pass = _contains_all(observed_sources, required_sources)
    concept_pass = _contains_all(observed_concepts, required_concepts)
    citation_present = bool(observed_sources)

    expected_fallback = bool(route_expectation.get("expected_fallback"))
    fallback_pass = None
    if expected_fallback:
        fallback_pass = actual_retrieval_mode == "local_graph_fallback_vector" and bool(response.get("warnings"))

    graph_useful = None
    if expected_route == "local_graph" and not expected_fallback:
        graph_useful = bool(response.get("graph_context") or response.get("graph_paths")) and concept_pass

    return EvalCaseResult(
        case_id=case["id"],
        question=case["question"],
        expected_route=expected_route,
        actual_route=actual_route,
        expected_question_type=expected_question_type,
        actual_question_type=actual_question_type,
        expected_retrieval_mode=expected_retrieval_mode,
        actual_retrieval_mode=actual_retrieval_mode,
        route_pass=route_pass,
        source_required=bool(required_sources),
        source_pass=source_pass,
        concept_pass=concept_pass,
        citation_present=citation_present,
        fallback_pass=fallback_pass,
        graph_useful=graph_useful,
        sources=observed_sources,
        concepts=observed_concepts,
        warnings=list(response.get("warnings", [])),
    )


def _summarize(results: list[EvalCaseResult]) -> dict[str, Any]:
    router_total = len([result for result in results if result.expected_route])
    router_hits = sum(1 for result in results if result.expected_route and result.route_pass)
    source_cases = [result for result in results if result.source_required]
    source_total = len(source_cases)
    source_hits = sum(1 for result in source_cases if result.source_pass)
    citation_coverage = sum(1 for result in results if result.citation_present) / len(results) if results else 0.0
    fallback_cases = [result for result in results if result.fallback_pass is not None]
    graph_cases = [result for result in results if result.graph_useful is not None]
    return {
        "case_count": len(results),
        "pass_count": sum(1 for result in results if result.passed),
        "router_accuracy": (router_hits, router_total),
        "source_recall_at_5": (source_hits, source_total),
        "citation_coverage": citation_coverage,
        "fallback": (sum(1 for result in fallback_cases if result.fallback_pass), len(fallback_cases)),
        "graph_useful": (sum(1 for result in graph_cases if result.graph_useful), len(graph_cases)),
    }


def _render_markdown(results: list[EvalCaseResult], summary: dict[str, Any]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    router_hit, router_total = summary["router_accuracy"]
    source_hit, source_total = summary["source_recall_at_5"]
    fallback_hit, fallback_total = summary["fallback"]
    graph_hit, graph_total = summary["graph_useful"]
    lines = [
        "# CourseBee v2 Evaluation Results",
        "",
        f"Generated: {generated_at}",
        "",
        "This evaluation uses a public synthetic NLP 11-week Course Pack fixture. It does not use private lecture materials.",
        "",
        "## Evaluation Snapshot",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Overall pass rate | {summary['pass_count']} / {summary['case_count']} |",
        f"| Router accuracy | {router_hit} / {router_total} |",
        f"| Source recall@5 | {source_hit} / {source_total} |",
        f"| Citation coverage | {_format_float(summary['citation_coverage'])} |",
        f"| No-context fallback pass | {fallback_hit} / {fallback_total} |",
        f"| Graph route useful cases | {graph_hit} / {graph_total} |",
        "",
        "## Case Results",
        "",
        "| ID | Expected | Actual | Sources | Concepts | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        expected = f"{result.expected_question_type} / {result.expected_route} / {result.expected_retrieval_mode}"
        actual = f"{result.actual_question_type} / {result.actual_route} / {result.actual_retrieval_mode}"
        source_text = ", ".join(result.sources) if result.sources else "-"
        concept_text = ", ".join(result.concepts) if result.concepts else "-"
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"| `{result.case_id}` | {expected} | {actual} | {source_text} | {concept_text} | {status} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Router accuracy checks `question_type`, `routed_mode`, and final `retrieval_mode`.",
            "- Source recall@5 checks whether required source filenames appear in answer sources, graph evidence, or hierarchical supporting chunks.",
            "- Citation coverage measures whether each answer returned at least one source-like evidence reference.",
            "- Graph route useful cases require graph context or graph paths plus expected concepts.",
            "- No-context fallback checks that relation questions with no matching course graph concepts fall back with a warning.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_fixture_docs(docs_dir: Path) -> list[Path]:
    paths = []
    for filename, text in FIXTURE_DOCS.items():
        path = docs_dir / filename
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _collect_source_filenames(response: dict[str, Any]) -> list[str]:
    filenames: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            filename = value.get("filename")
            if isinstance(filename, str) and filename not in filenames:
                filenames.append(filename)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for key in ["sources", "evidence_chunks", "supporting_chunks", "graph_context", "selected_summary_nodes"]:
        visit(response.get(key, []))
    return filenames


def _collect_concepts(response: dict[str, Any]) -> list[str]:
    concepts: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value and value not in concepts:
            concepts.append(value)

    for concept in response.get("matched_entities", []) or []:
        add(concept)
    for edge in response.get("graph_context", []) or []:
        add(edge.get("source"))
        add(edge.get("target"))
    for path in response.get("graph_paths", []) or []:
        for node in path.get("nodes", []) or []:
            add(node)
    return concepts


def _contains_all(observed: list[str], required: list[str]) -> bool:
    return all(any(item == candidate or item in candidate for candidate in observed) for item in required)


def _format_float(value: float) -> str:
    return f"{value:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
