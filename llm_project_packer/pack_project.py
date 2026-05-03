"""Command-line entry point for llm_project_packer.

Usage:
    python pack_project.py ./source_files --target chatgpt --mode balanced
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

from packer import presets
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
            "  python pack_project.py ./kb --target rag --mode balanced"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source_dir",
        type=Path,
        help="Folder of source files to scan recursively.",
    )
    parser.add_argument(
        "--target",
        choices=presets.TARGETS,
        required=True,
        help="Output target.",
    )
    parser.add_argument(
        "--mode",
        choices=presets.MODES,
        required=True,
        help="Packaging mode (controls token budget per bundle).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./llm_project_exports"),
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
    return parser


def build_config_from_args(args: argparse.Namespace) -> PackerConfig:
    source_dir = args.source_dir.expanduser().resolve()
    project_name = args.project_name or source_dir.name or "project"
    include_exts = _parse_extensions(args.include_extensions) or presets.DEFAULT_INCLUDE_EXTENSIONS
    extra_exclude = _parse_csv_list(args.exclude_dirs)
    exclude_dirs = tuple(set(presets.DEFAULT_EXCLUDE_DIRS) | set(extra_exclude))
    max_tokens = args.max_bundle_tokens or presets.get_bundle_token_budget(args.target, args.mode)

    cfg = PackerConfig(
        source_dir=source_dir,
        output_dir=args.output.expanduser().resolve(),
        target=args.target,
        mode=args.mode,
        project_name=project_name,
        max_bundle_tokens=max_tokens,
        include_extensions=include_exts,
        exclude_dirs=exclude_dirs,
    )
    cfg.validate()
    return cfg


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
    try:
        cfg = build_config_from_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
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
