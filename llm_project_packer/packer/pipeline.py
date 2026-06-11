"""Reusable packaging pipeline shared by the CLI and future UI adapters."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import presets
from .bundler import (
    ConvertedDoc,
    make_converted_doc,
    split_into_bundles,
    write_bundle,
)
from .chunking import Chunk, chunk_document
from .config import PackerConfig
from .exporters import (
    InstructionContext,
    assign_bundles_to_manifest,
    write_instructions,
    write_rag_export,
)
from .manifest import Manifest, ManifestEntry
from .markdown_utils import doc_id_for_index, safe_filename
from .readers import ReaderContext, read_file
from .scanner import ScannedFile, scan_directory
from .token_estimator import estimate_tokens, estimator_backend


@dataclass(frozen=True)
class ProgressEvent:
    """A progress update emitted by the packaging pipeline."""

    kind: str
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


ProgressCallback = Callable[[ProgressEvent], None]


@dataclass
class PackResult:
    """Structured outcome from a packaging job."""

    export_dir: Path
    instruction_path: Optional[Path]
    manifest_paths: Dict[str, Path]
    bundle_paths: List[Path]
    zip_path: Optional[Path]
    processed_count: int
    failed_count: int
    skipped_count: int
    total_token_estimate: int
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def run_packaging_job(
    source_dir,
    output_dir=Path("./llm_project_exports"),
    project_name: Optional[str] = None,
    target: str = "chatgpt",
    mode: str = "balanced",
    max_bundle_tokens: Optional[int] = None,
    include_extensions: Optional[Iterable[str]] = None,
    exclude_dirs: Optional[Iterable[str]] = None,
    included_files: Optional[Iterable[Path | str]] = None,
    chunk_selections: Optional[Mapping[str, Sequence[int]]] = None,
    chunk_token_budget: Optional[int] = None,
    options: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> PackResult:
    """Run a complete packaging job from plain arguments.

    This is the public backend entry point intended for both the current CLI
    and future UI adapters. The UI should pass user selections here instead of
    duplicating scan, convert, bundle, manifest, or export logic.

    ``chunk_selections`` maps source-relative paths to the 1-based chunk
    indices to keep, where chunks are computed by
    ``chunking.chunk_document(body, chunk_token_budget)``. Documents without
    an entry keep their full content; an explicit empty selection records the
    document as skipped. ``chunk_token_budget`` defaults to the resolved
    bundle token budget and must match the budget used to preview chunks.
    """
    del options
    source_path = Path(source_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    included_file_list = tuple(included_files) if included_files is not None else None
    include_exts = _normalize_extensions(include_extensions) or presets.DEFAULT_INCLUDE_EXTENSIONS
    if included_file_list is not None:
        include_exts = _include_selected_file_extensions(include_exts, included_file_list)
    exclude = tuple(set(presets.DEFAULT_EXCLUDE_DIRS) | set(exclude_dirs or ()))
    max_tokens = max_bundle_tokens or presets.get_bundle_token_budget(target, mode)
    cfg = PackerConfig(
        source_dir=source_path,
        output_dir=output_path,
        target=target,
        mode=mode,
        project_name=project_name or source_path.name or "project",
        max_bundle_tokens=max_tokens,
        include_extensions=include_exts,
        exclude_dirs=exclude,
    )
    cfg.validate()
    return run_packaging_config(
        cfg,
        included_files=included_file_list,
        chunk_selections=chunk_selections,
        chunk_token_budget=chunk_token_budget,
        progress_callback=progress_callback,
    )


def run_packaging_config(
    cfg: PackerConfig,
    *,
    included_files: Optional[Iterable[Path | str]] = None,
    chunk_selections: Optional[Mapping[str, Sequence[int]]] = None,
    chunk_token_budget: Optional[int] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> PackResult:
    """Run a complete packaging job from a validated ``PackerConfig``."""
    emit = _emitter(progress_callback)
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

    emit("header", "llm_project_packer v1")
    emit("header", f"  Source:    {cfg.source_dir}")
    emit("header", f"  Output:    {export_dir}")
    emit("header", f"  Target:    {cfg.target}")
    emit("header", f"  Mode:      {cfg.mode}")
    emit("header", f"  Budget:    {cfg.max_bundle_tokens:,} tokens / bundle")
    emit("header", f"  Estimator: {estimator_backend()}")
    emit("blank", "")

    warnings: List[str] = []
    errors: List[str] = []

    emit("scan_start", "Scanning files...")
    scan_exclude_dirs = set(cfg.exclude_dirs)
    if _path_is_relative_to(cfg.output_dir, cfg.source_dir):
        scan_exclude_dirs.add(cfg.output_dir.name)
        emit("scan_skip_output", f"  Skipping output directory during scan: {cfg.output_dir.name}")

    files = scan_directory(
        source_dir=cfg.source_dir,
        include_extensions=cfg.include_extensions,
        exclude_dirs=tuple(scan_exclude_dirs),
    )
    files, include_warnings = _apply_included_files_filter(files, included_files, cfg.source_dir)
    warnings.extend(include_warnings)
    for warning in include_warnings:
        emit("warning", f"  Warning: {warning}")

    emit("scan_done", f"  Found {len(files)} files to record/process.", {"count": len(files)})
    if not files:
        emit("no_files", "No matching files found. Nothing to do.")
        return PackResult(
            export_dir=export_dir,
            instruction_path=None,
            manifest_paths={},
            bundle_paths=[],
            zip_path=None,
            processed_count=0,
            failed_count=0,
            skipped_count=0,
            total_token_estimate=0,
            warnings=warnings,
            errors=errors,
        )

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
    converted_docs = _convert_files(files, reader_ctx, manifest, warnings, errors, emit)
    if chunk_selections:
        converted_docs = _apply_chunk_selections(
            converted_docs,
            chunk_selections=chunk_selections,
            max_chunk_tokens=chunk_token_budget or cfg.max_bundle_tokens,
            source_dir=cfg.source_dir,
            warnings=warnings,
            emit=emit,
        )

    bundle_paths: List[Path] = []
    bundle_filenames: List[str] = []
    if cfg.target != "rag":
        emit("blank", "")
        emit("bundle_start", "Bundling documents...")
        bundles = split_into_bundles(converted_docs, cfg.max_bundle_tokens)
        emit("bundle_done", f"  Created {len(bundles)} bundles.", {"count": len(bundles)})
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
            bundle_paths.append(path)
            bundle_filenames.append(path.name)
            emit(
                "bundle_written",
                f"  Wrote {path.name} ({bundle.total_tokens:,} tokens, {len(bundle.docs)} docs).",
                {"path": path, "tokens": bundle.total_tokens, "doc_count": len(bundle.docs)},
            )
        assign_bundles_to_manifest(manifest, bundles)
    else:
        emit("blank", "")
        emit("rag_start", "Target is 'rag'; skipping Markdown bundling.")
        rag_dir = export_dir / "rag_ready"
        write_rag_export(
            rag_dir,
            converted_docs=converted_docs,
            max_chunk_tokens=cfg.max_bundle_tokens,
        )
        emit("rag_written", f"  Wrote RAG chunks to {rag_dir}.", {"path": rag_dir})

    emit("blank", "")
    emit("manifest_start", "Writing manifest...")
    manifest_paths = {
        "markdown": export_dir / "01_SOURCE_MANIFEST.md",
        "csv": export_dir / "manifest.csv",
        "json": export_dir / "manifest.json",
    }
    manifest.write_markdown(manifest_paths["markdown"])
    manifest.write_csv(manifest_paths["csv"])
    manifest.write_json(manifest_paths["json"])

    total_tokens = sum(e.token_estimate for e in manifest.entries)
    instruction_ctx = InstructionContext(
        project_name=cfg.project_name,
        target=cfg.target,
        mode=cfg.mode,
        bundle_filenames=bundle_filenames,
        total_documents=len(manifest.entries),
        total_tokens=total_tokens,
        max_bundle_tokens=cfg.max_bundle_tokens,
    )
    instruction_path = write_instructions(cfg.target, export_dir, instruction_ctx)
    emit("instruction_written", f"  Wrote {instruction_path.name}.", {"path": instruction_path})
    emit("blank", "")
    emit("complete", f"Export complete: {export_dir}", {"path": export_dir})

    return PackResult(
        export_dir=export_dir,
        instruction_path=instruction_path,
        manifest_paths=manifest_paths,
        bundle_paths=bundle_paths,
        zip_path=None,
        processed_count=len(manifest.entries),
        failed_count=sum(1 for e in manifest.entries if e.status == "failed"),
        skipped_count=sum(1 for e in manifest.entries if e.status == "skipped"),
        total_token_estimate=total_tokens,
        warnings=warnings,
        errors=errors,
    )


def _convert_files(
    files: Sequence[ScannedFile],
    reader_ctx: ReaderContext,
    manifest: Manifest,
    warnings: List[str],
    errors: List[str],
    emit: Callable[[str, str, Optional[Dict[str, Any]]], None],
) -> List[ConvertedDoc]:
    converted_docs: List[ConvertedDoc] = []
    for index, scanned in enumerate(files, start=1):
        doc_id = doc_id_for_index(index)
        rel_str = scanned.relative_path.as_posix()
        emit("file_start", f"  Processing {doc_id} {rel_str}...", {"doc_id": doc_id, "path": rel_str})
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
            emit(
                "file_extracted",
                f"    Extracted {result.char_count:,} chars / {doc.token_estimate:,} tokens.",
                {"doc_id": doc_id, "char_count": result.char_count, "token_estimate": doc.token_estimate},
            )
        elif result.status == "ok":
            entry.token_estimate = estimate_tokens(result.markdown)
            emit("file_empty", "    Reader returned no content; recorded in manifest only.", {"doc_id": doc_id})
        elif result.status == "skipped":
            warning = f"{doc_id} {rel_str}: {result.notes}"
            warnings.append(warning)
            emit("file_skipped", f"    Skipped: {result.notes}", {"doc_id": doc_id, "notes": result.notes})
        else:
            error = f"{doc_id} {rel_str}: {result.notes}"
            errors.append(error)
            emit("file_failed", f"    FAILED: {result.notes}", {"doc_id": doc_id, "notes": result.notes})

        manifest.add(entry)
    return converted_docs


def _apply_chunk_selections(
    converted_docs: List[ConvertedDoc],
    *,
    chunk_selections: Mapping[str, Sequence[int]],
    max_chunk_tokens: int,
    source_dir: Path,
    warnings: List[str],
    emit: Callable[..., None],
) -> List[ConvertedDoc]:
    normalized = {
        _included_key(path, source_dir): tuple(int(i) for i in indices)
        for path, indices in chunk_selections.items()
    }
    matched: set[str] = set()
    kept_docs: List[ConvertedDoc] = []
    for doc in converted_docs:
        key = doc.entry.source_path.lower()
        if key not in normalized:
            kept_docs.append(doc)
            continue
        matched.add(key)
        requested = normalized[key]
        chunks = chunk_document(doc.body_markdown, max_chunk_tokens)
        if not requested:
            doc.entry.status = "skipped"
            doc.entry.token_estimate = 0
            doc.entry.notes = _append_note(
                doc.entry.notes,
                "All chunks were deselected during chunk review; content omitted.",
            )
            warning = (
                f"{doc.entry.doc_id} {doc.entry.source_path}: all chunks deselected; "
                "document omitted from export."
            )
            warnings.append(warning)
            emit("chunk_doc_omitted", f"  {warning}", {"doc_id": doc.entry.doc_id})
            continue
        valid = sorted({i for i in requested if 1 <= i <= len(chunks)})
        invalid = sorted(set(requested) - set(valid))
        if invalid:
            warning = (
                f"{doc.entry.doc_id} {doc.entry.source_path}: chunk indices out of "
                f"range were ignored: {invalid} (document has {len(chunks)} chunks)"
            )
            warnings.append(warning)
            emit("warning", f"  Warning: {warning}")
        if not valid or len(valid) == len(chunks):
            kept_docs.append(doc)
            continue
        trimmed_body = "\n\n".join(chunks[i - 1].text for i in valid)
        trimmed_doc = make_converted_doc(doc.entry, trimmed_body)
        trimmed_doc.entry.token_estimate = trimmed_doc.token_estimate
        trimmed_doc.entry.notes = _append_note(
            trimmed_doc.entry.notes,
            f"Partial content: kept {len(valid)} of {len(chunks)} chunks via chunk review.",
        )
        emit(
            "chunk_selection_applied",
            f"  {doc.entry.doc_id}: kept {len(valid)} of {len(chunks)} chunks.",
            {"doc_id": doc.entry.doc_id, "kept": len(valid), "total": len(chunks)},
        )
        kept_docs.append(trimmed_doc)

    for key in sorted(set(normalized) - matched):
        warning = f"Chunk selection ignored for unprocessed or excluded file: {key}"
        warnings.append(warning)
        emit("warning", f"  Warning: {warning}")
    return kept_docs


def _append_note(existing: str, note: str) -> str:
    return f"{existing}; {note}" if existing else note


@dataclass
class DocumentChunkPreview:
    """Chunks for one source file, converted in a throwaway workspace."""

    status: str
    notes: str
    chunks: List[Chunk]

    @property
    def total_tokens(self) -> int:
        return sum(chunk.token_estimate for chunk in self.chunks)


def preview_document_chunks(
    scanned: ScannedFile,
    source_root: Path,
    max_chunk_tokens: int,
) -> DocumentChunkPreview:
    """Convert one file in a temporary workspace and return its chunk preview.

    Intended for UI adapters that let the user review and select chunks before
    export. Asset/data copies made during conversion land in a temp directory
    and are discarded. The placeholder doc id matches the length of real
    ``DOC_xxxx`` ids so asset links don't shift chunk boundaries at export.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        ctx = ReaderContext(
            source_root=Path(source_root).expanduser().resolve(),
            assets_dir=tmp_path / "assets",
            data_dir=tmp_path / "data",
        )
        result = read_file(scanned, doc_id="DOC_0000", ctx=ctx)
    if result.status != "ok":
        return DocumentChunkPreview(status=result.status, notes=result.notes, chunks=[])
    return DocumentChunkPreview(
        status="ok",
        notes=result.notes,
        chunks=chunk_document(result.markdown, max_chunk_tokens),
    )


