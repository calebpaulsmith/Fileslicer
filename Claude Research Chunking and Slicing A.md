# Packaging Prose & Documents for RAG and Hosted-LLM "Projects" — Part A (Document Destinations)

*Research date: June 13, 2026. Scope: prose/document destinations only. Structured/tabular routing is reserved as a stub for Part B (Databricks Genie / Azure Knowledge Assistant). Throughout, documented platform behavior is separated from inference and community findings, and unknowns are flagged.*

## TL;DR
- **External chunking only pays off where YOU own the embedder + vector store (Destination 1, self-hosted RAG). For the two hosted "Projects" destinations (Claude, ChatGPT) it is inert-to-harmful: both platforms re-chunk what you give them on their own side and discard your chunk boundaries, so the only levers that move the needle there are bundling (fewer, complete, well-structured Markdown files), content selection/boilerplate removal, clean headings, and stable document IDs.**
- **The single best default for all three destinations is the same input artifact: clean, heading-structured Markdown in a small number of complete files with a manifest of stable IDs.** Self-hosted RAG additionally consumes a `chunks.jsonl` (heading-aligned, ≤ embedder max input length) and benefits from heading-breadcrumb prefixing; the hosted destinations should receive bundles, never your pre-split micro-chunks.
- **Future-proofing favors bundling + structure + selection over chunk-tuning for the hosted destinations.** Context windows and agentic file-search are growing fast (Claude 200K→500K standard, 1M via API/Code; ChatGPT GPT-5.x at 128K–196K in-app, 272K–1M API), so investment in tuning chunk size/overlap for Claude/ChatGPT will age badly, while investment in clean bundles and selection compounds. For self-hosted RAG the chunk-tuning lever stays real but is bounded by your embedder's max input length.

---

## 1. The Decision Matrix: Destinations × Levers

