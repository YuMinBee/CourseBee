from __future__ import annotations

import re
from collections import Counter, OrderedDict

from v2.graph.concept_map import build_concept_map, extract_concepts
from v2.providers.openai import OpenAIProvider, OpenAIProviderError
from v2.rag.answering import _best_sentence, _keyword_terms, _sources_from_chunks
from v2.rag.citations import check_text_grounding, skipped_citation_check
from v2.schemas import Chunk
from v2.study_kit import KNOWN_TERMS


def generate_course_pack_summary(
    chunks: list[Chunk],
    llm_provider: str = "mock",
    llm_model: str | None = None,
    max_items: int = 5,
) -> dict:
    warnings: list[str] = []
    if not chunks:
        return {
            "overview": {"text": "", "sources": []},
            "lecture_summaries": [],
            "key_concepts": [],
            "connections": [],
            "review_points": [],
            "sources": [],
            "llm": {"provider": llm_provider, "model": llm_model, "status": "skipped"},
            "citation_check": skipped_citation_check("No source chunks were provided.").to_dict(),
            "warnings": ["No source chunks were provided. Course Pack summary generation was skipped."],
        }

    grouped = _group_chunks_by_document(chunks)
    representatives = [_representative_chunk(group) for group in grouped.values()]
    representatives = [chunk for chunk in representatives if chunk is not None]
    source_chunks = representatives or chunks[:max_items]
    key_concepts = _key_concepts(chunks, limit=max_items)
    lecture_summaries = [_lecture_summary(group) for group in grouped.values()]
    rule_overview_text = _rule_overview(grouped, key_concepts)
    overview = {
        "text": rule_overview_text,
        "sources": _source_dicts(source_chunks),
    }
    citation_check = skipped_citation_check("Rule/mock summary does not require API citation validation.", source_chunks)
    llm_status = "mock"
    model = llm_model

    if llm_provider == "openai":
        provider = OpenAIProvider(model=llm_model)
        model = provider.model
        if not provider.available:
            llm_status = "fallback"
            warnings.append("OPENAI_API_KEY is not set. Falling back to rule-based summary.")
        else:
            try:
                refined = provider.summarize(source_chunks)
                if refined.strip():
                    candidate_check = check_text_grounding(refined, source_chunks)
                    if candidate_check.passed:
                        overview["text"] = refined.strip()
                        citation_check = candidate_check
                        llm_status = "used"
                    else:
                        citation_check = candidate_check
                        llm_status = "fallback"
                        warnings.extend(candidate_check.warnings)
                        warnings.append("OpenAIProvider summary failed citation_check. Falling back to rule-based summary.")
                else:
                    llm_status = "fallback"
                    warnings.append("OpenAIProvider returned an empty summary. Falling back to rule-based summary.")
            except OpenAIProviderError as exc:
                llm_status = "fallback"
                warnings.append(f"OpenAIProvider failed. Falling back to rule-based summary: {exc}")
    elif llm_provider not in {"mock", "rule", "local"}:
        llm_status = "fallback"
        warnings.append(f"Unsupported llm_provider '{llm_provider}'. Falling back to rule-based summary.")

    return {
        "overview": overview,
        "lecture_summaries": lecture_summaries,
        "key_concepts": key_concepts,
        "connections": _connections_from_concepts(chunks, key_concepts, limit=max_items),
        "review_points": _review_points(lecture_summaries, limit=max_items),
        "sources": _source_dicts(source_chunks),
        "llm": {"provider": llm_provider, "model": model, "status": llm_status},
        "citation_check": citation_check.to_dict(),
        "warnings": warnings,
    }


def _group_chunks_by_document(chunks: list[Chunk]) -> OrderedDict[str, list[Chunk]]:
    groups: OrderedDict[str, list[Chunk]] = OrderedDict()
    for chunk in chunks:
        metadata = chunk.metadata or {}
        key = str(metadata.get("doc_id") or metadata.get("filename") or "document")
        groups.setdefault(key, []).append(chunk)
    return groups


def _representative_chunk(chunks: list[Chunk]) -> Chunk | None:
    if not chunks:
        return None
    meaningful = [chunk for chunk in chunks if len(chunk.text.strip()) >= 30]
    candidates = meaningful or chunks
    return max(candidates, key=lambda chunk: (len(_keyword_terms(chunk.text)), min(len(chunk.text), 1200)))


