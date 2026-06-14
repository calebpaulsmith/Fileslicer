"""Command-line entry point for llm_project_packer.

Usage:
    python pack_project.py ./source_files --target chatgpt --mode balanced
    python pack_project.py ./source_files --profile "RAG Ready Export"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

from packer import presets, profiles
from packer.config import PackerConfig
from packer.pipeline import (
    PackResult,
    ProgressEvent,
    run_packaging_config,
    run_packaging_job,
)


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


def _parse_csv_list(value: str) -> Tuple[str, ...]:
    if not value:
        return ()
    items = [item.strip() for item in value.split(",")]
    return tuple(item for item in items if item)


def _parse_extensions(value: str) -> Tuple[str, ...]:
    items = _parse_csv_list(value)
    normalized = []
    for item in items:
        ext = item.lower()
        if not ext.startswith("."):
            ext = "." + ext
        normalized.append(ext)
    return tuple(normalized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pack_project.py",
        description="Pack a folder of mixed source files into upload-ready "
        "Markdown bundles for ChatGPT, Claude, generic LLMs, or RAG.",
        epilog=(
            "Examples:\n"
            "  python pack_project.py ./sample_input --target chatgpt --mode balanced\n"
            "  python pack_project.py ./docs --target claude --mode lean\n"
            "  python pack_project.py ./kb --target rag --mode balanced\n"
            '  python pack_project.py ./kb --profile "RAG Ready Export"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source_dir",
        type=Path,
        nargs="?",
        default=None,
        help="Folder of source files to scan recursively. Optional when "
        "--profile supplies a default source folder.",
    )
    parser.add_argument(
        "--target",
        choices=presets.TARGETS,
        default=None,
        help="Output target. Required unless --profile is given.",
    )
    parser.add_argument(
        "--mode",
        choices=presets.MODES,
        default=None,
        help="Packaging mode (controls token budget per bundle). "
        "Required unless --profile is given.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: ./llm_project_exports).",
    )
    parser.add_argument(
        "--max-bundle-tokens",
        type=int,
        default=None,
        help="Override the per-bundle token budget. Defaults to the target/mode preset.",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Project name. Defaults to the source folder name.",
    )
    parser.add_argument(
        "--include-extensions",
        type=str,
        default="",
        help="Comma-separated list of extensions to include (e.g. .md,.txt,.html,.pdf). "
        "Defaults to the built-in set.",
    )
    parser.add_argument(
        "--exclude-dirs",
        type=str,
        default="",
        help="Comma-separated list of directory names to skip. Adds to the built-in defaults.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Run with a saved profile (from ~/.llm_project_packer/profiles/) "
        "or a built-in template, by name. The profile supplies source/target/"
        "mode/chunking settings; explicit flags override its values.",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=None,
        help="Directory to load saved profiles from "
        "(default: ~/.llm_project_packer/profiles).",
    )
    parser.add_argument(
        "--appeals-db",
        type=Path,
        default=None,
        help="Package FEMA appeals from a pa_rag SQLite database "
        "(pa_appeals.sqlite3) instead of scanning a folder. When set, "
        "source_dir is not required.",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="For --target cowork: embed chunks for vector/hybrid search. "
        "Use 'hashing' (offline, default for the Local Hybrid RAG profile), "
        "'openai:text-embedding-3-small', or 'voyage:voyage-3'. API backends "
        "send chunk text to the provider.",
    )
    return parser


def enforce_required_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Replicate argparse's missing-required errors when no profile is given.

    ``source_dir``, ``--target``, and ``--mode`` are only optional in the
    parser so that ``--profile`` can supply them; without a profile they stay
    required with the same error message and exit code as before.
    """
    if args.profile:
        return
    missing = []
    if args.source_dir is None and args.appeals_db is None:
        missing.append("source_dir")
    if args.target is None:
        missing.append("--target")
    if args.mode is None:
        missing.append("--mode")
    if missing:
        parser.error("the following arguments are required: " + ", ".join(missing))


