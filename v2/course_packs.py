from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import time
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from threading import Event
from urllib.parse import quote
from uuid import uuid4

from v2.audio_script import generate_audio_script
from v2.background_knowledge import BACKGROUND_SCOPE_VALUES, background_chunks_for_query
from v2.course_pack_artifacts import (
    artifact_name as _artifact_name,
    artifact_preview as _artifact_preview,
    export_concept_map as _export_concept_map,
    save_artifact,
)
from v2.course_pack_store import (
    course_pack_dir,
    list_course_packs,
    load_course_pack,
    load_course_pack_chunks,
)
from v2.course_summary import generate_course_pack_summary
from v2.documents import load_chunks
from v2.graph.concept_map import build_concept_map
from v2.hierarchical_retrieval import build_hierarchical_summary_index, retrieve_hierarchical_summary
from v2.ingest import ingest_local_document
from v2.io_utils import atomic_write_json
from v2.onboarding_report import (
    build_source_snapshot,
    compare_source_snapshots,
    generate_onboarding_report,
    write_onboarding_report_artifacts,
)
from v2.providers.base import LLMProvider
from v2.providers.local import MockLLMProvider
from v2.providers.ollama import OllamaProvider
from v2.providers.semantic import SemanticHybridRetriever
from v2.providers.web_search import WebSearchProviderError, WikipediaSearchProvider, web_results_to_chunks
from v2.rag.answering import _keyword_terms, _sources_from_chunks, generate_source_grounded_answer
from v2.rag.retrieval import chunks_from_contexts, retrieve_contexts
from v2.retrieval_router import classify_course_pack_question
from v2.runtime import current_request_id
from v2.schemas import Chunk
from v2.study_kit import generate_study_kit

__all__ = ["list_course_packs", "load_course_pack"]

OVERVIEW_QUERY_TERMS = {
    "전체",
    "요약",
    "정리",
    "핵심",
    "개요",
    "흐름",
    "course",
    "pack",
    "overview",
    "summary",
    "summarize",
    "outline",
}

CoursePackProgressCallback = Callable[[str, int, int], None]


def create_course_pack(
    paths: list[str],
    output_root: str = "outputs",
    max_chunk_chars: int = 900,
    pack_id: str | None = None,
    append: bool = False,
    progress_callback: CoursePackProgressCallback | None = None,
) -> dict:
    warnings: list[str] = []
    new_documents: list[dict] = []
    new_chunks: list[Chunk] = []

    requested_pack_id = _safe_pack_id(pack_id) if pack_id else None
    existing_documents: list[dict] = []
    existing_chunks: list[Chunk] = []
    if append and requested_pack_id:
        existing_pack = load_course_pack(requested_pack_id, output_root=output_root)
        if existing_pack.get("output_dir"):
            existing_documents = list(existing_pack.get("documents") or [])
            existing_chunks = load_course_pack_chunks(requested_pack_id, output_root=output_root)
            warnings.extend(existing_pack.get("warnings") or [])

    total_documents = len(paths)
    for index, path in enumerate(paths, start=1):
        result = ingest_local_document(path=path, output_root=output_root, max_chunk_chars=max_chunk_chars)
        document = result.to_dict()
        document_chunks = load_chunks(result.doc_id, output_root=output_root)
        document_title = _document_display_title(document_chunks, result.filename)
        document["title"] = document_title
        new_documents.append(document)
        warnings.extend([f"{result.filename}: {warning}" for warning in result.warnings])
        for chunk in document_chunks:
            chunk.metadata.setdefault("doc_id", result.doc_id)
            chunk.metadata.setdefault("filename", result.filename)
            chunk.metadata.setdefault("title", document_title)
            new_chunks.append(chunk)
        _report_course_pack_progress(progress_callback, "ingesting_documents", index, total_documents)

    documents, added_document_count, duplicate_document_count = _merge_course_pack_documents(
        existing_documents,
        new_documents,
    )
    chunks = _merge_course_pack_chunks(existing_chunks, new_chunks)
    safe_pack_id = requested_pack_id or _pack_id_from_documents(documents)
    for chunk in chunks:
        chunk.metadata["pack_id"] = safe_pack_id

    output_dir = course_pack_dir(safe_pack_id, output_root=output_root)
    (output_dir / "answers").mkdir(parents=True, exist_ok=True)

    response = {
        "pack_id": safe_pack_id,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "added_document_count": added_document_count,
        "duplicate_document_count": duplicate_document_count,
        "documents": documents,
        "output_dir": str(output_dir),
        "warnings": list(dict.fromkeys(warnings)),
    }

    _write_json(output_dir / "course_pack.json", response)
    _write_json(output_dir / "chunks.json", {"chunks": [asdict(chunk) for chunk in chunks]})
    _report_course_pack_progress(progress_callback, "building_concept_map", total_documents, total_documents)
    build_concept_map(chunks, output_dir=str(output_dir))
    _report_course_pack_progress(progress_callback, "building_summary_index", total_documents, total_documents)
    _write_json(output_dir / "hierarchical_summary_index.json", build_hierarchical_summary_index(chunks, safe_pack_id))
    _write_json(output_dir / "summary.json", {})
    _write_json(output_dir / "study_kit.json", {})
    _write_json(output_dir / "audio_script.json", {})
    _report_course_pack_progress(progress_callback, "finalizing", total_documents, total_documents)
    return response


def _merge_course_pack_documents(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    documents = list(existing)
    seen = {_document_identity(document) for document in documents}
    added = 0
    duplicates = 0
    for document in incoming:
        identity = _document_identity(document)
        if identity in seen:
            duplicates += 1
            continue
        documents.append(document)
        seen.add(identity)
        added += 1
    return documents, added, duplicates


def _merge_course_pack_chunks(existing: list[Chunk], incoming: list[Chunk]) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen: set[tuple[str, str]] = set()
    for chunk in [*existing, *incoming]:
        document_identity = str(chunk.metadata.get("doc_id") or chunk.metadata.get("filename") or "document")
        identity = (document_identity, chunk.chunk_id)
        if identity in seen:
            continue
        chunks.append(chunk)
        seen.add(identity)
    return chunks


def _document_identity(document: dict) -> str:
    return str(document.get("doc_id") or document.get("filename") or document.get("output_dir") or id(document))


def _document_display_title(chunks: list[Chunk], filename: str) -> str:
    for chunk in chunks:
        for line in chunk.text.splitlines():
            title = re.sub(r"^#{1,6}\s*", "", line).strip()
            if 3 <= len(title) <= 100:
                return title
    return Path(filename).stem


def _report_course_pack_progress(
    callback: CoursePackProgressCallback | None,
    stage: str,
    processed_documents: int,
    total_documents: int,
) -> None:
    if callback is not None:
        callback(stage, processed_documents, total_documents)


def ask_course_pack(
    pack_id: str,
    question: str,
    output_root: str = "outputs",
    top_k: int = 4,
    mode: str = "vector",
    llm_provider: str = "mock",
    llm_model: str | None = None,
    allow_general_fallback: bool = False,
    allow_web_fallback: bool = False,
    web_provider: str = "wikipedia",
    web_top_k: int = 3,
    conversation_history: list[dict] | None = None,
    token_callback: Callable[[str], None] | None = None,
    cancel_event: Event | None = None,
) -> dict:
    trace = _new_trace()
    total_started = time.perf_counter()
    conversation = _normalize_conversation(conversation_history)
    conversation_context_used = _needs_conversation_context(question, conversation)
    retrieval_question = _contextualized_retrieval_question(question, conversation) if conversation_context_used else question
    generation_question = _contextualized_generation_question(question, conversation) if conversation_context_used else question
    answer_provider = _answer_provider(llm_provider, llm_model, token_callback=token_callback, cancel_event=cancel_event)
    course_allow_general = allow_general_fallback and not allow_web_fallback

    if mode in {"auto", "router", "dual", "lightrag", "lightrag_dual"}:
        started = time.perf_counter()
        route = classify_course_pack_question(retrieval_question)
        _trace_stage(trace, "classify_question", started)
        payload = _ask_course_pack_with_router(
            pack_id=pack_id,
            question=generation_question,
            retrieval_question=retrieval_question,
            output_root=output_root,
            top_k=top_k,
            route=route,
            trace=trace,
            answer_provider=answer_provider,
            allow_general_fallback=course_allow_general,
        )
    elif mode == "local_graph":
        payload = _ask_course_pack_with_graph(pack_id=pack_id, question=generation_question, retrieval_question=retrieval_question, output_root=output_root, top_k=top_k, trace=trace, answer_provider=answer_provider, allow_general_fallback=course_allow_general)
    elif mode in {"hierarchical", "hierarchical_summary"}:
        payload = _ask_course_pack_with_hierarchical_summary(pack_id=pack_id, question=generation_question, retrieval_question=retrieval_question, output_root=output_root, top_k=top_k, trace=trace, answer_provider=answer_provider, allow_general_fallback=course_allow_general)
    else:
        payload = _ask_course_pack_with_vector(pack_id=pack_id, question=generation_question, retrieval_question=retrieval_question, output_root=output_root, top_k=top_k, mode=mode, trace=trace, answer_provider=answer_provider, allow_general_fallback=course_allow_general)

    if payload.get("answer_scope") == "none" and allow_web_fallback:
        started = time.perf_counter()
        payload = _answer_with_web_fallback(
            query=generation_question,
            search_query=retrieval_question,
            provider_name=web_provider,
            top_k=web_top_k,
            answer_provider=answer_provider,
            course_payload=payload,
        )
        _trace_stage(trace, "external_web_rag", started)

    if payload.get("answer_scope") == "none" and allow_general_fallback:
        started = time.perf_counter()
        payload = _answer_with_general_fallback(
            query=generation_question,
            answer_provider=answer_provider,
            previous_payload=payload,
        )
        _trace_stage(trace, "general_knowledge_fallback", started)

    payload["llm"] = _answer_llm_metadata(llm_provider, llm_model, answer_provider, payload.get("warnings", []))
    payload["question"] = question
    payload["retrieval_query"] = retrieval_question
    payload["conversation_context_used"] = conversation_context_used
    payload["conversation_turns_used"] = len(conversation) if conversation_context_used else 0
    debug = payload.pop("_retrieval_debug", {})
    _finish_trace(trace, payload, debug, total_started)
    payload["trace"] = trace
    _save_pack_artifact(pack_id, output_root, f"answers/{_artifact_name(question)}.json", payload)
    return payload




def _answer_provider(
    llm_provider: str,
    llm_model: str | None,
    token_callback: Callable[[str], None] | None = None,
    cancel_event: Event | None = None,
) -> LLMProvider:
    provider = (llm_provider or "mock").lower()
    if provider in {"ollama", "qwen", "qwen3"}:
        return OllamaProvider(
            model=llm_model or "qwen3:14b",
            timeout=180,
            stream_callback=token_callback,
            cancel_event=cancel_event,
        )
    return MockLLMProvider()


_FOLLOW_UP_PREFIX = re.compile(
    r"^\s*(그럼|그러면|그렇다면|그건|이건|그것|이것|저것|앞에서|위에서|방금|왜|장점|단점|예시|차이|비교|더|구체적으로|쉽게|어떻게)",
    re.IGNORECASE,
)


def _normalize_conversation(conversation_history: list[dict] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in (conversation_history or [])[-12:]:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        elif hasattr(item, "dict"):
            item = item.dict()
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = " ".join(str(item.get("content") or "").split()).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content[:1500]})
    return normalized


