from __future__ import annotations

import json
from pathlib import Path

from v2.providers.base import ParserProvider
from v2.rag.retrieval import chunks_from_contexts, retrieve_contexts
from v2.schemas import AnswerWithSources, Chunk, PageMarkdown, RelationTriple, VectorSource


class LocalStorageProvider:
    def __init__(self, root: str = "outputs") -> None:
        self.root = Path(root)

    def save_json(self, doc_id: str, name: str, payload: dict) -> str:
        path = self.root / doc_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def save_bytes(self, doc_id: str, name: str, payload: bytes) -> str:
        path = self.root / doc_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return str(path)


class MockDocumentParser(ParserProvider):
    def parse(self, pdf_path: str) -> list[PageMarkdown]:
        return [
            PageMarkdown(
                page_number=1,
                markdown=(
                    "# CourseBee\n"
                    "sha256 cache reduces repeated processing cost. "
                    "request_id enables failure tracking. "
                    "OCR fallback handles scanned PDFs."
                ),
            )
        ]


class MockLLMProvider:
    def summarize(self, chunks: list[Chunk]) -> str:
        return "CourseBee focuses on reliable ingestion, source-grounded Q&A, and learning artifacts."

    def answer(self, question: str, chunks: list[Chunk], graph_context: list[RelationTriple]) -> AnswerWithSources:
        if not chunks:
            return AnswerWithSources(answer="")
        sources = [
            VectorSource(page=chunk.page, chunk_id=chunk.chunk_id, score=chunk.metadata.get("retrieval_score"))
            for chunk in chunks
        ]
        evidence = " ".join(chunk.text for chunk in chunks)
        answer = f"Based on the retrieved document context: {evidence[:300]}"
        return AnswerWithSources(answer=answer, vector_sources=sources, graph_context=graph_context)

    def extract_relations(self, chunks: list[Chunk]) -> list[RelationTriple]:
        return [
            RelationTriple("sha256 cache", "reduces", "repeated processing cost"),
            RelationTriple("request_id", "enables", "failure tracking"),
            RelationTriple("OCR fallback", "handles", "scanned PDFs"),
        ]

    def generate_script(self, chunks: list[Chunk], minutes: int) -> str:
        return f"CourseBee presentation script. Target length: {minutes} minutes."


class MockTTSProvider:
    def synthesize(self, doc_id: str, script: str) -> None:
        return None


class MockIndexProvider:
    def build(self, doc_id: str, chunks: list[Chunk]) -> str:
        return f"outputs/{doc_id}/vector_index.json"

    def search(self, question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
        result = retrieve_contexts(question, chunks, top_k=top_k)
        return chunks_from_contexts(result.contexts)



