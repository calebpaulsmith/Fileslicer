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
from .chunking import (
    DEFAULT_HEADING_LEVEL,
    STRATEGY_TOKENS,
    Chunk,
    chunk_document,
    match_heading_patterns,
)
from .config import PackerConfig
from .exporters import (
    InstructionContext,
    assign_bundles_to_manifest,
    write_cowork_bundle,
    write_instructions,
    write_rag_export,
)
from .manifest import Manifest, ManifestEntry
from .markdown_utils import doc_id_for_index, safe_filename
from .readers import ReaderContext, read_file
from .scanner import ScannedFile, match_path_patterns, scan_directory
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
    exclude_files: Optional[Sequence[str]] = None,
    chunk_selections: Optional[Mapping[str, Sequence[int]]] = None,
    chunk_token_budget: Optional[int] = None,
    chunk_strategy: str = STRATEGY_TOKENS,
    chunk_heading_level: int = DEFAULT_HEADING_LEVEL,
    chunk_exclude_headings: Optional[Sequence[str]] = None,
    chunk_min_tokens: int = 0,
    chunk_overlap_tokens: int = 0,
    chunk_split_sentences: bool = False,
    chunk_fence_aware: bool = False,
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
    bundle token budget and, with ``chunk_strategy`` and
    ``chunk_heading_level``, must match the settings used to preview chunks.
    For the ``rag`` target a provided ``chunk_token_budget`` and strategy
    also shape ``rag_ready/chunks.jsonl``; without them the V1 token-based
    behavior is unchanged.

    ``chunk_exclude_headings`` is a corpus-wide rule set: glob patterns
    (case-insensitive, e.g. ``*_html``) matched against each chunk's first
    heading. Matching chunks are dropped from every document that has no
    explicit entry in ``chunk_selections`` — an explicit per-document
    selection always wins over the rules.

    ``exclude_files`` holds glob patterns matched against source-relative
    paths (see ``scanner.match_path_patterns``); matching files are dropped
    after the scan and never appear in the manifest. ``included_files`` is
    an explicit allowlist that already encodes any exclusions, so callers
    pass one or the other, not both.

    ``chunk_min_tokens`` (0 disables) merges chunks under the floor into a
    neighbor wherever documents are chunked — previews, selections, heading
    rules, and the ``rag``/``cowork`` JSONL. ``chunk_overlap_tokens`` (0
    disables) applies only to ``rag_ready/chunks.jsonl``: each chunk is
    prefixed with the tail of its predecessor without moving boundaries, so
    chunk indices and selections are unaffected. ``chunk_split_sentences``
    (default off) splits single lines larger than the chunk budget at
    sentence, then word, boundaries instead of emitting over-budget chunks;
    like ``chunk_min_tokens`` it changes boundaries and applies everywhere
    documents are chunked. ``chunk_fence_aware`` (default off; intended for
    codebases) treats fenced code blocks as atomic so no chunk boundary
    lands inside a fence; a fence larger than the budget is kept whole as
    an over-budget chunk.
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
        exclude_files=exclude_files,
        chunk_selections=chunk_selections,
        chunk_token_budget=chunk_token_budget,
        chunk_strategy=chunk_strategy,
        chunk_heading_level=chunk_heading_level,
        chunk_exclude_headings=chunk_exclude_headings,
        chunk_min_tokens=chunk_min_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
        chunk_split_sentences=chunk_split_sentences,
        chunk_fence_aware=chunk_fence_aware,
        progress_callback=progress_callback,
    )


