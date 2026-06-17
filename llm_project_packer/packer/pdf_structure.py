"""Structure-aware re-rendering of converted PDF text.

The PDF readers in :mod:`packer.readers` emit flat ``## Page N`` blocks of raw
extracted text. For a long, well-structured policy document (e.g. the FEMA
PAPPG) that flat output is poor for the ChatGPT Enterprise / "DHS chat"
destination: medium-grained bundling would split at arbitrary *page* boundaries
instead of real section boundaries, and every page carries running-header and
page-number boilerplate.

:func:`restructure_pdf_markdown` post-processes that page-segmented Markdown
into clean, heading-structured Markdown — it strips repeated running
headers/footers, promotes chapter and lettered-section headings, normalizes
symbol-font bullets, and reflows hard-wrapped lines into paragraphs — so that
heading-aware splitting lands on chapters/sections and the body reads cleanly.
It is deliberately conservative and never raises: on any problem it returns the
input unchanged.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_PAGE_RE = re.compile(r"^##\s+Page\s+\d+\s*$", re.IGNORECASE)
# A chapter heading, e.g. "Chapter 7: Emergency Work Eligibility" — requires the
# "Chapter N: Title" colon form so inline cross-references ("see Chapter 2 to
# learn more...", "Chapter 11.") are not promoted to split boundaries.
_CHAPTER_RE = re.compile(r"^Chapter\s+\d+:\s+[A-Z]")
# A lettered section heading, e.g. "A. Simplified Procedures".
_LETTER_RE = re.compile(r"^[A-Z]\.\s+[A-Z(]")
# Symbol-font / private-use bullet glyphs that survive extraction as gibberish.
_BULLET_CHARS = "•▪●"
_BULLET_RE = re.compile(rf"^[{_BULLET_CHARS}]\s*")
# A bare page-number / footnote-number line (digits only).
_NUMERIC_RE = re.compile(r"^\d{1,4}$")

# A line is a candidate running header/footer if it repeats on at least this
# fraction of pages.
_BOILERPLATE_FRACTION = 0.35
_BOILERPLATE_MAX_LEN = 60


def restructure_pdf_markdown(markdown: str) -> str:
    """Re-render page-segmented PDF Markdown as clean, heading-structured text.

    Returns the input unchanged when it has no ``## Page N`` markers or when any
    error occurs, so callers can apply it unconditionally to PDF output.
    """
    try:
        return _restructure(markdown)
    except Exception:  # pragma: no cover - defensive; never break a run
        return markdown


def _restructure(markdown: str) -> str:
    pages = _split_pages(markdown)
    if len(pages) < 1 or not any(_PAGE_RE.match(line) for line in markdown.splitlines()):
        return markdown

    boilerplate = _detect_boilerplate(pages)
    out_lines: List[str] = []
    for page in pages:
        for raw in page:
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped:
                out_lines.append("")
                continue
            if stripped in boilerplate or _NUMERIC_RE.match(stripped):
                continue
            rendered = _render_line(stripped)
            out_lines.append(rendered)
    body = _reflow("\n".join(out_lines))
    return body


def _split_pages(markdown: str) -> List[List[str]]:
    """Split the markdown into per-page line lists on ``## Page N`` markers."""
    pages: List[List[str]] = []
    current: List[str] = []
    started = False
    for line in markdown.splitlines():
        if _PAGE_RE.match(line):
            if started:
                pages.append(current)
            current = []
            started = True
            continue
        current.append(line)
    if current:
        pages.append(current)
    return pages


def _detect_boilerplate(pages: List[List[str]]) -> set:
    """Return short lines that recur across many pages (running headers/footers)."""
    if len(pages) < 4:
        return set()
    counts: dict = {}
    for page in pages:
        seen = set()
        for raw in page:
            s = raw.strip()
            if not s or len(s) > _BOILERPLATE_MAX_LEN or _NUMERIC_RE.match(s):
                continue
            if s in seen:
                continue
            seen.add(s)
            counts[s] = counts.get(s, 0) + 1
    threshold = max(2, int(len(pages) * _BOILERPLATE_FRACTION))
    return {line for line, count in counts.items() if count >= threshold}


def _render_line(stripped: str) -> str:
    """Promote heading-like lines and normalize bullets; else return prose."""
    bullet = _BULLET_RE.match(stripped)
    if bullet:
        return "- " + stripped[bullet.end():].strip()
    if stripped.startswith("o ") and len(stripped) > 2:
        return "  - " + stripped[2:].strip()
    if _is_chapter_heading(stripped):
        return "## " + stripped
    if _is_lettered_heading(stripped):
        return "### " + stripped
    return stripped


def _is_chapter_heading(stripped: str) -> bool:
    """True for a real ``Chapter N: Title`` line, not a prose cross-reference."""
    if not _CHAPTER_RE.match(stripped) or "...." in stripped:
        return False
    # Real chapter titles are not sentences/clauses; references end in punctuation.
    return not stripped.endswith((".", ";", ","))


def _is_lettered_heading(stripped: str) -> bool:
    """True for short lettered section titles like ``A. Offset Amounts``."""
    if not _LETTER_RE.match(stripped):
        return False
    if len(stripped) > 80 or "...." in stripped:
        return False
    # Section titles are short phrases, not sentences.
    return len(stripped.split()) <= 10 and not stripped.endswith((".", ":", ";"))


def _reflow(text: str) -> str:
    """Join hard-wrapped prose lines into paragraphs; keep headings/lists apart."""
    lines = text.split("\n")
    blocks: List[str] = []
    buffer: List[str] = []

    def flush() -> None:
        if buffer:
            blocks.append(" ".join(part.strip() for part in buffer).strip())
            buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("#"):
            flush()
            blocks.append(stripped)
            continue
        if stripped.startswith("- ") or stripped.startswith("  - "):
            flush()
            blocks.append(line.rstrip())
            continue
        buffer.append(stripped)
    flush()

    rendered = "\n\n".join(b for b in blocks if b)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered.strip() + "\n"


def outline(markdown: str) -> List[Tuple[int, str]]:
    """Return ``(level, text)`` for each Markdown heading; for previews/tests."""
    result: List[Tuple[int, str]] = []
    for line in markdown.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            result.append((len(match.group(1)), match.group(2).strip()))
    return result
