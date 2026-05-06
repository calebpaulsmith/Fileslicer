# TODO.md — Version 2 implementation plan

Goal: add a local Streamlit UI on top of the existing Version 1 CLI without
breaking CLI behavior or duplicating processing logic.

This is a plan only. Do not implement until each milestone is approved.

## Guiding rules (from CLAUDE.md, repeated for discoverability)

- The CLI must keep working exactly as today: same flags, same defaults,
  same exit codes, same output folder layout, same file contents.
- Streamlit is an adapter over the backend. Every scan / convert / bundle /
  chunk / write call goes through shared `packer/` functions — never a
  parallel implementation in the UI layer.
- One bad input file must never crash a run. Errors are caught per file and
  recorded in the manifest with `status="failed"`.
- No automated upload to ChatGPT or Claude. The UI shows the export folder
  and instruction text; the user uploads by hand.

## Milestone summary

Status legend: ✅ shipped · 🟡 in progress · ⚪ not started

| # | Status | Milestone | Touches | Output |
|---|---|---|---|---|
| 1 | ✅ | Refactor backend into reusable functions | `pack_project.py`, `packer/` | `packer/pipeline.py` with `run_packaging_job(...) -> PackResult` |
| 2 | ✅ | Add dataclasses / options / result objects | `packer/pipeline.py` | `PackResult`, `ProgressEvent`, manifest-paths dict |
| 3 | ✅ | Add project profile support | `packer/profiles.py`, `tests/test_profiles.py` | Save/load/list/delete + 5 built-in templates + `to_packaging_kwargs()` |
| 4 | ✅ | Streamlit project setup screen | `streamlit_app.py`, `requirements-ui.txt` | UI skeleton: built-in/saved profile selectors + setup/packaging/advanced/save sections |
| 5 | ✅ | Source scan / audit screen | `streamlit_app.py` | Read-only scan dashboard |
| 6 | ✅ | File review / include-exclude | `streamlit_app.py` | Session-state per-file selection for a future `included_files` hook |
| 7 | ✅ | Packaging settings screen | `streamlit_app.py` | Override surface + projected bundle count |
| 8 | ✅ | Preview screen | `streamlit_app.py` | Selection-based summary + instruction preview + warnings |
| 9 | ✅ | Export / progress / results | `streamlit_app.py` | Calls `run_packaging_job` with included files + progress + results |
| 10 | 🟡 | README + manual test instructions | `README.md`, `CLAUDE.md` | Docs follow each shipped milestone |

Notes since the original plan was written:

- Milestones 1–9 are merged. The pipeline
  signature settled on
  `run_packaging_job(source_dir, output_dir, project_name, target, mode,
  max_bundle_tokens=None, include_extensions=None, exclude_dirs=None,
  included_files=None, options=None, progress_callback=None) -> PackResult`.
  The UI now passes selected relative paths through `included_files` when
  creating an export.
- The UI is a single-file Streamlit app today (`streamlit_app.py`) rather
  than the originally planned `streamlit_ui/` package. Splitting into
  per-screen modules is fine when the file gets long; do it without
  ceremony.
- File review state is keyed by the resolved scan tuple and uses relative
  paths as the stable file identity:
  `st.session_state["file_review_selections"] == {repr(scan_key):
  {relative_path: bool}}`. Re-scans preserve selections for paths still
  present, default new supported files included, default new unsupported
  files excluded, and drop missing paths.
- Preview/export shipped as a single-file `streamlit_app.py` implementation:
  preview uses scan metadata plus current selections for counts, rough bundle
  estimates, warnings, output-folder pattern, and temporary instruction-file
  preview. Export calls `run_packaging_job` with `included_files`, displays
  progress messages, generated files, success/failure counts, and manual
  target-specific upload instructions. It does not automate upload.
- Packaging settings shipped in `streamlit_app.py`: after scan/review it
  shows target/mode, default budget, resolved budget, a max-token override,
  rough selected-token estimate, and projected bundle count.
- The "Advanced options" expander already binds every inert profile field
  (`include_assets`, `copy_data_files`, `spreadsheet_preview_rows`,
  `include_pdf_page_headers`, `include_source_metadata`,
  `bundle_separator_style`, `create_zip`). When any of these get wired into
  the pipeline they move from `profiles.INERT_FIELDS` to
  `profiles.ACTIVE_FIELDS` per the rule in CLAUDE.md.

## How V2 connects to the longer-term Project Context Packager vision

