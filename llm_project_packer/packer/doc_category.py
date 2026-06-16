"""Document categories for folder-sourced packaging (policy vs. appeal tiers).

A "category" is a coarse source-hierarchy tier assigned to each folder-sourced
document. It lets a mixed FEMA Public Assistance corpus — an authoritative
policy manual (the PAPPG) alongside individual second-appeal decision letters —
be packaged with tier-appropriate handling: policy documents are restructured
(heading-aware) and bundled first as the governing authority, while appeal/case
documents are kept as focused, complete files.

Categories are *opt-in*: when classification is disabled the packaging pipeline
behaves exactly as before. The user assigns categories explicitly in the UI;
:func:`guess_category` provides a filename-based default so a run with no
overrides still separates the obvious cases.
"""

from __future__ import annotations

import re
from typing import Dict, Mapping, Optional, Sequence

CATEGORY_POLICY = "policy"
CATEGORY_APPEAL = "appeal"
CATEGORY_OTHER = "other"

CATEGORIES: Sequence[str] = (CATEGORY_POLICY, CATEGORY_APPEAL, CATEGORY_OTHER)

# Bundling tier order: authority (policy) first, then case decisions, then the
# rest. Lower-indexed bundles sort ahead in the destination workspace.
CATEGORY_ORDER: Sequence[str] = (CATEGORY_POLICY, CATEGORY_APPEAL, CATEGORY_OTHER)

CATEGORY_LABELS: Dict[str, str] = {
    CATEGORY_POLICY: "PA Policy / Guidance",
    CATEGORY_APPEAL: "Appeal / Case Decision",
    CATEGORY_OTHER: "Other",
}

# Filename tokens that mark an authoritative policy / guidance document.
_POLICY_TOKENS = (
    "pappg",
    "policy",
    "guidance",
    "guide",
    "manual",
    "handbook",
    "directive",
    "stafford",
    "cfr",
    "fact sheet",
    "factsheet",
)

# Filename tokens that mark an individual appeal / case decision.
_APPEAL_TOKENS = (
    "appeal",
    "second appeal",
    "project worksheet",
    " pw",
    "pws",
    "gmp",
    "dsr",
    "pa id",
    "determination",
)

# Disaster declaration patterns, e.g. "4021-DR", "3589-EM", "FEMA-1174-DR-ND".
_DISASTER_RE = re.compile(r"\b\d{3,4}\s*-\s*(?:dr|em)\b", re.IGNORECASE)


def normalize_category(value: Optional[str]) -> str:
    """Return a valid category, falling back to ``CATEGORY_OTHER``."""
    if value is None:
        return CATEGORY_OTHER
    candidate = str(value).strip().lower()
    return candidate if candidate in CATEGORIES else CATEGORY_OTHER


def guess_category(relative_path: str) -> str:
    """Guess a document's category from its source-relative path / filename.

    Policy markers win over appeal markers because an authoritative guide (e.g.
    the PAPPG) often discusses appeals without being one. Returns
    ``CATEGORY_OTHER`` when nothing matches.
    """
    text = str(relative_path).lower()
    if any(token in text for token in _POLICY_TOKENS):
        return CATEGORY_POLICY
    if _DISASTER_RE.search(text) or any(token in text for token in _APPEAL_TOKENS):
        return CATEGORY_APPEAL
    return CATEGORY_OTHER


def resolve_category(relative_path: str, overrides: Optional[Mapping[str, str]]) -> str:
    """Resolve one document's category from explicit overrides or the guesser.

    ``overrides`` maps source-relative POSIX paths (case-insensitive) to a
    category. A missing or invalid override falls back to :func:`guess_category`.
    """
    if overrides:
        key = str(relative_path).strip("/").lower()
        if key in overrides:
            return normalize_category(overrides[key])
    return guess_category(relative_path)


def normalize_overrides(overrides: Optional[Mapping[str, str]]) -> Dict[str, str]:
    """Lower-case override keys to source-relative POSIX paths for stable lookup."""
    if not overrides:
        return {}
    return {
        str(path).strip("/").lower(): normalize_category(value)
        for path, value in overrides.items()
    }
