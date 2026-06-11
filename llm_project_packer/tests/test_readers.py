from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
TEST_TMP_ROOT = WORKSPACE_DIR / "test_output" / "test_readers_tmp"
sys.path.insert(0, str(PROJECT_DIR))

from packer.readers import ReaderContext, read_file  # noqa: E402
from packer.scanner import ScannedFile  # noqa: E402


class JsonReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _read(self, name: str, content: str):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        scanned = ScannedFile(
            absolute_path=path,
            relative_path=Path(name),
            extension=".json",
            file_type="json",
            size_bytes=path.stat().st_size,
        )
        ctx = ReaderContext(
            source_root=self.root,
            assets_dir=self.root / "assets",
            data_dir=self.root / "data",
        )
        return read_file(scanned, doc_id="DOC_0001", ctx=ctx)

    def test_object_keys_become_headings(self) -> None:
        result = self._read(
            "record.json",
            '{"title": "Wheeling", "summary": "A storm damaged the hall."}',
        )
        self.assertEqual(result.status, "ok")
        self.assertIn("# JSON: record.json", result.markdown)
        self.assertIn("## title", result.markdown)
        self.assertIn("Wheeling", result.markdown)
        self.assertIn("## summary", result.markdown)
        self.assertIn("A storm damaged the hall.", result.markdown)

    def test_nested_objects_get_deeper_headings(self) -> None:
        result = self._read(
            "nested.json",
            '{"brief": {"disaster": "FEMA-1507-DR", "applicant": "Township"}}',
        )
        self.assertIn("## brief", result.markdown)
        self.assertIn("### disaster", result.markdown)
        self.assertIn("FEMA-1507-DR", result.markdown)

    def test_scalar_lists_become_bullets(self) -> None:
        result = self._read(
            "list.json",
            '{"authorities": ["44 CFR 206.223", "Landslide Policy"]}',
        )
        self.assertIn("- 44 CFR 206.223", result.markdown)
        self.assertIn("- Landslide Policy", result.markdown)

    def test_null_and_empty_values_are_explicit(self) -> None:
        result = self._read(
            "sparse.json",
            '{"conclusion": null, "footnotes": [], "flag": true}',
        )
        self.assertIn("(null)", result.markdown)
        self.assertIn("(empty list)", result.markdown)
        self.assertIn("true", result.markdown)

    def test_list_of_objects_uses_item_headings(self) -> None:
        result = self._read(
            "items.json",
            '{"appeals": [{"id": 1}, {"id": 2}]}',
        )
        self.assertIn("### item 1", result.markdown)
        self.assertIn("### item 2", result.markdown)

    def test_invalid_json_fails_without_raising(self) -> None:
        result = self._read("broken.json", "{not valid json")
        self.assertEqual(result.status, "failed")
        self.assertIn("Invalid JSON", result.notes)


if __name__ == "__main__":
    unittest.main()