def _needs_conversation_context(question: str, conversation: list[dict[str, str]]) -> bool:
    if not any(item["role"] == "user" for item in conversation):
        return False
    compact = " ".join(question.split())
    if _FOLLOW_UP_PREFIX.search(compact):
        return True
    return any(marker in compact for marker in ("이 방식", "그 방식", "이 내용", "그 내용", "두 개", "둘의", "방금 답"))


def _contextualized_retrieval_question(question: str, conversation: list[dict[str, str]]) -> str:
    previous_user = next((item["content"] for item in reversed(conversation) if item["role"] == "user"), "")
    return f"이전 질문: {previous_user}\n현재 후속 질문: {question}" if previous_user else question


def _contextualized_generation_question(question: str, conversation: list[dict[str, str]]) -> str:
    lines = [f"{'사용자' if item['role'] == 'user' else 'CourseBee'}: {item['content']}" for item in conversation[-6:]]
    return "최근 대화:\n" + "\n".join(lines) + f"\n\n현재 질문: {question}\n현재 질문에 직접 답하세요."


_FALLBACK_METADATA_KEYS = (
    "mode",
    "routed_mode",
    "question_type",
    "retrieval_plan",
    "selected_retrievers",
)


def _answer_with_web_fallback(
    query: str,
    search_query: str,
    provider_name: str,
    top_k: int,
    answer_provider: LLMProvider,
    course_payload: dict,
) -> dict:
    web_metadata = {
        "provider": provider_name,
        "query": search_query,
        "status": "searching",
        "result_count": 0,
        "results": [],
    }
    if provider_name != "wikipedia":
        return _failed_web_payload(
            course_payload,
            web_metadata,
            f"Unsupported web search provider: {provider_name}",
        )

    try:
        results = WikipediaSearchProvider().search(search_query, top_k=top_k)
    except WebSearchProviderError as exc:
        return _failed_web_payload(course_payload, web_metadata, f"External web search failed: {exc}")

    web_metadata.update(
        {
            "status": "used" if results else "no_results",
            "result_count": len(results),
            "results": [
                {"title": result.title, "url": result.url, "language": result.language, "rank": result.rank}
                for result in results
            ],
        }
    )
    if not results:
        return _failed_web_payload(course_payload, web_metadata, "External web search returned no usable results.")

    chunks = web_results_to_chunks(results)
    result = generate_source_grounded_answer(
        query=query,
        chunks=chunks,
        index_provider=_PreselectedIndexProvider(),
        llm_provider=answer_provider,
        top_k=top_k,
        allow_general_fallback=False,
    )
    payload = result.to_dict()
    payload["answer_scope"] = "external_web" if payload.get("answer") else "none"
    payload["grounding_status"] = "web_grounded" if payload.get("answer") else "not_answered"
    payload["general_knowledge_used"] = False
    payload["web_search_used"] = True
    payload["web_search"] = web_metadata
    payload["sentence_citations"] = _sentence_citations(payload.get("answer", ""), chunks)
    payload["retrieval_mode"] = "external_web"
    payload["retrieval_details"] = {
        "implementation": "wikipedia_search_rag",
        "provider": provider_name,
        "candidate_chunks": len(chunks),
        "selected_chunks": len(chunks),
        "fallback_used": True,
    }
    payload["warnings"] = _dedupe_strings(
        [
            *(warning for warning in course_payload.get("warnings", []) if "No relevant context" not in warning),
            *payload.get("warnings", []),
            "No Course Pack evidence was found; the answer uses cited external web sources.",
        ]
    )
    payload["_retrieval_debug"] = {
        "candidate_chunks": len(chunks),
        "selected_chunks": len(chunks),
        "fallback_used": True,
        "retrieval_implementation": "wikipedia_search_rag",
    }
    _copy_fallback_metadata(payload, course_payload)
    return payload


def _failed_web_payload(course_payload: dict, web_metadata: dict, warning: str) -> dict:
    payload = {**course_payload}
    payload["web_search_used"] = True
    payload["web_search"] = {**web_metadata, "status": web_metadata.get("status", "failed")}
    if payload["web_search"]["status"] == "searching":
        payload["web_search"]["status"] = "failed"
    payload["warnings"] = _dedupe_strings([*payload.get("warnings", []), warning])
    return payload


def _answer_with_general_fallback(query: str, answer_provider: LLMProvider, previous_payload: dict) -> dict:
    result = generate_source_grounded_answer(
        query=query,
        chunks=[],
        index_provider=_PreselectedIndexProvider(),
        llm_provider=answer_provider,
        top_k=1,
        allow_general_fallback=True,
    )
    payload = result.to_dict()
    payload["web_search_used"] = bool(previous_payload.get("web_search_used"))
    payload["web_search"] = previous_payload.get("web_search", {})
    payload["retrieval_mode"] = "general_knowledge_fallback"
    payload["retrieval_details"] = {
        "implementation": "llm_general_knowledge",
        "fallback_used": True,
        "selected_chunks": 0,
    }
    payload["warnings"] = _dedupe_strings([*previous_payload.get("warnings", []), *payload.get("warnings", [])])
    payload["_retrieval_debug"] = {
        "candidate_chunks": 0,
        "selected_chunks": 0,
        "fallback_used": True,
        "retrieval_implementation": "llm_general_knowledge",
    }
    _copy_fallback_metadata(payload, previous_payload)
    return payload


def _copy_fallback_metadata(target: dict, source: dict) -> None:
    for key in _FALLBACK_METADATA_KEYS:
        if key in source:
            target[key] = source[key]


