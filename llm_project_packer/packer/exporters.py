"""Generate platform-specific instruction files and the RAG export."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .bundler import Bundle, ConvertedDoc
from .chunking import (
    DEFAULT_HEADING_LEVEL,
    STRATEGY_HEADINGS,
    STRATEGY_TOKENS,
    chunk_markdown,
    chunk_markdown_by_headings_with_reasons,
)
from .manifest import Manifest
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
        "",
        "Chunks in Version 1 are split greedily by paragraph against the per-chunk token budget. "
        "If you want overlap, smaller chunks, or sentence-level splitting, pre-process "
        "`chunks.jsonl` before embedding.",
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


# ---------------------------------------------------------------------------
# RAG export
# ---------------------------------------------------------------------------


def write_rag_export(
    rag_dir: Path,
    converted_docs: List[ConvertedDoc],
    max_chunk_tokens: int,
    chunk_strategy: str = STRATEGY_TOKENS,
    heading_level: int = DEFAULT_HEADING_LEVEL,
) -> None:
    """Write ``chunks.jsonl`` and ``source_map.json`` under ``rag_dir``.

    The default token strategy preserves V1 output exactly. Callers that ran
    chunk review can pass ``chunk_strategy``/``heading_level`` so the JSONL
    chunks match what the user previewed.
    """
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
                chunk_texts = [
                    chunk_text
                    for chunk_text, _ in chunk_markdown_by_headings_with_reasons(
                        text, max_chunk_tokens, heading_level
                    )
                ]
            else:
                chunk_texts = chunk_markdown(text, max_chunk_tokens)
            chunk_ids: List[str] = []
            for i, chunk_text in enumerate(chunk_texts, start=1):
                chunk_id = f"{doc.entry.doc_id}__c{i:03d}"
                tokens = estimate_tokens(chunk_text)
                payload = {
                    "chunk_id": chunk_id,
                    "doc_id": doc.entry.doc_id,
                    "source_file": doc.entry.source_file,
                    "source_path": doc.entry.source_path,
                    "text": chunk_text,
                    "token_estimate": tokens,
                }
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
