from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.bundler import (  # noqa: E402
    Bundle,
    ConvertedDoc,
    make_converted_doc,
    split_doc_at_headings,
    split_into_bundles,
    split_into_bundles_medium,
)
from packer.manifest import ManifestEntry  # noqa: E402


def _doc(index: int) -> ConvertedDoc:
    entry = ManifestEntry(
        doc_id=f"DOC_{index:04d}",
        source_file=f"file_{index}.txt",
        source_path=f"file_{index}.txt",
        original_extension=".txt",
        file_type="text",
        status="ok",
    )
    return make_converted_doc(entry, " ".join(["word"] * 200))


def _doc_with_body(index: int, body: str) -> ConvertedDoc:
    entry = ManifestEntry(
        doc_id=f"DOC_{index:04d}",
        source_file=f"file_{index}.md",
        source_path=f"file_{index}.md",
        original_extension=".md",
        file_type="text",
        status="ok",
    )
    return make_converted_doc(entry, body)


def _bundles(doc_count: int) -> list[Bundle]:
    docs = [_doc(i) for i in range(1, doc_count + 1)]
    return split_into_bundles(docs, max_bundle_tokens=1)


class BundleFilenameTests(unittest.TestCase):
    def test_small_exports_keep_two_digit_prefixes(self) -> None:
        bundles = _bundles(3)
        self.assertEqual(
            [b.filename for b in bundles],
            ["02_BUNDLE_001.md", "03_BUNDLE_002.md", "04_BUNDLE_003.md"],
        )

    def test_two_digit_prefixes_up_to_98_bundles(self) -> None:
        bundles = _bundles(98)
        self.assertEqual(bundles[0].filename, "02_BUNDLE_001.md")
        self.assertEqual(bundles[-1].filename, "99_BUNDLE_098.md")

    def test_prefixes_widen_past_98_bundles(self) -> None:
        bundles = _bundles(99)
        self.assertEqual(bundles[0].filename, "020_BUNDLE_001.md")
        self.assertEqual(bundles[-1].filename, "118_BUNDLE_099.md")

    def test_lexical_order_keeps_instructions_manifest_then_bundles(self) -> None:
        fixed = ["00_GENERIC_INSTRUCTIONS.md", "01_SOURCE_MANIFEST.md"]
        for doc_count in (1, 9, 98, 99, 120, 981):
            bundles = _bundles(doc_count)
            filenames = [b.filename for b in bundles]
            self.assertEqual(len(set(filenames)), doc_count)
            self.assertEqual(
                sorted(fixed + filenames), fixed + filenames,
                f"order broken at {doc_count} bundles",
            )


class MediumBundlingTests(unittest.TestCase):
    def _oversize_doc(self) -> ConvertedDoc:
        words = " ".join(["word"] * 400)
        body = f"## Section One\n\n{words}\n\n## Section Two\n\n{words}\n"
        return _doc_with_body(1, body)

    def test_within_budget_doc_is_unchanged(self) -> None:
        doc = _doc_with_body(1, "## A\n\nshort body\n")
        parts = split_doc_at_headings(doc, target_tokens=10_000)
        self.assertEqual(parts, [doc])

    def test_oversize_doc_splits_at_headings(self) -> None:
        doc = self._oversize_doc()
        # Budget below the whole doc but above each section forces a split.
        parts = split_doc_at_headings(doc, target_tokens=doc.token_estimate // 2)
        self.assertGreater(len(parts), 1)
        self.assertEqual([p.entry.doc_id for p in parts], ["DOC_0001_p01", "DOC_0001_p02"])
        for part in parts:
            self.assertLessEqual(part.token_estimate, doc.token_estimate)
            self.assertIn("part", part.entry.notes.lower())

    def test_oversize_doc_without_headings_kept_whole(self) -> None:
        doc = _doc_with_body(1, " ".join(["word"] * 400))
        parts = split_doc_at_headings(doc, target_tokens=10)
        self.assertEqual(parts, [doc])

    def test_medium_bundles_keep_byte_identical_numbering(self) -> None:
        docs = [_doc(i) for i in range(1, 4)]
        bundles = split_into_bundles_medium(docs, target_tokens=1)
        self.assertEqual(
            [b.filename for b in bundles],
            ["02_BUNDLE_001.md", "03_BUNDLE_002.md", "04_BUNDLE_003.md"],
        )

    def test_medium_splits_oversize_into_extra_bundles(self) -> None:
        doc = self._oversize_doc()
        bundles = split_into_bundles_medium([doc], target_tokens=doc.token_estimate // 2)
        # The single oversize doc becomes >1 in-budget bundle.
        self.assertGreater(len(bundles), 1)
        for bundle in bundles:
            self.assertLessEqual(bundle.total_tokens, doc.token_estimate)


if __name__ == "__main__":
    unittest.main()
