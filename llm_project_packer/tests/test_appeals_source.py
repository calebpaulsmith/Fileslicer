from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer import appeals_source  # noqa: E402
from packer.appeals_source import load_appeal_docs  # noqa: E402
from packer.manifest import Manifest  # noqa: E402
from packer.pipeline import (  # noqa: E402
    load_appeal_documents,
    run_packaging_job,
    summarize_appeal_bundles,
    summarize_appeal_chunks,
)

_FINAL_COLUMNS = (
    "final_id",
    "html_id",
    "final_title",
    "final_appellant",
    "final_recipient",
    "final_pa_id",
    "final_disaster_number_raw",
    "final_disaster_number_norm",
    "final_decision_signed_date",
    "final_declaration_date",
    "final_pw_gmp_compact",
    "final_gmp_number",
    "final_pw_number",
    "final_region",
    "final_status",
    "final_summary_text",
    "final_analysis_text",
    "final_conclusion_text",
    "final_letter_text",
    "final_headnotes_text",
    "final_authorities_text",
    "final_footnotes_text",
    "final_body_text",
)


def _build_db(path: Path, appeals, citations=None, *, with_citation_tables=True) -> None:
    """Create a minimal pa_rag-shaped appeals database.

    ``appeals`` is a list of dicts (a subset of ``_FINAL_COLUMNS`` plus an
    optional ``html_doc_key``). ``citations`` maps html_doc_key -> list of
    canonical labels.
    """
    conn = sqlite3.connect(path)
    cols_ddl = ", ".join(f"{c} {'INTEGER' if c.endswith('_id') else 'TEXT'}" for c in _FINAL_COLUMNS)
    conn.execute(f"CREATE TABLE final_appeal_authority ({cols_ddl})")
    conn.execute("CREATE TABLE src_html_appeal (html_id INTEGER, html_doc_key TEXT)")
    if with_citation_tables:
        conn.execute(
            "CREATE TABLE document_citation (parent_doc_key TEXT, citation_id TEXT)"
        )
        conn.execute(
            "CREATE TABLE citation_reference (citation_id TEXT, canonical_label TEXT)"
        )
    for appeal in appeals:
        values = [appeal.get(c) for c in _FINAL_COLUMNS]
        placeholders = ", ".join(["?"] * len(_FINAL_COLUMNS))
        conn.execute(
            f"INSERT INTO final_appeal_authority ({', '.join(_FINAL_COLUMNS)}) "
            f"VALUES ({placeholders})",
            values,
        )
        key = appeal.get("html_doc_key")
        if key:
            conn.execute(
                "INSERT INTO src_html_appeal (html_id, html_doc_key) VALUES (?, ?)",
                (appeal.get("html_id"), key),
            )
    if with_citation_tables and citations:
        cid = 0
        for key, labels in citations.items():
            for label in labels:
                cid += 1
                ref = f"cit:{cid}"
                conn.execute(
                    "INSERT INTO citation_reference (citation_id, canonical_label) VALUES (?, ?)",
                    (ref, label),
                )
                conn.execute(
                    "INSERT INTO document_citation (parent_doc_key, citation_id) VALUES (?, ?)",
                    (key, ref),
                )
    conn.commit()
    conn.close()


class AppealsSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "appeals.sqlite3"
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _load(self, appeals, citations=None, **kwargs):
        _build_db(self.db, appeals, citations, **kwargs)
        manifest = Manifest(project_name="t", target="chatgpt", mode="balanced")
        warnings: list = []
        errors: list = []
        docs = load_appeal_docs(
            self.db, manifest, warnings=warnings, errors=errors, emit=lambda *a: None
        )
        return docs, manifest, warnings, errors

    def test_renders_one_doc_per_appeal_with_overview(self) -> None:
        docs, manifest, _, _ = self._load(
            [
                {
                    "final_id": 1,
                    "html_id": 10,
                    "html_doc_key": "fema_html:alpha:abc",
                    "final_title": "Alpha Appeal",
                    "final_appellant": "City of Alpha",
                    "final_pa_id": "001-12345",
                    "final_disaster_number_raw": "4431",
                    "final_disaster_number_norm": "4431",
                    "final_region": "9",
                    "final_status": "Denied",
                    "final_summary_text": "A short summary paragraph.",
                    "final_analysis_text": "The analysis section text.",
                },
                {
                    "final_id": 2,
                    "html_id": 11,
                    "html_doc_key": "fema_html:beta:def",
                    "final_title": "Beta Appeal",
                    "final_body_text": "Only body text here.",
                },
            ],
            citations={"fema_html:alpha:abc": ["44 C.F.R. 206.226(a)", "Stafford Act 406"]},
        )
        self.assertEqual(len(docs), 2)
        self.assertEqual([d.entry.doc_id for d in docs], ["DOC_0001", "DOC_0002"])
        alpha = docs[0]
        self.assertIn("# Alpha Appeal", alpha.body_markdown)
        self.assertIn("## Appeal Overview", alpha.body_markdown)
        self.assertIn("**Appellant:** City of Alpha", alpha.body_markdown)
        self.assertIn("**Status:** Denied", alpha.body_markdown)
        self.assertIn("## Summary", alpha.body_markdown)
        self.assertIn("## Analysis", alpha.body_markdown)
        # Citations from the join show up in the overview block.
        self.assertIn("44 C.F.R. 206.226(a)", alpha.body_markdown)
        self.assertIn("Stafford Act 406", alpha.body_markdown)
        # The body-only appeal falls back to a Decision section.
        self.assertIn("## Decision", docs[1].body_markdown)
        self.assertIn("Only body text here.", docs[1].body_markdown)
        # Manifest accounting is consistent.
        self.assertEqual(len(manifest.entries), 2)
        self.assertTrue(all(e.status == "ok" for e in manifest.entries))
        self.assertTrue(all(e.token_estimate > 0 for e in manifest.entries))

    def test_stable_ids_ordered_by_final_id(self) -> None:
        docs, _, _, _ = self._load(
            [
                {"final_id": 5, "final_title": "Fifth"},
                {"final_id": 2, "final_title": "Second"},
            ]
        )
        # Ordered by final_id, so Second (2) gets DOC_0001.
        self.assertIn("# Second", docs[0].body_markdown)
        self.assertIn("# Fifth", docs[1].body_markdown)

    def test_no_citation_tables_renders_none_extracted(self) -> None:
        docs, _, _, _ = self._load(
            [{"final_id": 1, "final_title": "Solo", "final_summary_text": "x"}],
            with_citation_tables=False,
        )
        self.assertIn("**Cited authorities:** none extracted", docs[0].body_markdown)

    def test_bad_row_is_isolated(self) -> None:
        original = appeals_source._render_appeal_markdown

        def flaky(row, citations):
            if row["final_id"] == 1:
                raise ValueError("boom")
            return original(row, citations)

        appeals_source._render_appeal_markdown = flaky
        try:
            docs, manifest, _, errors = self._load(
                [
                    {"final_id": 1, "final_title": "Bad"},
                    {"final_id": 2, "final_title": "Good", "final_summary_text": "ok"},
                ]
            )
        finally:
            appeals_source._render_appeal_markdown = original
        # One good doc converted, one failed entry recorded, run continued.
        self.assertEqual(len(docs), 1)
        self.assertIn("# Good", docs[0].body_markdown)
        statuses = sorted(e.status for e in manifest.entries)
        self.assertEqual(statuses, ["failed", "ok"])
        self.assertTrue(errors)

    def test_missing_table_is_fatal(self) -> None:
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
        conn.commit()
        conn.close()
        manifest = Manifest(project_name="t", target="chatgpt", mode="balanced")
        with self.assertRaises(ValueError):
            load_appeal_docs(
                self.db, manifest, warnings=[], errors=[], emit=lambda *a: None
            )

    def test_end_to_end_rag_export_has_chunks(self) -> None:
        _build_db(
            self.db,
            [
                {
                    "final_id": 1,
                    "final_title": "Alpha",
                    "final_summary_text": "Summary text.",
                    "final_analysis_text": "Analysis text.",
                }
            ],
        )
        out = self.tmp / "out"
        result = run_packaging_job(
            appeals_db=self.db,
            source_kind="appeals",
            output_dir=out,
            project_name="Appeals",
            target="rag",
            mode="balanced",
        )
        self.assertEqual(result.processed_count, 1)
        self.assertEqual(result.failed_count, 0)
        chunks = result.export_dir / "rag_ready" / "chunks.jsonl"
        self.assertTrue(chunks.exists())
        first = json.loads(chunks.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(first["doc_id"], "DOC_0001")
        # Appeal chunks carry structured metadata for filtering/citation.
        self.assertIn("metadata", first)
        self.assertEqual(first["metadata"]["title"], "Alpha")

    def test_metadata_includes_citations_and_fields(self) -> None:
        docs, _, _, _ = self._load(
            [
                {
                    "final_id": 7,
                    "html_id": 7,
                    "html_doc_key": "k7",
                    "final_title": "Cited Appeal",
                    "final_appellant": "County Y",
                    "final_status": "Denied",
                    "final_summary_text": "Body.",
                }
            ],
            citations={"k7": ["44 C.F.R. 206.226(a)", "Stafford Act 406"]},
        )
        meta = docs[0].metadata
        self.assertEqual(meta["appellant"], "County Y")
        self.assertEqual(meta["status"], "Denied")
        self.assertIn("44 C.F.R. 206.226(a)", meta["citations"])


class AppealPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "appeals.sqlite3"
        self.addCleanup(shutil.rmtree, self.tmp, True)
        rows = [
            {
                "final_id": i,
                "final_title": f"Appeal {i}",
                "final_summary_text": "Severe storms damaged the road. " * 20,
            }
            for i in range(1, 13)
        ]
        _build_db(self.db, rows)

    def test_load_appeal_documents_renders_without_export(self) -> None:
        docs = load_appeal_documents(self.db)
        self.assertEqual(len(docs), 12)
        self.assertTrue(all(d.token_estimate > 0 for d in docs))

    def test_bundle_summary_responds_to_budget(self) -> None:
        docs = load_appeal_documents(self.db)
        small = summarize_appeal_bundles(docs, 400, "greedy")
        large = summarize_appeal_bundles(docs, 5000, "greedy")
        # A smaller budget yields more bundles; totals are stable.
        self.assertGreater(small["bundle_count"], large["bundle_count"])
        self.assertEqual(small["total_tokens"], large["total_tokens"])
        self.assertEqual(len(small["per_bundle"]), small["bundle_count"])

    def test_chunk_summary_reports_sizes(self) -> None:
        docs = load_appeal_documents(self.db)
        summary = summarize_appeal_chunks(docs, 120, "tokens")
        self.assertEqual(summary["doc_count"], 12)
        self.assertGreater(summary["chunk_count"], 0)
        self.assertEqual(len(summary["sizes"]), summary["chunk_count"])
        self.assertLessEqual(summary["smallest"], summary["largest"])


if __name__ == "__main__":
    unittest.main()
