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

### Direction update (2026-06, pending deep-research validation)

The product owner has sharpened the vision; these goals override the narrower
framing above where they conflict, and the specifics are pending a deep-research
pass on how each destination platform ingests and retrieves documents:

- **Organize data optimally for whatever product the user is building.** The
  tool's job is to produce the best possible packaging — bundles, chunks,
  heading/structure selections — for the specific destination, not to expose a
  pile of toggles the user must understand. "Best solution no matter what
  product is being built" is the bar.
- **Self-hosted / embedding-model RAG is a PRIMARY use case**, co-equal with
  hosted projects — not the "future local RAG workflows" afterthought it was
  treated as. Chunking quality for a user-owned embedding model (including
  basic/small models) is first-class.
- **Destination platforms to support and advise on** now explicitly include:
  self-hosted RAG with a user-owned embedding model; Claude Projects; OpenAI
  ChatGPT, including enterprise/government ChatGPT workspace deployments (e.g.
  the "DHS chat" workspace, currently on GPT-5.1 and upgrading to ~5.4);
  Microsoft Azure Databricks **Genie** (conversational analytics over lakehouse
  tables — structured data, so packaging means table structure, column
  descriptions, and metadata rather than prose chunking); and the Databricks /
  Azure **Knowledge Assistant** (RAG over unstructured documents). These are
  goals, not shipped targets.
- **A product-aware questionnaire / goal selector** should drive configuration:
  the tool asks a short triage (what product/destination, structured vs. prose
  data, who owns retrieval, etc.) and then either auto-defaults the packaging
  features or directs the user to the right settings — so the user is not left
  guessing which toggles are effective. This is the intended home for the V3
  recommendation engine.
- **Per-feature, cited guidance.** Every chunking/bundling feature (shipped,
  planned, or proposed) should carry guidance on when it helps, is inert, or
  backfires for each destination, grounded in researched evidence rather than
  assertion. A known open question the research must settle: whether external
  chunking is even effective for hosted projects that re-chunk on their side,
  or whether bundling + structure preservation + content selection is the only
  lever that matters there.

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
  `00_GENERIC_*`, `00_RAG_EXPORT_NOTES.md`, `00_COWORK_MCP_INSTRUCTIONS.md`).
- For `--target rag`: `rag_ready/chunks.jsonl` + `rag_ready/source_map.json`.
- For `--target cowork`: everything in the `rag` export plus a self-contained
  `mcp_server/` directory (FastMCP stdio `server.py`, FTS5-indexed
  `index.sqlite`, paste-ready `cowork_config.json`, `requirements.txt`,
  `README.md`) that exposes the bundle to Claude/Cowork as MCP tools
  (`list_documents`, `get_document`, `search`, `get_chunk`,
  `get_asset_path`). The server runs locally over stdio; the user still
  registers it with their MCP-aware client manually — the tool never
  performs the registration itself.
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
  other chunk-setting change. The corpus audit also renders a "Heading
  browser" (`pipeline.corpus_heading_summary` aggregates audit chunks by
  first heading with chunk/token/document counts, sorted by token share):
  ticking `exclude` on a heading appends it as an exact rule, unticking
  removes exact-heading rules, headings covered only by wildcard rules
  warn instead of unticking, and headingless chunks are reported as
  untargetable by rules. Browser edits bump the form generation so the
  rules text input refreshes from the profile.
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
- Minimum chunk size and chunk overlap (both profile-bound active fields,
  default 0 = off, so existing exports are byte-identical):
  `Profile.chunk_min_tokens` merges chunks under the floor into a neighbor
  via `chunking.merge_undersized_chunks` — combined chunks carry boundary
  reason `chunking.REASON_MERGED_SMALL`, merging never exceeds the chunk
  budget (an undersized chunk between full neighbors stays as-is), and it
  applies everywhere documents are chunked: previews, the corpus audit,
  selection re-chunking, heading rules, and the `rag`/`cowork` JSONL, so
  changing it clears chunk selections like any other boundary-affecting
  setting. `Profile.chunk_overlap_tokens` applies only to
  `rag_ready/chunks.jsonl` via `chunking.apply_chunk_overlap`: each chunk
  is prefixed with whole trailing lines of its original predecessor until
  the overlap budget is covered (capped at one full chunk); boundaries,
  chunk counts, indices, and selections are unchanged, so previews show
  chunks without the overlap text and the UI says so. Both are wired
  through `run_packaging_job(chunk_min_tokens=..., chunk_overlap_tokens=
  ...)`, have number inputs in chunk review, and re-run from the CLI via
  `--profile`. The pipeline warns (without failing) when either value is
  not below the effective chunk budget. Documented generated-file change:
  the chunk-splitting paragraph in `00_RAG_EXPORT_NOTES.md` now describes
  the configurable strategy/overlap/minimum instead of telling users to
  pre-process for overlap.
