from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from v2.runtime import MAX_UPLOAD_BATCH_BYTES, MAX_UPLOAD_BYTES, MAX_UPLOAD_FILES, UPLOAD_ROOT, safe_upload_filename


async def save_uploaded_files(files: list, upload_root: Path = UPLOAD_ROOT) -> list[str]:
    if not files:
        raise ValueError("at least one file is required")
    if len(files) > MAX_UPLOAD_FILES:
        raise ValueError(f"a maximum of {MAX_UPLOAD_FILES} files can be uploaded at once")

    batch_dir = upload_root / f"batch_{uuid4().hex[:12]}"
    batch_dir.mkdir(parents=True, exist_ok=False)
    saved: list[Path] = []
    batch_size = 0
    try:
        for index, upload in enumerate(files, start=1):
            filename = safe_upload_filename(getattr(upload, "filename", None), index=index)
            target = _available_target(batch_dir, filename)
            size = 0
            with target.open("xb") as handle:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    if size == 0:
                        _validate_file_signature(filename, chunk)
                    size += len(chunk)
                    batch_size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise ValueError(f"{filename} exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit")
                    if batch_size > MAX_UPLOAD_BATCH_BYTES:
                        raise ValueError(
                            f"upload batch exceeds the {MAX_UPLOAD_BATCH_BYTES // (1024 * 1024)} MB total limit"
                        )
                    handle.write(chunk)
            if size == 0:
                raise ValueError(f"{filename} is empty")
            saved.append(target)
    except Exception:
        for path in [*saved, *batch_dir.glob("*")]:
            if path.is_file():
                path.unlink(missing_ok=True)
        try:
            batch_dir.rmdir()
        except OSError:
            pass
        raise
    finally:
        for upload in files:
            close = getattr(upload, "close", None)
            if close is None:
                continue
            result = close()
            if hasattr(result, "__await__"):
                await result
    return [str(path) for path in saved]


def _validate_file_signature(filename: str, first_chunk: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and b"%PDF-" not in first_chunk[:1024]:
        raise ValueError(f"{filename} does not contain a valid PDF header")
    if suffix == ".pptx" and not first_chunk.startswith(b"PK\x03\x04"):
        raise ValueError(f"{filename} does not contain a valid PPTX zip header")
    if suffix in {".txt", ".md"} and b"\x00" in first_chunk[:4096]:
        raise ValueError(f"{filename} contains binary data and is not a supported text file")


def _available_target(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 2
    while True:
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
