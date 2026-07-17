from __future__ import annotations

import unittest
from unittest.mock import patch

from v2.providers.semantic import SemanticHybridRetriever, clear_semantic_caches, reciprocal_rank_fusion
from v2.schemas import Chunk


def _chunk(chunk_id: str, text: str, filename: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        page=1,
        text=text,
        char_start=0,
        char_end=len(text),
        metadata={"doc_id": chunk_id, "filename": filename},
    )


class FakeEncoder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    def encode(self, texts: list[str], **kwargs) -> list[list[float]]:
        return [self.vectors[text] for text in texts]


class FakeReranker:
    def predict(self, pairs: list[tuple[str, str]], **kwargs) -> list[float]:
        return [1.0 if "best evidence" in passage else 0.1 for _, passage in pairs]


class BrokenEncoder:
    def encode(self, texts: list[str], **kwargs) -> list[list[float]]:
        raise RuntimeError("model unavailable")


class CountingEncoder:
    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: list[str], **kwargs) -> list[list[float]]:
        self.calls += 1
        return [[1.0, 0.0] if "question" in text else [0.9, 0.1] for text in texts]


class SemanticRetrievalTest(unittest.TestCase):
    def test_dense_retrieval_finds_semantic_match_without_shared_terms(self) -> None:
        chunks = [
            _chunk("car", "automobile transport", "transport.txt"),
            _chunk("fruit", "banana nutrition", "food.txt"),
        ]
        encoder = FakeEncoder(
            {
                "vehicle question": [1.0, 0.0],
                "automobile transport": [0.95, 0.05],
                "banana nutrition": [0.0, 1.0],
            }
        )

        run = SemanticHybridRetriever(
            embedding_model="fake-model",
            include_lexical=False,
            encoder=encoder,
        ).search_with_details("vehicle question", chunks, top_k=1)

        self.assertEqual(run.retrieval_mode, "semantic")
        self.assertEqual(run.chunks[0].chunk_id, "car")
        self.assertEqual(run.chunks[0].metadata["retrieval_stage"], "dense")
        self.assertFalse(run.fallback_used)

    def test_rrf_rewards_candidates_found_by_both_retrievers(self) -> None:
        first = _chunk("first", "first", "first.txt")
        shared = _chunk("shared", "shared", "shared.txt")
        third = _chunk("third", "third", "third.txt")

        fused = reciprocal_rank_fusion(
            ("lexical", [first, shared]),
            ("dense", [shared, third]),
        )

        self.assertEqual(fused[0].chunk_id, "shared")
        self.assertEqual(fused[0].metadata["retrieval_sources"], ["lexical", "dense"])

    def test_cross_encoder_reranks_only_the_fused_candidates(self) -> None:
        chunks = [
            _chunk("dense-first", "initial candidate", "first.txt"),
            _chunk("reranked", "best evidence", "best.txt"),
        ]
        encoder = FakeEncoder(
            {
                "question": [1.0, 0.0],
                "initial candidate": [0.95, 0.05],
                "best evidence": [0.8, 0.2],
            }
        )

        run = SemanticHybridRetriever(
            embedding_model="fake-model",
            reranker_model="fake-reranker",
            include_lexical=False,
            use_reranker=True,
            encoder=encoder,
            reranker=FakeReranker(),
        ).search_with_details("question", chunks, top_k=2)

        self.assertEqual(run.retrieval_mode, "semantic_rerank")
        self.assertEqual(run.chunks[0].chunk_id, "reranked")
        self.assertEqual(run.chunks[0].metadata["retrieval_stage"], "cross_encoder")
        self.assertTrue(run.reranked)

    def test_embedding_failure_falls_back_to_local_hybrid(self) -> None:
        chunks = [
            _chunk("ocr", "OCR handles scanned PDF pages.", "ocr.txt"),
            _chunk("other", "Banana nutrition facts.", "food.txt"),
        ]

        run = SemanticHybridRetriever(
            embedding_model="broken-model",
            include_lexical=False,
            encoder=BrokenEncoder(),
        ).search_with_details("OCR scanned PDF", chunks, top_k=1)

        self.assertEqual(run.retrieval_mode, "semantic_fallback_hybrid")
        self.assertEqual(run.chunks[0].chunk_id, "ocr")
        self.assertTrue(run.fallback_used)
        self.assertIn("model unavailable", run.warnings[0])

    def test_document_embeddings_are_reused_across_retriever_instances(self) -> None:
        clear_semantic_caches()
        encoder = CountingEncoder()
        chunks = [_chunk("cached", "cached passage", "cached.txt")]

        with patch("v2.providers.semantic._load_sentence_transformer", return_value=encoder):
            first = SemanticHybridRetriever(embedding_model="cache-model", include_lexical=False)
            second = SemanticHybridRetriever(embedding_model="cache-model", include_lexical=False)
            first.search("question", chunks, top_k=1)
            second.search("question", chunks, top_k=1)

        self.assertEqual(encoder.calls, 1)
        clear_semantic_caches()


if __name__ == "__main__":
    unittest.main()
