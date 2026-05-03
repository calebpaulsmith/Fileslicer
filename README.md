# llm_project_packer

A local Python command-line tool and Streamlit UI that turns a folder of mixed
source files into upload-ready project context bundles for ChatGPT Projects,
Claude Projects, generic LLM chats, or simple RAG workflows.

The long-term goal is a **Project Context Packager**: a local app that helps
choose the right packaging strategy for the LLM and task, not just a file
combiner. See `CLAUDE.md` for the full product vision and version scope.

Status:

- **Version 1 CLI:** shipped. Recursive scan, per-type Markdown conversion,
  identity headers, manifests, target-aware bundles, instructions, and RAG
  chunks.
- **Version 2 UI:** in progress but usable for local preview/export. The
  Streamlit app can load/save profiles, scan/audit sources, review included
  files, preview the planned export, and create bundles through the shared
  backend.

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
5. Check the preview: included/skipped counts, target/mode, bundle budget,
   rough bundle count, output folder pattern, warnings, and instruction
   preview.
6. Click `Create LLM Project Bundles`.
7. Use the generated folder path and manual upload instructions shown after
   export.

Profiles are saved to `~/.llm_project_packer/profiles/`, the same location
used by the profile API.

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
| `--target` | One of `chatgpt`, `claude`, `generic`, `rag`. |
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

`--mode` controls the default per-bundle token budget:

| Target / Mode | chatgpt | claude | generic | rag |
| --- | ---: | ---: | ---: | ---: |
| `lean` | 60,000 | 80,000 | 40,000 | 25,000 |
| `balanced` | 90,000 | 120,000 | 60,000 | 40,000 |
| `full` | 120,000 | 160,000 | 90,000 | 50,000 |
| `visual_manual` | 90,000 | 120,000 | 60,000 | 40,000 |

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

No upload step is automated.

## Current Limitations

- No automatic upload to ChatGPT, Claude, or any other LLM.
- No OCR.
- No embeddings or vector database.
- No login automation.
- No cloud hosting.
- Token presets are packaging targets, not official platform limits.