- Sentence splitting for oversize lines (profile-bound active field
  `Profile.chunk_split_sentences`, default off = byte-identical): a single
  line larger than the chunk budget — the source of every over-budget
  chunk warning — is split at sentence boundaries (naive
  `(?<=[.!?])\s+`, so abbreviations like "e.g." may split early), falling
  back to word boundaries; a single word larger than the budget still
  stays whole. Pieces carry boundary reason
  `chunking.REASON_SENTENCE_SPLIT` and are packed against the estimate of
  the joined text so separator overhead cannot push a piece over the
  budget. Like `chunk_min_tokens` it changes boundaries, so it applies
  everywhere documents are chunked and changing it clears chunk
  selections; it is a checkbox in chunk review, flows through
  `run_packaging_job(chunk_split_sentences=...)`, and re-runs from the
  CLI via `--profile`. The over-budget guidance tip now suggests it.
  Documented generated-file change: the `00_RAG_EXPORT_NOTES.md`
  chunk-splitting paragraph lists sentence splitting as configurable
  instead of suggesting pre-processing.
- Fence-aware chunking for codebases (profile-bound active field
  `Profile.chunk_fence_aware`, default off = byte-identical): the token
  chunker normally splits at every blank line, so a fenced ``` code block
  containing a blank line can be cut mid-fence, leaving chunks with
  unbalanced fence markers. With the toggle on,
  `chunking.split_paragraphs_fence_aware` keeps each fence atomic when
  splitting paragraphs, `_split_oversize_paragraph` treats a fence as one
  unbreakable unit, and a fence larger than the chunk budget is emitted
  whole with boundary reason `chunking.REASON_FENCE_KEPT` (it shows up in
  the audit's over-budget warning rather than being broken; sentence
  splitting never applies inside a fence). Intended for codebases and
  technical Markdown — converted PDFs and office documents rarely contain
  fences, so it stays off by default and the UI checkbox ("Keep code
  blocks whole (for codebases)") says so. Like the other
  boundary-affecting settings it applies everywhere documents are chunked,
  changing it clears chunk selections, it flows through
  `run_packaging_job(chunk_fence_aware=...)`, and it re-runs from the CLI
  via `--profile`. One documented opt-in nuance: whitespace-only lines
  count as blank when fence-aware splitting is on, where plain
  `split("\n\n")` does not.
- Heading-path breadcrumbs for retrieval (profile-bound active field
  `Profile.chunk_heading_path_mode`, one of
  `chunking.HEADING_PATH_MODES` = `off`/`metadata`/`prefix`/`both`,
  default `off` = byte-identical): attaches each `rag`/`cowork` chunk's
  chain of enclosing headings (outermost first, full depth) to
  `rag_ready/chunks.jsonl`. `chunking.heading_paths_for_texts` computes
  paths by walking the ordered chunk texts with a per-level heading stack —
  a chunk's path is the state established by *preceding* chunks, so a
  heading that opens a chunk is its own subject (already in the text) and
  becomes the breadcrumb for the chunks that follow; a heading clears
  deeper stack levels, and headings inside fences are ignored. `metadata`
  adds a `heading_path` list field (for citation/filtering — invisible to
  an embedding model), `prefix` folds the breadcrumb into the chunk text
  via `chunking.apply_heading_path_prefix` (so a basic embedding model sees
  the context), and `both` does each. The mode never moves boundaries, so
  unlike the other chunk settings it does **not** clear chunk selections;
  the breadcrumb is computed and shown in the chunk review table's "heading
  path" column regardless of mode, and only the export writes it.
  `Chunk.heading_path` carries the tuple; it flows through
  `run_packaging_job(chunk_heading_path_mode=...)` and re-runs from the CLI
  via `--profile`. Scoped to the chunked targets — bundles already preserve
  each document's own headings, so breadcrumbs are not injected there.
  Documented generated-file change: `00_RAG_EXPORT_NOTES.md` now lists the
  optional `heading_path` key in the chunk schema and the breadcrumb in the
  configurable-settings paragraph.
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
- Appeals SQLite source, destination profiles, guidance, and medium-grained
  bundling (the FEMA-appeals repurposing — see "Product vision"; an additive
  CLI/backend change, folder-source behavior and byte-identical output
  unchanged):
  - `packer/appeals_source.py` reads FEMA second-appeal decisions directly
    from a `pa_rag` SQLite database (`pa_appeals.sqlite3`) instead of scanning
    a folder. `load_appeal_docs(db_path, manifest, ...)` queries the canonical
    `final_appeal_authority` table (joined to `src_html_appeal` and the
    `document_citation`/`citation_reference` tables for per-appeal cited
    authorities) and renders one clean Markdown document per appeal —
    identity header, then an "Appeal Overview" metadata block (appellant, PA
    ID, disaster, dates, region, status, cited authorities), then the decision
    prose (summary → analysis → conclusion → letter → headnotes → authorities
    → footnotes, falling back to `final_body_text`). Appeals are ordered by
    `final_id` so the assigned `DOC_xxxx` ids are stable across runs. Per-appeal
    failures are isolated (rule 4): a bad row becomes a `status="failed"`
    manifest entry and the run continues; a missing `final_appeal_authority`
    table is a fatal `ValueError`. The pipeline branches on
    `PackerConfig.source_kind` (`folder` default / `appeals`); everything from
    bundling onward is the shared path. The DB is opened read-only.
  - **Appeals workspace in `streamlit_app.py`** (`_render_appeals_export` and
    helpers): the UI exposes every CLI lever for the appeals source — token
    budget, bundling mode, destination, embedder, and the full chunk-setting set
    (incl. `chunk_exclude_headings`) — plus a live packing/chunking visualizer.
    It is backed by three preview functions in `pipeline`:
    `load_appeal_documents(db)` renders the appeals once (cached in session
    state), and `summarize_appeal_bundles(...)` / `summarize_appeal_chunks(...)`
    reuse the real bundler/chunker to compute the bundle plan or chunk-size
    distribution without writing files, so the preview matches a run (rule 3 —
    no duplicated packing logic in the UI). The summaries also report
    `total_bytes`/per-bundle `bytes` so the UI shows export size in MB; the
    export result shows the real on-disk folder size.
  - Appeals rendering now also emits each appeal's **source URL**
    (`src_html_appeal.source_url`) and **linked source PDF filename**
    (`link_html_filename` → `src_filename_pdf.name`) in the overview block and
    the chunk `metadata` (`url`, `pdf_filename`). The query guards on column /
    table presence (`_column_exists`) so a DB without those stays supported.
  - Default appeals DB path: `presets.DEFAULT_APPEALS_DB`
    (`C:\Users\caleb\Documents\GitHub\pa_rag\data\pa_appeals.sqlite3`). The CLI
    `--appeals-db` takes an optional value (bare flag = the default), and the UI
    pre-fills the path.
  - `packer/context_probe.py` (`build_context_probe(output_dir, bundle_tokens,
    bundles)`): generates a local needle-in-a-haystack probe — N canary bundles
    + an in-file depth file (canaries at 10–150% of the budget) + an answer key
    + instructions — to *manually* measure a destination's effective retrieval
    window (e.g. confirm the ~110K ChatGPT-Enterprise stuffing budget for a
    specific workspace). FileSlicer cannot query a hosted platform, so it only
    writes the artifacts; the user uploads and asks the answer-key questions.
    CLI: `--context-probe [N]` (short-circuits the run); UI: a button in the
    appeals workspace. The 110,000 default traces to the OpenAI Enterprise
    file-upload doc ("up to 110K tokens from uploaded documents in the context
    window"), per the repo-root research.
  - `packer/guidance.py` (`guidance_for_destination(destination)`) holds a
    per-destination lever cheat-sheet (effective/inert/harmful) distilled from
    the repo-root research docs, for the four destinations
    `self_hosted_rag`/`claude_project`/`chatgpt_project`/`chatgpt_enterprise`.
    The pipeline passes it into `InstructionContext.guidance_lines` and each
    `00_*` instruction writer renders a "Packaging guidance for this
    destination" section. Empty `destination` ⇒ no section ⇒ byte-identical.
  - Medium-grained bundling (`bundling_mode="medium"`, default `"greedy"`):
    `bundler.split_into_bundles_medium` / `split_doc_at_headings` first split
    any over-budget document at major headings, then pack with the same greedy
    packer and byte-identical numbering as `split_into_bundles`. The pipeline's
    `_prepare_medium_docs` keeps the manifest consistent (an over-budget doc's
    entry is replaced in place by one `*_pNN` part entry per heading split) and
    writes a front-of-corpus `00_CORPUS_OVERVIEW.md` index
    (`exporters.write_corpus_overview`). Intended for the ChatGPT Enterprise /
    "DHS chat" destination, where one mega-bundle strands content past the
    ~110K stuffing budget and microchunks fragment it.
- Local embedding RAG (Phase B / V3 of the appeals repurpose; lifts the V2
  embeddings exclusion — see Explicit exclusions):
  - **Metadata-rich chunks.** `ConvertedDoc` carries an optional `metadata`
    dict (`bundler.make_converted_doc(..., metadata=...)`); `appeals_source`
    fills it with the appeal's appellant/recipient/PA-ID/disaster/date/region/
    status/final_id/source_key plus the cited-authority list.
    `exporters.write_rag_export` emits it as a `metadata` object on each
    `rag_ready/chunks.jsonl` record **only when present**, so folder-sourced
    RAG output stays byte-identical.
  - **Pluggable embedder** (`packer/embedder.py`, self-contained, no `packer`
    imports so it can be copied into a server): `resolve_embedder(spec)` builds
    a `HashingEmbedder` (offline, deterministic, dependency-free — the default),
    `OpenAIEmbedder`, `VoyageEmbedder`, or `SentenceTransformerEmbedder` (local
    bge/e5) from a spec like `hashing`, `openai:text-embedding-3-small`,
    `voyage:voyage-3`, or `local:bge-small-en-v1.5`. API and local backends
    lazily import their package, read `OPENAI_API_KEY`/`VOYAGE_API_KEY` where
    needed, and raise `EmbedderError` (caught upstream → FTS5-only) when
    unavailable. `embed(texts, is_query=False)` applies asymmetric query/passage
    handling where the model asks for it (e5/bge prefixes via `_local_prefix`,
    Voyage `input_type`); the generated server passes `is_query=True` for
    queries. `embedder_meta`/`build_embedder_from_meta` round-trip an embedder's
    identity for storage in the index.
  - **Hybrid cowork MCP server.** `run_packaging_job(embedding_model=...)` flows
    to `exporters.write_cowork_bundle`, which (after the FTS5 index)
    `_build_vector_index` embeds every chunk and stores float32 vectors +
    `embedder_meta` in `index.sqlite`, copies `embedder.py` into `mcp_server/`,
    and the generated `server.py` gains `vector_search` (cosine) and
    `hybrid_search` (BM25 + vector fused with Reciprocal Rank Fusion, optional
    cross-encoder `rerank` that degrades to a no-op without
    `sentence-transformers`). The chunks table gains a `metadata` column. When
    no embedder is available the server is FTS5-only and unchanged in spirit.
    `embedding_model` defaults to `""` (no vectors) except for the
    `Local Hybrid RAG` built-in (`hashing`). Embedding is the only step that may
    call an external API, and only when the user opts into an API backend.
- Project profile storage in `packer/profiles.py`:
  - `Profile` dataclass (31 fields total) + `save_profile`,
    `load_profile`, `list_profiles`, `delete_profile`. JSON is stored under
    `~/.llm_project_packer/profiles/` by default; every function accepts a
    `profiles_dir` override so tests and a future UI can redirect the
    location.
  - `Profile.to_packaging_kwargs(source_dir=..., output_dir=...,
    project_name=..., appeals_db=...)` returns kwargs ready for
    `run_packaging_job`. It emits only the active fields and lets callers
    override source/output/project/appeals-db at call time without mutating the
    profile. When the profile (or the `appeals_db` override) selects the
    appeals source, a folder `source_dir` is not required.
  - `profiles.ACTIVE_FIELDS` lists the twenty-three fields that influence
    packaging today (`project_name`, `default_source_folder`,
    `default_output_folder`, `target`, `mode`, `max_bundle_tokens`,
    `include_extensions`, `exclude_dirs`, `exclude_files`,
    `chunk_exclude_headings`, `chunk_token_budget`, `chunk_strategy`,
    `chunk_heading_level`, `chunk_min_tokens`, `chunk_overlap_tokens`,
    `chunk_split_sentences`, `chunk_fence_aware`,
    `chunk_heading_path_mode`, `source_kind`, `appeals_db`, `bundling_mode`,
    `destination`, `embedding_model`).
    `profiles.INERT_FIELDS` lists
    seven fields that are stored and round-tripped but not yet honored by
    the backend (`include_assets`, `copy_data_files`,
    `spreadsheet_preview_rows`, `include_pdf_page_headers`,
    `include_source_metadata`, `bundle_separator_style`, `create_zip`).
  - Ten built-in templates available via `get_built_in_profile(name)` and
    `list_built_in_profiles()`: `ChatGPT Balanced Project`,
    `Claude Full Project`, `Visual Repair Manual`, `RAG Ready Export`,
    `Lean One-Shot Chat`, and the destination-aware
    `Claude Project`, `ChatGPT Project`, `DHS / ChatGPT Enterprise` (medium
    bundling at a 110K budget), `Self-hosted RAG` (heading-aligned 512-token
    chunks with heading-path breadcrumbs), and `Local Hybrid RAG`
    (`target=cowork` with the offline `hashing` embedder for a self-contained
    BM25 + vector MCP server). Each call returns an independent copy.
  - Forward-compat: unknown JSON keys are dropped on load, a
    `_schema_version` is written, and a corrupt file does not break
    `list_profiles`.
- CLI profile support (a documented CLI addition under repository rule 2;
  behavior without `--profile` is unchanged, including error messages and
  exit codes): `pack_project.py --profile <name>` loads a saved profile
  from `~/.llm_project_packer/profiles/` (falling back to built-in template
  names), builds kwargs via `Profile.to_packaging_kwargs(...)`, and runs
  `run_packaging_job(...)` — so a profile saved in the UI, including the
  full chunking configuration (chunk size, strategy, heading level, corpus
  chunk rules) and `exclude_files`, re-runs identically from the CLI. With
  `--profile`, `source_dir`, `--target`, and `--mode` become optional and
  fall back to profile values; explicit flags still override the profile,
  and `--exclude-dirs` adds to the profile's list. `--profiles-dir <path>`
  redirects profile storage (mirroring the `profiles_dir` parameter on the
  profile API). An unknown profile name fails with exit code 2 and lists
  the available saved and built-in names.
- CLI appeals source (`--appeals-db <path>`, a documented additive CLI change
  under repository rule 2; behavior without the flag is unchanged):
  `pack_project.py --appeals-db pa_appeals.sqlite3 --target ... --mode ...`
  packages FEMA appeals from the SQLite database instead of a folder, so
  `source_dir` is no longer required. It composes with `--profile`
  (`--profile "DHS / ChatGPT Enterprise" --appeals-db <path>` runs the medium
  bundling + DHS guidance against the appeals corpus). A missing/non-file DB
  path fails with exit code 2.
- CLI embedding model (`--embedding-model <spec>`, additive; default behavior
  unchanged): for `--target cowork`, embeds chunks for vector/hybrid search.
  `hashing` (offline default of `Local Hybrid RAG`),
  `openai:text-embedding-3-small`, or `voyage:voyage-3`. Threads to
  `run_packaging_job(embedding_model=...)`; API backends send chunk text to the
  provider, so they are opt-in.
- JSON file support in `packer/presets.py` and `packer/readers.py`:
  `.json` classifies as file type `json` and `_read_json` renders objects
  as Markdown with one heading per key (top level `##`, nested objects one
  level deeper, scalar lists as bullets, explicit `(null)` / `(empty list)`
  markers). Invalid JSON records a failed manifest entry without raising.
  This makes structured records (e.g., scraped FEMA appeal JSON) flow
  through scan, chunk review, and export with field-aligned headings.