def _lecture_summary(chunks: list[Chunk]) -> dict:
    chunk = _representative_chunk(chunks)
    if chunk is None:
        return {"filename": None, "doc_id": None, "text": "", "sources": []}
    metadata = chunk.metadata or {}
    filename = metadata.get("filename")
    source_chunks = chunks[:3]
    sentences: list[str] = []
    for source_chunk in source_chunks:
        sentence = _best_sentence(source_chunk.text, _keyword_terms(source_chunk.text))
        if sentence and sentence not in sentences:
            sentences.append(sentence)
    summary_text = " ".join(sentences)[:900]
    return {
        "filename": filename,
        "doc_id": metadata.get("doc_id"),
        "text": f"{filename or '이 강의자료'}의 핵심 내용은 다음과 같습니다. {summary_text}",
        "sources": _source_dicts(source_chunks),
    }


def _rule_overview(grouped: OrderedDict[str, list[Chunk]], key_concepts: list[dict]) -> str:
    filenames = [_filename_for_group(group) for group in grouped.values()]
    concept_terms = [item["term"] for item in key_concepts[:4]]
    file_part = ", ".join(name for name in filenames if name)
    concept_part = ", ".join(concept_terms) if concept_terms else "핵심 개념"
    return (
        f"이 Course Pack은 {len(grouped)}개의 강의자료를 묶어 {concept_part}를 중심으로 학습 흐름을 정리합니다. "
        f"각 요약과 복습 포인트는 검색된 chunk의 파일명, 페이지, chunk_id를 근거로 제공합니다."
        + (f" 대상 자료: {file_part}." if file_part else "")
    )


def _filename_for_group(chunks: list[Chunk]) -> str | None:
    for chunk in chunks:
        filename = (chunk.metadata or {}).get("filename")
        if filename:
            return str(filename)
    return None


def _key_concepts(chunks: list[Chunk], limit: int) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for chunk in chunks:
        lowered = chunk.text.lower()
        candidates = [
            *[term for term in KNOWN_TERMS if term.lower() in lowered],
            *extract_concepts(chunk.text, limit=max(limit * 2, 10)),
        ]
        for term in candidates:
            normalized = term.lower()
            if normalized in seen:
                continue
            sentence = _sentence_for_term(term, chunk.text)
            items.append(
                {
                    "term": term,
                    "description": sentence or KNOWN_TERMS.get(term) or f"Course Pack에서 확인된 주요 개념입니다: {term}.",
                    "source_quote": sentence,
                    "sources": _source_dicts([chunk]),
                }
            )
            seen.add(normalized)
            if len(items) >= limit:
                return items

    if items:
        return items

    counts: Counter[str] = Counter()
    first_source: dict[str, Chunk] = {}
    for chunk in chunks:
        for token in _tokens(chunk.text):
            counts[token] += 1
            first_source.setdefault(token, chunk)
    for term, _ in counts.most_common(limit):
        chunk = first_source[term]
        items.append(
            {
                "term": term,
                "description": f"Course Pack 근거에서 반복적으로 등장하는 주요 표현입니다: {term}.",
                "sources": _source_dicts([chunk]),
            }
        )
    return items


def _connections_from_concepts(chunks: list[Chunk], key_concepts: list[dict], limit: int) -> list[dict]:
    terms = {item["term"] for item in key_concepts}
    graph = build_concept_map(chunks)
    connections: list[dict] = []
    for edge in graph.get("edges", []):
        if edge.get("edge_type") != "conceptual":
            continue
        if edge.get("source") not in terms and edge.get("target") not in terms:
            continue
        connections.append(
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "relation": edge.get("relation", "related_in_context"),
                "evidence": edge.get("evidence", []),
            }
        )
        if len(connections) >= limit:
            return connections
    return connections


def _review_points(lecture_summaries: list[dict], limit: int) -> list[dict]:
    points: list[dict] = []
    for item in lecture_summaries[:limit]:
        filename = item.get("filename") or "이 강의자료"
        points.append(
            {
                "text": f"{filename}의 대표 근거를 기준으로 핵심 개념과 페이지 출처를 함께 복습하세요.",
                "sources": item.get("sources", []),
            }
        )
    return points


def _tokens(text: str) -> list[str]:
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "week",
        "source",
        "document",
        "강의자료",
        "자연어처리",
        "페이지",
        "한다",
        "있다",
        "대한",
        "작업",
        "처리",
    }
    tokens = re.findall(r"[A-Za-z0-9가-힣_-]{3,}", text)
    return [token for token in tokens if token.lower() not in stopwords]


def _sentence_for_term(term: str, text: str) -> str:
    compact_term = re.sub(r"\s+", "", term).lower()
    for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", text):
        sentence = sentence.strip()
        if sentence and compact_term in re.sub(r"\s+", "", sentence).lower():
            return sentence[:360]
    return _best_sentence(text, _keyword_terms(term))[:360]


def _source_dicts(chunks: list[Chunk]) -> list[dict]:
    return [source.to_dict() for source in _sources_from_chunks(chunks)]


