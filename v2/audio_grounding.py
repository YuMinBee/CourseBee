from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from v2.schemas import Chunk

CREATIVE_MIN_COVERAGE = 0.18
STRICT_MIN_COVERAGE = 0.35

_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]*|\d+(?:\.\d+)?%?|[가-힣]{2,}")
_LATIN_OR_NUMBER_PATTERN = re.compile(r"^(?:[a-z][a-z0-9_.+-]*|\d+(?:\.\d+)?%?)$")
_HANGUL_PATTERN = re.compile(r"[가-힣]")

_GENERIC_TERMS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "about",
    "be",
    "because",
    "by",
    "can",
    "coursebee",
    "does",
    "each",
    "episode",
    "every",
    "example",
    "for",
    "from",
    "guest",
    "has",
    "have",
    "host",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "of",
    "on",
    "or",
    "podcast",
    "script",
    "that",
    "the",
    "their",
    "then",
    "this",
    "to",
    "today",
    "use",
    "uses",
    "using",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "will",
    "with",
    "감사",
    "개념",
    "결론",
    "과정",
    "관계",
    "그렇습니다",
    "그런데",
    "내용",
    "다시",
    "다음",
    "대화",
    "도움",
    "마지막",
    "맞아요",
    "먼저",
    "모습",
    "방법",
    "부분",
    "설명",
    "시간",
    "실제",
    "어떤",
    "어떻게",
    "오늘",
    "완벽",
    "왜",
    "이때",
    "이야기",
    "이유",
    "이해",
    "자료",
    "잠깐",
    "정리",
    "정확히",
    "좋아요",
    "중요",
    "지금",
    "질문",
    "처음",
    "핵심",
    "함께",
}

_SAFE_LATIN_TERMS = {
    "ai",
    "coursebee",
    "episode",
    "guest",
    "host",
    "nlp",
    "podcast",
}

_KOREAN_SUFFIXES = (
    "에서는",
    "이라는",
    "이라고",
    "으로는",
    "있습니다",
    "없습니다",
    "됩니다",
    "입니다",
    "이에요",
    "하면서",
    "하지만",
    "하는데",
    "되어서",
    "하도록",
    "으로",
    "에서",
    "부터",
    "까지",
    "처럼",
    "보다",
    "에게",
    "하는",
    "되는",
    "하며",
    "하고",
    "해서",
    "해요",
    "예요",
    "이죠",
    "하죠",
    "되죠",
    "라고",
    "이나",
    "와는",
    "과는",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "도",
    "와",
    "과",
    "로",
    "만",
)

_CONTEXT_MARKERS = (
    "감사합니다",
    "강의형 대본",
    "지금부터",
    "넘어가",
    "마지막으로",
    "살펴볼까요",
    "안녕하세요",
    "어떤 모습일까요",
    "어떻게 처리할까요",
    "이야기해볼게요",
    "정리로",
    "질문을",
)


