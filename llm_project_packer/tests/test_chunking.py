from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.chunking import (  # noqa: E402
    REASON_BUDGET_REACHED,
    REASON_END_OF_DOCUMENT,
    REASON_OVERSIZE_SPLIT,
    REASON_WHOLE_DOCUMENT,
    Chunk,
    analyze_markdown_structure,
    chunk_document,
    chunk_markdown,
    chunk_markdown_with_reasons,
)


def _paragraph(word: str, repeats: int = 30) -> str:
    return " ".join([word] * repeats)


class ChunkMarkdownTests(unittest.TestCase):
    def test_small_text_is_a_single_chunk(self) -> None:
        text = "One short paragraph."
        self.assertEqual(chunk_markdown(text, 1000), [text])

    def test_paragraphs_split_into_multiple_chunks(self) -> None:
        text = "\n\n".join(
            [_paragraph("alpha"), _paragraph("bravo"), _paragraph("charlie")]
        )
        chunks = chunk_markdown(text, 10)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual("\n\n".join(chunks), text)

    def test_non_positive_budget_returns_text_unchanged(self) -> None:
        text = "anything at all"
        self.assertEqual(chunk_markdown(text, 0), [text])

    def test_oversize_paragraph_is_split_by_lines(self) -> None:
        paragraph = "\n".join(_paragraph("delta") for _ in range(5))
        chunks = chunk_markdown(paragraph, 10)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("\n".join(chunks), paragraph)

    def test_chunking_is_deterministic(self) -> None:
        text = "\n\n".join(_paragraph(word) for word in ("echo", "foxtrot", "golf"))
        self.assertEqual(chunk_markdown(text, 12), chunk_markdown(text, 12))


class ChunkDocumentTests(unittest.TestCase):
    def test_empty_body_yields_no_chunks(self) -> None:
        self.assertEqual(chunk_document("", 100), [])
        self.assertEqual(chunk_document("   \n\n  ", 100), [])

    def test_chunks_are_indexed_from_one_with_token_estimates(self) -> None:
        text = "\n\n".join([_paragraph("hotel"), _paragraph("india")])
        chunks = chunk_document(text, 10)
        self.assertGreaterEqual(len(chunks), 2)
        for position, chunk in enumerate(chunks, start=1):
            self.assertIsInstance(chunk, Chunk)
            self.assertEqual(chunk.index, position)
            self.assertGreater(chunk.token_estimate, 0)

    def test_chunk_texts_match_chunk_markdown(self) -> None:
        text = "\n\n".join([_paragraph("juliet"), _paragraph("kilo")])
        self.assertEqual(
            [chunk.text for chunk in chunk_document(text, 10)],
            chunk_markdown(text.strip(), 10),
        )


class BoundaryReasonTests(unittest.TestCase):
    def test_single_chunk_is_whole_document(self) -> None:
        pairs = chunk_markdown_with_reasons("One short paragraph.", 1000)
        self.assertEqual(pairs, [("One short paragraph.", REASON_WHOLE_DOCUMENT)])

    def test_budget_splits_end_with_end_of_document(self) -> None:
        # Each paragraph fits the budget alone but not together with another.
        text = "\n\n".join(
            _paragraph(word, repeats=6) for word in ("lima", "mike", "echo")
        )
        pairs = chunk_markdown_with_reasons(text, 10)
        self.assertGreaterEqual(len(pairs), 2)
        for _, reason in pairs[:-1]:
            self.assertEqual(reason, REASON_BUDGET_REACHED)
        self.assertEqual(pairs[-1][1], REASON_END_OF_DOCUMENT)

    def test_oversize_paragraph_chunks_are_marked(self) -> None:
        paragraph = "\n".join(_paragraph("oscar") for _ in range(5))
        pairs = chunk_markdown_with_reasons(paragraph, 10)
        self.assertGreater(len(pairs), 1)
        for _, reason in pairs:
            self.assertEqual(reason, REASON_OVERSIZE_SPLIT)

    def test_reasons_match_chunk_markdown_texts(self) -> None:
        text = "\n\n".join(_paragraph(word) for word in ("papa", "quebec"))
        self.assertEqual(
            [chunk_text for chunk_text, _ in chunk_markdown_with_reasons(text, 10)],
            chunk_markdown(text, 10),
        )

    def test_chunk_document_populates_reason_and_structure(self) -> None:
        text = "# Title\n\nBody paragraph here."
        chunks = chunk_document(text, 1000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].boundary_reason, REASON_WHOLE_DOCUMENT)
        self.assertIsNotNone(chunks[0].structure)
        self.assertEqual(chunks[0].first_heading, "Title")


class StructureAnalysisTests(unittest.TestCase):
    def test_counts_headings_paragraphs_lists_and_tables(self) -> None:
        text = (
            "# Setup\n\n"
            "First paragraph of prose.\n\n"
            "## Steps\n\n"
            "- step one\n"
            "- step two\n"
            "1. numbered step\n\n"
            "| part | torque |\n"
            "| --- | --- |\n"
            "| bolt | 10 Nm |\n"
        )
        structure = analyze_markdown_structure(text)
        self.assertEqual(structure.headings, ("Setup", "Steps"))
        self.assertEqual(structure.list_item_count, 3)
        self.assertEqual(structure.table_row_count, 3)
        self.assertGreaterEqual(structure.paragraph_count, 4)
        description = structure.describe()
        self.assertIn("heading", description)
        self.assertIn("list item", description)
        self.assertIn("table row", description)

    def test_fenced_code_is_not_counted_as_structure(self) -> None:
        text = "Intro.\n\n```\n# not a heading\n- not a list\n```\n"
        structure = analyze_markdown_structure(text)
        self.assertEqual(structure.headings, ())
        self.assertEqual(structure.list_item_count, 0)


if __name__ == "__main__":
    unittest.main()
