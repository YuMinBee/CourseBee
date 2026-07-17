from __future__ import annotations

from pathlib import Path

from v2.ingest import _parse_pdf, _parse_pptx, _parse_text_document
from v2.providers.mock import LocalStorageProvider, MockLLMProvider, MockTTSProvider
from v2.providers.ocr import LocalTesseractOCRProvider, MockOCRProvider
from v2.providers.openai import OpenAIProvider, OpenAIProviderError
from v2.providers.semantic import EmbeddingRetriever, SemanticHybridRetriever
from v2.rag.retrieval import chunks_from_contexts, retrieve_contexts
from v2.schemas import Chunk, PageMarkdown


class LocalParserProvider:
    def parse(self, path: str) -> list[PageMarkdown]:
        source_path = Path(path)
        warnings: list[str] = []
        extension = source_path.suffix.lower()
        if extension == ".pdf":
            return _parse_pdf(source_path, warnings)
        if extension == ".pptx":
            return _parse_pptx(source_path, warnings)
        if extension in {".txt", ".md"}:
            return _parse_text_document(source_path, warnings, parser=extension.lstrip("."))
        return []


class LexicalRetriever:
    def search(self, question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
        return chunks_from_contexts(retrieve_contexts(question, chunks, top_k=top_k, strategy="lexical").contexts)


class HybridRetriever:
    def search(self, question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
        return chunks_from_contexts(retrieve_contexts(question, chunks, top_k=top_k, strategy="hybrid").contexts)


class SimpleRetriever(LexicalRetriever):
    pass


class LocalIndexProvider(HybridRetriever):
    def build(self, doc_id: str, chunks: list[Chunk]) -> str:
        return f"outputs/{doc_id}/simple_retriever.json"


__all__ = [
    "LocalStorageProvider",
    "MockLLMProvider",
    "MockTTSProvider",
    "MockOCRProvider",
    "LocalTesseractOCRProvider",
    "LocalParserProvider",
    "LexicalRetriever",
    "HybridRetriever",
    "EmbeddingRetriever",
    "SemanticHybridRetriever",
    "SimpleRetriever",
    "LocalIndexProvider",
    "OpenAIProviderError",
    "OpenAIProvider",
]
