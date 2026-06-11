"""Deterministic Markdown chunking shared by the RAG export and chunk review.

Chunk boundaries depend only on the input text and the token budget, so the
chunks shown to a user during review line up with the chunks the pipeline
re-computes at export time. Each chunk also carries the reason its boundary
was drawn and a summary of the Markdown structure it contains, so reviewers
can see how the chunker behaves on their corpus instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import List, Optional, Sequence, Tuple

from .token_estimator import estimate_tokens

REASON_WHOLE_DOCUMENT = "entire document fits in one chunk"
REASON_BUDGET_REACHED = "token budget reached; split before the next paragraph"
REASON_BEFORE_OVERSIZE = "flushed before a paragraph larger than the budget"
REASON_OVERSIZE_SPLIT = "oversize paragraph split at line boundaries"
REASON_END_OF_DOCUMENT = "end of document"
REASON_HEADING_SECTION = "section starts at a heading"
REASON_PREAMBLE = "content before the first heading"

STRATEGY_TOKENS = "tokens"
STRATEGY_HEADINGS = "headings"
STRATEGIES = (STRATEGY_TOKENS, STRATEGY_HEADINGS)
DEFAULT_HEADING_LEVEL = 2

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


@dataclass(frozen=True)
class ChunkStructure:
    """Summary of the Markdown elements inside one chunk."""

    headings: Tuple[str, ...]
    paragraph_count: int
    list_item_count: int
    table_row_count: int

    def describe(self) -> str:
        parts: List[str] = []
        if self.headings:
            parts.append(f"{len(self.headings)} heading(s)")
        parts.append(f"{self.paragraph_count} paragraph(s)")
        if self.list_item_count:
            parts.append(f"{self.list_item_count} list item(s)")
        if self.table_row_count:
            parts.append(f"{self.table_row_count} table row(s)")
        return ", ".join(parts)


@dataclass(frozen=True)
class Chunk:
    """A contiguous portion of a converted document body."""

    index: int  # 1-based, stable for a given (text, max_tokens) pair
    text: str
    token_estimate: int
    boundary_reason: str = ""
    structure: Optional[ChunkStructure] = None

    @property
    def first_heading(self) -> str:
        if self.structure and self.structure.headings:
            return self.structure.headings[0]
        return ""


def chunk_markdown(text: str, max_tokens: int) -> List[str]:
    """Split text into chunks at paragraph boundaries within a token budget.

    Paragraphs are joined into a chunk while the running token estimate stays
    under ``max_tokens``. Paragraphs that exceed the budget on their own are
    further split by lines so we never emit silently-truncated content.
    """
    return [chunk_text for chunk_text, _ in chunk_markdown_with_reasons(text, max_tokens)]


def chunk_markdown_with_reasons(text: str, max_tokens: int) -> List[Tuple[str, str]]:
    """Chunk like :func:`chunk_markdown` and pair each chunk with the reason
    its boundary was drawn (one of the module-level ``REASON_*`` constants)."""
    if max_tokens <= 0:
        return [(text, REASON_WHOLE_DOCUMENT)]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [(text, REASON_WHOLE_DOCUMENT)]

    chunks: List[Tuple[str, str]] = []
    buffer: List[str] = []
    buffer_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if para_tokens > max_tokens:
            # Flush current buffer first.
            if buffer:
                chunks.append(("\n\n".join(buffer), REASON_BEFORE_OVERSIZE))
                buffer = []
                buffer_tokens = 0
            # Split the oversize paragraph by lines.
            chunks.extend(
                (piece, REASON_OVERSIZE_SPLIT)
                for piece in _split_oversize_paragraph(para, max_tokens)
            )
            continue

        if buffer_tokens + para_tokens <= max_tokens:
            buffer.append(para)
            buffer_tokens += para_tokens
        else:
            chunks.append(("\n\n".join(buffer), REASON_BUDGET_REACHED))
            buffer = [para]
            buffer_tokens = para_tokens

    if buffer:
        reason = REASON_WHOLE_DOCUMENT if not chunks else REASON_END_OF_DOCUMENT
        chunks.append(("\n\n".join(buffer), reason))

    return chunks


def chunk_document(
    body_markdown: str,
    max_tokens: int,
    strategy: str = STRATEGY_TOKENS,
    heading_level: int = DEFAULT_HEADING_LEVEL,
) -> List[Chunk]:
    """Chunk a converted document body into indexed, annotated chunks.

    ``strategy`` is one of :data:`STRATEGIES`. The ``tokens`` strategy packs
    paragraphs greedily against the budget. The ``headings`` strategy never
    merges content across headings of level ``heading_level`` or shallower:
    each section becomes its own chunk, with the token chunker applied only
    inside sections that exceed the budget. Documents without qualifying
    headings fall back to the token strategy.
    """
    text = (body_markdown or "").strip()
    if not text:
        return []
    if strategy == STRATEGY_HEADINGS:
        pairs = chunk_markdown_by_headings_with_reasons(text, max_tokens, heading_level)
    else:
        pairs = chunk_markdown_with_reasons(text, max_tokens)
    return [
        Chunk(
            index=i,
            text=chunk_text,
            token_estimate=estimate_tokens(chunk_text),
            boundary_reason=reason,
            structure=analyze_markdown_structure(chunk_text),
        )
        for i, (chunk_text, reason) in enumerate(pairs, start=1)
    ]


def split_into_heading_sections(text: str, heading_level: int) -> List[str]:
    """Split text into sections that start at headings of ``heading_level``
    or shallower. Content before the first qualifying heading is its own
    section. Headings inside fenced code blocks are ignored."""
    sections: List[str] = []
    current: List[str] = []
    in_code_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
        if not in_code_fence:
            heading = _HEADING_RE.match(stripped)
            if heading and len(heading.group(1)) <= heading_level and current:
                section = "\n".join(current).strip()
                if section:
                    sections.append(section)
                current = []
        current.append(line)
    section = "\n".join(current).strip()
    if section:
        sections.append(section)
    return sections


def chunk_markdown_by_headings_with_reasons(
    text: str,
    max_tokens: int,
    heading_level: int = DEFAULT_HEADING_LEVEL,
) -> List[Tuple[str, str]]:
    """Heading-aligned chunking: one chunk per heading section, with the
    token chunker applied inside sections larger than the budget."""
    sections = split_into_heading_sections(text, heading_level)
    if not sections:
        return []
    if len(sections) == 1 and not _starts_with_heading(sections[0], heading_level):
        return chunk_markdown_with_reasons(sections[0], max_tokens)

    pairs: List[Tuple[str, str]] = []
    for section in sections:
        if _starts_with_heading(section, heading_level):
            section_reason = REASON_HEADING_SECTION
        else:
            section_reason = REASON_PREAMBLE
        if max_tokens <= 0 or estimate_tokens(section) <= max_tokens:
            pairs.append((section, section_reason))
        else:
            pairs.extend(chunk_markdown_with_reasons(section, max_tokens))
    return pairs


def _starts_with_heading(section: str, heading_level: int) -> bool:
    first_line = section.split("\n", 1)[0].strip()
    heading = _HEADING_RE.match(first_line)
    return heading is not None and len(heading.group(1)) <= heading_level


def analyze_markdown_structure(text: str) -> ChunkStructure:
    """Summarize the Markdown elements in ``text`` (fenced code is skipped)."""
    headings: List[str] = []
    list_items = 0
    table_rows = 0
    in_code_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            headings.append(heading.group(2).strip())
            continue
        if _LIST_ITEM_RE.match(line):
            list_items += 1
            continue
        if _TABLE_ROW_RE.match(line):
            table_rows += 1
    paragraph_count = sum(1 for block in text.split("\n\n") if block.strip())
    return ChunkStructure(
        headings=tuple(headings),
        paragraph_count=paragraph_count,
        list_item_count=list_items,
        table_row_count=table_rows,
    )


def match_heading_patterns(heading: str, patterns: Sequence[str]) -> Tuple[str, ...]:
    """Return the patterns that match ``heading``.

    Matching is case-insensitive and glob-style (``*`` wildcards, e.g.
    ``*_html``). Blank patterns and blank headings never match.
    """
    if not heading or not heading.strip():
        return ()
    candidate = heading.strip().lower()
    return tuple(
        pattern
        for pattern in patterns
        if pattern and pattern.strip() and fnmatchcase(candidate, pattern.strip().lower())
    )


def _split_oversize_paragraph(para: str, max_tokens: int) -> List[str]:
    """Last-ditch line-level split for paragraphs that exceed the chunk budget."""
    lines = para.split("\n")
    chunks: List[str] = []
    buffer: List[str] = []
    buffer_tokens = 0
    for line in lines:
        line_tokens = estimate_tokens(line)
        if buffer_tokens + line_tokens <= max_tokens:
            buffer.append(line)
            buffer_tokens += line_tokens
        else:
            if buffer:
                chunks.append("\n".join(buffer))
            buffer = [line]
            buffer_tokens = line_tokens
    if buffer:
        chunks.append("\n".join(buffer))
    return chunks
