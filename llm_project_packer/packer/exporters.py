"""Generate platform-specific instruction files and the RAG / Cowork exports."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .bundler import Bundle, ConvertedDoc
from .chunking import (
    DEFAULT_HEADING_LEVEL,
    HEADING_PATH_BOTH,
    HEADING_PATH_METADATA,
    HEADING_PATH_OFF,
    HEADING_PATH_PREFIX,
    STRATEGY_HEADINGS,
    STRATEGY_TOKENS,
    apply_chunk_overlap,
    apply_heading_path_prefix,
    chunk_markdown_by_headings_with_reasons,
    chunk_markdown_with_reasons,
    heading_paths_for_texts,
    merge_undersized_chunks,
)
from .guidance import DESTINATION_LABELS
from .manifest import Manifest
from .markdown_utils import rows_to_markdown_table, safe_filename
from .token_estimator import estimate_tokens, estimator_backend


# ---------------------------------------------------------------------------
# Instruction files
# ---------------------------------------------------------------------------


@dataclass
class InstructionContext:
    """Inputs available when writing instruction files."""

    project_name: str
    target: str
    mode: str
    bundle_filenames: List[str]
    total_documents: int
    total_tokens: int
    max_bundle_tokens: int
    destination: str = ""
    guidance_lines: List[str] = field(default_factory=list)


def _guidance_block(ctx: InstructionContext) -> List[str]:
    """Render the per-destination guidance section, or nothing if unset."""
    if not ctx.guidance_lines:
        return []
    label = DESTINATION_LABELS.get(ctx.destination, ctx.destination)
    lines = [
        "## Packaging guidance for this destination",
        "",
        f"Optimized for: **{label}**",
        "",
    ]
    lines += [f"- {item}" for item in ctx.guidance_lines]
    lines.append("")
    return lines


_DISCLAIMER = (
    "These bundle token budgets are *packaging targets* this tool uses to "
    "decide how to split content. They are NOT official platform "
    "context-window limits, which change over time. Edit the presets in "
    "`packer/presets.py` if you want different bundle sizes."
)


def write_instructions(target: str, output_dir: Path, ctx: InstructionContext) -> Path:
    """Write the instruction file appropriate for ``target``."""
    if target == "chatgpt":
        return _write_chatgpt(output_dir, ctx)
    if target == "claude":
        return _write_claude(output_dir, ctx)
    if target == "generic":
        return _write_generic(output_dir, ctx)
    if target == "rag":
        return _write_rag_notes(output_dir, ctx)
    if target == "cowork":
        return _write_cowork_notes(output_dir, ctx)
    raise ValueError(f"Unknown target: {target!r}")


def _common_header(ctx: InstructionContext, title: str) -> List[str]:
    bundle_list = "\n".join(f"  - `{name}`" for name in ctx.bundle_filenames) or "  - (none)"
    return [
        f"# {title}",
        "",
        f"- **Project:** {ctx.project_name}",
        f"- **Target:** {ctx.target}",
        f"- **Mode:** {ctx.mode}",
        f"- **Documents:** {ctx.total_documents}",
        f"- **Estimated total tokens:** {ctx.total_tokens:,}",
        f"- **Per-bundle token budget:** {ctx.max_bundle_tokens:,}",
        f"- **Token estimator backend:** {estimator_backend()}",
        "",
        "## Files in this export",
        "",
        "- `01_SOURCE_MANIFEST.md` — index of every source document",
        "- `manifest.csv` / `manifest.json` — machine-readable manifest",
        "- Bundles:",
        bundle_list,
        "- `assets/` — copied images and other binary assets, grouped by `DOC_ID`",
        "- `data/` — copied original CSV/XLSX files, prefixed with `DOC_ID`",
        "",
    ]


def _write_chatgpt(output_dir: Path, ctx: InstructionContext) -> Path:
    lines = _common_header(ctx, f"ChatGPT Project Instructions — {ctx.project_name}")
    lines += _guidance_block(ctx)
    lines += [
        "## How to use this export in a ChatGPT Project",
        "",
        "1. Create a new ChatGPT Project (or open an existing one).",
        "2. Upload every file from this export folder, including all `02_BUNDLE_*.md` files, "
        "the `01_SOURCE_MANIFEST.md`, and any files inside `assets/` and `data/` you want the "
        "model to reference.",
        "3. Paste the **Project instructions** below into the project's instructions field.",
        "",
        "## Project instructions to paste",
        "",
        "```text",
        f"You are working with curated source material for the project: {ctx.project_name}.",
        "",
        "Use the uploaded files as the primary source of truth.",
        "",
        "Rules:",
        "- Answer from the provided files first.",
        "- When making source-backed claims, cite both DOC_ID and SOURCE_FILE",
        "  (for example: \"per DOC_0007 in example.html\").",
        "- Clearly separate source-backed facts from your own inference or reasoning.",
        "- If the answer is not in the files, say so explicitly. Do not invent details.",
        "- Preserve exact values, dates, citations, warnings, measurements,",
        "  deadlines, and technical specifications. Do not paraphrase numbers or",
        "  procedures.",
        "- Do not assume missing procedures or facts. If a step is not documented,",
        "  say it is not documented.",
        "- The bundles are split for upload convenience; treat all bundles as one",
        "  combined corpus.",
        "```",
        "",
        "## Notes",
        "",
        _DISCLAIMER,
        "",
        "This tool does not upload anything to ChatGPT for you. Uploads are manual.",
        "",
    ]
    return _write(output_dir / "00_CHATGPT_PROJECT_INSTRUCTIONS.md", lines)


def _write_claude(output_dir: Path, ctx: InstructionContext) -> Path:
    lines = _common_header(ctx, f"Claude Project Instructions — {ctx.project_name}")
    lines += _guidance_block(ctx)
    lines += [
        "## How to use this export in a Claude Project",
        "",
        "1. Create a new Claude Project (or open an existing one).",
        "2. Add every file from this export folder to the project's **Project knowledge** "
        "(bundles, manifest, and any `assets/` or `data/` files you want available).",
        "3. Paste the **Custom instructions** below into the project's custom-instructions field.",
        "",
        "## Custom instructions to paste",
        "",
        "```text",
        f"You are working with the Project knowledge base for: {ctx.project_name}.",
        "",
        "Treat the uploaded files as the project knowledge base and your primary",
        "source of truth.",
        "",
        "Rules:",
        "- Prefer exact, source-backed answers grounded in the uploaded files.",
        "- Cite both DOC_ID and SOURCE_FILE when you reference the knowledge base",
        "  (for example: \"per DOC_0007 in example.html\").",
        "- Clearly separate source facts from your reasoning or inference.",
        "- Avoid over-generalizing from incomplete sources. If only one document",
        "  describes a procedure, say so rather than presenting it as universal.",
        "- Preserve exact values, dates, warnings, measurements, deadlines, and",
        "  technical specifications without paraphrasing.",
        "- If the answer is not in the knowledge base, say so explicitly.",
        "- The bundles are split for upload convenience; treat all bundles as one",
        "  combined knowledge base.",
        "```",
        "",
        "## Notes",
        "",
        _DISCLAIMER,
        "",
        "This tool does not upload anything to Claude for you. Uploads are manual.",
        "",
    ]
    return _write(output_dir / "00_CLAUDE_PROJECT_INSTRUCTIONS.md", lines)


def _write_generic(output_dir: Path, ctx: InstructionContext) -> Path:
    lines = _common_header(ctx, f"Generic LLM Instructions — {ctx.project_name}")
    lines += _guidance_block(ctx)
    lines += [
        "## How to use this export with a generic LLM chat",
        "",
        "Different chat tools accept files in different ways. The general pattern:",
        "",
        "1. Upload (or paste) `01_SOURCE_MANIFEST.md` first so the model has an index.",
        "2. Upload (or paste) each `02_BUNDLE_*.md` file in order.",
        "3. Paste the system / role prompt below before asking your questions.",
        "",
        "## Suggested system prompt",
        "",
        "```text",
        f"You are working with curated source material for: {ctx.project_name}.",
        "Use the provided documents as your primary source of truth.",
        "",
        "Rules:",
        "- Answer from the provided documents first.",
        "- Cite both DOC_ID and SOURCE_FILE when making source-backed claims.",
        "- Clearly separate source-backed facts from inference.",
        "- Preserve exact values, dates, warnings, measurements, deadlines,",
        "  and technical specifications verbatim.",
        "- If the answer is not in the documents, say so explicitly.",
        "- Treat all bundles as one combined corpus.",
        "```",
        "",
        "## Notes",
        "",
        _DISCLAIMER,
        "",
        "This tool does not upload anything for you. Uploads are manual.",
        "",
    ]
    return _write(output_dir / "00_GENERIC_LLM_INSTRUCTIONS.md", lines)


def _write_cowork_notes(output_dir: Path, ctx: InstructionContext) -> Path:
    safe_project = safe_filename(ctx.project_name) or "project"
    server_id = f"fileslicer_{safe_project}"
    lines = [
        f"# Cowork MCP Bundle — {ctx.project_name}",
        "",
        f"- **Target:** {ctx.target}",
        f"- **Mode:** {ctx.mode}",
        f"- **Documents:** {ctx.total_documents}",
        f"- **Estimated total tokens:** {ctx.total_tokens:,}",
        f"- **Per-chunk token budget:** {ctx.max_bundle_tokens:,}",
        f"- **Token estimator backend:** {estimator_backend()}",
        "",
        *_guidance_block(ctx),
        "## What this export contains",
        "",
        "- `01_SOURCE_MANIFEST.md` / `manifest.csv` / `manifest.json` — the canonical document list.",
        "- `rag_ready/chunks.jsonl` + `rag_ready/source_map.json` — the chunked corpus the server reads from.",
        "- `assets/` and `data/` — copied images and original CSV/XLSX files.",
        "- `mcp_server/` — a self-contained local MCP server that exposes this bundle as tools.",
        "",
        "## How to use this bundle with Claude / Cowork",
        "",
        "1. Install the MCP runtime inside the bundle (one-time per Python environment):",
        "",
        "   ```powershell",
        f"   pip install -r mcp_server\\requirements.txt",
        "   ```",
        "",
        "2. Register the server with your MCP-aware client. The bundle ships a paste-ready",
        "   snippet at `mcp_server/cowork_config.json`. Merge its `mcpServers` entry into your",
        "   client's MCP config (for example `~/.claude/mcp.json` or the Claude Desktop config),",
        "   then restart the client.",
        "",
        "3. Confirm the server is connected. Claude / Cowork will list the tools provided by",
        f"   `{server_id}` and let you call `search`, `get_document`, `list_documents`,",
        "   `get_chunk`, and `get_asset_path` directly from chat.",
        "",
        "## Tools the server exposes",
        "",
        "- `list_documents(limit=50, status=None)` — manifest rows (doc_id, source_file, status, token estimate).",
        "- `get_document(doc_id)` — identity header + full text for one document.",
        "- `search(query, limit=10)` — SQLite FTS5 keyword search across all chunks, ranked by BM25.",
        "- `get_chunk(chunk_id)` — chunk text plus the previous/next chunk ids in the same document.",
        "- `get_asset_path(doc_id, name)` — absolute local path to a copied image or data file.",
        "",
        "## Notes",
        "",
        _DISCLAIMER,
        "",
        "This tool does not upload anything to Claude for you. The MCP server runs locally on",
        "your machine and only responds to the MCP client you have explicitly registered it with.",
        "",
    ]
    return _write(output_dir / "00_COWORK_MCP_INSTRUCTIONS.md", lines)


def _write_rag_notes(output_dir: Path, ctx: InstructionContext) -> Path:
    lines = [
        f"# RAG Export Notes — {ctx.project_name}",
        "",
        f"- **Target:** {ctx.target}",
        f"- **Mode:** {ctx.mode}",
        f"- **Documents:** {ctx.total_documents}",
        f"- **Estimated total tokens:** {ctx.total_tokens:,}",
        f"- **Per-chunk token budget:** {ctx.max_bundle_tokens:,}",
        f"- **Token estimator backend:** {estimator_backend()}",
        "",
        *_guidance_block(ctx),
        "## What this export contains",
        "",
        "- `01_SOURCE_MANIFEST.md` / `manifest.csv` / `manifest.json` —"
        " the canonical list of source documents.",
        "- `rag_ready/chunks.jsonl` — one JSON object per line, each one a chunk.",
        "- `rag_ready/source_map.json` — a mapping from `doc_id` to chunk metadata.",
        "- `assets/` and `data/` — copied binary originals (images, CSV/XLSX).",
        "",
        "## Chunk schema",
        "",
        "Each line of `chunks.jsonl` is a JSON object with these keys:",
        "",
        "- `chunk_id`  — stable id like `DOC_0007__c001`",
        "- `doc_id`    — parent document id",
        "- `source_file` — original file name",
        "- `source_path` — original file path relative to the input root",
        "- `text`      — chunk text",
        "- `token_estimate` — estimated token count for this chunk",
        "- `heading_path` — (only when the heading-breadcrumb metadata mode is on)"
        " the list of enclosing headings above the chunk, outermost first; use it"
        " to cite or filter chunks by section.",
        "- `metadata` — (only for record sources such as the FEMA appeals database)"
        " a per-document object of structured fields (e.g. appellant, PA ID,"
        " disaster, decision date, region, status, and cited authorities); use it"
        " for metadata filtering and citation.",
        "",
        "Chunks are split greedily by paragraph against the per-chunk token budget "
        "(or at headings when the heading strategy is selected). Chunk size, strategy, "
        "overlap between adjacent chunks, a minimum chunk size that merges tiny "
        "chunks, sentence-level splitting of oversize lines, and an optional heading "
        "breadcrumb (added as metadata and/or prefixed into the chunk text) are all "
        "configurable in the chunk review screen and saved profiles.",
        "",
        "## Optimizing this export for retrieval",
        "",
        "- **Chunk size:** retrieval works best when each chunk holds one "
        "self-contained idea. Roughly 300–800 tokens per chunk is a good "
        "starting range; very large chunks dilute retrieval precision and "
        "very small ones lose context.",
        "- **Respect document structure:** chunks that align with headings or "
        "record fields retrieve better than chunks that cut across sections. "
        "Use the chunk review screen's heading strategy (or pre-process) so "
        "boundaries follow the document's own structure.",
        "- **Trim boilerplate before embedding:** repeated headers, footers, "
        "duplicated HTML renderings of the same text, and scrape metadata "
        "add embedding cost and pollute results. Deselect those chunks "
        "during review instead of embedding them.",
        "- **Keep identifiers with content:** each chunk's `doc_id` and "
        "`source_path` come along in the JSONL; store them with your "
        "embeddings so answers can cite the source document.",
        "- **Watch over-budget chunks:** chunks larger than the budget come "
        "from single unbreakable lines (often tables). Consider reworking "
        "those source files or accepting the oversize chunks knowingly.",
        "",
        "## Notes",
        "",
        _DISCLAIMER,
        "",
        "This tool does not embed, index, or upload anything for you in Version 1.",
        "",
    ]
    return _write(output_dir / "00_RAG_EXPORT_NOTES.md", lines)


def _write(path: Path, lines: List[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_corpus_overview(
    output_dir: Path,
    project_name: str,
    manifest: Manifest,
    bundles: List[Bundle],
) -> Path:
    """Write ``00_CORPUS_OVERVIEW.md`` — a front-of-corpus index of every document.

    Used by the medium-grained bundling mode so the destination's retriever (and
    the reader) sees an overview/index first: which document landed in which
    bundle, with key identity columns. Sorts among the ``00_*`` instruction
    files, ahead of the bundles.
    """
    bundle_by_doc = {
        doc_id: bundle.filename for bundle in bundles for doc_id in bundle.doc_ids
    }
    ok_entries = [e for e in manifest.entries if e.status == "ok"]
    lines: List[str] = [
        f"# Corpus Overview — {project_name}",
        "",
        f"- **Documents:** {len(ok_entries)}",
        f"- **Bundles:** {len(bundles)}",
        f"- **Estimated total tokens:** {sum(e.token_estimate for e in ok_entries):,}",
        "",
        "This index lists every packaged document and the bundle it lives in. "
        "Read it first to locate a source, then open the named bundle.",
        "",
    ]
    headers = ["DOC_ID", "Source File", "Tokens", "Bundle"]
    rows = [
        (
            e.doc_id,
            e.source_file,
            f"{e.token_estimate:,}",
            bundle_by_doc.get(e.doc_id, "-"),
        )
        for e in ok_entries
    ]
    lines.append(rows_to_markdown_table(headers, rows))
    lines.append("")
    return _write(output_dir / "00_CORPUS_OVERVIEW.md", lines)


# ---------------------------------------------------------------------------
# RAG export
# ---------------------------------------------------------------------------


def write_rag_export(
    rag_dir: Path,
    converted_docs: List[ConvertedDoc],
    max_chunk_tokens: int,
    chunk_strategy: str = STRATEGY_TOKENS,
    heading_level: int = DEFAULT_HEADING_LEVEL,
    min_chunk_tokens: int = 0,
    overlap_tokens: int = 0,
    split_sentences: bool = False,
    fence_aware: bool = False,
    heading_path_mode: str = HEADING_PATH_OFF,
) -> None:
    """Write ``chunks.jsonl`` and ``source_map.json`` under ``rag_dir``.

    The defaults preserve V1 output exactly. Callers that ran chunk review
    can pass ``chunk_strategy``/``heading_level``/``min_chunk_tokens``/
    ``split_sentences``/``fence_aware`` so the JSONL chunk boundaries match
    what the user previewed. ``overlap_tokens > 0`` additionally prefixes
    each chunk with the tail of its predecessor (boundaries and chunk count
    are unchanged; only the exported text gains the overlap).

    ``heading_path_mode`` attaches each chunk's enclosing heading breadcrumb:
    ``metadata`` adds a ``heading_path`` list field, ``prefix`` prepends the
    breadcrumb to the chunk text (so an embedding model sees it), ``both``
    does each, and ``off`` (default) does neither — boundaries, chunk counts,
    and ids are unchanged by any mode.
    """
    want_metadata = heading_path_mode in (HEADING_PATH_METADATA, HEADING_PATH_BOTH)
    want_prefix = heading_path_mode in (HEADING_PATH_PREFIX, HEADING_PATH_BOTH)
    rag_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = rag_dir / "chunks.jsonl"
    source_map_path = rag_dir / "source_map.json"

    source_map = {}
    with chunks_path.open("w", encoding="utf-8") as f:
        for doc in converted_docs:
            text = doc.body_markdown.strip()
            if not text:
                # Still record a single empty chunk so the doc shows up.
                chunk_id = f"{doc.entry.doc_id}__c001"
                payload = {
                    "chunk_id": chunk_id,
                    "doc_id": doc.entry.doc_id,
                    "source_file": doc.entry.source_file,
                    "source_path": doc.entry.source_path,
                    "text": "",
                    "token_estimate": 0,
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                source_map[doc.entry.doc_id] = {
                    "source_file": doc.entry.source_file,
                    "source_path": doc.entry.source_path,
                    "chunk_ids": [chunk_id],
                    "token_estimate": 0,
                }
                continue

            if chunk_strategy == STRATEGY_HEADINGS:
                pairs = chunk_markdown_by_headings_with_reasons(
                    text, max_chunk_tokens, heading_level, split_sentences, fence_aware
                )
            else:
                pairs = chunk_markdown_with_reasons(
                    text, max_chunk_tokens, split_sentences, fence_aware
                )
            pairs = merge_undersized_chunks(pairs, min_chunk_tokens, max_chunk_tokens)
            boundary_texts = [chunk_text for chunk_text, _ in pairs]
            heading_paths = heading_paths_for_texts(boundary_texts)
            chunk_texts = apply_chunk_overlap(boundary_texts, overlap_tokens)
            chunk_ids: List[str] = []
            for i, (chunk_text, path) in enumerate(
                zip(chunk_texts, heading_paths), start=1
            ):
                chunk_id = f"{doc.entry.doc_id}__c{i:03d}"
                if want_prefix:
                    chunk_text = apply_heading_path_prefix(chunk_text, path)
                tokens = estimate_tokens(chunk_text)
                payload = {
                    "chunk_id": chunk_id,
                    "doc_id": doc.entry.doc_id,
                    "source_file": doc.entry.source_file,
                    "source_path": doc.entry.source_path,
                    "text": chunk_text,
                    "token_estimate": tokens,
                }
                if want_metadata:
                    payload["heading_path"] = list(path)
                if doc.metadata:
                    payload["metadata"] = doc.metadata
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                chunk_ids.append(chunk_id)
            source_map[doc.entry.doc_id] = {
                "source_file": doc.entry.source_file,
                "source_path": doc.entry.source_path,
                "chunk_ids": chunk_ids,
                "token_estimate": doc.token_estimate,
            }

    source_map_path.write_text(
        json.dumps(source_map, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Manifest convenience
# ---------------------------------------------------------------------------


def assign_bundles_to_manifest(manifest: Manifest, bundles: List[Bundle]) -> None:
    """After bundling, record which bundle each doc landed in."""
    by_id = {entry.doc_id: entry for entry in manifest.entries}
    for bundle in bundles:
        for doc in bundle.docs:
            entry = by_id.get(doc.entry.doc_id)
            if entry is not None:
                entry.output_bundle = bundle.filename


# ---------------------------------------------------------------------------
# Cowork / MCP export
# ---------------------------------------------------------------------------


def write_cowork_bundle(
    export_dir: Path,
    project_name: str,
    rag_dir: Path,
    embedding_model: str = "",
) -> Path:
    """Build the ``mcp_server/`` directory next to the RAG export.

    Reads ``rag_dir / chunks.jsonl`` and writes an FTS5-indexed SQLite database
    plus a self-contained FastMCP stdio server script that serves the bundle
    as MCP tools. When ``embedding_model`` resolves to a usable embedder, every
    chunk is also embedded into a vector index so the server exposes vector and
    hybrid (BM25 + vector, RRF) search; otherwise the server degrades to FTS5
    keyword search. Returns the path to the generated ``mcp_server/`` directory.
    """
    mcp_dir = export_dir / "mcp_server"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    index_path = mcp_dir / "index.sqlite"
    server_path = mcp_dir / "server.py"
    config_path = mcp_dir / "cowork_config.json"
    requirements_path = mcp_dir / "requirements.txt"
    readme_path = mcp_dir / "README.md"
    chunks_path = rag_dir / "chunks.jsonl"

    _build_fts_index(index_path, chunks_path)
    meta = _build_vector_index(index_path, embedding_model)
    _copy_embedder_module(mcp_dir)

    safe_project = safe_filename(project_name) or "project"
    server_id = f"fileslicer_{safe_project}"
    server_path.write_text(_render_server_script(project_name, server_id), encoding="utf-8")
    requirements_path.write_text(
        "mcp[cli]>=1.0\n# Optional, only for the embedder chosen at export time:\n"
        "# openai>=1.0           # for --embedding-model openai:...\n"
        "# voyageai>=0.2         # for --embedding-model voyage:...\n"
        "# sentence-transformers # for --embedding-model local:...\n",
        encoding="utf-8",
    )
    config_path.write_text(_render_cowork_config(server_id, server_path), encoding="utf-8")
    readme_path.write_text(
        _render_server_readme(project_name, server_id, meta), encoding="utf-8"
    )

    return mcp_dir


def _copy_embedder_module(mcp_dir: Path) -> None:
    """Copy ``packer/embedder.py`` into the server dir so it can embed queries."""
    source = Path(__file__).resolve().parent / "embedder.py"
    (mcp_dir / "embedder.py").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _build_fts_index(index_path: Path, chunks_path: Path) -> None:
    if index_path.exists():
        index_path.unlink()
    conn = sqlite3.connect(str(index_path))
    try:
        conn.executescript(
            """
            CREATE TABLE chunks (
                chunk_id      TEXT PRIMARY KEY,
                doc_id        TEXT NOT NULL,
                source_file   TEXT,
                source_path   TEXT,
                token_estimate INTEGER,
                ordinal       INTEGER,
                text          TEXT,
                metadata      TEXT
            );
            CREATE INDEX idx_chunks_doc_id ON chunks(doc_id, ordinal);
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                chunk_id UNINDEXED,
                doc_id UNINDEXED,
                source_file,
                text,
                tokenize = 'unicode61 remove_diacritics 2'
            );
            """
        )
        if chunks_path.exists():
            with chunks_path.open("r", encoding="utf-8") as f:
                doc_ordinals: dict[str, int] = {}
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    doc_id = payload.get("doc_id", "")
                    ordinal = doc_ordinals.get(doc_id, 0)
                    doc_ordinals[doc_id] = ordinal + 1
                    metadata = payload.get("metadata")
                    conn.execute(
                        "INSERT INTO chunks (chunk_id, doc_id, source_file, source_path,"
                        " token_estimate, ordinal, text, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            payload.get("chunk_id", ""),
                            doc_id,
                            payload.get("source_file", ""),
                            payload.get("source_path", ""),
                            int(payload.get("token_estimate") or 0),
                            ordinal,
                            payload.get("text", ""),
                            json.dumps(metadata, ensure_ascii=False) if metadata else None,
                        ),
                    )
                    conn.execute(
                        "INSERT INTO chunks_fts (chunk_id, doc_id, source_file, text)"
                        " VALUES (?, ?, ?, ?)",
                        (
                            payload.get("chunk_id", ""),
                            doc_id,
                            payload.get("source_file", ""),
                            payload.get("text", ""),
                        ),
                    )
        conn.commit()
    finally:
        conn.close()


def _build_vector_index(index_path: Path, embedding_model: str) -> Optional[dict]:
    """Embed every chunk and store float32 vectors + embedder metadata in the index.

    Returns the embedder metadata dict on success, or ``None`` if embedding was
    skipped (no chunks) or failed (missing dependency/key) — in which case the
    server falls back to FTS5-only retrieval. Never raises: a failed embedder
    must not break the export (it degrades to keyword search).
    """
    from array import array

    from .embedder import build_embedder_from_meta, embedder_meta, resolve_embedder

    try:
        embedder = resolve_embedder(embedding_model)
    except Exception:  # noqa: BLE001 - degrade to FTS5-only
        return None

    conn = sqlite3.connect(str(index_path))
    try:
        rows = conn.execute("SELECT chunk_id, text FROM chunks ORDER BY rowid").fetchall()
        if not rows:
            return None
        texts = [r[1] or "" for r in rows]
        try:
            vectors = embedder.embed(texts)
        except Exception:  # noqa: BLE001 - degrade to FTS5-only
            return None
        conn.execute(
            "CREATE TABLE vectors (chunk_id TEXT PRIMARY KEY, vector BLOB)"
        )
        conn.execute("CREATE TABLE embedder_meta (key TEXT PRIMARY KEY, value TEXT)")
        for (chunk_id, _text), vector in zip(rows, vectors):
            conn.execute(
                "INSERT INTO vectors (chunk_id, vector) VALUES (?, ?)",
                (chunk_id, array("f", vector).tobytes()),
            )
        meta = embedder_meta(embedder)
        for key, value in meta.items():
            conn.execute(
                "INSERT INTO embedder_meta (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        conn.commit()
        return meta
    finally:
        conn.close()


def _render_cowork_config(server_id: str, server_path: Path) -> str:
    payload = {
        "mcpServers": {
            server_id: {
                "command": "python",
                "args": [str(server_path.resolve())],
            }
        }
    }
    return json.dumps(payload, indent=2) + "\n"


def _render_server_readme(project_name: str, server_id: str, embedder_meta: Optional[dict]) -> str:
    if embedder_meta:
        embed_line = (
            f"This bundle is embedded with **{embedder_meta.get('backend')}:"
            f"{embedder_meta.get('model')}** ({embedder_meta.get('dim')} dims), so the\n"
            "server also exposes `vector_search` and `hybrid_search`. To query, the\n"
            "server re-embeds your query with the same backend"
        )
        if embedder_meta.get("backend") in ("openai", "voyage"):
            embed_line += (
                ", which needs the matching API key in the environment "
                f"(`{ 'OPENAI_API_KEY' if embedder_meta.get('backend') == 'openai' else 'VOYAGE_API_KEY' }`)"
                " and the provider package installed. Without them, hybrid/vector tools\n"
                "fall back to keyword search."
            )
        else:
            embed_line += " (offline; no key needed)."
        embed_block = "\n## Retrieval\n\n" + embed_line + "\n"
        tool_lines = (
            "- `search` — SQLite FTS5 keyword search across chunks, ranked by BM25.\n"
            "- `vector_search` — nearest-neighbour search over the embedded chunks.\n"
            "- `hybrid_search` — fuses BM25 and vector results with Reciprocal Rank Fusion.\n"
        )
    else:
        embed_block = (
            "\n## Retrieval\n\nThis bundle was exported without embeddings, so the server\n"
            "provides keyword (`search`) retrieval only. Re-export with an embedding model\n"
            "(`--embedding-model hashing` or `--embedding-model openai:text-embedding-3-small`)\n"
            "to enable vector and hybrid search.\n"
        )
        tool_lines = "- `search` — SQLite FTS5 keyword search across chunks, ranked by BM25.\n"
    return (
        f"# MCP server for {project_name}\n\n"
        "This directory is a self-contained MCP server generated by\n"
        "`llm_project_packer --target cowork`. It exposes the bundle in this\n"
        "export folder to any MCP-aware client (Claude Desktop, Cowork, etc.).\n"
        f"{embed_block}\n"
        "## One-time setup\n\n"
        "```powershell\n"
        "pip install -r requirements.txt\n"
        "```\n\n"
        "## Register the server\n\n"
        f"Open `cowork_config.json` and merge the `mcpServers.{server_id}` entry into\n"
        "your client's MCP config file (for example `~/.claude/mcp.json` or the\n"
        "Claude Desktop config), then restart the client.\n\n"
        "## Tools provided\n\n"
        "- `list_documents` — list manifest rows.\n"
        "- `get_document` — return one document's full text.\n"
        f"{tool_lines}"
        "- `get_chunk` — return one chunk plus the previous/next chunk ids.\n"
        "- `get_asset_path` — return the absolute local path of an asset or data file.\n\n"
        "Moving or renaming this folder is fine; the server resolves paths at runtime.\n"
        "If you move it, regenerate `cowork_config.json` or update the `args` path inside\n"
        "your MCP config to point at the new `server.py` location.\n"
    )


# Retrieval tools appended to the generated server. Kept as a plain (non-f)
# string so its braces need no escaping.
_SERVER_RETRIEVAL_TOOLS = '''

def _table_exists(name: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
        ).fetchone()
    return row is not None


_EMBEDDER = None
_EMBEDDER_TRIED = False


def _embedder():
    """Lazily build the embedder recorded in the index (or None if unavailable)."""
    global _EMBEDDER, _EMBEDDER_TRIED
    if _EMBEDDER_TRIED:
        return _EMBEDDER
    _EMBEDDER_TRIED = True
    if not _table_exists("embedder_meta"):
        return None
    try:
        with _connect() as conn:
            rows = conn.execute("SELECT key, value FROM embedder_meta").fetchall()
        meta = {r["key"]: json.loads(r["value"]) for r in rows}
        if str(SERVER_DIR) not in sys.path:
            sys.path.insert(0, str(SERVER_DIR))
        from embedder import build_embedder_from_meta

        _EMBEDDER = build_embedder_from_meta(meta)
    except Exception:
        _EMBEDDER = None
    return _EMBEDDER


def _cosine(a, b) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / math.sqrt(na * nb)


def _chunk_meta(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _vector_ranked(query: str, pool: int):
    embedder = _embedder()
    if embedder is None or not _table_exists("vectors"):
        return None
    try:
        qv = embedder.embed([query], is_query=True)[0]
    except Exception:
        return None
    scored = []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT v.chunk_id AS chunk_id, v.vector AS vector, c.doc_id AS doc_id,"
            " c.source_file AS source_file, c.text AS text, c.metadata AS metadata"
            " FROM vectors v JOIN chunks c ON c.chunk_id = v.chunk_id"
        ).fetchall()
    for r in rows:
        vec = array("f")
        vec.frombytes(r["vector"])
        scored.append((_cosine(qv, vec), r))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:pool]


def _bm25_ranked(query: str, pool: int):
    fts_query = _escape_fts_query(query)
    if not fts_query:
        return []
    with _connect() as conn:
        return conn.execute(
            "SELECT chunk_id, doc_id, source_file, bm25(chunks_fts) AS score"
            " FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY score ASC LIMIT ?",
            (fts_query, pool),
        ).fetchall()


@mcp.tool()
def vector_search(query: str, limit: int = 10) -> Dict[str, Any]:
    """Nearest-neighbour search over the embedded chunks (cosine similarity).

    Requires that this bundle was exported with an embedding model. Returns
    ``available=False`` with an empty hit list when no vector index is present
    or the embedder cannot be loaded (use ``search`` for keyword retrieval).
    """
    capped = max(1, min(int(limit or 10), 100))
    ranked = _vector_ranked(query, capped)
    if ranked is None:
        return {
            "query": query,
            "available": False,
            "hits": [],
            "note": "No vector index or embedder unavailable; use search().",
        }
    hits = []
    for score, r in ranked:
        text = r["text"] or ""
        hits.append(
            {
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "source_file": r["source_file"],
                "score": round(float(score), 6),
                "metadata": _chunk_meta(r["metadata"]),
                "snippet": text[:240],
            }
        )
    return {"query": query, "available": True, "hit_count": len(hits), "hits": hits}


def _maybe_rerank(query: str, hits: List[Dict[str, Any]]):
    """Optionally re-score hits with a cross-encoder; no-op without the dependency."""
    if not hits:
        return hits, False
    try:
        from sentence_transformers import CrossEncoder
    except Exception:
        return hits, False
    try:
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        scores = model.predict([(query, h["snippet"]) for h in hits])
        order = sorted(range(len(hits)), key=lambda i: float(scores[i]), reverse=True)
        reranked = [dict(hits[i], rerank_score=round(float(scores[i]), 6)) for i in order]
        return reranked, True
    except Exception:
        return hits, False


@mcp.tool()
def hybrid_search(query: str, limit: int = 10, rerank: bool = False) -> Dict[str, Any]:
    """Hybrid retrieval: fuse BM25 keyword and vector rankings via Reciprocal Rank Fusion.

    Falls back to keyword-only ranking when no vector index is available. When
    ``rerank`` is true and the optional ``sentence-transformers`` package is
    installed, the fused results are re-scored with a cross-encoder; otherwise
    the fused order is returned unchanged.
    """
    capped = max(1, min(int(limit or 10), 100))
    pool = max(capped * 5, 50)
    k = 60
    scores: Dict[str, float] = {}
    for rank, r in enumerate(_bm25_ranked(query, pool)):
        scores[r["chunk_id"]] = scores.get(r["chunk_id"], 0.0) + 1.0 / (k + rank + 1)
    vec = _vector_ranked(query, pool)
    used_vectors = vec is not None
    if vec:
        for rank, (_score, r) in enumerate(vec):
            scores[r["chunk_id"]] = scores.get(r["chunk_id"], 0.0) + 1.0 / (k + rank + 1)
    if not scores:
        return {"query": query, "used_vectors": used_vectors, "hit_count": 0, "hits": []}
    top_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:capped]
    hits = []
    with _connect() as conn:
        for cid in top_ids:
            row = conn.execute(
                "SELECT chunk_id, doc_id, source_file, text, metadata FROM chunks WHERE chunk_id = ?",
                (cid,),
            ).fetchone()
            if row is None:
                continue
            text = row["text"] or ""
            hits.append(
                {
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "source_file": row["source_file"],
                    "rrf_score": round(scores[cid], 6),
                    "metadata": _chunk_meta(row["metadata"]),
                    "snippet": text[:240],
                }
            )
    reranked = False
    if rerank:
        hits, reranked = _maybe_rerank(query, hits)
    return {
        "query": query,
        "used_vectors": used_vectors,
        "reranked": reranked,
        "hit_count": len(hits),
        "hits": hits,
    }
'''


def _render_server_script(project_name: str, server_id: str) -> str:
    # The docstring interpolation must survive any project name: strip
    # backslashes and quotes so the generated module cannot break.
    safe_project = project_name.replace("\\", "/").replace('"', "'")
    return f'''"""MCP stdio server for the {safe_project!s} llm_project_packer bundle.