def run_packaging_config(
    cfg: PackerConfig,
    *,
    included_files: Optional[Iterable[Path | str]] = None,
    exclude_files: Optional[Sequence[str]] = None,
    chunk_selections: Optional[Mapping[str, Sequence[int]]] = None,
    chunk_token_budget: Optional[int] = None,
    chunk_strategy: str = STRATEGY_TOKENS,
    chunk_heading_level: int = DEFAULT_HEADING_LEVEL,
    chunk_exclude_headings: Optional[Sequence[str]] = None,
    chunk_min_tokens: int = 0,
    chunk_overlap_tokens: int = 0,
    chunk_split_sentences: bool = False,
    chunk_fence_aware: bool = False,
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
    if exclude_files:
        files, exclude_warnings = _apply_excluded_files_filter(files, exclude_files)
        warnings.extend(exclude_warnings)
        for warning in exclude_warnings:
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
    effective_chunk_tokens = chunk_token_budget or cfg.max_bundle_tokens
    if chunk_min_tokens and chunk_min_tokens >= effective_chunk_tokens:
        warning = (
            f"chunk_min_tokens ({chunk_min_tokens}) is not below the chunk "
            f"budget ({effective_chunk_tokens}); most chunks will merge up to "
            "the budget."
        )
        warnings.append(warning)
        emit("warning", f"  Warning: {warning}")
    if chunk_selections or chunk_exclude_headings:
        converted_docs = _apply_chunk_selections(
            converted_docs,
            chunk_selections=chunk_selections or {},
            exclude_headings=tuple(chunk_exclude_headings or ()),
            max_chunk_tokens=effective_chunk_tokens,
            chunk_strategy=chunk_strategy,
            chunk_heading_level=chunk_heading_level,
            chunk_min_tokens=chunk_min_tokens,
            chunk_split_sentences=chunk_split_sentences,
            chunk_fence_aware=chunk_fence_aware,
            source_dir=cfg.source_dir,
            warnings=warnings,
            emit=emit,
        )

    bundle_paths: List[Path] = []
    bundle_filenames: List[str] = []
    chunked_targets = {"rag", "cowork"}
    if cfg.target not in chunked_targets:
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
        emit(
            "rag_start",
            f"Target is {cfg.target!r}; chunking documents for retrieval.",
        )
        if chunk_overlap_tokens and chunk_overlap_tokens >= effective_chunk_tokens:
            warning = (
                f"chunk_overlap_tokens ({chunk_overlap_tokens}) is not below "
                f"the chunk budget ({effective_chunk_tokens}); adjacent chunks "
                "will repeat most of their text."
            )
            warnings.append(warning)
            emit("warning", f"  Warning: {warning}")
        rag_dir = export_dir / "rag_ready"
        write_rag_export(
            rag_dir,
            converted_docs=converted_docs,
            max_chunk_tokens=effective_chunk_tokens,
            chunk_strategy=chunk_strategy,
            heading_level=chunk_heading_level,
            min_chunk_tokens=chunk_min_tokens,
            overlap_tokens=chunk_overlap_tokens,
            split_sentences=chunk_split_sentences,
            fence_aware=chunk_fence_aware,
        )
        emit("rag_written", f"  Wrote RAG chunks to {rag_dir}.", {"path": rag_dir})
        if cfg.target == "cowork":
            mcp_dir = write_cowork_bundle(
                export_dir=export_dir,
                project_name=cfg.project_name,
                rag_dir=rag_dir,
            )
            emit(
                "cowork_written",
                f"  Wrote MCP server bundle to {mcp_dir}.",
                {"path": mcp_dir},
            )

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
    exclude_headings: Sequence[str] = (),
    max_chunk_tokens: int,
    chunk_strategy: str = STRATEGY_TOKENS,
    chunk_heading_level: int = DEFAULT_HEADING_LEVEL,
    chunk_min_tokens: int = 0,
    chunk_split_sentences: bool = False,
    chunk_fence_aware: bool = False,
    source_dir: Path,
    warnings: List[str],
    emit: Callable[..., None],
) -> List[ConvertedDoc]:
    normalized = {
        _included_key(path, source_dir): tuple(int(i) for i in indices)
        for path, indices in chunk_selections.items()
    }
    patterns = tuple(p.strip() for p in exclude_headings if p and p.strip())
    pattern_hits: Dict[str, int] = {pattern: 0 for pattern in patterns}
    matched: set[str] = set()
    kept_docs: List[ConvertedDoc] = []
    for doc in converted_docs:
        key = doc.entry.source_path.lower()
        if key not in normalized:
            if patterns:
                kept_docs.extend(
                    _apply_heading_rules(
                        doc,
                        patterns=patterns,
                        pattern_hits=pattern_hits,
                        max_chunk_tokens=max_chunk_tokens,
                        chunk_strategy=chunk_strategy,
                        chunk_heading_level=chunk_heading_level,
                        chunk_min_tokens=chunk_min_tokens,
                        chunk_split_sentences=chunk_split_sentences,
                        chunk_fence_aware=chunk_fence_aware,
                        warnings=warnings,
                        emit=emit,
                    )
                )
            else:
                kept_docs.append(doc)
            continue
        matched.add(key)
        requested = normalized[key]
        chunks = chunk_document(
            doc.body_markdown,
            max_chunk_tokens,
            strategy=chunk_strategy,
            heading_level=chunk_heading_level,
            min_tokens=chunk_min_tokens,
            split_sentences=chunk_split_sentences,
            fence_aware=chunk_fence_aware,
        )
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
    for pattern, hits in pattern_hits.items():
        if hits == 0:
            warning = f"Heading exclusion rule matched no chunks: {pattern!r}"
            warnings.append(warning)
            emit("warning", f"  Warning: {warning}")
    return kept_docs