The product vision in `CLAUDE.md` (goal selector, target-platform strategy
recommendations, named packaging strategies, recommendation engine, source
hierarchy, richer audit dashboard, chunking strategies, source quality
scoring, deduplication, privacy redaction) is **V3** work, not V2.

V2's job is to make the existing backend usable from a UI, with one
explicit alignment to V3:

- The scan/audit screen (milestone 5) is the seed for the V3 audit
  dashboard. V2 ships only the cheap, read-only metrics derivable from
  `scanner.scan_directory` + `presets.classify_extension`. Anything that
  requires running the readers (broken images, OCR-needed flags) is a
  later optional pass; anything that requires content hashing
  (deduplication), heuristics (sensitive data, source quality scoring), or
  recommendations is V3.

V2 does not introduce: goal selectors, named packaging strategies that
aren't already a target/mode pair, the recommendation engine, source
hierarchy, chunking-strategy selector, OCR, dedup, sensitive-data
detection, privacy redaction, or multiple-export comparison. Those wait.

---

## Milestone 1 — Refactor backend into reusable functions

### Files to modify
- `llm_project_packer/pack_project.py` — shrink `run(cfg)` to a thin CLI
  adapter that calls the new pipeline and prints progress events.

### Files to create
- `llm_project_packer/packer/pipeline.py` — public functions
  `scan(cfg)`, `convert(cfg, scanned, on_progress=None)`,
  `assemble(cfg, manifest, converted_docs, on_progress=None)`,
  and the convenience `pack(cfg, on_progress=None) -> PackResult`.

### Behavior
- `scan(cfg) -> ScanResult` returns the list of `ScannedFile` plus a
  classification breakdown (counts by `file_type`, total bytes). Pure read.
- `convert(cfg, scanned, on_progress) -> (Manifest, list[ConvertedDoc])`
  iterates the readers, builds `ManifestEntry` + `ConvertedDoc`, and emits
  `ProgressEvent` items. Does not write any files except asset/data copies
  performed by readers (which need an `assets_dir` / `data_dir` — see below).
- `assemble(cfg, manifest, converted_docs, on_progress) -> PackResult`
  writes bundles (or RAG chunks), manifest, and instruction files. Returns a
  fully populated `PackResult`.
- `pack(cfg, on_progress) -> PackResult` is the all-in-one shortcut the CLI
  uses; the UI is free to call the three steps individually.
- Reader asset/data targets currently live under the export folder. To let
  the UI scan/preview without committing, introduce a `WorkspacePaths`
  dataclass (export_dir, assets_dir, data_dir) and let the caller pass a
  temp workspace for previews.

### Tests / manual checks
- New `llm_project_packer/tests/test_pipeline.py`:
  - `scan` returns the expected file count for `sample_input/`.
  - `convert` populates a manifest with one entry per scanned file and
    `len(converted_docs) == count(status="ok" with non-empty body)`.
  - `pack` against `sample_input/` for each `(target, mode)` combo writes
    the documented output structure.
- Re-run all CLI smoke commands from CLAUDE.md; output must be byte-equivalent
  to a pre-refactor baseline (capture before, diff after — accept only
  timestamp/path differences).

### Risk areas
- Asset/data copy currently happens inside readers and assumes an export
  folder exists already. Splitting `convert` from `assemble` requires a
  workspace path before `assemble` runs.
- Preserving exact bundle/manifest content under refactor (whitespace, doc
  order, manifest column order) is fragile — easy to drift.
- `print()`-based logging in `run()` must move into the CLI adapter, not the
  pipeline.

### Acceptance criteria
- `pack(cfg)` produces output identical to today's `run(cfg)` for every
  smoke-test command (modulo timestamp).
- The CLI module's only responsibility is argparse → `PackerConfig` →
  `pack()` + a `print` callback. No business logic remains in
  `pack_project.py`.
- All public pipeline functions have type hints and a one-line docstring.

---

## Milestone 2 — Dataclasses / options / result objects

### Files to modify
- `llm_project_packer/packer/pipeline.py` — adopt the new types.
- `llm_project_packer/packer/manifest.py` — accept a precomputed counts
  helper if needed (read-only).

### Files to create
- `llm_project_packer/packer/events.py` — `ProgressEvent` dataclass
  (`kind`, `message`, `doc_id`, `current`, `total`, `level`).
