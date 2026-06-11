from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.chunking import Chunk, chunk_document, chunk_markdown  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
