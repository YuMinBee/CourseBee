from __future__ import annotations

import json
from pathlib import Path

from v2.documents import chunk_from_dict
from v2.schemas import Chunk


def course_pack_dir(pack_id: str, output_root: str = "outputs") -> Path:
    return Path(output_root) / "course_packs" / pack_id


def load_course_pack(pack_id: str, output_root: str = "outputs") -> dict:
    path = course_pack_dir(pack_id, output_root=output_root) / "course_pack.json"
    if not path.exists():
        return {"pack_id": pack_id, "warnings": [f"course pack not found: {pack_id}"]}
    return json.loads(path.read_text(encoding="utf-8"))


def list_course_packs(output_root: str = "outputs") -> list[dict]:
    root = Path(output_root) / "course_packs"
    if not root.exists():
        return []
    packs: list[dict] = []
    for path in root.glob("*/course_pack.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload["updated_at"] = path.stat().st_mtime
        packs.append(payload)
    return sorted(packs, key=lambda item: item.get("updated_at", 0), reverse=True)


def load_course_pack_chunks(pack_id: str, output_root: str = "outputs") -> list[Chunk]:
    path = course_pack_dir(pack_id, output_root=output_root) / "chunks.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks = [chunk_from_dict(item) for item in data.get("chunks", [])]
    for chunk in chunks:
        chunk.metadata.setdefault("pack_id", pack_id)
    return chunks