- The result/option dataclasses live in `pipeline.py`:
  - `WorkspacePaths(export_dir, assets_dir, data_dir)`
  - `ScanResult(files, counts_by_type, total_bytes)`
  - `ConversionResult(manifest, converted_docs, stats)`
  - `ConversionStats(ok, skipped, failed, total_tokens)`
  - `PackResult(export_dir, bundle_paths, manifest_paths, rag_paths,
    instruction_path, manifest, converted_docs, stats, scanned_files)`

### Behavior
- `ProgressEvent.kind` is one of `scan_start`, `scan_done`, `file_start`,
  `file_done`, `bundle_written`, `manifest_written`, `instruction_written`,
  `rag_written`, `done`, `error`.
- Pipeline functions accept `on_progress: Callable[[ProgressEvent], None] | None`.
- `PackResult` is JSON-serializable via `dataclasses.asdict` so the UI can
  cache it in `st.session_state` without custom encoders.

### Tests / manual checks
- `tests/test_events.py`: emitted event sequence for a 3-file run.
- `tests/test_pipeline.py`: `PackResult.stats.ok + skipped + failed`
  equals total scanned files.
- CLI smoke run still succeeds; the new `print()` adapter formats events
  the same way the V1 output looked (compare line-for-line).

### Risk areas
- Over-modeling. Keep dataclasses small and focused; resist adding helpers
  that aren't used by either CLI or UI.
- `ConvertedDoc` already exists in `bundler.py`; do not duplicate it.

### Acceptance criteria
- Every pipeline function signature uses the new types.
- The CLI's progress output is generated from `ProgressEvent`s, not from
  scattered `print` calls inside the pipeline.

---

## Milestone 3 — Project profile support

### Files to modify
- `llm_project_packer/packer/config.py` — add `Profile.to_config()` and
  `PackerConfig.from_profile()` adapters; do not let `Profile` replace
  `PackerConfig`.

### Files to create
- `llm_project_packer/packer/profiles.py` — `Profile` dataclass +
  `load_profile`, `save_profile`, `list_profiles`, `delete_profile`.
- `profiles/` (gitignored except for `.gitkeep`) — default storage location.

### Behavior
- A `Profile` captures every UI-relevant setting:
  - `name`, `source_dir`, `output_dir`, `target`, `mode`,
    `max_bundle_tokens`, `include_extensions`, `exclude_dirs`,
    `selected_doc_ids` (per-file overrides — see milestone 6),
    `created_at`, `updated_at`, `notes`.
- Stored as JSON under `profiles/<safe_filename(name)>.json`.
- The CLI keeps working without profiles. A new optional flag
  `--profile <name>` (V2-only) loads a profile and lets other CLI flags
  override fields. Defaults are unchanged.

### Tests / manual checks
- `tests/test_profiles.py`: round-trip save/load preserves every field;
  `list_profiles()` returns saved profiles sorted by `updated_at` desc.
- Manual: `python pack_project.py --profile demo` runs the same pack the UI
  would run for that profile.

### Risk areas
- File-locking on Windows when two processes touch the same profile file.
  Acceptable for V2: last-write-wins; document it.
- Path portability — store paths as absolute strings; warn on load if a
  path no longer exists (do not crash).

### Acceptance criteria
- A profile saved by the UI can be re-run by the CLI and produces the same
  export structure.
- Profile JSON is human-readable and editable by hand.

---

## Milestone 4 — Streamlit project setup screen

### Files to modify
- `llm_project_packer/requirements-ui.txt` (new) — `streamlit>=1.30`.
  Do NOT add Streamlit to the core `requirements.txt`.
- `README.md` — note the optional UI install path; CLI install unchanged.

### Files to create
- `streamlit_app.py` (repo root) — entrypoint:
  `streamlit run streamlit_app.py`.
- `streamlit_ui/__init__.py`
- `streamlit_ui/state.py` — `st.session_state` keys, helpers, navigation.
- `streamlit_ui/setup_screen.py` — first screen.

### Behavior
- Sidebar: profile picker (load existing or "+ New profile").
- Main area:
  - Project name (free text, defaults to source folder name).
  - Source directory: text input + folder-picker hint (Windows browser
    integrations are unreliable; document this).
  - Target dropdown (`chatgpt | claude | generic | rag`).
  - Mode dropdown (`lean | balanced | full | visual_manual`).
  - "Save profile" + "Continue" buttons.
- Continue persists the profile and advances to the scan screen.

### Tests / manual checks
- Manual: launch the app, create a new profile pointing at `sample_input/`,
  verify it appears in `profiles/`, reload the app, confirm the profile
  loads back into the form.
