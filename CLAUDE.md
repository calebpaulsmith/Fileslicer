# CLAUDE.md — guidance for Claude Code working in this repo

This file is loaded into Claude Code's context whenever it works in this
repository. Read it before suggesting changes.

## Product vision

`llm_project_packer` is evolving into a local **Project Context Packager**:
a tool that helps users turn messy source folders into optimized, source-safe
knowledge bundles for ChatGPT Projects, Claude Projects, one-off LLM chats,
Gemini/large-context tools, NotebookLM-style source sets, API agents, and
future local RAG workflows.

The product is not just a file combiner. Its long-term value is helping the
user choose the right packaging strategy for the job:

- repair/manual troubleshooting should preserve procedure order, warnings,
  torque specs, diagrams, and source IDs;
- FEMA/legal/policy analysis should preserve citations, source hierarchy,
  dates, authorities, issues, and appeal/case context;
- codebase understanding should preserve folder structure, README context,
  dependency files, symbols, and implementation boundaries;
- research/data projects should preserve titles, tables, units, dates,
  spreadsheet structure, and source provenance.

The tool stays local. It creates export folders and instructions; the user
manually uploads the outputs. Do not automate uploads, logins, browser flows,
or remote hosting.

## Version 1 scope (shipped)

- Local CLI only (`pack_project.py` at repo root → real entrypoint at
  `llm_project_packer/pack_project.py`).
- Recursive scan of a source folder with include/exclude filters.
- Per-type Markdown converters for txt/md, html, pdf, docx, csv, xlsx, images.
- Stable `DOC_xxxx` IDs and YAML-style identity headers
  (`DOC_ID/SOURCE_FILE/SOURCE_PATH/ORIGINAL_EXTENSION`).
- Token estimation via `tiktoken` if installed, else `chars / 4` heuristic.
- Greedy token-budget bundling into `02_BUNDLE_*.md` files.
- Three-format manifest: `01_SOURCE_MANIFEST.md`, `manifest.csv`, `manifest.json`.
- Target-specific instruction files (`00_CHATGPT_*`, `00_CLAUDE_*`,
  `00_GENERIC_*`, `00_RAG_EXPORT_NOTES.md`).
- For `--target rag`: `rag_ready/chunks.jsonl` + `rag_ready/source_map.json`.
- Per-file failure isolation; unsupported files appear in the manifest as
  `status=skipped`.

## Version 2 scope

Version 2 should be a practical local UI over the existing backend, not the
full recommendation engine. Keep it small enough to ship.

Already shipped (backend only — no Streamlit yet):

- Shared backend entry point: `run_packaging_job(...) -> PackResult` in
  `packer/pipeline.py`. CLI and future UI must both call into
  `packer.pipeline` — do not duplicate scan/convert/bundle/export logic in
  UI code. The CLI runs the pipeline through a `_print_progress` callback;
  the UI will run it through a different callback.
- Project profile storage in `packer/profiles.py`:
  - `Profile` dataclass (16 fields total) + `save_profile`,
    `load_profile`, `list_profiles`, `delete_profile`. JSON is stored under
    `~/.llm_project_packer/profiles/` by default; every function accepts a
    `profiles_dir` override so tests and a future UI can redirect the
    location.
  - `Profile.to_packaging_kwargs(source_dir=..., output_dir=...,
    project_name=...)` returns kwargs ready for `run_packaging_job`. It
    emits only the active fields and lets callers override
    source/output/project at call time without mutating the profile.
  - `profiles.ACTIVE_FIELDS` lists the eight fields that influence
    packaging today (`project_name`, `default_source_folder`,
    `default_output_folder`, `target`, `mode`, `max_bundle_tokens`,
    `include_extensions`, `exclude_dirs`). `profiles.INERT_FIELDS` lists
    seven fields that are stored and round-tripped but not yet honored by
    the backend (`include_assets`, `copy_data_files`,
    `spreadsheet_preview_rows`, `include_pdf_page_headers`,
    `include_source_metadata`, `bundle_separator_style`, `create_zip`).
  - Five built-in templates available via `get_built_in_profile(name)` and
    `list_built_in_profiles()`: `ChatGPT Balanced Project`,
    `Claude Full Project`, `Visual Repair Manual`, `RAG Ready Export`,
    `Lean One-Shot Chat`. Each call returns an independent copy.
  - Forward-compat: unknown JSON keys are dropped on load, a
    `_schema_version` is written, and a corrupt file does not break
    `list_profiles`.
