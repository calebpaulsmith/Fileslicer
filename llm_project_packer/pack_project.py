"""Command-line entry point for llm_project_packer.

Usage:
    python pack_project.py ./source_files --target chatgpt --mode balanced
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from packer import presets
from packer.bundler import (
    ConvertedDoc,
    make_converted_doc,
    split_into_bundles,
    write_bundle,
)
from packer.config import PackerConfig
from packer.exporters import (
    InstructionContext,
    assign_bundles_to_manifest,
    write_instructions,
    write_rag_export,
)
from packer.manifest import Manifest, ManifestEntry
from packer.markdown_utils import doc_id_for_index, safe_filename
from packer.readers import ReaderContext, read_file
from packer.scanner import scan_directory
from packer.token_estimator import estimate_tokens, estimator_backend


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


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run(cfg: PackerConfig) -> Path:
    """Execute one packing run end-to-end and return the export directory path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_name = safe_filename(
        f"{cfg.project_name}_{cfg.target}_{cfg.mode}_{timestamp}"
    )
    export_dir = cfg.output_dir / export_name
    assets_dir = export_dir / "assets"
    data_dir = export_dir / "data"
    export_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"llm_project_packer v1")
    print(f"  Source:    {cfg.source_dir}")
    print(f"  Output:    {export_dir}")
    print(f"  Target:    {cfg.target}")
    print(f"  Mode:      {cfg.mode}")
    print(f"  Budget:    {cfg.max_bundle_tokens:,} tokens / bundle")
    print(f"  Estimator: {estimator_backend()}")
    print()

    print("Scanning files...")
    scan_exclude_dirs = set(cfg.exclude_dirs)
    if _path_is_relative_to(cfg.output_dir, cfg.source_dir):
        scan_exclude_dirs.add(cfg.output_dir.name)
        print(f"  Skipping output directory during scan: {cfg.output_dir.name}")
    files = scan_directory(
        source_dir=cfg.source_dir,
        include_extensions=cfg.include_extensions,
        exclude_dirs=tuple(scan_exclude_dirs),
    )
    print(f"  Found {len(files)} files to record/process.")
    if not files:
        print("No matching files found. Nothing to do.")
        return export_dir

    manifest = Manifest(
        project_name=cfg.project_name,
        target=cfg.target,
        mode=cfg.mode,
    )
    reader_ctx = ReaderContext(
        source_root=cfg.source_dir,
        assets_dir=assets_dir,
        data_dir=data_dir,
    )

    converted_docs: List[ConvertedDoc] = []

    for index, scanned in enumerate(files, start=1):
        doc_id = doc_id_for_index(index)
        rel_str = scanned.relative_path.as_posix()
        print(f"  Processing {doc_id} {rel_str}...")
        result = read_file(scanned, doc_id=doc_id, ctx=reader_ctx)

        entry = ManifestEntry(
            doc_id=doc_id,
            source_file=scanned.relative_path.name,
            source_path=rel_str,
            original_extension=scanned.extension,
            file_type=scanned.file_type,
            status=result.status,
            char_count=result.char_count,
            word_count=result.word_count,
            notes=result.notes,
        )

        if result.status == "ok" and result.markdown.strip():
            doc = make_converted_doc(entry, result.markdown)
            entry.token_estimate = doc.token_estimate
            converted_docs.append(doc)
            print(
                f"    Extracted {result.char_count:,} chars / "
                f"{doc.token_estimate:,} tokens."
            )
        elif result.status == "ok":
            # ok but empty body — still counts as present, just nothing to bundle.
            entry.token_estimate = estimate_tokens(result.markdown)
            print("    Reader returned no content; recorded in manifest only.")
        elif result.status == "skipped":
            print(f"    Skipped: {result.notes}")
        else:
            print(f"    FAILED: {result.notes}")

        manifest.add(entry)

    # ----- Bundle (skip for rag target; rag uses chunks instead) -----
    bundle_filenames: List[str] = []
    if cfg.target != "rag":
        print("\nBundling documents...")
        bundles = split_into_bundles(converted_docs, cfg.max_bundle_tokens)
        print(f"  Created {len(bundles)} bundles.")
        for bundle in bundles:
            path = write_bundle(
                bundle,
                output_dir=export_dir,
                project_name=cfg.project_name,
                target=cfg.target,
                mode=cfg.mode,
                max_bundle_tokens=cfg.max_bundle_tokens,
                total_bundles=len(bundles),
            )
            bundle_filenames.append(path.name)
            print(
                f"  Wrote {path.name} ({bundle.total_tokens:,} tokens, "
                f"{len(bundle.docs)} docs)."
            )
        assign_bundles_to_manifest(manifest, bundles)
    else:
        print("\nTarget is 'rag'; skipping Markdown bundling.")
        rag_dir = export_dir / "rag_ready"
        write_rag_export(
            rag_dir,
            converted_docs=converted_docs,
            max_chunk_tokens=cfg.max_bundle_tokens,
        )
        print(f"  Wrote RAG chunks to {rag_dir}.")

    # ----- Manifest files -----
    print("\nWriting manifest...")
    manifest.write_markdown(export_dir / "01_SOURCE_MANIFEST.md")
    manifest.write_csv(export_dir / "manifest.csv")
    manifest.write_json(export_dir / "manifest.json")

    # ----- Instruction files -----
    instruction_ctx = InstructionContext(
        project_name=cfg.project_name,
        target=cfg.target,
        mode=cfg.mode,
        bundle_filenames=bundle_filenames,
        total_documents=len(manifest.entries),
        total_tokens=sum(e.token_estimate for e in manifest.entries),
        max_bundle_tokens=cfg.max_bundle_tokens,
    )
    instruction_path = write_instructions(cfg.target, export_dir, instruction_ctx)
    print(f"  Wrote {instruction_path.name}.")

    print(f"\nExport complete: {export_dir}")
    return export_dir


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
