from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.course_packs import ask_course_pack, create_course_pack  # noqa: E402

DEFAULT_SUITE_PATH = REPO_ROOT / "eval" / "generalization_suite.json"
DEFAULT_RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest_generalization_eval.md"
DEFAULT_RUNTIME_DIR = REPO_ROOT / "outputs" / "_eval_generalization"


@dataclass
class CaseResult:
    domain: str
    case_id: str
    expected_route: str
    actual_route: str
    route_pass: bool
    source_pass: bool
    term_pass: bool
    citation_pass: bool
    graph_pass: bool
    sources: list[str]

    @property
    def passed(self) -> bool:
        return all((self.route_pass, self.source_pass, self.term_pass, self.citation_pass, self.graph_pass))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CourseBee multi-domain generalization evaluation.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    results: list[CaseResult] = []
    for domain in suite.get("domains", []):
        pack_id = f"pack_eval_{domain['id']}"
        paths = _write_documents(domain["id"], domain.get("documents", {}))
        create_course_pack(
            paths=[str(path) for path in paths],
            output_root=str(DEFAULT_RUNTIME_DIR / "outputs"),
            pack_id=pack_id,
        )
        for case in domain.get("cases", []):
            results.append(_run_case(domain["id"], pack_id, case))

    markdown = _render_markdown(results)
    args.results_path.parent.mkdir(parents=True, exist_ok=True)
    args.results_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0 if all(result.passed for result in results) else 1


def _write_documents(domain: str, documents: dict[str, str]) -> list[Path]:
    directory = DEFAULT_RUNTIME_DIR / "docs" / domain
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename, content in documents.items():
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def _run_case(domain: str, pack_id: str, case: dict[str, Any]) -> CaseResult:
    response = ask_course_pack(
        pack_id=pack_id,
        question=case["question"],
        output_root=str(DEFAULT_RUNTIME_DIR / "outputs"),
        top_k=4,
        mode="auto",
    )
    sources = _source_filenames(response)
    text = json.dumps(response, ensure_ascii=False).lower()
    expected_route = case["expected_route"]
    graph_required = expected_route == "local_graph"
    return CaseResult(
        domain=domain,
        case_id=case["id"],
        expected_route=expected_route,
        actual_route=str(response.get("routed_mode") or ""),
        route_pass=response.get("routed_mode") == expected_route,
        source_pass=case["expected_source"] in sources,
        term_pass=all(term.lower() in text for term in case.get("expected_terms", [])),
        citation_pass=bool(sources),
        graph_pass=not graph_required or bool(response.get("graph_context") or response.get("graph_paths")),
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
    citation_hits = sum(result.citation_pass for result in results)
    graph_results = [result for result in results if result.expected_route == "local_graph"]
    graph_hits = sum(result.graph_pass for result in graph_results)
    lines = [
        "# CourseBee Multi-domain Generalization Evaluation",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "Synthetic fixtures cover biology, economics, and software engineering.",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Overall pass rate | {passed} / {len(results)} |",
        f"| Router accuracy | {route_hits} / {len(results)} |",
        f"| Required source recall | {source_hits} / {len(results)} |",
        f"| Citation coverage | {citation_hits} / {len(results)} |",
        f"| Graph evidence usefulness | {graph_hits} / {len(graph_results)} |",
        "",
        "| Domain | Case | Expected route | Actual route | Source | Terms | Citation | Graph | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        values = [
            result.domain,
            f"`{result.case_id}`",
            result.expected_route,
            result.actual_route or "-",
            _mark(result.source_pass),
            _mark(result.term_pass),
            _mark(result.citation_pass),
            _mark(result.graph_pass),
            "PASS" if result.passed else "FAIL",
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def _mark(value: bool) -> str:
    return "PASS" if value else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
