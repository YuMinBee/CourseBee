from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

try:
    from fastapi import BackgroundTasks, HTTPException
except ImportError:  # pragma: no cover
    BackgroundTasks = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]

from v2.api import routes
from v2.api.schemas import (
    ConversationMessage,
    CoursePackAudioScriptRequest,
    CoursePackConceptMapExportRequest,
    CoursePackConceptMapRequest,
    CoursePackIngestRequest,
    CoursePackJobRequest,
    CoursePackQueryRequest,
    CoursePackStudyKitRequest,
    CoursePackSummaryRequest,
)
from v2.providers.semantic import SemanticRetrievalRun
from v2.providers.web_search import WebSearchResult
from v2.schemas import AnswerWithSources

TEST_OUTPUT_ROOT = Path.cwd() / "outputs" / "_test_course_packs"


class CoursePackBehaviorTest(unittest.TestCase):
    def _case_dir(self) -> Path:
        path = TEST_OUTPUT_ROOT / uuid4().hex
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _create_pack(self) -> tuple[dict, Path]:
        root = self._case_dir()
        first = root / "week1.txt"
        second = root / "week2.md"
        first.write_text(
            "Week 1 explains OCR, PDF parsing, source citation, and RAG chunks.",
            encoding="utf-8",
        )
        second.write_text(
            "# Week 2\n\nGraphRAG-lite builds a concept map. OCR supports scanned PDF parsing.",
            encoding="utf-8",
        )
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(
                paths=[str(first), str(second)],
                output_root=str(root / "outputs"),
                max_chunk_chars=90,
            )
        )
        return pack, root

    def test_v2_course_pack_ingests_multiple_documents(self) -> None:
        pack, _ = self._create_pack()

        self.assertTrue(pack["pack_id"].startswith("pack_"))
        self.assertEqual(pack["document_count"], 2)
        self.assertGreaterEqual(pack["chunk_count"], 2)
        self.assertEqual(pack["warnings"], [])
        self.assertTrue((Path(pack["output_dir"]) / "course_pack.json").exists())
        self.assertTrue((Path(pack["output_dir"]) / "chunks.json").exists())

    def test_v2_course_pack_chunks_keep_document_source(self) -> None:
        pack, _ = self._create_pack()
        chunks = json.loads((Path(pack["output_dir"]) / "chunks.json").read_text(encoding="utf-8"))["chunks"]

        first_metadata = chunks[0]["metadata"]
        self.assertIn("doc_id", first_metadata)
        self.assertIn("filename", first_metadata)
        self.assertEqual(first_metadata["pack_id"], pack["pack_id"])
        self.assertIn("page", chunks[0])
        self.assertIn("chunk_id", chunks[0])

    def test_v2_course_pack_append_preserves_existing_documents_and_skips_duplicates(self) -> None:
        pack, root = self._create_pack()
        output_root = root / "outputs"
        third = root / "week3.txt"
        third.write_text("Week 3 explains BPE tokenization and OOV handling.", encoding="utf-8")

        appended = routes.ingest_course_pack(
            CoursePackIngestRequest(
                paths=[str(third)],
                output_root=str(output_root),
                pack_id=pack["pack_id"],
                append=True,
            )
        )

        self.assertEqual(appended["pack_id"], pack["pack_id"])
        self.assertEqual(appended["document_count"], 3)
        self.assertEqual(appended["added_document_count"], 1)
        self.assertEqual(appended["duplicate_document_count"], 0)
        self.assertEqual(
            {document["filename"] for document in appended["documents"]},
            {"week1.txt", "week2.md", "week3.txt"},
        )
        chunk_count = appended["chunk_count"]

        duplicate = routes.ingest_course_pack(
            CoursePackIngestRequest(
                paths=[str(third)],
                output_root=str(output_root),
                pack_id=pack["pack_id"],
                append=True,
            )
        )

        self.assertEqual(duplicate["document_count"], 3)
        self.assertEqual(duplicate["chunk_count"], chunk_count)
        self.assertEqual(duplicate["added_document_count"], 0)
        self.assertEqual(duplicate["duplicate_document_count"], 1)

    def test_v2_course_pack_ask_returns_document_sources(self) -> None:
        pack, root = self._create_pack()
        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="OCR PDF parsing source citation",
                output_root=str(root / "outputs"),
                top_k=4,
            )
        )

        self.assertTrue(response["answer"])
        self.assertTrue(response["sources"])
        source = response["sources"][0]
        self.assertIn("doc_id", source)
        self.assertIn("filename", source)
        self.assertIn("page", source)
        self.assertIn("chunk_id", source)
        self.assertIn("excerpt", source)
        self.assertIn("OCR", source["excerpt"])

    def test_follow_up_question_uses_recent_conversation_for_retrieval(self) -> None:
        pack, root = self._create_pack()

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="그럼 장점은?",
                output_root=str(root / "outputs"),
                mode="auto",
                conversation_history=[
                    ConversationMessage(role="user", content="OCR와 PDF 파싱의 관계를 설명해줘"),
                    ConversationMessage(role="assistant", content="OCR은 스캔 PDF에서 텍스트를 추출합니다."),
                ],
            )
        )

        self.assertTrue(response["conversation_context_used"])
        self.assertEqual(response["conversation_turns_used"], 2)
        self.assertIn("OCR와 PDF 파싱", response["retrieval_query"])
        self.assertIn("그럼 장점은?", response["retrieval_query"])
        self.assertTrue(response["sources"])

    def test_independent_question_does_not_inherit_stale_conversation_terms(self) -> None:
        pack, root = self._create_pack()

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="GraphRAG-lite란?",
                output_root=str(root / "outputs"),
                conversation_history=[
                    ConversationMessage(role="user", content="BPE와 OOV 관계를 설명해줘"),
                    ConversationMessage(role="assistant", content="BPE는 subword를 사용합니다."),
                ],
            )
        )

        self.assertFalse(response["conversation_context_used"])
        self.assertEqual(response["conversation_turns_used"], 0)
        self.assertEqual(response["retrieval_query"], "GraphRAG-lite란?")

    def test_web_rag_runs_after_course_pack_miss_and_returns_url_sources(self) -> None:
        pack, root = self._create_pack()
        web_result = WebSearchResult(
            title="강화 학습",
            url="https://ko.wikipedia.org/wiki/강화_학습",
            text="강화 학습은 에이전트가 환경과 상호작용하며 누적 보상을 최대화하는 정책을 학습하는 방법이다.",
            language="ko",
            page_id=101,
        )

        with (
            patch("v2.course_packs._balanced_chunks", return_value=[]),
            patch("v2.course_packs.WikipediaSearchProvider.search", return_value=[web_result]),
        ):
            response = routes.ask_course_pack(
                CoursePackQueryRequest(
                    pack_id=pack["pack_id"],
                    question="강화학습이란?",
                    output_root=str(root / "outputs"),
                    mode="vector",
                    allow_web_fallback=True,
                    allow_general_fallback=True,
                )
            )

        self.assertEqual(response["answer_scope"], "external_web")
        self.assertEqual(response["grounding_status"], "web_grounded")
        self.assertTrue(response["web_search_used"])
        self.assertFalse(response["general_knowledge_used"])
        self.assertEqual(response["web_search"]["provider"], "wikipedia")
        self.assertEqual(response["sources"][0]["url"], web_result.url)
        self.assertEqual(response["sources"][0]["source_type"], "external_web")
        self.assertIn("누적 보상", response["sources"][0]["excerpt"])
        self.assertTrue(response["sentence_citations"])

    def test_course_pack_evidence_skips_web_search(self) -> None:
        pack, root = self._create_pack()

        with patch("v2.course_packs.WikipediaSearchProvider.search") as web_search:
            response = routes.ask_course_pack(
                CoursePackQueryRequest(
                    pack_id=pack["pack_id"],
                    question="OCR PDF parsing source citation",
                    output_root=str(root / "outputs"),
                    mode="vector",
                    allow_web_fallback=True,
                    allow_general_fallback=True,
                )
            )

        self.assertEqual(response["answer_scope"], "course_pack")
        self.assertFalse(response.get("web_search_used", False))
        web_search.assert_not_called()

    def test_general_knowledge_runs_only_after_web_search_has_no_results(self) -> None:
        pack, root = self._create_pack()

        class FakeGeneralProvider:
            model = "fake-general"

            def answer(self, question, chunks, graph_context):
                return AnswerWithSources(answer="일반지식 기반 답변입니다.")

        with (
            patch("v2.course_packs._balanced_chunks", return_value=[]),
            patch("v2.course_packs.WikipediaSearchProvider.search", return_value=[]),
            patch("v2.course_packs._answer_provider", return_value=FakeGeneralProvider()),
        ):
            response = routes.ask_course_pack(
                CoursePackQueryRequest(
                    pack_id=pack["pack_id"],
                    question="강화학습이란?",
                    output_root=str(root / "outputs"),
                    mode="vector",
                    llm_provider="ollama",
                    allow_web_fallback=True,
                    allow_general_fallback=True,
                )
            )

        self.assertEqual(response["answer_scope"], "general_knowledge")
        self.assertTrue(response["general_knowledge_used"])
        self.assertTrue(response["web_search_used"])
        self.assertEqual(response["web_search"]["status"], "no_results")

    def test_v2_course_pack_semantic_mode_exposes_execution_details(self) -> None:
        pack, root = self._create_pack()

        class FakeSemanticRetriever:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def search_with_details(self, question, chunks, top_k=4) -> SemanticRetrievalRun:
                return SemanticRetrievalRun(
                    chunks=chunks[:top_k],
                    retrieval_mode="semantic_rerank",
                    implementation="retrieve_rrf_rerank",
                    embedding_model="fake-embedding",
                    reranker_model="fake-reranker",
                    lexical_candidates=2,
                    dense_candidates=2,
                    fused_candidates=2,
                    candidate_chunks=len(chunks),
                    reranked=True,
                )

        with patch("v2.course_packs.SemanticHybridRetriever", FakeSemanticRetriever):
            response = routes.ask_course_pack(
                CoursePackQueryRequest(
                    pack_id=pack["pack_id"],
                    question="How are OCR and PDF parsing related?",
                    output_root=str(root / "outputs"),
                    top_k=2,
                    mode="semantic_rerank",
                )
            )

        self.assertEqual(response["retrieval_mode"], "semantic_rerank")
        self.assertEqual(response["retrieval_details"]["embedding_model"], "fake-embedding")
        self.assertTrue(response["retrieval_details"]["reranked"])
        self.assertEqual(response["trace"]["retrieval_debug"]["retrieval_implementation"], "retrieve_rrf_rerank")

    def test_v2_course_pack_sources_include_lecture_metadata(self) -> None:
        root = self._case_dir()
        first = root / "자연어처리_11주차_1차시.txt"
        second = root / "자연어처리_11주차_2차시.txt"
        first.write_text("BPE reduces OOV through subword tokenization.", encoding="utf-8")
        second.write_text("LSTM improves RNN sequence memory with gates.", encoding="utf-8")
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(
                paths=[str(first), str(second)],
                output_root=str(root / "outputs"),
                max_chunk_chars=90,
            )
        )

        chunks = json.loads((Path(pack["output_dir"]) / "chunks.json").read_text(encoding="utf-8"))["chunks"]
        first_metadata = chunks[0]["metadata"]
        self.assertEqual(first_metadata["week"], 11)
        self.assertEqual(first_metadata["lecture_no"], 1)

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="BPE OOV",
                output_root=str(root / "outputs"),
            )
        )
        source = response["sources"][0]
        self.assertEqual(source["week"], 11)
        self.assertEqual(source["lecture_no"], 1)
    def test_v2_course_pack_ask_local_graph_uses_edge_evidence(self) -> None:
        root = self._case_dir()
        first = root / "자연어처리_11주차_1차시.txt"
        first.write_text("BPE reduces OOV through subword tokenization.", encoding="utf-8")
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(
                paths=[str(first)],
                output_root=str(root / "outputs"),
                max_chunk_chars=120,
            )
        )

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="BPE와 OOV는 어떤 관계야?",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="local_graph",
            )
        )

        self.assertEqual(response["mode"], "local_graph")
        self.assertEqual(response["retrieval_mode"], "local_graph")
        self.assertTrue(response["sources"])
        self.assertTrue(response["graph_context"])
        self.assertTrue(any(edge["source"] == "BPE" and edge["target"] == "OOV" for edge in response["graph_context"]))
        self.assertTrue(response["graph_context"][0]["evidence"])
    def test_v2_course_pack_local_graph_returns_prerequisite_path(self) -> None:
        root = self._case_dir()
        first = root / "자연어처리_11주차_1차시.txt"
        first.write_text(
            "Tokenizer and subword tokenization are prerequisites for BPE. BPE reduces OOV.",
            encoding="utf-8",
        )
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(
                paths=[str(first)],
                output_root=str(root / "outputs"),
                max_chunk_chars=180,
            )
        )

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="BPE를 이해하려면 먼저 뭘 알아야 해?",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="local_graph",
            )
        )

        self.assertEqual(response["mode"], "local_graph")
        self.assertEqual(response["retrieval_mode"], "course_graph_path")
        self.assertEqual(response["traversal_strategy"], "prerequisite")
        self.assertIn("BPE", response["matched_entities"])
        self.assertTrue(response["graph_paths"])
        self.assertTrue(response["evidence_chunks"])
        self.assertTrue(
            any(
                edge["relation"] == "prerequisite_of" and edge["target"] == "BPE"
                for edge in response["graph_context"]
            )
        )

    def test_v2_course_pack_local_graph_returns_pipeline_paths(self) -> None:
        root = self._case_dir()
        first = root / "자연어처리_11주차_2차시.txt"
        first.write_text(
            "RNN handles sequence data in the NLP pipeline. "
            "LSTM improves RNN long-term dependency. "
            "CNN captures local pattern for text classification in the NLP pipeline.",
            encoding="utf-8",
        )
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(
                paths=[str(first)],
                output_root=str(root / "outputs"),
                max_chunk_chars=260,
            )
        )

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="RNN, LSTM, CNN은 NLP pipeline에서 어떻게 연결돼?",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="local_graph",
            )
        )

        self.assertEqual(response["retrieval_mode"], "course_graph_path")
        self.assertEqual(response["traversal_strategy"], "path")
        self.assertTrue({"RNN", "LSTM", "CNN"}.issubset(set(response["matched_entities"])))
        self.assertTrue(response["graph_paths"])
        self.assertTrue(any(edge["relation"] == "used_in" for edge in response["graph_context"]))
    def test_v2_course_pack_auto_router_selects_vector_for_fact_question(self) -> None:
        pack, root = self._create_pack()
        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="OCR 정의가 뭐야?",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="auto",
            )
        )

        self.assertEqual(response["mode"], "auto")
        self.assertEqual(response["question_type"], "fact_question")
        self.assertEqual(response["routed_mode"], "vector")
        self.assertEqual(response["retrieval_mode"], "vector")
        self.assertIn("vector", response["selected_retrievers"])
        self.assertTrue(response["retrieval_plan"])

    def test_v2_course_pack_auto_router_selects_graph_for_relation_question(self) -> None:
        root = self._case_dir()
        first = root / "자연어처리_11주차_1차시.txt"
        first.write_text("BPE reduces OOV through subword tokenization.", encoding="utf-8")
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(paths=[str(first)], output_root=str(root / "outputs"), max_chunk_chars=120)
        )

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="BPE와 OOV는 어떤 관계야?",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="auto",
            )
        )

        self.assertEqual(response["mode"], "auto")
        self.assertEqual(response["question_type"], "relation_question")
        self.assertEqual(response["routed_mode"], "local_graph")
        self.assertEqual(response["retrieval_mode"], "local_graph")
        self.assertIn("course_graph", response["selected_retrievers"])
        self.assertTrue(response["graph_context"])

    def test_v2_course_pack_auto_router_selects_hierarchical_for_overview_question(self) -> None:
        pack, root = self._create_pack()
        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="course pack 전체 흐름 요약해줘",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="auto",
            )
        )

        self.assertEqual(response["mode"], "auto")
        self.assertEqual(response["question_type"], "overview_question")
        self.assertEqual(response["routed_mode"], "hierarchical")
        self.assertEqual(response["retrieval_mode"], "hierarchical_summary")
        self.assertIn("hierarchical_summary", response["selected_retrievers"])
        self.assertTrue(response["selected_summary_nodes"])

    def test_v2_course_pack_auto_router_selects_prerequisite_graph_for_learning_path(self) -> None:
        root = self._case_dir()
        first = root / "자연어처리_11주차_1차시.txt"
        first.write_text(
            "Tokenizer and subword tokenization are prerequisites for BPE. BPE reduces OOV.",
            encoding="utf-8",
        )
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(paths=[str(first)], output_root=str(root / "outputs"), max_chunk_chars=180)
        )

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="BPE를 이해하려면 먼저 뭘 알아야 해?",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="auto",
            )
        )

        self.assertEqual(response["mode"], "auto")
        self.assertEqual(response["question_type"], "learning_path_question")
        self.assertEqual(response["routed_mode"], "local_graph")
        self.assertEqual(response["traversal_strategy"], "prerequisite")
        self.assertTrue(response["graph_paths"])

    def test_v2_course_pack_auto_router_returns_trace(self) -> None:
        root = self._case_dir()
        first = root / "nlp_week11_lecture1.txt"
        first.write_text("BPE reduces OOV through subword tokenization.", encoding="utf-8")
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(paths=[str(first)], output_root=str(root / "outputs"), max_chunk_chars=120)
        )

        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="What is the relationship between BPE and OOV?",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="auto",
            )
        )

        trace = response["trace"]
        self.assertTrue(trace["request_id"].startswith("req_"))
        self.assertTrue(trace["stages"])
        self.assertTrue(any(stage["name"] == "classify_question" for stage in trace["stages"]))
        self.assertTrue(any(stage["name"] == "retrieve_graph_context" for stage in trace["stages"]))
        self.assertGreaterEqual(trace["retrieval_debug"]["candidate_chunks"], 1)
        self.assertGreaterEqual(trace["retrieval_debug"]["selected_chunks"], 1)
        self.assertFalse(trace["retrieval_debug"]["fallback_used"])

    def test_v2_course_pack_writes_hierarchical_summary_index(self) -> None:
        pack, _ = self._create_pack()
        index_path = Path(pack["output_dir"]) / "hierarchical_summary_index.json"
        self.assertTrue(index_path.exists())
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["root_id"], "course_pack_summary")
        node_types = {node["type"] for node in index["nodes"]}
        self.assertIn("course_pack_summary", node_types)
        self.assertIn("lecture_summary", node_types)
        self.assertIn("chunk_summary", node_types)

    def test_v2_course_pack_ask_hierarchical_summary_uses_overview_level(self) -> None:
        pack, root = self._create_pack()
        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="11주차 전체 흐름 설명해줘",
                output_root=str(root / "outputs"),
                top_k=4,
                mode="hierarchical",
            )
        )

        self.assertEqual(response["mode"], "hierarchical")
        self.assertEqual(response["retrieval_mode"], "hierarchical_summary")
        self.assertEqual(response["abstraction_level"], "course_pack")
        self.assertTrue(response["selected_summary_nodes"])
        self.assertTrue(any(node["type"] == "course_pack_summary" for node in response["selected_summary_nodes"]))
        self.assertTrue(response["supporting_chunks"])
        self.assertGreater(response["hierarchical_summary_index"]["node_count"], 0)
    def test_v2_course_pack_overview_query_balances_document_sources(self) -> None:
        pack, root = self._create_pack()
        response = routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="course pack overview summary",
                output_root=str(root / "outputs"),
                top_k=4,
            )
        )

        filenames = {source["filename"] for source in response["sources"]}
        self.assertIn("week1.txt", filenames)
        self.assertIn("week2.md", filenames)

    def test_v2_course_pack_study_kit_has_document_sources(self) -> None:
        pack, root = self._create_pack()
        response = routes.study_kit_course_pack(
            CoursePackStudyKitRequest(
                pack_id=pack["pack_id"],
                query="GraphRAG-lite concept map",
                output_root=str(root / "outputs"),
                max_items=3,
            )
        )

        self.assertTrue(response["summary"]["sources"])
        self.assertIn("doc_id", response["summary"]["sources"][0])
        self.assertTrue(all(item["sources"] for item in response["key_points"]))

    def test_v2_course_pack_study_kit_is_course_pack_shaped(self) -> None:
        pack, root = self._create_pack()
        response = routes.study_kit_course_pack(
            CoursePackStudyKitRequest(
                pack_id=pack["pack_id"],
                query="course pack overview summary",
                output_root=str(root / "outputs"),
                max_items=3,
            )
        )

        self.assertTrue(response["overview"]["text"])
        self.assertTrue(response["lecture_summaries"])
        self.assertIn("connections", response)
        self.assertTrue(response["key_concepts"])
        self.assertTrue(response["expected_questions"])
        self.assertTrue(response["flashcards"])
        self.assertTrue(response["sources"])
        self.assertTrue((Path(pack["output_dir"]) / "study_kit.json").exists())
    def test_v2_course_pack_summary_has_sources(self) -> None:
        pack, root = self._create_pack()
        response = routes.summary_course_pack(
            CoursePackSummaryRequest(
                pack_id=pack["pack_id"],
                question="course pack overview summary",
                output_root=str(root / "outputs"),
                top_k=4,
                max_items=3,
            )
        )

        self.assertEqual(response["pack_id"], pack["pack_id"])
        self.assertTrue(response["overview"]["text"])
        self.assertTrue(response["overview"]["sources"])
        self.assertTrue(response["lecture_summaries"])
        self.assertTrue(all(item["sources"] for item in response["lecture_summaries"]))
        self.assertTrue(response["key_concepts"])
        self.assertTrue((Path(pack["output_dir"]) / "summary.json").exists())

    def test_v2_course_pack_summary_openai_without_key_falls_back(self) -> None:
        pack, root = self._create_pack()
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            response = routes.summary_course_pack(
                CoursePackSummaryRequest(
                    pack_id=pack["pack_id"],
                    output_root=str(root / "outputs"),
                    llm_provider="openai",
                    llm_model="gpt-5.4-mini",
                )
            )

        self.assertEqual(response["llm"]["provider"], "openai")
        self.assertEqual(response["llm"]["status"], "fallback")
        self.assertTrue(response["overview"]["sources"])
        self.assertTrue(any("OPENAI_API_KEY" in warning for warning in response["warnings"]))

    def test_v2_course_pack_summary_openai_grounded_refine_passes_citation_check(self) -> None:
        pack, root = self._create_pack()
        refined = "OCR와 PDF parsing, source citation, RAG chunks, GraphRAG-lite concept map을 정리합니다."
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("v2.course_summary.OpenAIProvider.summarize", return_value=refined):
                response = routes.summary_course_pack(
                    CoursePackSummaryRequest(
                        pack_id=pack["pack_id"],
                        output_root=str(root / "outputs"),
                        llm_provider="openai",
                        llm_model="gpt-5.4-mini",
                    )
                )

        self.assertEqual(response["llm"]["status"], "used")
        self.assertEqual(response["overview"]["text"], refined)
        self.assertTrue(response["citation_check"]["checked"])
        self.assertTrue(response["citation_check"]["passed"])

    def test_v2_course_pack_summary_openai_ungrounded_refine_falls_back(self) -> None:
        pack, root = self._create_pack()
        ungrounded = "양자역학과 르네상스 미술사를 중심으로 설명합니다."
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("v2.course_summary.OpenAIProvider.summarize", return_value=ungrounded):
                response = routes.summary_course_pack(
                    CoursePackSummaryRequest(
                        pack_id=pack["pack_id"],
                        output_root=str(root / "outputs"),
                        llm_provider="openai",
                        llm_model="gpt-5.4-mini",
                    )
                )

        self.assertEqual(response["llm"]["status"], "fallback")
        self.assertNotEqual(response["overview"]["text"], ungrounded)
        self.assertTrue(response["citation_check"]["checked"])
        self.assertFalse(response["citation_check"]["passed"])
        self.assertTrue(response["citation_check"]["unsupported_terms"])
        self.assertTrue(any("citation_check" in warning for warning in response["warnings"]))


    def test_v2_course_pack_audio_script_has_document_sources(self) -> None:
        pack, root = self._create_pack()
        response = routes.audio_script_course_pack(
            CoursePackAudioScriptRequest(
                pack_id=pack["pack_id"],
                query="OCR",
                output_root=str(root / "outputs"),
                mode="briefing_3min",
            )
        )

        self.assertEqual(response["tts_status"], "mock")
        self.assertTrue(response["script"])
        self.assertTrue(all(item["sources"] for item in response["script"]))
        self.assertIn("filename", response["script"][0]["sources"][0])

    def test_v2_course_pack_audio_overview_spreads_sources_across_documents(self) -> None:
        root = self._case_dir()
        paths = []
        for index in range(1, 6):
            path = root / f"week{index}.txt"
            path.write_text(
                f"Course pack overview topic {index}. Distinct lecture evidence number {index}.",
                encoding="utf-8",
            )
            paths.append(str(path))
        pack = routes.ingest_course_pack(
            CoursePackIngestRequest(paths=paths, output_root=str(root / "outputs"), pack_id="pack_audio_spread")
        )

        response = routes.audio_script_course_pack(
            CoursePackAudioScriptRequest(
                pack_id=pack["pack_id"],
                query="course pack overview summary",
                output_root=str(root / "outputs"),
                mode="podcast",
                top_k=3,
            )
        )

        self.assertEqual(
            {source["filename"] for source in response["sources"]},
            {"week1.txt", "week3.txt", "week5.txt"},
        )

    def test_v2_tts_failure_does_not_return_stale_audio_without_reuse(self) -> None:
        pack, root = self._create_pack()
        target = Path(pack["output_dir"]) / "audio_overview_edge_tts.mp3"
        target.write_bytes(b"old audio")

        class FailingCommunicate:
            def __init__(self, text, voice) -> None:
                self.text = text
                self.voice = voice

            async def stream(self):
                raise RuntimeError("tts unavailable")
                yield {}

        fake_edge_tts = types.SimpleNamespace(Communicate=FailingCommunicate)
        with patch.dict(sys.modules, {"edge_tts": fake_edge_tts}):
            response = routes.tts_course_pack(
                CoursePackAudioScriptRequest(
                    pack_id=pack["pack_id"],
                    query="OCR overview",
                    output_root=str(root / "outputs"),
                    mode="podcast",
                    reuse_existing=False,
                )
            )

        self.assertEqual(response["tts_status"], "failed")
        self.assertIsNone(response["audio_path"])
        self.assertIsNone(response["audio_url"])
        self.assertEqual(target.read_bytes(), b"old audio")
        self.assertTrue(any("stale audio" in warning for warning in response["warnings"]))

    def test_v2_tts_uses_distinct_host_and_guest_voices(self) -> None:
        pack, root = self._create_pack()
        calls: list[tuple[str, str]] = []

        class FakeCommunicate:
            def __init__(self, text, voice) -> None:
                self.text = text
                self.voice = voice
                calls.append((text, voice))

            async def stream(self):
                yield {"type": "audio", "data": f"[{self.voice}]".encode()}

        fake_edge_tts = types.SimpleNamespace(Communicate=FakeCommunicate)
        with patch.dict(sys.modules, {"edge_tts": fake_edge_tts}):
            response = routes.tts_course_pack(
                CoursePackAudioScriptRequest(
                    pack_id=pack["pack_id"],
                    query="OCR PDF overview",
                    output_root=str(root / "outputs"),
                    mode="podcast",
                    voice="ko-KR-SunHiNeural",
                    guest_voice="ko-KR-InJoonNeural",
                )
            )

        used_voices = {voice for _, voice in calls}
        self.assertEqual(used_voices, {"ko-KR-SunHiNeural", "ko-KR-InJoonNeural"})
        self.assertEqual(response["tts_status"], "edge_tts")
        self.assertEqual(response["voices"]["host"], "ko-KR-SunHiNeural")
        self.assertEqual(response["voices"]["guest"], "ko-KR-InJoonNeural")
        self.assertTrue(Path(response["audio_path"]).exists())

    def test_v2_course_pack_audio_script_can_include_background_rag(self) -> None:
        pack, root = self._create_pack()
        response = routes.audio_script_course_pack(
            CoursePackAudioScriptRequest(
                pack_id=pack["pack_id"],
                query="BPE OOV CNN podcast background",
                output_root=str(root / "outputs"),
                mode="podcast",
                knowledge_scope="course_pack_plus_background",
            )
        )

        self.assertEqual(response["knowledge_scope"], "course_pack_plus_background")
        self.assertTrue(response["background_sources"])
        self.assertTrue(any(source.get("filename") == "background_nlp_reference.md" for item in response["script"] for source in item["sources"]))
    def test_v2_course_pack_concept_map_links_documents(self) -> None:
        pack, root = self._create_pack()
        response = routes.concept_map_course_pack(
            CoursePackConceptMapRequest(pack_id=pack["pack_id"], output_root=str(root / "outputs"))
        )

        self.assertIn("nodes", response)
        self.assertIn("edges", response)
        self.assertTrue(any(node.get("type") == "document" for node in response["nodes"]))
        self.assertTrue(any(edge.get("relation") == "appears_in" for edge in response["edges"]))
        self.assertTrue(all(edge["evidence"] for edge in response["edges"]))
        self.assertTrue(any("doc_id" in edge["evidence"][0] for edge in response["edges"] if edge["evidence"]))

    def test_v2_course_pack_concept_map_reuses_ingest_graph(self) -> None:
        pack, root = self._create_pack()

        with patch("v2.course_packs.build_concept_map") as rebuild:
            response = routes.concept_map_course_pack(
                CoursePackConceptMapRequest(pack_id=pack["pack_id"], output_root=str(root / "outputs"))
            )

        rebuild.assert_not_called()
        self.assertTrue(response["nodes"])
        self.assertTrue(response["edges"])

    def test_v2_course_pack_artifacts_preview_returns_generated_outputs(self) -> None:
        pack, root = self._create_pack()
        routes.ask_course_pack(
            CoursePackQueryRequest(
                pack_id=pack["pack_id"],
                question="OCR source citation",
                output_root=str(root / "outputs"),
            )
        )
        routes.summary_course_pack(
            CoursePackSummaryRequest(pack_id=pack["pack_id"], output_root=str(root / "outputs"))
        )

        response = routes.get_course_pack_artifacts(
            pack["pack_id"],
            output_root=str(root / "outputs"),
            include_content=True,
        )

        self.assertEqual(response["pack_id"], pack["pack_id"])
        self.assertTrue(response["artifacts"]["course_pack"]["exists"])
        self.assertEqual(response["artifacts"]["course_pack"]["data"]["pack_id"], pack["pack_id"])
        self.assertTrue(response["artifacts"]["summary"]["exists"])
        self.assertTrue(response["artifacts"]["graph"]["exists"])
        self.assertTrue(response["answers"])

    def test_v2_course_pack_concept_map_export_writes_mermaid_and_html(self) -> None:
        pack, root = self._create_pack()
        response = routes.export_concept_map_course_pack(
            CoursePackConceptMapExportRequest(
                pack_id=pack["pack_id"],
                output_root=str(root / "outputs"),
                max_nodes=20,
                max_edges=40,
            )
        )

        mermaid_path = Path(response["mermaid_path"])
        html_path = Path(response["html_path"])
        self.assertTrue(mermaid_path.exists())
        self.assertTrue(html_path.exists())
        self.assertIn("flowchart LR", response["mermaid"])
        self.assertGreater(response["exported_node_count"], 0)
        self.assertGreater(response["exported_edge_count"], 0)
        self.assertIn("mermaid", html_path.read_text(encoding="utf-8"))



    def test_v2_course_pack_job_records_status_and_pack(self) -> None:
        root = self._case_dir()
        first = root / "nlp_week11_lecture1.txt"
        second = root / "nlp_week11_lecture2.txt"
        first.write_text("BPE reduces OOV through subword tokenization.", encoding="utf-8")
        second.write_text("LSTM improves RNN sequence memory with gates.", encoding="utf-8")

        job = routes.create_course_pack_job(
            CoursePackJobRequest(
                paths=[str(first), str(second)],
                output_root=str(root / "outputs"),
                max_chunk_chars=120,
                pack_id="pack_job_test",
            )
        )

        self.assertTrue(job["job_id"].startswith("job_"))
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["stage"], "completed")
        self.assertEqual(job["progress"], 1.0)
        self.assertEqual(job["processed_documents"], 2)
        self.assertEqual(job["total_documents"], 2)
        self.assertEqual(job["pack_id"], "pack_job_test")
        self.assertEqual(job["course_pack"]["pack_id"], "pack_job_test")

        loaded = routes.get_course_pack_job(job["job_id"], output_root=str(root / "outputs"))
        self.assertEqual(loaded["job_id"], job["job_id"])
        self.assertEqual(loaded["status"], "succeeded")
        self.assertTrue((root / "outputs" / "course_pack_jobs" / f"{job['job_id']}.json").exists())
        self.assertTrue((root / "outputs" / "course_packs" / "pack_job_test" / "course_pack.json").exists())


    def test_v2_course_pack_job_can_run_as_background_task(self) -> None:
        if BackgroundTasks is None:
            self.skipTest("FastAPI BackgroundTasks unavailable")
        root = self._case_dir()
        first = root / "nlp_week11_async1.txt"
        second = root / "nlp_week11_async2.txt"
        first.write_text("BPE reduces OOV through subword tokenization.", encoding="utf-8")
        second.write_text("CNN captures local text patterns.", encoding="utf-8")
        background_tasks = BackgroundTasks()

        job = routes.create_course_pack_job(
            CoursePackJobRequest(
                paths=[str(first), str(second)],
                output_root=str(root / "outputs"),
                max_chunk_chars=120,
                pack_id="pack_async_job_test",
                run_async=True,
            ),
            background_tasks=background_tasks,
        )

        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["stage"], "queued")
        self.assertEqual(job["progress"], 0.0)
        self.assertEqual(job["inputs"]["pack_id"], "pack_async_job_test")

        queued = routes.get_course_pack_job(job["job_id"], output_root=str(root / "outputs"))
        self.assertEqual(queued["status"], "queued")

        asyncio.run(background_tasks())

        loaded = routes.get_course_pack_job(job["job_id"], output_root=str(root / "outputs"))
        self.assertEqual(loaded["status"], "succeeded")
        self.assertEqual(loaded["stage"], "completed")
        self.assertEqual(loaded["pack_id"], "pack_async_job_test")
        self.assertEqual(loaded["processed_documents"], 2)
        self.assertTrue(loaded["started_at"])
        self.assertTrue(loaded["finished_at"])
        self.assertTrue((root / "outputs" / "course_packs" / "pack_async_job_test" / "course_pack.json").exists())

    def test_v2_missing_course_pack_returns_404(self) -> None:
        missing_id = f"missing-{uuid4().hex}"
        if HTTPException is None:
            with self.assertRaises(FileNotFoundError):
                routes.get_course_pack(missing_id, output_root=str(TEST_OUTPUT_ROOT))
        else:
            with self.assertRaises(HTTPException) as context:
                routes.get_course_pack(missing_id, output_root=str(TEST_OUTPUT_ROOT))
            self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()





