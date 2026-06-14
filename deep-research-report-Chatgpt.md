# Document RAG Packaging for Hosted LLM Knowledge Systems

## Findings that settle the decision

The central answer is not the same across destinations. For **self-hosted / custom RAG**, external chunking is a first-class quality lever: current vendor guidance and recent retrieval research both show that chunking strategy materially changes recall, precision, index size, and latency, and that content-aware chunking usually beats naive fixed-size splitting. For **Claude Projects** and **ChatGPT hosted knowledge surfaces**, the platform owns retrieval. There, external chunk tuning is usually weak leverage at best, because the hosted system can switch to its own retrieval path and does not expose chunking controls; in practice, **content selection, structure preservation, and sane file granularity matter more than pre-splitting into many tiny files**. citeturn35view0turn18view2turn18view0turn18view3turn2view5turn13view2

If you want one sentence per destination, it is this. For **self-hosted RAG**, export **retrieval-ready chunks plus metadata**. For **Claude Projects**, export **complete, well-named, text-forward files** and let Claude decide between in-context use and RAG. For **ChatGPT Projects/custom GPTs**, export **a small number of clear, complete files or modest topical bundles**, because file slots are limited and OpenAI does not expose chunk controls. For **ChatGPT Enterprise/Gov**, export **focused medium-grained files**—not one giant omnibus, but also not thousands of microchunks—because OpenAI documents a fixed “stuffing + private search index” pipeline and explicitly says that fewer focused documents generally give higher accuracy. citeturn27view0turn2view4turn2view5turn8view0turn14view0turn14view3turn13view2

Two platform-specific conclusions are especially important for your packaging tool. First, **Claude and ChatGPT hosted products do not give you user-visible control over their internal chunking boundaries**, so your own `chunks.jsonl` is usually not the retrieval unit they operate on; at most, it becomes a set of uploaded files that the platform may parse and rechunk again. Second, **OpenAI Enterprise/Gov is the one hosted destination here with unusually concrete published mechanics**: text is partially stuffed into context, the remainder goes into a private search index, and the system performs hybrid keyword-plus-semantic retrieval from that index. That makes “one huge mega-bundle” and “many tiny chunk files” both bad defaults there. citeturn2view5turn13view2turn13view3

## Self-hosted and custom RAG

### What is documented

In self-hosted RAG, you own the entire ingestion path, so external organization is not an upload convenience issue; it **is the retrieval design**. Pinecone’s data-modeling guidance says that if source content is longer than what you want to retrieve as one hit, you should chunk it in your application before upsert and store each chunk with a chunk ID plus metadata tying it back to the parent document. Qdrant’s chunking guidance likewise frames chunking as the key determinant of what embeddings capture and what retrieval can surface, and it recommends preserving meaningful semantic units and attaching rich metadata such as `document_id`, `document_title`, `section_title`, and chunk indexes. Azure’s RAG guidance makes the same point in a more benchmark-like form: chunks that are too small lose necessary context, while chunks that are too large dilute relevance and waste compute. citeturn27view0turn27view2turn22view3

Recent evidence is stronger than “best-practice folklore.” A March 2026 cross-domain benchmark covering 36 chunking strategies, six domains, and five embedding models found that **content-aware chunking significantly outperformed naive fixed-length baselines**, with paragraph group chunking posting the best overall retrieval quality and simple fixed-size character chunking performing poorly. The same study found that better chunking and better embeddings are **complementary**, not substitutes: larger embedding models help, but they remain sensitive to suboptimal segmentation. citeturn35view0

Structure-aware chunking is also now well-supported by platform docs. Azure AI Search recommends starting a fixed-size baseline at **512 tokens with 25% overlap**, but also says that if you need intact passages, larger chunks and variable chunking that preserves sentence structure often produce better results. Unstructured’s open-source docs go further: they partition documents into semantic elements first, then chunk across elements, only falling back to text splitting when one element itself is too large; their `by_title` strategy explicitly preserves section boundaries and can merge tiny sections back together. Weaviate’s starter guidance offers similar practical baselines, suggesting 100–200 word windows with overlap as a baseline but noting that chunking by paragraphs or sections is often preferable when it preserves related information. citeturn18view0turn31view0turn31view1turn18view3