- Automated tests under `llm_project_packer/tests/`:
  `test_pipeline.py` (38 cases), `test_chunking.py` (60 cases),
  `test_readers.py` (6 cases), `test_profiles.py` (37 cases),
  `test_cli.py` (14 cases), `test_bundler.py` (9 cases),
  `test_appeals_source.py` (10 cases), `test_embedder.py` (9 cases),
  `test_cowork_hybrid.py` (3 cases), `test_appeals_quality.py` (7 cases), and
  `test_context_probe.py` (4 cases) — 199 in total; passes with
  `python -m unittest discover -s tests` or `pytest`.

V2 should focus next on (in roughly this order):

- **profile UI extensions** — done: chunk settings, chunk rules, and the
  file review selection (`exclude_files`) are all bound to the `Profile`,
  so a saved profile captures the user's full configuration.

Backend cleanup that still belongs in V2:

- Bundle filename prefixes — done: `bundler.split_into_bundles` assigns every
  bundle a shared `prefix_width`, and `Bundle.filename` keeps the documented
  two-digit `02_`–`99_` prefixes (byte-identical output) up to 98 bundles.
  Larger exports use width-uniform prefixes numbered from "02" zero-extended
  (`020_BUNDLE_001.md`, …, `118_BUNDLE_099.md`, …) so bundles always sort
  lexically after the `00_*` instructions and `01_SOURCE_MANIFEST.md` and in
  bundle order; plain zero-padding (`002_`) would sort before `00_*`.
