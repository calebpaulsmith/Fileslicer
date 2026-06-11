from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.bundler import Bundle, ConvertedDoc, make_converted_doc, split_into_bundles  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