Hybrid retrieval and reranking are also now mainstream “current best practice,” not advanced extras. Azure describes hybrid search as parallel keyword plus vector retrieval fused with Reciprocal Rank Fusion, and Pinecone/Qdrant both describe reranking as a second-stage relevance improvement that reduces noise before the LLM sees context. In other words, once you own retrieval, the best baseline in 2026 is usually **good chunking + hybrid retrieval + reranking**, not dense vectors alone. citeturn33search2turn33search0turn33search1turn33search3

### Best packaging strategy

The best fit for your tool here is **chunk-first export**, not bundle-first export. Emit `chunks.jsonl` as the primary artifact, plus a manifest, stable document IDs, source path, section lineage, and enough metadata to support grouping, filtering, reranking, and citation. Bundles are still useful as a side artifact for human inspection, manual upload, or fallback long-context prompting, but for production retrieval they should be secondary. That recommendation is directly aligned with Pinecone’s and Qdrant’s guidance that the retrievable unit should be application-controlled and metadata-rich. citeturn27view0turn27view2turn21view0

My recommended default is **structure-aware chunking first**: split on top-level semantic boundaries such as headings, paragraphs, list blocks, table blocks, and code constructs; only use fixed-size or sentence-level splitting as a fallback for oversized elements. A good initial baseline is to target **roughly 400–700 tokens per chunk**, using **~10–25% overlap only when you are forced into fixed-size fallback splitting**. That number is a synthesis: Azure’s starting recommendation is 512 tokens with 25% overlap, while Weaviate’s baseline windows are smaller by word count, and the newest large benchmark strongly favors content-aware paragraph grouping over naive fixed spans. citeturn18view0turn18view3turn35view0

For **small/basic embedding models**, contextual augmentation is worth serious attention. Anthropic’s Contextual Retrieval work reports a **35% reduction in top-20 retrieval failures** from contextual embeddings in the cookbook, and **49% fewer failed retrievals** when paired with contextual BM25 in the engineering write-up; with reranking, the reduction reaches **67%**. A separate 2025 contextual-embedding benchmark shows that standard embedding models struggle when document-wide context is needed. That does **not** prove a specific gain for “heading breadcrumbs” on every small model, but it does strongly support the design principle behind them: adding concise enclosing-heading context to a chunk improves representational quality when local chunk text is ambiguous. My recommendation is therefore to treat heading breadcrumbs as **on by default** for self-hosted chunk export, either embedded directly into chunk text or stored as metadata that is prepended before embedding. citeturn18view1turn18view2turn25view0

Tables and code deserve special handling. Unstructured’s chunker keeps tables isolated as `Table` or `TableChunk` elements, and its table-retrieval guidance recommends preserving full structure while embedding a natural-language summary for better matching. For code, Qdrant’s code-search tutorial recommends chunking by language-level constructs such as functions, methods, structs, and enums, with docstrings and contextual metadata attached. For your tool, that means: **do not shatter tables into arbitrary prose fragments**, and **do not break code fences or language-level units unless you absolutely must**. citeturn31view2turn30view1turn32view0

### Lever verdicts and defaults

