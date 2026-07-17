from __future__ import annotations

import re

LEARNING_PATH_TERMS = {
    "먼저",
    "이해하려면",
    "선수",
    "기초",
    "순서",
    "prerequisite",
    "before",
    "learning path",
    "배우기 전",
    "알아야",
    "선행",
    "사전에",
    "전에",
}
OVERVIEW_TERMS = {
    "전체",
    "흐름",
    "개요",
    "요약",
    "정리",
    "주차",
    "course pack",
    "overview",
    "summary",
    "summarize",
    "한눈에",
    "전반",
    "종합",
    "무엇을 배웠",
}
RELATION_TERMS = {
    "관계",
    "연결",
    "관련",
    "이어",
    "차이",
    "비교",
    "대조",
    "pipeline",
    "connect",
    "relationship",
    "related",
    "relation",
    "contrast",
    "compare",
    "영향",
    "미치는",
    "연관",
    "연계",
    "상호작용",
    "연결고리",
}
FACT_TERMS = {
    "정의",
    "뜻",
    "뭐야",
    "무엇",
    "설명",
    "definition",
    "what is",
    "explain",
}


def classify_course_pack_question(question: str) -> dict:
    normalized = _normalize(question)
    has_learning_path = _has_any(normalized, LEARNING_PATH_TERMS)
    has_overview = _has_any(normalized, OVERVIEW_TERMS) or _looks_like_week_overview(normalized)
    entity_count = len(set(re.findall(r"\b[A-Z][A-Z0-9_-]{1,}\b", question or "")))
    has_relation = _has_any(normalized, RELATION_TERMS) or (
        entity_count >= 2 and _has_any(normalized, {"어떻게", "왜", "같이"})
    )
    has_fact = _has_any(normalized, FACT_TERMS)

    if has_learning_path:
        question_type = "learning_path_question"
        selected_mode = "local_graph"
        plan = [
            _plan("high", "course_graph", "Question asks for prerequisite or learning path traversal."),
            _plan("low", "evidence_chunks", "Ground the graph path in source chunks."),
        ]
    elif has_overview and has_relation:
        question_type = "mixed_question"
        selected_mode = "hierarchical"
        plan = [
            _plan("high", "hierarchical_summary", "Question asks for cross-lecture flow or overview."),
            _plan("high", "course_graph", "Relation terms indicate concepts may need graph follow-up."),
            _plan("low", "evidence_chunks", "Return supporting chunks for provenance."),
        ]
    elif has_overview:
        question_type = "overview_question"
        selected_mode = "hierarchical"
        plan = [
            _plan("high", "hierarchical_summary", "Question asks for course-level or lecture-level overview."),
            _plan("low", "supporting_chunks", "Attach representative source chunks."),
        ]
    elif has_relation:
        question_type = "relation_question"
        selected_mode = "local_graph"
        plan = [
            _plan("high", "course_graph", "Question asks about concept relationships or paths."),
            _plan("low", "evidence_chunks", "Use evidence chunks attached to graph edges."),
        ]
    else:
        question_type = "fact_question"
        selected_mode = "vector"
        plan = [
            _plan("low", "vector", "Question uses the local hybrid lexical and character-level implementation."),
        ]

    return {
        "question_type": question_type,
        "selected_mode": selected_mode,
        "selected_retrievers": [item["strategy"] for item in plan],
        "retrieval_plan": plan,
        "retrieval_implementation": "hybrid" if selected_mode == "vector" else selected_mode,
        "confidence": _route_confidence(has_learning_path, has_overview, has_relation, has_fact, normalized),
    }


def _plan(level: str, strategy: str, reason: str) -> dict:
    return {"level": level, "strategy": strategy, "reason": reason}


def _has_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def _looks_like_week_overview(text: str) -> bool:
    return bool(re.search(r"\d+\s*주(?:차| 동안)", text)) and _has_any(text, {"배웠", "내용", "다룬", "보여"})


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _route_confidence(*signals) -> float:
    normalized = signals[-1]
    matched = sum(bool(signal) for signal in signals[:-1])
    if not normalized:
        return 0.0
    return round(min(0.98, 0.55 + (0.12 * matched)), 2)