def _dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _answer_llm_metadata(
    requested_provider: str,
    requested_model: str | None,
    provider: LLMProvider,
    warnings: list[str],
) -> dict:
    requested = (requested_provider or "mock").lower()
    failed = any("LLM answer generation failed" in warning for warning in warnings)
    model = getattr(provider, "model", requested_model)
    if isinstance(provider, MockLLMProvider):
        status = "mock" if requested in {"mock", "rule", "local"} else "fallback"
    else:
        status = "fallback" if failed else "used"
    return {"provider": requested, "model": model, "status": status}


def _sentence_citations(answer: str, chunks: list[Chunk]) -> list[dict]:
    sentences = _split_answer_for_citations(answer)
    sources = _sources_from_chunks(chunks)
    source_index_by_key = {_source_key_from_source(source): index for index, source in enumerate(sources, start=1)}
    citations: list[dict] = []
    for sentence in sentences:
        item = {"sentence": sentence, "grounded": False}
        source_index, matched_terms = _best_sentence_source(sentence, chunks, source_index_by_key)
        if source_index is not None:
            item.update({"grounded": True, "source_index": source_index, "matched_terms": matched_terms})
        citations.append(item)
    return citations


def _split_answer_for_citations(answer: str) -> list[str]:
    lines = [line.strip() for line in str(answer or "").splitlines() if line.strip()]
    sentences: list[str] = []
    sentence_pattern = re.compile(r"(?<=[.!?])\s+|(?<=\ub2e4\.)\s*")
    for line in lines:
        if re.match(r"^\s*[-*]\s+", line):
            sentences.append(line)
            continue
        parts = sentence_pattern.split(line)
        sentences.extend(part.strip() for part in parts if part.strip())
    return sentences


def _best_sentence_source(sentence: str, chunks: list[Chunk], source_index_by_key: dict[tuple, int]) -> tuple[int | None, list[str]]:
    terms = _citation_terms(sentence)
    if not terms:
        return None, []
    best_chunk: Chunk | None = None
    best_hits: list[str] = []
    best_score = 0
    for chunk in chunks:
        chunk_text = chunk.text.lower()
        chunk_terms = set(_citation_terms(chunk.text))
        hits = [term for term in terms if term in chunk_terms or term in chunk_text]
        technical_hits = [term for term in hits if re.search(r"[A-Za-z0-9]", term) or len(term) >= 4]
        score = len(hits) + len(technical_hits)
        if score > best_score:
            best_chunk = chunk
            best_hits = hits
            best_score = score
    if best_chunk is None:
        return None, []
    technical_hit = any(re.search(r"[A-Za-z0-9]", term) for term in best_hits)
    threshold = 1 if technical_hit else 2
    if len(best_hits) < threshold:
        return None, []
    source_index = source_index_by_key.get(_source_key_from_chunk(best_chunk))
    if source_index is None:
        return None, []
    return source_index, best_hits[:8]


def _citation_terms(text: str) -> list[str]:
    stopwords = {
        "the", "and", "for", "with", "this", "that", "from", "into", "only", "about",
        "are", "was", "were", "been", "being", "have", "has", "had", "does", "did",
        "you", "your", "what", "why", "how", "when", "where", "which", "will", "would",
        "\uc790\ub8cc", "\ub0b4\uc6a9", "\uc124\uba85", "\uc815\ub9ac", "\ubb38\uc7a5", "\ubd80\ubd84",
        "\uadf8\ub9ac\uace0", "\ud558\uc9c0\ub9cc", "\uadf8\ub798\uc11c", "\ub300\ud55c", "\ud1b5\ud574",
        "\uc788\uc2b5\ub2c8\ub2e4", "\ud569\ub2c8\ub2e4", "\ub429\ub2c8\ub2e4", "\uac83\uc785\ub2c8\ub2e4",
    }
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_]+|[\uac00-\ud7a3]+", str(text).lower()):
        if len(token) < 2 or token in stopwords or token in terms:
            continue
        terms.append(token)
    return terms

def _source_key_from_chunk(chunk: Chunk) -> tuple:
    metadata = chunk.metadata or {}
    return (metadata.get("doc_id"), metadata.get("filename"), chunk.page, chunk.chunk_id)


def _source_key_from_source(source) -> tuple:
    return (source.doc_id, source.filename, source.page, source.chunk_id)

def _new_trace() -> dict:
    return {
        "request_id": current_request_id() or f"req_{uuid4().hex[:8]}",
        "stages": [],
        "retrieval_debug": {},
    }