| Lever | Verdict | Recommended default |
|---|---|---|
| bundle vs. chunk | **Effective** — chunk is the primary retrieval unit in self-hosted RAG | Prefer `chunks.jsonl`; optionally also write bundles for inspection |
| bundle token budget | **Neutral** — useful for human review or long-context prompting, not primary retrieval | If writing bundles, keep them readable and topic-coherent rather than tightly optimized |
| chunk size | **Effective** — one of the highest-impact retrieval levers | Start around **512 tokens** or equivalent semantic size; adjust per corpus |
| chunk overlap | **Effective in fixed-size fallback; can backfire if overused** | Use **0 overlap** for structure-aware chunks; **10–25%** only for fixed-size fallback |
| pack-by-paragraph vs. split-at-headings | **Effective** | Prefer headings/paragraphs over raw fixed spans |
| heading level | **Effective** | Split at meaningful headings, typically top-level section boundaries first |
| minimum chunk size | **Effective** | Merge tiny fragments into neighboring chunks unless they are true standalone units |
| sentence-level splitting of over-long lines | **Effective as fallback** | Use only when an element exceeds max size |
| keep code fences intact | **Effective** | Preserve fenced/code-construct integrity whenever possible |
| heading breadcrumbs in text | **Effective** | Turn on by default for embeddings, especially with weaker embeddings |
| heading chain as metadata | **Effective** | Always store it, even if also prepended to chunk text |
| content selection / boilerplate removal | **Effective** | Remove headers, footers, nav chrome, duplicated boilerplate before embedding |
| stable per-document IDs + manifest | **Effective** | Always on |

These verdicts are strongly documented for self-hosted pipelines; the exact numeric defaults are a synthesis of current vendor guidance and recent retrieval benchmarking rather than a one-size-fits-all law. citeturn18view0turn18view3turn21view0turn27view2turn35view0

## Claude Projects

### What is documented

Claude Projects are a persistent knowledge surface with an explicit **two-mode behavior**. Anthropic says that a project normally uses **context-based processing**, but when project knowledge approaches or exceeds context limits, Claude **automatically enables RAG mode** and starts using a **project knowledge search tool** that retrieves only relevant information from uploaded documents. Anthropic also says this switch is automatic, requires no setup, and can reverse if project knowledge later drops below the threshold. That is unusually clear documentation compared with other hosted products. citeturn2view5

Anthropic’s current help center also exposes several concrete limits. For project files, the limit is **30 MB per file**, with an **unlimited number of files** in principle, but the total content must fit within Claude’s context window; for paid plans, projects can expand capacity **up to 10×** through automatic RAG. Anthropic separately says current paid Claude chat context windows are **500K tokens** for some models and **200K** otherwise, and that projects use RAG to work with larger amounts of information by loading only relevant content into the window. Project files are **text extraction only**, except for multimodal PDFs; descriptive filenames are explicitly recommended because they help Claude retrieve the right information more effectively. citeturn4view0turn4view1turn3search5

The most important negative fact is what Anthropic does **not** document. It does not publish user-facing chunk sizes, overlap controls, retrieval counts, or any statement that your uploaded file boundaries will be respected as the final retrievable units. Once project RAG activates, Claude uses its own project knowledge search tool. That means the hosted retriever, not your local pre-chunker, is the actor that matters. citeturn2view5turn4view1

### Best packaging strategy

For Claude Projects, the best packaging strategy is **bundle-oriented, not chunk-oriented**. In practice that means **complete, clean, well-structured files with descriptive filenames**, ideally one file per logical source document or a small thematic bundle if the source materials are tiny and fragmented. This aligns with Claude’s two-mode behavior. If your full project still fits below the relevant context threshold, complete files maximize Claude’s ability to use in-context processing. If the project crosses the threshold, Claude flips to its own retrieval layer anyway, and Anthropic’s own advice is to upload comprehensive content and use descriptive filenames, not to micro-manage chunking. citeturn2view5turn2view6turn4view0

For your levers, that means external chunk files are usually **inert-to-harmful**. They add file clutter, they weaken filename semantics, and they fragment context that Claude might otherwise consume together if the project still fits in-context. The only time I would pre-split for Claude is when a single source document is itself unwieldy—too large, too noisy, or too heterogeneous—and can be split into **self-contained section files** at major headings without changing meaning. That is not retrieval tuning; it is content selection and file hygiene. This is a synthesis from Anthropic’s documented mechanics rather than a published Anthropic benchmark. citeturn2view5turn4view0

A practical default for your exporter is therefore: write **Markdown or other text-forward files**, preserve headings and tables inline, keep a stable ID header at the top of each document, include a manifest, and only bundle multiple tiny documents together when they would otherwise produce noisy filename spam. Do **not** make `chunks.jsonl` the primary output for Claude. citeturn4view0turn2view5