- Pipeline printing — done: `packer/` contains no direct `print` calls; the
  pipeline emits `ProgressEvent`s and the CLI renders them via its
  `_print_progress` callback.
- Keep tests and CLI smoke commands passing after every milestone.

V2 should not attempt OCR, embeddings, vector databases, automated upload,
privacy redaction, deduplication, image captioning, or a full recommendation
engine. Those belong in Version 3 or later unless explicitly approved.

## Version 3 scope

Version 3 is where the app becomes a smarter packaging assistant rather than
just a UI for the packer.

Candidate Version 3 features:

- **product-aware questionnaire / goal selector** (the priority V3 entry per
  the 2026-06 direction update): a short triage — what destination/product,
  structured vs. prose data, who owns retrieval, context-window size, citation
  needs — that maps each answer pattern to a concrete packaging configuration
  and either auto-defaults the features or directs the user to the right
  settings. This is the answer to "the user shouldn't have to guess which
  toggles are effective." Its rule set is to be grounded in the pending
  deep-research findings on per-destination ingestion/retrieval behavior;
- goal selector content: repair manual, FEMA/legal/policy, codebase, research,
  data/spreadsheet, reusable project knowledge, one-shot chat;
- target-platform strategy recommendations for self-hosted embedding-model RAG
  (primary), Claude Projects, OpenAI ChatGPT (incl. enterprise/government
  ChatGPT workspaces such as the GPT-5.1→5.4 "DHS chat"), Azure Databricks
  Genie (structured/lakehouse-table analytics), the Databricks/Azure Knowledge
  Assistant (document RAG), one-off chats, Gemini/large-context tools,
  NotebookLM-style source sets, and API agents;
