from __future__ import annotations

import os
import re
import secrets
import tempfile
import time
from pathlib import Path
from uuid import uuid4

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:  # pragma: no cover - optional when importing the scaffold without API dependencies
    pass

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from v2.api.routes import router as v2_router, v3_router
from v2.demo import ensure_demo_course_pack
from v2.runtime import DATA_ROOT, DEMO_FIXTURE_ROOT, reset_request_id, set_request_id

app = FastAPI(
    title="CourseBee",
    version="3.0.0",
    description="Source-grounded onboarding reports, Q&A, and audio briefings from enterprise documents.",
)
DEMO_UI_PATH = Path(__file__).resolve().parent / "assets" / "coursebee_demo_ui.html"


@app.middleware("http")
async def request_context(request: Request, call_next):
    started = time.perf_counter()
    supplied_request_id = request.headers.get("x-request-id", "")
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", supplied_request_id):
        request_id = supplied_request_id
    else:
        request_id = uuid4().hex

    request_id_token = set_request_id(request_id)
    try:
        configured_api_key = os.environ.get("COURSEBEE_API_KEY", "")
        supplied_api_key = request.headers.get("x-api-key", "")
        if (
            configured_api_key
            and request.url.path.startswith(("/v2", "/v3"))
            and request.method != "OPTIONS"
            and not secrets.compare_digest(supplied_api_key, configured_api_key)
        ):
            response = JSONResponse(
                status_code=401,
                content={"detail": {"error": "invalid_api_key"}},
            )
        else:
            response = await call_next(request)
    finally:
        reset_request_id(request_id_token)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        descriptor, probe_name = tempfile.mkstemp(prefix=".coursebee-ready-", dir=DATA_ROOT)
        os.close(descriptor)
        Path(probe_name).unlink(missing_ok=True)
        fixture_count = len(list(DEMO_FIXTURE_ROOT.glob("*.txt")))
        if not DEMO_UI_PATH.is_file() or fixture_count == 0:
            raise OSError("packaged demo assets are unavailable")
    except OSError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": {"runtime": "failed"}, "detail": str(exc)},
        )
    return {
        "status": "ready",
        "checks": {"data_root": "writable", "demo_ui": "available", "demo_fixtures": fixture_count},
    }


@app.get("/demo", include_in_schema=False)
def demo_ui():
    ensure_demo_course_pack()
    return FileResponse(DEMO_UI_PATH)


@app.get("/demo-ko", include_in_schema=False)
def demo_ui_ko():
    ensure_demo_course_pack()
    return FileResponse(DEMO_UI_PATH)


if v2_router is not None:
    app.include_router(v2_router)
if v3_router is not None:
    app.include_router(v3_router)
