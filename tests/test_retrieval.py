from __future__ import annotations

import unittest

from v2.providers.mock import MockIndexProvider, MockLLMProvider
from v2.rag.chunking import chunk_pages
from v2.rag.retrieval import retrieve_contexts
from v2.rag.vector_rag import NO_CONTEXT_ANSWER, answer_with_sources
from v2.schemas import Chunk, PageMarkdown


class RetrievalTest(unittest.TestCase):
    def test_retrieve_contexts_keeps_page_and_score(self) -> None:
        chunks = chunk_pages(
            [
                PageMarkdown(page_number=1, markdown="cache reduces repeated OCR cost", parser="txt"),
                PageMarkdown(page_number=2, markdown="request_id enables failure tracking", parser="txt"),
            ],
            max_chars=100,
            filename="sample.txt",
        )

        result = retrieve_contexts("failure tracking", chunks, top_k=1)

        self.assertEqual(result.query, "failure tracking")
        self.assertEqual(result.top_k, 1)
        self.assertEqual(len(result.contexts), 1)
        self.assertEqual(result.contexts[0].chunk_id, "p2_c1")
        self.assertEqual(result.contexts[0].page, 2)
        self.assertGreater(result.contexts[0].score, 0)
        self.assertEqual(result.contexts[0].metadata["filename"], "sample.txt")

    def test_retrieve_contexts_returns_empty_for_no_match(self) -> None:
        chunks = chunk_pages([PageMarkdown(page_number=1, markdown="cache cost", parser="txt")])

        result = retrieve_contexts("unrelated banana", chunks, top_k=4)

        self.assertEqual(result.contexts, [])

    def test_english_character_fragments_do_not_create_false_matches(self) -> None:
        chunks = chunk_pages(
            [PageMarkdown(page_number=1, markdown="Tokenizer and subword tokenization reduce OOV.", parser="txt")]
        )

        result = retrieve_contexts("Transformer와 Attention은 어떤 관계야?", chunks, top_k=4)

        self.assertEqual(result.contexts, [])

    def test_ocr_line_break_hyphenation_is_normalized(self) -> None:
        chunks = [
            Chunk(
                chunk_id="ocr-1",
                page=1,
                text="A cir-\ncuit breaker prevents cascading fail-\nures in distributed systems.",
                char_start=0,
                char_end=75,
                metadata={"filename": "scanned-operations.pdf"},
            ),
            Chunk(
                chunk_id="noise-1",
                page=1,
                text="The release calendar lists maintenance windows.",
                char_start=0,
                char_end=47,
                metadata={"filename": "calendar.txt"},
            ),
        ]

        result = retrieve_contexts("circuit breaker cascading failures", chunks, top_k=2)

        self.assertEqual([context.chunk_id for context in result.contexts], ["ocr-1"])

    def test_source_grounded_answer_does_not_hallucinate_without_context(self) -> None:
        chunks = chunk_pages([PageMarkdown(page_number=1, markdown="cache cost", parser="txt")])

        answer = answer_with_sources(
            question="unrelated banana",
            chunks=chunks,
            index_provider=MockIndexProvider(),
            llm_provider=MockLLMProvider(),
        )

        self.assertEqual(answer.answer, NO_CONTEXT_ANSWER)
        self.assertEqual(answer.vector_sources, [])


if __name__ == "__main__":
    unittest.main()