def _apply_heading_rules(
    doc: ConvertedDoc,
    *,
    patterns: Tuple[str, ...],
    pattern_hits: Dict[str, int],
    max_chunk_tokens: int,
    chunk_strategy: str,
    chunk_heading_level: int,
    chunk_min_tokens: int = 0,
    chunk_split_sentences: bool = False,
    chunk_fence_aware: bool = False,
    warnings: List[str],
    emit: Callable[..., None],
) -> List[ConvertedDoc]:
    chunks = chunk_document(
        doc.body_markdown,
        max_chunk_tokens,
        strategy=chunk_strategy,
        heading_level=chunk_heading_level,
        min_tokens=chunk_min_tokens,
        split_sentences=chunk_split_sentences,
        fence_aware=chunk_fence_aware,
    )
    kept_chunks: List[Chunk] = []
    excluded = 0
    for chunk in chunks:
        hits = match_heading_patterns(chunk.first_heading, patterns)
        if hits:
            excluded += 1
            for pattern in hits:
                pattern_hits[pattern] += 1
        else:
            kept_chunks.append(chunk)
    if not excluded:
        return [doc]
    if not kept_chunks:
        doc.entry.status = "skipped"
        doc.entry.token_estimate = 0
        doc.entry.notes = _append_note(
            doc.entry.notes,
            f"All {len(chunks)} chunks matched corpus heading rules; content omitted.",
        )
        warning = (
            f"{doc.entry.doc_id} {doc.entry.source_path}: every chunk matched "
            "the heading exclusion rules; document omitted from export."
        )
        warnings.append(warning)
        emit("chunk_doc_omitted", f"  {warning}", {"doc_id": doc.entry.doc_id})
        return []
    trimmed_body = "\n\n".join(chunk.text for chunk in kept_chunks)
    trimmed_doc = make_converted_doc(doc.entry, trimmed_body)
    trimmed_doc.entry.token_estimate = trimmed_doc.token_estimate
    trimmed_doc.entry.notes = _append_note(
        trimmed_doc.entry.notes,
        f"Excluded {excluded} of {len(chunks)} chunks via corpus heading rules.",
    )
    emit(
        "chunk_rules_applied",
        f"  {doc.entry.doc_id}: excluded {excluded} of {len(chunks)} chunks by heading rules.",
        {"doc_id": doc.entry.doc_id, "excluded": excluded, "total": len(chunks)},
    )
    return [trimmed_doc]


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
    chunk_strategy: str = STRATEGY_TOKENS,
    chunk_heading_level: int = DEFAULT_HEADING_LEVEL,
    chunk_min_tokens: int = 0,
    chunk_split_sentences: bool = False,
    chunk_fence_aware: bool = False,
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
        chunks=chunk_document(
            result.markdown,
            max_chunk_tokens,
            strategy=chunk_strategy,
            heading_level=chunk_heading_level,
            min_tokens=chunk_min_tokens,
            split_sentences=chunk_split_sentences,
            fence_aware=chunk_fence_aware,
        ),
    )


@dataclass(frozen=True)
class HeadingSummary:
    """Aggregate stats for one first-heading across a corpus chunk audit."""

    heading: str  # "" groups chunks that have no leading heading
    chunk_count: int
    token_estimate: int
    document_count: int


