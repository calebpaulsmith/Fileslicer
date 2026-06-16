from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.pdf_structure import outline, restructure_pdf_markdown  # noqa: E402


def _page(n: int, body: str) -> str:
    return f"## Page {n}\n\n{body}\n"


class RestructureTests(unittest.TestCase):
    def test_no_page_markers_returns_input_unchanged(self) -> None:
        text = "# Already structured\n\nSome prose.\n"
        self.assertEqual(restructure_pdf_markdown(text), text)

    def test_strips_repeated_running_header_and_page_numbers(self) -> None:
        pages = "\n".join(
            _page(
                i,
                f"PAPPG v5\n{40 + i}\n\nBody text on page {i} that is real content "
                "and should be kept in the output.",
            )
            for i in range(1, 7)
        )
        out = restructure_pdf_markdown(pages)
        self.assertNotIn("PAPPG v5", out)
        # The bare page-number lines are gone too.
        self.assertNotIn("\n41\n", out)
        self.assertIn("real content", out)

    def test_promotes_chapter_headings_to_level_two(self) -> None:
        pages = _page(1, "Chapter 1: Declarations and Planning\n\nIntro prose here.") + _page(
            2, "Chapter 2: Coordination and Appeal Rights\n\nMore prose."
        )
        out = restructure_pdf_markdown(pages)
        chapters = [text for level, text in outline(out) if level == 2]
        self.assertEqual(
            chapters,
            ["Chapter 1: Declarations and Planning", "Chapter 2: Coordination and Appeal Rights"],
        )

    def test_does_not_promote_inline_chapter_references(self) -> None:
        pages = _page(
            1,
            "See Chapter 2 to learn more about the RFI Process.\n\n"
            "Refer to Chapter 11.\n\nreference Chapter 7: Emergency Work Eligibility.",
        )
        out = restructure_pdf_markdown(pages)
        self.assertEqual([t for lvl, t in outline(out) if lvl == 2], [])

    def test_promotes_lettered_sections_to_level_three(self) -> None:
        pages = _page(1, "A. Offset Amounts\n\nFEMA applies values as follows.")
        out = restructure_pdf_markdown(pages)
        self.assertIn((3, "A. Offset Amounts"), outline(out))

    def test_normalizes_bullets(self) -> None:
        pages = _page(1, "Intro line.\n\n• First bullet\n• Second bullet")
        out = restructure_pdf_markdown(pages)
        self.assertIn("- First bullet", out)
        self.assertIn("- Second bullet", out)

    def test_reflows_hard_wrapped_prose(self) -> None:
        pages = _page(
            1,
            "This sentence was hard wrapped\nacross several lines by the\nPDF extractor.",
        )
        out = restructure_pdf_markdown(pages)
        self.assertIn(
            "This sentence was hard wrapped across several lines by the PDF extractor.",
            out,
        )

    def test_never_raises_returns_input_on_bad_data(self) -> None:
        # Even degenerate input must not raise.
        self.assertIsInstance(restructure_pdf_markdown(""), str)
        self.assertIsInstance(restructure_pdf_markdown("## Page 1\n\n"), str)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
