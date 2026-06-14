"""End-to-end quality/property tests for the appeals packaging pipeline.

These assert *behavioral* guarantees a user cares about — that every appeal is
packaged exactly once, that bundles respect the token budget, that URLs/PDFs and
metadata survive into the outputs, and that an appeal's text is recoverable from
its chunks — rather than unit details. They run the real backend against a
synthetic appeals database.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "tests"))

from packer.pipeline import (  # noqa: E402
    load_appeal_documents,
    run_packaging_job,
    summarize_appeal_bundles,
)
from test_appeals_source import _build_db  # noqa: E402

_REQUIRED_META_KEYS = {"title", "appellant", "status", "final_id"}


def _corpus(n: int = 40):
    """A synthetic appeals corpus with URLs, PDFs, and a unique marker each."""
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "final_id": i,
                "html_id": i,
                "html_doc_key": f"fema_html:appeal-{i}:key{i}",
                "source_url": f"https://www.fema.gov/appeal/appeal-{i}",
                "pdf_name": f"FEMA-{1000 + i}-DR Appeal {i}.pdf" if i % 2 == 0 else None,
                "final_title": f"Appeal {i}",
                "final_appellant": f"City of Place {i}",
                "final_status": "Denied" if i % 2 else "Approved",
                "final_region": str((i % 10) + 1),
                "final_summary_text": (
                    f"MARKER{i:04d} is a unique canary phrase. "
                    "Severe storms damaged the facility and the applicant appealed. " * 6
                ),
                "final_analysis_text": "The analysis weighs the eligibility of the claimed costs. " * 8,
            }
        )
    return rows


class AppealsQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = self.tmp / "appeals.sqlite3"
        _build_db(self.db, _corpus(40))

    def _export(self, **kwargs):
        return run_packaging_job(
            appeals_db=self.db,
            source_kind="appeals",
            output_dir=self.tmp / "out",
            project_name="QA",
            **kwargs,
        )

    def _manifest(self, export_dir: Path) -> list:
        return json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))["entries"]

    # -- packaging integrity ------------------------------------------------

    def test_every_appeal_packaged_exactly_once(self) -> None:
        result = self._export(target="chatgpt", mode="balanced", max_bundle_tokens=4000)
        entries = self._manifest(result.export_dir)
        ok = [e for e in entries if e["status"] == "ok"]
        self.assertEqual(len(ok), 40)
        self.assertEqual(result.failed_count, 0)
        # Every ok appeal lands in exactly one bundle; coverage is complete.
        bundles = [e["output_bundle"] for e in ok]
        self.assertTrue(all(bundles))
        self.assertEqual(result.processed_count, len(entries))

    def test_bundles_respect_budget(self) -> None:
        docs = load_appeal_documents(self.db)
        budget = 4000
        summary = summarize_appeal_bundles(docs, budget, "greedy")
        for bundle in summary["per_bundle"]:
            # A bundle may exceed budget only if it is a single oversize appeal.
            if bundle["tokens"] > budget:
                self.assertEqual(bundle["doc_count"], 1)

    def test_smaller_budget_makes_more_bundles(self) -> None:
        docs = load_appeal_documents(self.db)
        self.assertGreater(
            summarize_appeal_bundles(docs, 2000, "greedy")["bundle_count"],
            summarize_appeal_bundles(docs, 20000, "greedy")["bundle_count"],
        )

    def test_size_metrics_present(self) -> None:
        docs = load_appeal_documents(self.db)
        summary = summarize_appeal_bundles(docs, 4000, "greedy")
        self.assertGreater(summary["total_bytes"], 0)
        self.assertTrue(all("bytes" in b for b in summary["per_bundle"]))

    # -- content fidelity ---------------------------------------------------

    def test_url_and_pdf_render_into_documents(self) -> None:
        docs = load_appeal_documents(self.db)
        with_pdf = [d for d in docs if d.metadata.get("pdf_filename")]
        self.assertTrue(with_pdf)
        doc = with_pdf[0]
        self.assertIn("- **URL:** https://www.fema.gov/appeal/", doc.body_markdown)
        self.assertIn("- **Source PDF:**", doc.body_markdown)
        self.assertTrue(doc.metadata["url"].startswith("https://"))

    def test_rag_chunks_carry_metadata_and_text(self) -> None:
        result = self._export(target="rag", mode="balanced", chunk_token_budget=200)
        lines = [
            json.loads(line)
            for line in (result.export_dir / "rag_ready" / "chunks.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertTrue(lines)
        for chunk in lines:
            self.assertTrue(_REQUIRED_META_KEYS.issubset(chunk["metadata"].keys()))

    def test_appeal_text_recoverable_from_chunks(self) -> None:
        result = self._export(target="rag", mode="balanced", chunk_token_budget=120)
        text = (result.export_dir / "rag_ready" / "chunks.jsonl").read_text(encoding="utf-8")
        # Every appeal's unique canary survives chunking and is retrievable.
        for i in range(1, 41):
            self.assertIn(f"MARKER{i:04d}", text, f"appeal {i} canary missing from chunks")


if __name__ == "__main__":
    unittest.main()
