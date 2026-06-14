# Part B — Packaging Structured/Tabular Data for Databricks Genie and the Databricks/Azure Knowledge Assistant

## Products researched & confidence in identification
- **Microsoft Azure Databricks AI/BI Genie** ("Genie Spaces"). GA on all clouds since the Data + AI Summit (June 11, 2025); per Databricks, "over 4000 customers adopted AI/BI Genie during its preview." Confidence: **very high** — confirmed against official Databricks and Microsoft Learn docs.
- **Agent Bricks: Knowledge Assistant** — the genuine "Databricks/Azure Knowledge Assistant." Confidence: **very high.** It is a no-code RAG agent inside Agent Bricks, announced in Beta at Data + AI Summit (June 11, 2025), went **GA January 27, 2026** (Databricks blog), and is GA on Azure ("Azure Databricks Agent Bricks Knowledge Assistant"). Naming-overlap warnings: (a) it is NOT Azure AI Search, Azure AI Foundry "on your data," or Copilot Studio knowledge sources — those are separate Microsoft products I researched only for disambiguation; (b) Databricks renames frequently — "Genie" now spans Genie Spaces, Genie Code, and Genie One, and the Knowledge Assistant sits under the "Agent Bricks" umbrella alongside Information Extraction, Custom LLM, and Supervisor agents.

## TL;DR
- **For Genie, packaging is NOT prose chunking — confirmed.** Genie answers from governed Unity Catalog **tables + their metadata** (table/column comments, PK/FK relationships, sampled values, synonyms), plus space-level **example SQL, SQL expressions, instructions, and trusted assets/metric views**. It never consumes uploaded prose chunks or bundles. Keep data **as data** (loaded into UC tables); emit column descriptions, units, keys, and example-query scaffolding as sidecar artifacts.
- **For the Knowledge Assistant, external pre-chunking is mostly inert on the default path but valuable on one specific path.** On "Files in a Volume" / "Files in a Table," it runs a fully managed parse→chunk→embed pipeline (`ai_parse_document`, 50 MB / 500-page skip limits) with **no user chunk controls** — so bundling and content cleanup help, but custom chunk files do not. On the **"AI Search Index"** path you build your own Vector Search index and "can prepare chunks however you want" — this is where the tool's chunk export adds real value.
- **The tool should grow a "structured/tabular" branch:** table-aware export (copy original data file + Markdown preview + row/column counts), a **column-description / data-dictionary file**, schema/keys/units emission, and **example-query + metric scaffolding** for Genie; and for the Knowledge Assistant, a **bundle-first** default plus an **optional chunks.jsonl tuned for the AI-Search-index path** (text + doc_uri + stable source IDs).

## Key Findings

### Destination 1 — Genie: what it uses and what improves accuracy
Genie is a **compound AI text-to-SQL system over governed lakehouse tables**, not a document reader. Per Microsoft Learn ("What is a Genie Space") and the Databricks "Curate/Tune" docs, Genie generates answers from:
- **Unity Catalog table metadata** — table names, descriptions, and defined **primary-key/foreign-key relationships**.
- **Column names + descriptions** (Genie filters for the relevant ones).
- **Sampled/representative values** via **prompt matching** — "format assistance" (sampling representative values) and "entity matching" (curated distinct values, up to 120 columns, up to 1,024 distinct values each, ≤127 chars).
- **Knowledge store** — space-scoped table/column descriptions, **synonyms**, **join relationships**, and **SQL expressions** (measures/filters/dimensions). Limit: 200 knowledge-store snippets per space.
- **Example SQL queries** — Genie matches user prompts to verified SQL and learns query patterns.
- **SQL functions / trusted assets** — registered UC functions and parameterized example queries that return *verified* answers. Note: "Genie does not consider the SQL **content** of your trusted assets when responding" — it invokes them by their comments/signatures.
- **General instructions** (plain text) — for company jargon, fiscal calendars, etc. Limits: 100 instructions per space; ≤30 tables/views per space.
- **Metric views (Unity Catalog Business Semantics)** — certified measures/dimensions defined once in YAML; synonyms and display names ("agent metadata") import into Genie. Business Semantics GA'd in early 2026.

