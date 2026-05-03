"""Small helpers for producing readable Markdown and safe filenames."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence

# Characters that are unsafe on Windows filesystems (and a few problematic
# elsewhere). We replace them with underscores.
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, max_length: int = 120) -> str:
    """Return a filesystem-safe version of ``name``.

    Replaces unsafe characters with underscores, collapses whitespace, and
    truncates to ``max_length``.
    """
    name = name.strip()
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)
    name = re.sub(r"\s+", "_", name)
    name = name.strip("._")
    if not name:
        name = "untitled"
    if len(name) > max_length:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            keep = max_length - len(ext) - 1
            name = stem[:keep] + "." + ext
        else:
            name = name[:max_length]
    return name


def doc_id_for_index(index: int) -> str:
    """Return a stable document ID like ``DOC_0007`` for the given 1-based index."""
    return f"DOC_{index:04d}"


def doc_header(
    doc_id: str,
    source_file: str,
    source_path: str,
    original_extension: str,
) -> str:
    """Render the YAML-style identity header that prefixes every document."""
    return (
        "---\n"
        f"DOC_ID: {doc_id}\n"
        f"SOURCE_FILE: {source_file}\n"
        f"SOURCE_PATH: {source_path}\n"
        f"ORIGINAL_EXTENSION: {original_extension}\n"
        "---\n"
    )


def section_divider() -> str:
    """Return the divider used between documents inside a bundle."""
    return "\n\n<!-- ================================================== -->\n\n"


def escape_table_cell(value: object) -> str:
    """Escape a value so it can be safely embedded in a Markdown table cell."""
    if value is None:
        return ""
    s = str(value)
    s = s.replace("\\", "\\\\")
    s = s.replace("|", "\\|")
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return s


def rows_to_markdown_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
) -> str:
    """Render a list of row tuples as a Markdown table."""
    headers = [escape_table_cell(h) if h is not None else "" for h in headers]
    if not headers:
        return ""
    out: List[str] = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        cells = [escape_table_cell(c) for c in row]
        # Pad / truncate to header length so the table is well-formed.
        if len(cells) < len(headers):
            cells = cells + [""] * (len(headers) - len(cells))
        elif len(cells) > len(headers):
            cells = cells[: len(headers)]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def unique_destination(dest_dir: Path, filename: str) -> Path:
    """Return a path inside ``dest_dir`` that does not collide with an existing file.

    Appends ``_1``, ``_2``, etc. before the extension when needed.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = Path(filename).stem
    ext = Path(filename).suffix
    candidate = dest_dir / f"{base}{ext}"
    counter = 1
    while candidate.exists():
        candidate = dest_dir / f"{base}_{counter}{ext}"
        counter += 1
    return candidate


def normalize_newlines(text: str) -> str:
    """Normalize CRLF / CR line endings to LF and strip trailing whitespace lines."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Trim trailing spaces on each line; keeps Markdown clean.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip() + "\n"