Verdicts: **E** = effective (worth doing), **N** = inert/neutral (no measurable effect — don't bother), **H** = harmful (backfires).

| Lever | Self-hosted RAG (you own embedder+store) | Claude Projects | ChatGPT Projects / custom GPTs |
|---|---|---|---|
| **Bundle vs. chunk** | **E** — you need chunks for the vector store, but bundle first then chunk from clean Markdown | **E (bundle)** — Claude loads full text into context until its RAG threshold; complete files win | **E (bundle)** — platform re-chunks+embeds; fewer complete files reduce fragmentation & file-count limits |
| **Bundle token budget** | **E** — size bundles to your embedder pipeline, then chunk | **E** — keep total knowledge under the in-context threshold (~200K/500K) to stay out of RAG mode | **E** — 2,000,000-token/512MB hard cap per file; budget bundles to the ~110K–128K effective in-app retrieval pass |
| **Chunk size (tokens)** | **E** — bounded by embedder: ~256–512 for BGE/E5 (512 max), up to 1–2K for Nomic/Arctic (8192 max) | **H/N** — your chunk size is discarded; tiny files force premature RAG mode | **N** — discarded; OpenAI re-chunks at 800-token/400-overlap default |
| **Chunk overlap** | **N→E** — recent evidence: often no measurable benefit; reserve for boundary-sensitive docs | **N** — discarded | **N** — discarded (OpenAI's 400-token overlap applied on their side) |
| **Pack-by-paragraph vs. split-at-headings** | **E** — heading-aligned splitting is the best default | **N** (boundaries discarded) but headings still help LLM reading | **N** (boundaries discarded) but headings improve their semantic chunking |
| **Heading level to split on** | **E** — split at H2; group H3 if under token limit | **N** | **N** |
| **Min chunk size (merge fragments)** | **E** — merge tiny fragments; avoids degenerate vectors | **N** | **N** |
| **Sentence-level splitting of over-long lines** | **E** — sentence boundaries are the cost-effective default | **N** | **N** |
| **Keep code blocks/fences intact** | **E** — never split fenced code or tables | **E** — helps model reading | **E** — helps model reading & their chunker |
| **Heading breadcrumbs (prefix chunk with heading chain)** | **E (primary lever to test)** — strongest cheap structural lever for small embedders; quantify per corpus | **N→E** — as in-file text it helps the LLM locate content; as your metadata, discarded | **N→E** — same; helps their chunker keep section context |
| **Content selection / boilerplate removal** | **E** — removes noise, raises precision | **E** — saves context budget, raises answer quality | **E** — fewer irrelevant chunks retrieved |
| **Stable per-doc IDs + manifest** | **E** — essential for citation + metadata filtering | **E** — lets user reference files by name; aids citation | **E** — filename-based citation; aids retrieval targeting |

**The crux, stated plainly:** External chunk-size/overlap tuning is a *real* lever **only for Destination 1**, because only there does your chunk become the literal unit that is embedded and retrieved. For Claude and ChatGPT Projects, the platform **re-ingests and re-chunks your files on its own side** (Claude: loads full text into context, then switches to its own RAG / `project_knowledge_search` over its own index; ChatGPT: parses, chunks at ~800 tokens / 400 overlap, embeds, and hybrid-searches). Your chunk boundaries are therefore discarded — so for the hosted destinations, **bundling + content selection + clean headings + stable IDs are the only levers that survive.**

---

## 2. The Configuration Questionnaire (Decision Table)

A 3–6 question triage the local packaging tool should ask. "Auto-default" = the tool sets the levers without asking further; "Steer" = the answer narrows options but the tool still asks follow-ups.

| # | Question | Answer options | Maps to configuration | Auto vs. steer |
|---|---|---|---|---|
| **Q1** | **What is the destination?** | (a) Self-hosted/custom RAG I run; (b) Claude Project; (c) ChatGPT Project / custom GPT; (d) *Structured/tabular analytics* | (a)→full chunk+bundle+FTS5 pipeline; (b)/(c)→**bundle-only** pipeline (no external micro-chunks); (d)→**[STUB — ROUTE TO PART B: Databricks Genie / Azure Knowledge Assistant]** | **Auto** (sets the whole pipeline shape) |
| **Q2** | **Do you own the embedding + retrieval step?** (only if Q1=a or ambiguous) | Yes / No | Yes→emit `chunks.jsonl` + heading breadcrumbs + FTS5 server; No→treat as hosted (bundle-only) | **Auto** |
| **Q3** | **Is your content prose or structured/tabular?** | Prose / Mixed / Tabular | Prose→Markdown bundles; Tabular→**[STUB — PART B]**; Mixed→prose pipeline + flag tables for Part B | **Auto** (routes branch) |
| **Q4** | **What's the effective context window / knowledge budget at the destination?** | Small (<32K) / Medium (128–200K) / Large (≥500K–1M) | Small→smaller bundles, aggressive selection; Large→fewer, bigger bundles, lean toward whole-document | **Steer** (sets bundle token budget) |
| **Q5** | **Do you need per-claim citations / source traceability?** | Yes / No | Yes→emit manifest with stable doc IDs, keep heading breadcrumbs, smaller bundles for locatability; No→relax | **Steer** |
| **Q6** | **(Self-hosted only) Which embedder tier?** | BGE/E5-class (512-token) / Nomic/Arctic-class (8192-token) | 512-class→chunk target 256–512 tok; 8192-class→chunk target up to 1–2K tok, enables late-chunking option | **Auto** (sets chunk size ceiling) |

**Structured-data branch:** Any Q1=(d) or Q3=Tabular answer is routed to a **reserved stub** to be filled by Part B (Databricks Genie + Databricks/Azure Knowledge Assistant). Part A does not specify tabular packaging.

---

## 3. Per-Destination Cheat-Sheet ("if I tell users only three things")

**Self-hosted RAG (PRIMARY):**
1. Chunk **heading-aligned at H2, 256–512 tokens for BGE/E5 (512-token cap), up to ~1–2K for Nomic/Arctic (8192 cap)**; never split code/tables; merge tiny fragments.
2. **Prefix each chunk with its heading breadcrumb** (e.g., `Doc > Revenue > Q3 > Regional`) before embedding — it's the cheapest structural lever and most helps in long documents; A/B test it on your corpus.
3. Default **overlap to 0–15%** (recent evidence says overlap often adds nothing) and add **hybrid keyword search (your FTS5 server) + reranking** before spending effort on fancy chunking.

**Claude Projects:**
1. **Bundle into a few complete, well-structured Markdown files** — Claude loads full text into context while it can; Anthropic advises that for knowledge bases under ~200,000 tokens (≈500 pages) you should "include the entire knowledge base directly in the model's prompt, skipping the need for retrieval systems entirely." Keep total knowledge under the in-context threshold (~200K standard / 500K on some Enterprise/newer models) to avoid forcing RAG mode.
2. **Do NOT pre-split into many small files** — community testing shows Claude flips to `project_knowledge_search` at ~13 files regardless of size, and RAG mode retrieves fragments (worse answers).
3. **Select hard** (strip boilerplate) and **name files clearly** so you can reference them by name.

**ChatGPT Projects / custom GPTs:**
1. **Bundle into ≤20 complete Markdown files** (custom GPT hard cap is "up to 20 files… up to 512 MB" each; Projects allow ~20–40 plan-dependent), each well under the **2,000,000-token / 512MB** per-file cap; the platform chunks+embeds them itself.
2. **Don't bother tuning chunk size** — OpenAI re-chunks at 800 tokens / 400 overlap on its side; your splitting is discarded. Spend effort on **clean headings and removing noise** instead.
3. **Keep an index/README file and stable filenames** for citation and to help the retriever target the right source.

---

## 4. Destination 1 — Self-Hosted / Custom RAG (PRIMARY)

### 4.1 Ingestion & retrieval mechanics
You own every step: parse → chunk → embed (local model) → store in a vector DB (Chroma, pgvector, Qdrant, LanceDB — interchangeable) → retrieve top-K by similarity (optionally hybrid with BM25/FTS5) → optionally rerank → stuff into the generator's context. **This is the one destination where your chunk is the literal retrieval unit**, so all chunking levers are live. Guidance is kept framework-agnostic (not tied to LangChain vs. LlamaIndex or a specific store).

**Embedder tier (anchoring constraint).** Confirmed specs for the small-to-base local tier (served via Ollama / sentence-transformers on consumer 8GB-VRAM GPUs):
- **bge-small-en-v1.5**: 384-dim, **512-token** max.
- **bge-base-en-v1.5**: 768-dim, **512-token** max.
- **e5-small-v2**: 384-dim, **512-token** max (model card: "Long texts will be truncated to at most 512 tokens").
- **e5-base-v2**: 768-dim, **512-token** max.
- **nomic-embed-text-v1.5**: 768-dim (Matryoshka 768→256), **8192-token** max.
- **snowflake-arctic-embed-s**: 384-dim, **512-token**; **-m**: 768-dim, **512-token**; **-m-long**: 768-dim, 2048 (8192 w/ RPE); **-m-v2.0**: 768-dim, 8192-token.

**Hard constraint:** chunk size must fit under the embedder's max input or text is silently truncated. So chunk-size guidance is framed against that ceiling, not in the abstract.

### 4.2 Chunk vs. bundle recommendation
**Bundle first (to clean Markdown), then chunk from the bundle.** Concatenating sources into clean, heading-structured Markdown gives the chunker reliable boundaries and lets you attach a heading breadcrumb to each chunk. Emit both: (a) the `chunks.jsonl` for the vector store, and (b) a local FTS5 keyword index for hybrid search.

### 4.3 Lever-by-lever verdict & recommended defaults
| Lever | Verdict | Recommended default | Why |
|---|---|---|---|
| Chunk size | **E** | **256–512 tok (BGE/E5); 512–1024 tok (Nomic/Arctic)** | Multi-dataset evidence (arXiv:2505.21700): small chunks (64–128 tok) best for short fact lookup; 512–1024 for descriptive/technical. 512 is the common universal starting point. |
| Overlap | **N (default), E (boundary-sensitive only)** | **0–15%** | Independent Jan-2026 study (arXiv:2601.14123, Bennani & Moslonka): overlap gave "no measurable benefit and increases indexing cost." Reserve for legal/reference docs where facts straddle boundaries. |
| Split strategy | **E** | **Heading-aligned, split at H2; sentence boundaries for over-long blocks** | Same study: sentence chunking matched semantic chunking cheaply up to ~5K tokens; headings map to topic boundaries. |
| Min chunk size | **E** | **Merge fragments < ~50–100 tok** | Tiny chunks make degenerate, low-signal vectors. |
| Keep code/tables intact | **E** | **Never split fenced code; repeat table header if a table spans chunks** | Split tables/functions are unusable for the model. |
| Heading breadcrumbs | **E (test first)** | **Prefix chunk with heading chain + store as metadata** | See 4.4. Cheapest structural lever; biggest help in long docs. |
| Content selection | **E** | **Strip nav/boilerplate/TOC/footers before embedding** | Noise dilutes vectors and wastes retrieval slots. |
| Stable IDs + manifest | **E** | **Per-doc stable ID + section path in metadata** | Enables citation and metadata filtering. |
| Hybrid + rerank | **E** | **Add BM25/FTS5 + a cross-encoder reranker** | Anthropic: embeddings+BM25 beat embeddings alone; reranking drove the biggest single gain. |

### 4.4 Does "contextual retrieval" / heading-prefixing help SMALL local embedders? (and by how much)
This was the thinnest-sourced sub-question, so it was researched directly. **Honest finding: direct evidence on Anthropic's exact "prepend-context-then-embed" recipe applied to bge-small/base or e5 specifically is genuinely thin — those models were not in Anthropic's study, which used Gemini Text-004 and Voyage.** What we can say with citations:

- **Anthropic's headline numbers** ("Introducing Contextual Retrieval," anthropic.com, Sep 19, 2024, by Daniel Ford): Contextual Embeddings alone cut top-20 retrieval-failure **35% (5.7%→3.7%)**; + Contextual BM25 → **49% (→2.9%)**; and "Reranked Contextual Embedding and Contextual BM25 reduced the top-20-chunk retrieval failure rate by **67% (5.7% → 1.9%)**." The added context is "usually 50–100 tokens" prepended per chunk. **But all embedders tested were API models (Gemini/Voyage best); no small local model was tested.** Per-domain variance is large (some appendix datasets show little benefit on ArXiv at top-20; others much larger).
- **Late Chunking (Jina, arXiv:2409.04701, v1 Sep 2024 / v3 Jul 7 2025) — a *related but different* technique** (embed whole doc, then pool per chunk; requires a long-context model, so tested on jina-v2-small, jina-v3, **nomic-embed-text-v1**): verbatim, "Averaging results across three models and four datasets, we find a **3.63% relative improvement (1.9% absolute)** from naive chunking with sentence boundaries to late chunking using sentence boundaries." The smallest model (jina-v2-small) showed the *largest* single gain (NFCorpus +6.5 nDCG) but nomic was often flat. Benefit correlates with **document length** (≈zero gain on very short docs like Quora).
- **Contextual Document Embeddings / cde-small-v1 (Morris & Rush, Cornell, arXiv:2410.02525, Oct 2024 / ICLR 2025) — a *trained* contextual architecture, 768-dim, 281M params:** SOTA on MTEB for sub-250M-param models at release; a "random documents" (fake context) baseline drops ~1.2 nDCG, quantifying that *genuine* context is what helps.
- **2025–26 reproductions on open models:** "Reconstructing Context" (arXiv:2504.19754) found Anthropic-style contextual rank-fusion on Jina-V3 beat late chunking on NFCorpus (nDCG@10 ~0.31 vs naive ~0.20). "Beyond Chunk-Then-Embed" (2026) tested jina-v2-small, jina-v3, nomic, e5-large and warns contextualization can **degrade in-document retrieval** and that large % gains often reflect "recovery from a very low pre-embedding baseline rather than achieving top-tier effectiveness."

**Verdict for the tool:** Heading-breadcrumb prefixing is a *recommended, low-cost* default for the self-hosted destination (it is essentially a cheap, deterministic form of contextual embedding), **but it must be presented as "test on your corpus," not as a guaranteed 35–67% win** — those numbers are Anthropic's, on large API embedders, and do not transfer cleanly to the 384–768-dim local tier. Expected lift on small local models, where it helps, is in the **low single-digit nDCG points and is largest on long documents**.

---

## 5. Destination 2 — Claude Projects (Anthropic)

### 5.1 Ingestion & retrieval mechanics (documented vs. inferred)
**Documented (Anthropic Help Center, "Retrieval augmented generation (RAG) for projects" & "What are projects?"):** Projects have a knowledge base. When project knowledge fits, Claude uses **in-context processing** (the whole text is placed in the context window) — "When possible, projects will use in-context processing for optimal performance." When knowledge **approaches/exceeds the context-window limit**, Claude **automatically switches to RAG mode**, shown by a visual indicator, expanding capacity "by up to 10x." In RAG mode Claude uses a **`project_knowledge_search` tool** to pull only relevant content. No user configuration; activation is automatic. Context window (per "How large is the context window on paid Claude plans?"): **200K tokens standard on paid plans; 500K on some Enterprise/newer models; 1M for some models via Claude Code/API.** Anthropic's own guidance: under ~200,000 tokens (≈500 pages) you can skip retrieval and include the whole knowledge base directly.

**Community-tested (flagged as community, not official):** A GitHub issue (anthropics/claude-code #25759) reports the in-context→RAG switch triggering at **~13 files regardless of total token size** (≈2% of displayed capacity), with the warning "To save space in chats, Claude will look up specific information as needed," and reports **RAG mode producing worse results than direct loading** (partial retrieval, more hallucination, weaker instruction adherence). Treat the exact threshold as community observation that may change.

**Re-chunking:** In RAG mode Claude indexes and retrieves over its own representation — **your file/chunk boundaries are not the retrieval unit.** In in-context mode the full text is loaded, so structure (headings) helps the model read but your chunking is irrelevant. Either way, **external micro-chunking does not help and can hurt** (more files → premature RAG mode).

### 5.2 Chunk vs. bundle recommendation
**Strongly bundle.** Fewer, complete, well-structured Markdown files keep Claude in superior in-context mode longer and avoid the file-count trigger for RAG mode. Pasting text directly into knowledge is also supported (a small advantage over ChatGPT, which requires file uploads).

### 5.3 Lever-by-lever
Bundling **E**; bundle budget **E** (stay under ~200K/500K to avoid RAG mode); external chunk size/overlap/split **N→H** (discarded; many small files force RAG mode); headings/code-fences intact **E** (reading aid); heading breadcrumbs as text **E** (locatability), as metadata **N** (discarded); content selection **E**; stable IDs/filenames + manifest **E** (reference-by-name, citation — though Claude Projects RAG currently provides no per-claim source citations, a documented community-observed limitation).

---

## 6. Destination 3 — ChatGPT Projects & Custom GPTs (OpenAI)

### 6.1 Ingestion & retrieval mechanics (documented vs. proxy)
**Documented limits (OpenAI Help Center):** Custom GPT knowledge = **"up to 20 files to a GPT. Each file can be up to 512 MB"** (Creating and editing GPTs). The File Uploads FAQ adds: "All files uploaded to a GPT or to a ChatGPT conversation have a hard limit of 512MB per file. All text and document files… are capped at 2M tokens per file. This limitation does not apply to spreadsheets." Only text is indexed (images ignored unless Enterprise Visual Retrieval). Projects: file caps vary by plan (commonly **20 files/project**, Pro/Team/Enterprise/Edu up to 40; **10 files per upload batch**; ~80 files/3h rolling for Plus). Org storage 100GB / user 25GB.

**Retrieval behavior (documented for Enterprise + proxied from Assistants/Retrieval API):** ChatGPT does **not** load whole files; per the Enterprise file-upload doc it **builds a private hybrid (keyword + semantic) search index, "stuffs" as much text as fits, and retrieves relevant chunks** for the rest, bounded by a **~110K–128K token** model window. GPT-series models do **one search per prompt**; o-series can do **2–3 sequential searches**. The Assistants/Retrieval API (best-documented proxy) confirms OpenAI **"automatically parses and chunks your documents, creates and stores the embeddings, and uses both vector and keyword search,"** with defaults: "max_chunk_size_tokens is set to 800 and chunk_overlap_tokens is set to 400, meaning every file is indexed by being split up into 800-token chunks, with 400-token overlap" (configurable 100–4096 via API, **NOT in consumer ChatGPT**). It "outputs up to 20 chunks for gpt-4* and o-series models and up to 5 chunks for gpt-3.5-turbo," using text-embedding-3-large at 256 dims by default.

**Re-chunking:** Yes — **OpenAI re-chunks and re-embeds everything on its side; your boundaries are discarded.** External chunk tuning is therefore inert for this destination.

**Model version note:** As of mid-2026, ChatGPT in-app windows are **128K (GPT-5.5 Instant) / 196K (GPT-5.5 Thinking)** per OpenAI's Enterprise models page; API GPT-5.x ranges 272K–400K and GPT-5.5 added a 1M-token API window (Apr 23 2026). These differences would only shift packaging if a destination's effective window is unusually small; otherwise assume parity with a standard Project. The enterprise/government "DHS chat"-style workspace running ~GPT-5.1 is treated as a standard ChatGPT Project for packaging purposes (no government-specific deployment detail researched, per scope).

### 6.2 Chunk vs. bundle recommendation
**Bundle.** Consolidate into a small number of complete Markdown files well under 2M tokens each. This (a) respects the 20-file and 10-per-batch limits, (b) reduces fragmented/duplicated retrieval, and (c) gives the platform's own chunker clean structure to work with. Add a README/index file.

### 6.3 Lever-by-lever
Bundling **E**; bundle budget **E** (≤2M tok/file; aim bundles at the ~110K–128K effective retrieval pass); external chunk size/overlap/split **N** (discarded, re-chunked at 800/400); headings/code-fences intact **E**; heading breadcrumbs as text **N→E** (helps their semantic chunker keep section context); content selection **E**; stable IDs/filenames + README + manifest **E** (citation + retrieval targeting; prompts can reference section titles/filenames).

---

## 7. What's Changing / How to Future-Proof (6–24 months)

| Trend | Evidence | Implication for packaging |
|---|---|---|
| **Context windows growing fast** | Claude 200K→500K (Enterprise/newer)→1M (API/Code); ChatGPT GPT-5.5 1M API window (Apr 23 2026), in-app 128K (Instant)/196K (Thinking) | Bundling + selection get *more* valuable; external micro-chunking for hosted destinations ages worse. |
| **Automatic in-context↔RAG switching** | Claude Projects auto-RAG; ChatGPT hybrid stuff+search | The platform owns chunking; your boundaries matter less over time. Lean into clean structure, not chunk counts. |
| **Agentic / multi-search retrieval** | o-series 2–3 searches/prompt; Claude `project_knowledge_search`; Research tools | Clear headings + stable IDs help the agent target sources; chunk-size tuning irrelevant. |
| **Connectors / MCP** | MCP open-sourced Nov 2024; Anthropic Integrations (May 2025); OpenAI MCP in Agents SDK; connectors across Claude/ChatGPT | Live-source connectors may displace manual uploads for some users — but a local "write clean Markdown bundles" tool stays useful as the canonical-source producer. |
| **GPT-5.x cadence + built-in citations** | GPT-5.1/5.2 (Jan 2026), GPT-5.5 (Apr 2026); ChatGPT search emits citation markers | Per-claim citations increasingly native on the hosted side; your job is clean, ID-stable sources to cite. |

**Prediction (moderate-high confidence):** For Claude and ChatGPT Projects, **investing in external chunk-size/overlap tuning will age badly**; investing in **bundling, clean Markdown structure, content selection, and stable IDs** will compound. For self-hosted RAG, **chunk tuning remains a real lever** but is increasingly supplemented (not replaced) by hybrid search, reranking, and — for long-context local embedders — late/contextual chunking. Confidence is lower on the exact Claude file-count RAG threshold (community-sourced, may change) and on small-embedder contextual-prefix lift (thinly studied).

---

## 8. Caveats & Unknowns (epistemic flags)
- **Claude's ~13-file RAG trigger is community-observed** (GitHub issue anthropics/claude-code #25759), not official; Anthropic documents only "approaches/exceeds context limit." The threshold may change without notice.
- **ChatGPT consumer retrieval internals are inferred** from the Assistants/Retrieval API and the Enterprise file-upload doc; OpenAI does not fully document consumer-ChatGPT chunking. The 800/400 default is API-documented and not user-configurable in consumer ChatGPT.
- **Contextual-retrieval lift on small local embedders is thinly evidenced.** Anthropic's 35–67% figures are on large API embedders (Gemini/Voyage); transfer to bge-small/e5 is unproven. Late-chunking gains (+1.9 absolute nDCG avg, per arXiv:2409.04701) require long-context models (Nomic/Arctic/Jina), not 512-token BGE/E5.
- **Overlap guidance is in flux:** a Jan-2026 study (arXiv:2601.14123) found no benefit; older vendor guidance recommends 10–20%. Default to low/zero overlap, but treat as corpus-dependent.
- **Plan-dependent file limits change frequently;** verify current ChatGPT Project/GPT caps and Claude context windows at use time.
- **Part B (structured/tabular: Databricks Genie, Azure Knowledge Assistant) is out of scope here** and is the destination for any tabular routing from the questionnaire (Q1=d / Q3=Tabular).