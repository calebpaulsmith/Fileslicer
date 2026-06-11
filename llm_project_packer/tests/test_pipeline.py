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

from packer.pipeline import ProgressEvent, run_packaging_job  # noqa: E402


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

    def test_cowork_target_builds_mcp_server_bundle(self) -> None:
        import sqlite3

        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "torque.txt").write_text(
                "Procedure: tighten bolt to 18 Nm using calibrated torque wrench.",
                encoding="utf-8",
            )
            (source / "wiring.txt").write_text(
                "Wiring diagram references TB-7 ground stud on chassis.",
                encoding="utf-8",
            )

            result = run_packaging_job(
                source,
                output,
                target="cowork",
                mode="balanced",
            )

            self.assertEqual(result.processed_count, 2)
            self.assertEqual(result.failed_count, 0)
            chunks_path = result.export_dir / "rag_ready" / "chunks.jsonl"
            self.assertTrue(chunks_path.exists())

            mcp_dir = result.export_dir / "mcp_server"
            self.assertTrue((mcp_dir / "server.py").exists())
            self.assertTrue((mcp_dir / "index.sqlite").exists())
            self.assertTrue((mcp_dir / "cowork_config.json").exists())
            self.assertTrue((mcp_dir / "requirements.txt").exists())
            self.assertTrue((mcp_dir / "README.md").exists())
            self.assertTrue((result.export_dir / "00_COWORK_MCP_INSTRUCTIONS.md").exists())

            conn = sqlite3.connect(str(mcp_dir / "index.sqlite"))
            try:
                hits = conn.execute(
                    "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ?",
                    ('"torque"',),
                ).fetchall()
            finally:
                conn.close()
            self.assertGreaterEqual(len(hits), 1)

            config_payload = (mcp_dir / "cowork_config.json").read_text(encoding="utf-8")
            self.assertIn("mcpServers", config_payload)
            self.assertIn("server.py", config_payload)
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


if __name__ == "__main__":
    unittest.main()
