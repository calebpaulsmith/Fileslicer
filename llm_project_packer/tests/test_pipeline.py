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
