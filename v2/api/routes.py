from __future__ import annotations

import asyncio
import json
import queue
import threading
from uuid import uuid4

try:
    from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
    from fastapi.responses import FileResponse, StreamingResponse
except ImportError:  # Keeps the scaffold importable without FastAPI installed.
    APIRouter = None  # type: ignore[assignment]
    BackgroundTasks = None  # type: ignore[assignment]
    File = None  # type: ignore[assignment]
    Form = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    UploadFile = None  # type: ignore[assignment]
    FileResponse = None  # type: ignore[assignment]
    StreamingResponse = None  # type: ignore[assignment]

from v2.api.schemas import (
    AnswerResponse,
    AudioScriptRequest,
    AudioScriptResponse,
    ConceptMapRequest,
    ConceptMapResponse,
    CoursePackArtifactsResponse,
    CoursePackAudioScriptRequest,
    CoursePackConceptMapExportRequest,
    CoursePackConceptMapExportResponse,
    CoursePackConceptMapRequest,
    CoursePackIngestRequest,
    CoursePackJobRequest,
    CoursePackJobResponse,
    CoursePackOnboardingReportImpactResponse,
    CoursePackOnboardingReportRequest,
    CoursePackOnboardingReportResponse,
    CoursePackQueryRequest,
    CoursePackResponse,
    CoursePackStudyKitRequest,
    CoursePackSummaryRequest,
    CoursePackSummaryResponse,
    DocumentResponse,
    IngestRequest,
    QueryRequest,
    StudyKitRequest,
)
from v2.audio_script import generate_audio_script
from v2.course_pack_jobs import (
    create_course_pack_job as create_course_pack_job_service,
    load_course_pack_job,
    run_course_pack_job,
)
from v2.course_packs import (
    artifacts_for_course_pack,
    ask_course_pack as ask_course_pack_service,
    audio_script_for_course_pack,
    concept_map_for_course_pack,
    course_pack_dir,
    create_course_pack,
    export_concept_map_for_course_pack,
    list_course_packs,
    load_course_pack,
    mindmap_view_for_course_pack,
    onboarding_report_for_course_pack,
    onboarding_report_impact_for_course_pack,
    study_kit_for_course_pack,
    summary_for_course_pack,
    tts_for_course_pack,
)
from v2.documents import chunks_from_payload_or_doc, document_dir, load_document
from v2.graph.concept_map import build_concept_map
from v2.ingest import ingest_local_document
from v2.io_utils import atomic_write_json
from v2.providers.local import LocalIndexProvider, MockLLMProvider
from v2.rag.answering import generate_source_grounded_answer
from v2.rag.retrieval import retrieve_contexts
from v2.runtime import DATA_ROOT, RuntimePathError, resolve_output_root, resolve_source_path, validate_identifier
from v2.study_kit import generate_study_kit
from v2.uploads import save_uploaded_files

router = APIRouter(prefix="/v2", tags=["v2-compatible"]) if APIRouter else None
v3_router = APIRouter(prefix="/v3", tags=["v3"]) if APIRouter else None
_FILE_REQUIRED = File(...) if File is not None else None
_FORM_NONE = Form(None) if Form is not None else None
_FORM_TRUE = Form(True) if Form is not None else True
_FORM_FALSE = Form(False) if Form is not None else False


def _payload(model) -> dict:
    payload = model.model_dump(exclude_none=True) if hasattr(model, "model_dump") else model.dict(exclude_none=True)
    try:
        if "output_root" in payload:
            payload["output_root"] = str(resolve_output_root(payload["output_root"]))
        if payload.get("output_dir"):
            payload["output_dir"] = str(resolve_output_root(payload["output_dir"]))
        if payload.get("path"):
            payload["path"] = str(resolve_source_path(payload["path"]))
        if "paths" in payload:
            payload["paths"] = [str(resolve_source_path(path)) for path in payload.get("paths", [])]
        if payload.get("pack_id"):
            payload["pack_id"] = validate_identifier(payload["pack_id"], "pack_id")
        if payload.get("doc_id"):
            payload["doc_id"] = validate_identifier(payload["doc_id"], "doc_id")
    except (RuntimePathError, ValueError) as exc:
        _raise_bad_request("invalid_path_or_identifier", str(exc))
    return payload