What concretely **improves** accuracy (in Databricks' own priority order): well-documented, **simplified/pre-joined datasets**; **SQL expressions and example SQL over text instructions**; clear column descriptions + synonyms; prompt matching; metric views for governed metrics; benchmarks (up to 500 questions; target >80% before UAT) to measure. What is **ignored / unhelpful:** uploaded prose documents (Genie "works with structured data only … cannot answer questions about PDFs, Word documents"); the literal SQL body of trusted assets (used via comments); too many/conflicting text instructions (Databricks warns these reduce effectiveness, especially in long conversations).

**Does Genie ingest CSV/XLSX directly?** Normally **no** — data must be registered to Unity Catalog (managed/external/foreign tables, views, materialized/metric views). One exception: a **"Upload a file" feature, in gated Public Preview** (per Azure Databricks AI/BI release notes 2025: "To enable file uploads, contact your Databricks account team"), lets a user drag CSV/Excel (and PDF in Agent mode) into a *conversation* to blend with UC data. Limits: up to 25 files per conversation, each <200 MB and <100 columns; CSV/Excel uploads not available in Agent mode; uploads land in a hidden user/space-specific managed volume. This is for ad-hoc blending, not a substitute for modeling.

### How to prepare raw CSV/XLSX BEFORE loading into the lakehouse
1. **Load it as a table, don't flatten to Markdown.** Read CSV → write a Delta/UC table (`spark.read.csv(...).write.saveAsTable(...)`). Genie performs over typed columns, not prose.
2. **Type columns correctly** (numeric/date/decimal) — Genie reasons about types and formats; strings-for-numbers degrade SQL.
3. **Name columns clearly**; add a **column comment per column** (`COMMENT ON`, or AI-generated comments in Catalog Explorer, then human-reviewed). Put **units and enumerations in the comment** ("for columns with a set enumeration of values, increase accuracy by defining them clearly in the comment").
4. **Declare PK/FK relationships** in Unity Catalog (or as space-level join relationships in the knowledge store).
5. **Pre-join / de-normalize** into ≤30 focused tables/views; aim for ≤5 tables per space; hide unneeded columns.
6. **Add synonyms** for business terms; enable **prompt matching / entity matching** on categorical columns.
7. **Define certified metrics as metric views** (YAML measures/dimensions + agent metadata) so Genie resolves metrics deterministically instead of inferring them.
8. **Author example SQL + trusted assets** for recurring questions; add **benchmark questions with gold SQL**.

### Destination 2 — Knowledge Assistant: ingestion & retrieval
The Knowledge Assistant is a **fully managed RAG agent** built on Databricks' **Instructed Retriever** (query decomposition, context-informed re-ranking, metadata reasoning). Per Databricks' GA blog, it "is powered by Databricks AI research and achieves up to 70% higher answer quality than simplistic RAG approaches, without the operational overhead" — the 70% figure comes from the Instructed Retriever blog's high-difficulty benchmark suite (which also reports "35-50% gains in retrieval recall" on the StaRK-Instruct benchmark and an additional ~15% gain over sophisticated DIY rerank pipelines; research led by ex-Google research director Michael Bendersky). Every response carries **page-level citations**.

**Chunk/embed/retrieve behavior depends on the knowledge-source type** (three options, up to 10 sources per agent):
- **Files in a Volume** (UC volume) — the default. Managed parse→chunk→embed using `ai_parse_document`. **No user chunk-size/overlap/heading controls.** "Upload your documents and Knowledge Assistant handles the rest." Requires manual **Sync** (incremental).
- **Files in a Table** — UC table (streaming or CDF-enabled) with a content column + metadata STRUCT; **only the selected content column is ingested**, other columns ignored. Still managed chunking. Requires Sync.
- **AI Search Index** — you supply your own Vector Search index (text column + doc-URI column for citations). **You control chunking entirely** — Databricks' own engineering blog states: "Because Databricks Knowledge Assistant lets you use your own vector index, **you can prepare chunks however you want and just point Knowledge Assistant at the result.**" Index must use a supported embedding model (`databricks-gte-large-en`, `databricks-bge-large-en`, or `databricks-qwen3-embedding-0-6b`); updates automatically, no manual sync.

**Documented limits & status:** Supported file types (volume path): **txt, pdf, md, ppt/pptx, doc/docx** (no HTML, no CSV/XLSX, no JSON). Files >50 MB skipped. PDF/DOC/DOCX/PPT/PPTX >500 pages skipped (each slide = a page; TXT/MD have no page limit, but `ai_parse_document` has a 500-page limit per document). Files whose names start with `_` or `.` are skipped. Up to 10 knowledge sources. Status: **GA (January 27, 2026)**; GA on Azure.

**What file structure improves results.** Because the volume path re-parses and re-chunks everything, the levers that survive are (a) **clean, well-structured source files** (headings, real tables, no boilerplate), (b) **good per-source descriptions** ("Describe the content" routes the Instructed Retriever), and (c) **splitting distinct topics into distinct sources** (up to 10) so source-level descriptions discriminate. Databricks' code-RAG engineering study (an evaluation dataset of 46 questions; 1,000-character target chunks with 200-char overlap) found that "all three strategies achieve 85%+ retrieval sufficiency, meaning Knowledge Assistant's retrieval techniques find relevant context regardless of how the code was chunked," yet "AST-based chunking produces a fully correct answer 70% of the time, compared to 59% for Naive and 61% for Language-Aware." Conclusion: **chunk quality affects answer completeness more than retrieval**, and these techniques "work best when the underlying chunks preserve meaningful semantic boundaries."

**Chunk vs. bundle verdict (parallels Part A).** On the volume/table paths, **bundling + content selection is the right lever; external pre-chunking is inert** (the managed pipeline overrides your boundaries). On the AI-Search-index path, **external chunking is the lever** and your chunks.jsonl maps directly to retrieval units. Default recommendation: ship **bundles** for the volume path; offer an **opt-in chunks→index export** for teams using the AI-Search path.

## Lever-by-lever matrix

| Lever | Genie | Knowledge Assistant |
|---|---|---|
| Keep data **as data** (UC tables) vs. flatten to Markdown | **Effective** — Genie only queries tables; Markdown is unusable to it | n/a (KA is for unstructured docs; CSV/XLSX unsupported) |
| Table preservation / typed columns | **Effective** — correct types drive correct SQL | n/a |
| Column descriptions / comments | **Effective** — core accuracy lever | **Neutral-to-effective** — only if surfaced as text/metadata in source/index |
| Units in comments/metadata | **Effective** — disambiguates measures | **Neutral** — only as inline text |
| Schema / PK-FK / join relationships | **Effective** — drives correct joins | n/a |
| Certified metrics / metric views | **Effective** — deterministic, governed metrics | n/a |
| Example queries / trusted assets | **Effective** — highest-leverage after good metadata | n/a |
| General instructions (plain text) | **Effective in moderation; harmful in excess** | **Effective** — agent "Instructions" + per-source "Describe the content" steer retrieval |
| Bundle (concatenate docs) | n/a | **Effective** on volume path — clean structured docs parse well |
| External pre-chunking (chunks.jsonl) | n/a | **Inert** on volume/table path; **Effective** on AI-Search-index path |
| Chunk size / overlap | n/a | **Inert** (volume/table); **Effective** (you build the index) |
| Split-at-headings | n/a | **Weakly effective** — improves semantic boundaries the parser sees; decisive only on index path |
| Heading breadcrumbs (prefix/metadata) | n/a | **Effective on index path** (carry into text/metadata); neutral on volume path |
| Content selection / boilerplate removal | n/a | **Effective** — less noise → better chunks/citations |
| Source IDs / manifest for citation | **Neutral** (Genie cites SQL/tables) | **Effective on index path** — doc-URI column powers page-level citations |
| File size / count management | **Neutral** | **Effective** — respect 50 MB/500-page skips; ≤10 sources; split topics across sources |

## Structured-data questionnaire branch (fills the Part A stub)

Trigger this branch when destination = **Databricks Genie** or **Knowledge Assistant**, or when content is **structured/tabular (CSV/XLSX)**.

| Question | Answers → maps to |
|---|---|
| Is your content tabular (CSV/XLSX) or documents (PDF/DOCX/etc.)? | Tabular → **Genie branch**; Documents → **Knowledge Assistant branch** |
| Destination platform? | Databricks Genie / Databricks Knowledge Assistant / (else fall back to Part A hosted-RAG branch) |
| **[Genie]** Will you load data into Unity Catalog tables? | Yes → emit **table + data-dictionary + DDL/COMMENT scaffold**; No (just exploring) → emit clean CSV ≤200 MB, <100 cols for Genie file-upload Preview |
| **[Genie]** Do you have a data dictionary / column descriptions? | Yes → ingest into per-column `COMMENT` scaffold; No → generate a **dictionary stub** for human completion |
| **[Genie]** Units / enumerations per column? | Provide → fold into column comments; Unknown → flag in stub |
| **[Genie]** Primary/foreign keys known? | Yes → emit `ALTER TABLE … PK/FK` + join-relationship notes; No → leave TODO |
| **[Genie]** Certified metrics to define? | Yes → emit **metric-view YAML scaffold**; No → skip |
| **[Genie]** Recurring/expected questions? | Yes → emit **example-SQL + benchmark (gold-SQL) scaffold**; No → skip |
| **[KA]** Which knowledge-source path? | Volume/Table → **bundle mode** (clean structured Markdown, respect 50 MB/500-page limits); AI Search Index → **chunks.jsonl mode** (text + doc_uri + source IDs) |
| **[KA]** Do you need fine control over chunking? | Yes → AI-Search-index path + chunk export; No → volume path + bundles |
| **[KA]** Distinct topics? | Many → split into ≤10 sources w/ descriptions; Few → single source |

## Prioritized "features to build"
1. **Table-aware tabular export (Genie + general):** copy the original CSV/XLSX alongside a Markdown preview, emit **row/column counts**, per-column **inferred type**, sample values, and a null/cardinality summary.
2. **Data-dictionary / column-description file:** machine-readable (JSON/YAML) + human-editable Markdown, with fields for description, **unit**, enumeration/allowed values, synonyms — designed to drop into UC `COMMENT`/knowledge-store.
3. **UC DDL + COMMENT scaffold generator:** `CREATE TABLE`, `COMMENT ON`, PK/FK `ALTER TABLE`, from the dictionary.
4. **Metric-view YAML scaffold:** measures/dimensions + display names/synonyms ("agent metadata") for certified metrics.
5. **Example-SQL + benchmark scaffold:** template pairing NL questions with gold SQL, exportable as Genie benchmarks/example queries.
6. **KA bundle exporter (default):** clean, heading-structured Markdown bundles within 50 MB/500-page limits, boilerplate stripped, filenames avoiding leading `_`/`.`.
7. **KA chunks→index export (opt-in):** chunks.jsonl with `text`, `doc_uri`/source ID, heading breadcrumbs in metadata, sized for the user's embedding model — for the AI-Search-index path.
8. **Per-source description generator:** short "what's in here" blurbs to feed KA's "Describe the content" routing.

## What's changing / how to future-proof (6–24 months, with confidence)
- **The platform is absorbing the unstructured-RAG plumbing (high confidence).** Knowledge Assistant's whole pitch is eliminating manual "parsing, chunking, and embedding." Investing in external *document chunking* for the default KA path ages **poorly** — it's already inert there. Bundling/cleanup ages **well** (clean inputs always help). Chunk export remains valuable only for teams who deliberately choose the AI-Search-index path.
- **The semantic layer is consolidating in Unity Catalog (high confidence).** Metric views / Business Semantics GA'd in early 2026; Genie resolves governed metrics from them. Investing in **structured metadata, dictionaries, units, keys, certified metrics, and example queries ages very well** — these are exactly what the platform rewards and increasingly what agents (and managed MCP servers) consume.
- **Genie is expanding (medium confidence on specifics):** Genie Deep Research / Agent mode (multi-step "why" questions), Conversation APIs (Slack/Teams), Knowledge Store "knowledge mining" that auto-proposes instructions from usage, and a move to **pay-as-you-go pricing** ("Usage beyond the free amount is billed in DBUs… Before July 6, 2026, review the budget controls available through Unity AI Gateway"). Direction: less manual curation, but **good metadata still gates quality** ("garbage in, garbage out").
- **Net guidance:** Bet on **structured-metadata emission** (dictionaries, schema, units, metrics, example queries) for Genie, and **bundling + clean inputs** for KA, with **chunk export as an opt-in** that tracks the AI-Search-index path. Avoid over-engineering chunk-size/overlap heuristics for KA's managed path.

## If I tell users only three things per destination
**Genie:** (1) Keep data **as data in UC tables** — never flatten to Markdown. (2) Your accuracy comes from **column comments + synonyms + units, PK/FK, and metric views** — emit a data dictionary. (3) Add **example SQL / trusted assets and benchmark questions** for recurring questions.

**Knowledge Assistant:** (1) On the default volume path it **re-chunks everything for you** — give it **clean, well-structured docs** (and respect 50 MB/500-page limits), not custom chunks. (2) **Split distinct topics into separate sources (≤10)** and write a good "Describe the content" blurb for each. (3) If you need real chunk control, build your **own AI Search index** and export **chunks with text + doc-URI + source IDs** — that's the only path where pre-chunking counts.

## Caveats
- Knowledge Assistant's exact internal chunk size/overlap for the volume path is **not published**; "managed/automatic" rests on the absence of any documented control plus Databricks' "handles the rest" framing.
- The "70% higher quality," "35–50% retrieval recall," and "85%+ retrieval sufficiency / 59→70% correctness" figures are **Databricks' own** (Instructed Retriever blog; code-RAG engineering blog with a small 46-question eval set) — vendor benchmarks, not independent.
- Genie file-upload and PDF-in-conversation are **gated Public Preview / Beta** and require admin enablement (and, for CSV/Excel, contacting your Databricks account team); treat as in flux.
- Product names/limits change frequently (Genie One/Code/Spaces; Agent Bricks rebrands). Limits cited reflect docs current as of June 2026.