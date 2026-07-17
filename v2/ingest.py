from __future__ import annotations

import hashlib
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from v2.graph.concept_map import build_concept_map
from v2.io_utils import atomic_write_json
from v2.providers.ocr import LocalTesseractOCRProvider
from v2.rag.chunking import chunk_pages
from v2.schemas import DocumentIngestResult, PageMarkdown

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".pptx"}
PML_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
DRAWING_TEXT_TAG = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
REL_ID_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def ingest_local_document(path: str, output_root: str = "outputs", max_chunk_chars: int = 900) -> DocumentIngestResult:
    source_path = Path(path)
    warnings: list[str] = []

    if not source_path.exists():
        doc_id = f"missing_{uuid4().hex[:12]}"
        warnings.append(f"file not found: {source_path}")
        return _write_ingest_outputs(doc_id, source_path.name, [], output_root, warnings, max_chunk_chars)

    extension = source_path.suffix.lower()
    doc_id = _sha256_file(source_path)

    if extension not in SUPPORTED_EXTENSIONS:
        warnings.append(f"unsupported file extension: {extension or '<none>'}")
        return _write_ingest_outputs(doc_id, source_path.name, [], output_root, warnings, max_chunk_chars)

    if extension == ".pdf":
        pages = _parse_pdf(source_path, warnings)
    elif extension == ".pptx":
        pages = _parse_pptx(source_path, warnings)
    else:
        pages = _parse_text_document(source_path, warnings, parser=extension.lstrip("."))

    return _write_ingest_outputs(doc_id, source_path.name, pages, output_root, warnings, max_chunk_chars)


def _parse_text_document(path: Path, warnings: list[str], parser: str) -> list[PageMarkdown]:
    text = _read_text(path, warnings)
    if not text.strip():
        warnings.append("document text is empty")
        return []
    return [PageMarkdown(page_number=1, markdown=text, parser=parser)]


def _parse_pptx(path: Path, warnings: list[str]) -> list[PageMarkdown]:
    try:
        with zipfile.ZipFile(path) as archive:
            slide_names = _ordered_pptx_slide_names(archive)
            if not slide_names:
                warnings.append("PPTX contains no readable slides.")
                return []

            pages: list[PageMarkdown] = []
            for slide_number, slide_name in enumerate(slide_names, start=1):
                text = _pptx_xml_text(archive.read(slide_name))
                if text.strip():
                    pages.append(PageMarkdown(page_number=slide_number, markdown=text, parser="pptx"))
            if not pages:
                warnings.append("PPTX slides did not contain extractable text.")
            return pages
    except zipfile.BadZipFile:
        warnings.append("PPTX parser failed: invalid pptx zip package")
        return []
    except KeyError as error:
        warnings.append(f"PPTX parser failed: missing package part {error}")
        return []
    except ET.ParseError as error:
        warnings.append(f"PPTX parser failed: invalid slide XML {error}")
        return []