### Lever verdicts and defaults

| Lever | Verdict | Recommended default |
|---|---|---|
| bundle vs. chunk | **Effective for bundle; harmful for chunk** | Prefer full files; only split at major section boundaries when necessary |
| bundle token budget | **Moderately effective** | Keep files logically complete; avoid absurdly huge omnibus files |
| chunk size | **Mostly inert** | Do not expose as a primary user setting |
| chunk overlap | **Likely harmful** | Off |
| pack-by-paragraph vs. split-at-headings | **Effective only as file-hygiene split** | If splitting at all, split at major headings, not arbitrary paragraphs |
| heading level | **Moderately effective** | Use top-level or semantically meaningful section breaks |
| minimum chunk size | **Mostly inert** | If splitting, merge tiny fragments back into parent sections |
| sentence-level splitting of over-long lines | **Useful only for parser cleanup** | On internally, but invisible to user |
| keep code fences intact | **Effective** | Preserve intact |
| heading breadcrumbs in text | **Mostly inert** | Usually unnecessary; let Claude use the full file structure |
| heading chain as metadata | **Moderately effective** | Keep in manifest and headers for traceability |
| content selection / boilerplate removal | **Highly effective** | On by default |
| stable per-document IDs + manifest | **Effective** | On by default |

## ChatGPT Projects, custom GPTs, and enterprise or government workspaces

### ChatGPT Projects and custom GPTs

OpenAI’s currently published consumer/business documentation is strongest on **limits and file hygiene**, and much weaker on retrieval internals. Projects can have **5, 25, or 40 files** depending on plan, and GPTs can attach **up to 20 files**. Across ChatGPT uploads, OpenAI documents a **512 MB per-file** hard limit and a **2 million token cap** for text and document files. For Projects, OpenAI also says that ChatGPT can draw from project chats, uploaded files, and custom instructions, and for Plus/Pro users it says project responses **prioritize project chats and files**. For custom GPT knowledge, OpenAI says to use knowledge for reference material, prefer **clear, text-forward files**, and specify citation behavior in instructions if you want quotes or citations. citeturn2view1turn2view0turn8view0turn14view1turn14view3

What OpenAI does **not** currently publish for consumer/business Projects or GPT Knowledge is the sort of explicit retrieval description Anthropic publishes for Projects or OpenAI publishes for Enterprise file uploads. In the current help-center material, there is no public chunk-size control, no public overlap control, and no public statement that your uploaded file boundaries are respected as final retrievable units. Because those mechanics are opaque, the safest recommendation is **not** to bet on external chunk boundaries. citeturn8view0turn2view1

My recommendation for both ChatGPT Projects and custom GPTs is therefore **few, complete, well-structured, text-forward files**, with modest bundling if you need to conserve file slots. For custom GPTs, the 20-file cap makes over-fragmentation especially costly. For Projects, the same principle applies, though the exact cap depends on plan. If a source document is very large, split it into **self-contained section files at major headings**, not retrieval-sized snippets. That is an inference from the documented file-slot limits plus the absence of user chunk controls. citeturn2view1turn8view0

A good default export profile for these surfaces is: convert to Markdown where possible, preserve headings/tables/lists inline, strip boilerplate, prepend a stable document header, and bundle small related documents into a topic file when that reduces slot pressure. `chunks.jsonl` should not be the primary output here; if you write it at all, it is only for your own local FTS/MCP tooling, not as the upload artifact. citeturn8view0turn14view3

### ChatGPT Enterprise and government workspaces

For Enterprise, OpenAI’s documentation is much more explicit. ChatGPT Enterprise says it processes files through **text extraction, code analysis, and image interpretation** depending on file type. For text-based retrieval, OpenAI states that some uploaded text is **“stuffed”** directly into the model context while the rest is sent to a **private search index**, explicitly described as a vector store; when the user asks a question, ChatGPT combines the included text with **relevant chunks retrieved from that index**. For text documents, OpenAI says the product can process **up to 110K tokens from uploaded documents in the context window**; if a single file is longer than that, only the **first 110K tokens** are stuffed, with the remainder only in the search index. If multiple files exceed the stuffing budget, OpenAI allocates the first **55K evenly across files**, then the next **55K proportionally** across remaining content. citeturn13view0turn13view2

