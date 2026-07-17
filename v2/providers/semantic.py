from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from threading import Lock
from typing import Any

from v2.rag.retrieval import chunks_from_contexts, retrieve_contexts
from v2.schemas import Chunk

DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
_EMBEDDING_CACHE: OrderedDict[tuple[str, str], tuple[float, ...]] = OrderedDict()
_EMBEDDING_CACHE_LOCK = Lock()


@dataclass(slots=True)
class SemanticRetrievalRun:
    chunks: list[Chunk]
    retrieval_mode: str
    implementation: str
    embedding_model: str
    reranker_model: str | None = None
    lexical_candidates: int = 0
    dense_candidates: int = 0
    fused_candidates: int = 0
    candidate_chunks: int = 0
    reranked: bool = False
    fallback_used: bool = False
    warnings: list[str] = field(default_factory=list)

    def details(self) -> dict[str, Any]:
        return {
            "implementation": self.implementation,
            "embedding_model": self.embedding_model,
            "reranker_model": self.reranker_model,
            "lexical_candidates": self.lexical_candidates,
            "dense_candidates": self.dense_candidates,
            "fused_candidates": self.fused_candidates,
            "candidate_chunks": self.candidate_chunks,
            "selected_chunks": len(self.chunks),
            "reranked": self.reranked,
            "fallback_used": self.fallback_used,
        }


