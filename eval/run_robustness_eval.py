from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.course_packs import ask_course_pack, create_course_pack  # noqa: E402
from v2.io_utils import atomic_write_text  # noqa: E402

DEFAULT_SUITE_PATH = REPO_ROOT / "eval" / "robustness_suite.json"
DEFAULT_RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest_robustness_eval.md"
DEFAULT_RUNTIME_DIR = REPO_ROOT / "outputs" / "_eval_robustness"


@dataclass
class CaseResult:
    scenario: str
    case_id: str
    expected_route: str
    actual_route: str
    route_pass: bool
    source_recall: float
    source_precision: float
    source_pass: bool
    forbidden_pass: bool
    term_pass: bool
    citation_pass: bool
    abstention_pass: bool
    graph_pass: bool
    latency_ms: float
    latency_pass: bool
    sources: list[str]

    @property
    def passed(self) -> bool:
        return all(
            (
                self.route_pass,
                self.source_pass,
                self.forbidden_pass,
                self.term_pass,
                self.citation_pass,
                self.abstention_pass,
                self.graph_pass,
                self.latency_pass,
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CourseBee retrieval robustness evaluation.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    results: list[CaseResult] = []
    for scenario in suite.get("scenarios", []):
        scenario_id = str(scenario["id"])
        pack_id = f"pack_robust_{scenario_id}"
        paths = _write_documents(args.runtime_dir, scenario_id, scenario.get("documents", {}))
        create_course_pack(
            paths=[str(path) for path in paths],
            output_root=str(args.runtime_dir / "outputs"),
            pack_id=pack_id,
        )
        for case in scenario.get("cases", []):
            results.append(_run_case(args.runtime_dir, scenario_id, pack_id, case))

    markdown = _render_markdown(results)
    atomic_write_text(args.results_path, markdown)
    print(markdown)
    return 0 if results and all(result.passed for result in results) else 1


def _write_documents(runtime_dir: Path, scenario: str, documents: dict[str, str]) -> list[Path]:
    directory = runtime_dir / "docs" / scenario
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename, content in documents.items():
        path = directory / filename
        atomic_write_text(path, content)
        paths.append(path)
    return paths


def _run_case(runtime_dir: Path, scenario: str, pack_id: str, case: dict[str, Any]) -> CaseResult:
    started = time.perf_counter()
    response = ask_course_pack(
        pack_id=pack_id,
        question=case["question"],
        output_root=str(runtime_dir / "outputs"),
        top_k=int(case.get("top_k", 5)),
        mode="auto",
    )
    latency_ms = (time.perf_counter() - started) * 1000

    sources = _source_filenames(response)
    required = set(case.get("required_sources", []))
    forbidden = set(case.get("forbidden_sources", []))
    returned = set(sources)
    expected_abstention = bool(case.get("expected_abstention"))
    source_recall = len(required & returned) / len(required) if required else 1.0
    source_precision = len(required & returned) / len(returned) if returned else (1.0 if not required else 0.0)
    minimum_precision = float(case.get("min_source_precision", 0.0))
    text = json.dumps(response, ensure_ascii=False).lower()
    expected_route = str(case["expected_route"])
    warnings = [str(warning).lower() for warning in response.get("warnings", [])]

    abstention_pass = True
    if expected_abstention:
        abstention_pass = (
            not str(response.get("answer") or "").strip()
            and not returned
            and any("no relevant context" in warning for warning in warnings)
        )

    return CaseResult(
        scenario=scenario,
        case_id=str(case["id"]),
        expected_route=expected_route,
        actual_route=str(response.get("routed_mode") or response.get("retrieval_mode") or ""),
        route_pass=(response.get("routed_mode") or response.get("retrieval_mode")) == expected_route,
        source_recall=source_recall,
        source_precision=source_precision,
        source_pass=source_recall == 1.0 and source_precision >= minimum_precision,
        forbidden_pass=not bool(forbidden & returned),
        term_pass=all(str(term).lower() in text for term in case.get("expected_terms", [])),
        citation_pass=not required or bool(returned),
        abstention_pass=abstention_pass,
        graph_pass=not case.get("require_graph_evidence", False)
        or bool(response.get("graph_context") or response.get("graph_paths")),
        latency_ms=latency_ms,
        latency_pass=latency_ms <= float(case.get("max_latency_ms", 1000)),
        sources=sources,
    )


def _source_filenames(response: dict[str, Any]) -> list[str]:
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

    visit(response)
    return filenames


def _render_markdown(results: list[CaseResult]) -> str:
    passed = sum(result.passed for result in results)
    route_hits = sum(result.route_pass for result in results)
    source_hits = sum(result.source_pass for result in results)
    abstention_results = [result for result in results if not result.sources]
    graph_results = [result for result in results if result.expected_route == "local_graph"]
    latencies = [result.latency_ms for result in results]
    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = _percentile(latencies, 0.95)
    lines = [
        "# CourseBee Retrieval Robustness Evaluation",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "Scenarios cover OCR line-break noise, source conflicts, cross-document relations, distractors, and abstention.",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Overall pass rate | {passed} / {len(results)} |",
        f"| Router accuracy | {route_hits} / {len(results)} |",
        f"| Source recall and precision checks | {source_hits} / {len(results)} |",
        f"| Graph evidence checks | {sum(result.graph_pass for result in graph_results)} / {len(graph_results)} |",
        f"| Abstention checks | {sum(result.abstention_pass for result in abstention_results)} / {len(abstention_results)} |",
        f"| Ask latency p50 / p95 | {p50:.2f} ms / {p95:.2f} ms |",
        "",
        "| Scenario | Case | Route | Recall | Precision | Forbidden | Terms | Abstain | Graph | Latency | Status |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | ---: | --- |",
    ]
    for result in results:
        route = f"{result.expected_route} / {result.actual_route or '-'}"
        values = [
            result.scenario,
            f"`{result.case_id}`",
            route,
            f"{result.source_recall:.2f}",
            f"{result.source_precision:.2f}",
            _mark(result.forbidden_pass),
            _mark(result.term_pass),
            _mark(result.abstention_pass),
            _mark(result.graph_pass),
            f"{result.latency_ms:.2f} ms",
            "PASS" if result.passed else "FAIL",
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def _mark(value: bool) -> str:
    return "PASS" if value else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
