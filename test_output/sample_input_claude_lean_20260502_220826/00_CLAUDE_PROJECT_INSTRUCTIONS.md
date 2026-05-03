# Claude Project Instructions — sample_input

- **Project:** sample_input
- **Target:** claude
- **Mode:** lean
- **Documents:** 5
- **Estimated total tokens:** 375
- **Per-bundle token budget:** 80,000
- **Token estimator backend:** heuristic (chars/4)

## Files in this export

- `01_SOURCE_MANIFEST.md` — index of every source document
- `manifest.csv` / `manifest.json` — machine-readable manifest
- Bundles:
  - `02_BUNDLE_001.md`
- `assets/` — copied images and other binary assets, grouped by `DOC_ID`
- `data/` — copied original CSV/XLSX files, prefixed with `DOC_ID`

## How to use this export in a Claude Project

1. Create a new Claude Project (or open an existing one).
2. Add every file from this export folder to the project's **Project knowledge** (bundles, manifest, and any `assets/` or `data/` files you want available).
3. Paste the **Custom instructions** below into the project's custom-instructions field.

## Custom instructions to paste

```text
You are working with the Project knowledge base for: sample_input.

Treat the uploaded files as the project knowledge base and your primary
source of truth.

Rules:
- Prefer exact, source-backed answers grounded in the uploaded files.
- Cite both DOC_ID and SOURCE_FILE when you reference the knowledge base
  (for example: "per DOC_0007 in example.html").
- Clearly separate source facts from your reasoning or inference.
- Avoid over-generalizing from incomplete sources. If only one document
  describes a procedure, say so rather than presenting it as universal.
- Preserve exact values, dates, warnings, measurements, deadlines, and
  technical specifications without paraphrasing.
- If the answer is not in the knowledge base, say so explicitly.
- The bundles are split for upload convenience; treat all bundles as one
  combined knowledge base.
```

## Notes

These bundle token budgets are *packaging targets* this tool uses to decide how to split content. They are NOT official platform context-window limits, which change over time. Edit the presets in `packer/presets.py` if you want different bundle sizes.

This tool does not upload anything to Claude for you. Uploads are manual.
