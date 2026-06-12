from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.chunking import (  # noqa: E402
    REASON_BUDGET_REACHED,
    REASON_END_OF_DOCUMENT,
    REASON_HEADING_SECTION,
    REASON_MERGED_SMALL,
    REASON_OVERSIZE_SPLIT,
    REASON_PREAMBLE,
    REASON_SENTENCE_SPLIT,
    REASON_WHOLE_DOCUMENT,
    STRATEGY_HEADINGS,
    Chunk,
    analyze_markdown_structure,
    apply_chunk_overlap,
    chunk_document,
    chunk_markdown,
    chunk_markdown_by_headings_with_reasons,
    chunk_markdown_with_reasons,
    match_heading_patterns,
    merge_undersized_chunks,
    split_into_heading_sections,
)
from packer.token_estimator import estimate_tokens  # noqa: E402


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


class HeadingChunkingTests(unittest.TestCase):
    DOC = (
        "Intro before any heading.\n\n"
        "# Manual\n\nOverview paragraph.\n\n"
        "## Setup\n\nSetup paragraph.\n\n### Tools\n\nTools paragraph.\n\n"
        "## Procedure\n\nProcedure paragraph.\n"
    )

    def test_sections_split_at_qualifying_headings(self) -> None:
        sections = split_into_heading_sections(self.DOC, 2)
        self.assertEqual(len(sections), 4)
        self.assertTrue(sections[0].startswith("Intro"))
        self.assertTrue(sections[1].startswith("# Manual"))
        self.assertTrue(sections[2].startswith("## Setup"))
        self.assertIn("### Tools", sections[2])
        self.assertTrue(sections[3].startswith("## Procedure"))

    def test_deeper_split_level_separates_subsections(self) -> None:
        sections = split_into_heading_sections(self.DOC, 3)
        self.assertEqual(len(sections), 5)
        self.assertTrue(any(s.startswith("### Tools") for s in sections))

    def test_each_section_becomes_a_chunk_with_reasons(self) -> None:
        pairs = chunk_markdown_by_headings_with_reasons(self.DOC, 1000, 2)
        self.assertEqual(len(pairs), 4)
        self.assertEqual(pairs[0][1], REASON_PREAMBLE)
        for _, reason in pairs[1:]:
            self.assertEqual(reason, REASON_HEADING_SECTION)

    def test_oversize_section_is_subdivided_by_token_chunker(self) -> None:
        big_section = "## Big\n\n" + "\n\n".join(
            " ".join(["word"] * 30) for _ in range(3)
        )
        pairs = chunk_markdown_by_headings_with_reasons(big_section, 10, 2)
        self.assertGreater(len(pairs), 1)
        self.assertEqual(
            [text for text, _ in pairs],
            chunk_markdown(big_section, 10),
        )

    def test_document_without_headings_falls_back_to_token_chunking(self) -> None:
        text = "\n\n".join(" ".join(["plain"] * 30) for _ in range(3))
        self.assertEqual(
            chunk_markdown_by_headings_with_reasons(text, 10, 2),
            chunk_markdown_with_reasons(text, 10),
        )

    def test_chunk_document_headings_strategy(self) -> None:
        chunks = chunk_document(self.DOC, 1000, strategy=STRATEGY_HEADINGS)
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[1].first_heading, "Manual")
        self.assertEqual(chunks[2].first_heading, "Setup")
        self.assertEqual(chunks[1].boundary_reason, REASON_HEADING_SECTION)

    def test_code_fence_headings_do_not_split(self) -> None:
        text = "## Real\n\nBody.\n\n```\n## fake heading\n```\n\nMore body.\n"
        sections = split_into_heading_sections(text, 2)
        self.assertEqual(len(sections), 1)


