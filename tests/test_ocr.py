from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

from v2.api import routes
from v2.api.schemas import AudioScriptRequest, ConceptMapRequest, QueryRequest, StudyKitRequest
from v2.ingest import ingest_local_document
from v2.providers.ocr import LocalTesseractOCRProvider, MockOCRProvider

TEST_OUTPUT_ROOT = Path.cwd() / "outputs" / "_test_ocr"


class OCRFallbackTest(unittest.TestCase):
    def _case_dir(self) -> Path:
        path = TEST_OUTPUT_ROOT / uuid4().hex
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _image_only_pdf(self, root: Path) -> Path:
        pdf_path = root / "image_only.pdf"
        image = Image.new("RGB", (1400, 500), "white")
        draw = ImageDraw.Draw(image)
        font_path = Path(r"C:\Windows\Fonts\arial.ttf")
        font = ImageFont.truetype(str(font_path), 58) if font_path.exists() else ImageFont.load_default()
        draw.text((70, 150), "OCR fallback PDF parsing source citation", fill="black", font=font)
        image.save(pdf_path, "PDF", resolution=200)
        return pdf_path

    def test_mock_ocr_provider_is_testable_without_engine(self) -> None:
        pages = MockOCRProvider("Mock OCR scanned PDF text").extract_pages("missing.pdf")

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].parser, "mock_ocr")
        self.assertIn("scanned PDF", pages[0].markdown)

    def test_tesseract_provider_extracts_image_only_pdf_when_available(self) -> None:
        provider = LocalTesseractOCRProvider()
        if not provider.is_available():
            self.skipTest("Tesseract OCR engine is not installed")

        root = self._case_dir()
        pdf_path = self._image_only_pdf(root)
        warnings: list[str] = []

        pages = provider.extract_pages(str(pdf_path), warnings)

        self.assertEqual(warnings, [])
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].parser, "tesseract_ocr")
        self.assertIn("OCR", pages[0].markdown)
        self.assertIn("PDF", pages[0].markdown)

    def test_pdf_ingest_uses_tesseract_ocr_fallback_when_available(self) -> None:
        provider = LocalTesseractOCRProvider()
        if not provider.is_available():
            self.skipTest("Tesseract OCR engine is not installed")

        root = self._case_dir()
        pdf_path = self._image_only_pdf(root)
        result = ingest_local_document(str(pdf_path), output_root=str(root / "outputs"), max_chunk_chars=300)

        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.chunk_count, 1)
        self.assertTrue(any("OCR fallback used" in warning for warning in result.warnings))
        chunks = json.loads((Path(result.output_dir) / "chunks.json").read_text(encoding="utf-8"))["chunks"]
        self.assertEqual(chunks[0]["page"], 1)
        self.assertEqual(chunks[0]["chunk_id"], "p1_c1")
        self.assertIn("OCR", chunks[0]["text"])

    def test_ocr_ingested_pdf_flows_to_v2_services(self) -> None:
        provider = LocalTesseractOCRProvider()
        if not provider.is_available():
            self.skipTest("Tesseract OCR engine is not installed")

        root = self._case_dir()
        pdf_path = self._image_only_pdf(root)
        result = ingest_local_document(str(pdf_path), output_root=str(root / "outputs"), max_chunk_chars=300)
        output_root = str(Path(result.output_dir).parent)

        ask = routes.ask(QueryRequest(doc_id=result.doc_id, question="OCR fallback PDF parsing", output_root=output_root))
        study = routes.study_kit(StudyKitRequest(doc_id=result.doc_id, output_root=output_root))
        audio = routes.audio_script(AudioScriptRequest(doc_id=result.doc_id, query="OCR fallback", output_root=output_root))
        graph = routes.concept_map(ConceptMapRequest(doc_id=result.doc_id, output_root=output_root))

        self.assertTrue(ask["answer"])
        self.assertTrue(ask["sources"])
        self.assertTrue(study["summary"]["sources"])
        self.assertTrue(audio["script"])
        self.assertTrue(audio["script"][0]["sources"])
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)


if __name__ == "__main__":
    unittest.main()