@dataclass(slots=True)
class AudioSegmentGroundingResult:
    index: int
    checked: bool
    passed: bool
    status: str
    coverage: float = 0.0
    matched_terms: list[str] = field(default_factory=list)
    unsupported_terms: list[str] = field(default_factory=list)
    high_risk_terms: list[str] = field(default_factory=list)
    source_chunk_ids: list[str] = field(default_factory=list)
    source_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_audio_script_grounding(
    script: list[dict],
    source_chunks: list[Chunk],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for index, segment in enumerate(script):
        chunks = source_chunks_for_segment(segment, source_chunks)
        result = evaluate_audio_segment_grounding(
            str(segment.get("text") or ""),
            chunks,
            index=index,
            strict=strict,
        )
        results.append(result.to_dict())

    checked = [result for result in results if result["checked"]]
    grounded = [result for result in checked if result["passed"]]
    unsupported = [result for result in checked if not result["passed"]]
    contexts = [result for result in results if result["status"] == "context"]
    mean_coverage = sum(result["coverage"] for result in checked) / len(checked) if checked else 1.0

    return {
        "checked": bool(script),
        "passed": bool(script) and not unsupported,
        "method": "lexical_claim_overlap_v1",
        "mode": "strict" if strict else "creative",
        "minimum_coverage": STRICT_MIN_COVERAGE if strict else CREATIVE_MIN_COVERAGE,
        "segment_count": len(script),
        "checked_segment_count": len(checked),
        "context_segment_count": len(contexts),
        "grounded_segment_count": len(grounded),
        "unsupported_segment_count": len(unsupported),
        "segment_pass_rate": round(len(grounded) / len(checked), 3) if checked else 1.0,
        "mean_coverage": round(mean_coverage, 3),
        "unsupported_segments": [
            {
                "index": result["index"],
                "coverage": result["coverage"],
                "unsupported_terms": result["unsupported_terms"],
                "high_risk_terms": result["high_risk_terms"],
            }
            for result in unsupported
        ],
        "segments": results,
    }


def evaluate_audio_segment_grounding(
    text: str,
    source_chunks: list[Chunk],
    *,
    index: int = 0,
    strict: bool = False,
) -> AudioSegmentGroundingResult:
    source_ids = list(dict.fromkeys(chunk.chunk_id for chunk in source_chunks))
    if not text.strip() or not source_chunks:
        return AudioSegmentGroundingResult(
            index=index,
            checked=True,
            passed=False,
            status="unsupported",
            source_chunk_ids=source_ids,
            source_count=len(source_chunks),
        )

    claim_terms = _claim_terms(text)
    source_terms = set(_source_terms(source_chunks))
    source_text = " ".join(chunk.text.lower() for chunk in source_chunks)
    matched_terms = [term for term in claim_terms if _term_supported(term, source_terms, source_text)]
    unsupported_terms = [term for term in claim_terms if term not in matched_terms]
    high_risk_terms = _high_risk_terms(text, unsupported_terms)

    if _is_context_segment(text, claim_terms, matched_terms, high_risk_terms):
        return AudioSegmentGroundingResult(
            index=index,
            checked=False,
            passed=True,
            status="context",
            matched_terms=matched_terms[:12],
            unsupported_terms=unsupported_terms[:12],
            source_chunk_ids=source_ids,
            source_count=len(source_chunks),
        )

    coverage = len(matched_terms) / len(claim_terms) if claim_terms else 1.0
    minimum_coverage = STRICT_MIN_COVERAGE if strict else CREATIVE_MIN_COVERAGE
    passed = bool(matched_terms) and coverage >= minimum_coverage and not high_risk_terms
    return AudioSegmentGroundingResult(
        index=index,
        checked=True,
        passed=passed,
        status="grounded" if passed else "unsupported",
        coverage=round(coverage, 3),
        matched_terms=matched_terms[:12],
        unsupported_terms=unsupported_terms[:12],
        high_risk_terms=high_risk_terms[:8],
        source_chunk_ids=source_ids,
        source_count=len(source_chunks),
    )


def source_chunks_for_segment(segment: dict, source_chunks: list[Chunk]) -> list[Chunk]:
    matched: list[Chunk] = []
    for source in segment.get("sources") or []:
        for chunk in source_chunks:
            if _source_matches_chunk(source, chunk) and chunk not in matched:
                matched.append(chunk)
    return matched or list(source_chunks)


def report_without_segments(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "segments"}


def _source_matches_chunk(source: dict, chunk: Chunk) -> bool:
    metadata = chunk.metadata or {}
    source_doc_id = source.get("doc_id")
    source_filename = source.get("filename")
    if source_doc_id and metadata.get("doc_id") != source_doc_id:
        return False
    if source_filename and metadata.get("filename") != source_filename:
        return False
    if source.get("page") is not None and int(source["page"]) != chunk.page:
        return False
    if source.get("chunk_id") and source["chunk_id"] != chunk.chunk_id:
        return False
    return bool(source_doc_id or source_filename or source.get("chunk_id"))


def _claim_terms(text: str) -> list[str]:
    terms: list[str] = []
    for raw in _TOKEN_PATTERN.findall(text):
        term = _normalize_term(raw)
        if not term or term in _GENERIC_TERMS or term in terms:
            continue
        if term.isdigit() and len(term) == 1:
            continue
        terms.append(term)
    return terms


def _source_terms(chunks: list[Chunk]) -> list[str]:
    terms: list[str] = []
    for chunk in chunks:
        for raw in _TOKEN_PATTERN.findall(chunk.text):
            term = _normalize_term(raw)
            if term and term not in terms:
                terms.append(term)
    return terms


def _normalize_term(value: str) -> str:
    term = value.lower().strip("._+-")
    if not term or not _HANGUL_PATTERN.search(term):
        return term
    for suffix in _KOREAN_SUFFIXES:
        if term.endswith(suffix) and len(term) - len(suffix) >= 2:
            return term[: -len(suffix)]
    return term


def _term_supported(term: str, source_terms: set[str], source_text: str) -> bool:
    if term in source_terms:
        return True
    if _LATIN_OR_NUMBER_PATTERN.fullmatch(term):
        return False
    return len(term) >= 2 and term in source_text


def _high_risk_terms(text: str, unsupported_terms: list[str]) -> list[str]:
    high_risk: list[str] = []
    for term in unsupported_terms:
        if not _LATIN_OR_NUMBER_PATTERN.fullmatch(term) or term in _SAFE_LATIN_TERMS:
            continue
        if term.isdigit() and len(term) == 1:
            continue
        if re.search(rf"\b{re.escape(term)}\s*(?:분|초|개|번째)\b", text.lower()):
            continue
        high_risk.append(term)
    return high_risk


def _is_context_segment(
    text: str,
    claim_terms: list[str],
    matched_terms: list[str],
    high_risk_terms: list[str],
) -> bool:
    if high_risk_terms:
        return False
    if not claim_terms:
        return True
    if len(text) <= 90 and "?" in text and len(matched_terms) <= 1:
        return True
    return len(text) <= 80 and not matched_terms and any(marker in text for marker in _CONTEXT_MARKERS)