class MatchHeadingPatternsTests(unittest.TestCase):
    def test_exact_match_is_case_insensitive(self) -> None:
        self.assertEqual(
            match_heading_patterns("Content_Hash", ("content_hash",)),
            ("content_hash",),
        )

    def test_glob_wildcards_match(self) -> None:
        self.assertEqual(
            match_heading_patterns("appeal_letter_html", ("*_html",)),
            ("*_html",),
        )
        self.assertEqual(match_heading_patterns("appeal_letter_text", ("*_html",)), ())

    def test_blank_heading_and_blank_patterns_never_match(self) -> None:
        self.assertEqual(match_heading_patterns("", ("*",)), ())
        self.assertEqual(match_heading_patterns("title", ("", "  ")), ())

    def test_returns_every_matching_pattern(self) -> None:
        self.assertEqual(
            match_heading_patterns("url", ("url", "u*", "slug")),
            ("url", "u*"),
        )


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


class MergeUndersizedChunksTests(unittest.TestCase):
    def test_zero_min_tokens_returns_input_unchanged(self) -> None:
        pairs = [("a", REASON_BUDGET_REACHED), ("b", REASON_END_OF_DOCUMENT)]
        self.assertEqual(merge_undersized_chunks(pairs, 0, 1000), pairs)

    def test_tiny_chunk_merges_into_previous(self) -> None:
        big = _paragraph("alpha")
        pairs = [(big, REASON_BUDGET_REACHED), ("tiny", REASON_END_OF_DOCUMENT)]
        merged = merge_undersized_chunks(pairs, 10, 1000)
        self.assertEqual(merged, [(f"{big}\n\ntiny", REASON_MERGED_SMALL)])

    def test_tiny_first_chunk_merges_into_next(self) -> None:
        big = _paragraph("bravo")
        pairs = [("tiny", REASON_HEADING_SECTION), (big, REASON_HEADING_SECTION)]
        merged = merge_undersized_chunks(pairs, 10, 1000)
        self.assertEqual(merged, [(f"tiny\n\n{big}", REASON_MERGED_SMALL)])

    def test_chain_of_tiny_chunks_collapses(self) -> None:
        pairs = [
            ("a a a", REASON_HEADING_SECTION),
            ("b b b", REASON_HEADING_SECTION),
            ("c c c", REASON_HEADING_SECTION),
        ]
        merged = merge_undersized_chunks(pairs, 50, 1000)
        self.assertEqual(merged, [("a a a\n\nb b b\n\nc c c", REASON_MERGED_SMALL)])

    def test_budget_blocks_merging(self) -> None:
        big = _paragraph("charlie")
        pairs = [(big, REASON_BUDGET_REACHED), ("tiny", REASON_END_OF_DOCUMENT)]
        merged = merge_undersized_chunks(pairs, 10, estimate_tokens(big))
        self.assertEqual(merged, pairs)

    def test_chunk_document_honors_min_tokens(self) -> None:
        text = f"## A\n\ntiny\n\n## B\n\n{_paragraph('delta')}"
        without = chunk_document(text, 1000, strategy=STRATEGY_HEADINGS, heading_level=2)
        self.assertEqual(len(without), 2)
        with_min = chunk_document(
            text, 1000, strategy=STRATEGY_HEADINGS, heading_level=2, min_tokens=20
        )
        self.assertEqual(len(with_min), 1)
        self.assertEqual(with_min[0].boundary_reason, REASON_MERGED_SMALL)
        self.assertIn("tiny", with_min[0].text)
        self.assertIn("delta", with_min[0].text)


