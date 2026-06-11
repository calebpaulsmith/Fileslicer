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

Already shipped:

- Shared backend entry point: `run_packaging_job(...) -> PackResult` in
  `packer/pipeline.py`. CLI and future UI must both call into
  `packer.pipeline` — do not duplicate scan/convert/bundle/export logic in
  UI code. The CLI runs the pipeline through a `_print_progress` callback;
  the UI will run it through a different callback.
- Streamlit UI at the repo root (`streamlit_app.py` +
  `requirements-ui.txt`). Launches with
  `streamlit run streamlit_app.py`. Today it loads built-in templates,
  loads / saves user profiles via `packer.profiles`, lets the user edit
  every active and inert profile field, includes a scan/audit dashboard
  plus file review include/exclude controls, previews the planned export,
  and calls `run_packaging_job` to create local bundles. The CLI is
  unchanged. Streamlit lives in
  `requirements-ui.txt`, never in the core `requirements.txt`. Profiles
  edited in the UI live at
  `~/.llm_project_packer/profiles/`, the same location the CLI's profile
  API reads from.
- Scan/audit screen in `streamlit_app.py`: "Scan Source Folder" and
  "Re-scan" use `packer.scanner.scan_directory(...)` plus
  `packer.presets.classify_extension(...)` only. The dashboard is read-only:
  totals, supported/unsupported counts, extension and file-type breakdowns,
  total size, duplicate filename groups, applied exclude directories,
  zero-supported warning, and a sortable file dataframe with read-only
  `will_process`. Scan results are cached in `st.session_state` by the
  resolved source/include/exclude tuple. This screen does not call readers,
  `run_packaging_job`, or write files.
- File review/include-exclude in `streamlit_app.py`: after a successful scan,
  the UI shows discovered files with editable include flags, file name,
  relative path, extension, file type, size, status, and notes. Supported
  files (`file_type != "unsupported"`) default included; unsupported files
  default excluded but remain visible with clear notes. Search by file
  name/path, extension filtering, include/exclude all, include/exclude
  visible, and include/exclude by extension are implemented. Selections live
  in `st.session_state["file_review_selections"]` as
  `{repr(scan_key): {relative_path: bool}}`, with relative paths as stable
  identities. Re-scans preserve selections for paths still present, add new
  files with the support-status defaults, and drop missing paths. Export
  passes included relative paths to `run_packaging_job(included_files=...)`
  so excluded files are not processed.
- Preview/export in `streamlit_app.py`: after scan/review, the UI shows
  included and skipped counts, rough bundle count, target/mode, max bundle
  tokens, planned output folder pattern, warning notes, and an instruction
  preview generated in a temporary directory. The `Create LLM Project
  Bundles` button calls the shared backend, displays progress messages,
  stores the `PackResult` in session state, lists generated files, shows
  success/failure counts, and renders target-specific manual upload
  instructions. It does not automate upload to any LLM.
- Packaging settings in `streamlit_app.py`: after scan/review, the UI shows
  target/mode, default token budget, resolved budget, max-token override,
  rough selected-token estimate, and projected bundle count. Override values
  are stored on the active `Profile` and passed to the export call.
