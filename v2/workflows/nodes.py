from __future__ import annotations

from dataclasses import asdict

from v2.graph.concept_map import build_concept_map
from v2.providers.base import DocumentParser, IndexProvider, LLMProvider, StorageProvider
from v2.rag.chunking import chunk_pages
from v2.rag.citations import check_text_grounding
from v2.rag.vector_rag import answer_with_sources
from v2.workflows.state import BeePDFState


def parse_pdf_node(state: BeePDFState, parser: DocumentParser) -> BeePDFState:
    try:
        state.pages = parser.parse(state.pdf_path)
    except Exception as error:  # pragma: no cover - boundary node
        state.add_error("parse_pdf_node", error, retryable=False)
    return state


def ocr_fallback_node(state: BeePDFState) -> BeePDFState:
    # Real OCR fallback can be attached here when page markdown quality is low.
    return state


def chunk_node(state: BeePDFState) -> BeePDFState:
    try:
        state.chunks = chunk_pages(state.pages)
    except Exception as error:  # pragma: no cover - boundary node
        state.add_error("chunk_node", error, retryable=False)
    return state


def vector_index_node(state: BeePDFState, index_provider: IndexProvider) -> BeePDFState:
    try:
        state.vector_index_path = index_provider.build(state.doc_id, state.chunks)
    except Exception as error:  # pragma: no cover - boundary node
        state.add_error("vector_index_node", error, retryable=True)
    return state


def graph_index_node(state: BeePDFState, llm_provider: LLMProvider, storage_provider: StorageProvider) -> BeePDFState:
    try:
        graph = build_concept_map(state.chunks)
        state.graph_path = storage_provider.save_json(state.doc_id, "graph.json", graph)
        state.outputs["concept_map"] = graph
        state.outputs["graph_context"] = []
    except Exception as error:  # pragma: no cover - boundary node
        state.add_error("graph_index_node", error, retryable=True)
    return state


def rag_answer_node(state: BeePDFState, question: str, index_provider: IndexProvider, llm_provider: LLMProvider) -> BeePDFState:
    try:
        answer = answer_with_sources(question, state.chunks, index_provider, llm_provider)
        state.outputs["answer"] = answer.to_dict()
    except Exception as error:  # pragma: no cover - boundary node
        state.add_error("rag_answer_node", error, retryable=True)
    return state


def graphrag_answer_node(state: BeePDFState, question: str, index_provider: IndexProvider, llm_provider: LLMProvider) -> BeePDFState:
    try:
        triples = state.outputs.get("graph_context", [])
        answer = answer_with_sources(question, state.chunks, index_provider, llm_provider, graph_context=triples)
        state.outputs["answer"] = answer.to_dict()
    except Exception as error:  # pragma: no cover - boundary node
        state.add_error("graphrag_answer_node", error, retryable=True)
    return state


def script_generation_node(state: BeePDFState, llm_provider: LLMProvider, minutes: int = 3) -> BeePDFState:
    try:
        state.outputs["script"] = llm_provider.generate_script(state.chunks, minutes=minutes)
    except Exception as error:  # pragma: no cover - boundary node
        state.add_error("script_generation_node", error, retryable=True)
    return state


def citation_check_node(state: BeePDFState) -> BeePDFState:
    answer = state.outputs.get("answer", {})
    if not answer.get("vector_sources"):
        state.outputs["citation_check"] = {
            "checked": True,
            "passed": False,
            "coverage": 0.0,
            "matched_terms": [],
            "unsupported_terms": [],
            "source_count": 0,
            "warnings": ["Citation check failed because the answer has no vector sources."],
        }
        return state

    state.outputs["citation_check"] = check_text_grounding(
        answer.get("answer", ""),
        state.chunks,
    ).to_dict()
    return state


def export_node(state: BeePDFState, storage_provider: StorageProvider) -> BeePDFState:
    try:
        state.outputs["chunks_path"] = storage_provider.save_json(
            state.doc_id,
            "chunks.json",
            {"chunks": [asdict(chunk) for chunk in state.chunks]},
        )
        if "answer" in state.outputs:
            state.outputs["answer_path"] = storage_provider.save_json(
                state.doc_id,
                "answer_with_sources.json",
                state.outputs["answer"],
            )
    except Exception as error:  # pragma: no cover - boundary node
        state.add_error("export_node", error, retryable=True)
    return state

