from __future__ import annotations

import unittest

from v2.api.routes import router
from v2.api.schemas import (
    AudioScriptRequest,
    AudioScriptResponse,
    CoursePackJobRequest,
    CoursePackOnboardingReportRequest,
    CoursePackSummaryRequest,
    IngestRequest,
    QueryRequest,
)


class ApiSchemaTest(unittest.TestCase):
    def test_pydantic_requests_validate_defaults(self) -> None:
        ingest = IngestRequest(path="sample.txt")
        query = QueryRequest(doc_id="abc123", question="What is this document about?")
        audio = AudioScriptRequest(doc_id="abc123", query="OCR", mode="briefing_3min")
        summary = CoursePackSummaryRequest(pack_id="pack_abc123")
        report = CoursePackOnboardingReportRequest(pack_id="pack_abc123")
        job = CoursePackJobRequest(paths=["week1.txt"])
        audio_response = AudioScriptResponse(mode="podcast", grounding_check={"passed": True})

        self.assertEqual(ingest.output_root, "outputs")
        self.assertEqual(query.top_k, 4)
        self.assertEqual(audio.mode, "briefing_3min")
        self.assertEqual(audio.llm_provider, "mock")
        self.assertEqual(audio.grounding, "creative")
        self.assertEqual(audio.target_minutes, None)
        self.assertEqual(audio.target_chars, None)
        self.assertEqual(audio.knowledge_scope, "course_pack")
        self.assertTrue(audio_response.model_dump()["grounding_check"]["passed"])
        self.assertEqual(summary.llm_provider, "mock")
        self.assertEqual(summary.llm_model, None)
        self.assertEqual(report.audience, "신입 구성원")
        self.assertEqual(report.max_sections, 6)
        self.assertEqual(job.output_root, "outputs")
        self.assertEqual(job.max_chunk_chars, 900)
        self.assertFalse(job.run_async)
        self.assertTrue(CoursePackJobRequest(paths=["week1.txt"], run_async=True).run_async)

    def test_router_is_defined_when_fastapi_is_available(self) -> None:
        if router is not None:
            paths = {getattr(route, "path", None) for route in router.routes}
            self.assertIn("/v2/documents/ingest", paths)
            self.assertIn("/v2/documents/{doc_id}", paths)
            self.assertIn("/v2/course-packs/jobs", paths)
            self.assertIn("/v2/course-packs/jobs/{job_id}", paths)
            self.assertIn("/v2/ask", paths)
            self.assertIn("/v2/study-kit", paths)
            self.assertIn("/v2/audio-script", paths)
            self.assertIn("/v2/concept-map", paths)
            self.assertIn("/v2/course-packs/onboarding-report", paths)
            self.assertIn("/v2/course-packs/{pack_id}/onboarding-report-impact", paths)


if __name__ == "__main__":
    unittest.main()
