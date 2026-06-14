from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
TEST_TMP_ROOT = WORKSPACE_DIR / "test_output" / "test_pipeline_tmp"
sys.path.insert(0, str(PROJECT_DIR))

from packer.chunking import (  # noqa: E402
    STRATEGY_HEADINGS,
    STRATEGY_TOKENS,
    Chunk,
    chunk_document,
)
from packer.pipeline import (  # noqa: E402
    DocumentChunkPreview,
    ProgressEvent,
    chunking_guidance,
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

    def test_medium_bundling_writes_overview_and_guidance(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "a.txt").write_text("Alpha content.", encoding="utf-8")
            (source / "b.txt").write_text("Bravo content.", encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="chatgpt",
                mode="balanced",
                bundling_mode="medium",
                destination="chatgpt_enterprise",
            )
            overview = result.export_dir / "00_CORPUS_OVERVIEW.md"
            self.assertTrue(overview.exists())
            overview_text = overview.read_text(encoding="utf-8")
            self.assertIn("Corpus Overview", overview_text)
            # Manifest accounting stays consistent.
            self.assertEqual(result.failed_count, 0)
            self.assertEqual(result.processed_count, 2)
            # Destination guidance lands in the instruction file.
            instr_text = result.instruction_path.read_text(encoding="utf-8")
            self.assertIn("Packaging guidance for this destination", instr_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_greedy_default_writes_no_overview_or_guidance(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "a.txt").write_text("Alpha content.", encoding="utf-8")

            result = run_packaging_job(source, output, target="chatgpt", mode="balanced")
            self.assertFalse((result.export_dir / "00_CORPUS_OVERVIEW.md").exists())
            instr_text = result.instruction_path.read_text(encoding="utf-8")
            self.assertNotIn("Packaging guidance for this destination", instr_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

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

    def test_cowork_server_script_survives_hostile_project_name(self) -> None:
        import ast

        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "doc.txt").write_text("Some content.", encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                project_name='evil """ name \\ with "quotes"',
                target="cowork",
                mode="balanced",
            )

            server_path = result.export_dir / "mcp_server" / "server.py"
            ast.parse(server_path.read_text(encoding="utf-8"))
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

    def test_heading_strategy_chunk_selection_round_trip(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            text = (
                "## Keep\n\nKeep this section.\n\n"
                "## Drop\n\nDrop this section entirely.\n"
            )
            (source / "doc.md").write_text(text, encoding="utf-8")

            files = scan_directory(source, (".md",), ())
            preview = preview_document_chunks(
                files[0], source, 1000, STRATEGY_HEADINGS, 2
            )
            self.assertEqual(len(preview.chunks), 2)
            self.assertEqual(preview.chunks[0].first_heading, "Keep")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_selections={"doc.md": [1]},
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_heading_level=2,
            )
            bundle_text = result.bundle_paths[0].read_text(encoding="utf-8")
            self.assertIn("Keep this section.", bundle_text)
            self.assertNotIn("Drop this section entirely.", bundle_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rag_export_honors_chunk_settings(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "doc.md").write_text(
                "## One\n\nFirst section.\n\n## Two\n\nSecond section.\n",
                encoding="utf-8",
            )

            result = run_packaging_job(
                source,
                output,
                target="rag",
                mode="balanced",
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
            )
            chunks_path = result.export_dir / "rag_ready" / "chunks.jsonl"
            lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("## One", lines[0])
            self.assertIn("## Two", lines[1])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _heading_path_doc(self) -> str:
        long_body = " ".join(["remove the bolt"] * 60)
        return f"# Manual\n\n## Transmission\n\n{long_body}\n"

    def _run_heading_path_export(self, mode: str):
        root = self.make_tempdir()
        source = root / "source"
        output = root / "output"
        source.mkdir()
        (source / "doc.md").write_text(self._heading_path_doc(), encoding="utf-8")
        result = run_packaging_job(
            source,
            output,
            target="rag",
            mode="balanced",
            chunk_token_budget=40,
            chunk_strategy=STRATEGY_HEADINGS,
            chunk_heading_path_mode=mode,
        )
        lines = (
            (result.export_dir / "rag_ready" / "chunks.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        records = [json.loads(line) for line in lines]
        return root, records

    def test_rag_heading_path_off_adds_no_field(self) -> None:
        root, records = self._run_heading_path_export("off")
        try:
            self.assertTrue(len(records) > 1)
            self.assertTrue(all("heading_path" not in r for r in records))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rag_heading_path_metadata_adds_field_without_touching_text(self) -> None:
        root, records = self._run_heading_path_export("metadata")
        try:
            tail = records[-1]
            self.assertEqual(tail["heading_path"], ["Manual", "Transmission"])
            self.assertFalse(tail["text"].startswith("Manual > Transmission"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rag_heading_path_prefix_folds_into_text(self) -> None:
        root, records = self._run_heading_path_export("prefix")
        try:
            tail = records[-1]
            self.assertTrue(tail["text"].startswith("Manual > Transmission\n\n"))
            self.assertNotIn("heading_path", tail)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rag_heading_path_both_does_each(self) -> None:
        root, records = self._run_heading_path_export("both")
        try:
            tail = records[-1]
            self.assertEqual(tail["heading_path"], ["Manual", "Transmission"])
            self.assertTrue(tail["text"].startswith("Manual > Transmission\n\n"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rag_export_applies_chunk_overlap(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "doc.md").write_text(
                "## One\n\nFirst section.\n\n## Two\n\nSecond section.\n",
                encoding="utf-8",
            )

            result = run_packaging_job(
                source,
                output,
                target="rag",
                mode="balanced",
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_overlap_tokens=5,
            )
            chunks_path = result.export_dir / "rag_ready" / "chunks.jsonl"
            lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            first = json.loads(lines[0])
            second = json.loads(lines[1])
            self.assertEqual(first["text"], "## One\n\nFirst section.")
            self.assertIn("First section.", second["text"])
            self.assertTrue(second["text"].endswith("Second section."))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rag_export_merges_undersized_chunks(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "doc.md").write_text(
                "## A\n\ntiny\n\n## B\n\nA longer section with several words in it.\n",
                encoding="utf-8",
            )

            result = run_packaging_job(
                source,
                output,
                target="rag",
                mode="balanced",
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_min_tokens=20,
            )
            chunks_path = result.export_dir / "rag_ready" / "chunks.jsonl"
            lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("tiny", lines[0])
            self.assertIn("longer section", lines[0])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rag_export_splits_oversize_lines_at_sentences(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            long_line = " ".join(["A sentence about spare parts and torque."] * 30)
            (source / "doc.md").write_text(long_line + "\n", encoding="utf-8")

            default = run_packaging_job(
                source,
                output,
                target="rag",
                mode="balanced",
                chunk_token_budget=50,
            )
            default_lines = (
                (default.export_dir / "rag_ready" / "chunks.jsonl")
                .read_text(encoding="utf-8")
                .strip()
                .splitlines()
            )
            self.assertEqual(len(default_lines), 1)
            self.assertGreater(json.loads(default_lines[0])["token_estimate"], 50)

            split = run_packaging_job(
                source,
                output,
                target="rag",
                mode="balanced",
                chunk_token_budget=50,
                chunk_split_sentences=True,
            )
            split_lines = (
                (split.export_dir / "rag_ready" / "chunks.jsonl")
                .read_text(encoding="utf-8")
                .strip()
                .splitlines()
            )
            self.assertGreater(len(split_lines), 1)
            for line in split_lines:
                self.assertLessEqual(json.loads(line)["token_estimate"], 50)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rag_export_keeps_code_fences_whole_when_fence_aware(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            filler = " ".join(["filler"] * 25)
            code = " ".join(["code"] * 20)
            (source / "doc.md").write_text(
                f"{filler}\n\n```python\n{code}\n\n{code}\n```\n\n{filler}\n",
                encoding="utf-8",
            )

            def fence_marker_counts(result) -> list:
                lines = (
                    (result.export_dir / "rag_ready" / "chunks.jsonl")
                    .read_text(encoding="utf-8")
                    .strip()
                    .splitlines()
                )
                return [
                    sum(
                        1
                        for text_line in json.loads(line)["text"].split("\n")
                        if text_line.strip().startswith("```")
                    )
                    for line in lines
                ]

            broken = run_packaging_job(
                source,
                output,
                target="rag",
                mode="balanced",
                chunk_token_budget=30,
            )
            self.assertTrue(any(count % 2 for count in fence_marker_counts(broken)))

            kept = run_packaging_job(
                source,
                output,
                target="rag",
                mode="balanced",
                chunk_token_budget=30,
                chunk_fence_aware=True,
            )
            counts = fence_marker_counts(kept)
            self.assertGreater(len(counts), 1)
            self.assertTrue(all(count % 2 == 0 for count in counts))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_chunk_selection_uses_merged_boundaries(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "doc.md").write_text(
                "## A\n\ntiny\n\n## B\n\nA longer section with several words in it.\n",
                encoding="utf-8",
            )

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_selections={"doc.md": [1]},
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_min_tokens=20,
            )
            bundle_text = result.bundle_paths[0].read_text(encoding="utf-8")
            self.assertIn("tiny", bundle_text)
            self.assertIn("longer section", bundle_text)
            manifest_text = result.manifest_paths["markdown"].read_text(encoding="utf-8")
            self.assertNotIn("Partial content", manifest_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ChunkRuleTests(unittest.TestCase):
    def make_tempdir(self) -> Path:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        path = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        return path

    RECORD = (
        "## url\n\nhttps://example.com/case\n\n"
        "## summary\n\nThe storm damaged the hall.\n\n"
        "## letter_html\n\n<p>html copy</p>\n"
    )

    def test_heading_rules_trim_matching_chunks_corpus_wide(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "a.md").write_text(self.RECORD, encoding="utf-8")
            (source / "b.md").write_text(self.RECORD, encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_exclude_headings=["url", "*_html"],
            )
            bundle_text = result.bundle_paths[0].read_text(encoding="utf-8")
            self.assertIn("The storm damaged the hall.", bundle_text)
            self.assertNotIn("https://example.com/case", bundle_text)
            self.assertNotIn("html copy", bundle_text)
            manifest_text = result.manifest_paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("corpus heading rules", manifest_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_explicit_selection_overrides_rules(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "a.md").write_text(self.RECORD, encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_selections={"a.md": [1, 2, 3]},
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_exclude_headings=["url", "*_html"],
            )
            bundle_text = result.bundle_paths[0].read_text(encoding="utf-8")
            self.assertIn("https://example.com/case", bundle_text)
            self.assertIn("html copy", bundle_text)
            self.assertTrue(
                any("matched no chunks" in w for w in result.warnings),
                result.warnings,
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_all_chunks_matching_rules_skips_document(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "meta.md").write_text(
                "## url\n\nhttps://example.com\n", encoding="utf-8"
            )
            (source / "keep.md").write_text(
                "## summary\n\nKeep me.\n", encoding="utf-8"
            )

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_exclude_headings=["url"],
            )
            self.assertEqual(result.skipped_count, 1)
            bundle_text = result.bundle_paths[0].read_text(encoding="utf-8")
            self.assertIn("Keep me.", bundle_text)
            self.assertNotIn("example.com", bundle_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_unmatched_rule_warns_without_failing(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "a.md").write_text("## summary\n\nText.\n", encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_exclude_headings=["no_such_field"],
            )
            self.assertEqual(result.processed_count, 1)
            self.assertTrue(
                any("matched no chunks" in w for w in result.warnings)
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ExcludeFilesTests(unittest.TestCase):
    def make_tempdir(self) -> Path:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        path = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        return path

    def test_exclude_files_drops_matching_paths_from_manifest(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "keep.txt").write_text("Keep me.", encoding="utf-8")
            (source / "drop.txt").write_text("Drop me.", encoding="utf-8")
            (source / "draft_a.md").write_text("Draft A.", encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                exclude_files=["drop.txt", "draft_*"],
            )

            self.assertEqual(result.processed_count, 1)
            manifest_text = result.manifest_paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("keep.txt", manifest_text)
            self.assertNotIn("drop.txt", manifest_text)
            self.assertNotIn("draft_a.md", manifest_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_unmatched_exclude_pattern_warns_without_failing(self) -> None:
        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "keep.txt").write_text("Keep me.", encoding="utf-8")

            result = run_packaging_job(
                source,
                output,
                target="generic",
                mode="lean",
                exclude_files=["missing.txt"],
            )
            self.assertEqual(result.processed_count, 1)
            self.assertTrue(
                any("matched no files" in w for w in result.warnings)
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_profile_exclude_files_drive_export(self) -> None:
        from packer.profiles import Profile

        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "keep.txt").write_text("Keep me.", encoding="utf-8")
            (source / "drop.txt").write_text("Drop me.", encoding="utf-8")

            profile = Profile(
                profile_name="With exclusions",
                exclude_files=["drop.txt"],
            )
            result = run_packaging_job(
                **profile.to_packaging_kwargs(source_dir=source, output_dir=output)
            )
            self.assertEqual(result.processed_count, 1)
            bundle_text = result.bundle_paths[0].read_text(encoding="utf-8")
            self.assertIn("Keep me.", bundle_text)
            self.assertNotIn("Drop me.", bundle_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ProfileDrivenExportTests(unittest.TestCase):
    def make_tempdir(self) -> Path:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        path = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        return path

    def test_profile_chunk_settings_drive_rag_export(self) -> None:
        from packer.profiles import Profile

        root = self.make_tempdir()
        try:
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "doc.md").write_text(
                "## One\n\nFirst section.\n\n## Two\n\nSecond section.\n",
                encoding="utf-8",
            )

            profile = Profile(
                profile_name="RAG with headings",
                target="rag",
                mode="balanced",
                chunk_token_budget=1000,
                chunk_strategy=STRATEGY_HEADINGS,
                chunk_heading_level=2,
            )
            kwargs = profile.to_packaging_kwargs(
                source_dir=source, output_dir=output
            )
            result = run_packaging_job(**kwargs)

            chunks_path = result.export_dir / "rag_ready" / "chunks.jsonl"
            lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("## One", lines[0])
            self.assertIn("## Two", lines[1])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class CorpusHeadingSummaryTests(unittest.TestCase):
    @staticmethod
    def preview(*headings: str, tokens: int = 100) -> DocumentChunkPreview:
        from packer.chunking import ChunkStructure

        chunks = [
            Chunk(
                index=i,
                text="x",
                token_estimate=tokens,
                boundary_reason="section starts at a heading",
                structure=ChunkStructure(
                    headings=(heading,) if heading else (),
                    paragraph_count=1,
                    list_item_count=0,
                    table_row_count=0,
                ),
            )
            for i, heading in enumerate(headings, start=1)
        ]
        return DocumentChunkPreview(status="ok", notes="", chunks=chunks)

    def test_groups_case_insensitively_and_counts_documents(self) -> None:
        from packer.pipeline import corpus_heading_summary

        previews = {
            "a.json": self.preview("url", "summary"),
            "b.json": self.preview("URL"),
        }
        summaries = corpus_heading_summary(previews)
        by_key = {s.heading.lower(): s for s in summaries}
        self.assertEqual(by_key["url"].chunk_count, 2)
        self.assertEqual(by_key["url"].document_count, 2)
        self.assertEqual(by_key["url"].token_estimate, 200)
        self.assertEqual(by_key["summary"].chunk_count, 1)

    def test_sorted_by_token_estimate_descending(self) -> None:
        from packer.pipeline import corpus_heading_summary

        previews = {
            "a.json": self.preview("small", tokens=10),
            "b.json": self.preview("big", "big", tokens=500),
        }
        summaries = corpus_heading_summary(previews)
        self.assertEqual(summaries[0].heading, "big")

    def test_headingless_chunks_group_under_empty_string(self) -> None:
        from packer.pipeline import corpus_heading_summary

        previews = {"a.txt": self.preview("", "", "intro")}
        summaries = corpus_heading_summary(previews)
        unnamed = next(s for s in summaries if not s.heading)
        self.assertEqual(unnamed.chunk_count, 2)


class ChunkingGuidanceTests(unittest.TestCase):
    @staticmethod
    def preview(token_sizes: list[int], headings_per_chunk: int = 0) -> DocumentChunkPreview:
        from packer.chunking import ChunkStructure

        chunks = [
            Chunk(
                index=i,
                text="x",
                token_estimate=tokens,
                boundary_reason="end of document",
                structure=ChunkStructure(
                    headings=tuple("h" for _ in range(headings_per_chunk)),
                    paragraph_count=1,
                    list_item_count=0,
                    table_row_count=0,
                ),
            )
            for i, tokens in enumerate(token_sizes, start=1)
        ]
        return DocumentChunkPreview(status="ok", notes="", chunks=chunks)

    def test_no_chunks_no_tips(self) -> None:
        self.assertEqual(chunking_guidance({}, 800, STRATEGY_TOKENS, "generic"), [])

    def test_over_budget_chunks_produce_tip(self) -> None:
        previews = {"a.md": self.preview([900, 100])}
        tips = chunking_guidance(previews, 800, STRATEGY_TOKENS, "generic")
        self.assertTrue(any("exceed" in tip for tip in tips))

    def test_heading_rich_corpus_suggests_heading_strategy(self) -> None:
        previews = {"a.md": self.preview([100, 100], headings_per_chunk=4)}
        tips = chunking_guidance(previews, 800, STRATEGY_TOKENS, "generic")
        self.assertTrue(any("headings" in tip for tip in tips))
        tips_headings = chunking_guidance(previews, 800, STRATEGY_HEADINGS, "generic")
        self.assertFalse(any("'headings' strategy" in tip for tip in tips_headings))

    def test_tiny_chunks_tip_only_for_heading_strategy(self) -> None:
        previews = {"a.md": self.preview([10, 10, 10, 500])}
        tips = chunking_guidance(previews, 800, STRATEGY_HEADINGS, "generic")
        self.assertTrue(any("under" in tip for tip in tips))

    def test_large_budget_for_rag_produces_tip(self) -> None:
        previews = {"a.md": self.preview([1000, 1200])}
        tips = chunking_guidance(previews, 40_000, STRATEGY_TOKENS, "rag")
        self.assertTrue(any("large for RAG" in tip for tip in tips))

    def test_single_chunk_docs_tip(self) -> None:
        previews = {
            "a.md": self.preview([100]),
            "b.md": self.preview([120]),
            "c.md": self.preview([50, 60]),
        }
        tips = chunking_guidance(previews, 800, STRATEGY_TOKENS, "generic")
        self.assertTrue(any("single" in tip for tip in tips))


if __name__ == "__main__":
    unittest.main()
