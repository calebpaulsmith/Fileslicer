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
from typing import List, Optional, Tuple

from .token_estimator import estimate_tokens

REASON_WHOLE_DOCUMENT = "entire document fits in one chunk"
REASON_BUDGET_REACHED = "token budget reached; split before the next paragraph"
REASON_BEFORE_OVERSIZE = "flushed before a paragraph larger than the budget"
REASON_OVERSIZE_SPLIT = "oversize paragraph split at line boundaries"
REASON_END_OF_DOCUMENT = "end of document"

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


def chunk_document(body_markdown: str, max_tokens: int) -> List[Chunk]:
    """Chunk a converted document body into indexed, annotated chunks."""
    text = (body_markdown or "").strip()
    if not text:
        return []
    return [
        Chunk(
            index=i,
            text=chunk_text,
            token_estimate=estimate_tokens(chunk_text),
            boundary_reason=reason,
            structure=analyze_markdown_structure(chunk_text),
        )
        for i, (chunk_text, reason) in enumerate(
            chunk_markdown_with_reasons(text, max_tokens), start=1
        )
    ]


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