- per-feature, cited configuration guidance: for every shipped/planned chunking
  and bundling feature, a per-destination verdict (effective / inert / risky)
  plus recommended defaults, surfaced to the user at the point of decision;
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
- No cloud hosting, no hosted or remote server, no remote storage. The one
  sanctioned exception is the `cowork` target's generated MCP server: it
  runs locally over stdio, serves only files inside its own export folder,
  and the user registers it with their MCP-aware client by hand — the tool
  never starts it, registers it, or exposes it to the network.
- No claims that token presets equal official platform context-window limits.
- No new heavyweight dependencies without a clear reason; `tiktoken` stays
  optional. The Phase B embedding backends (`openai`, `voyageai`, and
  `sentence-transformers` for local bge/e5) are **lazy and optional**: the
  default embedder is a dependency-free, offline hashing embedder, and a missing
  package or API key degrades the cowork server to FTS5-only retrieval rather
  than failing.
- No OCR, automated redaction, or image captioning yet. These require explicit
  future milestones.
- **Embeddings / vector search are now in scope (Phase B / V3 of the appeals
  repurpose).** The earlier V2 exclusion of "embeddings, vector database,
  similarity search" has been lifted because self-hosted embedding RAG is the
  now-primary use case (see the 2026-06 Direction Update). It is implemented
  locally: a pluggable embedder (`packer/embedder.py`) and a hybrid
  (BM25 + vector, RRF) retrieval layer inside the **local, stdio-only** cowork
  MCP server — the sanctioned local exception. Embedding via an API backend
  sends chunk text to that provider and is therefore strictly opt-in
  (`--embedding-model openai:…`); the default stays offline.

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
  `pipeline`, `profiles`, `appeals_source`, `guidance`, `embedder`,
  `context_probe`.
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
python pack_project.py .\sample_input --target cowork  --mode balanced --output .\test_output