OpenAI also documents retrieval/search behavior by model family inside this Enterprise file pipeline. It says GPT-series and o-series models use **identical context stuffing and search embedding logic** and perform **hybrid keyword-plus-semantic search** against the private search index. The difference is that GPT-series models usually do **one** search per prompt, while o-series models can do **multiple searches**, typically two to three, updating the search plan as they go. OpenAI also says that **fewer, focused documents generally lead to higher accuracy**. This is the most decisive hosted-platform evidence in your whole request. citeturn13view2turn13view3

That leads to a very specific packaging answer for Enterprise/Gov. The best upload strategy is **not** one monolithic mega-bundle, because a single file over ~110K tokens gets front-loaded and everything after that becomes retrieval-only. It is also **not** thousands of microchunk files, because that fragments context and shrinks the initial per-file representation when multiple files compete for the stuffing budget. The best strategy is **medium-grained, focused files**: each file should be internally complete and topically coherent, but large sources should be split at meaningful section boundaries so that important material is not stranded deep in an oversized file. Put the most important overview and index-like material near the top of each file. citeturn13view2

For government deployments, the right default is “treat it like Enterprise unless your agency’s deployment guide says otherwise.” OpenAI’s FedRAMP documentation says ChatGPT FedRAMP is a **configuration of ChatGPT Enterprise** with added compliance, while ChatGPT Gov is a containerized frontend that agencies deploy in Azure and that includes many of the same features as ChatGPT Enterprise, including file uploads and custom GPTs. OpenAI’s public materials do **not** separately document a different file-ingestion algorithm for FedRAMP or Gov. So, absent agency-specific documentation, the Enterprise file-upload mechanics are the highest-confidence public proxy. citeturn16view0turn16view1turn16view2

### How GPT model upgrades affect packaging

The key point is that **model upgrades are less important here than the file-ingestion layer**. OpenAI’s Enterprise upload article says the stuffing and search-embedding logic are identical across major model families in that product surface. Meanwhile, newer GPT-5.x ChatGPT release notes emphasize better context-window management and longer reasoning, and OpenAI expanded manual Thinking context in ChatGPT in early 2026. Those changes can improve retrieval-driven answer quality, multi-step search behavior, and the model’s ability to integrate retrieved evidence, but they do **not** change the basic packaging advice established by the Enterprise file-ingestion docs. citeturn13view2turn12view0turn12view1

So for a DHS-style workspace moving from something described internally as GPT-5.1 to GPT-5.4, my best evidence-based answer is: **do not redesign packaging around the model upgrade**. Expect some improvement in long-horizon reasoning and context handling, but keep the same file strategy: focused, complete documents; no microchunk uploads; split very large sources at major headings; put key overview material early; preserve stable IDs and structure. Public OpenAI docs no longer expose a canonical GPT-5.1 file-upload spec, so any more specific claim than that would be guesswork. citeturn13view2turn12view0turn12view1

### Lever verdicts and defaults

#### ChatGPT Projects and custom GPTs

| Lever | Verdict | Recommended default |
|---|---|---|
| bundle vs. chunk | **Bundle effective; chunk likely harmful** | Prefer complete files or modest topic bundles |
| bundle token budget | **Moderately effective** | Bundle tiny related docs; avoid giant omnibus files |
| chunk size | **Mostly inert** | Hide this setting by default |
| chunk overlap | **Likely harmful** | Off |
| pack-by-paragraph vs. split-at-headings | **Effective only as file split hygiene** | If splitting large sources, split at major headings |
| heading level | **Moderately effective** | Top-level section breaks only |
| minimum chunk size | **Mostly inert** | Merge tiny sections back together |
| sentence-level splitting of over-long lines | **Useful only for cleanup** | On internally |
| keep code fences intact | **Effective** | Preserve intact |
| heading breadcrumbs in text | **Usually inert** | Off unless the user explicitly wants inline citation context |
| heading chain as metadata | **Moderately effective** | Keep in headers/manifest |
| content selection / boilerplate removal | **Highly effective** | On by default |
| stable per-document IDs + manifest | **Effective** | On by default |