- Automated tests under `llm_project_packer/tests/`:
  `test_pipeline.py` (2 cases) and `test_profiles.py` (26 cases) —
  28 in total; passes with `python -m unittest discover -s tests` or
  `pytest`.

V2 should focus on:

- optional Streamlit UI as a thin adapter over `packer.pipeline`;
- project setup screen: project name, source path, target, mode, output path;
- file scan/audit screen showing file count, type breakdown, total size,
  estimated tokens where available, unsupported files, and broken/missing
  assets surfaced by readers;
- packaging mode selector using the current modes (`lean`, `balanced`,
  `full`, `visual_manual`) plus clear UI labels such as ChatGPT Project,
  Claude Project, one-shot chat, and RAG-ready where they map to existing
  backend targets;
- file review/include-exclude before export;
- preview of manifest, bundle headers, first converted sections, warnings,
  and estimated bundle count;
- export screen with progress events, result paths, and copy-friendly
  instruction text;
- project profile UI: build the setup screen and per-screen forms on top
  of `packer.profiles` (the storage layer is already shipped).

Backend cleanup that still belongs in V2:

- Fix `bundler.Bundle.filename` so numeric prefixes remain correct past 9
  bundles.
- Split chunking out of `exporters.py` only if the UI needs chunk-preview or
  strategy controls.
- Replace any remaining direct pipeline printing with `ProgressEvent`
  callbacks while preserving CLI output.
- Keep tests and CLI smoke commands passing after every milestone.

V2 should not attempt OCR, embeddings, vector databases, automated upload,
privacy redaction, deduplication, image captioning, or a full recommendation
engine. Those belong in Version 3 or later unless explicitly approved.

## Version 3 scope

Version 3 is where the app becomes a smarter packaging assistant rather than
just a UI for the packer.

Candidate Version 3 features:

- goal selector: repair manual, FEMA/legal/policy, codebase, research,
  data/spreadsheet, reusable project knowledge, one-shot chat;
- target-platform strategy recommendations for ChatGPT Project, Claude
  Project, one-off chats, Gemini/large-context tools, NotebookLM-style source
  sets, local RAG, and API agents;
- named packaging strategies: Claude-safe bundle, ChatGPT Project bundle,
  one-shot chat bundle, RAG-ready export, visual/manual bundle, human archive;
- recommendation engine that explains why a strategy fits the source set
  and target;
- token budget planner that distinguishes "can upload" from "can reason over
  all of it at once";
- source hierarchy controls for authoritative manuals/policies, guidance,
  appeal/case decisions, internal notes, user notes, web sources, and
  inference;
- richer audit dashboard: duplicate candidates, stale sources, image-heavy
  docs, OCR-needed flags, broken links/assets, sensitive-data warnings, and
  source-quality notes;
- chunking strategies by heading, page, token count, code symbol, legal issue,
  repair procedure, disaster/applicant/project, or semantic topic;
- visual/manual enhancements: diagram index, image-reference preservation,
  optional visual companion export, and image handling controls;
- source quality scoring and deduplication;
- optional privacy/redaction workflow for SSNs, claim numbers, addresses,
  phone numbers, emails, medical info, bank/card info, VINs, and license
  plates;
- multiple export variants from the same source set.

Treat Version 3 features as design targets, not permission to implement them
early.

## Explicit exclusions

- No automated upload to ChatGPT, Claude, or any other LLM provider.
- No login automation, OAuth flows, or browser automation.
- No cloud hosting, no server, no remote storage.
- No claims that token presets equal official platform context-window limits.
- No new heavyweight dependencies without a clear reason; `tiktoken` stays
  optional.
- For V2: no OCR, embeddings, vector database, similarity search, automated
  redaction, or image captioning. These require explicit future milestones.

