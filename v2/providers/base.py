from __future__ import annotations

from typing import Protocol

from v2.providers.web_search import WebSearchResult
from v2.schemas import AnswerWithSources, Chunk, PageMarkdown, RelationTriple


class StorageProvider(Protocol):
    def save_json(self, doc_id: str, name: str, payload: dict) -> str:
        """Persist a JSON artifact and return its path or URL."""

    def save_bytes(self, doc_id: str, name: str, payload: bytes) -> str:
        """Persist a binary artifact and return its path or URL."""


class LLMProvider(Protocol):
    def summarize(self, chunks: list[Chunk]) -> str:
        """Generate a document summary from source chunks."""

    def answer(self, question: str, chunks: list[Chunk], graph_context: list[RelationTriple]) -> AnswerWithSources:
        """Generate an answer grounded in retrieved chunks and optional graph triples."""

    def extract_relations(self, chunks: list[Chunk]) -> list[RelationTriple]:
        """Extract relation triples for GraphRAG-lite."""

    def generate_script(self, chunks: list[Chunk], minutes: int) -> str:
        """Generate an audio or presentation script."""


class TTSProvider(Protocol):
    def synthesize(self, doc_id: str, script: str) -> str | None:
        """Generate audio and return a local path, remote URL, or None for mock TTS."""


class RetrieverProvider(Protocol):
    def search(self, question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
        """Return relevant chunks while preserving source metadata."""


class WebSearchProvider(Protocol):
    def search(self, query: str, top_k: int = 3) -> list[WebSearchResult]:
        """Return trusted external documents for Web RAG."""


class IndexProvider(RetrieverProvider, Protocol):
    def build(self, doc_id: str, chunks: list[Chunk]) -> str:
        """Build an index and return the index path or collection name."""

class ParserProvider(Protocol):
    def parse(self, path: str) -> list[PageMarkdown]:
        """Parse a local document into page-level markdown."""


class OCRProvider(Protocol):
    def extract_pages(self, pdf_path: str, warnings: list[str] | None = None) -> list[PageMarkdown]:
        """Extract page text from a scanned PDF or image-only PDF."""


DocumentParser = ParserProvider