#### ChatGPT Enterprise and government workspaces

| Lever | Verdict | Recommended default |
|---|---|---|
| bundle vs. chunk | **Neither extreme; medium-grained bundle wins** | One file per logical source or major section, not microchunks |
| bundle token budget | **Highly effective** | Keep files focused and preferably below the point where important content is buried deep beyond stuffing |
| chunk size | **Mostly inert as an upload lever** | Do not upload retrieval-sized snippets |
| chunk overlap | **Harmful** | Off |
| pack-by-paragraph vs. split-at-headings | **Effective as file split strategy** | Split very large docs at major headings/chapters |
| heading level | **Effective** | Use semantically meaningful top-level splits |
| minimum chunk size | **Moderately effective** | Merge tiny sections into larger coherent files |
| sentence-level splitting of over-long lines | **Useful only for cleanup** | On internally |
| keep code fences intact | **Effective** | Preserve intact |
| heading breadcrumbs in text | **Usually inert-to-harmful** | Avoid duplicative breadcrumb prefixes in the body |
| heading chain as metadata | **Effective** | Keep in header/manifest for traceability |
| content selection / boilerplate removal | **Highly effective** | On by default |
| stable per-document IDs + manifest | **Effective** | On by default |

## Matrix and triage questionnaire

### Lever matrix

The matrix below is a compact synthesis of the destination-specific sections above. **E** means effective, **N** means neutral or mostly inert, and **H** means harmful or usually counterproductive.

| Destination | Bundle vs chunk | Bundle budget | Chunk size | Overlap | Split strategy | Min size merge | Sentence fallback | Keep code intact | Breadcrumb text | Breadcrumb metadata | Boilerplate removal | Stable IDs + manifest |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Self-hosted / custom RAG | **E** — chunk is the retrieval unit | **N** — secondary | **E** — major retrieval lever | **E** — only for fixed fallback | **E** — headings/paragraphs beat naive spans | **E** | **E** | **E** | **E** | **E** | **E** | **E** |
| Claude Projects | **E/H** — full files good, microchunks bad | **E** — sane file granularity helps | **N** | **H** | **E** only for large-source file splits | **N** | **N** | **E** | **N** | **E** | **E** | **E** |
| ChatGPT Projects / custom GPTs | **E/H** — full files or modest bundles good, chunk files waste slots | **E** | **N** | **H** | **E** only for major heading splits | **N** | **N** | **E** | **N** | **E** | **E** | **E** |
| ChatGPT Enterprise / Gov | **E/H** — medium-grained files win; mega-file and microchunks both bad | **E** — highly important | **N** as upload lever | **H** | **E** — split huge docs at major headings | **E** | **N** | **E** | **N/H** if repetitive | **E** | **E** | **E** |

This table is a synthesis of: current self-hosted retrieval guidance and benchmarks; Anthropic’s published Project Knowledge/RAG behavior; OpenAI’s Projects/GPTs limits and file hygiene guidance; and OpenAI Enterprise’s documented stuffing-plus-search-index mechanics. citeturn35view0turn18view2turn2view5turn4view0turn8view0turn14view3turn13view2

### The triage questionnaire

Your questionnaire should be brief and mostly destination-driven, because that is where the largest configuration differences come from.

#### Question set

**Question:** What are you packaging for?  
**Answer options:**  
Self-hosted / custom RAG I control • Claude Projects • ChatGPT Projects • Custom GPT • ChatGPT Enterprise or government workspace • Structured / tabular destination  
**Why this matters:** This question alone determines whether chunking is a primary lever or mostly a distraction. Route “Structured / tabular destination” to the Part B branch stub. citeturn27view0turn2view5turn13view2