- CLI regression: re-run all CLAUDE.md smoke commands.

### Risk areas
- Folder pickers in Streamlit are limited; avoid third-party components
  that pull in heavy native deps. A plain text input is acceptable for V2.
- Streamlit reruns the whole script on every interaction — keep
  `setup_screen.render()` cheap and read-only until the user clicks save.

### Acceptance criteria
- Setup screen creates and loads profiles end-to-end.
- No state leaks between sessions: closing and reopening the app shows the
  expected last-active profile (or none).

---

## Milestone 5 — Source scan / audit screen

### Files to modify
- `streamlit_app.py` — add a "Scan Source Folder" button and a
  read-only audit dashboard. Cache the result in `st.session_state` keyed
  by the resolved source/include/exclude tuple so a re-render does not
  re-walk the disk.

### Files to create
- None required; only split `streamlit_app.py` into a `streamlit_ui/`
  package if the file gets unwieldy.

### Behavior
- Button reuses `packer.scanner.scan_directory(source, include, exclude)`
  exactly as the CLI / pipeline already do — no parallel scan logic.
- Show, all derivable from the existing `ScannedFile` records and
  `presets.classify_extension`:
  - total files found
  - supported files (anything not classified `unsupported`)
  - unsupported files
  - counts by extension and by `file_type` (text / html / pdf / docx /
    csv / xlsx / image / unsupported)
  - total bytes (sum of `ScannedFile.size_bytes`), human-readable
  - duplicate filenames within the source tree (group by lowercase
    `relative_path.name`, list the duplicates) — this is filename-only,
    NOT content hashing
  - the resolved exclude-dirs that the scan actually applied (merge of
    `presets.DEFAULT_EXCLUDE_DIRS` + profile's `exclude_dirs`)
  - clear warning when zero supported files are found
- Render the file list as a sortable Streamlit dataframe with columns
  `relative_path`, `file_type`, `extension`, `size_bytes`, and a
  read-only `will_process` flag. Per-file include/exclude controls are
  milestone 6, not here.
- "Re-scan" button invalidates the cache and re-runs.
- No conversion. Do not call `run_packaging_job`. Do not write files.

### Tests / manual checks
- Unit: a helper that aggregates `List[ScannedFile]` into the audit
  summary (counts, totals, duplicates) is pure and unit-testable.
- Manual: scan `sample_input/`; total files matches what
  `01_SOURCE_MANIFEST.md` reports from a CLI run, and the duplicate-filename
  list is empty.
- Manual: drop a deliberately-named duplicate
  (e.g. add `sample_input/notes/README.md` clone elsewhere); duplicate
  list shows it.

### Risk areas
- Large source folders (10k+ files): keep the dataframe paginated or
  capped, and surface a count near any cap in the UI.
- OneDrive-on-demand folders may trigger downloads when walked.
  Document this; do not silently force-download.
- Don't smuggle V3 features in. OCR-needed flags, broken-image detection,
  content-hash deduplication, sensitive-data warnings, and source-quality
  scoring are V3 and require explicit milestones.

### Acceptance criteria
- Audit values in the UI agree with what
  `packer.scanner.scan_directory` + `presets.classify_extension` return
  from a Python REPL with the same inputs.
- The CLI smoke commands in CLAUDE.md still pass.
- No new top-level dependencies added; Streamlit stays in
  `requirements-ui.txt` only.

---

## Milestone 6 — File review / include-exclude

### Files to modify
- `streamlit_app.py` — shipped in the single-file UI. No backend, profile,
  CLI, reader, export, or pipeline behavior changed in this milestone.

### Files to create
- None. A future split into `streamlit_ui/review_screen.py` is still allowed
  when the Streamlit app gets large enough to justify it.

### Behavior
- After a successful scan, render the discovered files with editable include
  flags, file name, relative path, extension, file type, human-readable size,
  `size_bytes`, status, and notes.
- Supported files (`file_type != "unsupported"`) default included.
  Unsupported files default excluded but remain visible with clear
  unsupported status/notes.
- Controls shipped: search by file name or relative path, filter by
  extension, include all supported files, exclude all files, include visible
  supported files, exclude visible files, include by extension, and exclude
  by extension.
- Selection state is stored in `st.session_state`, keyed by the resolved scan
  tuple. Relative paths are the stable file identity. Filtering and searching
  do not reset selections.
- Re-scan reconciliation preserves selections for paths still present, drops
  missing paths, defaults newly discovered supported files included, and
  defaults newly discovered unsupported files excluded.
- The selection is not yet persisted to profiles and is not yet fed to
  `run_packaging_job`.

### Tests / manual checks
- `python -m py_compile streamlit_app.py`
- `python -m pytest -q llm_project_packer\tests`
- `streamlit run streamlit_app.py --server.headless=true --server.port=8519`
  boots cleanly and `curl.exe -I http://localhost:8519` returns HTTP 200.
- Manual: scan `.\sample_input`; expect 5 discovered files, 5 supported, 0
  unsupported, and 5 included by default.
- Manual: use search/filter plus bulk include/exclude controls; selections
  should persist through reruns and filtering.
- Manual: add unsupported-only files in a temporary folder or add
  `sample_input\scratch.tmp`; unsupported rows should remain visible,
  excluded by default, with clear status/notes.
- Manual: exclude an existing supported file, add a new supported file,
  remove a different file, and click `Re-scan`; expect still-present
  selections preserved, new supported files included, new unsupported files
  excluded, and missing paths dropped.

### Risk areas
- The relationship between manifest `DOC_ID` and "selected by user" must
  remain stable across re-scans. Use the relative path as the stable key,
  not the doc index.
- Ensure unsupported-file rows stay visible in the review UI even when
  excluded by default — never silently drop a file from review.
- Later milestones must decide whether the session-state selection is saved
  to profiles, passed directly as `included_files`, or both.

### Acceptance criteria
- Per-file include/exclude survives Streamlit reruns, filtering/search, and
  re-scans for stable relative paths.
- Unsupported files are visible, excluded by default, and clearly explained.
- No readers, conversion, packaging, export, file writes, or CLI behavior
  changes were introduced.

---

## Milestone 7 — Packaging settings screen

### Files to modify
- `streamlit_ui/state.py` — settings keys.
- `llm_project_packer/packer/presets.py` — only if a new tunable is added
  (e.g. a separate RAG chunk-size budget); do not change defaults.

### Files to create
- `streamlit_ui/settings_screen.py`.

### Behavior
- Show the resolved per-bundle token budget for the current target/mode.
- Allow the user to override `max_bundle_tokens`.
- Show the rough projected bundle count using the cached scan result and
  a quick token estimate per file (use `len(text) // 4` if the readers
  haven't run yet, else use `ConvertedDoc.token_estimate`).
- Optional: display the "this is a packaging target, not a platform limit"
  disclaimer inline.

### Tests / manual checks
- Manual: pick `--target chatgpt --mode lean` (60k budget), override to
  10k, confirm projected bundle count grows; pack, verify output bundles
  are sized accordingly.

### Risk areas
- Projected bundle count is an estimate; do not present it as authoritative.
- Avoid coupling settings UI directly to `presets.py` constants — read
  through `presets.get_bundle_token_budget(target, mode)`.

### Acceptance criteria
- Override persists in the profile and is honored by `pack()`.
- The disclaimer text is present and editable in one place
  (`presets.py` + `exporters.py` `_DISCLAIMER`).

---

## Milestone 8 — Preview screen

### Files to modify
- `llm_project_packer/packer/pipeline.py` — `convert()` already produces
  `ConvertedDoc` objects; no change needed if it works with a temp
  `WorkspacePaths`.

### Files to create
- `streamlit_ui/preview_screen.py`.

### Behavior
- Run `pipeline.convert(cfg, scanned, ...)` against a temp workspace
  (`tempfile.TemporaryDirectory`).
- List converted documents with their `DOC_ID`, source path, token estimate,
  and a "View Markdown" expander that renders `doc.total_markdown`.
- "Re-run preview" button to refresh after settings or selection changes.
- Caching: store the last `ConversionResult` in `st.session_state`; only
  re-run if `cfg` or selection changed.

### Tests / manual checks
- Manual: preview `sample_input/`; the `intro.html` preview shows the
  cleaned Markdown (no `<script>`, no `<nav>`, missing-image marker
  inline).
- Unit: `convert(cfg, scanned, workspace=temp_workspace)` does not write
  to the configured `cfg.output_dir`.

### Risk areas
- Temp workspace cleanup on Windows can fail if files are still mapped.
  Use `TemporaryDirectory(ignore_cleanup_errors=True)` (Python 3.10+).
- Large previews (50MB+ converted Markdown) can choke Streamlit. Truncate
  display at, e.g., 200KB per doc with a "show full" toggle.

### Acceptance criteria
- Preview never writes to the user's chosen output directory.
- Preview output for a doc matches what would land in the final bundle for
  that doc (modulo bundle header).

---

## Milestone 9 — Export / progress / results

### Files to modify
- `streamlit_ui/state.py` — export-job key, progress buffer.

### Files to create
- `streamlit_ui/export_screen.py`.

### Behavior
- "Pack" button calls `pipeline.pack(cfg, on_progress=event_handler)` in a
  background thread; the handler appends `ProgressEvent`s to a queue read
  on each Streamlit rerun.
- Render a live progress bar plus the most recent N events.
- On `ProgressEvent.kind == "done"`:
  - Show the export folder path with a "Open in Explorer" button
    (Windows: `os.startfile`).
  - List bundle / manifest / instruction file paths.
  - Render the contents of the relevant `00_*_INSTRUCTIONS.md` instruction
    block in a copy-friendly code block.
- Errors during pack: surface `ProgressEvent.kind == "error"` items as
  warnings; the run continues per the "one bad file" rule.

### Tests / manual checks
- Manual: pack `sample_input/` for each target; verify the export folder
  matches the V1 structure and instruction text is shown verbatim.
- Manual: introduce a deliberately bad file (e.g. an empty `.docx` named
  `bad.docx`); confirm the pack completes, the file appears in the
  manifest as `failed`, and the UI shows a warning.

### Risk areas
- Streamlit + threads: do not call `st.*` from the worker thread. Use a
  thread-safe queue and pull from it on rerun.
- The "Open in Explorer" affordance only works on Windows; gate it.
- Long packs may exceed Streamlit's default rerun timeout; keep the worker
  off the main loop.

### Acceptance criteria
- A successful pack from the UI produces the same export folder as the
  equivalent CLI command.
- Progress events emitted during the pack match those the CLI prints.

---

## Milestone 10 — README + manual test instructions

### Files to modify
- `README.md` — add a "Streamlit UI (optional)" section with install /
  launch / first-run walkthrough; CLI section unchanged.
- `CLAUDE.md` — promote V2 milestone status to "shipped" when each one
  lands; update the testing-commands block to include the UI smoke flow.
- `.gitignore` — add `profiles/`, `streamlit_ui/__pycache__/`, etc.

### Files to create
- (None new beyond docs.)

### Behavior
- Document:
  - `pip install -r llm_project_packer/requirements-ui.txt`
  - `streamlit run streamlit_app.py`
  - The five-screen flow (setup → scan → review → settings → preview →
    export).
  - That the CLI is still the supported automation path.
  - That nothing is uploaded — the UI just opens the export folder.

### Tests / manual checks
- Run every command in the README on a clean checkout in a fresh venv.
- Confirm the CLI smoke commands from CLAUDE.md still succeed.

### Risk areas
- Documentation drift between README, CLAUDE.md, and the UI copy. Pick one
  source of truth per topic (e.g. token preset table lives in README; UI
  reads `presets.py`; CLAUDE.md links to README).

### Acceptance criteria
- A new user can follow the README to install, run a CLI pack, install
  the UI extras, run a UI pack, and end up with the same export structure
  in both cases.
- CLAUDE.md's "definition of done" checklist applies to V2 changes
  unchanged.

---

## Cross-cutting risks (apply to every milestone)

- **Streamlit's rerun model**: every interaction reruns the script
  top-to-bottom. Cache scan/convert results in `st.session_state` and
  guard against accidental re-conversion.
- **Long-running operations**: a 10-minute pack must not freeze the UI.
  Always run `pack()` in a background thread with progress events.
- **Path handling on Windows**: OneDrive paths, long paths (>260 chars),
  and case-insensitive matching all bite. Use `Path.resolve()` and the
  existing `safe_filename` helper consistently.
- **Backwards compatibility**: every CLI smoke command from CLAUDE.md must
  pass after every milestone, not just at the end.
- **Test discipline**: V1 has no automated tests. Milestone 1 is the right
  moment to add `pytest` + a minimal `tests/` directory; subsequent
  milestones extend it.
- **Optional dependency creep**: keep Streamlit in `requirements-ui.txt`
  so headless / CLI-only users do not pull it in.

## Out of scope for V2

- Automated upload to ChatGPT or Claude (still excluded; see CLAUDE.md).
- OCR, embeddings, vector DB, hosted server.
- Browser automation or login flows.
- Editing original files in place.
- Multi-user / multi-tenant features.
