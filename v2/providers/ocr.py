from __future__ import annotations

import os
import shutil
from io import BytesIO
from pathlib import Path

from v2.schemas import PageMarkdown

DEFAULT_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


class MockOCRProvider:
    def __init__(self, text: str = "OCR fallback extracted text from a scanned PDF.") -> None:
        self.text = text

    def extract_pages(self, pdf_path: str, warnings: list[str] | None = None) -> list[PageMarkdown]:
        return [PageMarkdown(page_number=1, markdown=self.text, parser="mock_ocr")]


class LocalTesseractOCRProvider:
    def __init__(self, tesseract_cmd: str | None = None, lang: str | None = None, dpi: int = 200) -> None:
        self.tesseract_cmd = tesseract_cmd or _resolve_tesseract_cmd()
        self.lang = lang or os.environ.get("COURSEBEE_OCR_LANG", "eng")
        self.dpi = dpi

    def is_available(self) -> bool:
        return bool(self.tesseract_cmd and Path(self.tesseract_cmd).exists())

    def extract_pages(self, pdf_path: str, warnings: list[str] | None = None) -> list[PageMarkdown]:
        warnings = warnings if warnings is not None else []
        if not self.is_available():
            warnings.append("OCR fallback unavailable: Tesseract executable was not found.")
            return []

        try:
            import fitz  # type: ignore[import-not-found]
            import pytesseract  # type: ignore[import-not-found]
            from PIL import Image
        except ImportError as error:
            warnings.append(f"OCR fallback unavailable: {error}")
            return []

        pytesseract.pytesseract.tesseract_cmd = str(self.tesseract_cmd)
        pages: list[PageMarkdown] = []
        try:
            with fitz.open(str(pdf_path)) as document:
                for index, page in enumerate(document, start=1):
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(self.dpi / 72, self.dpi / 72), alpha=False)
                    image = Image.open(BytesIO(pixmap.tobytes("png")))
                    text = pytesseract.image_to_string(image, lang=self.lang).strip()
                    if text:
                        pages.append(PageMarkdown(page_number=index, markdown=text, parser="tesseract_ocr"))
        except Exception as error:  # pragma: no cover - optional OCR boundary
            warnings.append(f"Tesseract OCR failed: {error}")
            return []

        if not pages:
            warnings.append("Tesseract OCR produced no text.")
        return pages


def _resolve_tesseract_cmd() -> str | None:
    env_path = os.environ.get("TESSERACT_CMD")
    if env_path and Path(env_path).exists():
        return env_path

    path_cmd = shutil.which("tesseract")
    if path_cmd:
        return path_cmd

    for candidate in DEFAULT_TESSERACT_PATHS:
        if Path(candidate).exists():
            return candidate
    return None