## Coding conventions

- Python 3.10+. Prefer standard library + the deps already in
  `requirements.txt`.
- Use `pathlib.Path`, not raw strings, for filesystem paths.
- Type hints on public functions and dataclass fields. Docstrings on
  module-level public functions and dataclasses.
- Default to no comments. Only comment when WHY is non-obvious.
- One responsibility per module. Keep `packer/` modules narrow:
  `presets`, `config`, `scanner`, `readers`, `markdown_utils`,
  `token_estimator`, `manifest`, `bundler`, `exporters`, `pipeline`,
  `profiles`.
- Readers must never raise on a single bad file; they catch their own
  exceptions and return a `ReaderResult` with `status="failed"` and a useful
  `notes` string.
- Optional dependencies (`tiktoken`, `pymupdf`, `pypdf`, `pandas`, etc.) are
  imported lazily and the tool degrades gracefully when they're missing.
- New file types: add to `presets.classify_extension`, add a `_read_<type>`
  function in `readers.py`, wire it through the dispatcher in
  `read_file`. Do not bypass the manifest.
- Generated filenames must be filesystem-safe (use
  `markdown_utils.safe_filename`) and collision-safe across folders (use
  `markdown_utils.unique_destination` or the `DOC_xxxx_` prefix pattern).
- Markdown output must include the doc identity header before the body so
  downstream LLMs can cite `DOC_ID` and `SOURCE_FILE`.

## Testing commands

Automated tests exist under `llm_project_packer/tests/`. Run them with:

```powershell
py -3 -m pytest -q llm_project_packer\tests
```

If you need to run tests from the project virtual environment instead, install
pytest into `.venv` first and use:

```powershell
.\.venv\Scripts\python.exe -m pytest -q llm_project_packer\tests
```

Every change must also be smoke-tested with the relevant manual commands below
before being declared done.

## Manual verification commands

Run from the repo root (`C:\Users\caleb\OneDrive\Desktop\Scripts\Fileslicer`):

```powershell
# Imports parse and the estimator backend resolves
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'llm_project_packer'); from packer import bundler, config, exporters, manifest, markdown_utils, pipeline, presets, profiles, readers, scanner, token_estimator; print('ok', token_estimator.estimator_backend())"

# All five built-in profile templates load and validate
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'llm_project_packer'); from packer.profiles import list_built_in_profiles, get_built_in_profile; [get_built_in_profile(n).validate() for n in list_built_in_profiles()]; print('built-ins ok:', list_built_in_profiles())"

# Four target / mode combinations against the sample input
python pack_project.py .\sample_input --target chatgpt --mode balanced --output .\test_output
python pack_project.py .\sample_input --target claude  --mode lean     --output .\test_output
python pack_project.py .\sample_input --target generic --mode full     --output .\test_output --max-bundle-tokens 5000
python pack_project.py .\sample_input --target rag     --mode balanced --output .\test_output

# CLI behaviour
python pack_project.py                                              # prints help + clear error, exit code 2
python pack_project.py .\sample_input --target chatgpt              # argparse error: --mode required
python pack_project.py .\does\not\exist --target chatgpt --mode balanced  # config error, exit code 2
```

After a run, inspect the newest folder under `.\test_output\`:

- `01_SOURCE_MANIFEST.md` — every input file present; `OK + Skipped + Failed`
  equals `Total documents`.
- `02_BUNDLE_001.md` — identity headers (`DOC_ID/SOURCE_FILE/SOURCE_PATH/
  ORIGINAL_EXTENSION`) before each body, dividers between docs, citation note
  in the bundle header.
- `manifest.csv` and `manifest.json` round-trip the same data.
- `assets/DOC_xxxx/` for image-bearing docs; `data/DOC_xxxx_*` for CSV/XLSX.
- For `--target rag`: `rag_ready/chunks.jsonl` (one JSON per line) and
  `rag_ready/source_map.json` (doc_id → chunk_ids).

## Output folder expectations

For `--target chatgpt | claude | generic`:

```
<output>/
  PROJECT_NAME_TARGET_MODE_TIMESTAMP/
    00_*_INSTRUCTIONS.md
    01_SOURCE_MANIFEST.md
    manifest.csv
    manifest.json
    02_BUNDLE_001.md
    03_BUNDLE_002.md
    ...
    assets/
      DOC_xxxx/
    data/
      DOC_xxxx_<original-name>.<ext>
