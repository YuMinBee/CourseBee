from __future__ import annotations

from pathlib import Path

from v2.course_packs import create_course_pack, load_course_pack
from v2.runtime import DATA_ROOT, DEMO_FIXTURE_ROOT

DEMO_PACK_ID = "pack_static_nlp_11week_demo"


def ensure_demo_course_pack(output_root: str | Path = DATA_ROOT) -> dict:
    root = str(output_root)
    existing = load_course_pack(DEMO_PACK_ID, output_root=root)
    if existing.get("output_dir"):
        return existing

    paths = sorted(DEMO_FIXTURE_ROOT.glob("*.txt"))
    if not paths:
        return {
            "pack_id": DEMO_PACK_ID,
            "warnings": [f"demo fixtures not found: {DEMO_FIXTURE_ROOT}"],
        }
    return create_course_pack(
        paths=[str(path) for path in paths],
        output_root=root,
        max_chunk_chars=700,
        pack_id=DEMO_PACK_ID,
    )
