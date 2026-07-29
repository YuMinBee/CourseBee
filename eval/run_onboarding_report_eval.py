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

from v2.course_packs import (  # noqa: E402
    create_course_pack,
    onboarding_report_for_course_pack,
    onboarding_report_impact_for_course_pack,
)
from v2.io_utils import atomic_write_text  # noqa: E402

DEFAULT_SUITE_PATH = REPO_ROOT / "eval" / "onboarding_report_suite.json"
DEFAULT_RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest_onboarding_report_eval.md"
DEFAULT_RUNTIME_DIR = REPO_ROOT / "outputs" / "_eval_onboarding_report"
FIXTURE_DIR = REPO_ROOT / "v2" / "assets" / "demo_fixtures"


@dataclass(slots=True)
class CaseResult:
    case_id: str
    quality_pass: bool
    source_recall_pass: bool
    source_precision_pass: bool
    term_pass: bool
    export_pass: bool
    citation_coverage: float
    document_coverage: float
    grounded_sections: int
    section_count: int

    @property
    def passed(self) -> bool:
        return all(
            (
                self.quality_pass,
                self.source_recall_pass,
                self.source_precision_pass,
                self.term_pass,
                self.export_pass,
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CourseBee v3 onboarding report evaluation.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    output_root = DEFAULT_RUNTIME_DIR / "outputs"
    pack_id = "pack_eval_enterprise_onboarding"
    fixture_paths = sorted(FIXTURE_DIR.glob("enterprise_*.txt"))
    create_course_pack(
        paths=[str(path) for path in fixture_paths],
        output_root=str(output_root),
        pack_id=pack_id,
        max_chunk_chars=700,
    )
    results = [_run_case(pack_id, output_root, case) for case in suite.get("cases", [])]
    impact_result = _run_source_update_case(output_root)
    markdown = _render_markdown(results, impact_result)
    atomic_write_text(args.results_path, markdown)
    print(markdown)
    return 0 if results and all(result.passed for result in results) and all(impact_result.values()) else 1


def _run_case(pack_id: str, output_root: Path, case: dict[str, Any]) -> CaseResult:
    report = onboarding_report_for_course_pack(
        pack_id=pack_id,
        query=str(case["objective"]),
        output_root=str(output_root),
        top_k=10,
        title=str(case["title"]),
        audience=str(case["audience"]),
        objective=str(case["objective"]),
        max_sections=6,
        llm_provider="mock",
    )
    quality = report.get("quality", {})
    filenames = {
        str(source.get("filename"))
        for source in report.get("source_register", [])
        if source.get("filename")
    }
    expected_sources = {str(filename) for filename in case.get("expected_sources", [])}
    allowed_sources = {str(filename) for filename in case.get("allowed_sources", case.get("expected_sources", []))}
    serialized = json.dumps(report, ensure_ascii=False).lower()
    artifacts = report.get("artifacts", {})
    return CaseResult(
        case_id=str(case["id"]),
        quality_pass=bool(quality.get("passed")),
        source_recall_pass=expected_sources.issubset(filenames),
        source_precision_pass=filenames.issubset(allowed_sources),
        term_pass=all(str(term).lower() in serialized for term in case.get("expected_terms", [])),
        export_pass=all(Path(path).is_file() for path in artifacts.values()),
        citation_coverage=float(quality.get("citation_coverage") or 0),
        document_coverage=float(quality.get("source_document_coverage") or 0),
        grounded_sections=int(quality.get("grounded_section_count") or 0),
        section_count=int(quality.get("section_count") or 0),
    )


def _run_source_update_case(output_root: Path) -> dict[str, bool]:
    source_dir = output_root.parent / "impact_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    security = source_dir / "enterprise_security_policy.txt"
    handbook = source_dir / "enterprise_employee_handbook.txt"
    security.write_text(
        (FIXTURE_DIR / security.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    handbook.write_text(
        (FIXTURE_DIR / handbook.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    pack_id = "pack_eval_onboarding_impact"
    create_course_pack(
        paths=[str(security), str(handbook)],
        output_root=str(output_root),
        pack_id=pack_id,
        max_chunk_chars=700,
    )
    report_args = {
        "pack_id": pack_id,
        "output_root": str(output_root),
        "audience": "신입 구성원",
        "objective": "핵심 보안과 근무 규정 이해",
        "llm_provider": "mock",
    }
    onboarding_report_for_course_pack(**report_args)
    security.write_text(
        security.read_text(encoding="utf-8")
        + "\n개정 정책: 관리자 권한 요청은 보안 담당자의 사전 승인을 받아야 한다.\n",
        encoding="utf-8",
    )
    create_course_pack(
        paths=[str(security)],
        output_root=str(output_root),
        pack_id=pack_id,
        append=True,
        max_chunk_chars=700,
    )
    impact = onboarding_report_impact_for_course_pack(pack_id=pack_id, output_root=str(output_root))
    regenerated = onboarding_report_for_course_pack(**report_args)
    refreshed = onboarding_report_impact_for_course_pack(pack_id=pack_id, output_root=str(output_root))
    return {
        "change_detected": bool(impact.get("requires_regeneration")) and len(impact.get("updated_sources", [])) == 1,
        "affected_section_found": bool(impact.get("affected_sections")),
        "unchanged_section_reused": regenerated.get("generation", {}).get("reused_section_count") == 1,
        "refresh_returns_current": refreshed.get("status") == "current" and not refreshed.get("requires_regeneration"),
    }


def _render_markdown(results: list[CaseResult], impact_result: dict[str, bool]) -> str:
    passed = sum(result.passed for result in results)
    total_sections = sum(result.section_count for result in results)
    grounded_sections = sum(result.grounded_sections for result in results)
    mean_citation = sum(result.citation_coverage for result in results) / len(results) if results else 0
    mean_document = sum(result.document_coverage for result in results) / len(results) if results else 0
    lines = [
        "# CourseBee v3 Onboarding Report Evaluation",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "Public synthetic enterprise documents verify source recall and precision, section grounding, "
        "change impact, and export readiness.",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Overall pass rate | {passed} / {len(results)} |",
        f"| Grounded sections | {grounded_sections} / {total_sections} |",
        f"| Mean citation coverage | {mean_citation:.2f} |",
        f"| Mean source-document coverage | {mean_document:.2f} |",
        f"| JSON / Markdown / HTML export | {sum(result.export_pass for result in results)} / {len(results)} |",
        f"| Objective-specific source selection | "
        f"{sum(result.source_recall_pass and result.source_precision_pass for result in results)} / {len(results)} |",
        f"| Source update impact checks | {sum(impact_result.values())} / {len(impact_result)} |",
        "",
        "| Case | Quality | Source recall | Source precision | Terms | Export | Citation coverage | "
        "Document coverage | Status |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{result.case_id}`",
                    _mark(result.quality_pass),
                    _mark(result.source_recall_pass),
                    _mark(result.source_precision_pass),
                    _mark(result.term_pass),
                    _mark(result.export_pass),
                    f"{result.citation_coverage:.2f}",
                    f"{result.document_coverage:.2f}",
                    "PASS" if result.passed else "FAIL",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Source Update Impact",
            "",
            "| Check | Result |",
            "| --- | --- |",
            *[
                f"| `{name}` | {'PASS' if passed else 'FAIL'} |"
                for name, passed in impact_result.items()
            ],
        ]
    )
    return "\n".join(lines) + "\n"


def _mark(value: bool) -> str:
    return "PASS" if value else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
