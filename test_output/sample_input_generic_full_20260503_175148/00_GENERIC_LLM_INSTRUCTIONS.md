# Generic LLM Instructions — sample_input

- **Project:** sample_input
- **Target:** generic
- **Mode:** full
- **Documents:** 5
- **Estimated total tokens:** 375
- **Per-bundle token budget:** 5,000
- **Token estimator backend:** heuristic (chars/4)

## Files in this export

- `01_SOURCE_MANIFEST.md` — index of every source document
- `manifest.csv` / `manifest.json` — machine-readable manifest
- Bundles:
  - `02_BUNDLE_001.md`
- `assets/` — copied images and other binary assets, grouped by `DOC_ID`
- `data/` — copied original CSV/XLSX files, prefixed with `DOC_ID`

## How to use this export with a generic LLM chat

Different chat tools accept files in different ways. The general pattern:

1. Upload (or paste) `01_SOURCE_MANIFEST.md` first so the model has an index.
2. Upload (or paste) each `02_BUNDLE_*.md` file in order.
3. Paste the system / role prompt below before asking your questions.

## Suggested system prompt

```text
You are working with curated source material for: sample_input.
Use the provided documents as your primary source of truth.

Rules:
- Answer from the provided documents first.
- Cite both DOC_ID and SOURCE_FILE when making source-backed claims.
- Clearly separate source-backed facts from inference.
- Preserve exact values, dates, warnings, measurements, deadlines,
  and technical specifications verbatim.
- If the answer is not in the documents, say so explicitly.
- Treat all bundles as one combined corpus.
```

## Notes

These bundle token budgets are *packaging targets* this tool uses to decide how to split content. They are NOT official platform context-window limits, which change over time. Edit the presets in `packer/presets.py` if you want different bundle sizes.

This tool does not upload anything for you. Uploads are manual.