```

For `--target rag`:

```
<output>/
  PROJECT_NAME_rag_MODE_TIMESTAMP/
    00_RAG_EXPORT_NOTES.md
    01_SOURCE_MANIFEST.md
    manifest.csv
    manifest.json
    assets/
    data/
    rag_ready/
      chunks.jsonl
      source_map.json
```

Rules for output:

- The export folder name is `safe_filename(f"{project}_{target}_{mode}_{timestamp}")`.
- The export folder must be created fresh on every run; never overwrite or
  reuse a previous timestamped folder.
- `assets/` and `data/` always exist (even if empty) so downstream tooling
  can rely on them.
- If the resolved `--output` lives inside `--source`, the scanner must skip
  it automatically so old exports don't get re-packed.

## Repository rules (must hold for every change)

1. **Do not automate uploading to ChatGPT or Claude.** This tool produces
   files on the user's disk. The user uploads them by hand. No browser
   automation, no API uploads, no clipboard tricks, no "open the project
   page for me" shortcuts. Instructions are written into the `00_*` files;
   the act of uploading stays with the user.

2. **Preserve CLI behavior while adding UI.** Any future Streamlit (or other
   UI) work must not change CLI flags, defaults, exit codes, output folder
   layout, or generated file contents. The smoke-test commands above must
   keep producing equivalent output. If a CLI change is genuinely needed,
   call it out explicitly and document it in this file before shipping.

3. **Prefer backend refactoring over duplicating logic in Streamlit.** When
   the UI needs scan / convert / bundle / chunk / write logic, refactor the
   `packer/` package so both the CLI and the UI consume the same functions.
   No copy-pasted scan loops, no second token estimator, no second manifest
   writer in the UI layer. The UI is an adapter, not a parallel
   implementation.

4. **One bad input file must not crash an entire packaging job.** Reader
   exceptions are caught inside `readers.read_file` and converted to
   `ReaderResult(status="failed", notes=...)`. Optional-dependency failures
   degrade gracefully (e.g. PDF without `pymupdf`/`pypdf` records a failed
   manifest entry but the run continues). Anywhere a new I/O step is added,
   the same rule applies: catch per-file errors, record them in the manifest,
   keep going.

5. **Profile fields are explicit about active vs inert.** Every field on
   `packer.profiles.Profile` must appear in either `ACTIVE_FIELDS` (and be
   wired through `Profile.to_packaging_kwargs` plus `run_packaging_job`) or
   `INERT_FIELDS` (stored and round-tripped only). Saved JSON must round-trip
   for every field on disk — never silently drop a known field. When wiring
   an inert field, move its name from `INERT_FIELDS` to `ACTIVE_FIELDS` in
   the same change and update `to_packaging_kwargs`.

## Definition of done for any feature

A change is not done until all of the following hold:

1. The feature works against `.\sample_input` for every target/mode the
   change could affect (use the smoke-test commands above).
2. No regression: existing manual verification commands still succeed and
   still produce the documented output structure.
3. Errors on a single bad input file are caught and recorded in the
   manifest; the rest of the run completes.
4. New code follows the conventions in this file: `pathlib`, type hints on
   public surfaces, docstrings on public functions/dataclasses, no
   gratuitous comments, lazy imports for optional deps.
5. New file types or output artifacts are reflected in `README.md`,
   `presets.py` (if a new extension), and the relevant `00_*` instruction
   templates (if user-visible).
6. Automated tests pass:
   `py -3 -m pytest -q llm_project_packer\tests`.
7. If the change touches the public pipeline (scan/convert/assemble), both
   the CLI and any UI adapter exercise the same code path — no duplicated
   logic.
8. If anything in this file becomes wrong, this file is updated in the same
   change.