- Document chunk review in `streamlit_app.py`, backed by `packer/chunking.py`:
  chunking was split out of `exporters.py` into `packer.chunking`
  (`Chunk`, `chunk_markdown`, `chunk_document`); the RAG export now calls
  `chunking.chunk_markdown` with identical output. The UI section sits
  between file review and packaging settings: the user picks a chunk size
  in tokens (default 800), previews how one included document splits into
  chunks via `pipeline.preview_document_chunks(...)` (conversion happens in
  a temporary workspace using a fixed-width `DOC_0000` placeholder id so
  asset links don't shift chunk boundaries), and toggles per-chunk include
  flags. Chunking behavior is transparent: every chunk carries a
  `boundary_reason` (one of the `chunking.REASON_*` constants explaining why
  its boundary was drawn) and a `ChunkStructure` summary (headings,
  paragraph/list-item/table-row counts via
  `chunking.analyze_markdown_structure`, skipping fenced code). The chunk
  table shows heading, structure, and boundary columns, and a "Corpus
  chunking audit" expander converts every included document at the current
  chunk size to show corpus-wide totals, size distribution, a
  boundary-reason breakdown, per-document chunk stats, and over-budget
  chunk warnings — this is the V2 seed for V3 chunking-strategy rules.
  Selections live in `st.session_state["chunk_review_selections"]`
  as `{repr(scan_key): {relative_path: {"budget", "selected", "total"}}}`;
  changing the chunk size clears selections made at a different size.
  Export passes partial selections to
  `run_packaging_job(chunk_selections=..., chunk_token_budget=...)`. The
  pipeline re-chunks each selected document with the same deterministic
  chunker, keeps only the selected 1-based chunk indices, rebuilds the
  `ConvertedDoc`, and appends a "Partial content: kept m of n chunks" note
  to the manifest entry. An explicit empty selection records the document
  as `status=skipped` with a clear note; out-of-range indices and
  selections for unprocessed files produce warnings without failing the
  run. Documents without a chunk selection export in full. The CLI is
  unchanged.
- Chunking strategies and guidance (approved pull-forward of the V3
  "chunking by heading" candidate; the richer strategies stay V3):
  `chunking.STRATEGY_TOKENS` (V1 paragraph packing) and
  `chunking.STRATEGY_HEADINGS` (`split_into_heading_sections` +
  `chunk_markdown_by_headings_with_reasons`: a new chunk starts at every
  heading of the chosen level or shallower, deeper headings stay inside
  their section, oversize sections fall back to the token chunker, and
  documents without qualifying headings fall back entirely).
  `run_packaging_job` accepts `chunk_strategy` and `chunk_heading_level`;
  chunk-selection re-chunking and `preview_document_chunks` honor them.
  For `--target rag`, a provided `chunk_token_budget`/`chunk_strategy`
  shapes `rag_ready/chunks.jsonl`; without them V1 output is byte-identical.
  The UI's chunk review has a strategy selector and heading-level control,
  clears selections made under different settings, and always passes the
  current review settings to export so a UI RAG export matches the preview.
  `pipeline.chunking_guidance(previews, budget, strategy, target)` turns a
  corpus audit into plain-language tips (over-budget chunks, heading-rich
  corpora, tiny boilerplate chunks, single-chunk documents, RAG chunk-size
  range); the corpus audit expander renders them under "Chunking guidance".
  Documented generated-file change: `00_RAG_EXPORT_NOTES.md` gained an
  "Optimizing this export for retrieval" section with static RAG tips.
- Corpus chunk rules: `Profile.chunk_exclude_headings` (active field) holds
  case-insensitive glob patterns (e.g. `*_html`, `content_hash`) matched by
  `chunking.match_heading_patterns` against each chunk's first heading.
  `run_packaging_job(chunk_exclude_headings=...)` drops matching chunks
  from every document that has no explicit `chunk_selections` entry — an
  explicit per-document selection always wins. Trimmed documents get an
  "Excluded m of n chunks via corpus heading rules" manifest note; a
  document whose chunks all match is recorded as `status=skipped`; rules
  that match nothing produce warnings without failing the run. In the UI
  the rules live in a text input in chunk review (bound to the profile and
  saved with it), rule-matched chunks default to deselected in per-document
  previews, the corpus audit shows per-rule match counts and flags rules
  that match nothing, and changing the rules clears selections like any
  other chunk-setting change.
- Profile-bound chunk settings: `Profile.chunk_token_budget` (None means
  the pipeline default), `Profile.chunk_strategy`, and
  `Profile.chunk_heading_level` are active fields emitted by
  `to_packaging_kwargs`, validated against `chunking.STRATEGIES` and
  heading levels 1–6. The chunk review widgets bind to them (loading a
  profile refreshes the widgets; edits write back), and the export path
  reads the profile, so a saved profile captures the full chunking
  configuration — size, strategy, heading level, and exclusion rules. The
  `RAG Ready Export` built-in template now sets `chunk_token_budget=800`,
  so running it via `to_packaging_kwargs` produces retrieval-sized chunks
  by default.
- Profile-bound file review selection: `Profile.exclude_files` (active
  field) holds case-insensitive glob patterns matched by
  `scanner.match_path_patterns` against source-relative POSIX paths.
  `run_packaging_job(exclude_files=...)` drops matching files after the
  scan so they never appear in the manifest; patterns matching nothing
  warn without failing. `included_files` is an explicit allowlist that
  already encodes exclusions, so callers pass one or the other — the UI
  export keeps passing `included_files`, while profile-driven runs use
  `exclude_files`. In file review, deselecting a supported file writes
  its exact path back to the profile and a fresh scan defaults files
  matching the profile patterns to excluded (per-scan selections still
  win); hand-written globs in profile JSON are honored at scan defaults
  and profile-driven exports but the UI rewrites the list with exact
  paths when the selection changes.
- Project profile storage in `packer/profiles.py`:
  - `Profile` dataclass (21 fields total) + `save_profile`,
    `load_profile`, `list_profiles`, `delete_profile`. JSON is stored under
    `~/.llm_project_packer/profiles/` by default; every function accepts a
    `profiles_dir` override so tests and a future UI can redirect the
    location.
  - `Profile.to_packaging_kwargs(source_dir=..., output_dir=...,
    project_name=...)` returns kwargs ready for `run_packaging_job`. It
    emits only the active fields and lets callers override
    source/output/project at call time without mutating the profile.
  - `profiles.ACTIVE_FIELDS` lists the thirteen fields that influence
    packaging today (`project_name`, `default_source_folder`,
    `default_output_folder`, `target`, `mode`, `max_bundle_tokens`,
    `include_extensions`, `exclude_dirs`, `exclude_files`,
    `chunk_exclude_headings`, `chunk_token_budget`, `chunk_strategy`,
    `chunk_heading_level`).
    `profiles.INERT_FIELDS` lists
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
- JSON file support in `packer/presets.py` and `packer/readers.py`:
  `.json` classifies as file type `json` and `_read_json` renders objects
  as Markdown with one heading per key (top level `##`, nested objects one
  level deeper, scalar lists as bullets, explicit `(null)` / `(empty list)`
  markers). Invalid JSON records a failed manifest entry without raising.
  This makes structured records (e.g., scraped FEMA appeal JSON) flow
  through scan, chunk review, and export with field-aligned headings.
- Automated tests under `llm_project_packer/tests/`:
  `test_pipeline.py` (22 cases), `test_chunking.py` (26 cases),
  `test_readers.py` (6 cases), and `test_profiles.py` (31 cases) — 85 in
  total; passes with `python -m unittest discover -s tests` or `pytest`.

V2 should focus next on (in roughly this order):

- **profile UI extensions** — done: chunk settings, chunk rules, and the
  file review selection (`exclude_files`) are all bound to the `Profile`,
  so a saved profile captures the user's full configuration.

Backend cleanup that still belongs in V2:

- Fix `bundler.Bundle.filename` so numeric prefixes remain correct past 9
  bundles.
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
- chunking strategies beyond the shipped token/heading pair: by page, code
  symbol, legal issue, repair procedure, disaster/applicant/project, or
  semantic topic;
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
  `token_estimator`, `manifest`, `bundler`, `chunking`, `exporters`,
  `pipeline`, `profiles`.
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

UI smoke checks for the scan/review screens:

```powershell
# Syntax check
python -m py_compile streamlit_app.py

# Headless boot; expect HTTP 200 from curl.exe, then stop Streamlit with Ctrl+C
streamlit run streamlit_app.py --server.headless=true --server.port=8519
curl.exe -I http://localhost:8519
```

Manual Streamlit inputs and expected outputs:

- Source folder: `.\sample_input`; click `Scan Source Folder`.
  Expected: `Discovered = 5`, `Supported = 5`, `Unsupported = 0`,
  `Included = 5`, and all rows default included.
- In file review, click `Exclude all files`.
  Expected: `Included = 0`; all visible include flags are unchecked.
- Select `.txt` in `Extension action target`, click `Include by extension`.
  Expected: `Included = 1`; filtering/search changes do not reset it.
- Search for `notes`, click `Exclude visible files`.
  Expected: only currently visible matching rows are changed; hidden rows keep
  their previous selection.
- Add an unsupported file such as `sample_input\scratch.tmp`, then click
  `Re-scan`.
  Expected: the unsupported row remains visible, defaults excluded, has
  `status = unsupported`, and notes explain that the extension is unsupported.
- For re-scan preservation, start with a supported file excluded, add a new
  supported file, remove a different file, then click `Re-scan`.
  Expected: the still-present excluded path remains excluded, the new
  supported file defaults included, unsupported files default excluded, and
  removed paths disappear from the selection state.
- In `Document chunk review`, set `Chunk size (tokens)` to `50`, pick a
  multi-paragraph document, click `Preview chunks`.
  Expected: the chunk table lists every chunk with token estimates, first
  heading, structure summary, and boundary reason; all chunks default
  included and `Selected tokens` equals the document total.
- Open `Corpus chunking audit`, click `Analyze corpus chunking`.
  Expected: totals for documents/chunks/tokens, smallest/median/largest
  chunk sizes, a boundary-reason breakdown table, a per-document table with
  chunk counts and over-budget flags, a warning when any chunk exceeds
  the budget (long unbreakable lines), and a `Chunking guidance` block with
  plain-language tips (or a "nothing stood out" caption).
- Switch `Chunking strategy` to `Heading sections (split at headings)`,
  preview a document with headings (e.g., a converted JSON record).
  Expected: one chunk per heading section with boundary reason
  `section starts at a heading`; selections made under the token strategy
  are cleared with an info message; `Split at heading level` appears.
- With the heading strategy and `--target rag` semantics in mind, export a
  RAG profile from the UI after setting chunk size/strategy.
  Expected: the preview warns which chunk settings `rag_ready/chunks.jsonl`
  will use, and the JSONL chunk boundaries match the previewed chunks.
- Uncheck one chunk, then export.
  Expected: the preview warns that one document has a partial chunk
  selection, the bundle omits the deselected chunk's text, and the manifest
  entry notes `Partial content: kept m of n chunks`.
- Click `Exclude all chunks`, then export.
  Expected: a warning that the document will be skipped; the manifest
  records `status = skipped` with an "all chunks deselected" note and the
  bundle omits the document entirely.
- Change `Chunk size (tokens)` after making a selection.
  Expected: selections made at the old size are cleared and an info message
  reports how many were reset.
- Enter `url, *_html` in `Corpus chunk rules`, preview a converted JSON
  record with the heading strategy.
  Expected: chunks whose first heading matches default to deselected with
  an info message; the corpus audit lists per-rule match counts; export
  trims matching chunks from documents that were never previewed and the
  manifest notes `Excluded m of n chunks via corpus heading rules`; a rule
  matching nothing produces a warning, and an explicit per-document
  selection overrides the rules for that document.
- Load the `RAG Ready Export` built-in, then scan.
  Expected: `Chunk size (tokens)` shows `800` from the profile; changing
  strategy/size/level updates the profile, and `Save profile` round-trips
  the chunk settings so a reloaded profile restores them.
- Exclude a supported file in file review, save the profile, load it
  fresh, and scan again.
  Expected: the profile JSON lists the path under `exclude_files`, the
  fresh scan defaults that file to excluded while new files stay
  included, and a profile-driven export (`to_packaging_kwargs`) omits the
  file from the manifest entirely.

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
