from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from uuid import uuid4

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

from v2.providers.semantic import SemanticRetrievalRun
from v2.providers.web_search import WebSearchResult
from v2.schemas import AnswerWithSources


@unittest.skipIf(TestClient is None, "FastAPI TestClient is unavailable")
class HttpApiWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from v2.main import app

        cls.client = TestClient(app)

    def test_health_has_request_trace_headers(self) -> None:
        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            response = self.client.get("/health", headers={"X-Request-ID": "http-test-1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.headers["x-request-id"], "http-test-1")
        self.assertGreaterEqual(float(response.headers["x-process-time-ms"]), 0)

    def test_readiness_checks_storage_and_packaged_demo_assets(self) -> None:
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(response.json()["checks"]["data_root"], "writable")
        self.assertGreaterEqual(response.json()["checks"]["demo_fixtures"], 6)

    def test_optional_api_key_protects_v2_routes(self) -> None:
        with patch.dict(os.environ, {"COURSEBEE_API_KEY": "secret-test-key"}):
            denied = self.client.get("/v2/course-packs")
            allowed = self.client.get("/v2/course-packs", headers={"X-API-Key": "secret-test-key"})
            health = self.client.get("/health")

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(denied.json()["detail"]["error"], "invalid_api_key")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(health.status_code, 200)

    def test_upload_job_and_grounded_question_work_end_to_end(self) -> None:
        pack_id = f"pack_http_{uuid4().hex[:10]}"
        files = [
            ("files", ("biology-1.txt", "광합성은 엽록체에서 빛 에너지를 화학 에너지로 전환합니다.", "text/plain")),
            ("files", ("biology-2.txt", "캘빈 회로는 이산화탄소를 고정해 당 합성에 필요한 물질을 만듭니다.", "text/plain")),
        ]
        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            uploaded = self.client.post(
                "/v2/course-packs/upload",
                files=files,
                data={"pack_id": pack_id, "run_async": "true"},
            )

            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            job_id = uploaded.json()["job_id"]
            job = self.client.get(f"/v2/course-packs/jobs/{job_id}")
            answer = self.client.post(
                "/v2/course-packs/ask",
                headers={"X-Request-ID": "http-answer-trace"},
                json={
                    "pack_id": pack_id,
                    "question": "빛 에너지는 어떤 에너지로 바뀌나요?",
                    "mode": "auto",
                },
            )

        self.assertEqual(job.status_code, 200, job.text)
        self.assertEqual(job.json()["status"], "succeeded")
        self.assertEqual(job.json()["processed_documents"], 2)
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertTrue(answer.json()["answer"])
        self.assertTrue(answer.json()["sources"])
        self.assertEqual(answer.json()["sources"][0]["filename"], "biology-1.txt")
        self.assertEqual(answer.headers["x-request-id"], "http-answer-trace")
        self.assertEqual(answer.json()["trace"]["request_id"], "http-answer-trace")

    def test_upload_append_keeps_existing_pack_documents(self) -> None:
        pack_id = f"pack_http_append_{uuid4().hex[:8]}"
        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            created = self.client.post(
                "/v2/course-packs/upload",
                files={"files": ("first.txt", "first course source", "text/plain")},
                data={"pack_id": pack_id, "run_async": "false"},
            )
            appended = self.client.post(
                "/v2/course-packs/upload",
                files={"files": ("second.txt", "second course source", "text/plain")},
                data={"pack_id": pack_id, "append": "true", "run_async": "false"},
            )
            loaded = self.client.get(f"/v2/course-packs/{pack_id}")

        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(appended.status_code, 200, appended.text)
        self.assertEqual(appended.json()["processed_documents"], 1)
        self.assertEqual(appended.json()["course_pack"]["document_count"], 2)
        self.assertEqual(appended.json()["course_pack"]["added_document_count"], 1)
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(
            {document["filename"] for document in loaded.json()["documents"]},
            {"first.txt", "second.txt"},
        )

    def test_v3_onboarding_report_and_impact_contract(self) -> None:
        pack_id = f"pack_http_report_{uuid4().hex[:8]}"
        files = [
            ("files", ("handbook.txt", "신입 구성원은 입사 첫날 인사 시스템에서 비상 연락처를 등록합니다.", "text/plain")),
            ("files", ("security.txt", "업무 계정은 다중 요소 인증을 활성화하고 비밀번호를 공유하지 않습니다.", "text/plain")),
        ]
        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            uploaded = self.client.post(
                "/v3/course-packs/upload",
                files=files,
                data={"pack_id": pack_id, "run_async": "false"},
            )
            report = self.client.post(
                "/v3/course-packs/onboarding-report",
                json={
                    "pack_id": pack_id,
                    "title": "신입 구성원 온보딩 보고서",
                    "audience": "신입 구성원",
                    "objective": "핵심 필수 인사 및 보안 절차 이해",
                    "llm_provider": "mock",
                },
            )
            impact = self.client.get(f"/v3/course-packs/{pack_id}/onboarding-report-impact")

        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(report.json()["quality"]["grounded_section_count"], 2)
        self.assertEqual(report.json()["source_snapshot"]["document_count"], 2)
        self.assertEqual(report.json()["generation"]["mode"], "full")
        self.assertEqual(impact.status_code, 200, impact.text)
        self.assertTrue(impact.json()["report_exists"])
        self.assertEqual(impact.json()["status"], "current")
        self.assertFalse(impact.json()["requires_regeneration"])

    def test_invalid_inputs_are_rejected_at_http_boundary(self) -> None:
        chunk = {"chunk_id": "c1", "page": 1, "text": "근거 문장입니다."}
        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            blank_question = self.client.post("/v2/ask", json={"question": "   ", "chunks": [chunk]})
            local_path = self.client.post(
                "/v2/course-packs",
                json={"paths": ["README.md"], "pack_id": "pack_invalid_path"},
            )
            traversal_id = self.client.post(
                "/v2/course-packs/ask",
                json={"pack_id": "../outside", "question": "test"},
            )
            bad_upload = self.client.post(
                "/v2/course-packs/upload",
                files={"files": ("payload.exe", b"not allowed", "application/octet-stream")},
            )

        self.assertEqual(blank_question.status_code, 422)
        self.assertEqual(local_path.status_code, 400)
        self.assertEqual(traversal_id.status_code, 422)
        self.assertEqual(bad_upload.status_code, 400)

    def test_semantic_execution_details_survive_http_response_model(self) -> None:
        pack_id = f"pack_http_semantic_{uuid4().hex[:8]}"

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
                    lexical_candidates=1,
                    dense_candidates=1,
                    fused_candidates=1,
                    candidate_chunks=len(chunks),
                    reranked=True,
                )

        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            uploaded = self.client.post(
                "/v2/course-packs/upload",
                files={"files": ("semantic.txt", "semantic retrieval evidence", "text/plain")},
                data={"pack_id": pack_id, "run_async": "false"},
            )
            self.assertEqual(uploaded.status_code, 200, uploaded.text)

            with patch("v2.course_packs.SemanticHybridRetriever", FakeSemanticRetriever):
                answer = self.client.post(
                    "/v2/course-packs/ask",
                    json={
                        "pack_id": pack_id,
                        "question": "semantic evidence",
                        "mode": "semantic_rerank",
                    },
                )

        self.assertEqual(answer.status_code, 200, answer.text)
        payload = answer.json()
        self.assertEqual(payload["retrieval_mode"], "semantic_rerank")
        self.assertEqual(payload["retrieval_details"]["embedding_model"], "fake-embedding")
        self.assertTrue(payload["retrieval_details"]["reranked"])
        self.assertEqual(payload["trace"]["retrieval_debug"]["reranker_model"], "fake-reranker")

    def test_general_knowledge_scope_survives_http_response_model(self) -> None:
        pack_id = f"pack_http_general_{uuid4().hex[:8]}"

        class FakeGeneralKnowledgeProvider:
            model = "fake-general-model"

            def answer(self, question, chunks, graph_context):
                return AnswerWithSources(answer="자료에서는 확인되지 않지만 일반지식으로 설명합니다.")

        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            uploaded = self.client.post(
                "/v2/course-packs/upload",
                files={"files": ("nlp.txt", "BPE subword tokenization reduces OOV.", "text/plain")},
                data={"pack_id": pack_id, "run_async": "false"},
            )
            self.assertEqual(uploaded.status_code, 200, uploaded.text)

            with patch("v2.course_packs._answer_provider", return_value=FakeGeneralKnowledgeProvider()):
                answer = self.client.post(
                    "/v2/course-packs/ask",
                    json={
                        "pack_id": pack_id,
                        "question": "reinforcement learning policy reward",
                        "mode": "auto",
                        "llm_provider": "ollama",
                        "allow_general_fallback": True,
                    },
                )

        self.assertEqual(answer.status_code, 200, answer.text)
        payload = answer.json()
        self.assertEqual(payload["sources"], [])
        self.assertEqual(payload["answer_scope"], "general_knowledge")
        self.assertEqual(payload["grounding_status"], "ungrounded")
        self.assertTrue(payload["general_knowledge_used"])
        self.assertEqual(payload["trace"]["answer_scope"], "general_knowledge")
        self.assertTrue(payload["trace"]["general_knowledge_used"])

    def test_course_pack_answer_stream_returns_status_and_result_events(self) -> None:
        pack_id = f"pack_http_stream_{uuid4().hex[:8]}"
        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            uploaded = self.client.post(
                "/v2/course-packs/upload",
                files={"files": ("stream.txt", "BPE subword tokenization reduces OOV.", "text/plain")},
                data={"pack_id": pack_id, "run_async": "false"},
            )
            self.assertEqual(uploaded.status_code, 200, uploaded.text)

            response = self.client.post(
                "/v2/course-packs/ask/stream",
                json={
                    "pack_id": pack_id,
                    "question": "BPE와 OOV 관계",
                    "mode": "auto",
                    "conversation_history": [
                        {"role": "user", "content": "토큰화가 뭐야?"},
                        {"role": "assistant", "content": "텍스트를 처리 단위로 나누는 과정입니다."},
                    ],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertIn("event: status", response.text)
        self.assertIn("event: result", response.text)
        self.assertIn('"excerpt"', response.text)

    def test_external_web_scope_and_urls_survive_http_response_model(self) -> None:
        pack_id = f"pack_http_web_{uuid4().hex[:8]}"
        web_result = WebSearchResult(
            title="강화 학습",
            url="https://ko.wikipedia.org/wiki/강화_학습",
            text="강화 학습은 환경과 상호작용하며 누적 보상을 최대화하는 행동을 학습한다.",
            language="ko",
            page_id=101,
        )
        with patch.dict(os.environ, {"COURSEBEE_API_KEY": ""}):
            uploaded = self.client.post(
                "/v2/course-packs/upload",
                files={"files": ("nlp.txt", "BPE subword tokenization reduces OOV.", "text/plain")},
                data={"pack_id": pack_id, "run_async": "false"},
            )
            self.assertEqual(uploaded.status_code, 200, uploaded.text)

            with (
                patch("v2.course_packs._balanced_chunks", return_value=[]),
                patch("v2.course_packs.WikipediaSearchProvider.search", return_value=[web_result]),
            ):
                answer = self.client.post(
                    "/v2/course-packs/ask",
                    json={
                        "pack_id": pack_id,
                        "question": "강화학습이란?",
                        "mode": "vector",
                        "allow_web_fallback": True,
                        "allow_general_fallback": True,
                    },
                )

        self.assertEqual(answer.status_code, 200, answer.text)
        payload = answer.json()
        self.assertEqual(payload["answer_scope"], "external_web")
        self.assertEqual(payload["grounding_status"], "web_grounded")
        self.assertTrue(payload["web_search_used"])
        self.assertEqual(payload["sources"][0]["url"], web_result.url)
        self.assertEqual(payload["trace"]["answer_scope"], "external_web")
        self.assertTrue(payload["trace"]["web_search_used"])


if __name__ == "__main__":
    unittest.main()
