# FileSlicer — Appeals Packaging Test Plan (Phase A + B)

> **How to use this file:** Paste its contents into a fresh Claude Code session
> as your first message. The assistant will walk you through testing each
> feature below, one section at a time — running each command, showing you the
> output, confirming the expected result, and pausing before moving on. You can
> also just follow it yourself.

---

## Instructions to the assistant

You are helping me manually test FileSlicer's FEMA-appeals packaging features
(Phases A and B). Work through the sections **in order**. For each numbered
feature:

1. State what the feature is in one line.
2. Run the command(s) shown (use the Bash or PowerShell tool).
3. Show me the relevant output.
4. Tell me whether the **Expected** result held (✅/❌). If ❌, stop and help me debug.
5. Pause and wait for me to say "next" before continuing.

Do **not** automate uploads to ChatGPT/Claude or register MCP servers for me —
those steps are mine. Only generate local files and run local commands.

### Environment

- Repo root: `C:\Users\caleb\OneDrive\Desktop\Scripts\Fileslicer`
- Python: `.\.venv\Scripts\python.exe` (or `python` if the venv is active)
- Appeals DB (default): `C:\Users\caleb\Documents\GitHub\pa_rag\data\pa_appeals.sqlite3`
- All exports below go to `.\test_output` (safe to delete afterward).

First, make sure the code is current and the venv has the UI deps:

```powershell
cd C:\Users\caleb\OneDrive\Desktop\Scripts\Fileslicer
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
```

---

## 0. Automated test suite (baseline)

The whole thing should be green before manual testing.

```powershell
.\.venv\Scripts\python.exe -m pytest -q llm_project_packer\tests
```

**Expected:** `199 passed`.

---

# Phase A — appeals source, destinations, guidance, bundling

## 1. Appeals source — read the DB, one Markdown doc per appeal

```powershell
.\.venv\Scripts\python.exe pack_project.py --profile "ChatGPT Project" --appeals-db --output .\test_output
```

**Expected:** "Export complete" with **2157** appeals processed, **0 failed**.
Open the newest `.\test_output\pa_appeals_chatgpt_*` folder → `02_BUNDLE_001.md`.
Each appeal has an identity header (`DOC_ID/SOURCE_FILE/...`), an `## Appeal
Overview` block, and the decision prose.

## 2. URL + PDF per appeal (C-round)

In the bundle from step 1, find the first appeal's overview block.

**Expected:** it includes `- **URL:** https://www.fema.gov/appeal/...` and, for
most appeals, `- **Source PDF:** FEMA-...-DR ... .pdf`. (All 2,157 appeals have
URLs; ~1,952 have a linked PDF.)

## 3. Destination profiles + per-destination guidance

```powershell
.\.venv\Scripts\python.exe pack_project.py --profile "DHS / ChatGPT Enterprise" --appeals-db --output .\test_output
.\.venv\Scripts\python.exe pack_project.py --profile "Claude Project" --appeals-db --output .\test_output
```

**Expected:** the DHS export's `00_CHATGPT_PROJECT_INSTRUCTIONS.md` contains a
**"Packaging guidance for this destination"** section that names *ChatGPT
Enterprise / government workspace ("DHS chat")* and warns about the ~110K
stuffing budget. The Claude export's instructions show the Claude guidance
("bundle, don't micro-chunk").

## 4. Medium-grained bundling + corpus overview (DHS)

Still in the DHS export from step 3:

**Expected:** there is a `00_CORPUS_OVERVIEW.md` (a DOC_ID → bundle index), and
~**66** bundle files (`02_BUNDLE_001.md` …), each capped near the 110,000-token
budget. Confirm with:

```powershell
(Get-ChildItem .\test_output\pa_appeals_chatgpt_full_* | Sort-Object LastWriteTime | Select-Object -Last 1 | Get-ChildItem -Filter "0*_BUNDLE_*.md").Count
```

## 5. CLI `--appeals-db` — path vs. bare default, and error handling

```powershell
.\.venv\Scripts\python.exe pack_project.py --appeals-db .\nope.sqlite3 --target rag --mode balanced --output .\test_output  # expect: error, exit code 2
echo "exit=$LASTEXITCODE"
```

**Expected:** "Appeals database does not exist or is not a file", `exit=2`.
(Step 1 already proved the bare `--appeals-db` uses the default DB.)

## 6. Streamlit appeals workspace — levers + visualizer

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open the printed `localhost` URL. In the **FEMA appeals workspace**:

1. The DB path is pre-filled. Click **Load appeals** → "Loaded 2,157 appeals."
2. Set Target = `chatgpt` (Packaging target section). Tick **Override token
   budget**, set it to `60000`. **Expected:** the visualizer bundle count jumps
   to ~**122**; set `200000` → ~**36**. The bar chart of tokens-per-bundle and
   the "total ÷ budget ≈ N" caption update live.
3. Check the **MB** caption ("Estimated export size: ~28.x MB total").
4. Switch Target = `rag`. **Expected:** chunk settings appear; the visualizer
   shows chunk count + a size-distribution histogram + over-budget count.
5. Expand **Preview a rendered appeal** → pick one → confirm the Markdown looks
   right (URL + PDF present).
6. Click **Package appeals** → an Export result with an **Export size (MB)**
   metric.

Leave Streamlit running for steps 9 and 13; stop it later with Ctrl+C.

---

# Phase B — metadata chunks, embedders, hybrid local RAG

## 7. Metadata-rich `chunks.jsonl`

```powershell
.\.venv\Scripts\python.exe pack_project.py --profile "Self-hosted RAG" --appeals-db --output .\test_output
```

Open the newest `pa_appeals_rag_*` → `rag_ready\chunks.jsonl`, look at line 1.

