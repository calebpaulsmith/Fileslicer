"""Runtime configuration for a single packing run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from . import presets

# Where a packing job reads its documents from.
SOURCE_KINDS = ("folder", "appeals")

# How whole documents are grouped into bundles for the non-chunked targets.
BUNDLING_MODES = ("greedy", "medium")


@dataclass
class PackerConfig:
    """All knobs needed to run a single packing job."""

    source_dir: Path
    output_dir: Path
    target: str
    mode: str
    project_name: str
    max_bundle_tokens: int
    include_extensions: Tuple[str, ...] = field(
        default_factory=lambda: presets.DEFAULT_INCLUDE_EXTENSIONS
    )
    exclude_dirs: Tuple[str, ...] = field(
        default_factory=lambda: presets.DEFAULT_EXCLUDE_DIRS
    )
    source_kind: str = "folder"
    appeals_db: Optional[Path] = None
    bundling_mode: str = "greedy"
    destination: str = ""
    embedding_model: str = ""
    classify_documents: bool = False

    def validate(self) -> None:
        if self.target not in presets.TARGETS:
            raise ValueError(
                f"Unknown target {self.target!r}. Choose from {presets.TARGETS}."
            )
        if self.mode not in presets.MODES:
            raise ValueError(
                f"Unknown mode {self.mode!r}. Choose from {presets.MODES}."
            )
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(
                f"Unknown source_kind {self.source_kind!r}. Choose from {SOURCE_KINDS}."
            )
        if self.bundling_mode not in BUNDLING_MODES:
            raise ValueError(
                f"Unknown bundling_mode {self.bundling_mode!r}. Choose from {BUNDLING_MODES}."
            )
        if self.source_kind == "appeals":
            if self.appeals_db is None:
                raise ValueError("appeals source requires appeals_db to be set.")
            db = Path(self.appeals_db)
            if not db.exists() or not db.is_file():
                raise ValueError(
                    f"Appeals database does not exist or is not a file: {db}"
                )
        elif not self.source_dir.exists() or not self.source_dir.is_dir():
            raise ValueError(
                f"Source directory does not exist or is not a directory: {self.source_dir}"
            )
        if self.max_bundle_tokens <= 0:
            raise ValueError("max-bundle-tokens must be a positive integer.")
        if not self.project_name:
            raise ValueError("project-name must be a non-empty string.")
