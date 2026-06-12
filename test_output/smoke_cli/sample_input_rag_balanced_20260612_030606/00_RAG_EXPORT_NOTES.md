# RAG Export Notes — sample_input

- **Target:** rag
- **Mode:** balanced
- **Documents:** 5
- **Estimated total tokens:** 288
- **Per-chunk token budget:** 40,000
- **Token estimator backend:** heuristic (chars/4)

## What this export contains

- `01_SOURCE_MANIFEST.md` / `manifest.csv` / `manifest.json` — the canonical list of source documents.
- `rag_ready/chunks.jsonl` — one JSON object per line, each one a chunk.
- `rag_ready/source_map.json` — a mapping from `doc_id` to chunk metadata.
- `assets/` and `data/` — copied binary originals (images, CSV/XLSX).

## Chunk schema

Each line of `chunks.jsonl` is a JSON object with these keys:

- `chunk_id`  — stable id like `DOC_0007__c001`
- `doc_id`    — parent document id
- `source_file` — original file name
- `source_path` — original file path relative to the input root
- `text`      — chunk text
- `token_estimate` — estimated token count for this chunk

Chunks in Version 1 are split greedily by paragraph against the per-chunk token budget. If you want overlap, smaller chunks, or sentence-level splitting, pre-process `chunks.jsonl` before embedding.

## Optimizing this export for retrieval

- **Chunk size:** retrieval works best when each chunk holds one self-contained idea. Roughly 300–800 tokens per chunk is a good starting range; very large chunks dilute retrieval precision and very small ones lose context.
- **Respect document structure:** chunks that align with headings or record fields retrieve better than chunks that cut across sections. Use the chunk review screen's heading strategy (or pre-process) so boundaries follow the document's own structure.
- **Trim boilerplate before embedding:** repeated headers, footers, duplicated HTML renderings of the same text, and scrape metadata add embedding cost and pollute results. Deselect those chunks during review instead of embedding them.
- **Keep identifiers with content:** each chunk's `doc_id` and `source_path` come along in the JSONL; store them with your embeddings so answers can cite the source document.
- **Watch over-budget chunks:** chunks larger than the budget come from single unbreakable lines (often tables). Consider reworking those source files or accepting the oversize chunks knowingly.

## Notes

These bundle token budgets are *packaging targets* this tool uses to decide how to split content. They are NOT official platform context-window limits, which change over time. Edit the presets in `packer/presets.py` if you want different bundle sizes.

This tool does not embed, index, or upload anything for you in Version 1.