def _trace_stage(trace: dict | None, name: str, started: float) -> None:
    if trace is None:
        return
    trace.setdefault("stages", []).append(
        {
            "name": name,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    )


def _finish_trace(trace: dict, payload: dict, debug: dict, started: float) -> None:
    fallback_used = bool(debug.get("fallback_used")) or "fallback" in str(payload.get("retrieval_mode", ""))
    trace["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    trace["answer_scope"] = payload.get("answer_scope", "course_pack")
    trace["grounding_status"] = payload.get("grounding_status", "grounded")
    trace["general_knowledge_used"] = bool(payload.get("general_knowledge_used"))
    trace["web_search_used"] = bool(payload.get("web_search_used"))
    trace["retrieval_debug"] = {
        "candidate_chunks": debug.get("candidate_chunks", 0),
        "selected_chunks": debug.get("selected_chunks", len(payload.get("sources", []))),
        "candidate_graph_edges": debug.get("candidate_graph_edges", 0),
        "selected_graph_edges": debug.get("selected_graph_edges", len(payload.get("graph_context", []))),
        "fallback_used": fallback_used,
        "retrieval_mode": payload.get("retrieval_mode"),
        "routed_mode": payload.get("routed_mode") or payload.get("mode"),
        "retrieval_implementation": debug.get("retrieval_implementation", "local_hybrid"),
        "embedding_model": debug.get("embedding_model"),
        "reranker_model": debug.get("reranker_model"),
        "lexical_candidates": debug.get("lexical_candidates", 0),
        "dense_candidates": debug.get("dense_candidates", 0),
        "reranked": debug.get("reranked", False),
    }


def summary_for_course_pack(
    pack_id: str,
    query: str = "",
    output_root: str = "outputs",
    top_k: int = 8,
    max_items: int = 5,
    llm_provider: str = "mock",
    llm_model: str | None = None,
) -> dict:
    all_chunks = load_course_pack_chunks(pack_id, output_root=output_root)
    target_query = query or "course pack overview summary"
    min_top_k = max(top_k, max_items, len(_group_chunks_by_document(all_chunks)))
    selected_chunks = _balanced_chunks(query=target_query, chunks=all_chunks, top_k=min_top_k)
    summary_chunks = _dedupe_chunks([*selected_chunks, *all_chunks])
    payload = generate_course_pack_summary(
        summary_chunks,
        llm_provider=llm_provider,
        llm_model=llm_model,
        max_items=max_items,
    )
    payload["pack_id"] = pack_id
    _save_pack_artifact(pack_id, output_root, "summary.json", payload)
    return payload


def onboarding_report_for_course_pack(
    pack_id: str,
    query: str = "",
    output_root: str = "outputs",
    top_k: int = 8,
    title: str | None = None,
    audience: str = "신입 구성원",
    objective: str = "핵심 규정과 업무 흐름을 출처와 함께 이해",
    max_sections: int = 6,
    llm_provider: str = "mock",
    llm_model: str | None = None,
) -> dict:
    all_chunks = _latest_document_version_chunks(load_course_pack_chunks(pack_id, output_root=output_root))
    output_dir = course_pack_dir(pack_id, output_root=output_root)
    previous_report = _load_onboarding_report(output_dir)
    current_snapshot = build_source_snapshot(all_chunks)
    impact_at_generation = compare_source_snapshots(
        (previous_report or {}).get("source_snapshot"),
        current_snapshot,
        (previous_report or {}).get("sections", []),
    )
    target_query = query or objective or "온보딩 핵심 규정 업무 흐름"
    report_chunks = _select_onboarding_report_chunks(
        query=target_query,
        chunks=all_chunks,
        top_k=max(top_k, max_sections),
    )
    payload = generate_onboarding_report(
        report_chunks,
        title=title or f"{audience} 온보딩 보고서",
        audience=audience,
        objective=objective,
        max_sections=max_sections,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    reused_sections = _reuse_unchanged_report_sections(
        previous_report,
        payload,
        impact_at_generation,
    )
    payload["pack_id"] = pack_id
    selected_documents = _group_chunks_by_document(report_chunks)
    payload["selection"] = {
        "mode": "all_documents" if len(selected_documents) == len(_group_chunks_by_document(all_chunks)) else "objective_relevant",
        "query": target_query,
        "selected_document_count": len(selected_documents),
        "pack_document_count": len(_group_chunks_by_document(all_chunks)),
        "selected_filenames": [
            str((group[0].metadata or {}).get("filename") or (group[0].metadata or {}).get("doc_id") or "document")
            for group in selected_documents.values()
            if group
        ],
    }
    payload["source_snapshot"] = current_snapshot
    payload["impact_at_generation"] = impact_at_generation
    payload["generation"] = {
        "mode": "incremental" if previous_report and impact_at_generation["requires_regeneration"] else "full",
        "previous_report_found": bool(previous_report),
        "reused_section_count": reused_sections,
        "regenerated_section_count": max(0, len(payload.get("sections", [])) - reused_sections),
    }
    payload["artifacts"] = {
        "json_path": str(output_dir / "onboarding_report.json"),
        "markdown_path": str(output_dir / "onboarding_report.md"),
        "html_path": str(output_dir / "onboarding_report.html"),
    }
    payload["report_url"] = _course_pack_file_url(
        pack_id,
        "onboarding_report.html",
        output_root,
        api_version="v3",
    )
    write_onboarding_report_artifacts(payload, output_dir)
    return payload


def onboarding_report_impact_for_course_pack(
    pack_id: str,
    output_root: str = "outputs",
) -> dict:
    output_dir = course_pack_dir(pack_id, output_root=output_root)
    report = _load_onboarding_report(output_dir)
    current_chunks = _latest_document_version_chunks(load_course_pack_chunks(pack_id, output_root=output_root))
    current_snapshot = build_source_snapshot(current_chunks)
    impact = compare_source_snapshots(
        (report or {}).get("source_snapshot"),
        current_snapshot,
        (report or {}).get("sections", []),
    )
    return {
        "pack_id": pack_id,
        "report_exists": bool(report),
        "report_generated_at": (report or {}).get("generated_at"),
        "report_title": (report or {}).get("title"),
        "current_source_snapshot": current_snapshot,
        **impact,
    }


def study_kit_for_course_pack(
    pack_id: str,
    query: str = "",
    output_root: str = "outputs",
    top_k: int = 4,
    max_items: int = 4,
) -> dict:
    all_chunks = load_course_pack_chunks(pack_id, output_root=output_root)
    chunks = _select_pack_chunks(pack_id, query=query, output_root=output_root, top_k=top_k)
    study_chunks = _dedupe_chunks([*chunks, *all_chunks])
    base = generate_study_kit(chunks, max_items=max_items)
    summary_payload = generate_course_pack_summary(study_chunks, max_items=max(max_items, 5))
    payload = {
        "overview": summary_payload.get("overview", {}),
        "lecture_summaries": summary_payload.get("lecture_summaries", []),
        "connections": summary_payload.get("connections", []),
        "key_concepts": summary_payload.get("key_concepts", []),
        "expected_questions": base.get("expected_questions", []),
        "flashcards": _flashcards_from_study_payload(base, summary_payload, limit=max_items),
        "summary": base.get("summary", {"text": "", "sources": []}),
        "key_points": base.get("key_points", []),
        "glossary": base.get("glossary", []),
        "quiz": base.get("quiz", []),
        "sources": summary_payload.get("sources", []),
        "warnings": [*base.get("warnings", []), *summary_payload.get("warnings", [])],
    }
    _save_pack_artifact(pack_id, output_root, "study_kit.json", payload)
    return payload


def audio_script_for_course_pack(
    pack_id: str,
    query: str = "",
    output_root: str = "outputs",
    top_k: int = 4,
    mode: str = "briefing_3min",
    llm_provider: str = "mock",
    llm_model: str | None = None,
    grounding: str = "creative",
    target_minutes: int | None = None,
    target_chars: int | None = None,
    knowledge_scope: str = "course_pack",
) -> dict:
    chunks = _select_pack_chunks(pack_id, query=query, output_root=output_root, top_k=top_k)
    background_chunks: list[Chunk] = []
    if knowledge_scope in BACKGROUND_SCOPE_VALUES:
        background_chunks = background_chunks_for_query(query=query, source_chunks=chunks)
        chunks = _dedupe_chunks([*chunks, *background_chunks])
    payload = generate_audio_script(chunks, mode=mode, llm_provider=llm_provider, llm_model=llm_model, grounding=grounding, target_minutes=target_minutes, target_chars=target_chars)
    payload["knowledge_scope"] = knowledge_scope
    payload["background_sources"] = [chunk.metadata for chunk in background_chunks]
    _save_pack_artifact(pack_id, output_root, "audio_script.json", payload)
    return payload


def _course_pack_file_url(
    pack_id: str,
    filename: str,
    output_root: str,
    api_version: str = "v2",
) -> str:
    return (
        f"/{api_version}/course-packs/{quote(pack_id, safe='')}/files/{quote(filename, safe='')}"
        f"?output_root={quote(output_root, safe='')}"
    )


def _audio_file_url(pack_id: str, filename: str, output_root: str) -> str:
    return _course_pack_file_url(pack_id, filename, output_root)


def _audio_script_text(script: list[dict]) -> str:
    lines: list[str] = []
    for segment in script:
        text = str(segment.get("text") or segment.get("content") or "").strip()
        if text:
            lines.append(text)
    return "\n\n".join(lines)


async def _save_edge_tts_script(
    edge_tts_module,
    script: list[dict],
    target: Path,
    host_voice: str,
    guest_voice: str,
) -> None:
    audio_chunks = 0
    with target.open("wb") as handle:
        for segment in script:
            text = str(segment.get("text") or segment.get("content") or "").strip()
            if not text:
                continue
            speaker = str(segment.get("speaker") or "narrator").lower()
            voice = guest_voice if speaker == "guest" else host_voice
            communicate = edge_tts_module.Communicate(text, voice)
            async for chunk in communicate.stream():
                if chunk.get("type") != "audio" or not chunk.get("data"):
                    continue
                handle.write(chunk["data"])
                audio_chunks += 1
    if audio_chunks == 0:
        raise RuntimeError("Edge TTS returned no audio frames")


def _existing_audio_artifact(output_dir: Path) -> Path | None:
    preferred = output_dir / "audio_overview_edge_tts.mp3"
    if preferred.exists():
        return preferred
    candidates = sorted(output_dir.glob("*edge_tts*.mp3"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def tts_for_course_pack(
    pack_id: str,
    query: str = "",
    output_root: str = "outputs",
    top_k: int = 4,
    mode: str = "podcast",
    llm_provider: str = "mock",
    llm_model: str | None = None,
    grounding: str = "creative",
    target_minutes: int | None = None,
    target_chars: int | None = None,
    knowledge_scope: str = "course_pack",
    voice: str = "ko-KR-SunHiNeural",
    guest_voice: str = "ko-KR-InJoonNeural",
    reuse_existing: bool = False,
) -> dict:
    payload = audio_script_for_course_pack(
        pack_id=pack_id,
        query=query,
        output_root=output_root,
        top_k=top_k,
        mode=mode,
        llm_provider=llm_provider,
        llm_model=llm_model,
        grounding=grounding,
        target_minutes=target_minutes,
        target_chars=target_chars,
        knowledge_scope=knowledge_scope,
    )
    output_dir = course_pack_dir(pack_id, output_root=output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "audio_overview_edge_tts.mp3"
    warnings = list(payload.get("warnings", []))

    audio_path: Path | None = target if reuse_existing and target.exists() else None
    tts_status = "existing_mp3" if audio_path else "pending"
    script_text = _audio_script_text(payload.get("script", []))

    if audio_path is None and script_text:
        temporary = output_dir / f".{target.stem}.{uuid4().hex}.tmp.mp3"
        try:
            import edge_tts

            async def _save_audio() -> None:
                await _save_edge_tts_script(
                    edge_tts,
                    payload.get("script", []),
                    temporary,
                    host_voice=voice,
                    guest_voice=guest_voice,
                )

            asyncio.run(_save_audio())
            if not temporary.exists() or temporary.stat().st_size == 0:
                raise RuntimeError("Edge TTS returned an empty audio file")
            temporary.replace(target)
            audio_path = target
            tts_status = "edge_tts"
        except Exception as exc:  # pragma: no cover - network/provider dependent.
            fallback = _existing_audio_artifact(output_dir) if reuse_existing else None
            if fallback:
                audio_path = fallback
                tts_status = "existing_mp3"
                warnings.append(f"Edge TTS failed; reused existing mp3 artifact: {exc}")
            else:
                tts_status = "failed"
                warnings.append(f"Edge TTS failed; the newly generated script was not replaced with stale audio: {exc}")
        finally:
            temporary.unlink(missing_ok=True)
    elif audio_path is None:
        fallback = _existing_audio_artifact(output_dir) if reuse_existing else None
        if fallback:
            audio_path = fallback
            tts_status = "existing_mp3"
            warnings.append("No script text was produced; reused an existing mp3 artifact.")
        else:
            tts_status = "failed"
            warnings.append("No script text was produced for TTS.")

    payload["tts_status"] = tts_status
    payload["audio_path"] = str(audio_path) if audio_path else None
    payload["artifact_name"] = audio_path.name if audio_path else None
    payload["audio_url"] = _audio_file_url(pack_id, audio_path.name, output_root) if audio_path else None
    payload["voices"] = {"host": voice, "narrator": voice, "guest": guest_voice}
    payload["duration_seconds"] = None
    payload["warnings"] = warnings
    if audio_path:
        _save_pack_artifact(pack_id, output_root, "audio_overview.json", payload)
    return payload


def concept_map_for_course_pack(
    pack_id: str,
    output_root: str = "outputs",
) -> dict:
    chunks = load_course_pack_chunks(pack_id, output_root=output_root)
    return _load_or_build_course_pack_graph(pack_id, output_root, chunks)


def mindmap_view_for_course_pack(
    pack_id: str,
    output_root: str = "outputs",
) -> dict:
    graph = concept_map_for_course_pack(pack_id=pack_id, output_root=output_root)
    view = _mindmap_view_from_graph(pack_id=pack_id, graph=graph)
    _save_pack_artifact(pack_id, output_root, "mindmap_view.json", view)
    return view


def _mindmap_view_from_graph(pack_id: str, graph: dict) -> dict:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_by_id = {str(node.get("id") or node.get("label")): node for node in nodes}
    concept_nodes = [(node_id, node) for node_id, node in node_by_id.items() if node.get("type") == "concept"]
    concept_ids = {node_id for node_id, _ in concept_nodes}
    concept_edges = [
        edge
        for edge in edges
        if str(edge.get("source")) in concept_ids and str(edge.get("target")) in concept_ids
    ]
    degree = Counter()
    for edge in concept_edges:
        degree[str(edge.get("source"))] += 1
        degree[str(edge.get("target"))] += 1

    concepts_by_document: OrderedDict[str, list[str]] = OrderedDict()
    ungrouped: list[str] = []
    for concept_id, node in concept_nodes:
        documents = node.get("documents") or []
        filenames = [str(item.get("filename") or item.get("doc_id")) for item in documents if isinstance(item, dict)]
        if not filenames:
            ungrouped.append(concept_id)
        for filename in filenames:
            concepts_by_document.setdefault(filename, []).append(concept_id)
    if ungrouped:
        concepts_by_document["Key concepts"] = ungrouped

    branches = []
    for index, (document, document_concepts) in enumerate(concepts_by_document.items()):
        ranked = sorted(set(document_concepts), key=lambda item: (-degree[item], item.lower()))[:8]
        if not ranked:
            continue
        children = [
            {
                "id": concept_id,
                "label": str(node_by_id[concept_id].get("label") or concept_id),
                "present": True,
                "evidence": _first_mindmap_evidence(concept_id, edges),
            }
            for concept_id in ranked
        ]
        label = Path(document).stem if document != "Key concepts" else document
        branches.append(
            {
                "id": f"branch_{index + 1}",
                "label": label,
                "summary": f"{len(document_concepts)} concepts grounded in {document}.",
                "children": children,
            }
        )

    relation_edges = sorted(
        concept_edges,
        key=lambda edge: (
            str(edge.get("relation")) == "related_in_context",
            -(degree[str(edge.get("source"))] + degree[str(edge.get("target"))]),
        ),
    )
    relations = []
    seen_relations: set[tuple[str, str, str]] = set()
    for edge in relation_edges:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        relation = str(edge.get("relation") or "related_in_context")
        key = (source, target, relation)
        if source == target or key in seen_relations:
            continue
        seen_relations.add(key)
        relations.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "present": True,
                "evidence": (edge.get("evidence") or [None])[0],
            }
        )
        if len(relations) >= 16:
            break

    top_concepts = sorted(concept_ids, key=lambda item: (-degree[item], item.lower()))[:5]
    summary = "Key concepts: " + ", ".join(top_concepts) if top_concepts else "No concepts were extracted."

    view = {
        "pack_id": pack_id,
        "title": "Course Pack Mindmap",
        "root": {"id": pack_id, "label": "Course Pack", "summary": summary},
        "branches": branches,
        "relations": relations,
        "source_graph": {"node_count": len(nodes), "edge_count": len(edges)},
        "warnings": graph.get("warnings", []),
    }
    return view


def _first_mindmap_evidence(concept: str, edges: list[dict]) -> dict | None:
    for edge in edges:
        if str(edge.get("source")) == concept or str(edge.get("target")) == concept:
            evidence = edge.get("evidence") or []
            if evidence:
                return evidence[0]
    return None


def artifacts_for_course_pack(
    pack_id: str,
    output_root: str = "outputs",
    include_content: bool = True,
) -> dict:
    output_dir = course_pack_dir(pack_id, output_root=output_root)
    warnings: list[str] = []
    artifact_names = {
        "course_pack": "course_pack.json",
        "summary": "summary.json",
        "onboarding_report": "onboarding_report.json",
        "onboarding_report_markdown": "onboarding_report.md",
        "onboarding_report_html": "onboarding_report.html",
        "study_kit": "study_kit.json",
        "audio_script": "audio_script.json",
        "audio_overview": "audio_overview.json",
        "graph": "graph.json",
        "chunks": "chunks.json",
        "concept_map_mermaid": "concept_map.mmd",
        "concept_map_html": "concept_map.html",
        "mindmap_view": "mindmap_view.json",
        "hierarchical_summary_index": "hierarchical_summary_index.json",
    }
    artifacts = {
        name: _artifact_preview(output_dir / filename, include_content=include_content)
        for name, filename in artifact_names.items()
    }
    answers_dir = output_dir / "answers"
    answers = []
    if answers_dir.exists():
        answers = [_artifact_preview(path, include_content=include_content) for path in sorted(answers_dir.glob("*.json"))]

    missing = [name for name, artifact in artifacts.items() if not artifact["exists"]]
    if missing:
        warnings.append("Missing artifacts: " + ", ".join(missing))

    return {
        "pack_id": pack_id,
        "output_dir": str(output_dir),
        "artifacts": artifacts,
        "answers": answers,
        "warnings": warnings,
    }


def export_concept_map_for_course_pack(
    pack_id: str,
    output_root: str = "outputs",
    max_nodes: int = 60,
    max_edges: int = 120,
) -> dict:
    output_dir = course_pack_dir(pack_id, output_root=output_root)
    graph = concept_map_for_course_pack(pack_id=pack_id, output_root=output_root)
    export = _export_concept_map(graph, output_dir=output_dir, max_nodes=max_nodes, max_edges=max_edges)
    return {
        "pack_id": pack_id,
        "output_dir": str(output_dir),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        **export,
        "warnings": [*graph.get("warnings", []), *export.get("warnings", [])],
    }


def select_balanced_course_pack_chunks(pack_id: str, query: str, output_root: str = "outputs", top_k: int = 4) -> list[Chunk]:
    chunks = load_course_pack_chunks(pack_id, output_root=output_root)
    return _balanced_chunks(query=query, chunks=chunks, top_k=top_k)



def _ask_course_pack_with_vector(
    pack_id: str,
    question: str,
    output_root: str,
    top_k: int,
    retrieval_question: str | None = None,
    mode: str = "vector",
    trace: dict | None = None,
    answer_provider: LLMProvider | None = None,
    allow_general_fallback: bool = False,
) -> dict:
    all_chunks = load_course_pack_chunks(pack_id, output_root=output_root)
    search_question = retrieval_question or question
    started = time.perf_counter()
    if mode in {"semantic", "semantic_hybrid", "semantic_rerank"}:
        semantic_run = SemanticHybridRetriever(
            include_lexical=mode != "semantic",
            use_reranker=mode == "semantic_rerank",
        ).search_with_details(search_question, all_chunks, top_k=top_k)
        chunks = semantic_run.chunks
        retrieval_mode = semantic_run.retrieval_mode
        retrieval_details = semantic_run.details()
        retrieval_warnings = semantic_run.warnings
        retrieval_debug = {
            **retrieval_details,
            "retrieval_implementation": semantic_run.implementation,
        }
        _trace_stage(trace, "select_semantic_chunks", started)
    else:
        chunks = _balanced_chunks(query=search_question, chunks=all_chunks, top_k=top_k)
        retrieval_mode = "vector"
        retrieval_details = {
            "implementation": "local_hybrid",
            "candidate_chunks": len(all_chunks),
            "selected_chunks": len(chunks),
            "fallback_used": False,
        }
        retrieval_warnings = []
        retrieval_debug = {
            "candidate_chunks": len(all_chunks),
            "selected_chunks": len(chunks),
            "fallback_used": False,
            "retrieval_implementation": "local_hybrid",
        }
        _trace_stage(trace, "select_vector_chunks", started)

    started = time.perf_counter()
    result = generate_source_grounded_answer(
        query=question,
        chunks=chunks,
        index_provider=_PreselectedIndexProvider(),
        llm_provider=answer_provider or MockLLMProvider(),
        top_k=top_k,
        allow_general_fallback=allow_general_fallback,
    )
    _trace_stage(trace, "compose_answer", started)

    payload = result.to_dict()
    payload["sentence_citations"] = _sentence_citations(payload.get("answer", ""), chunks)
    payload["mode"] = mode
    payload["retrieval_mode"] = retrieval_mode
    payload["retrieval_details"] = retrieval_details
    payload["warnings"] = [*payload.get("warnings", []), *retrieval_warnings]
    payload["_retrieval_debug"] = retrieval_debug
    return payload


def _ask_course_pack_with_router(
    pack_id: str,
    question: str,
    output_root: str,
    top_k: int,
    retrieval_question: str | None = None,
    route: dict | None = None,
    trace: dict | None = None,
    answer_provider: LLMProvider | None = None,
    allow_general_fallback: bool = False,
) -> dict:
    search_question = retrieval_question or question
    if route is None:
        started = time.perf_counter()
        route = classify_course_pack_question(search_question)
        _trace_stage(trace, "classify_question", started)

    started = time.perf_counter()
    selected_mode = route["selected_mode"]
    _trace_stage(trace, "route_decision", started)

    if selected_mode == "local_graph":
        payload = _ask_course_pack_with_graph(pack_id=pack_id, question=question, retrieval_question=search_question, output_root=output_root, top_k=top_k, trace=trace, answer_provider=answer_provider, allow_general_fallback=allow_general_fallback)
    elif selected_mode == "hierarchical":
        payload = _ask_course_pack_with_hierarchical_summary(pack_id=pack_id, question=question, retrieval_question=search_question, output_root=output_root, top_k=top_k, trace=trace, answer_provider=answer_provider, allow_general_fallback=allow_general_fallback)
    else:
        payload = _ask_course_pack_with_vector(pack_id=pack_id, question=question, retrieval_question=search_question, output_root=output_root, top_k=top_k, trace=trace, answer_provider=answer_provider, allow_general_fallback=allow_general_fallback)

    payload["mode"] = "auto"
    payload["routed_mode"] = selected_mode
    payload["question_type"] = route["question_type"]
    payload["retrieval_plan"] = route["retrieval_plan"]
    payload["selected_retrievers"] = route["selected_retrievers"]
    if route["question_type"] == "mixed_question":
        payload["warnings"] = [
            *payload.get("warnings", []),
            "Mixed question routed to hierarchical summary first; course_graph is included in the retrieval plan for relationship follow-up.",
        ]
    return payload

def _ask_course_pack_with_hierarchical_summary(
    pack_id: str,
    question: str,
    output_root: str,
    top_k: int,
    retrieval_question: str | None = None,
    trace: dict | None = None,
    answer_provider: LLMProvider | None = None,
    allow_general_fallback: bool = False,
) -> dict:
    all_chunks = load_course_pack_chunks(pack_id, output_root=output_root)
    search_question = retrieval_question or question
    started = time.perf_counter()
    retrieval = retrieve_hierarchical_summary(query=search_question, chunks=all_chunks, pack_id=pack_id, top_k=top_k)
    _trace_stage(trace, "retrieve_hierarchical_summary", started)
    chunks = retrieval.pop("chunks")

    started = time.perf_counter()
    result = generate_source_grounded_answer(
        query=question,
        chunks=chunks,
        index_provider=_PreselectedIndexProvider(),
        llm_provider=answer_provider or MockLLMProvider(),
        top_k=top_k,
        allow_general_fallback=allow_general_fallback,
    )
    _trace_stage(trace, "compose_answer", started)

    payload = result.to_dict()
    payload["sentence_citations"] = _sentence_citations(payload.get("answer", ""), chunks)
    payload["mode"] = "hierarchical"
    payload["retrieval_mode"] = "hierarchical_summary"
    payload["abstraction_level"] = retrieval["abstraction_level"]
    payload["selected_summary_nodes"] = retrieval["selected_summary_nodes"]
    payload["supporting_chunks"] = retrieval["supporting_chunks"]
    payload["hierarchical_summary_index"] = {
        "root_id": retrieval["hierarchical_summary_index"].get("root_id"),
        "node_count": len(retrieval["hierarchical_summary_index"].get("nodes", [])),
    }
    payload["_retrieval_debug"] = {
        "candidate_chunks": len(all_chunks),
        "selected_chunks": len(chunks),
        "fallback_used": False,
    }
    return payload

COURSE_GRAPH_PATH_RELATIONS = {
    "prerequisite_of",
    "explains",
    "contrasts",
    "used_in",
    "is_a",
    "reduces",
    "handles",
    "improves",
    "captures",
    "supports",
    "uses",
    "extends",
    "grounds",
    "augments",
    "builds",
    "related_to",
}
PREREQUISITE_RELATIONS = {"prerequisite_of"}
CONTRAST_RELATIONS = {"contrasts"}
STRUCTURAL_RELATIONS = {"contains", "mentions", "evidence_in", "appears_in", "introduces"}


def _ask_course_pack_with_graph(
    pack_id: str,
    question: str,
    output_root: str,
    top_k: int,
    retrieval_question: str | None = None,
    trace: dict | None = None,
    answer_provider: LLMProvider | None = None,
    allow_general_fallback: bool = False,
) -> dict:
    all_chunks = load_course_pack_chunks(pack_id, output_root=output_root)
    search_question = retrieval_question or question

    started = time.perf_counter()
    graph = _load_or_build_course_pack_graph(pack_id, output_root=output_root, chunks=all_chunks)
    _trace_stage(trace, "load_course_graph", started)

    started = time.perf_counter()
    graph_selection = _select_course_graph_context(search_question, graph)
    graph_edges = graph_selection["graph_context"]
    _trace_stage(trace, "retrieve_graph_context", started)

    started = time.perf_counter()
    graph_chunks = _chunks_from_graph_edges(graph_edges, all_chunks)
    warnings: list[str] = []
    retrieval_mode = "course_graph_path" if graph_selection["graph_paths"] else "local_graph"

    if graph_chunks:
        supplemental_chunks = _balanced_chunks(query=search_question, chunks=all_chunks, top_k=top_k)
        chunks = _dedupe_chunks([*graph_chunks, *supplemental_chunks])[:top_k]
        fallback_used = False
    else:
        supplemental_chunks = []
        retrieval_mode = "local_graph_fallback_vector"
        fallback_used = True
        warnings.append("No matching course graph evidence was found. Falling back to balanced vector retrieval.")
        chunks = _balanced_chunks(query=search_question, chunks=all_chunks, top_k=top_k)
    _trace_stage(trace, "select_evidence_chunks", started)

    started = time.perf_counter()
    result = generate_source_grounded_answer(
        query=question,
        chunks=chunks,
        index_provider=_PreselectedIndexProvider(),
        llm_provider=answer_provider or MockLLMProvider(),
        top_k=top_k,
        allow_general_fallback=allow_general_fallback,
    )
    _trace_stage(trace, "compose_answer", started)

    payload = result.to_dict()
    payload["sentence_citations"] = _sentence_citations(payload.get("answer", ""), chunks)
    payload["mode"] = "local_graph"
    payload["retrieval_mode"] = retrieval_mode
    payload["graph_context"] = graph_edges
    payload["matched_entities"] = graph_selection["matched_entities"]
    payload["traversal_strategy"] = graph_selection["traversal_strategy"]
    payload["graph_paths"] = graph_selection["graph_paths"]
    payload["evidence_chunks"] = [source_ref.to_dict() for source_ref in _sources_from_chunks(chunks)]
    payload["warnings"] = [*payload.get("warnings", []), *warnings]
    payload["_retrieval_debug"] = {
        "candidate_chunks": len(all_chunks),
        "selected_chunks": len(chunks),
        "candidate_graph_edges": len(graph.get("edges", [])),
        "selected_graph_edges": len(graph_edges),
        "supplemental_chunks": len(supplemental_chunks),
        "fallback_used": fallback_used,
    }
    return payload


def _load_or_build_course_pack_graph(pack_id: str, output_root: str, chunks: list[Chunk]) -> dict:
    output_dir = course_pack_dir(pack_id, output_root=output_root)
    graph_path = output_dir / "graph.json"
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list) and isinstance(graph.get("edges"), list):
            return graph
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return build_concept_map(chunks, output_dir=str(output_dir))


def _select_course_graph_context(question: str, graph: dict) -> dict:
    entities = sorted(_query_entities(question, graph))
    strategy = _graph_traversal_strategy(question, entities)
    graph_paths: list[dict] = []

    if not entities:
        return {
            "matched_entities": [],
            "traversal_strategy": strategy,
            "graph_context": [],
            "graph_paths": [],
        }

    if strategy == "prerequisite":
        graph_edges = _prerequisite_edges(entities, graph)
        graph_paths = _direct_edge_paths(graph_edges)
    elif strategy == "contrast":
        graph_edges = _contrast_edges(entities, graph)
        graph_paths = _direct_edge_paths(graph_edges)
    elif strategy == "path":
        graph_edges, graph_paths = _graph_paths_between_entities(entities, graph)
        if not graph_edges:
            graph_edges = _select_graph_edges(question, graph, entities=entities)
    else:
        graph_edges = _select_graph_edges(question, graph, entities=entities)

    return {
        "matched_entities": entities,
        "traversal_strategy": strategy,
        "graph_context": _dedupe_graph_edges(graph_edges),
        "graph_paths": graph_paths,
    }


def _graph_traversal_strategy(question: str, entities: list[str]) -> str:
    normalized = question.lower()
    if any(term in normalized for term in ["먼저", "이해하려면", "선수", "기초", "prerequisite", "before"]):
        return "prerequisite"
    if any(term in normalized for term in ["차이", "비교", "대조", "contrast", "different"]):
        return "contrast"
    if len(entities) >= 2 and any(term in normalized for term in ["연결", "흐름", "pipeline", "path", "connect"]):
        return "path"
    return "edge"


def _select_graph_edges(question: str, graph: dict, entities: list[str] | None = None) -> list[dict]:
    target_entities = set(entities or _query_entities(question, graph))
    if not target_entities:
        return []
    exact: list[dict] = []
    partial: list[dict] = []
    for edge in graph.get("edges", []):
        relation = str(edge.get("relation", ""))
        if relation in STRUCTURAL_RELATIONS:
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source in target_entities and target in target_entities:
            exact.append(edge)
        elif source in target_entities or target in target_entities:
            partial.append(edge)
    return [*exact, *partial]


def _prerequisite_edges(entities: list[str], graph: dict) -> list[dict]:
    target_entities = set(entities)
    edges: list[dict] = []
    for edge in graph.get("edges", []):
        if edge.get("relation") in PREREQUISITE_RELATIONS and edge.get("target") in target_entities:
            edges.append(edge)
    if edges:
        return edges
    for edge in graph.get("edges", []):
        if edge.get("target") in target_entities and edge.get("relation") in {"is_a", "uses", "explains"}:
            edges.append(edge)
    return edges


def _contrast_edges(entities: list[str], graph: dict) -> list[dict]:
    target_entities = set(entities)
    edges = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("relation") in CONTRAST_RELATIONS
        and (edge.get("source") in target_entities or edge.get("target") in target_entities)
    ]
    return edges or _select_graph_edges(" ".join(entities), graph, entities=entities)


def _graph_paths_between_entities(entities: list[str], graph: dict) -> tuple[list[dict], list[dict]]:
    edges: list[dict] = []
    paths: list[dict] = []
    for index, source in enumerate(entities):
        for target in entities[index + 1 :]:
            steps = _find_shortest_graph_path(source, target, graph, max_depth=4)
            if not steps:
                continue
            edges.extend(step[0] for step in steps)
            paths.append(_graph_path_payload(steps))
            if len(paths) >= 4:
                return _dedupe_graph_edges(edges), paths
    return _dedupe_graph_edges(edges), paths


def _find_shortest_graph_path(source: str, target: str, graph: dict, max_depth: int = 4) -> list[tuple[dict, str, str, str]]:
    adjacency: dict[str, list[tuple[str, dict, str]]] = {}
    for edge in graph.get("edges", []):
        relation = str(edge.get("relation", ""))
        if relation not in COURSE_GRAPH_PATH_RELATIONS:
            continue
        left = str(edge.get("source", ""))
        right = str(edge.get("target", ""))
        if not left or not right:
            continue
        adjacency.setdefault(left, []).append((right, edge, "forward"))
        adjacency.setdefault(right, []).append((left, edge, "reverse"))

    queue: list[tuple[str, list[tuple[dict, str, str, str]]]] = [(source, [])]
    visited = {source}
    while queue:
        current, path = queue.pop(0)
        if len(path) >= max_depth:
            continue
        for neighbor, edge, direction in adjacency.get(current, []):
            if neighbor in visited:
                continue
            next_path = [*path, (edge, direction, current, neighbor)]
            if neighbor == target:
                return next_path
            visited.add(neighbor)
            queue.append((neighbor, next_path))
    return []


def _graph_path_payload(steps: list[tuple[dict, str, str, str]]) -> dict:
    if not steps:
        return {"nodes": [], "edges": []}
    nodes = [steps[0][2]]
    edges: list[dict] = []
    for edge, direction, _current, neighbor in steps:
        nodes.append(neighbor)
        edges.append(
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "relation": edge.get("relation"),
                "direction": direction,
                "evidence": edge.get("evidence", []),
            }
        )
    return {"nodes": nodes, "edges": edges, "description": _graph_path_description(nodes, edges)}


def _graph_path_description(nodes: list[str], edges: list[dict]) -> str:
    if not nodes:
        return ""
    parts = [nodes[0]]
    for index, edge in enumerate(edges):
        relation = str(edge.get("relation") or "related_to")
        arrow = f"--{relation}-->" if edge.get("direction") == "forward" else f"<--{relation}--"
        parts.extend([arrow, nodes[index + 1]])
    return " ".join(parts)


def _direct_edge_paths(edges: list[dict]) -> list[dict]:
    paths: list[dict] = []
    for edge in _dedupe_graph_edges(edges):
        paths.append(
            {
                "nodes": [edge.get("source"), edge.get("target")],
                "edges": [
                    {
                        "source": edge.get("source"),
                        "target": edge.get("target"),
                        "relation": edge.get("relation"),
                        "direction": "forward",
                        "evidence": edge.get("evidence", []),
                    }
                ],
                "description": f"{edge.get('source')} --{edge.get('relation')}--> {edge.get('target')}",
            }
        )
    return paths


def _dedupe_graph_edges(edges: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for edge in edges:
        evidence = (edge.get("evidence") or [{}])[0]
        key = (
            str(edge.get("source", "")),
            str(edge.get("target", "")),
            str(edge.get("relation", "")),
            str(evidence.get("chunk_id", "")),
        )
        if key in seen:
            continue
        deduped.append(edge)
        seen.add(key)
    return deduped


def _query_entities(question: str, graph: dict) -> set[str]:
    normalized = question.lower()
    compact_question = re.sub(r"[^0-9a-z가-힣]", "", normalized)
    entities: set[str] = set()
    for node in graph.get("nodes", []):
        if node.get("type") != "concept":
            continue
        node_id = str(node.get("id", ""))
        label = str(node.get("label") or node_id)
        compact_id = re.sub(r"[^0-9a-z가-힣]", "", node_id.lower())
        compact_label = re.sub(r"[^0-9a-z가-힣]", "", label.lower())
        if (
            node_id.lower() in normalized
            or label.lower() in normalized
            or (len(compact_id) >= 2 and compact_id in compact_question)
            or (len(compact_label) >= 2 and compact_label in compact_question)
        ):
            entities.add(node_id)
    return entities


def _chunks_from_graph_edges(edges: list[dict], chunks: list[Chunk]) -> list[Chunk]:
    selected: list[Chunk] = []
    for edge in edges:
        for evidence in edge.get("evidence", []) or []:
            matched = _chunk_from_evidence(evidence, chunks)
            if matched is not None:
                selected.append(matched)
    return selected


def _chunk_from_evidence(evidence: dict, chunks: list[Chunk]) -> Chunk | None:
    for chunk in chunks:
        metadata = chunk.metadata or {}
        if evidence.get("chunk_id") != chunk.chunk_id:
            continue
        if evidence.get("page") != chunk.page:
            continue
        if evidence.get("doc_id") and evidence.get("doc_id") != metadata.get("doc_id"):
            continue
        if evidence.get("filename") and evidence.get("filename") != metadata.get("filename"):
            continue
        return chunk
    return None


def _flashcards_from_study_payload(base: dict, summary_payload: dict, limit: int) -> list[dict]:
    cards: list[dict] = []
    for item in base.get("glossary", []):
        term = item.get("term")
        definition = item.get("definition")
        if not term or not definition:
            continue
        cards.append({"front": term, "back": definition, "sources": item.get("sources", [])})
        if len(cards) >= limit:
            return cards
    for item in summary_payload.get("key_concepts", []):
        term = item.get("term")
        description = item.get("description")
        if not term or not description:
            continue
        cards.append({"front": term, "back": description, "sources": item.get("sources", [])})
        if len(cards) >= limit:
            return cards
    return cards
def _select_pack_chunks(pack_id: str, query: str, output_root: str, top_k: int) -> list[Chunk]:
    chunks = load_course_pack_chunks(pack_id, output_root=output_root)
    if not query:
        return _balanced_chunks(query="전체 요약", chunks=chunks, top_k=max(top_k, len(_group_chunks_by_document(chunks))))
    return _balanced_chunks(query=query, chunks=chunks, top_k=top_k)


def _balanced_chunks(query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
    if not chunks or top_k <= 0:
        return []

    groups = _group_chunks_by_document(chunks)
    is_overview = _is_overview_query(query)
    group_selected: list[Chunk] = []
    selected: list[Chunk] = []

    for group in groups.values():
        contexts = retrieve_contexts(query=query, chunks=group, top_k=1).contexts if query else []
        if contexts:
            group_selected.extend(chunks_from_contexts(contexts))
            continue
        if is_overview:
            representative = _representative_chunk(group)
            if representative is not None:
                group_selected.append(representative)

    selected.extend(_spread_chunks(group_selected, top_k) if is_overview else group_selected)

    global_contexts = retrieve_contexts(query=query, chunks=chunks, top_k=max(top_k, 1)).contexts if query else []
    if not is_overview or len(selected) < top_k:
        selected.extend(chunks_from_contexts(global_contexts))

    if not selected and is_overview:
        selected.extend(chunk for chunk in (_representative_chunk(group) for group in groups.values()) if chunk is not None)

    return _dedupe_chunks(selected)[:top_k]


def _spread_chunks(chunks: list[Chunk], limit: int) -> list[Chunk]:
    if limit <= 0 or not chunks:
        return []
    if len(chunks) <= limit:
        return list(chunks)
    if limit == 1:
        return [chunks[0]]
    indexes = [round(index * (len(chunks) - 1) / (limit - 1)) for index in range(limit)]
    return [chunks[index] for index in indexes]


def _group_chunks_by_document(chunks: list[Chunk]) -> OrderedDict[str, list[Chunk]]:
    groups: OrderedDict[str, list[Chunk]] = OrderedDict()
    for chunk in chunks:
        key = _document_key(chunk)
        groups.setdefault(key, []).append(chunk)
    return groups


def _latest_document_version_chunks(chunks: list[Chunk]) -> list[Chunk]:
    latest_groups: OrderedDict[str, list[Chunk]] = OrderedDict()
    for group in _group_chunks_by_document(chunks).values():
        if not group:
            continue
        metadata = group[0].metadata or {}
        key = str(metadata.get("filename") or metadata.get("doc_id") or "document")
        latest_groups[key] = group
    return [chunk for group in latest_groups.values() for chunk in group]


def _select_onboarding_report_chunks(query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
    groups = _group_chunks_by_document(chunks)
    if not groups:
        return []
    if _is_overview_query(query):
        return list(chunks)

    selected = _balanced_chunks(query=query, chunks=chunks, top_k=max(top_k, 1))
    selected_keys = {_document_key(chunk) for chunk in selected}
    query_terms = {term.lower() for term in _keyword_terms(query) if len(term) >= 2}

    for key, group in groups.items():
        if not group:
            continue
        metadata = group[0].metadata or {}
        filename = str(metadata.get("filename") or "")
        first_line = next((line.strip() for line in group[0].text.splitlines() if line.strip()), "")
        heading = f"{filename} {first_line}".lower()
        if any(term in heading for term in query_terms):
            selected_keys.add(key)

    if not selected_keys:
        return list(chunks)
    return [chunk for key, group in groups.items() if key in selected_keys for chunk in group]


def _document_key(chunk: Chunk) -> str:
    metadata = chunk.metadata or {}
    return str(metadata.get("doc_id") or metadata.get("filename") or "document")


def _representative_chunk(chunks: list[Chunk]) -> Chunk | None:
    if not chunks:
        return None
    meaningful = [chunk for chunk in chunks if len(chunk.text.strip()) >= 30]
    if meaningful:
        return meaningful[0]
    return chunks[0]


def _dedupe_chunks(chunks: list[Chunk]) -> list[Chunk]:
    deduped: list[Chunk] = []
    seen: set[tuple[str | None, str | None, int, str]] = set()
    for chunk in chunks:
        metadata = chunk.metadata or {}
        key = (metadata.get("doc_id"), metadata.get("filename"), chunk.page, chunk.chunk_id)
        if key in seen:
            continue
        deduped.append(chunk)
        seen.add(key)
    return deduped


def _is_overview_query(query: str) -> bool:
    normalized = query.lower()
    return not query.strip() or any(term in normalized for term in OVERVIEW_QUERY_TERMS)


def _pack_id_from_documents(documents: list[dict]) -> str:
    if not documents:
        return f"pack_{uuid4().hex[:12]}"
    digest = hashlib.sha256()
    for document in documents:
        digest.update(str(document.get("doc_id", "")).encode("utf-8"))
        digest.update(str(document.get("filename", "")).encode("utf-8"))
    return f"pack_{digest.hexdigest()[:16]}"


def _safe_pack_id(pack_id: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", pack_id or "").strip("-_.")
    return cleaned or f"pack_{uuid4().hex[:12]}"


def _save_pack_artifact(pack_id: str, output_root: str, name: str, payload: dict) -> None:
    save_artifact(course_pack_dir(pack_id, output_root=output_root), name, payload)


def _load_onboarding_report(output_dir: Path) -> dict | None:
    path = output_dir / "onboarding_report.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _reuse_unchanged_report_sections(
    previous_report: dict | None,
    current_report: dict,
    impact: dict,
) -> int:
    if not previous_report:
        return 0
    if (
        previous_report.get("audience") != current_report.get("audience")
        or previous_report.get("objective") != current_report.get("objective")
    ):
        return 0

    changed_keys = {
        *(str(item.get("filename") or item.get("doc_id") or "") for item in impact.get("added_sources", [])),
        *(str(item.get("filename") or item.get("doc_id") or "") for item in impact.get("removed_sources", [])),
        *(
            str((item.get("after") or {}).get("filename") or (item.get("after") or {}).get("doc_id") or "")
            for item in impact.get("updated_sources", [])
        ),
    }
    previous_by_source = {
        _report_section_source_key(section): section
        for section in previous_report.get("sections", [])
        if _report_section_source_key(section)
    }
    reused = 0
    sections = current_report.get("sections", [])
    for index, section in enumerate(list(sections)):
        source_key = _report_section_source_key(section)
        previous = previous_by_source.get(source_key)
        if not previous or source_key in changed_keys:
            continue
        replacement = copy.deepcopy(previous)
        replacement["index"] = section.get("index")
        sections[index] = replacement
        reused += 1
    return reused


def _report_section_source_key(section: dict) -> str:
    sources = section.get("sources", [])
    if not sources:
        return ""
    source = sources[0]
    return str(source.get("filename") or source.get("doc_id") or "")


def _write_json(path: Path, payload: dict) -> None:
    atomic_write_json(path, payload)


class _PreselectedIndexProvider:
    def search(self, question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
        return chunks[:top_k]





