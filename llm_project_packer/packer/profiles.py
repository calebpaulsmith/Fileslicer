"""Project profile storage and built-in templates.

Profiles capture a reusable set of packaging settings so the same job can be
re-run from the CLI or a future UI. Active fields are wired into
``run_packaging_job``; inert fields are stored and round-tripped today and
will be honored by later milestones.

Profiles are stored as JSON under ``~/.llm_project_packer/profiles/``. Tests
and other callers can override the storage location by passing
``profiles_dir``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from . import presets
from .chunking import DEFAULT_HEADING_LEVEL, STRATEGIES, STRATEGY_TOKENS
from .markdown_utils import safe_filename


PathLike = Union[str, Path]

_PROFILE_SCHEMA_VERSION = 1
_PROFILE_FILE_SUFFIX = ".json"


def default_profiles_dir() -> Path:
    """Return the default per-user profiles directory.

    The directory is *not* created here; writers create it on demand so a
    read-only call (e.g. ``list_profiles``) on a fresh machine does not have
    side effects.
    """
    return Path.home() / ".llm_project_packer" / "profiles"


# Fields that are passed through to ``run_packaging_job`` today.
ACTIVE_FIELDS: Sequence[str] = (
    "project_name",
    "default_source_folder",
    "default_output_folder",
    "target",
    "mode",
    "max_bundle_tokens",
    "include_extensions",
    "exclude_dirs",
    "chunk_exclude_headings",
    "chunk_token_budget",
    "chunk_strategy",
    "chunk_heading_level",
)

# Fields that are stored and round-tripped, but not yet honored by the
# packaging backend. They will be wired in later milestones.
INERT_FIELDS: Sequence[str] = (
    "include_assets",
    "copy_data_files",
    "spreadsheet_preview_rows",
    "include_pdf_page_headers",
    "include_source_metadata",
    "bundle_separator_style",
    "create_zip",
)


@dataclass
class Profile:
    """A reusable packaging profile.

    See ``ACTIVE_FIELDS`` for fields that influence packaging today and
    ``INERT_FIELDS`` for fields stored for forward compatibility only.
    """

    profile_name: str
    project_name: str = ""
    default_source_folder: str = ""
    default_output_folder: str = "./llm_project_exports"
    target: str = "chatgpt"
    mode: str = "balanced"
    max_bundle_tokens: Optional[int] = None
    include_extensions: List[str] = field(default_factory=list)
    exclude_dirs: List[str] = field(default_factory=list)
    chunk_exclude_headings: List[str] = field(default_factory=list)
    chunk_token_budget: Optional[int] = None
    chunk_strategy: str = STRATEGY_TOKENS
    chunk_heading_level: int = DEFAULT_HEADING_LEVEL
    include_assets: bool = True
    copy_data_files: bool = True
    spreadsheet_preview_rows: int = 25
    include_pdf_page_headers: bool = True
    include_source_metadata: bool = True
    bundle_separator_style: str = "comment"
    create_zip: bool = False

    def validate(self) -> None:
        """Raise ``ValueError`` if the profile is not internally consistent."""
        if not self.profile_name or not self.profile_name.strip():
            raise ValueError("profile_name must be a non-empty string.")
        if self.target not in presets.TARGETS:
            raise ValueError(
                f"Unknown target {self.target!r}. Choose from {presets.TARGETS}."
            )
        if self.mode not in presets.MODES:
            raise ValueError(
                f"Unknown mode {self.mode!r}. Choose from {presets.MODES}."
            )
        if self.max_bundle_tokens is not None and self.max_bundle_tokens <= 0:
            raise ValueError(
                "max_bundle_tokens must be a positive integer when set."
            )
        if self.spreadsheet_preview_rows < 0:
            raise ValueError("spreadsheet_preview_rows must be >= 0.")
        if not isinstance(self.include_extensions, list):
            raise ValueError("include_extensions must be a list of strings.")
        if not isinstance(self.exclude_dirs, list):
            raise ValueError("exclude_dirs must be a list of strings.")
        if not isinstance(self.chunk_exclude_headings, list):
            raise ValueError("chunk_exclude_headings must be a list of strings.")
        if self.chunk_token_budget is not None and self.chunk_token_budget <= 0:
            raise ValueError("chunk_token_budget must be a positive integer when set.")
        if self.chunk_strategy not in STRATEGIES:
            raise ValueError(
                f"Unknown chunk_strategy {self.chunk_strategy!r}. "
                f"Choose from {STRATEGIES}."
            )
        if not 1 <= int(self.chunk_heading_level) <= 6:
            raise ValueError("chunk_heading_level must be between 1 and 6.")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the profile to a JSON-friendly dict, including a schema tag."""
        data: Dict[str, Any] = {"_schema_version": _PROFILE_SCHEMA_VERSION}
        data.update(asdict(self))
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Profile":
        """Build a ``Profile`` from a dict, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if "include_extensions" in kwargs and kwargs["include_extensions"] is not None:
            kwargs["include_extensions"] = list(kwargs["include_extensions"])
        if "exclude_dirs" in kwargs and kwargs["exclude_dirs"] is not None:
            kwargs["exclude_dirs"] = list(kwargs["exclude_dirs"])
        if (
            "chunk_exclude_headings" in kwargs
            and kwargs["chunk_exclude_headings"] is not None
        ):
            kwargs["chunk_exclude_headings"] = list(kwargs["chunk_exclude_headings"])
        return cls(**kwargs)

    def to_packaging_kwargs(
        self,
        *,
        source_dir: Optional[PathLike] = None,
        output_dir: Optional[PathLike] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convert active fields into kwargs for ``run_packaging_job``.

        ``source_dir``, ``output_dir``, and ``project_name`` accept call-time
        overrides. The profile itself is never mutated. Inert fields are
        intentionally omitted; they are not yet honored by the backend.
        """
        resolved_source = source_dir if source_dir is not None else self.default_source_folder
        if not resolved_source:
            raise ValueError(
                "source_dir is required: pass an override or set "
                "Profile.default_source_folder."
            )
        resolved_output = (
            output_dir if output_dir is not None else self.default_output_folder
        )
        if not resolved_output:
            resolved_output = "./llm_project_exports"
        resolved_project = project_name if project_name else (self.project_name or None)

        kwargs: Dict[str, Any] = {
            "source_dir": Path(resolved_source).expanduser(),
            "output_dir": Path(resolved_output).expanduser(),
            "project_name": resolved_project,
            "target": self.target,
            "mode": self.mode,
            "max_bundle_tokens": self.max_bundle_tokens,
            "include_extensions": list(self.include_extensions) or None,
            "exclude_dirs": list(self.exclude_dirs) or None,
            "chunk_exclude_headings": list(self.chunk_exclude_headings) or None,
            "chunk_token_budget": self.chunk_token_budget,
            "chunk_strategy": self.chunk_strategy,
            "chunk_heading_level": int(self.chunk_heading_level),
        }
        return kwargs


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _resolve_profiles_dir(profiles_dir: Optional[PathLike]) -> Path:
    return Path(profiles_dir).expanduser() if profiles_dir is not None else default_profiles_dir()


