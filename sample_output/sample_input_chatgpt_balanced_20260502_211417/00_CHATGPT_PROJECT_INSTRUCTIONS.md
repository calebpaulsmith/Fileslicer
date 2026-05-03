# ChatGPT Project Instructions — sample_input

- **Project:** sample_input
- **Target:** chatgpt
- **Mode:** balanced
- **Documents:** 5
- **Estimated total tokens:** 374
- **Per-bundle token budget:** 90,000
- **Token estimator backend:** heuristic (chars/4)

## Files in this export

- `01_SOURCE_MANIFEST.md` — index of every source document
- `manifest.csv` / `manifest.json` — machine-readable manifest
- Bundles:
  - `02_BUNDLE_001.md`
- `assets/` — copied images and other binary assets, grouped by `DOC_ID`
- `data/` — copied original CSV/XLSX files, prefixed with `DOC_ID`

## How to use this export in a ChatGPT Project

1. Create a new ChatGPT Project (or open an existing one).
2. Upload every file from this export folder, including all `02_BUNDLE_*.md` files, the `01_SOURCE_MANIFEST.md`, and any files inside `assets/` and `data/` you want the model to reference.
3. Paste the **Project instructions** below into the project's instructions field.

## Project instructions to paste

```text
You are working with curated source material for the project: sample_input.

Use the uploaded files as the primary source of truth.

Rules:
- Answer from the provided files first.
- When making source-backed claims, cite both DOC_ID and SOURCE_FILE
  (for example: "per DOC_0007 in example.html").
- Clearly separate source-backed facts from your own inference or reasoning.
- If the answer is not in the files, say so explicitly. Do not invent details.
- Preserve exact values, dates, citations, warnings, measurements,
  deadlines, and technical specifications. Do not paraphrase numbers or
  procedures.
- Do not assume missing procedures or facts. If a step is not documented,
  say it is not documented.
- The bundles are split for upload convenience; treat all bundles as one
  combined corpus.
```

## Notes

These bundle token budgets are *packaging targets* this tool uses to decide how to split content. They are NOT official platform context-window limits, which change over time. Edit the presets in `packer/presets.py` if you want different bundle sizes.

This tool does not upload anything to ChatGPT for you. Uploads are manual.
