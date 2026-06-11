"""Deterministic Markdown chunking shared by the RAG export and chunk review.

Chunk boundaries depend only on the input text and the token budget, so the
chunks shown to a user during review line up with the chunks the pipeline
re-computes at export time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .token_estimator import estimate_tokens


@dataclass(frozen=True)
class Chunk:
    """A contiguous portion of a converted document body."""

    index: int  # 1-based, stable for a given (text, max_tokens) pair
    text: str
    token_estimate: int


def chunk_markdown(text: str, max_tokens: int) -> List[str]:
    """Split text into chunks at paragraph boundaries within a token budget.

    Paragraphs are joined into a chunk while the running token estimate stays
    under ``max_tokens``. Paragraphs that exceed the budget on their own are
    further split by lines so we never emit silently-truncated content.
    """
    if max_tokens <= 0:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text]

    chunks: List[str] = []
    buffer: List[str] = []
    buffer_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if para_tokens > max_tokens:
            # Flush current buffer first.
            if buffer:
                chunks.append("\n\n".join(buffer))
                buffer = []
                buffer_tokens = 0
            # Split the oversize paragraph by lines.
            chunks.extend(_split_oversize_paragraph(para, max_tokens))
            continue

        if buffer_tokens + para_tokens <= max_tokens:
            buffer.append(para)
            buffer_tokens += para_tokens
        else:
            chunks.append("\n\n".join(buffer))
            buffer = [para]
            buffer_tokens = para_tokens

    if buffer:
        chunks.append("\n\n".join(buffer))

    return chunks


def chunk_document(body_markdown: str, max_tokens: int) -> List[Chunk]:
    """Chunk a converted document body into indexed, token-estimated chunks."""
    text = (body_markdown or "").strip()
    if not text:
        return []
    return [
        Chunk(index=i, text=chunk_text, token_estimate=estimate_tokens(chunk_text))
        for i, chunk_text in enumerate(chunk_markdown(text, max_tokens), start=1)
    ]


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