# CLI behaviour
python pack_project.py                                              # prints help + clear error, exit code 2
python pack_project.py .\sample_input --target chatgpt              # argparse error: --mode required
python pack_project.py .\does\not\exist --target chatgpt --mode balanced  # config error, exit code 2

# Profile-driven CLI runs
python pack_project.py .\sample_input --profile "RAG Ready Export" --output .\test_output   # rag/balanced with 800-token chunks from the template
python pack_project.py .\sample_input --profile "RAG Ready Export" --target generic --mode lean --output .\test_output  # flags override the profile
python pack_project.py .\sample_input --profile "No Such Profile"  # error listing saved + built-in names, exit code 2
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
- Set `Min chunk size (tokens, 0 = off)` to `20`, preview a document with a
  tiny heading section (e.g., a converted JSON record) under the heading
  strategy.
  Expected: undersized sections merge into a neighbor with boundary reason
  `undersized chunk merged into its neighbor`; chunk counts drop in the
  corpus audit; changing the value clears selections like a chunk-size
  change; merging never pushes a chunk over the budget.
- Set `Chunk overlap (tokens, 0 = off)` to `40` with `--target rag`
  semantics, then export.
  Expected: the preview warning lists the overlap, each chunk after the
  first in `rag_ready/chunks.jsonl` starts with the tail of its
  predecessor, chunk counts and ids match the preview (previews show
  chunks without the overlap text), and changing the overlap does not
  clear chunk selections.