class SentenceSplitTests(unittest.TestCase):
    LONG_LINE = " ".join(["This is sentence number one."] * 12)

    def test_default_keeps_oversize_line_whole(self) -> None:
        pairs = chunk_markdown_with_reasons(self.LONG_LINE, 20)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0], (self.LONG_LINE, REASON_OVERSIZE_SPLIT))

    def test_split_sentences_breaks_oversize_line_within_budget(self) -> None:
        pairs = chunk_markdown_with_reasons(self.LONG_LINE, 20, split_sentences=True)
        self.assertGreater(len(pairs), 1)
        for text, reason in pairs:
            self.assertEqual(reason, REASON_SENTENCE_SPLIT)
            self.assertLessEqual(estimate_tokens(text), 20)
        self.assertEqual(" ".join(text for text, _ in pairs), self.LONG_LINE)

    def test_sentence_without_punctuation_falls_back_to_words(self) -> None:
        line = " ".join(["word"] * 200)
        pairs = chunk_markdown_with_reasons(line, 10, split_sentences=True)
        self.assertGreater(len(pairs), 1)
        for text, reason in pairs:
            self.assertEqual(reason, REASON_SENTENCE_SPLIT)
            self.assertLessEqual(estimate_tokens(text), 10)
        self.assertEqual(" ".join(text for text, _ in pairs), line)

    def test_single_giant_word_stays_whole(self) -> None:
        line = "x" * 400
        pairs = chunk_markdown_with_reasons(line, 10, split_sentences=True)
        self.assertEqual(pairs, [(line, REASON_SENTENCE_SPLIT)])

    def test_normal_lines_in_oversize_paragraph_keep_line_splitting(self) -> None:
        para = "\n".join([_paragraph("echo", 10)] * 8)
        default_pairs = chunk_markdown_with_reasons(para, 30)
        sentence_pairs = chunk_markdown_with_reasons(para, 30, split_sentences=True)
        self.assertEqual(default_pairs, sentence_pairs)
        self.assertTrue(
            all(reason == REASON_OVERSIZE_SPLIT for _, reason in sentence_pairs)
        )

    def test_chunk_document_honors_split_sentences(self) -> None:
        without = chunk_document(self.LONG_LINE, 20)
        self.assertEqual(len(without), 1)
        with_split = chunk_document(self.LONG_LINE, 20, split_sentences=True)
        self.assertGreater(len(with_split), 1)
        self.assertEqual(with_split[0].boundary_reason, REASON_SENTENCE_SPLIT)

    def test_heading_strategy_passes_split_sentences_into_sections(self) -> None:
        text = f"## Long\n\n{self.LONG_LINE}"
        pairs = chunk_markdown_by_headings_with_reasons(
            text, 20, heading_level=2, split_sentences=True
        )
        self.assertGreater(len(pairs), 1)
        self.assertTrue(
            any(reason == REASON_SENTENCE_SPLIT for _, reason in pairs)
        )


class ApplyChunkOverlapTests(unittest.TestCase):
    def test_zero_overlap_returns_input_unchanged(self) -> None:
        chunks = ["one", "two"]
        self.assertEqual(apply_chunk_overlap(chunks, 0), chunks)

    def test_single_chunk_is_unchanged(self) -> None:
        self.assertEqual(apply_chunk_overlap(["only"], 100), ["only"])

    def test_tail_of_previous_chunk_is_prefixed(self) -> None:
        chunks = ["first line\nlast line of one", "body of two"]
        overlapped = apply_chunk_overlap(chunks, 1)
        self.assertEqual(overlapped[0], chunks[0])
        self.assertTrue(overlapped[1].startswith("last line of one\n\n"))
        self.assertTrue(overlapped[1].endswith("body of two"))

    def test_overlap_never_exceeds_whole_previous_chunk(self) -> None:
        overlapped = apply_chunk_overlap(["ab", "cd"], 10_000)
        self.assertEqual(overlapped, ["ab", "ab\n\ncd"])

    def test_overlap_uses_original_predecessor_not_overlapped_text(self) -> None:
        overlapped = apply_chunk_overlap(["A", "B", "C"], 10_000)
        self.assertEqual(overlapped, ["A", "A\n\nB", "B\n\nC"])

    def test_boundary_count_is_preserved(self) -> None:
        chunks = ["one one one", "two two two", "three three three"]
        self.assertEqual(len(apply_chunk_overlap(chunks, 2)), len(chunks))


if __name__ == "__main__":
    unittest.main()
