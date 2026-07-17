from __future__ import annotations

import re

from v2.schemas import Chunk, PageMarkdown
from v2.source_metadata import lecture_metadata_from_filename


def chunk_pages(
    pages: list[PageMarkdown],
    max_chars: int = 900,
    filename: str | None = None,
    doc_id: str | None = None,
) -> list[Chunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    chunks: list[Chunk] = []
    for page in pages:
        text = page.markdown
        if not text.strip():
            continue

        chunk_index = 1
        overlap_chars = min(120, max(0, max_chars // 6)) if max_chars >= 240 else 0
        for start, end in _chunk_spans(text, max_chars=max_chars, overlap_chars=overlap_chars):
            raw_part = text[start:end]
            if not raw_part.strip():
                continue
            leading = len(raw_part) - len(raw_part.lstrip())
            trailing = len(raw_part) - len(raw_part.rstrip())
            clean_start = start + leading
            clean_end = end - trailing
            metadata = {"parser": page.parser}
            if doc_id:
                metadata["doc_id"] = doc_id
            if filename:
                metadata["filename"] = filename
                metadata.update(lecture_metadata_from_filename(filename))
            chunks.append(
                Chunk(
                    chunk_id=f"p{page.page_number}_c{chunk_index}",
                    page=page.page_number,
                    text=raw_part.strip(),
                    char_start=clean_start,
                    char_end=clean_end,
                    metadata=metadata,
                )
            )
            chunk_index += 1
    return chunks


def _chunk_spans(text: str, max_chars: int, overlap_chars: int) -> list[tuple[int, int]]:
    if len(text) <= max_chars:
        return [(0, len(text))]

    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + max_chars)
        end = _preferred_boundary(text, start, hard_end, max_chars)
        if end <= start:
            end = hard_end
        spans.append((start, end))
        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap_chars)
        whitespace = re.search(r"\s+", text[next_start:end])
        if whitespace:
            next_start += whitespace.end()
        start = min(next_start, end)
    return spans


def _preferred_boundary(text: str, start: int, hard_end: int, max_chars: int) -> int:
    if hard_end >= len(text):
        return len(text)
    minimum = start + max(40, int(max_chars * 0.55))
    window = text[minimum:hard_end]
    boundaries = [
        match.end() + minimum
        for match in re.finditer(r"(?:[.!?。！？]\s+|\n{2,}|\n|\s)", window)
    ]
    return boundaries[-1] if boundaries else hard_end