def _ordered_pptx_slide_names(archive: zipfile.ZipFile) -> list[str]:
    names = set(archive.namelist())
    fallback = sorted(
        (name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
        key=_slide_number_from_name,
    )

    try:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        rels = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
    except (KeyError, ET.ParseError):
        return fallback

    relationships = {
        rel.attrib.get("Id"): rel.attrib.get("Target", "")
        for rel in rels
        if rel.attrib.get("Id") and rel.attrib.get("Target")
    }

    ordered: list[str] = []
    for slide_id in presentation.findall(f".//{PML_NS}sldId"):
        rel_id = slide_id.attrib.get(REL_ID_ATTR)
        target = relationships.get(rel_id or "")
        if not target:
            continue
        slide_name = _normalize_pptx_target(target)
        if slide_name in names:
            ordered.append(slide_name)

    return ordered or fallback


def _normalize_pptx_target(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    if target.startswith("ppt/"):
        return posixpath.normpath(target)
    return posixpath.normpath(f"ppt/{target}")


def _slide_number_from_name(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _pptx_xml_text(payload: bytes) -> str:
    root = ET.fromstring(payload)
    texts: list[str] = []
    for element in root.iter():
        if element.tag != DRAWING_TEXT_TAG or element.text is None:
            continue
        text = " ".join(element.text.split())
        if text:
            texts.append(text)
    return "\n".join(_dedupe_consecutive(texts))


def _dedupe_consecutive(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if not deduped or deduped[-1] != item:
            deduped.append(item)
    return deduped


def _has_enough_text(pages: list[PageMarkdown], min_chars: int = 40) -> bool:
    total_chars = sum(len(page.markdown.strip()) for page in pages)
    return total_chars >= min_chars


def _parse_pdf(path: Path, warnings: list[str]) -> list[PageMarkdown]:
    parser_seen = False
    for parser in (_parse_pdf_with_pymupdf4llm, _parse_pdf_with_pymupdf):
        pages = parser(path, warnings)
        if pages is None:
            continue
        parser_seen = True
        if _has_enough_text(pages):
            return pages

    ocr_pages = LocalTesseractOCRProvider().extract_pages(str(path), warnings)
    if ocr_pages:
        warnings.append("OCR fallback used: tesseract_ocr")
        return ocr_pages

    if not parser_seen:
        warnings.append("PDF parser is unavailable. Install pymupdf4llm or PyMuPDF to ingest PDF files.")
    return []


def _parse_pdf_with_pymupdf4llm(path: Path, warnings: list[str]) -> list[PageMarkdown] | None:
    try:
        import pymupdf4llm  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        result = pymupdf4llm.to_markdown(str(path), page_chunks=True)
    except Exception as error:  # pragma: no cover - optional dependency boundary
        warnings.append(f"pymupdf4llm failed: {error}")
        return []

    if isinstance(result, list):
        pages: list[PageMarkdown] = []
        for index, item in enumerate(result, start=1):
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("markdown") or "").strip()
                metadata = item.get("metadata") or {}
                page_number = int(metadata.get("page", index)) if isinstance(metadata, dict) else index
            else:
                text = str(item).strip()
                page_number = index
            if text:
                pages.append(PageMarkdown(page_number=page_number, markdown=text, parser="pymupdf4llm"))
        return pages

    text = str(result).strip()
    return [PageMarkdown(page_number=1, markdown=text, parser="pymupdf4llm")] if text else []


def _parse_pdf_with_pymupdf(path: Path, warnings: list[str]) -> list[PageMarkdown] | None:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        pages: list[PageMarkdown] = []
        with fitz.open(str(path)) as document:
            for index, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                if text:
                    pages.append(PageMarkdown(page_number=index, markdown=text, parser="pymupdf"))
        if not pages:
            warnings.append("PDF text layer is empty. OCR fallback is required for this document.")
        return pages
    except Exception as error:  # pragma: no cover - optional dependency boundary
        warnings.append(f"PyMuPDF failed: {error}")
        return []


def _write_ingest_outputs(
    doc_id: str,
    filename: str,
    pages: list[PageMarkdown],
    output_root: str,
    warnings: list[str],
    max_chunk_chars: int,
) -> DocumentIngestResult:
    chunks = chunk_pages(pages, max_chars=max_chunk_chars, filename=filename, doc_id=doc_id)
    output_dir = Path(output_root) / doc_id
    answers_dir = output_dir / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)

    result = DocumentIngestResult(
        doc_id=doc_id,
        filename=filename,
        page_count=len(pages),
        chunk_count=len(chunks),
        output_dir=str(output_dir),
        warnings=warnings,
    )

    _write_json(output_dir / "document.json", result.to_dict())
    _write_json(output_dir / "pages.json", {"pages": [asdict(page) for page in pages]})
    _write_json(output_dir / "chunks.json", {"chunks": [asdict(chunk) for chunk in chunks]})
    build_concept_map(chunks, output_dir=str(output_dir))
    _write_json(output_dir / "study_kit.json", {})
    _write_json(output_dir / "audio_script.json", {})
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_text(path: Path, warnings: list[str]) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp949"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    warnings.append("failed to decode text as utf-8, utf-8-sig, or cp949")
    return ""


def _write_json(path: Path, payload: dict) -> None:
    atomic_write_json(path, payload)