**Question:** Do you control the embedding model, vector store, or retrieval settings?  
**Answer options:**  
Yes, fully • Partially • No  
**Why this matters:** “Yes” means expose chunk controls. “No” means hide or strongly de-emphasize them. citeturn27view0turn13view2

**Question:** What best describes the source material?  
**Answer options:**  
Mostly prose/reference docs • Prose plus code snippets • Codebase / technical source files • Table-heavy / visually structured docs • Mostly structured/tabular data  
**Why this matters:** This selects table preservation, code-preserving chunking, or a Part B route. citeturn30view1turn32view0

**Question:** Are exact source traceability and citations required?  
**Answer options:**  
Strictly required • Helpful • Not important  
**Why this matters:** Strict traceability turns on stable IDs, richer manifest entries, page/section metadata, and more conservative bundling. citeturn21view0turn21view3

**Question:** Are the source documents usually very large?  
**Answer options:**  
Mostly short • Mixed • Often huge  
**Why this matters:** For hosted platforms, “often huge” means split at major headings into focused files. For self-hosted, it may justify more advanced chunking or late/contextual strategies. citeturn13view2turn26search1turn18view2

**Question:** Do you expect the user to rely on the packaged output through a local search/agent layer before upload?  
**Answer options:**  
Yes • No  
**Why this matters:** “Yes” justifies writing both bundles and `chunks.jsonl`, plus a manifest optimized for local FTS/MCP use. “No” means output only the destination-optimized artifact by default. This is mostly a product-design choice, but it follows from the different roles of chunks in self-hosted versus hosted destinations. citeturn27view0turn2view5turn13view2

### Decision table

| Answer pattern | Configuration |
|---|---|
| **Self-hosted / custom RAG** + **I control retrieval** | **Auto-default** to chunk mode. Emit `chunks.jsonl` as primary. Structure-aware chunking. Start near **512 tokens** equivalent. Overlap only for fixed-size fallback. Turn on heading-chain metadata and inline breadcrumbs. Keep code/table units intact. Always emit manifest and stable IDs. citeturn18view0turn31view0turn18view2turn30view1 |
| **Claude Projects** | **Auto-default** to bundle/file mode. Write one file per logical source or small thematic bundles. Preserve headings/tables inline. Strip boilerplate. Keep stable IDs and manifest. Hide chunk-size/overlap controls unless “advanced” is expanded. citeturn2view5turn4view0 |
| **ChatGPT Projects** | **Auto-default** to file mode with modest bundling. Preserve structure. Conserve file slots. Split only huge documents at major headings. Hide chunk-size/overlap controls. Keep manifest/IDs. citeturn2view1turn14view3turn2view0 |
| **Custom GPT** | Same as ChatGPT Projects, but bundle more aggressively because of the **20-file** cap. Preserve structure, strip boilerplate, stable IDs on. citeturn8view0 |
| **ChatGPT Enterprise or government workspace** + **documents often huge** | **Auto-default** to medium-grained focused files. Split huge source docs by major heading or chapter. Do not upload retrieval-sized snippets. Put key overview material early in each file. Keep manifest/IDs. citeturn13view2turn16view0turn16view1 |
| **ChatGPT Enterprise or government workspace** + **documents mostly short/mixed** | Prefer one file per logical source; avoid mega-bundles and avoid chunk files. Preserve structure and citations metadata. citeturn13view2 |
| **Source material = codebase / technical source files** + **self-hosted** | Chunk by functions, methods, classes, modules; attach file, module, and symbol metadata; preserve code intact. citeturn32view0 |
| **Source material = table-heavy / visually structured docs** + **self-hosted** | Preserve tables as tables/HTML/Markdown, isolate them, and consider embedding a table summary while keeping the full table attached. citeturn30view1turn31view2 |
| **Source material = mostly structured/tabular data** | Route to **Part B branch stub**. Keep the prose-side defaults hidden or disabled. |
| **Strict citations required** | Force stable IDs, manifest, source path, section/page metadata, and conservative no-duplication defaults. citeturn21view0turn21view3 |

