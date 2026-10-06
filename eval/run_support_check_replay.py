"""답변 근거 검사(support check)만 따로 평가한다.

검사를 끈 실행의 답변(초안)과 그 판정을 입력으로 받아, 같은 검색 결과에 대해 검사만 다시 돌린다.
생성은 매번 조금씩 달라서 검사 켠 실행과 끈 실행을 비교하면 검사 효과와 생성 차이가 섞인다. 여기서는 초안을 고정한다.

- 맞는 초안을 거절한 비율: correct/partial 판정 초안 중 not_supported (낮을수록 좋다)
- 틀린 초안을 잡은 비율: incorrect 판정 초안(답 있는 질문의 오답, 답 없는 질문에서 지어낸 답) 중 not_supported (높을수록 좋다)

  COURSEBEE_RETRIEVAL=semantic COURSEBEE_EMBEDDING_MODEL=nlpai-lab/KURE-v1 COURSEBEE_TODAY=2026-10-06 \\
    python eval/run_support_check_replay.py --split dev --drafts eval/results/ragbench_answers/dev_3_kure_prompt.json

판정은 --verdict-field(기본 claude_verdict, 없으면 verdict)에서 읽는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.run_ragbench_retrieval import DEFAULT_BENCH_DIR, load_bench  # noqa: E402
from v2.course_pack_store import load_course_pack_chunks  # noqa: E402
from v2.course_packs import VECTOR_RETRIEVAL_ALIASES, _balanced_chunks, create_course_pack  # noqa: E402
from v2.io_utils import atomic_write_text  # noqa: E402
from v2.providers.ollama import OllamaProvider, OllamaProviderError  # noqa: E402
from v2.providers.semantic import SemanticHybridRetriever  # noqa: E402

GROUPS = {
    "correct draft (answerable)": lambda row, verdict: row["answerable"] and verdict == "correct",
    "partial draft (answerable)": lambda row, verdict: row["answerable"] and verdict == "partial",
    "wrong draft (answerable)": lambda row, verdict: row["answerable"] and verdict == "incorrect",
    "made-up draft (unanswerable)": lambda row, verdict: not row["answerable"] and verdict == "incorrect",
    "refusal draft": lambda row, verdict: verdict == "abstained",
}


def select_chunks(question: str, chunks: list, top_k: int) -> list:
    """course_packs._ask_course_pack_with_vector와 같은 방식으로 근거를 고른다."""
    mode = VECTOR_RETRIEVAL_ALIASES.get(os.environ.get("COURSEBEE_RETRIEVAL", "lexical").lower(), "vector")
    if mode in {"semantic", "semantic_hybrid", "semantic_rerank"}:
        retriever = SemanticHybridRetriever(include_lexical=mode != "semantic", use_reranker=mode == "semantic_rerank")
        return retriever.search_with_details(question, chunks, top_k=top_k).chunks
    return _balanced_chunks(query=question, chunks=chunks, top_k=top_k)


def render(rows: list[dict], args: argparse.Namespace) -> str:
    lines = [
        "# CourseBee support check replay",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        f"Drafts `{args.drafts.as_posix()}` (verdicts from `{args.verdict_field}`), split `{args.split}`, "
        f"checker `{args.model}`, COURSEBEE_RETRIEVAL={os.environ.get('COURSEBEE_RETRIEVAL', 'lexical')}, "
        f"COURSEBEE_TODAY={os.environ.get('COURSEBEE_TODAY', 'today')}.",
        "",
        f"{args.note}" if args.note else "",
        "",
        "| Draft group | n | Rewritten as not supported | Check failed (draft kept) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name in GROUPS:
        group = [row for row in rows if row["group"] == name]
        rejected = sum(row["check"] == "not_supported" for row in group)
        share = f"{rejected} ({100 * rejected / len(group):.0f}%)" if group else "-"
        lines.append(f"| {name} | {len(group)} | {share} | {sum(row['check'] == 'error' for row in group)} |")
    lines += ["", "Rejected correct or partial drafts:", ""]
    for row in rows:
        if row["group"].startswith(("correct", "partial")) and row["check"] == "not_supported":
            lines.append(f"- {row['question_id']} ({row['question_type']}): {row['reason']}")
    lines += ["", "Wrong or made-up drafts that passed:", ""]
    for row in rows:
        if row["group"].startswith(("wrong", "made-up")) and row["check"] == "supported":
            lines.append(f"- {row['question_id']} ({row['question_type']}): {row['reason']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the answer support check on fixed, judged drafts.")
    parser.add_argument("--bench-dir", type=Path, default=DEFAULT_BENCH_DIR)
    parser.add_argument("--split", default="dev", choices=["all", "dev", "test"])
    parser.add_argument("--drafts", type=Path, required=True, help="answers JSON from a run with the check off")
    parser.add_argument("--verdict-field", default="claude_verdict")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--model", default="qwen3:14b")
    parser.add_argument("--note", default="", help="free text for the report, e.g. which prompt version")
    parser.add_argument("--results-path", type=Path, default=REPO_ROOT / "outputs" / "support_check_replay.md")
    parser.add_argument("--json-path", type=Path, default=REPO_ROOT / "outputs" / "support_check_replay.json")
    args = parser.parse_args()

    doc_paths, _texts, questions = load_bench(args.bench_dir, args.split)
    by_id = {question["id"]: question for question in questions}
    drafts = [row for row in json.loads(args.drafts.read_text(encoding="utf-8")) if row["question_id"] in by_id]
    provider = OllamaProvider(model=args.model)
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="coursebee-support-replay-") as output_root:
        create_course_pack(paths=[str(path) for path in doc_paths], output_root=output_root, pack_id="ragbench")
        chunks = load_course_pack_chunks("ragbench", output_root=output_root)
        for number, draft in enumerate(drafts, start=1):
            verdict = draft.get(args.verdict_field) or draft["verdict"]
            group = next((name for name, test in GROUPS.items() if test(draft, verdict)), "other")
            selected = select_chunks(draft["question"], chunks, args.top_k)
            retrieved = list(dict.fromkeys((c.metadata or {}).get("filename") for c in selected))
            started = time.perf_counter()
            try:
                check, reason = provider.check_support(draft["question"], selected, draft["answer"])
            except OllamaProviderError as exc:
                # 서비스에서는 검사가 실패하면 초안을 그대로 둔다(answering._check_answer_support).
                check, reason = "error", str(exc)[:200]
            rows.append(
                {
                    "question_id": draft["question_id"],
                    "question_type": draft["question_type"],
                    "answerable": draft["answerable"],
                    "group": group,
                    "draft_verdict": verdict,
                    "check": check,
                    "reason": reason,
                    "same_documents_as_run": retrieved[: len(draft["retrieved_docs"])] == draft["retrieved_docs"],
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            print(f"[{number}/{len(drafts)}] {draft['question_id']} {group}: {check}", flush=True)

    atomic_write_text(args.json_path, json.dumps(rows, ensure_ascii=False, indent=1))
    markdown = render(rows, args)
    atomic_write_text(args.results_path, markdown)
    print(markdown)
    mismatched = [row["question_id"] for row in rows if not row["same_documents_as_run"]]
    if mismatched:
        print(f"Retrieved documents differ from the original run for: {', '.join(mismatched)}")
    print(Counter(row["group"] for row in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