**Expected:** each JSON line has a `metadata` object with `title`, `appellant`,
`pa_id`, `disaster_number`, `region`, `status`, `url`, `pdf_filename`,
`citations`, plus a `heading_path` breadcrumb. (Confirm the *folder* RAG path
stays clean: `pack_project.py .\sample_input --target rag --mode balanced` →
its chunks have **no** `metadata` key — byte-identical contract.)

## 8. Pluggable embedder — offline default

```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'llm_project_packer'); from packer.embedder import resolve_embedder; e=resolve_embedder(None); v=e.embed(['flood damage','flood damage','unrelated']); print('default:', e.name); print('same vs diff:', round(sum(a*b for a,b in zip(v[0],v[1])),3), round(sum(a*b for a,b in zip(v[0],v[2])),3))"
```

**Expected:** `default: hashing:256`; identical texts cosine ≈ `1.0`, different ≈
`0.0`. (Local bge/e5 is opt-in: `--embedding-model local:bge-small-en-v1.5`
needs `pip install sentence-transformers` and downloads a model once.)

## 9. Hybrid local RAG (cowork MCP server) — build it

```powershell
.\.venv\Scripts\python.exe pack_project.py --profile "Local Hybrid RAG" --appeals-db --output .\test_output
```

**Expected:** a `mcp_server\` folder with `server.py`, `embedder.py`, and
`index.sqlite`. Confirm the index has vectors + metadata:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3,glob; d=sorted(glob.glob(r'.\test_output\pa_appeals_cowork_*'))[-1]; c=sqlite3.connect(d+r'\mcp_server\index.sqlite'); print('vectors:', c.execute('SELECT COUNT(*) FROM vectors').fetchone()[0]); print('embedder:', dict(c.execute('SELECT key,value FROM embedder_meta').fetchall()))"
```

**Expected:** ~9,000+ vectors and an `embedder_meta` row.

## 10. Hybrid retrieval actually works (query the index)

This queries the generated index directly (no MCP client needed). Ask the
assistant to run it, substituting the newest cowork export path:

```powershell
.\.venv\Scripts\python.exe -c "import sys,sqlite3,glob,json; from array import array; import math; sys.path.insert(0,'llm_project_packer'); d=sorted(glob.glob(r'.\test_output\pa_appeals_cowork_*'))[-1]+r'\mcp_server'; sys.path.insert(0,d); from embedder import build_embedder_from_meta; c=sqlite3.connect(d+r'\index.sqlite'); c.row_factory=sqlite3.Row; meta={r['key']:json.loads(r['value']) for r in c.execute('SELECT key,value FROM embedder_meta')}; emb=build_embedder_from_meta(meta); q=emb.embed(['debris removal eligibility'],is_query=True)[0]; rows=c.execute('SELECT v.chunk_id,v.vector,ch.metadata FROM vectors v JOIN chunks ch ON ch.chunk_id=v.chunk_id').fetchall(); scored=sorted(((sum(a*b for a,b in zip(q,array('f',bytes(r['vector'])))),r) for r in rows),key=lambda t:t[0],reverse=True)[:3]; [print(round(s,3), (json.loads(r['metadata']) or {}).get('title')) for s,r in scored]"
```

**Expected:** the top 3 results are appeals whose titles relate to debris
removal / eligibility (the vector search returns sensible hits). For the *real*
MCP experience, register the server with Claude Desktop using
`mcp_server\cowork_config.json` and its `README.md`, then call `hybrid_search`.

## 11. Embedder choice flows through

```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'llm_project_packer'); from packer.profiles import get_built_in_profile; p=get_built_in_profile('Local Hybrid RAG'); print('target:', p.target, '| embedder:', p.embedding_model)"
```

**Expected:** `target: cowork | embedder: hashing`. (Override at runtime with
`--embedding-model openai:text-embedding-3-small` — note that sends chunk text
to OpenAI, so it's opt-in.)

---

# C-round extras

## 12. Functional quality suite

```powershell
.\.venv\Scripts\python.exe -m pytest -q llm_project_packer\tests\test_appeals_quality.py
```

**Expected:** `7 passed` — proves every appeal is packaged exactly once,
bundles respect the budget, smaller budget → more bundles, URL/PDF render, chunk
metadata is complete, and each appeal's text is recoverable from its chunks.

## 13. Context probe — is the context really 110K?

```powershell
.\.venv\Scripts\python.exe pack_project.py --context-probe 8 --output .\test_output
```

**Expected:** a `*_probe_*` folder with `00_PROBE_INSTRUCTIONS.md`,
`01_PROBE_DEPTH_FILE.md`, eight `PROBE_BUNDLE` files, and `PROBE_ANSWER_KEY.md`.
**This is a manual test of your real workspace:** read
`00_PROBE_INSTRUCTIONS.md`, upload the bundles (NOT the answer key) to a fresh
DHS / ChatGPT Enterprise project, ask each answer-key question, and record which
unique canaries are retrieved. The pattern reveals the effective retrieval
breadth and the in-file stuffing cutoff — i.e. whether ~110K really holds for
your deployment. (Also available as a button in the Streamlit appeals
workspace.)

---

## Cleanup

```powershell
Remove-Item -Recurse -Force .\test_output
```

## What "all green" looks like

- Section 0 and 12: pytest green (199 total / 7 quality).
- Sections 1–6: appeals export with URL+PDF, DHS medium bundling + overview +
  guidance, working UI workspace + live visualizer + MB metrics.
- Sections 7–11: metadata chunks, offline embedder, cowork hybrid index with
  vectors, sensible vector-search hits, embedder plumbing.
- Section 13: probe artifacts generated (the upload/ask step is yours).
