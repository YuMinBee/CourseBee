"""한국어 RAG 벤치마크(eval/ragbench) end-to-end 평가. 로컬 Ollama로 실제 답변을 만들고 채점한다.

  python eval/run_ragbench_answers.py --split dev --model qwen3:14b
  python eval/run_ragbench_answers.py --split dev --resume      # 이어서 실행

채점:
- 답변 판정: LLM 심판(기본 qwen3:14b)이 정답과 비교해 correct / partial / incorrect / abstained 중 하나를 고른다.
  빈 답변(검색 결과가 없어 화면에 "답을 찾지 못했어요"가 뜨는 경우)은 심판 없이 abstained로 둔다.
- 블라인드 검토: JSON에 claude_verdict가 있으면(실행 이름을 가리고 섞어서 따로 채점한 결과) 표를 하나 더 만든다.
- 숫자 일치: 정답의 "숫자+단위"(예: 180일, 1만 5천원)가 답변에 그대로 있는지 결정적으로 확인한다.
- 인용: 답변이 근거로 표시한 문서와 정답 근거 문서를 문서 단위로 비교한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import tempfile
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.run_ragbench_retrieval import DEFAULT_BENCH_DIR, load_bench  # noqa: E402
from v2.course_packs import ask_course_pack, create_course_pack  # noqa: E402
from v2.io_utils import atomic_write_text  # noqa: E402

DEFAULT_RESULTS_PATH = REPO_ROOT / "eval" / "results" / "latest_ragbench_answers.md"
VERDICTS = ("correct", "partial", "incorrect", "abstained")
NUMBER_WITH_UNIT_RE = re.compile(
    r"(\d[\d,.]*)\s*(%|만\s*원|천\s*원|원|영업일|일|시간|분|초|회|개월|년|주|자|명|시|건|배|ms)"
)

JUDGE_PROMPT = """You grade answers from an internal-documents assistant at a Korean company. Today is 2026-10-06.

Question: {question}
Reference answer: {reference}
Assistant answer: {answer}

Choose one verdict:
- correct: the answer states the key facts of the reference answer. Numbers, dates, amounts and names must match exactly. Extra details are fine unless they contradict the reference.
- partial: some key facts are right but others are missing, or there is one minor error.
- incorrect: the answer states something that contradicts the reference (a wrong fact, number or procedure), presents an outdated rule as current, or makes up information.
- abstained: the answer does not give the requested information: it says the documents do not contain or confirm it, or it is empty. Choose abstained for such a refusal even though the reference shows the documents do contain the answer; a refusal is not an incorrect answer.

Reply with JSON only: {{"verdict": "correct|partial|incorrect|abstained", "reason": "<one short English sentence>"}}"""

# 답이 없는 질문은 "문서에 없다고 말했는가 / 지어냈는가"만 묻는다. 네 가지 선택지를 주면 심판이
# 올바른 거절을 "correct"로 표시하거나, 관련 사실을 덧붙인 거절을 "incorrect"로 잘못 판정했다.
UNANSWERABLE_JUDGE_PROMPT = """You grade answers from an internal-documents assistant at a Korean company. Today is 2026-10-06.
The company documents do NOT contain the answer to this question.

Question: {question}
Assistant answer: {answer}

Choose one verdict:
- abstained: the answer says the documents do not contain, state or confirm this information. It may mention related facts that are in the documents and may suggest whom to ask, as long as it does not present an answer to the question itself as fact. Reporting what the documents say about the topic, for example that something has not been decided yet or will be announced later, is also abstained.
- incorrect: the answer presents an answer to the question as fact (for example a yes/no, an amount, a place, a person or a procedure for exactly what was asked), even if it adds a caveat.

