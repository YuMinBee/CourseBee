from __future__ import annotations

import re

from v2.providers.base import IndexProvider, LLMProvider
from v2.rag.retrieval import normalize_retrieval_text
from v2.schemas import Chunk, SourceGroundedAnswer, SourceRef

NO_CONTEXT_WARNING = "No relevant context was found in the document. Answer generation was skipped."
GENERAL_FALLBACK_WARNING = "No relevant course context was found. The answer was generated from the LLM general knowledge without source citations."


def generate_source_grounded_answer(
    query: str,
    chunks: list[Chunk],
    index_provider: IndexProvider,
    llm_provider: LLMProvider | None = None,
    top_k: int = 4,
    allow_general_fallback: bool = False,
) -> SourceGroundedAnswer:
    selected_chunks = index_provider.search(query, chunks, top_k=top_k)
    warnings: list[str] = []
    if not selected_chunks:
        if allow_general_fallback and llm_provider is not None and llm_provider.__class__.__name__ != "MockLLMProvider":
            try:
                answer = llm_provider.answer(query, [], []).answer.strip()
            except Exception as exc:  # pragma: no cover - provider failures are runtime-dependent
                warnings.append(f"LLM general fallback failed: {exc}")
            else:
                if answer:
                    return SourceGroundedAnswer(
                        answer=answer,
                        sources=[],
                        warnings=[GENERAL_FALLBACK_WARNING, *warnings],
                        answer_scope="general_knowledge",
                        grounding_status="ungrounded",
                        general_knowledge_used=True,
                    )
        return SourceGroundedAnswer(
            answer="",
            sources=[],
            warnings=[NO_CONTEXT_WARNING, *warnings],
            answer_scope="none",
            grounding_status="not_answered",
        )

    sources = _sources_from_chunks(selected_chunks)
    answer = ""
    if llm_provider is not None and llm_provider.__class__.__name__ != "MockLLMProvider":
        try:
            answer = llm_provider.answer(query, selected_chunks, []).answer.strip()
        except Exception as exc:  # pragma: no cover - provider failures are runtime-dependent
            warnings.append(f"LLM answer generation failed; falling back to source composer: {exc}")
    if not answer:
        answer = _compose_grounded_answer(query, selected_chunks)
    if not answer.strip():
        return SourceGroundedAnswer(
            answer="",
            sources=[],
            warnings=[NO_CONTEXT_WARNING],
            answer_scope="none",
            grounding_status="not_answered",
        )
    return SourceGroundedAnswer(answer=answer, sources=sources, warnings=warnings)


def _compose_grounded_answer(query: str, chunks: list[Chunk]) -> str:
    evidence_items = _evidence_items(query, chunks, limit=4)
    if not evidence_items:
        return ""

    heading = "검색된 문서 근거만 기준으로 정리하면 다음과 같습니다."
    bullets = [f"- {label}: {sentence}" for label, sentence in evidence_items]
    source_hint = _source_hint(chunks[: len(evidence_items)])
    if source_hint:
        return "\n".join([heading, *bullets, f"근거 위치: {source_hint}"])
    return "\n".join([heading, *bullets])


def _evidence_items(query: str, chunks: list[Chunk], limit: int = 4) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    seen_sentences: set[str] = set()
    query_terms = _keyword_terms(query)
    for chunk in chunks:
        sentence = _best_sentence(chunk.text, query_terms)
        if not sentence or sentence in seen_sentences:
            continue
        items.append((_source_label(chunk), sentence))
        seen_sentences.add(sentence)
        if len(items) >= limit:
            break
    return items


def _best_sentence(text: str, query_terms: list[str]) -> str:
    fragments = [_clean_text(part, max_chars=180) for part in _split_sentences(text)]
    fragments = [fragment for fragment in fragments if fragment]
    if not fragments:
        return ""

    candidates = _merge_nearby_fragments(fragments)
    if not query_terms:
        return candidates[0]

    def score(sentence: str) -> tuple[float, int]:
        lowered = sentence.lower()
        hits = sum(1 for term in query_terms if term in lowered)
        has_hangul = any("가" <= char <= "힣" for char in sentence)
        quality = 0.0
        if has_hangul:
            quality += 2.0
        if len(sentence) >= 35:
            quality += 2.0
        if len(sentence) < 20:
            quality -= 2.0
        if sentence.endswith((".", "다", "다.", "요", "요.")):
            quality += 0.5
        return hits + quality, min(len(sentence), 500)

    best = max(candidates, key=score)
    return best if score(best)[0] > 0 else candidates[0]


def _merge_nearby_fragments(fragments: list[str]) -> list[str]:
    candidates: list[str] = []
    for index in range(len(fragments)):
        merged = " ".join(fragments[index : index + 6]).strip()
        if merged:
            candidates.append(_clean_text(merged))
    candidates.extend(fragments)
    return candidates


def _source_hint(chunks: list[Chunk]) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        label = _source_label(chunk)
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
    return ", ".join(labels)


def _source_label(chunk: Chunk) -> str:
    filename = chunk.metadata.get("filename") if chunk.metadata else None
    base = filename or "문서"
    return f"{base} {chunk.page}페이지/{chunk.chunk_id}"


def _sources_from_chunks(chunks: list[Chunk]) -> list[SourceRef]:
    sources: list[SourceRef] = []
    seen: set[tuple[str | None, str | None, int, str]] = set()
    for chunk in chunks:
        doc_id = chunk.metadata.get("doc_id") if chunk.metadata else None
        filename = chunk.metadata.get("filename") if chunk.metadata else None
        week = chunk.metadata.get("week") if chunk.metadata else None
        lecture_no = chunk.metadata.get("lecture_no") if chunk.metadata else None
        title = chunk.metadata.get("title") if chunk.metadata else None
        url = chunk.metadata.get("url") if chunk.metadata else None
        source_type = chunk.metadata.get("source_type") if chunk.metadata else None
        provider = chunk.metadata.get("web_provider") if chunk.metadata else None
        key = (doc_id, filename, chunk.page, chunk.chunk_id)
        if key in seen:
            continue
        sources.append(
            SourceRef(
                page=chunk.page,
                chunk_id=chunk.chunk_id,
                doc_id=doc_id,
                filename=filename,
                week=week,
                lecture_no=lecture_no,
                excerpt=_clean_text(chunk.text, max_chars=700),
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                title=title,
                url=url,
                source_type=source_type,
                provider=provider,
            )
        )
        seen.add(key)
    return sources


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+|(?<=다\.)\s*", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _clean_text(text: str, max_chars: int = 260) -> str:
    cleaned = " ".join(normalize_retrieval_text(text).split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "..."


def _keyword_terms(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9가-힣_-]{2,}", text.lower())
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "document",
        "source",
        "이",
        "그",
        "저",
        "내용",
        "핵심",
        "설명",
        "정리",
        "자료",
    }
    terms: list[str] = []
    for token in tokens:
        if token in stopwords or token in terms:
            continue
        terms.append(token)
    return terms


