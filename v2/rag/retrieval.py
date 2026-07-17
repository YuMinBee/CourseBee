from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from v2.schemas import Chunk, RetrievalContext, RetrievalResult

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\uac00-\ud7a3]+")
_KOREAN_SUFFIXES = (
    "으로부터",
    "에서부터",
    "이라고",
    "이라는",
    "에서는",
    "에게서",
    "까지는",
    "부터는",
    "입니다",
    "인가요",
    "이라면",
    "처럼",
    "보다",
    "으로",
    "에서",
    "에게",
    "한테",
    "에는",
    "에도",
    "의",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "와",
    "과",
    "에",
    "로",
    "도",
    "만",
)


def retrieve_contexts(
    query: str,
    chunks: list[Chunk],
    top_k: int = 4,
    strategy: str = "hybrid",
) -> RetrievalResult:
    query_terms = _tokenize(query)
    if not query_terms or top_k <= 0:
        return RetrievalResult(query=query, top_k=top_k, contexts=[])

    document_frequency = _document_frequency(chunks)
    total_docs = max(len(chunks), 1)
    scored: list[tuple[float, Chunk]] = []
    query_features = _character_features(query)
    normalized_query = _normalized_text(query)

    for chunk in chunks:
        chunk_terms = _tokenize(chunk.text)
        if not chunk_terms:
            continue
        term_counts = Counter(chunk_terms)
        lexical_score = 0.0
        for term in query_terms:
            if term not in term_counts:
                continue
            tf = term_counts[term] / len(chunk_terms)
            idf = math.log((1 + total_docs) / (1 + document_frequency.get(term, 0))) + 1
            lexical_score += tf * idf

        character_score = 0.0
        if strategy == "hybrid":
            character_score = _feature_similarity(query_features, _character_features(chunk.text))
            minimum_character_score = 0.18 if _contains_hangul(query) else 0.28
            if lexical_score == 0 and character_score < minimum_character_score:
                character_score = 0.0
        normalized_chunk = _normalized_text(chunk.text)
        phrase_bonus = 0.3 if normalized_query and normalized_query in normalized_chunk else 0.0
        score = lexical_score + (character_score * 0.75) + phrase_bonus
        if score >= 0.08:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    contexts = [
        RetrievalContext(
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            score=round(score, 4),
            text=chunk.text,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            metadata=chunk.metadata,
        )
        for score, chunk in scored[:top_k]
    ]
    return RetrievalResult(query=query, top_k=top_k, contexts=contexts)


def chunks_from_contexts(contexts: list[RetrievalContext]) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=context.chunk_id,
            page=context.page,
            text=context.text,
            char_start=context.char_start or 0,
            char_end=context.char_end or len(context.text),
            metadata={**context.metadata, "retrieval_score": context.score},
        )
        for context in contexts
    ]


def _document_frequency(chunks: list[Chunk]) -> dict[str, int]:
    frequency: dict[str, int] = {}
    for chunk in chunks:
        for term in set(_tokenize(chunk.text)):
            frequency[term] = frequency.get(term, 0) + 1
    return frequency


def _tokenize(text: str) -> list[str]:
    terms: list[str] = []
    for match in _TOKEN_PATTERN.finditer(normalize_retrieval_text(text)):
        raw = match.group(0).lower()
        normalized = _strip_korean_suffix(raw) if _contains_hangul(raw) else raw
        for term in (raw, normalized):
            if len(term) >= 2 and term not in terms:
                terms.append(term)
    return terms


def normalize_retrieval_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").replace("\u00ad", "")
    normalized = re.sub(r"(?<=[A-Za-z])-[ \t]*\r?\n[ \t]*(?=[A-Za-z])", "", normalized)
    return re.sub(r"(?<=[A-Za-z])-[ \t]+(?=[A-Za-z])", "", normalized)


def _strip_korean_suffix(token: str) -> str:
    for suffix in _KOREAN_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[: -len(suffix)]
    return token


def _contains_hangul(text: str) -> bool:
    return any("가" <= char <= "힣" for char in text)


def _normalized_text(text: str) -> str:
    return "".join(_tokenize(text))


def _character_features(text: str) -> set[str]:
    features: set[str] = set()
    for token in _tokenize(text):
        if not _contains_hangul(token):
            continue
        compact = re.sub(r"[^0-9a-z가-힣]", "", token.lower())
        if len(compact) < 2:
            continue
        features.add(compact)
        for size in (2, 3):
            features.update(
                compact[index : index + size]
                for index in range(max(0, len(compact) - size + 1))
            )
    return features


def _feature_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    if not overlap:
        return 0.0
    return overlap / math.sqrt(len(left) * len(right))