This file is generated by llm_project_packer's --target cowork export. It is
self-contained: it reads its sibling `index.sqlite` and the parent bundle's
`manifest.json`, `rag_ready/chunks.jsonl`, `assets/`, and `data/` directories.
You can move the whole export folder; the server resolves paths relative to
this script at runtime.
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from array import array
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - import-time guidance only
    raise SystemExit(
        "The 'mcp' package is required to run this server. Install it with:\\n"
        "    pip install -r " + str(Path(__file__).resolve().parent / "requirements.txt")
    ) from exc


SERVER_DIR = Path(__file__).resolve().parent
BUNDLE_DIR = SERVER_DIR.parent
INDEX_PATH = SERVER_DIR / "index.sqlite"
MANIFEST_PATH = BUNDLE_DIR / "manifest.json"
CHUNKS_PATH = BUNDLE_DIR / "rag_ready" / "chunks.jsonl"
SOURCE_MAP_PATH = BUNDLE_DIR / "rag_ready" / "source_map.json"
ASSETS_DIR = BUNDLE_DIR / "assets"
DATA_DIR = BUNDLE_DIR / "data"

PROJECT_NAME = {project_name!r}
SERVER_ID = {server_id!r}

mcp = FastMCP(SERVER_ID)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(INDEX_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _load_manifest() -> List[Dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return []
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    return list(entries or [])


def _load_source_map() -> Dict[str, Any]:
    if not SOURCE_MAP_PATH.exists():
        return {{}}
    try:
        return json.loads(SOURCE_MAP_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {{}}


def _escape_fts_query(query: str) -> str:
    cleaned = query.replace('"', " ").strip()
    if not cleaned:
        return cleaned
    tokens = [token for token in cleaned.split() if token]
    return " ".join(f'"{{token}}"' for token in tokens)


@mcp.tool()
def list_documents(limit: int = 50, status: Optional[str] = None) -> Dict[str, Any]:
    """List documents recorded in the bundle manifest.

    Args:
        limit: Maximum rows to return (default 50; pass 0 for no cap).
        status: Optional manifest status filter (``ok``, ``skipped``, ``failed``).
    """
    rows = _load_manifest()
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if limit and limit > 0:
        rows = rows[:limit]
    return {{"project_name": PROJECT_NAME, "count": len(rows), "documents": rows}}


@mcp.tool()
def get_document(doc_id: str) -> Dict[str, Any]:
    """Return the full text of one document by ``DOC_xxxx`` id, reconstructed from its chunks."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT chunk_id, source_file, source_path, text, token_estimate, ordinal"
            " FROM chunks WHERE doc_id = ? ORDER BY ordinal ASC",
            (doc_id,),
        ).fetchall()
    if not rows:
        return {{"doc_id": doc_id, "found": False, "text": ""}}
    text = "\\n\\n".join(r["text"] for r in rows if r["text"])
    return {{
        "doc_id": doc_id,
        "found": True,
        "source_file": rows[0]["source_file"],
        "source_path": rows[0]["source_path"],
        "chunk_count": len(rows),
        "token_estimate": sum(int(r["token_estimate"] or 0) for r in rows),
        "text": text,
    }}


@mcp.tool()
def search(query: str, limit: int = 10) -> Dict[str, Any]:
    """Run a BM25-ranked SQLite FTS5 keyword search across all chunks.

    Args:
        query: Free-text query. Quoted tokens are matched literally.
        limit: Max hits to return (default 10).
    """
    fts_query = _escape_fts_query(query)
    if not fts_query:
        return {{"query": query, "hits": []}}
    capped_limit = max(1, min(int(limit or 10), 100))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT chunks_fts.chunk_id AS chunk_id, chunks_fts.doc_id AS doc_id,"
            " chunks_fts.source_file AS source_file,"
            " snippet(chunks_fts, 3, '[[', ']]', '...', 24) AS snippet,"
            " bm25(chunks_fts) AS score"
            " FROM chunks_fts WHERE chunks_fts MATCH ?"
            " ORDER BY score ASC LIMIT ?",
            (fts_query, capped_limit),
        ).fetchall()
    hits = [
        {{
            "chunk_id": r["chunk_id"],
            "doc_id": r["doc_id"],
            "source_file": r["source_file"],
            "snippet": r["snippet"],
            "score": float(r["score"]) if r["score"] is not None else None,
        }}
        for r in rows
    ]
    return {{"query": query, "hit_count": len(hits), "hits": hits}}


@mcp.tool()
def get_chunk(chunk_id: str) -> Dict[str, Any]:
    """Return one chunk's text plus the previous/next chunk ids in the same document."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT chunk_id, doc_id, source_file, source_path, text, token_estimate, ordinal"
            " FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        if row is None:
            return {{"chunk_id": chunk_id, "found": False}}
        neighbors = conn.execute(
            "SELECT chunk_id, ordinal FROM chunks WHERE doc_id = ? ORDER BY ordinal ASC",
            (row["doc_id"],),
        ).fetchall()
    ordinal = row["ordinal"]
    prev_id = next((n["chunk_id"] for n in neighbors if n["ordinal"] == ordinal - 1), None)
    next_id = next((n["chunk_id"] for n in neighbors if n["ordinal"] == ordinal + 1), None)
    return {{
        "chunk_id": row["chunk_id"],
        "doc_id": row["doc_id"],
        "source_file": row["source_file"],
        "source_path": row["source_path"],
        "token_estimate": int(row["token_estimate"] or 0),
        "ordinal": ordinal,
        "previous_chunk_id": prev_id,
        "next_chunk_id": next_id,
        "text": row["text"],
        "found": True,
    }}


@mcp.tool()
def get_asset_path(doc_id: str, name: str) -> Dict[str, Any]:
    """Resolve an asset or data file copied for ``doc_id`` to its absolute local path.

    The MCP client (not this server) decides how to use the path. Returns
    ``found=False`` if no matching file exists.
    """
    candidates: List[Path] = []
    asset_root = ASSETS_DIR / doc_id
    if asset_root.exists():
        candidates.append(asset_root / name)
    if DATA_DIR.exists():
        candidates.extend(p for p in DATA_DIR.glob(f"{{doc_id}}_*") if p.name.endswith(name) or p.name == name)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.exists() and BUNDLE_DIR in resolved.parents:
                return {{
                    "doc_id": doc_id,
                    "name": name,
                    "found": True,
                    "path": str(resolved),
                }}
        except OSError:
            continue
    return {{"doc_id": doc_id, "name": name, "found": False, "path": None}}
''' + _SERVER_RETRIEVAL_TOOLS + '''

if __name__ == "__main__":
    mcp.run()
'''
