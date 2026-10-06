from __future__ import annotations

from v2.rag.lexical_index import index_for, normalize_retrieval_text
from v2.schemas import Chunk, RetrievalContext, RetrievalResult

__all__ = ["chunks_from_contexts", "normalize_retrieval_text", "retrieve_contexts"]


def retrieve_contexts(
    query: str,
    chunks: list[Chunk],
    top_k: int = 4,
    strategy: str = "hybrid",
) -> RetrievalResult:
    """BM25(+한국어 문자 n-gram) 순위. strategy="lexical"이면 n-gram 신호를 쓰지 않는다."""
    if top_k <= 0 or not chunks or not (query or "").strip():
        return RetrievalResult(query=query, top_k=top_k, contexts=[])

    ranked = index_for(chunks).search(query, top_k=top_k, strategy=strategy)
    contexts = [
        RetrievalContext(
            chunk_id=chunks[index].chunk_id,
            page=chunks[index].page,
            score=round(score, 4),
            text=chunks[index].text,
            char_start=chunks[index].char_start,
            char_end=chunks[index].char_end,
            metadata=chunks[index].metadata,
        )
        for score, index in ranked
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
