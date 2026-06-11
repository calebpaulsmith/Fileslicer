# llm_project_packer

A local Python command-line tool and Streamlit UI that turns a folder of mixed
source files into upload-ready project context bundles for ChatGPT Projects,
Claude Projects, generic LLM chats, simple RAG workflows, or a local MCP
server that exposes the bundle to Claude / Cowork as tools.

The long-term goal is a **Project Context Packager**: a local app that helps
choose the right packaging strategy for the LLM and task, not just a file
combiner. See `CLAUDE.md` for the full product vision and version scope.

Status:

- **Version 1 CLI:** shipped. Recursive scan, per-type Markdown conversion,
  identity headers, manifests, target-aware bundles, instructions, and RAG
  chunks.
- **Version 2 UI:** in progress but usable for local preview/export. The
  Streamlit app can load/save profiles, scan/audit sources, review included
  files, review per-document chunks and deselect unwanted portions, preview
  the planned export, and create bundles through the shared backend.

Everything is local. The tool does not upload files, automate logins, drive a
browser, run OCR, create embeddings, or host a server.

## Quick Start On Windows

From this repo root:

```powershell
cd C:\Users\caleb\OneDrive\Desktop\Scripts\Fileslicer
python -m venv llm_project_packer\.venv
.\llm_project_packer\.venv\Scripts\python.exe -m pip install -r .\llm_project_packer\requirements.txt
python .\pack_project.py .\sample_input --target chatgpt --mode balanced
```

If you want to pack your own folder, replace `.\sample_input` with the folder
you want to process.

## macOS / Linux

```bash
cd llm_project_packer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python pack_project.py ../sample_input --target chatgpt --mode balanced
```

## Streamlit UI

Install the optional UI dependency from the repo root. This does not add
Streamlit to the core CLI install.

```powershell
pip install -r requirements-ui.txt
streamlit run streamlit_app.py
```

Streamlit opens at `http://localhost:8501`.

UI flow:

1. Load a built-in profile or create a blank profile.
2. Set project name, source folder, output folder, target, and mode.
3. Click `Scan Source Folder`.
4. Review files and include/exclude what should be packed.
5. Optionally open `Document chunk review`, pick a chunking strategy —
   token packing or heading sections (a new chunk at every heading of the
   chosen level) — preview how an included document splits into chunks, and
   deselect the portions you don't want exported. Each chunk shows its
   first heading, a structure summary (headings, paragraphs, list items,
   table rows), and the reason its boundary was drawn. The corpus chunking
   audit applies the current settings to every included document and adds
   `Chunking guidance`: plain-language tips on over-budget chunks,
   heading-rich corpora, boilerplate sections, and RAG-friendly chunk
   sizes. For RAG exports, `rag_ready/chunks.jsonl` uses the reviewed chunk
   settings, and `00_RAG_EXPORT_NOTES.md` includes retrieval-optimization
   tips. Corpus chunk rules (saved with the profile) exclude chunks whose
   first heading matches glob patterns like `*_html` or `content_hash`
   across every document at once — per-document selections override them.
   Documents without a chunk selection export in full; trimmed documents
   are noted in the manifest.
6. Adjust packaging settings, including the optional max-token override and
   projected bundle count.
7. Check the preview: included/skipped counts, target/mode, bundle budget,
   rough bundle count, output folder pattern, warnings, and instruction
   preview.
8. Click `Create LLM Project Bundles`.
9. Use the generated folder path and manual upload instructions shown after
   export.

Profiles are saved to `~/.llm_project_packer/profiles/`, the same location
used by the profile API. A profile captures the full chunking configuration
— chunk size, strategy, heading level, and corpus chunk rules — plus the
file review selection (excluded files re-apply on the next scan), alongside
the packaging settings. The `RAG Ready Export` built-in defaults to
retrieval-sized 800-token chunks.

## What It Does

1. Scans a source folder recursively.
2. Converts supported files to Markdown.
3. Adds stable source identity headers with `DOC_ID`, `SOURCE_FILE`,
   `SOURCE_PATH`, and `ORIGINAL_EXTENSION`.
4. Estimates token counts with `tiktoken` if installed, otherwise a `chars / 4`
   fallback.
5. Splits converted content into Markdown bundles by target and mode.
6. Writes a source manifest as Markdown, CSV, and JSON.
7. Generates target-specific instruction files.
8. For `--target rag`, writes `rag_ready/chunks.jsonl` and
   `rag_ready/source_map.json`.
9. For `--target cowork`, additionally writes a self-contained `mcp_server/`
   directory (FastMCP stdio server, FTS5-indexed SQLite database, and a
   paste-ready config snippet) that exposes the bundle to Claude / Cowork
   as MCP tools (`list_documents`, `get_document`, `search`, `get_chunk`,
   `get_asset_path`). The server runs locally; you still register it with
   your MCP-aware client by hand.

## Supported File Types

Text and Markdown:

- `.txt`
- `.md`
- `.markdown`

Documents and web pages:

- `.html`
- `.htm`
- `.pdf`
- `.docx`

Spreadsheets and data:

- `.csv`
- `.xlsx`
- `.json` (structured records render as Markdown with one heading per
  field, so chunk review and heading-aware tooling see the record's own
  structure)

Images:

- `.png`
- `.jpg`
- `.jpeg`
- `.gif`
- `.webp`
- `.svg`

Unsupported file types are recorded in the manifest as skipped instead of
crashing the run when they are included.

## CLI Usage

```powershell
python .\pack_project.py .\source_files --target chatgpt --mode balanced
```

Arguments:

| Argument | Description |
| --- | --- |
| `source_dir` | Folder of source files to scan recursively. |
| `--target` | One of `chatgpt`, `claude`, `generic`, `rag`, `cowork`. |
| `--mode` | One of `lean`, `balanced`, `full`, `visual_manual`. |
| `--output` | Output directory. Default: `.\llm_project_exports`. |
| `--max-bundle-tokens` | Optional override for the per-bundle token budget. |
| `--project-name` | Optional project name. Defaults to the source folder name. |
| `--include-extensions` | Comma-separated list, for example `.md,.txt,.html,.pdf`. |
| `--exclude-dirs` | Comma-separated list of directory names to skip, added to the defaults. |

Examples:

```powershell
python .\pack_project.py ".\manuals\transmission" --target claude --mode balanced
python .\pack_project.py ".\docs" --target chatgpt --mode lean --include-extensions .html,.pdf
python .\pack_project.py ".\kb" --target rag --mode balanced
python .\pack_project.py ".\big_corpus" --target generic --mode full --max-bundle-tokens 50000
python .\pack_project.py ".\manuals" --target cowork --mode balanced
```

The CLI and UI both use the shared backend:

```python
from packer import run_packaging_job

result = run_packaging_job(
    source_dir="./source_files",
    output_dir="./llm_project_exports",
    target="chatgpt",
    mode="balanced",
)
```

## Targets And Modes

`--target` selects the instruction file and output format. The RAG target
creates JSONL chunks instead of Markdown bundles.

`--mode` controls the default per-bundle token budget. For `rag` and `cowork`
this budget is the per-chunk size, not the per-bundle size:

| Target / Mode | chatgpt | claude | generic | rag | cowork |
| --- | ---: | ---: | ---: | ---: | ---: |
| `lean` | 60,000 | 80,000 | 40,000 | 25,000 | 1,500 |
| `balanced` | 90,000 | 120,000 | 60,000 | 40,000 | 2,500 |
| `full` | 120,000 | 160,000 | 90,000 | 50,000 | 4,000 |
| `visual_manual` | 90,000 | 120,000 | 60,000 | 40,000 | 2,500 |

These are packaging targets, not official platform context-window limits.
Platform limits can change. Edit `packer/presets.py` if you want different
bundle sizes.

## Output Structure

For `chatgpt`, `claude`, or `generic`:

```text
llm_project_exports/
  PROJECT_NAME_TARGET_MODE_TIMESTAMP/
    00_*_INSTRUCTIONS.md
    01_SOURCE_MANIFEST.md
    manifest.csv
    manifest.json
    02_BUNDLE_001.md
    03_BUNDLE_002.md
    assets/
    data/
```

For `rag`:

```text
llm_project_exports/
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

For `cowork`:

```text
llm_project_exports/
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
      index.sqlite
      cowork_config.json
      requirements.txt
      README.md
```

The scanner skips common generated folders such as `.venv`, `node_modules`,
`llm_project_exports`, `sample_output`, and `test_output`. If the output
folder is inside the source folder, it is skipped automatically during scan.

## Manual Upload

ChatGPT Project:

1. Create a new ChatGPT Project.
2. Upload `01_SOURCE_MANIFEST.md` and all `02_BUNDLE_*.md` files.
3. Upload files from `assets/` and `data/` when you want those originals
   available too.
4. Open `00_CHATGPT_PROJECT_INSTRUCTIONS.md` and paste its instruction block
   into the project instructions.

Claude Project:

1. Create a new Claude Project.
2. Add the exported files to Project Knowledge.
3. Open `00_CLAUDE_PROJECT_INSTRUCTIONS.md` and paste its instruction block
   into the project's custom instructions.

RAG export:

1. Use `manifest.json` or `manifest.csv` as the source index.
2. Use `rag_ready/chunks.jsonl` as the chunk file.
3. Use `rag_ready/source_map.json` to map documents to chunks.

Cowork / MCP export:

1. Install the runtime dep inside the bundle:
   `pip install -r mcp_server\requirements.txt`.
2. Open `mcp_server/cowork_config.json` and merge its `mcpServers` entry
   into your MCP-aware client's config (for example `~/.claude/mcp.json` or
   the Claude Desktop config), then restart the client.
3. The server registers as `fileslicer_<project>` and exposes
   `list_documents`, `get_document`, `search`, `get_chunk`, and
   `get_asset_path` to the client.

No upload step is automated.

## Current Limitations

- No automatic upload to ChatGPT, Claude, or any other LLM.
- No OCR.
- No embeddings or vector database.
- No login automation.
- No cloud hosting.
- Token presets are packaging targets, not official platform limits.
