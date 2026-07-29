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

from v2.audio_grounding import evaluate_audio_segment_grounding  # noqa: E402
from v2.io_utils import atomic_write_text  # noqa: E402
from v2.schemas import Chunk  # noqa: E402

DEFAULT_SUITE_PATH = REPO_ROOT / "eval" / "audio_grounding_suite.json"
DEFAULT_RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest_audio_grounding_eval.md"


@dataclass(slots=True)
class CaseResult:
    case_id: str
    expected_passed: bool
    actual_passed: bool
    expected_status: str
    actual_status: str
    coverage: float
    high_risk_terms: list[str]
    expected_high_risk_terms: list[str]

    @property
    def passed(self) -> bool:
        return (
            self.actual_passed == self.expected_passed
            and self.actual_status == self.expected_status
            and all(term in self.high_risk_terms for term in self.expected_high_risk_terms)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CourseBee audio grounding evaluation.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    results = [_run_case(case, index) for index, case in enumerate(suite.get("cases", []), start=1)]
    markdown = _render_markdown(results)
    atomic_write_text(args.results_path, markdown)
    print(markdown)
    return 0 if results and all(result.passed for result in results) else 1


def _run_case(case: dict[str, Any], index: int) -> CaseResult:
    filename = f"audio-grounding-{index}.txt"
    chunk = Chunk(
        chunk_id=f"audio-grounding-{index}-c1",
        page=1,
        text=str(case["source"]),
        char_start=0,
        char_end=len(str(case["source"])),
        metadata={"doc_id": f"audio-grounding-{index}", "filename": filename},
    )
    result = evaluate_audio_segment_grounding(
        str(case["script"]),
        [chunk],
        strict=bool(case.get("strict")),
    )
    return CaseResult(
        case_id=str(case["id"]),
        expected_passed=bool(case["expected_passed"]),
        actual_passed=result.passed,
        expected_status=str(case["expected_status"]),
        actual_status=result.status,
        coverage=result.coverage,
        high_risk_terms=result.high_risk_terms,
        expected_high_risk_terms=[str(term) for term in case.get("expected_high_risk_terms", [])],
    )


def _render_markdown(results: list[CaseResult]) -> str:
    passed = sum(result.passed for result in results)
    lines = [
        "# CourseBee Audio Grounding Evaluation",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "Deterministic cases verify supported claims, conversational transitions, invented model names, numeric claims, and strict Korean grounding.",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Classification accuracy | {passed} / {len(results)} |",
        f"| Unsupported-claim detection | {sum(result.passed for result in results if not result.expected_passed)} / {sum(not result.expected_passed for result in results)} |",
        "",
        "| Case | Expected | Actual | Coverage | High-risk terms | Status |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for result in results:
        expected = f"{result.expected_status} / {'pass' if result.expected_passed else 'fail'}"
        actual = f"{result.actual_status} / {'pass' if result.actual_passed else 'fail'}"
        high_risk = ", ".join(f"`{term}`" for term in result.high_risk_terms) or "-"
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"| `{result.case_id}` | {expected} | {actual} | {result.coverage:.3f} | {high_risk} | {status} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