def _profile_filename(profile_name: str) -> str:
    return safe_filename(profile_name) + _PROFILE_FILE_SUFFIX


def _profile_path(profile_name: str, profiles_dir: Path) -> Path:
    return profiles_dir / _profile_filename(profile_name)


def save_profile(profile: Profile, profiles_dir: Optional[PathLike] = None) -> Path:
    """Validate ``profile`` and write it to disk as JSON. Returns the file path."""
    profile.validate()
    target_dir = _resolve_profiles_dir(profiles_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = _profile_path(profile.profile_name, target_dir)
    path.write_text(
        json.dumps(profile.to_dict(), indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_profile(profile_name: str, profiles_dir: Optional[PathLike] = None) -> Profile:
    """Load a profile by name. Raises ``FileNotFoundError`` if missing."""
    target_dir = _resolve_profiles_dir(profiles_dir)
    path = _profile_path(profile_name, target_dir)
    if not path.exists():
        raise FileNotFoundError(f"No profile found for name {profile_name!r} at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    profile = Profile.from_dict(data)
    profile.validate()
    return profile


def list_profiles(profiles_dir: Optional[PathLike] = None) -> List[str]:
    """Return the display names of saved profiles, sorted case-insensitively.

    Files that fail to parse are silently skipped so a single corrupt file
    does not break listing.
    """
    target_dir = _resolve_profiles_dir(profiles_dir)
    if not target_dir.exists():
        return []
    names: List[str] = []
    for entry in sorted(target_dir.iterdir()):
        if not entry.is_file() or entry.suffix.lower() != _PROFILE_FILE_SUFFIX:
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = data.get("profile_name") if isinstance(data, dict) else None
        if isinstance(name, str) and name.strip():
            names.append(name)
        else:
            names.append(entry.stem)
    names.sort(key=lambda value: value.lower())
    return names


def delete_profile(profile_name: str, profiles_dir: Optional[PathLike] = None) -> bool:
    """Delete a profile. Returns ``True`` if a file was removed, ``False`` otherwise."""
    target_dir = _resolve_profiles_dir(profiles_dir)
    path = _profile_path(profile_name, target_dir)
    if not path.exists():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------


def _make_built_in_profiles() -> Dict[str, Profile]:
    return {
        "ChatGPT Balanced Project": Profile(
            profile_name="ChatGPT Balanced Project",
            target="chatgpt",
            mode="balanced",
        ),
        "Claude Full Project": Profile(
            profile_name="Claude Full Project",
            target="claude",
            mode="full",
        ),
        "Visual Repair Manual": Profile(
            profile_name="Visual Repair Manual",
            target="claude",
            mode="visual_manual",
            include_assets=True,
            copy_data_files=True,
            include_pdf_page_headers=True,
            include_source_metadata=True,
        ),
        "RAG Ready Export": Profile(
            profile_name="RAG Ready Export",
            target="rag",
            mode="balanced",
            chunk_token_budget=800,
            include_assets=False,
            copy_data_files=True,
        ),
        "Lean One-Shot Chat": Profile(
            profile_name="Lean One-Shot Chat",
            target="generic",
            mode="lean",
            include_assets=False,
            copy_data_files=False,
        ),
    }


_BUILT_IN_PROFILES: Dict[str, Profile] = _make_built_in_profiles()


def list_built_in_profiles() -> List[str]:
    """Return the names of the bundled profile templates, in display order."""
    return list(_BUILT_IN_PROFILES.keys())


def get_built_in_profile(name: str) -> Profile:
    """Return a fresh copy of the named built-in template.

    Raises ``KeyError`` if the name is not a built-in.
    """
    if name not in _BUILT_IN_PROFILES:
        raise KeyError(
            f"Unknown built-in profile {name!r}. Available: {list(_BUILT_IN_PROFILES)}"
        )
    template = _BUILT_IN_PROFILES[name]
    return Profile.from_dict(template.to_dict())