def corpus_heading_summary(
    previews: Mapping[str, DocumentChunkPreview],
) -> List[HeadingSummary]:
    """Aggregate corpus-audit chunks by their first heading.

    Groups case-insensitively (the first casing seen is displayed), counts
    chunks, token estimates, and distinct documents per heading, and sorts
    by token estimate descending. Chunks without a leading heading group
    under the empty string.
    """
    stats: Dict[str, Dict[str, Any]] = {}
    for path, preview in previews.items():
        if preview.status != "ok":
            continue
        for chunk in preview.chunks:
            heading = chunk.first_heading.strip()
            key = heading.lower()
            entry = stats.setdefault(
                key,
                {"heading": heading, "chunks": 0, "tokens": 0, "docs": set()},
            )
            entry["chunks"] += 1
            entry["tokens"] += chunk.token_estimate
            entry["docs"].add(path)
    summaries = [
        HeadingSummary(
            heading=entry["heading"],
            chunk_count=entry["chunks"],
            token_estimate=entry["tokens"],
            document_count=len(entry["docs"]),
        )
        for entry in stats.values()
    ]
    summaries.sort(key=lambda item: (-item.token_estimate, item.heading.lower()))
    return summaries


def chunking_guidance(
    previews: Mapping[str, DocumentChunkPreview],
    max_chunk_tokens: int,
    chunk_strategy: str,
    target: str,
) -> List[str]:
    """Return plain-language tips for improving the current chunking setup.

    Rules-based interpretation of a corpus chunking audit; the UI shows the
    returned strings verbatim. An empty list means nothing stood out.
    """
    converted = [p for p in previews.values() if p.status == "ok"]
    chunks = [chunk for preview in converted for chunk in preview.chunks]
    tips: List[str] = []
    if not chunks:
        return tips

    over_budget = sum(1 for c in chunks if c.token_estimate > max_chunk_tokens)
    if over_budget:
        tips.append(
            f"{over_budget} chunk(s) exceed the {max_chunk_tokens:,}-token budget "
            "because a single line (often a table or one-line paragraph) or a "
            "code block kept whole cannot be split. Enable sentence splitting "
            "for oversize lines, raise the chunk size to absorb them, or "
            "accept them knowingly — for RAG they reduce retrieval precision."
        )

    heading_count = sum(
        len(c.structure.headings) for c in chunks if c.structure is not None
    )
    if chunk_strategy != "headings" and heading_count >= 3 * len(converted):
        tips.append(
            f"The corpus is heading-rich ({heading_count} headings across "
            f"{len(converted)} document(s)). The 'headings' strategy would align "
            "chunk boundaries with the documents' own sections, which usually "
            "retrieves and cites better than paragraph packing."
        )

    tiny_threshold = max(30, max_chunk_tokens // 10)
    tiny = sum(1 for c in chunks if c.token_estimate < tiny_threshold)
    if chunk_strategy == "headings" and tiny > len(chunks) // 4:
        tips.append(
            f"{tiny} of {len(chunks)} chunks are under {tiny_threshold} tokens — "
            "typically small metadata or boilerplate sections. Set a minimum "
            "chunk size to merge them into neighbors, deselect them during "
            "review, split at a shallower heading level, or accept them if "
            "those fields matter for lookup."
        )

    single_chunk_docs = sum(1 for p in converted if len(p.chunks) == 1)
    if single_chunk_docs > len(converted) // 2 and len(converted) > 1:
        tips.append(
            f"{single_chunk_docs} of {len(converted)} document(s) fit in a single "
            "chunk, so chunking has no effect on them. That is fine for project "
            "bundles; for RAG, a smaller chunk size gives retrieval more focused "
            "passages to match."
        )

    if target == "rag" and max_chunk_tokens > 1500:
        tips.append(
            f"The chunk size ({max_chunk_tokens:,} tokens) is large for RAG. "
            "Retrieval precision usually improves between roughly 300 and 800 "
            "tokens per chunk, where each chunk holds one self-contained idea."
        )

    return tips


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


def _apply_excluded_files_filter(
    files: List[ScannedFile],
    exclude_files: Sequence[str],
) -> Tuple[List[ScannedFile], List[str]]:
    patterns = [p.strip() for p in exclude_files if p and p.strip()]
    pattern_hits: Dict[str, int] = {pattern: 0 for pattern in patterns}
    kept: List[ScannedFile] = []
    for file in files:
        hits = match_path_patterns(file.relative_path, patterns)
        if hits:
            for pattern in hits:
                pattern_hits[pattern] += 1
        else:
            kept.append(file)
    warnings = [
        f"File exclusion pattern matched no files: {pattern!r}"
        for pattern, hits in pattern_hits.items()
        if hits == 0
    ]
    return kept, warnings


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