Reply with JSON only: {{"verdict": "abstained|incorrect", "reason": "<one short English sentence>"}}"""


@dataclass
class AnswerResult:
    question_id: str
    question_type: str
    answerable: bool
    question: str
    reference: str
    answer: str
    verdict: str
    judge_reason: str
    numbers_expected: list[str] = field(default_factory=list)
    numbers_found: list[str] = field(default_factory=list)
    gold_docs: list[str] = field(default_factory=list)
    retrieved_docs: list[str] = field(default_factory=list)
    cited_docs: list[str] = field(default_factory=list)
    answer_scope: str = ""
    latency_ms: float = 0.0
    support_revised: bool = False
    support_draft: str = ""
    claude_verdict: str = ""
    claude_reason: str = ""


KOREAN_AMOUNT_RE = re.compile(r"(?:(\d[\d,]*)\s*만\s*)?(?:(\d[\d,]*)\s*천\s*)?(\d[\d,]*)?\s*원")


def _won(text: str) -> list[str]:
    """'1만 5천원', '15,000원', '50만원'을 같은 정수로 맞춘다."""
    values = []
    for man, cheon, plain in KOREAN_AMOUNT_RE.findall(text):
        if not (man or cheon or plain):
            continue
        value = int(man.replace(",", "") or 0) * 10000 + int(cheon.replace(",", "") or 0) * 1000
        value += int(plain.replace(",", "") or 0) if plain else 0
        values.append(f"{value}원")
    return values


def numbers_with_units(text: str) -> list[str]:
    """정답 검사용 '숫자+단위'. 1회·1명처럼 말로 풀어 쓰기 쉬운 1은 뺀다."""
    found: list[str] = []
    for token in _won(text):
        if token not in found:
            found.append(token)
    for number, unit in NUMBER_WITH_UNIT_RE.findall(text):
        compact_unit = re.sub(r"\s+", "", unit)
        if "원" in compact_unit:
            continue
        number = number.replace(",", "").rstrip(".")
        if number == "1":
            continue
        token = number + compact_unit
        if token not in found:
            found.append(token)
    return found


def ollama_json(model: str, prompt: str, base_url: str = "http://127.0.0.1:11434") -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 200},
    }
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))
    try:
        return json.loads(data.get("response") or "{}")
    except json.JSONDecodeError:
        return {}


EMPTY_ANSWER_REASON = "empty answer: nothing was retrieved, so the UI shows a no-answer message"


def judge(question: dict, answer: str, model: str) -> tuple[str, str]:
    # qwen 심판은 빈 답변을 정답과 비교해 correct로 판정하곤 했다. 빈 답은 판정할 내용이 없다.
    if not answer.strip():
        return "abstained", EMPTY_ANSWER_REASON
    if question.get("answerable", True):
        prompt = JUDGE_PROMPT.format(question=question["question"], reference=question["answer"], answer=answer)
        allowed = VERDICTS
    else:
        prompt = UNANSWERABLE_JUDGE_PROMPT.format(question=question["question"], answer=answer)
        allowed = ("abstained", "incorrect")
    result = ollama_json(model, prompt)
    verdict = str(result.get("verdict", "")).strip().lower()
    return (verdict if verdict in allowed else "incorrect"), str(result.get("reason", ""))[:300]


def cited_documents(payload: dict) -> list[str]:
    sources = payload.get("sources") or []
    cited = []
    for item in payload.get("sentence_citations") or []:
        if not item.get("grounded"):
            continue
        indices = item.get("source_indices") or [item.get("source_index")]
        for index in indices:
            if isinstance(index, int) and 1 <= index <= len(sources):
                filename = sources[index - 1].get("filename")
                if filename and filename not in cited:
                    cited.append(filename)
    return cited


def run_question(question: dict, *, pack_id: str, output_root: str, args: argparse.Namespace) -> AnswerResult:
    started = time.perf_counter()
    payload = ask_course_pack(
        pack_id=pack_id,
        question=question["question"],
        output_root=output_root,
        top_k=args.top_k,
        mode=args.mode,
        llm_provider="ollama",
        llm_model=args.model,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    answer = str(payload.get("answer") or "")
    verdict, reason = judge(question, answer, args.judge_model)
    expected = numbers_with_units(question["answer"]) if question.get("answerable", True) else []
    found_in_answer = set(numbers_with_units(answer))
    return AnswerResult(
        question_id=question["id"],
        question_type=question["type"],
        answerable=bool(question.get("answerable", True)),
        question=question["question"],
        reference=question["answer"],
        answer=answer,
        verdict=verdict,
        judge_reason=reason,
        numbers_expected=expected,
        numbers_found=[number for number in expected if number in found_in_answer],
        gold_docs=sorted({item["doc"] for item in question.get("evidence", [])}),
        retrieved_docs=list(dict.fromkeys(s.get("filename") for s in payload.get("sources") or [] if s.get("filename"))),
        cited_docs=cited_documents(payload),
        answer_scope=str(payload.get("answer_scope") or ""),
        latency_ms=latency_ms,
        support_revised=bool((payload.get("support_check") or {}).get("revised")),
        # 검사가 바꾼 답은 초안도 남긴다. 검사가 맞는 초안을 막았는지 따로 채점할 수 있다.
        support_draft=str((payload.get("support_check") or {}).get("draft_answer") or ""),
    )


def run_config() -> str:
    """환경변수로 바꾸는 설정은 리포트만 봐서는 알 수 없으므로 함께 기록한다."""
    retrieval = os.environ.get("COURSEBEE_RETRIEVAL", "lexical")
    embedding = os.environ.get("COURSEBEE_EMBEDDING_MODEL", "default") if retrieval != "lexical" else "-"
    return (
        f"COURSEBEE_RETRIEVAL={retrieval}, COURSEBEE_EMBEDDING_MODEL={embedding}, "
        f"OLLAMA_THINK={os.environ.get('OLLAMA_THINK', 'false')}, "
        f"COURSEBEE_SUPPORT_CHECK={os.environ.get('COURSEBEE_SUPPORT_CHECK', 'on')}, "
        f"COURSEBEE_TODAY={os.environ.get('COURSEBEE_TODAY', 'today')}"
    )


def precision_recall(results: list[AnswerResult], attribute: str) -> tuple[float, float]:
    tp = fp = fn = 0
    for result in results:
        predicted = set(getattr(result, attribute))
        gold = set(result.gold_docs)
        tp += len(predicted & gold)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall


def verdict_lines(results: list[AnswerResult], attribute: str = "verdict") -> list[str]:
    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]

    def share(group: list[AnswerResult], verdict: str) -> str:
        return f"{100 * sum(getattr(r, attribute) == verdict for r in group) / len(group):.1f}%" if group else "-"

    lines = [
        "| Type | n | Correct | Partial | Incorrect | Abstained |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    types = sorted({r.question_type for r in answerable})
    for question_type in [*types, "answerable (all)"]:
        group = answerable if question_type == "answerable (all)" else [r for r in answerable if r.question_type == question_type]
        lines.append(
            f"| {question_type} | {len(group)} | {share(group, 'correct')} | {share(group, 'partial')} | "
            f"{share(group, 'incorrect')} | {share(group, 'abstained')} |"
        )
    lines.append(
        f"| unanswerable | {len(unanswerable)} | - | - | {share(unanswerable, 'incorrect')} (made up) | "
        f"{share(unanswerable, 'abstained')} (correct) |"
    )
    wrong = sum(getattr(r, attribute) == "incorrect" for r in results)
    score = sum((getattr(r, attribute) == "correct") + 0.5 * (getattr(r, attribute) == "partial") for r in answerable)
    lines += [
        "",
        f"- Answer score (correct + 0.5 x partial) on answerable questions: {100 * score / max(1, len(answerable)):.1f}%",
        f"- Stated something wrong (incorrect on any question): {wrong} / {len(results)} "
        f"({100 * wrong / max(1, len(results)):.1f}%)",
    ]
    return lines


def render(results: list[AnswerResult], args: argparse.Namespace) -> str:
    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]
    reviewed = [r for r in results if r.claude_verdict]

    lines = [
        "# CourseBee RAG Benchmark — Answers",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        f"Split `{args.split}`, retrieval mode `{args.mode}` (top_k={args.top_k}), generator `{args.model}`, "
        f"judge `{args.judge_model}`.",
        "",
        f"Config: {args.config or run_config()}",
        "",
    ]
    if reviewed and len(reviewed) == len(results):
        agree = sum(r.claude_verdict == r.verdict for r in results)
        lines += [
            "## Blind review (Claude)",
            "",
            "Answers from every compared run were shuffled together and graded without run names.",
            "",
            *verdict_lines(results, "claude_verdict"),
            "",
            f"## LLM judge (`{args.judge_model}`)",
            "",
            f"Agrees with the blind review on {agree} / {len(results)} answers.",
            "",
        ]
    lines += verdict_lines(results)

    numeric = [r for r in answerable if r.numbers_expected]
    exact = sum(len(r.numbers_found) == len(r.numbers_expected) for r in numeric)
    retrieved_p, retrieved_r = precision_recall(answerable, "retrieved_docs")
    cited_p, cited_r = precision_recall(answerable, "cited_docs")
    latencies = [r.latency_ms for r in results]
    lines += [
        "",
        "## Deterministic checks",
        "",
        f"- Empty answers (nothing retrieved): {sum(not r.answer.strip() for r in answerable)} / {len(answerable)} "
        f"answerable, {sum(not r.answer.strip() for r in unanswerable)} / {len(unanswerable)} unanswerable",
        f"- Every reference number/unit present in the answer: {exact} / {len(numeric)} answers",
        f"- Documents shown as sources (all retrieved): precision {retrieved_p:.2f} / recall {retrieved_r:.2f}",
        f"- Documents cited by answer sentences: precision {cited_p:.2f} / recall {cited_r:.2f}",
        f"- Answers rewritten by the support check: {sum(r.support_revised for r in answerable)} / {len(answerable)} "
        f"answerable, {sum(r.support_revised for r in unanswerable)} / {len(unanswerable)} unanswerable",
        f"- End-to-end latency p50 / p95: {statistics.median(latencies) / 1000:.1f} s / "
        f"{sorted(latencies)[int(0.95 * (len(latencies) - 1))] / 1000:.1f} s",
        "",
        "Verdicts come from LLMs; see the per-question JSON for their reasons.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end answer evaluation on the CourseBee Korean RAG benchmark.")
    parser.add_argument("--bench-dir", type=Path, default=DEFAULT_BENCH_DIR)
    parser.add_argument("--split", default="dev", choices=["all", "dev", "test"])
    parser.add_argument("--mode", default="vector")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--model", default="qwen3:14b")
    parser.add_argument("--judge-model", default="qwen3:14b")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--json-path", type=Path, default=REPO_ROOT / "outputs" / "ragbench_answers.json")
    parser.add_argument("--resume", action="store_true", help="reuse finished questions from --json-path")
    parser.add_argument("--max-new", type=int, default=0, help="answer at most N new questions in this run")
    parser.add_argument("--rejudge", action="store_true", help="re-grade stored answers without regenerating them")
    parser.add_argument("--render-only", action="store_true", help="redraw the report from --json-path without any LLM call")
    parser.add_argument("--config", default="", help="config line for the report (default: read from the environment)")
    args = parser.parse_args()

    if args.render_only:
        stored = [AnswerResult(**item) for item in json.loads(args.json_path.read_text(encoding="utf-8"))]
        for result in stored:
            if not result.answer.strip():
                result.verdict, result.judge_reason = "abstained", EMPTY_ANSWER_REASON
        atomic_write_text(args.json_path, json.dumps([asdict(item) for item in stored], ensure_ascii=False, indent=1))
        markdown = render(stored, args)
        atomic_write_text(args.results_path, markdown)
        print(markdown)
        return 0

    if args.rejudge:
        _paths, _texts, questions = load_bench(args.bench_dir, args.split)
        by_id = {question["id"]: question for question in questions}
        stored = [AnswerResult(**item) for item in json.loads(args.json_path.read_text(encoding="utf-8"))]
        for result in stored:
            result.verdict, result.judge_reason = judge(by_id[result.question_id], result.answer, args.judge_model)
        atomic_write_text(args.json_path, json.dumps([asdict(item) for item in stored], ensure_ascii=False, indent=1))
        markdown = render(stored, args)
        atomic_write_text(args.results_path, markdown)
        print(markdown)
        return 0

    doc_paths, _doc_texts, questions = load_bench(args.bench_dir, args.split)
    if args.limit:
        questions = questions[: args.limit]
    done: dict[str, AnswerResult] = {}
    if args.resume and args.json_path.exists():
        done = {
            item["question_id"]: AnswerResult(**item)
            for item in json.loads(args.json_path.read_text(encoding="utf-8"))
        }

    pending = [question for question in questions if question["id"] not in done]
    if args.max_new:
        pending = pending[: args.max_new]
    if pending:
        with tempfile.TemporaryDirectory(prefix="coursebee-ragbench-answers-") as output_root:
            create_course_pack(paths=[str(path) for path in doc_paths], output_root=output_root, pack_id="ragbench")
            for number, question in enumerate(pending, start=1):
                result = run_question(question, pack_id="ragbench", output_root=output_root, args=args)
                done[result.question_id] = result
                print(f"[{number}/{len(pending)}] {result.question_id} {result.verdict} {result.latency_ms / 1000:.1f}s", flush=True)
                # 중간에 프로세스가 죽어도 파일이 깨지지 않게 임시 파일에 쓴 뒤 교체한다.
                atomic_write_text(
                    args.json_path,
                    json.dumps([asdict(item) for item in done.values()], ensure_ascii=False, indent=1),
                )

    results = [done[question["id"]] for question in questions if question["id"] in done]
    remaining = len(questions) - len(results)
    if remaining:
        print(f"{len(results)} / {len(questions)} questions answered; rerun with --resume to continue.")
        return 0
    markdown = render(results, args)
    atomic_write_text(args.results_path, markdown)
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