The hidden rule behind the decision table is simple: **only expose chunk knobs when the user owns the retriever**. Everywhere else, default them away. That is the cleanest possible questionnaire logic for the product you described. citeturn27view0turn2view5turn13view2

## What is changing and how to future-proof

The direction of travel is clear. On the hosted side, both Anthropic and OpenAI are moving toward **native retrieval, larger context windows, more connectors, more citations, and more agentic query planning**, which all reduce the value of hand-tuned external chunking for uploads. Anthropic now treats project RAG as an automatic mode switch. OpenAI is simultaneously adding synced connectors, company knowledge with citations, and richer workspace/app retrieval, while newer GPT-5.x notes emphasize better context handling rather than exposing more user chunk controls. That means external chunk tuning for hosted products is likely to age badly; **bundling, structure preservation, content selection, and traceable IDs** are the safer investments. Confidence: **high**. citeturn2view5turn7search7turn6search2turn12view0turn12view1

The self-hosted trajectory is different. The last two years of retrieval work have increased, not decreased, the importance of good segmentation. Contextual retrieval, late chunking, hybrid retrieval, and reranking all improve quality, but they do so by making retrieval design more sophisticated, not by making it irrelevant. The March 2026 benchmark is especially telling here: even larger embedding models remain sensitive to chunking strategy, which means chunking optimization is not being washed away by better models. Confidence: **high**. citeturn18view2turn25view0turn26search1turn35view0

The most future-proof architecture for your tool is therefore a **dual export model** internally and a **destination-specific default** externally. Internally, keep the ability to produce both high-quality chunks and high-quality bundles with a manifest. Externally, surface only the artifacts that matter for the chosen destination. That gives you a stable foundation even if hosted products continue to evolve toward opaque native retrieval while self-hosted stacks continue to reward better chunk engineering. citeturn27view0turn2view5turn13view2

### If you tell users only three things per destination

**Self-hosted / custom RAG**  
Use structure-aware chunks, not naive fixed-size slices. Keep source/section metadata and stable IDs on every chunk. Add contextual heading information before embedding, especially if you use smaller embeddings. citeturn35view0turn18view2turn27view0

**Claude Projects**  
Upload complete, clean, well-named files. Do not waste effort on microchunk uploads; Claude will use in-context processing when it can and its own project search when it must. Preserve headings and remove boilerplate. citeturn2view5turn4view0

**ChatGPT Projects and custom GPTs**  
Optimize for limited file slots and opaque retrieval: use a few text-forward, well-structured files or modest bundles. Split only huge sources at major headings. Put citation instructions in the GPT instructions, not in the knowledge files themselves. citeturn2view1turn8view0

**ChatGPT Enterprise or government workspace**  
Do not upload one mega-file, and do not upload thousands of chunks. Use medium-grained, focused files so important content does not get stranded beyond the stuffing budget. Fewer focused documents generally help. citeturn13view2

### Open questions and limitations

The biggest unresolved area is **OpenAI consumer/business Projects and custom GPT retrieval internals**. Current public docs clearly describe limits and file hygiene, but they no longer publicly document the precise chunking semantics that older OpenAI materials discussed. So the recommendation there is partly **inference from what OpenAI documents for Enterprise**, plus the practical reality that the platform does not expose user chunk controls. citeturn8view0turn2view1turn13view2

A second unresolved area is **exact model-specific behavior inside government deployments**. Public documentation says FedRAMP ChatGPT is a configuration of ChatGPT Enterprise and that ChatGPT Gov includes many of the same capabilities, but OpenAI does not publish a separate file-ingestion algorithm for every government environment. So the Enterprise upload article is the highest-confidence public proxy, but agency-specific deployment notes could override it. citeturn16view0turn16view1turn16view2

A third limitation is that **headline breadcrumb gains are better-supported directionally than numerically for small embedding models specifically**. The evidence for contextual augmentation is strong overall, but the exact magnitude on your chosen small local embedding model is still something you should benchmark on representative queries. citeturn18view2turn25view0