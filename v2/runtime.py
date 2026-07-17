from __future__ import annotations

import os
import re
from contextvars import ContextVar, Token
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("COURSEBEE_DATA_ROOT", REPO_ROOT / "outputs")).resolve()
UPLOAD_ROOT = DATA_ROOT / "uploads"
DEMO_FIXTURE_ROOT = PACKAGE_ROOT / "assets" / "demo_fixtures"
SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".txt", ".md", ".pptx"}
MAX_UPLOAD_BYTES = int(os.environ.get("COURSEBEE_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UPLOAD_FILES = int(os.environ.get("COURSEBEE_MAX_UPLOAD_FILES", "20"))
MAX_UPLOAD_BATCH_BYTES = int(os.environ.get("COURSEBEE_MAX_UPLOAD_BATCH_BYTES", str(100 * 1024 * 1024)))
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REQUEST_ID: ContextVar[str | None] = ContextVar("coursebee_request_id", default=None)


class RuntimePathError(ValueError):
    pass


def resolve_output_root(value: str | Path | None = None) -> Path:
    candidate = Path(value or DATA_ROOT)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    if candidate != DATA_ROOT and DATA_ROOT not in candidate.parents:
        raise RuntimePathError("output_root must stay inside the configured CourseBee data directory")
    return candidate


def resolve_source_path(value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    allow_local = os.environ.get("COURSEBEE_ALLOW_LOCAL_PATHS", "").lower() in {"1", "true", "yes"}
    if allow_local:
        return candidate
    allowed_roots = (DATA_ROOT, DEMO_FIXTURE_ROOT.resolve())
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise RuntimePathError("source paths must come from an uploaded file or the bundled demo fixtures")
    return candidate


def validate_identifier(value: str, label: str = "identifier") -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value or ""):
        raise ValueError(f"invalid {label}: use 1-128 letters, numbers, dots, dashes, or underscores")
    return value


def safe_upload_filename(value: str | None, index: int = 1) -> str:
    raw = Path(value or f"document-{index}.txt").name.strip()
    suffix = Path(raw).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError(f"unsupported upload extension: {suffix or '<none>'}")
    stem = re.sub(r"[^0-9A-Za-z가-힣_.-]+", "-", Path(raw).stem).strip("-_.")
    stem = stem[:100] or f"document-{index}"
    return f"{stem}{suffix}"


def set_request_id(value: str) -> Token[str | None]:
    return _REQUEST_ID.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _REQUEST_ID.reset(token)


def current_request_id() -> str | None:
    return _REQUEST_ID.get()