- Tick `Split oversize lines at sentences`, preview a document containing
  a single line larger than the chunk size (e.g., a one-line paragraph
  from a converted PDF or JSON field).
  Expected: the over-budget chunk disappears, replaced by chunks within
  budget with boundary reason `oversize line split at sentence
  boundaries`; the corpus audit's over-budget warning clears; changing
  the checkbox clears selections like a chunk-size change.
- Tick `Keep code blocks whole (for codebases)`, preview a Markdown file
  containing a fenced code block with a blank line inside it, using a
  chunk size small enough to force a split near the fence.
  Expected: with the toggle off, some chunk contains an odd number of
  ``` markers (the fence is broken); with it on, every chunk's fences are
  balanced, a fence larger than the chunk size appears whole with
  boundary reason `oversize fenced code block kept whole`, and changing
  the toggle clears selections like a chunk-size change.
- Set `Heading breadcrumb (rag/cowork exports)` to each mode and preview a
  document with nested headings (e.g. `# Manual` / `## Transmission` with a
  long section), then export with `--target rag`.
  Expected: the chunk review table always shows a "heading path" column
  with the enclosing headings (a chunk that opens with a heading shows its
  ancestors, not itself); `off` writes no `heading_path` key and is
  byte-identical; `metadata` adds a `heading_path` list to each
  `chunks.jsonl` record without touching the text; `prefix` prepends the
  breadcrumb line to the chunk text; `both` does each; and changing the
  mode does NOT clear chunk selections (it doesn't move boundaries).
- In `Corpus chunking audit` with the heading strategy, open the
  `Heading browser` after analyzing.
  Expected: one row per distinct chunk heading with chunk/token/document
  counts sorted by token share; ticking `exclude` adds that heading to
  `Corpus chunk rules` (the text input refreshes), unticking removes the
  exact rule, a heading covered only by a wildcard rule warns instead of
  unticking, and headingless chunks are reported as untargetable.
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

For `--target cowork`:

```
<output>/
  PROJECT_NAME_cowork_MODE_TIMESTAMP/
    00_COWORK_MCP_INSTRUCTIONS.md
    01_SOURCE_MANIFEST.md
    manifest.csv
    manifest.json
    assets/
    data/
    rag_ready/
      chunks.jsonl
      source_map.json
    mcp_server/
      server.py
      embedder.py        # present so the server can embed queries
      index.sqlite       # FTS5 chunks + (when embedded) vectors + embedder_meta
      cowork_config.json
      requirements.txt
      README.md
```

The cowork target reuses the rag chunking path and adds the `mcp_server/`
directory next to the standard outputs. The per-bundle token budget under
this target is interpreted as a per-chunk budget, scaled smaller than the
rag defaults so each FTS5 hit fits comfortably inside a single MCP tool
response. When `embedding_model` resolves to a usable embedder, `index.sqlite`
also holds a `vectors` table and `embedder_meta`, `embedder.py` is copied in,
and the server exposes `vector_search` and `hybrid_search` alongside the
keyword `search`; otherwise the server is FTS5-only.

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
