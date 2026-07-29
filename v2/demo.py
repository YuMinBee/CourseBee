from __future__ import annotations

from pathlib import Path

from v2.course_packs import create_course_pack, load_course_pack
from v2.runtime import DATA_ROOT, DEMO_FIXTURE_ROOT

DEMO_PACK_ID = "pack_enterprise_onboarding_demo"


def ensure_demo_course_pack(output_root: str | Path = DATA_ROOT) -> dict:
    root = str(output_root)
    existing = load_course_pack(DEMO_PACK_ID, output_root=root)
    documents = existing.get("documents") or []
    if (
        existing.get("output_dir")
        and existing.get("chunk_count", 0) >= 6
        and documents
        and all(document.get("title") for document in documents)
    ):
        return existing

    paths = sorted(DEMO_FIXTURE_ROOT.glob("enterprise_*.txt"))
    if not paths:
        return {
            "pack_id": DEMO_PACK_ID,
            "warnings": [f"demo fixtures not found: {DEMO_FIXTURE_ROOT}"],
        }
    return create_course_pack(
        paths=[str(path) for path in paths],
        output_root=root,
        max_chunk_chars=320,
        pack_id=DEMO_PACK_ID,
    )
