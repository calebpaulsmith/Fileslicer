"""Runtime configuration for a single packing run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from . import presets


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

    def validate(self) -> None:
        if self.target not in presets.TARGETS:
            raise ValueError(
                f"Unknown target {self.target!r}. Choose from {presets.TARGETS}."
            )
        if self.mode not in presets.MODES:
            raise ValueError(
                f"Unknown mode {self.mode!r}. Choose from {presets.MODES}."
            )
        if not self.source_dir.exists() or not self.source_dir.is_dir():
            raise ValueError(
                f"Source directory does not exist or is not a directory: {self.source_dir}"
            )
        if self.max_bundle_tokens <= 0:
            raise ValueError("max-bundle-tokens must be a positive integer.")
        if not self.project_name:
            raise ValueError("project-name must be a non-empty string.")
