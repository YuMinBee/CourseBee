from __future__ import annotations

import unittest
from unittest.mock import patch

from v2.audio_script import generate_audio_script
from v2.graph.concept_map import build_concept_map
from v2.providers.mock import MockIndexProvider, MockLLMProvider
from v2.rag.answering import NO_CONTEXT_WARNING, generate_source_grounded_answer
from v2.rag.chunking import chunk_pages
from v2.rag.citations import check_text_grounding
from v2.schemas import AnswerWithSources, PageMarkdown
from v2.study_kit import generate_study_kit


class SourceGroundedGenerationTest(unittest.TestCase):
    def _chunks(self):
        return chunk_pages(
            [
                PageMarkdown(
                    page_number=1,
                    markdown="BeePDF structures PDF processing and keeps page citations for RAG answers.",
                    parser="txt",
                ),
                PageMarkdown(
                    page_number=2,
                    markdown="OCR fallback handles scanned PDFs. sha256 cache reduces repeated processing cost.",
                    parser="txt",
                ),
            ],
            max_chars=120,
            filename="sample.txt",
        )

    def test_source_grounded_answer_has_real_sources(self) -> None:
        result = generate_source_grounded_answer(
            query="PDF page citations",
            chunks=self._chunks(),
            index_provider=MockIndexProvider(),
            llm_provider=MockLLMProvider(),
            top_k=2,
        )

        payload = result.to_dict()
        self.assertTrue(payload["answer"])
        self.assertIn("검색된 문서 근거", payload["answer"])
        self.assertNotIn("Based on the retrieved source chunks", payload["answer"])
        self.assertGreaterEqual(len(payload["sources"]), 1)
        self.assertEqual(payload["sources"][0]["page"], 1)
        self.assertEqual(payload["sources"][0]["chunk_id"], "p1_c1")
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["answer_scope"], "course_pack")
        self.assertEqual(payload["grounding_status"], "grounded")
        self.assertFalse(payload["general_knowledge_used"])

    def test_source_grounded_answer_skips_when_no_context(self) -> None:
        result = generate_source_grounded_answer(
            query="unrelated banana",
            chunks=self._chunks(),
            index_provider=MockIndexProvider(),
            llm_provider=MockLLMProvider(),
        )

        self.assertEqual(result.answer, "")
        self.assertEqual(result.sources, [])
        self.assertEqual(result.warnings, [NO_CONTEXT_WARNING])
        self.assertEqual(result.answer_scope, "none")
        self.assertEqual(result.grounding_status, "not_answered")
        self.assertFalse(result.general_knowledge_used)

    def test_general_knowledge_fallback_is_explicitly_ungrounded(self) -> None:
        class GeneralKnowledgeProvider:
            def answer(self, question, chunks, graph_context):
                return AnswerWithSources(answer="자료에서는 확인되지 않지만 일반지식으로 설명합니다.")

        result = generate_source_grounded_answer(
            query="unrelated reinforcement learning",
            chunks=self._chunks(),
            index_provider=MockIndexProvider(),
            llm_provider=GeneralKnowledgeProvider(),
            allow_general_fallback=True,
        )

        self.assertTrue(result.answer)
        self.assertEqual(result.sources, [])
        self.assertEqual(result.answer_scope, "general_knowledge")
        self.assertEqual(result.grounding_status, "ungrounded")
        self.assertTrue(result.general_knowledge_used)

    def test_citation_check_passes_grounded_text(self) -> None:
        result = check_text_grounding(
            "OCR fallback handles scanned PDFs and sha256 cache reduces repeated processing cost.",
            self._chunks(),
        )

        self.assertTrue(result.checked)
        self.assertTrue(result.passed)
        self.assertGreater(result.coverage, 0)
        self.assertIn("ocr", result.matched_terms)

    def test_citation_check_flags_unsupported_text(self) -> None:
        result = check_text_grounding(
            "양자역학과 르네상스 미술사를 중심으로 설명합니다.",
            self._chunks(),
        )

        self.assertTrue(result.checked)
        self.assertFalse(result.passed)
        self.assertTrue(result.unsupported_terms)
        self.assertTrue(result.warnings)


    def test_study_kit_preserves_sources_for_all_items(self) -> None:
        kit = generate_study_kit(self._chunks())

        self.assertTrue(kit["summary"]["sources"])
        self.assertIn("근거에 따르면", kit["summary"]["text"])
        self.assertNotIn("This section explains", kit["summary"]["text"])
        self.assertTrue(kit["key_points"])
        self.assertTrue(kit["glossary"])
        self.assertTrue(kit["quiz"])
        self.assertTrue(kit["expected_questions"])
        self.assertTrue(all(item["sources"] for item in kit["key_points"]))
        self.assertTrue(all(item["sources"] for item in kit["glossary"]))
        self.assertTrue(all(item["sources"] for item in kit["quiz"]))
        self.assertTrue(all(item["sources"] for item in kit["expected_questions"]))
        self.assertEqual(kit["warnings"], [])

    def test_audio_script_modes_preserve_sources(self) -> None:
        for mode in ("brief_1min", "briefing_3min", "briefing_5min", "lecture", "podcast"):
            script = generate_audio_script(self._chunks(), mode=mode)

            self.assertEqual(script["mode"], mode)
            self.assertTrue(script["script"])
            self.assertRegex(script["script"][0]["text"], "오디오|브리핑|정리|흐름|강의형|설명")
            self.assertEqual(script["tts_status"], "mock")
            self.assertIsNone(script["audio_path"])
            self.assertTrue(all(segment["sources"] for segment in script["script"]))
            self.assertEqual(script["warnings"], [])

    def test_rule_based_podcast_is_domain_neutral_and_reports_quality_metadata(self) -> None:
        script = generate_audio_script(self._chunks(), mode="podcast", target_chars=2200)
        text = " ".join(segment["text"] for segment in script["script"])

        self.assertNotIn("11주차", text)
        self.assertNotIn("BPE", text)
        self.assertNotIn("RNN", text)
        self.assertNotIn("CNN", text)
        self.assertGreaterEqual(script["script_char_count"], 1900)
        self.assertEqual(script["segment_count"], len(script["script"]))
        self.assertEqual(script["source_count"], 2)
        self.assertEqual(len({segment["text"] for segment in script["script"]}), len(script["script"]))
        self.assertGreater(script["estimated_duration_seconds"], 0)

    def test_concept_map_edges_have_evidence(self) -> None:
        graph = build_concept_map(self._chunks())

        self.assertTrue(graph["nodes"])
        self.assertTrue(graph["edges"])
        self.assertTrue(all(edge["evidence"] for edge in graph["edges"]))
        self.assertEqual(graph["warnings"], [])

    def test_empty_concept_map_returns_warning(self) -> None:
        graph = build_concept_map([])

        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])
        self.assertTrue(graph["warnings"])



    def test_audio_script_ollama_provider_uses_llm_text_with_sources(self) -> None:
        with patch("v2.audio_script.OllamaProvider.generate_script", return_value="오프닝입니다.\n핵심 복습입니다."):
            script = generate_audio_script(
                self._chunks(),
                mode="briefing_3min",
                llm_provider="ollama",
                llm_model="qwen3:8b",
            )

        self.assertEqual(script["llm"]["provider"], "ollama")
        self.assertEqual(script["llm"]["model"], "qwen3:8b")
        self.assertEqual(script["llm"]["status"], "used")
        self.assertEqual(script["script"][0]["text"], "오프닝입니다.")
        self.assertTrue(script["script"][0]["sources"])

    def test_audio_script_ollama_uses_target_minutes(self) -> None:
        with patch("v2.audio_script.OllamaProvider.generate_script", return_value="HOST: 안녕하세요.\nGUEST: 8분 대본입니다.") as mocked:
            script = generate_audio_script(
                self._chunks(),
                mode="podcast",
                llm_provider="ollama",
                llm_model="qwen3:8b",
                target_minutes=8,
            )

        self.assertEqual(script["llm"]["target_minutes"], 8)
        self.assertEqual(mocked.call_args.kwargs["minutes"], 8)

    def test_audio_script_ollama_uses_target_chars(self) -> None:
        llm_text = "HOST: 안녕하세요.\nGUEST: 핵심 내용을 설명했습니다.\nHOST: 이제 마무리할게요."
        with patch("v2.audio_script.OllamaProvider.generate_script", return_value=llm_text) as mocked:
            script = generate_audio_script(
                self._chunks(),
                mode="podcast",
                llm_provider="ollama",
                llm_model="qwen3:8b",
                target_chars=2200,
            )

        self.assertEqual(script["llm"]["target_chars"], 2200)
        self.assertEqual(mocked.call_args.kwargs["target_chars"], 2200)
        self.assertLess(script["llm"]["raw_script_char_count"], 1980)
        self.assertEqual(script["llm"]["minimum_target_chars"], 1980)
        self.assertEqual(script["llm"]["length_status"], "source_expanded")
        self.assertGreaterEqual(script["script_char_count"], 1980)
        self.assertEqual(script["script"][-1]["text"], "이제 마무리할게요.")
        self.assertTrue(any("source-grounded expansion" in warning for warning in script["warnings"]))

    def test_audio_script_qwen3_alias_uses_ollama_provider(self) -> None:
        with patch("v2.audio_script.OllamaProvider.generate_script", return_value="HOST: 시작합니다.\nGUEST: 설명합니다."):
            script = generate_audio_script(
                self._chunks(),
                mode="podcast",
                llm_provider="qwen3",
                llm_model="qwen3:8b",
            )

        self.assertEqual(script["llm"]["provider"], "ollama")
        self.assertEqual(script["llm"]["model"], "qwen3:8b")
        self.assertEqual(script["llm"]["status"], "used")

    def test_audio_script_ollama_podcast_preserves_speakers(self) -> None:
        llm_text = "HOST: 오늘은 BPE가 왜 필요한지 이야기해볼게요.\nGUEST: BPE는 OOV 문제를 줄이기 위해 단어를 subword로 나눕니다."
        with patch("v2.audio_script.OllamaProvider.generate_script", return_value=llm_text):
            script = generate_audio_script(
                self._chunks(),
                mode="podcast",
                llm_provider="ollama",
                llm_model="qwen3:8b",
            )

        self.assertEqual(script["script"][0]["speaker"], "host")
        self.assertEqual(script["script"][1]["speaker"], "guest")
        self.assertIn("BPE", script["script"][0]["text"])
        self.assertTrue(script["script"][1]["sources"])

    def test_audio_script_ollama_maps_each_turn_to_matching_source(self) -> None:
        llm_text = "HOST: OCR fallback handles scanned PDFs.\nGUEST: PDF page citations ground RAG answers."
        with patch("v2.audio_script.OllamaProvider.generate_script", return_value=llm_text):
            script = generate_audio_script(
                self._chunks(),
                mode="podcast",
                llm_provider="ollama",
                llm_model="qwen3:14b",
            )

        self.assertEqual(script["script"][0]["sources"][0]["page"], 2)
        self.assertEqual(script["script"][1]["sources"][0]["page"], 1)
        self.assertEqual(script["source_count"], 2)

    def test_audio_script_ollama_podcast_splits_inline_speakers(self) -> None:
        llm_text = "HOST: Opening context. GUEST: Longer explanation. HOST: Smooth bridge. GUEST: Final recap."
        with patch("v2.audio_script.OllamaProvider.generate_script", return_value=llm_text):
            script = generate_audio_script(
                self._chunks(),
                mode="podcast",
                llm_provider="ollama",
                llm_model="qwen3:8b",
            )

        self.assertEqual([segment["speaker"] for segment in script["script"]], ["host", "guest", "host", "guest"])
        self.assertEqual(script["script"][1]["text"], "Longer explanation.")
        self.assertTrue(all(segment["sources"] for segment in script["script"]))

    def test_audio_script_ollama_removes_spoken_speaker_labels(self) -> None:
        llm_text = "HOST: 반가워요, GUEST.\nGUEST: 감사합니다, HOST!"
        with patch("v2.audio_script.OllamaProvider.generate_script", return_value=llm_text):
            script = generate_audio_script(
                self._chunks(),
                mode="podcast",
                llm_provider="ollama",
                llm_model="qwen3:8b",
            )

        self.assertEqual(script["script"][0]["text"], "반가워요.")
        self.assertEqual(script["script"][1]["text"], "감사합니다!")

    def test_audio_script_ollama_provider_falls_back_when_unavailable(self) -> None:
        from v2.providers.ollama import OllamaProviderError

        with patch("v2.audio_script.OllamaProvider.generate_script", side_effect=OllamaProviderError("missing model")):
            script = generate_audio_script(self._chunks(), llm_provider="ollama", llm_model="qwen3:8b")

        self.assertEqual(script["llm"]["status"], "mock")
        self.assertTrue(any("OllamaProvider failed" in warning for warning in script["warnings"]))
        self.assertTrue(script["script"])

if __name__ == "__main__":
    unittest.main()