def _normalize_extensions(values: Optional[Iterable[str]]) -> Tuple[str, ...]:
    if values is None:
        return ()
    normalized: List[str] = []
    for item in values:
        ext = str(item).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        normalized.append(ext)
    return tuple(normalized)


def _include_selected_file_extensions(
    include_exts: Tuple[str, ...],
    included_files: Iterable[Path | str],
) -> Tuple[str, ...]:
    extras = []
    for file_path in included_files:
        suffix = Path(file_path).suffix.lower()
        if suffix and suffix not in include_exts:
            extras.append(suffix)
    return tuple(dict.fromkeys((*include_exts, *extras)))


def _apply_included_files_filter(
    files: List[ScannedFile],
    included_files: Optional[Iterable[Path | str]],
    source_dir: Path,
) -> Tuple[List[ScannedFile], List[str]]:
    if included_files is None:
        return files, []
    wanted = {_included_key(item, source_dir) for item in included_files}
    filtered = [file for file in files if file.relative_path.as_posix().lower() in wanted]
    found = {file.relative_path.as_posix().lower() for file in filtered}
    missing = sorted(wanted - found)
    warnings = [f"Included file was not found or was excluded: {path}" for path in missing]
    return filtered, warnings


def _included_key(value: Path | str, source_dir: Path) -> str:
    path = Path(value)
    try:
        if path.is_absolute():
            path = path.resolve().relative_to(source_dir)
    except ValueError:
        pass
    return path.as_posix().strip("/").lower()


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _emitter(progress_callback: Optional[ProgressCallback]):
    def emit(kind: str, message: str = "", data: Optional[Dict[str, Any]] = None) -> None:
        if progress_callback is not None:
            progress_callback(ProgressEvent(kind=kind, message=message, data=data or {}))

    return emit
