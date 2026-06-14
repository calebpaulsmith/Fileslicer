"""Packaging presets and defaults.

These token budgets are *packaging targets* used by this tool to decide how
to split content into bundles. They are NOT official platform context-window
limits, and platform limits change over time. Edit these to taste.
"""

from __future__ import annotations

from typing import Dict

# Default location of the pa_rag FEMA appeals database, used as a convenience
# fallback by the CLI (`--appeals-db` with no value) and the UI (pre-filled
# path). Override by passing an explicit path.
DEFAULT_APPEALS_DB = r"C:\Users\caleb\Documents\GitHub\pa_rag\data\pa_appeals.sqlite3"

# Targets supported by the tool.
TARGETS = ("chatgpt", "claude", "generic", "rag", "cowork")

# Modes supported by the tool.
MODES = ("lean", "balanced", "full", "visual_manual")

# Per-target / per-mode bundle token budgets. For "rag" and "cowork" these
# are *per-chunk* budgets rather than per-bundle budgets.
BUNDLE_TOKEN_DEFAULTS: Dict[str, Dict[str, int]] = {
    "chatgpt": {
        "lean": 60_000,
        "balanced": 90_000,
        "full": 120_000,
        "visual_manual": 90_000,
    },
    "claude": {
        "lean": 80_000,
        "balanced": 120_000,
        "full": 160_000,
        "visual_manual": 120_000,
    },
    "generic": {
        "lean": 40_000,
        "balanced": 60_000,
        "full": 90_000,
        "visual_manual": 60_000,
    },
    "rag": {
        "lean": 25_000,
        "balanced": 40_000,
        "full": 50_000,
        "visual_manual": 40_000,
    },
    "cowork": {
        "lean": 1_500,
        "balanced": 2_500,
        "full": 4_000,
        "visual_manual": 2_500,
    },
}

# Default extensions processed by the tool. The user may override with
# --include-extensions.
DEFAULT_INCLUDE_EXTENSIONS = (
    ".txt",
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".pdf",
    ".docx",
    ".csv",
    ".xlsx",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
)

# Directories that should never be scanned.
DEFAULT_EXCLUDE_DIRS = (
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "llm_project_exports",
    "sample_output",
    "test_output",
    "dist",
    "build",
    ".DS_Store",
)

# Coarse classification of extensions into file-type buckets.
TEXT_EXTS = {".txt", ".md", ".markdown"}
HTML_EXTS = {".html", ".htm"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}
CSV_EXTS = {".csv"}
XLSX_EXTS = {".xlsx"}
JSON_EXTS = {".json"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def classify_extension(ext: str) -> str:
    """Return a coarse file-type label for a given extension."""
    ext = ext.lower()
    if ext in TEXT_EXTS:
        return "text"
    if ext in HTML_EXTS:
        return "html"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in DOCX_EXTS:
        return "docx"
    if ext in CSV_EXTS:
        return "csv"
    if ext in XLSX_EXTS:
        return "xlsx"
    if ext in JSON_EXTS:
        return "json"
    if ext in IMAGE_EXTS:
        return "image"
    return "unsupported"


def get_bundle_token_budget(target: str, mode: str) -> int:
    """Return the default token budget for a given target/mode."""
    try:
        return BUNDLE_TOKEN_DEFAULTS[target][mode]
    except KeyError as exc:
        raise ValueError(
            f"No bundle token default for target={target!r} mode={mode!r}"
        ) from exc
