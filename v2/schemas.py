from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class PageMarkdown:
    page_number: int
    markdown: str
    parser: str = "mock"


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    page: int
    text: str
    char_start: int
    char_end: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def page_number(self) -> int:
        return self.page

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceRef:
    page: int
    chunk_id: str
    doc_id: str | None = None
    filename: str | None = None
    week: int | None = None
    lecture_no: int | None = None
    excerpt: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    title: str | None = None
    url: str | None = None
    source_type: str | None = None
    provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(slots=True)
class RetrievalContext:
    chunk_id: str
    page: int
    score: float
    text: str
    char_start: int | None = None
    char_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RetrievalResult:
    query: str
    top_k: int
    contexts: list[RetrievalContext] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "top_k": self.top_k,
            "contexts": [context.to_dict() for context in self.contexts],
        }


@dataclass(slots=True)
class SourceGroundedAnswer:
    answer: str
    sources: list[SourceRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    answer_scope: str = "course_pack"
    grounding_status: str = "grounded"
    general_knowledge_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [source.to_dict() for source in self.sources],
            "warnings": self.warnings,
            "answer_scope": self.answer_scope,
            "grounding_status": self.grounding_status,
            "general_knowledge_used": self.general_knowledge_used,
        }


@dataclass(slots=True)
class VectorSource:
    page: int
    chunk_id: str
    doc_id: str | None = None
    filename: str | None = None
    week: int | None = None
    lecture_no: int | None = None
    score: float | None = None


@dataclass(slots=True)
class RelationTriple:
    subject: str
    predicate: str
    object: str

    def as_list(self) -> list[str]:
        return [self.subject, self.predicate, self.object]


@dataclass(slots=True)
class AnswerWithSources:
    answer: str
    vector_sources: list[VectorSource] = field(default_factory=list)
    graph_context: list[RelationTriple] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "vector_sources": [asdict(source) for source in self.vector_sources],
            "graph_context": [triple.as_list() for triple in self.graph_context],
        }


@dataclass(slots=True)
class WorkflowError:
    request_id: str
    node: str
    error_type: str
    message: str
    retryable: bool = False


@dataclass(slots=True)
class DocumentIngestResult:
    doc_id: str
    filename: str
    page_count: int
    chunk_count: int
    output_dir: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