def build_config_from_args(args: argparse.Namespace) -> PackerConfig:
    include_exts = _parse_extensions(args.include_extensions) or presets.DEFAULT_INCLUDE_EXTENSIONS
    extra_exclude = _parse_csv_list(args.exclude_dirs)
    exclude_dirs = tuple(set(presets.DEFAULT_EXCLUDE_DIRS) | set(extra_exclude))
    max_tokens = args.max_bundle_tokens or presets.get_bundle_token_budget(args.target, args.mode)
    output_dir = (args.output or Path("./llm_project_exports")).expanduser().resolve()

    if args.appeals_db is not None:
        appeals_db = args.appeals_db.expanduser().resolve()
        project_name = args.project_name or appeals_db.stem or "appeals"
        cfg = PackerConfig(
            source_dir=appeals_db.parent,
            output_dir=output_dir,
            target=args.target,
            mode=args.mode,
            project_name=project_name,
            max_bundle_tokens=max_tokens,
            include_extensions=include_exts,
            exclude_dirs=exclude_dirs,
            source_kind="appeals",
            appeals_db=appeals_db,
            embedding_model=args.embedding_model or "",
        )
        cfg.validate()
        return cfg

    source_dir = args.source_dir.expanduser().resolve()
    project_name = args.project_name or source_dir.name or "project"
    cfg = PackerConfig(
        source_dir=source_dir,
        output_dir=output_dir,
        target=args.target,
        mode=args.mode,
        project_name=project_name,
        max_bundle_tokens=max_tokens,
        include_extensions=include_exts,
        exclude_dirs=exclude_dirs,
        embedding_model=args.embedding_model or "",
    )
    cfg.validate()
    return cfg


def _load_cli_profile(name: str, profiles_dir: Path | None) -> profiles.Profile:
    try:
        return profiles.load_profile(name, profiles_dir=profiles_dir)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as exc:
        raise ValueError(f"Profile {name!r} is not valid JSON: {exc}") from exc
    try:
        return profiles.get_built_in_profile(name)
    except KeyError:
        saved = profiles.list_profiles(profiles_dir=profiles_dir)
        raise ValueError(
            f"Unknown profile {name!r}. "
            f"Saved profiles: {', '.join(saved) if saved else '(none)'}. "
            f"Built-in templates: {', '.join(profiles.list_built_in_profiles())}."
        ) from None


def build_job_kwargs_from_profile(args: argparse.Namespace) -> Dict[str, Any]:
    """Resolve ``--profile`` plus CLI overrides into ``run_packaging_job`` kwargs."""
    profile = _load_cli_profile(args.profile, args.profiles_dir)
    kwargs = profile.to_packaging_kwargs(
        source_dir=args.source_dir,
        output_dir=args.output,
        project_name=args.project_name,
        appeals_db=args.appeals_db,
    )
    if args.target:
        kwargs["target"] = args.target
    if args.mode:
        kwargs["mode"] = args.mode
    if args.max_bundle_tokens:
        kwargs["max_bundle_tokens"] = args.max_bundle_tokens
    if args.embedding_model is not None:
        kwargs["embedding_model"] = args.embedding_model
    include_exts = _parse_extensions(args.include_extensions)
    if include_exts:
        kwargs["include_extensions"] = include_exts
    extra_exclude = _parse_csv_list(args.exclude_dirs)
    if extra_exclude:
        existing = tuple(kwargs.get("exclude_dirs") or ())
        kwargs["exclude_dirs"] = tuple(set(existing) | set(extra_exclude))
    if kwargs.get("source_kind") == "appeals":
        appeals_db = Path(kwargs["appeals_db"]).expanduser().resolve()
        if not appeals_db.exists() or not appeals_db.is_file():
            raise ValueError(
                f"Appeals database does not exist or is not a file: {appeals_db}"
            )
        kwargs["appeals_db"] = str(appeals_db)
    else:
        source_dir = Path(kwargs["source_dir"]).expanduser().resolve()
        if not source_dir.exists() or not source_dir.is_dir():
            raise ValueError(
                f"Source directory does not exist or is not a directory: {source_dir}"
            )
    return kwargs


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _print_progress(event: ProgressEvent) -> None:
    print(event.message)


def run(cfg: PackerConfig) -> Path:
    """Execute one packing run end-to-end and return the export directory path."""
    result = run_job(cfg)
    return result.export_dir


def run_job(cfg: PackerConfig) -> PackResult:
    """Execute one packing run and return a structured result."""
    return run_packaging_config(cfg, progress_callback=_print_progress)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    if not argv:
        parser.print_help(sys.stderr)
        print(
            "\nerror: source_dir, --target, and --mode are required. "
            "If you are running from VS Code, add command-line arguments "
            "or run one of the example commands above in PowerShell.",
            file=sys.stderr,
        )
        return 2
    args = parser.parse_args(argv)
    enforce_required_args(parser, args)
    try:
        if args.profile:
            job_kwargs = build_job_kwargs_from_profile(args)
            cfg = None
        else:
            cfg = build_config_from_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        if cfg is None:
            run_packaging_job(**job_kwargs, progress_callback=_print_progress)
        else:
            run(cfg)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as exc:  # pragma: no cover
        import traceback

        traceback.print_exc()
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
