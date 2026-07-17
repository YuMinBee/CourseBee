from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4

try:
    from fastapi import HTTPException
except ImportError:  # pragma: no cover
    HTTPException = None  # type: ignore[assignment]

from v2.api import routes
from v2.api.schemas import AudioScriptRequest, ConceptMapRequest, IngestRequest, QueryRequest, StudyKitRequest

TEST_OUTPUT_ROOT = Path.cwd() / "outputs" / "_test_v2_endpoints"


class V2EndpointBehaviorTest(unittest.TestCase):
    def _case_dir(self) -> Path:
        path = TEST_OUTPUT_ROOT / uuid4().hex
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _ingest_text(self, suffix: str = ".txt") -> dict:
        root = self._case_dir()
        source = root / f"sample{suffix}"
        source.write_text(
            "BeePDF v2 keeps page source citation for PDF parsing. "
            "OCR supports scanned PDF parsing and GraphRAG-lite concept maps.",
            encoding="utf-8",
        )
        return routes.ingest_document(IngestRequest(path=str(source), output_root=str(root / "outputs"), max_chunk_chars=80))

    def test_v2_ingest_text_document(self) -> None:
        txt = self._ingest_text(".txt")
        md = self._ingest_text(".md")

        self.assertEqual(txt["page_count"], 1)
        self.assertGreaterEqual(txt["chunk_count"], 1)
        self.assertEqual(txt["warnings"], [])
        self.assertEqual(md["page_count"], 1)
        self.assertGreaterEqual(md["chunk_count"], 1)
        self.assertEqual(md["warnings"], [])

    def test_v2_chunks_keep_page_source(self) -> None:
        result = self._ingest_text(".txt")
        chunks = json.loads((Path(result["output_dir"]) / "chunks.json").read_text(encoding="utf-8"))["chunks"]

        self.assertIn("page", chunks[0])
        self.assertIn("chunk_id", chunks[0])
        self.assertEqual(chunks[0]["page"], 1)
        self.assertEqual(chunks[0]["chunk_id"], "p1_c1")
        self.assertEqual(chunks[0]["metadata"]["doc_id"], result["doc_id"])
        self.assertEqual(chunks[0]["metadata"]["filename"], "sample.txt")

    def test_v2_ask_returns_sources(self) -> None:
        result = self._ingest_text(".txt")
        response = routes.ask(
            QueryRequest(
                doc_id=result["doc_id"],
                question="PDF parsing source citation",
                output_root=str(Path(result["output_dir"]).parent),
                top_k=2,
            )
        )

        self.assertTrue(response["answer"])
        self.assertTrue(response["sources"])
        self.assertEqual(response["warnings"], [])

    def test_v2_missing_doc_returns_404(self) -> None:
        missing_id = f"missing-{uuid4().hex}"
        if HTTPException is None:
            with self.assertRaises(FileNotFoundError):
                routes.get_document(missing_id, output_root=str(TEST_OUTPUT_ROOT))
        else:
            with self.assertRaises(HTTPException) as context:
                routes.get_document(missing_id, output_root=str(TEST_OUTPUT_ROOT))
            self.assertEqual(context.exception.status_code, 404)

    def test_v2_study_kit_has_sources(self) -> None:
        result = self._ingest_text(".txt")
        response = routes.study_kit(StudyKitRequest(doc_id=result["doc_id"], output_root=str(Path(result["output_dir"]).parent)))

        self.assertTrue(response["summary"]["sources"])
        self.assertTrue(all(item["sources"] for item in response["key_points"]))
        self.assertTrue(all(item["sources"] for item in response["quiz"]))

    def test_v2_audio_script_has_sources(self) -> None:
        result = self._ingest_text(".txt")
        response = routes.audio_script(
            AudioScriptRequest(
                doc_id=result["doc_id"],
                query="PDF parsing",
                output_root=str(Path(result["output_dir"]).parent),
                mode="briefing_3min",
            )
        )

        self.assertEqual(response["tts_status"], "mock")
        self.assertIsNone(response["audio_path"])
        self.assertTrue(response["script"])
        self.assertTrue(all(item["sources"] for item in response["script"]))

    def test_v2_concept_map_no_crash(self) -> None:
        result = self._ingest_text(".txt")
        response = routes.concept_map(
            ConceptMapRequest(
                doc_id=result["doc_id"],
                output_root=str(Path(result["output_dir"]).parent),
            )
        )

        self.assertIn("nodes", response)
        self.assertIn("edges", response)
        self.assertTrue(all(edge["evidence"] for edge in response["edges"]))

    def test_existing_v1_endpoint_not_present_or_unchanged(self) -> None:
        # This local scaffold has no v1 FastAPI route files, so the v2 work has no v1 surface to mutate.
        paths = {getattr(route, "path", None) for route in routes.router.routes} if routes.router is not None else set()
        self.assertFalse(any(path.startswith("/v1") for path in paths))


if __name__ == "__main__":
    unittest.main()


