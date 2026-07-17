from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2.course_pack_artifacts import artifact_name, artifact_preview, export_concept_map, save_artifact
from v2.io_utils import atomic_write_json
from v2.uploads import save_uploaded_files


class _Upload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = io.BytesIO(content)
        self.closed = False

    async def read(self, size: int) -> bytes:
        return self._content.read(size)

    async def close(self) -> None:
        self.closed = True


class AtomicStorageTest(unittest.TestCase):
    def test_atomic_json_replaces_content_without_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "state.json"

            atomic_write_json(path, {"version": 1})
            atomic_write_json(path, {"version": 2, "ready": True})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 2, "ready": True})
            self.assertEqual(list(path.parent.glob(".*.tmp")), [])

    def test_course_pack_artifacts_are_saved_and_previewed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            path = save_artifact(root, "answers/result.json", {"answer": "grounded"})

            preview = artifact_preview(path, include_content=True)

            self.assertEqual(preview["data"], {"answer": "grounded"})
            self.assertTrue(preview["ready"])
            self.assertGreater(preview["size_bytes"], 2)
            self.assertFalse(artifact_preview(save_artifact(root, "empty.json", {}), include_content=False)["ready"])
            self.assertEqual(artifact_name("BPE와 OOV 관계는?"), "BPE와-OOV-관계는")

    def test_concept_map_export_limits_content_and_uses_coursebee_brand(self) -> None:
        graph = {
            "nodes": [
                {"id": "BPE", "label": "BPE", "type": "concept"},
                {"id": "OOV", "label": "OOV", "type": "concept"},
                {"id": "extra", "label": "extra", "type": "concept"},
            ],
            "edges": [
                {"source": "BPE", "target": "OOV", "relation": "reduces"},
                {"source": "OOV", "target": "extra", "relation": "related_to"},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            exported = export_concept_map(graph, Path(temporary_dir), max_nodes=2, max_edges=1)
            html = Path(exported["html_path"]).read_text(encoding="utf-8")

            self.assertEqual(exported["exported_node_count"], 2)
            self.assertEqual(exported["exported_edge_count"], 1)
            self.assertTrue(exported["warnings"])
            self.assertIn("CourseBee Concept Map", html)


class UploadStorageTest(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_upload_names_are_preserved_and_disambiguated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            first = _Upload("notes.txt", b"first")
            second = _Upload("notes.txt", b"second")

            paths = await save_uploaded_files([first, second], upload_root=Path(temporary_dir))

            self.assertEqual([Path(path).name for path in paths], ["notes.txt", "notes-2.txt"])
            self.assertEqual([Path(path).read_bytes() for path in paths], [b"first", b"second"])
            self.assertTrue(first.closed)
            self.assertTrue(second.closed)

    async def test_spoofed_pdf_is_rejected_and_cleaned_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            upload = _Upload("lecture.pdf", b"this is not a PDF")

            with self.assertRaisesRegex(ValueError, "valid PDF header"):
                await save_uploaded_files([upload], upload_root=Path(temporary_dir))

            self.assertEqual(list(Path(temporary_dir).iterdir()), [])
            self.assertTrue(upload.closed)

    async def test_total_batch_limit_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            uploads = [_Upload("one.txt", b"1234"), _Upload("two.txt", b"5678")]

            with patch("v2.uploads.MAX_UPLOAD_BATCH_BYTES", 6):
                with self.assertRaisesRegex(ValueError, "total limit"):
                    await save_uploaded_files(uploads, upload_root=Path(temporary_dir))

            self.assertEqual(list(Path(temporary_dir).iterdir()), [])
            self.assertTrue(all(upload.closed for upload in uploads))


if __name__ == "__main__":
    unittest.main()