def _query(payload: dict) -> str:
    return payload.get("question") or payload.get("query") or ""


def _required_query(payload: dict) -> str:
    query = _query(payload).strip()
    if not query:
        if HTTPException is not None:
            raise HTTPException(status_code=422, detail={"error": "question_required"})
        raise ValueError("question or query is required")
    return query


def _raise_bad_request(error: str, message: str) -> None:
    if HTTPException is not None:
        raise HTTPException(status_code=400, detail={"error": error, "message": message})
    raise ValueError(message)


def _safe_output_root(value: str) -> str:
    try:
        return str(resolve_output_root(value))
    except RuntimePathError as exc:
        _raise_bad_request("invalid_output_root", str(exc))
    raise AssertionError("unreachable")


def _safe_identifier(value: str, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except ValueError as exc:
        _raise_bad_request(f"invalid_{label}", str(exc))
    raise AssertionError("unreachable")


def _selected_chunks(payload: dict):
    chunks = chunks_from_payload_or_doc(payload)
    query = _query(payload)
    if not query:
        return chunks
    result = retrieve_contexts(query=query, chunks=chunks, top_k=payload.get("top_k", 4))
    from v2.rag.retrieval import chunks_from_contexts

    return chunks_from_contexts(result.contexts)


def _save_doc_artifact(payload: dict, name: str, data: dict) -> None:
    doc_id = payload.get("doc_id")
    if not doc_id:
        return
    path = document_dir(doc_id, payload.get("output_root", "outputs")) / name
    atomic_write_json(path, data)


def _raise_not_found(doc_id: str):
    if HTTPException is not None:
        raise HTTPException(status_code=404, detail={"error": "document_not_found", "doc_id": doc_id})
    raise FileNotFoundError(f"document not found: {doc_id}")


def _raise_pack_not_found(pack_id: str):
    if HTTPException is not None:
        raise HTTPException(status_code=404, detail={"error": "course_pack_not_found", "pack_id": pack_id})
    raise FileNotFoundError(f"course pack not found: {pack_id}")


def _ensure_course_pack(pack_id: str, output_root: str) -> dict:
    course_pack = load_course_pack(pack_id, output_root=output_root)
    if course_pack.get("warnings") and not course_pack.get("output_dir"):
        _raise_pack_not_found(pack_id)
    return course_pack


def ingest_document(request: IngestRequest) -> dict:
    payload = _payload(request)
    result = ingest_local_document(
        path=payload["path"],
        output_root=payload.get("output_root", "outputs"),
        max_chunk_chars=payload.get("max_chunk_chars", 900),
    )
    return result.to_dict()


def get_document(doc_id: str, output_root: str = "outputs") -> dict:
    doc_id = _safe_identifier(doc_id, "doc_id")
    output_root = _safe_output_root(output_root)
    document = load_document(doc_id, output_root=output_root)
    if document.get("warnings") and not document.get("filename"):
        _raise_not_found(doc_id)
    return document


def ask(request: QueryRequest) -> dict:
    payload = _payload(request)
    result = generate_source_grounded_answer(
        query=_required_query(payload),
        chunks=chunks_from_payload_or_doc(payload),
        index_provider=LocalIndexProvider(),
        llm_provider=MockLLMProvider(),
        top_k=payload.get("top_k", 4),
    )
    return result.to_dict()


def study_kit(request: StudyKitRequest) -> dict:
    payload = _payload(request)
    result = generate_study_kit(_selected_chunks(payload), max_items=payload.get("max_items", 4))
    _save_doc_artifact(payload, "study_kit.json", result)
    return result


def audio_script(request: AudioScriptRequest) -> dict:
    payload = _payload(request)
    result = generate_audio_script(
        _selected_chunks(payload),
        mode=payload.get("mode", "briefing_3min"),
        llm_provider=payload.get("llm_provider", "mock"),
        llm_model=payload.get("llm_model"),
        grounding=payload.get("grounding", "creative"),
        target_minutes=payload.get("target_minutes"),
        target_chars=payload.get("target_chars"),
    )
    _save_doc_artifact(payload, "audio_script.json", result)
    return result


def concept_map(request: ConceptMapRequest) -> dict:
    payload = _payload(request)
    output_dir = None
    if payload.get("doc_id"):
        output_dir = str(document_dir(payload["doc_id"], payload.get("output_root", "outputs")))
    return build_concept_map(_selected_chunks(payload), output_dir=output_dir)


def retrieve(request: QueryRequest) -> dict:
    payload = _payload(request)
    result = retrieve_contexts(
        query=_query(payload),
        chunks=chunks_from_payload_or_doc(payload),
        top_k=payload.get("top_k", 4),
    )
    return result.to_dict()


def ingest_course_pack(request: CoursePackIngestRequest) -> dict:
    payload = _payload(request)
    return create_course_pack(
        paths=payload.get("paths", []),
        output_root=payload.get("output_root", "outputs"),
        max_chunk_chars=payload.get("max_chunk_chars", 900),
        pack_id=payload.get("pack_id"),
        append=payload.get("append", False),
    )


async def upload_course_pack(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = _FILE_REQUIRED,
    pack_id: str | None = _FORM_NONE,
    append: bool = _FORM_FALSE,
    run_async: bool = _FORM_TRUE,
) -> dict:
    requested_pack_id = _safe_identifier(pack_id, "pack_id") if pack_id else f"pack_upload_{uuid4().hex[:12]}"
    try:
        paths = await save_uploaded_files(files)
    except ValueError as exc:
        if HTTPException is not None:
            raise HTTPException(status_code=400, detail={"error": "invalid_upload", "message": str(exc)}) from exc
        raise

    output_root = str(DATA_ROOT)
    job = create_course_pack_job_service(
        paths=paths,
        output_root=output_root,
        max_chunk_chars=900,
        pack_id=requested_pack_id,
        append=append,
        run_inline=not run_async,
    )
    if run_async:
        background_tasks.add_task(run_course_pack_job, job["job_id"], output_root)
    return job


def get_course_packs(output_root: str = "outputs") -> dict:
    return {"course_packs": list_course_packs(output_root=_safe_output_root(output_root))}


def create_course_pack_job(request: CoursePackJobRequest, background_tasks: BackgroundTasks = None) -> dict:
    payload = _payload(request)
    output_root = payload.get("output_root", "outputs")
    run_async = bool(payload.get("run_async"))
    job = create_course_pack_job_service(
        paths=payload.get("paths", []),
        output_root=output_root,
        max_chunk_chars=payload.get("max_chunk_chars", 900),
        pack_id=payload.get("pack_id"),
        append=payload.get("append", False),
        run_inline=not run_async,
    )
    if run_async:
        if background_tasks is not None and hasattr(background_tasks, "add_task"):
            background_tasks.add_task(run_course_pack_job, job["job_id"], output_root)
        else:
            job = run_course_pack_job(job["job_id"], output_root=output_root)
    return job


def get_course_pack_job(job_id: str, output_root: str = "outputs") -> dict:
    job_id = _safe_identifier(job_id, "job_id")
    output_root = _safe_output_root(output_root)
    job = load_course_pack_job(job_id, output_root=output_root)
    if job.get("status") == "not_found":
        if HTTPException is not None:
            raise HTTPException(status_code=404, detail={"error": "course_pack_job_not_found", "job_id": job_id})
        raise FileNotFoundError(f"course pack job not found: {job_id}")
    return job


def get_course_pack(pack_id: str, output_root: str = "outputs") -> dict:
    pack_id = _safe_identifier(pack_id, "pack_id")
    output_root = _safe_output_root(output_root)
    return _ensure_course_pack(pack_id, output_root=output_root)


def get_course_pack_artifacts(pack_id: str, output_root: str = "outputs", include_content: bool = True) -> dict:
    pack_id = _safe_identifier(pack_id, "pack_id")
    output_root = _safe_output_root(output_root)
    _ensure_course_pack(pack_id, output_root=output_root)
    return artifacts_for_course_pack(pack_id=pack_id, output_root=output_root, include_content=include_content)


def ask_course_pack(request: CoursePackQueryRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return ask_course_pack_service(
        pack_id=payload["pack_id"],
        question=_required_query(payload),
        output_root=payload.get("output_root", "outputs"),
        top_k=payload.get("top_k", 4),
        mode=payload.get("mode", "vector"),
        llm_provider=payload.get("llm_provider", "mock"),
        llm_model=payload.get("llm_model"),
        allow_general_fallback=payload.get("allow_general_fallback", False),
        allow_web_fallback=payload.get("allow_web_fallback", False),
        web_provider=payload.get("web_provider", "wikipedia"),
        web_top_k=payload.get("web_top_k", 3),
        conversation_history=payload.get("conversation_history", []),
    )


def _sse_event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_course_pack_answer(http_request: Request, request: CoursePackQueryRequest):
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    events: queue.Queue[tuple[str, object]] = queue.Queue()
    cancel_event = threading.Event()

    def on_token(text: str) -> None:
        if not cancel_event.is_set():
            events.put(("token", text))

    def run_service() -> None:
        try:
            result = ask_course_pack_service(
                pack_id=payload["pack_id"],
                question=_required_query(payload),
                output_root=payload.get("output_root", "outputs"),
                top_k=payload.get("top_k", 4),
                mode=payload.get("mode", "vector"),
                llm_provider=payload.get("llm_provider", "mock"),
                llm_model=payload.get("llm_model"),
                allow_general_fallback=payload.get("allow_general_fallback", False),
                allow_web_fallback=payload.get("allow_web_fallback", False),
                web_provider=payload.get("web_provider", "wikipedia"),
                web_top_k=payload.get("web_top_k", 3),
                conversation_history=payload.get("conversation_history", []),
                token_callback=on_token,
                cancel_event=cancel_event,
            )
        except Exception as exc:  # pragma: no cover - exercised through the HTTP contract
            events.put(("error", {"message": str(exc)}))
        else:
            events.put(("result", result))

    async def event_stream():
        worker = asyncio.create_task(asyncio.to_thread(run_service))
        token_started = False
        try:
            status_message = (
                "강의자료를 확인하고 필요하면 외부 검색을 진행해요."
                if payload.get("allow_web_fallback")
                else "자료를 검색하고 있어요."
            )
            yield _sse_event("status", {"stage": "retrieving", "message": status_message})
            while True:
                if await http_request.is_disconnected():
                    cancel_event.set()
                    break
                try:
                    event_name, data = events.get_nowait()
                except queue.Empty:
                    if worker.done():
                        break
                    await asyncio.sleep(0.04)
                    continue

                if event_name == "token":
                    if not token_started:
                        token_started = True
                        yield _sse_event("status", {"stage": "generating", "message": "답변을 작성하고 있어요."})
                    yield _sse_event("token", {"text": str(data)})
                    continue

                yield _sse_event(event_name, data if isinstance(data, dict) else {"message": str(data)})
                if event_name in {"result", "error"}:
                    break
        finally:
            if not worker.done():
                cancel_event.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def study_kit_course_pack(request: CoursePackStudyKitRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return study_kit_for_course_pack(
        pack_id=payload["pack_id"],
        query=_query(payload),
        output_root=payload.get("output_root", "outputs"),
        top_k=payload.get("top_k", 4),
        max_items=payload.get("max_items", 4),
    )


def summary_course_pack(request: CoursePackSummaryRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return summary_for_course_pack(
        pack_id=payload["pack_id"],
        query=_query(payload),
        output_root=payload.get("output_root", "outputs"),
        top_k=payload.get("top_k", 8),
        max_items=payload.get("max_items", 5),
        llm_provider=payload.get("llm_provider", "mock"),
        llm_model=payload.get("llm_model"),
    )


def onboarding_report_course_pack(request: CoursePackOnboardingReportRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return onboarding_report_for_course_pack(
        pack_id=payload["pack_id"],
        query=_query(payload),
        output_root=payload.get("output_root", "outputs"),
        top_k=payload.get("top_k", 8),
        title=payload.get("title"),
        audience=payload.get("audience", "신입 구성원"),
        objective=payload.get("objective", "핵심 규정과 업무 흐름을 출처와 함께 이해"),
        max_sections=payload.get("max_sections", 6),
        llm_provider=payload.get("llm_provider", "mock"),
        llm_model=payload.get("llm_model"),
    )


def get_onboarding_report_impact(pack_id: str, output_root: str = "outputs") -> dict:
    pack_id = _safe_identifier(pack_id, "pack_id")
    output_root = _safe_output_root(output_root)
    _ensure_course_pack(pack_id, output_root=output_root)
    return onboarding_report_impact_for_course_pack(pack_id=pack_id, output_root=output_root)


def audio_script_course_pack(request: CoursePackAudioScriptRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return audio_script_for_course_pack(
        pack_id=payload["pack_id"],
        query=_query(payload),
        output_root=payload.get("output_root", "outputs"),
        top_k=payload.get("top_k", 4),
        mode=payload.get("mode", "briefing_3min"),
        llm_provider=payload.get("llm_provider", "mock"),
        llm_model=payload.get("llm_model"),
        grounding=payload.get("grounding", "creative"),
        target_minutes=payload.get("target_minutes"),
        target_chars=payload.get("target_chars"),
        knowledge_scope=payload.get("knowledge_scope", "course_pack"),
    )


def tts_course_pack(request: CoursePackAudioScriptRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return tts_for_course_pack(
        pack_id=payload["pack_id"],
        query=_query(payload),
        output_root=payload.get("output_root", "outputs"),
        top_k=payload.get("top_k", 4),
        mode=payload.get("mode", "podcast"),
        llm_provider=payload.get("llm_provider", "mock"),
        llm_model=payload.get("llm_model"),
        grounding=payload.get("grounding", "creative"),
        target_minutes=payload.get("target_minutes"),
        target_chars=payload.get("target_chars"),
        knowledge_scope=payload.get("knowledge_scope", "course_pack"),
        voice=payload.get("voice", "ko-KR-SunHiNeural"),
        guest_voice=payload.get("guest_voice", "ko-KR-InJoonNeural"),
        reuse_existing=payload.get("reuse_existing", False),
    )


def get_course_pack_file(pack_id: str, name: str, output_root: str = "outputs"):
    pack_id = _safe_identifier(pack_id, "pack_id")
    output_root = _safe_output_root(output_root)
    _ensure_course_pack(pack_id, output_root=output_root)
    base = course_pack_dir(pack_id, output_root=output_root).resolve()
    target = (base / name).resolve()
    if target != base and base not in target.parents:
        if HTTPException is not None:
            raise HTTPException(status_code=400, detail={"error": "invalid_artifact_path", "name": name})
        raise ValueError(f"invalid artifact path: {name}")
    if not target.exists() or target.is_dir():
        if HTTPException is not None:
            raise HTTPException(status_code=404, detail={"error": "artifact_not_found", "name": name})
        raise FileNotFoundError(f"artifact not found: {name}")
    if FileResponse is None:
        return {"path": str(target)}
    return FileResponse(target)


def export_concept_map_course_pack(request: CoursePackConceptMapExportRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return export_concept_map_for_course_pack(
        pack_id=payload["pack_id"],
        output_root=payload.get("output_root", "outputs"),
        max_nodes=payload.get("max_nodes", 60),
        max_edges=payload.get("max_edges", 120),
    )


def concept_map_course_pack(request: CoursePackConceptMapRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return concept_map_for_course_pack(pack_id=payload["pack_id"], output_root=payload.get("output_root", "outputs"))


def mindmap_course_pack(request: CoursePackConceptMapRequest) -> dict:
    payload = _payload(request)
    _ensure_course_pack(payload["pack_id"], output_root=payload.get("output_root", "outputs"))
    return mindmap_view_for_course_pack(pack_id=payload["pack_id"], output_root=payload.get("output_root", "outputs"))


def ingest_alias(request: IngestRequest) -> dict:
    return ingest_document(request)


def answer_alias(request: QueryRequest) -> dict:
    return ask(request)


def _register_api_routes(target_router) -> None:
    target_router.post("/documents/ingest", response_model=DocumentResponse)(ingest_document)
    target_router.get("/documents/{doc_id}", response_model=DocumentResponse)(get_document)
    target_router.post("/course-packs", response_model=CoursePackResponse)(ingest_course_pack)
    target_router.post("/course-packs/upload", response_model=CoursePackJobResponse)(upload_course_pack)
    target_router.post("/course-packs/jobs", response_model=CoursePackJobResponse)(create_course_pack_job)
    target_router.get("/course-packs/jobs/{job_id}", response_model=CoursePackJobResponse)(get_course_pack_job)
    target_router.get("/course-packs")(get_course_packs)
    target_router.get("/course-packs/{pack_id}", response_model=CoursePackResponse)(get_course_pack)
    target_router.get("/course-packs/{pack_id}/artifacts", response_model=CoursePackArtifactsResponse)(get_course_pack_artifacts)
    target_router.post("/course-packs/ask", response_model=AnswerResponse)(ask_course_pack)
    target_router.post("/course-packs/ask/stream")(stream_course_pack_answer)
    target_router.post("/course-packs/study-kit")(study_kit_course_pack)
    target_router.post("/course-packs/summary", response_model=CoursePackSummaryResponse)(summary_course_pack)
    target_router.post(
        "/course-packs/onboarding-report",
        response_model=CoursePackOnboardingReportResponse,
    )(onboarding_report_course_pack)
    target_router.get(
        "/course-packs/{pack_id}/onboarding-report-impact",
        response_model=CoursePackOnboardingReportImpactResponse,
    )(get_onboarding_report_impact)
    target_router.post("/course-packs/audio-script", response_model=AudioScriptResponse)(audio_script_course_pack)
    target_router.post("/course-packs/tts", response_model=AudioScriptResponse)(tts_course_pack)
    target_router.get("/course-packs/{pack_id}/files/{name}")(get_course_pack_file)
    target_router.post("/course-packs/concept-map", response_model=ConceptMapResponse)(concept_map_course_pack)
    target_router.post("/course-packs/mindmap")(mindmap_course_pack)
    target_router.post("/course-packs/concept-map/export", response_model=CoursePackConceptMapExportResponse)(export_concept_map_course_pack)
    target_router.post("/ask", response_model=AnswerResponse)(ask)
    target_router.post("/study-kit")(study_kit)
    target_router.post("/audio-script", response_model=AudioScriptResponse)(audio_script)
    target_router.post("/concept-map", response_model=ConceptMapResponse)(concept_map)
    target_router.post("/retrieve")(retrieve)
    target_router.post("/ingest", response_model=DocumentResponse)(ingest_alias)
    target_router.post("/answer", response_model=AnswerResponse)(answer_alias)


if router:
    _register_api_routes(router)
if v3_router:
    _register_api_routes(v3_router)
