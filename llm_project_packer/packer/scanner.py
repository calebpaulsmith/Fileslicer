"""Recursive filesystem scanner.

Walks the source directory, applies include-extensions and exclude-dirs
filters, and yields stable, sorted file records.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from . import presets


@dataclass(frozen=True)
class ScannedFile:
    """A single file discovered by the scanner."""

    absolute_path: Path
    relative_path: Path
    extension: str  # lowercase, includes leading dot
    file_type: str  # text/html/pdf/docx/csv/xlsx/image/unsupported
    size_bytes: int


def _is_excluded_dir(name: str, excluded: Sequence[str]) -> bool:
    return name in excluded


def scan_directory(
    source_dir: Path,
    include_extensions: Iterable[str],
    exclude_dirs: Iterable[str],
) -> List[ScannedFile]:
    """Recursively scan ``source_dir`` and return the matching files.

    Supported files outside ``include_extensions`` are skipped entirely.
    Unsupported extensions are still returned so the manifest can record them
    as skipped instead of making them disappear. Files inside excluded
    directories at any depth are skipped. Results are sorted by relative path
    for deterministic ordering.
    """
    source_dir = source_dir.resolve()
    include = {e.lower() for e in include_extensions}
    exclude = tuple(exclude_dirs)

    found: List[ScannedFile] = []
    for path in _iter_files(source_dir, exclude):
        ext = path.suffix.lower()
        file_type = presets.classify_extension(ext)
        if file_type != "unsupported" and ext not in include:
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = 0
        rel = path.relative_to(source_dir)
        found.append(
            ScannedFile(
                absolute_path=path,
                relative_path=rel,
                extension=ext,
                file_type=file_type,
                size_bytes=size_bytes,
            )
        )

    found.sort(key=lambda f: str(f.relative_path).lower())
    return found


def _iter_files(root: Path, excluded: Tuple[str, ...]):
    """Yield every regular file under ``root``, skipping excluded directories."""
    # We use a manual stack so we can prune excluded directories cheaply.
    stack: List[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            try:
                if entry.is_dir():
                    if _is_excluded_dir(entry.name, excluded):
                        continue
                    stack.append(entry)
                elif entry.is_file():
                    if _is_excluded_dir(entry.name, excluded):
                        continue
                    yield entry
            except OSError:
                # Symlink loops or permission issues — skip silently.
                continue
