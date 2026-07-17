from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from v2.course_packs import create_course_pack
from v2.io_utils import atomic_write_json

_JOB_LOCKS: dict[str, Lock] = {}
_JOB_LOCKS_GUARD = Lock()


def create_course_pack_job(
    paths: list[str],
    output_root: str = "outputs",
    max_chunk_chars: int = 900,
    pack_id: str | None = None,
    append: bool = False,
    run_inline: bool = True,
) -> dict:
    job_id = _new_job_id()
    total_documents = len(paths)
    job = {
        "job_id": job_id,
        "status": "queued" if not run_inline else "running",
        "stage": "queued" if not run_inline else "ingesting_documents",
        "progress": 0.0 if not run_inline else 0.05,
        "processed_documents": 0,
        "total_documents": total_documents,
        "pack_id": pack_id,
        "course_pack": {},
        "inputs": {
            "paths": paths,
            "output_root": output_root,
            "max_chunk_chars": max_chunk_chars,
            "pack_id": pack_id,
            "append": append,
        },
        "warnings": [],
        "error": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "started_at": _now_iso() if run_inline else None,
        "finished_at": None,
    }
    _write_job(job, output_root=output_root)
    if run_inline:
        return run_course_pack_job(job_id, output_root=output_root)
    return job


def run_course_pack_job(job_id: str, output_root: str = "outputs") -> dict:
    with _job_lock(job_id):
        return _run_course_pack_job(job_id, output_root=output_root)


def _run_course_pack_job(job_id: str, output_root: str = "outputs") -> dict:
    job = load_course_pack_job(job_id, output_root=output_root)
    if job.get("status") == "not_found":
        return job
    if job.get("status") in {"succeeded", "failed"}:
        return job

    inputs = job.get("inputs", {})
    paths = list(inputs.get("paths") or [])
    max_chunk_chars = int(inputs.get("max_chunk_chars") or 900)
    requested_pack_id = inputs.get("pack_id") or job.get("pack_id")
    append = bool(inputs.get("append"))

    _update_job(
        job,
        output_root=output_root,
        status="running",
        stage="ingesting_documents",
        progress=0.05,
        processed_documents=0,
        started_at=job.get("started_at") or _now_iso(),
    )

    try:
        def record_progress(stage: str, processed: int, total: int) -> None:
            progress_by_stage = {
                "building_concept_map": 0.72,
                "building_summary_index": 0.84,
                "finalizing": 0.94,
            }
            if stage == "ingesting_documents":
                ratio = processed / max(total, 1)
                progress = 0.05 + (0.6 * ratio)
            else:
                progress = progress_by_stage.get(stage, 0.68)
            _update_job(
                job,
                output_root=output_root,
                stage=stage,
                progress=round(progress, 3),
                processed_documents=processed,
            )

        course_pack = create_course_pack(
            paths=paths,
            output_root=output_root,
            max_chunk_chars=max_chunk_chars,
            pack_id=requested_pack_id,
            append=append,
            progress_callback=record_progress,
        )
        _update_job(
            job,
            output_root=output_root,
            status="succeeded",
            stage="completed",
            progress=1.0,
            processed_documents=len(paths),
            pack_id=course_pack.get("pack_id"),
            course_pack=course_pack,
            warnings=course_pack.get("warnings", []),
            finished_at=_now_iso(),
        )
    except Exception as exc:  # pragma: no cover - defensive job status path
        _update_job(
            job,
            output_root=output_root,
            status="failed",
            stage="failed",
            progress=job.get("progress", 0.0),
            error=str(exc),
            warnings=[*job.get("warnings", []), str(exc)],
            finished_at=_now_iso(),
        )
    return job


def load_course_pack_job(job_id: str, output_root: str = "outputs") -> dict:
    path = course_pack_job_path(job_id, output_root=output_root)
    if not path.exists():
        return {
            "job_id": job_id,
            "status": "not_found",
            "stage": "missing",
            "progress": 0.0,
            "processed_documents": 0,
            "total_documents": 0,
            "warnings": [f"course pack job not found: {job_id}"],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def course_pack_job_path(job_id: str, output_root: str = "outputs") -> Path:
    return Path(output_root) / "course_pack_jobs" / f"{job_id}.json"


def _update_job(job: dict, output_root: str, **updates) -> None:
    job.update(updates)
    job["updated_at"] = _now_iso()
    _write_job(job, output_root=output_root)


def _write_job(job: dict, output_root: str) -> None:
    path = course_pack_job_path(job["job_id"], output_root=output_root)
    atomic_write_json(path, job)


def _job_lock(job_id: str) -> Lock:
    with _JOB_LOCKS_GUARD:
        return _JOB_LOCKS.setdefault(job_id, Lock())


def _new_job_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"job_{stamp}_{uuid4().hex[:6]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
