# Cowork MCP Bundle — sample_input

- **Target:** cowork
- **Mode:** balanced
- **Documents:** 5
- **Estimated total tokens:** 287
- **Per-chunk token budget:** 2,500
- **Token estimator backend:** heuristic (chars/4)

## What this export contains

- `01_SOURCE_MANIFEST.md` / `manifest.csv` / `manifest.json` — the canonical document list.
- `rag_ready/chunks.jsonl` + `rag_ready/source_map.json` — the chunked corpus the server reads from.
- `assets/` and `data/` — copied images and original CSV/XLSX files.
- `mcp_server/` — a self-contained local MCP server that exposes this bundle as tools.

## How to use this bundle with Claude / Cowork

1. Install the MCP runtime inside the bundle (one-time per Python environment):

   ```powershell
   pip install -r mcp_server\requirements.txt
   ```

2. Register the server with your MCP-aware client. The bundle ships a paste-ready
   snippet at `mcp_server/cowork_config.json`. Merge its `mcpServers` entry into your
   client's MCP config (for example `~/.claude/mcp.json` or the Claude Desktop config),
   then restart the client.

3. Confirm the server is connected. Claude / Cowork will list the tools provided by
   `fileslicer_sample_input` and let you call `search`, `get_document`, `list_documents`,
   `get_chunk`, and `get_asset_path` directly from chat.

## Tools the server exposes

- `list_documents(limit=50, status=None)` — manifest rows (doc_id, source_file, status, token estimate).
- `get_document(doc_id)` — identity header + full text for one document.
- `search(query, limit=10)` — SQLite FTS5 keyword search across all chunks, ranked by BM25.
- `get_chunk(chunk_id)` — chunk text plus the previous/next chunk ids in the same document.
- `get_asset_path(doc_id, name)` — absolute local path to a copied image or data file.

## Notes

These bundle token budgets are *packaging targets* this tool uses to decide how to split content. They are NOT official platform context-window limits, which change over time. Edit the presets in `packer/presets.py` if you want different bundle sizes.

This tool does not upload anything to Claude for you. The MCP server runs locally on
your machine and only responds to the MCP client you have explicitly registered it with.
