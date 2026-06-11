from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
TEST_TMP_ROOT = WORKSPACE_DIR / "test_output" / "test_pipeline_tmp"
sys.path.insert(0, str(PROJECT_DIR))

from packer.chunking import chunk_document  # noqa: E402
from packer.pipeline import (  # noqa: E402
    ProgressEvent,
    preview_document_chunks,
    run_packaging_job,
)
from packer.scanner import scan_directory  # noqa: E402


def _multi_chunk_text() -> str:
    return "\n\n".join(
        " ".join([word] * 30) for word in ("alpha", "bravo", "charlie")
    )


class PipelineTests(unittest.TestCase):
    def make_tempdir(self) -> Path:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        path = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        return path

    def test_run_packaging_job_returns_structured_result(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "notes.txt").write_text("Torque spec is 10 Nm.", encoding="utf-8")
            (source / "unsupported.xyz").write_text("unsupported", encoding="utf-8")

            events: list[ProgressEvent] = []
            result = run_packaging_job(
                source,
                output,
                target="chatgpt",
                mode="balanced",
                progress_callback=events.append,
            )

            self.assertTrue(result.export_dir.exists())
            self.assertTrue(result.instruction_path and result.instruction_path.exists())
            self.assertTrue(result.manifest_paths["markdown"].exists())
            self.assertEqual(len(result.bundle_paths), 1)
            self.assertEqual(result.processed_count, 2)
            self.assertEqual(result.failed_count, 0)
            self.assertEqual(result.skipped_count, 1)
            self.assertGreater(result.total_token_estimate, 0)
            self.assertIsNone(result.zip_path)
            self.assertTrue(any(event.kind == "complete" for event in events))

            manifest_text = result.manifest_paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("unsupported.xyz", manifest_text)
            self.assertIn("skipped", manifest_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_included_files_limits_packaging_scope(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "keep.txt").write_text("Keep me.", encoding="utf-8")
            (source / "drop.txt").write_text("Drop me.", encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                included_files=["keep.txt"],
            )

            self.assertEqual(result.processed_count, 1)
            manifest_text = result.manifest_paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("keep.txt", manifest_text)
            self.assertNotIn("drop.txt", manifest_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_chunk_selection_trims_document_content(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            text = _multi_chunk_text()
            (source / "doc.txt").write_text(text, encoding="utf-8")

            budget = 10
            chunks = chunk_document(text, budget)
            self.assertGreaterEqual(len(chunks), 2)

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_selections={"doc.txt": [1]},
                chunk_token_budget=budget,
            )

            self.assertEqual(result.skipped_count, 0)
            bundle_text = result.bundle_paths[0].read_text(encoding="utf-8")
            self.assertIn(chunks[0].text, bundle_text)
            self.assertNotIn(chunks[1].text, bundle_text)
            manifest_text = result.manifest_paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("Partial content", manifest_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_empty_chunk_selection_marks_document_skipped(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "keep.txt").write_text("Keep me.", encoding="utf-8")
            (source / "drop.txt").write_text(_multi_chunk_text(), encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_selections={"drop.txt": []},
                chunk_token_budget=10,
            )

            self.assertEqual(result.skipped_count, 1)
            self.assertTrue(any("deselected" in w for w in result.warnings))
            bundle_text = result.bundle_paths[0].read_text(encoding="utf-8")
            self.assertIn("keep.txt", bundle_text)
            self.assertNotIn("alpha", bundle_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_chunk_selection_for_unknown_file_warns(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "doc.txt").write_text("Some content.", encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_selections={"missing.txt": [1]},
                chunk_token_budget=10,
            )

            self.assertEqual(result.processed_count, 1)
            self.assertTrue(
                any("Chunk selection ignored" in w for w in result.warnings)
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_preview_document_chunks_matches_export_chunking(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            source.mkdir()
            text = _multi_chunk_text()
            (source / "doc.txt").write_text(text, encoding="utf-8")

            files = scan_directory(source, (".txt",), ())
            self.assertEqual(len(files), 1)

            budget = 10
            preview = preview_document_chunks(files[0], source, budget)
            self.assertEqual(preview.status, "ok")
            self.assertGreaterEqual(len(preview.chunks), 2)
            self.assertEqual(
                [chunk.text for chunk in preview.chunks],
                [chunk.text for chunk in chunk_document(text, budget)],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