class SemanticHybridRetriever:
    def __init__(
        self,
        embedding_model: str | None = None,
        reranker_model: str | None = None,
        *,
        include_lexical: bool = True,
        use_reranker: bool = False,
        candidate_multiplier: int = 4,
        minimum_dense_score: float = 0.1,
        encoder: Any | None = None,
        reranker: Any | None = None,
    ) -> None:
        self.embedding_model = embedding_model or os.environ.get(
            "COURSEBEE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        )
        self.reranker_model = reranker_model or os.environ.get(
            "COURSEBEE_RERANKER_MODEL", DEFAULT_RERANKER_MODEL
        )
        self.include_lexical = include_lexical
        self.use_reranker = use_reranker
        self.candidate_multiplier = max(1, candidate_multiplier)
        self.minimum_dense_score = minimum_dense_score
        self._encoder = encoder
        self._reranker = reranker

    def search(self, question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
        return self.search_with_details(question, chunks, top_k=top_k).chunks

    def search_with_details(self, question: str, chunks: list[Chunk], top_k: int = 4) -> SemanticRetrievalRun:
        if not question.strip() or not chunks or top_k <= 0:
            return SemanticRetrievalRun(
                chunks=[],
                retrieval_mode="semantic_hybrid" if self.include_lexical else "semantic",
                implementation="semantic_empty",
                embedding_model=self.embedding_model,
                candidate_chunks=len(chunks),
            )

        candidate_k = min(len(chunks), max(top_k, top_k * self.candidate_multiplier))
        lexical = self._lexical_candidates(question, chunks, candidate_k) if self.include_lexical else []
        try:
            dense = self._dense_candidates(question, chunks, candidate_k)
        except Exception as exc:  # Model import, download, and runtime failures share the same safe fallback.
            fallback = lexical or self._lexical_candidates(question, chunks, top_k)
            return SemanticRetrievalRun(
                chunks=fallback[:top_k],
                retrieval_mode="semantic_fallback_hybrid",
                implementation="local_hybrid_fallback",
                embedding_model=self.embedding_model,
                lexical_candidates=len(fallback),
                candidate_chunks=len(chunks),
                fallback_used=True,
                warnings=[_model_warning("embedding", exc)],
            )

        if not dense:
            fallback = lexical or self._lexical_candidates(question, chunks, top_k)
            return SemanticRetrievalRun(
                chunks=fallback[:top_k],
                retrieval_mode="semantic_fallback_hybrid",
                implementation="local_hybrid_fallback",
                embedding_model=self.embedding_model,
                lexical_candidates=len(fallback),
                candidate_chunks=len(chunks),
                fallback_used=True,
                warnings=["Semantic embedding search returned no candidates; local hybrid retrieval was used."],
            )

        if self.include_lexical:
            candidates = reciprocal_rank_fusion(("lexical", lexical), ("dense", dense))
            retrieval_mode = "semantic_hybrid"
            implementation = "rrf_lexical_dense"
        else:
            candidates = dense
            retrieval_mode = "semantic"
            implementation = "dense_bi_encoder"

        warnings: list[str] = []
        reranked = False
        if self.use_reranker and candidates:
            try:
                candidates = self._rerank(question, candidates)
                retrieval_mode = "semantic_rerank"
                implementation = "retrieve_rrf_rerank"
                reranked = True
            except Exception as exc:  # Dense/fusion results remain usable if only the reranker fails.
                warnings.append(_model_warning("reranker", exc))

        return SemanticRetrievalRun(
            chunks=candidates[:top_k],
            retrieval_mode=retrieval_mode,
            implementation=implementation,
            embedding_model=self.embedding_model,
            reranker_model=self.reranker_model if self.use_reranker else None,
            lexical_candidates=len(lexical),
            dense_candidates=len(dense),
            fused_candidates=len(candidates),
            candidate_chunks=len(chunks),
            reranked=reranked,
            fallback_used=bool(self.use_reranker and not reranked),
            warnings=warnings,
        )

    def _lexical_candidates(self, question: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        contexts = retrieve_contexts(question, chunks, top_k=top_k, strategy="hybrid").contexts
        return chunks_from_contexts(contexts)

    def _dense_candidates(self, question: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        encoder = self._encoder or _load_sentence_transformer(self.embedding_model)
        query_text = _embedding_text(question, self.embedding_model, is_query=True)
        passage_texts = [_embedding_text(chunk.text, self.embedding_model, is_query=False) for chunk in chunks]
        vectors = _encode(
            encoder,
            self.embedding_model,
            [query_text, *passage_texts],
            use_cache=self._encoder is None,
        )
        query_vector = vectors[0]
        scored = [
            (_dot(query_vector, vector), chunk)
            for vector, chunk in zip(vectors[1:], chunks)
        ]
        scored = [item for item in scored if item[0] >= self.minimum_dense_score]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            _copy_chunk(chunk, score, "dense", ["dense"])
            for score, chunk in scored[:top_k]
        ]

    def _rerank(self, question: str, chunks: list[Chunk]) -> list[Chunk]:
        reranker = self._reranker or _load_cross_encoder(self.reranker_model)
        pairs = [(question, chunk.text) for chunk in chunks]
        try:
            raw_scores = reranker.predict(pairs, show_progress_bar=False)
        except TypeError:
            raw_scores = reranker.predict(pairs)
        scored = sorted(
            ((float(score), chunk) for score, chunk in zip(raw_scores, chunks)),
            key=lambda item: item[0],
            reverse=True,
        )
        return [
            _copy_chunk(
                chunk,
                score,
                "cross_encoder",
                [*chunk.metadata.get("retrieval_sources", []), "reranker"],
                fusion_score=chunk.metadata.get("retrieval_score"),
            )
            for score, chunk in scored
        ]


class EmbeddingRetriever:
    def __init__(self, model: str | None = None, *, encoder: Any | None = None) -> None:
        self._retriever = SemanticHybridRetriever(
            embedding_model=model,
            include_lexical=False,
            encoder=encoder,
        )

    @property
    def model(self) -> str:
        return self._retriever.embedding_model

    def search(self, question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
        return self._retriever.search(question, chunks, top_k=top_k)


def reciprocal_rank_fusion(*rankings: tuple[str, list[Chunk]], rank_constant: int = 60) -> list[Chunk]:
    scores: dict[tuple[Any, ...], float] = {}
    sources: dict[tuple[Any, ...], list[str]] = {}
    chunks_by_key: dict[tuple[Any, ...], Chunk] = {}
    for name, chunks in rankings:
        for rank, chunk in enumerate(chunks, start=1):
            key = _chunk_key(chunk)
            chunks_by_key.setdefault(key, chunk)
            scores[key] = scores.get(key, 0.0) + (1.0 / (rank_constant + rank))
            if name not in sources.setdefault(key, []):
                sources[key].append(name)
    ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [
        _copy_chunk(chunks_by_key[key], scores[key], "rrf", sources[key])
        for key in ordered
    ]


@lru_cache(maxsize=4)
def _load_sentence_transformer(model: str) -> Any:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

    return SentenceTransformer(model)


@lru_cache(maxsize=4)
def _load_cross_encoder(model: str) -> Any:
    from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

    return CrossEncoder(model)


def clear_semantic_caches() -> None:
    _load_sentence_transformer.cache_clear()
    _load_cross_encoder.cache_clear()
    with _EMBEDDING_CACHE_LOCK:
        _EMBEDDING_CACHE.clear()


def _encode(encoder: Any, model: str, texts: list[str], *, use_cache: bool) -> list[tuple[float, ...]]:
    if not use_cache:
        return _encode_batch(encoder, texts)

    vectors_by_text: dict[str, tuple[float, ...]] = {}
    missing: list[str] = []
    with _EMBEDDING_CACHE_LOCK:
        for value in texts:
            key = (model, value)
            cached = _EMBEDDING_CACHE.get(key)
            if cached is not None:
                vectors_by_text[value] = cached
                _EMBEDDING_CACHE.move_to_end(key)
            elif value not in missing:
                missing.append(value)

    if missing:
        encoded = _encode_batch(encoder, missing)
        limit = max(128, int(os.environ.get("COURSEBEE_EMBEDDING_CACHE_SIZE", "4096")))
        with _EMBEDDING_CACHE_LOCK:
            for value, vector in zip(missing, encoded):
                vectors_by_text[value] = vector
                _EMBEDDING_CACHE[(model, value)] = vector
                _EMBEDDING_CACHE.move_to_end((model, value))
            while len(_EMBEDDING_CACHE) > limit:
                _EMBEDDING_CACHE.popitem(last=False)

    return [vectors_by_text[value] for value in texts]


def _encode_batch(encoder: Any, texts: list[str]) -> list[tuple[float, ...]]:
    vectors = encoder.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [tuple(float(value) for value in vector) for vector in vectors]


def _embedding_text(text: str, model: str, *, is_query: bool) -> str:
    if "e5" not in model.lower():
        return text
    return f"{'query' if is_query else 'passage'}: {text}"


def _dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return float(sum(a * b for a, b in zip(left, right)))


def _copy_chunk(
    chunk: Chunk,
    score: float,
    stage: str,
    sources: list[str],
    *,
    fusion_score: float | None = None,
) -> Chunk:
    metadata = {
        **chunk.metadata,
        "retrieval_score": round(float(score), 6),
        "retrieval_stage": stage,
        "retrieval_sources": list(dict.fromkeys(sources)),
    }
    if fusion_score is not None:
        metadata["fusion_score"] = fusion_score
    return Chunk(
        chunk_id=chunk.chunk_id,
        page=chunk.page,
        text=chunk.text,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        metadata=metadata,
    )


def _chunk_key(chunk: Chunk) -> tuple[Any, ...]:
    metadata = chunk.metadata or {}
    return (
        metadata.get("doc_id"),
        metadata.get("filename"),
        chunk.page,
        chunk.chunk_id,
    )


def _model_warning(stage: str, exc: Exception) -> str:
    message = " ".join(str(exc).split())[:240]
    return f"Semantic {stage} failed ({type(exc).__name__}: {message}); a lower-cost retrieval stage was used."
