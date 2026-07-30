from __future__ import annotations

import argparse
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "reports" / "coursebee-v3-portfolio-report-ko.html"
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "coursebee-v3-portfolio-report-ko.pdf"


def render_report(source: Path, output: Path) -> list[Path]:
    source = source.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1123, "height": 1587}, device_scale_factor=1)
        page.goto(source.as_uri(), wait_until="networkidle")
        page.emulate_media(media="print")
        page.pdf(
            path=str(output),
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()

    preview_dir = output.parent / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(output)
    if document.page_count != 2:
        raise RuntimeError(f"Expected 2 pages, got {document.page_count}")

    previews: list[Path] = []
    for index, pdf_page in enumerate(document):
        preview = preview_dir / f"{output.stem}-page-{index + 1}.png"
        pdf_page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False).save(preview)
        previews.append(preview)
    document.close()
    return previews


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the CourseBee portfolio report and PNG previews.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    previews = render_report(args.source, args.output)
    print(args.output.resolve())
    for preview in previews:
        print(preview.resolve())


if __name__ == "__main__":
    main()
