from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AudioMode = Literal["brief_1min", "briefing_3min", "briefing_5min", "lecture", "podcast"]
RetrievalMode = Literal[
    "vector", "hybrid", "lexical", "semantic", "semantic_hybrid", "semantic_rerank",
    "auto", "router", "local_graph", "hierarchical", "hierarchical_summary", "dual",
    "lightrag", "lightrag_dual",
]
LLMProviderName = Literal["mock", "rule", "local", "openai", "ollama", "qwen", "qwen3"]
WebProviderName = Literal["wikipedia"]


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChunkModel(BaseModel):
    chunk_id: str = Field(min_length=1, max_length=160)
    page: int = Field(default=1, ge=1, le=100000)
    text: str = Field(min_length=1, max_length=50000)
    char_start: int = Field(default=0, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    doc_id: str | None = None
    filename: str | None = None
    pack_id: str | None = None
    week: int | None = None
    lecture_no: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    output_root: str = Field(default="outputs", min_length=1, max_length=4096)
    max_chunk_chars: int = Field(default=900, ge=64, le=8000)


class DocumentResponse(BaseModel):
    doc_id: str
    filename: str | None = None
    page_count: int | None = None
    chunk_count: int | None = None
    output_dir: str | None = None
    warnings: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    doc_id: str | None = Field(default=None, min_length=1, max_length=160)
    question: str | None = Field(default=None, min_length=1, max_length=8000)
    query: str | None = Field(default=None, min_length=1, max_length=8000)
    top_k: int = Field(default=4, ge=1, le=50)
    output_root: str = Field(default="outputs", min_length=1, max_length=4096)
    output_dir: str | None = Field(default=None, min_length=1, max_length=4096)
    chunks: list[ChunkModel] | None = Field(default=None, max_length=500)


class AnswerResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    question: str | None = None
    retrieval_query: str | None = None
    conversation_context_used: bool = False
    conversation_turns_used: int = 0
    answer_scope: str = "course_pack"
    grounding_status: str = "grounded"
    general_knowledge_used: bool = False
    web_search_used: bool = False
    web_search: dict[str, Any] = Field(default_factory=dict)
    mode: str | None = None
    retrieval_mode: str | None = None
    retrieval_details: dict[str, Any] = Field(default_factory=dict)
    graph_context: list[dict[str, Any]] = Field(default_factory=list)
    matched_entities: list[str] = Field(default_factory=list)
    traversal_strategy: str | None = None
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    evidence_chunks: list[dict[str, Any]] = Field(default_factory=list)
    abstraction_level: str | None = None
    selected_summary_nodes: list[dict[str, Any]] = Field(default_factory=list)
    supporting_chunks: list[dict[str, Any]] = Field(default_factory=list)
    hierarchical_summary_index: dict[str, Any] = Field(default_factory=dict)
    routed_mode: str | None = None
    question_type: str | None = None
    retrieval_plan: list[dict[str, Any]] = Field(default_factory=list)
    selected_retrievers: list[str] = Field(default_factory=list)
    sentence_citations: list[dict[str, Any]] = Field(default_factory=list)
    llm: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

class StudyKitRequest(QueryRequest):
    max_items: int = Field(default=4, ge=1, le=50)


class AudioScriptRequest(QueryRequest):
    mode: AudioMode = "briefing_3min"
    llm_provider: LLMProviderName = "mock"
    llm_model: str | None = Field(default=None, min_length=1, max_length=200)
    grounding: Literal["creative", "strict"] = "creative"
    target_minutes: int | None = Field(default=None, ge=1, le=60)
    target_chars: int | None = Field(default=None, ge=200, le=100000)
    knowledge_scope: Literal["course_pack", "course_pack_plus_background", "external_rag", "background"] = "course_pack"


class AudioScriptResponse(BaseModel):
    mode: AudioMode | str
    script: list[dict[str, Any]] = Field(default_factory=list)
    script_char_count: int = 0
    segment_count: int = 0
    source_count: int = 0
    sources: list[dict[str, Any]] = Field(default_factory=list)
    estimated_duration_seconds: int = 0
    tts_status: str = "mock"
    audio_path: str | None = None
    audio_url: str | None = None
    duration_seconds: float | None = None
    artifact_name: str | None = None
    voices: dict[str, str] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    grounding: str | None = None
    grounding_check: dict[str, Any] = Field(default_factory=dict)
    knowledge_scope: str | None = None
    background_sources: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConceptMapRequest(QueryRequest):
    pass


class ConceptMapResponse(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CoursePackIngestRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=20)
    output_root: str = Field(default="outputs", min_length=1, max_length=4096)
    max_chunk_chars: int = Field(default=900, ge=64, le=8000)
    pack_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    append: bool = False


class CoursePackJobRequest(CoursePackIngestRequest):
    run_async: bool = False


class CoursePackJobResponse(BaseModel):
    job_id: str
    status: str
    stage: str
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    processed_documents: int = Field(default=0, ge=0)
    total_documents: int = Field(default=0, ge=0)
    pack_id: str | None = None
    course_pack: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class CoursePackResponse(BaseModel):
    pack_id: str
    document_count: int | None = None
    chunk_count: int | None = None
    added_document_count: int | None = None
    duplicate_document_count: int | None = None
    documents: list[dict[str, Any]] = Field(default_factory=list)
    output_dir: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CoursePackQueryRequest(BaseModel):
    pack_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    question: str | None = Field(default=None, min_length=1, max_length=8000)
    query: str | None = Field(default=None, min_length=1, max_length=8000)
    top_k: int = Field(default=4, ge=1, le=50)
    output_root: str = Field(default="outputs", min_length=1, max_length=4096)
    mode: RetrievalMode = "vector"
    llm_provider: LLMProviderName = "mock"
    llm_model: str | None = Field(default=None, min_length=1, max_length=200)
    allow_general_fallback: bool = False
    allow_web_fallback: bool = False
    web_provider: WebProviderName = "wikipedia"
    web_top_k: int = Field(default=3, ge=1, le=5)
    conversation_history: list[ConversationMessage] = Field(default_factory=list, max_length=12)


class CoursePackStudyKitRequest(CoursePackQueryRequest):
    max_items: int = Field(default=4, ge=1, le=50)


class CoursePackSummaryRequest(CoursePackQueryRequest):
    max_items: int = Field(default=5, ge=1, le=50)
    llm_provider: LLMProviderName = "mock"
    llm_model: str | None = Field(default=None, min_length=1, max_length=200)


class CoursePackSummaryResponse(BaseModel):
    pack_id: str | None = None
    overview: dict[str, Any] = Field(default_factory=dict)
    lecture_summaries: list[dict[str, Any]] = Field(default_factory=list)
    key_concepts: list[dict[str, Any]] = Field(default_factory=list)
    connections: list[dict[str, Any]] = Field(default_factory=list)
    review_points: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    llm: dict[str, Any] = Field(default_factory=dict)
    citation_check: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CoursePackOnboardingReportRequest(CoursePackQueryRequest):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    audience: str = Field(default="신입 구성원", min_length=1, max_length=200)
    objective: str = Field(
        default="핵심 규정과 업무 흐름을 출처와 함께 이해",
        min_length=1,
        max_length=500,
    )
    max_sections: int = Field(default=6, ge=1, le=20)


class CoursePackOnboardingReportResponse(BaseModel):
    pack_id: str
    report_type: str = "onboarding"
    title: str
    audience: str
    objective: str
    generated_at: str | None = None
    executive_summary: dict[str, Any] = Field(default_factory=dict)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    source_register: list[dict[str, Any]] = Field(default_factory=list)
    selection: dict[str, Any] = Field(default_factory=dict)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    impact_at_generation: dict[str, Any] = Field(default_factory=dict)
    generation: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    report_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CoursePackOnboardingReportImpactResponse(BaseModel):
    pack_id: str
    report_exists: bool = False
    report_generated_at: str | None = None
    report_title: str | None = None
    status: str
    requires_regeneration: bool
    change_count: int = 0
    added_sources: list[dict[str, Any]] = Field(default_factory=list)
    updated_sources: list[dict[str, Any]] = Field(default_factory=list)
    removed_sources: list[dict[str, Any]] = Field(default_factory=list)
    unchanged_source_count: int = 0
    executive_summary_affected: bool = False
    affected_sections: list[dict[str, Any]] = Field(default_factory=list)
    current_source_snapshot: dict[str, Any] = Field(default_factory=dict)


class CoursePackAudioScriptRequest(CoursePackQueryRequest):
    mode: AudioMode = "briefing_3min"
    llm_provider: LLMProviderName = "mock"
    llm_model: str | None = Field(default=None, min_length=1, max_length=200)
    grounding: Literal["creative", "strict"] = "creative"
    target_minutes: int | None = Field(default=None, ge=1, le=60)
    target_chars: int | None = Field(default=None, ge=200, le=100000)
    knowledge_scope: Literal["course_pack", "course_pack_plus_background", "external_rag", "background"] = "course_pack"
    voice: str = Field(default="ko-KR-SunHiNeural", pattern=r"^[A-Za-z0-9-]{1,80}$")
    guest_voice: str = Field(default="ko-KR-InJoonNeural", pattern=r"^[A-Za-z0-9-]{1,80}$")
    reuse_existing: bool = False


class CoursePackArtifactsResponse(BaseModel):
    pack_id: str
    output_dir: str | None = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    answers: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CoursePackConceptMapExportRequest(BaseModel):
    pack_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    output_root: str = Field(default="outputs", min_length=1, max_length=4096)
    max_nodes: int = Field(default=60, ge=1, le=500)
    max_edges: int = Field(default=120, ge=1, le=1000)


class CoursePackConceptMapExportResponse(BaseModel):
    pack_id: str
    output_dir: str | None = None
    format: str = "mermaid"
    mermaid_path: str | None = None
    html_path: str | None = None
    mermaid: str | None = None
    node_count: int = 0
    edge_count: int = 0
    exported_node_count: int = 0
    exported_edge_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class CoursePackConceptMapRequest(BaseModel):
    pack_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    output_root: str = Field(default="outputs", min_length=1, max_length=4096)

