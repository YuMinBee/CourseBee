from __future__ import annotations

import json
import unittest
from threading import Event
from unittest.mock import patch

from v2.providers.base import (
    IndexProvider,
    LLMProvider,
    ParserProvider,
    RetrieverProvider,
    StorageProvider,
    TTSProvider,
    WebSearchProvider,
)
from v2.providers.local import (
    LexicalRetriever,
    LocalIndexProvider,
    LocalParserProvider,
    LocalStorageProvider,
    MockLLMProvider,
    MockTTSProvider,
    SimpleRetriever,
)
from v2.providers.ollama import OllamaProvider, OllamaProviderError


class ProviderStructureTest(unittest.TestCase):
    def test_cloud_ready_provider_classes_exist(self) -> None:
        self.assertIsNotNone(StorageProvider)
        self.assertIsNotNone(LLMProvider)
        self.assertIsNotNone(TTSProvider)
        self.assertIsNotNone(RetrieverProvider)
        self.assertIsNotNone(IndexProvider)
        self.assertIsNotNone(ParserProvider)
        self.assertIsNotNone(WebSearchProvider)
        self.assertTrue(hasattr(LocalStorageProvider(), "save_json"))
        self.assertTrue(hasattr(MockLLMProvider(), "answer"))
        self.assertTrue(hasattr(MockTTSProvider(), "synthesize"))
        self.assertTrue(hasattr(LocalIndexProvider(), "search"))
        self.assertTrue(hasattr(LexicalRetriever(), "search"))
        self.assertTrue(hasattr(SimpleRetriever(), "search"))
        self.assertTrue(hasattr(LocalParserProvider(), "parse"))


    def test_lexical_retriever_returns_ranked_chunks(self) -> None:
        from v2.rag.chunking import chunk_pages
        from v2.schemas import PageMarkdown

        chunks = chunk_pages(
            [
                PageMarkdown(page_number=1, markdown="BPE reduces OOV", parser="txt"),
                PageMarkdown(page_number=2, markdown="CNN captures local pattern", parser="txt"),
            ],
            max_chars=100,
            filename="sample.txt",
        )

        result = LexicalRetriever().search("CNN local pattern", chunks, top_k=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].page, 2)
        self.assertEqual(result[0].metadata["filename"], "sample.txt")

    def test_mock_tts_provider_is_non_generating(self) -> None:
        self.assertIsNone(MockTTSProvider().synthesize("doc", "script"))

    def test_ollama_provider_emits_stream_tokens_and_combines_answer(self) -> None:
        class FakeStreamResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args) -> None:
                return None

            def __iter__(self):
                events = [
                    {"response": "강화", "done": False},
                    {"response": "학습", "done": True},
                ]
                return iter([(json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8") for event in events])

        tokens: list[str] = []
        provider = OllamaProvider(model="test-model", stream_callback=tokens.append)
        with patch("v2.providers.ollama.urllib.request.urlopen", return_value=FakeStreamResponse()):
            result = provider.answer("강화학습이란?", [], [])

        self.assertEqual(tokens, ["강화", "학습"])
        self.assertEqual(result.answer, "강화학습")

    def test_ollama_stream_honors_cancel_event_between_tokens(self) -> None:
        class FakeStreamResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args) -> None:
                return None

            def __iter__(self):
                events = [
                    {"response": "첫 토큰", "done": False},
                    {"response": "취소 뒤 토큰", "done": False},
                ]
                return iter([(json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8") for event in events])

        cancel_event = Event()
        tokens: list[str] = []

        def on_token(text: str) -> None:
            tokens.append(text)
            cancel_event.set()

        provider = OllamaProvider(model="test-model", stream_callback=on_token, cancel_event=cancel_event)
        with patch("v2.providers.ollama.urllib.request.urlopen", return_value=FakeStreamResponse()):
            with self.assertRaises(OllamaProviderError):
                provider.answer("질문", [], [])

        self.assertEqual(tokens, ["첫 토큰"])

    def test_ollama_podcast_prompt_prioritizes_requested_length(self) -> None:
        from v2.rag.chunking import chunk_pages
        from v2.schemas import PageMarkdown

        chunks = chunk_pages(
            [PageMarkdown(page_number=1, markdown="BPE reduces OOV with subword tokenization.", parser="txt")],
            max_chars=100,
            filename="sample.txt",
        )
        provider = OllamaProvider(model="test-model")

        with patch.object(provider, "_generate", return_value="HOST: 시작합니다.\nGUEST: 설명합니다.") as generate:
            provider.generate_script(chunks, minutes=5, style="podcast", target_chars=2200)

        prompt = generate.call_args.args[0]
        self.assertIn("2200-2530 Korean characters", prompt)
        self.assertIn("at least 1980 characters", prompt)
        self.assertGreater(prompt.index("FINAL LENGTH REQUIREMENT"), prompt.index("PODCAST TEMPLATE"))
        self.assertGreater(prompt.index("FINAL SOURCE BOUNDARY"), prompt.index("SOURCE CHUNKS"))
        self.assertIn("explain the concept without inventing one", prompt)


if __name__ == "__main__":
    unittest.main()
