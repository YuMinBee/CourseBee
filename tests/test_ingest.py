from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path
from uuid import uuid4

from v2.ingest import ingest_local_document

TEST_TMP_ROOT = Path.cwd() / "outputs" / "_test_ingest"


class LocalDocumentIngestTest(unittest.TestCase):
    def _case_dir(self) -> Path:
        path = TEST_TMP_ROOT / uuid4().hex
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_ingest_txt_writes_expected_artifacts_and_page_chunks(self) -> None:
        root = self._case_dir()
        source = root / "sample.txt"
        source.write_text("BeePDF uses sha256 cache.\nrequest_id enables tracking.", encoding="utf-8")

        result = ingest_local_document(str(source), output_root=str(root / "outputs"), max_chunk_chars=30)

        self.assertEqual(result.filename, "sample.txt")
        self.assertEqual(result.page_count, 1)
        self.assertGreaterEqual(result.chunk_count, 1)
        self.assertEqual(result.warnings, [])

        output_dir = Path(result.output_dir)
        self.assertTrue((output_dir / "document.json").exists())
        self.assertTrue((output_dir / "pages.json").exists())
        self.assertTrue((output_dir / "chunks.json").exists())
        self.assertTrue((output_dir / "graph.json").exists())
        self.assertTrue((output_dir / "answers").is_dir())
        self.assertTrue((output_dir / "study_kit.json").exists())
        self.assertTrue((output_dir / "audio_script.json").exists())

        document = json.loads((output_dir / "document.json").read_text(encoding="utf-8"))
        chunks = json.loads((output_dir / "chunks.json").read_text(encoding="utf-8"))["chunks"]
        self.assertEqual(document["doc_id"], result.doc_id)
        self.assertEqual(chunks[0]["chunk_id"], "p1_c1")
        self.assertEqual(chunks[0]["page"], 1)
        self.assertEqual(chunks[0]["char_start"], 0)
        self.assertGreater(chunks[0]["char_end"], chunks[0]["char_start"])
        self.assertEqual(chunks[0]["metadata"]["filename"], "sample.txt")
        self.assertEqual(chunks[0]["metadata"]["doc_id"], result.doc_id)

    def test_ingest_md_writes_one_page_without_dependency(self) -> None:
        root = self._case_dir()
        source = root / "sample.md"
        source.write_text("# BeePDF\n\nGraphRAG-lite keeps relation context.", encoding="utf-8")

        result = ingest_local_document(str(source), output_root=str(root / "outputs"))

        self.assertEqual(result.filename, "sample.md")
        self.assertEqual(result.page_count, 1)
        self.assertGreaterEqual(result.chunk_count, 1)
        self.assertEqual(result.warnings, [])

    def test_ingest_pptx_extracts_slide_text_without_dependency(self) -> None:
        root = self._case_dir()
        source = root / "lecture.pptx"
        _write_sample_pptx(
            source,
            [
                ["Natural Language Processing", "RAG keeps source citation"],
                ["GraphRAG-lite", "Concept map links OCR and PDF parsing"],
            ],
        )

        result = ingest_local_document(str(source), output_root=str(root / "outputs"), max_chunk_chars=120)

        self.assertEqual(result.filename, "lecture.pptx")
        self.assertEqual(result.page_count, 2)
        self.assertGreaterEqual(result.chunk_count, 2)
        self.assertEqual(result.warnings, [])

        output_dir = Path(result.output_dir)
        pages = json.loads((output_dir / "pages.json").read_text(encoding="utf-8"))["pages"]
        chunks = json.loads((output_dir / "chunks.json").read_text(encoding="utf-8"))["chunks"]
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertEqual(pages[0]["parser"], "pptx")
        self.assertIn("Natural Language Processing", pages[0]["markdown"])
        self.assertEqual(chunks[0]["page"], 1)
        self.assertEqual(chunks[0]["metadata"]["filename"], "lecture.pptx")
        self.assertEqual(chunks[0]["metadata"]["doc_id"], result.doc_id)

    def test_missing_file_returns_warning_without_raising(self) -> None:
        root = self._case_dir()
        result = ingest_local_document(str(root / "missing.pdf"), output_root=str(root / "outputs"))

        self.assertEqual(result.page_count, 0)
        self.assertEqual(result.chunk_count, 0)
        self.assertTrue(result.warnings)

    def test_pdf_parser_failure_returns_warning_without_raising(self) -> None:
        root = self._case_dir()
        source = root / "sample.pdf"
        source.write_bytes(b"not a real pdf")

        result = ingest_local_document(str(source), output_root=str(root / "outputs"))

        self.assertEqual(result.page_count, 0)
        self.assertEqual(result.chunk_count, 0)
        self.assertTrue(result.warnings)

    def test_unsupported_extension_returns_warning_without_raising(self) -> None:
        root = self._case_dir()
        source = root / "sample.csv"
        source.write_text("a,b\n1,2", encoding="utf-8")

        result = ingest_local_document(str(source), output_root=str(root / "outputs"))

        self.assertEqual(result.page_count, 0)
        self.assertEqual(result.chunk_count, 0)
        self.assertTrue(result.warnings)


def _write_sample_pptx(path: Path, slides: list[list[str]]) -> None:
    slide_ids = "".join(
        f'<p:sldId id="{256 + index}" r:id="rId{index}"/>' for index in range(1, len(slides) + 1)
    )
    rels = "".join(
        '<Relationship '
        f'Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        f'Target="slides/slide{index}.xml"/>'
        for index in range(1, len(slides) + 1)
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "ppt/presentation.xml",
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>{slide_ids}</p:sldIdLst>
</p:presentation>''',
        )
        archive.writestr(
            "ppt/_rels/presentation.xml.rels",
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>''',
        )
        for index, texts in enumerate(slides, start=1):
            archive.writestr(f"ppt/slides/slide{index}.xml", _slide_xml(texts))


def _slide_xml(texts: list[str]) -> str:
    paragraphs = "".join(f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p>" for text in texts)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree><p:sp><p:txBody>{paragraphs}</p:txBody></p:sp></p:spTree></p:cSld>
</p:sld>'''


if __name__ == "__main__":
    unittest.main()
