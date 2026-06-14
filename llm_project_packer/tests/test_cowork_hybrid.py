from __future__ import annotations

import json
import math
import py_compile
import shutil
import sqlite3
import sys
import tempfile
import unittest
from array import array
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "tests"))

from packer.exporters import _SERVER_RETRIEVAL_TOOLS  # noqa: E402
from packer.pipeline import run_packaging_job  # noqa: E402
from test_appeals_source import _build_db  # noqa: E402


class _FakeMcp:
    def tool(self):
        def deco(fn):
            return fn

        return deco


def _load_server_tools(mcp_dir: Path) -> dict:
    """Exec the generated retrieval block against a real index with light stubs.

    The full server.py needs the optional ``mcp`` package to import, so we run
    the provider-agnostic retrieval functions directly instead.
    """

    def _connect():
        conn = sqlite3.connect(mcp_dir / "index.sqlite")
        conn.row_factory = sqlite3.Row
        return conn

    def _escape_fts_query(query: str) -> str:
        tokens = [t for t in query.replace('"', " ").split() if t]
        return " ".join(f'"{t}"' for t in tokens)

    ns = {
        "json": json,
        "math": math,
        "sys": sys,
        "sqlite3": sqlite3,
        "Path": Path,
        "array": array,
        "Dict": dict,
        "Any": object,
        "List": list,
        "Optional": object,
        "SERVER_DIR": mcp_dir,
        "_connect": _connect,
        "_escape_fts_query": _escape_fts_query,
        "mcp": _FakeMcp(),
    }
    exec(_SERVER_RETRIEVAL_TOOLS, ns)
    return ns


class CoworkHybridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = self.tmp / "a.sqlite3"
        _build_db(
            self.db,
            [
                {
                    "final_id": 1,
                    "html_id": 1,
                    "html_doc_key": "k1",
                    "final_title": "Flood Debris Removal",
                    "final_summary_text": "The applicant requested funds for flood debris removal after the storm.",
                    "final_status": "Approved",
                },
                {
                    "final_id": 2,
                    "html_id": 2,
                    "html_doc_key": "k2",
                    "final_title": "Building Code Upgrade",
                    "final_summary_text": "Disputed costs for building code upgrades on a damaged facility.",
                    "final_status": "Denied",
                },
            ],
            {"k1": ["44 C.F.R. 206.224"]},
        )

    def _export(self, embedding_model: str):
        safe = (embedding_model or "none").replace(":", "_")
        result = run_packaging_job(
            appeals_db=self.db,
            source_kind="appeals",
            output_dir=self.tmp / f"out_{safe}",
            project_name="Appeals",
            target="cowork",
            mode="balanced",
            embedding_model=embedding_model,
        )
        return result.export_dir / "mcp_server"

    def test_cowork_builds_vector_index_and_server(self) -> None:
        mcp_dir = self._export("hashing")
        py_compile.compile(str(mcp_dir / "server.py"), doraise=True)
        self.assertTrue((mcp_dir / "embedder.py").exists())
        conn = sqlite3.connect(mcp_dir / "index.sqlite")
        try:
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0], 0)
            meta = dict(conn.execute("SELECT key, value FROM embedder_meta").fetchall())
            self.assertIn("backend", meta)
            with_meta = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE metadata IS NOT NULL"
            ).fetchone()[0]
            self.assertGreater(with_meta, 0)
        finally:
            conn.close()

    def test_vector_and_hybrid_search(self) -> None:
        mcp_dir = self._export("hashing")
        tools = _load_server_tools(mcp_dir)
        vs = tools["vector_search"]("flood debris removal", 3)
        self.assertTrue(vs["available"])
        self.assertEqual(vs["hits"][0]["doc_id"], "DOC_0001")
        self.assertEqual(vs["hits"][0]["metadata"]["title"], "Flood Debris Removal")

        hs = tools["hybrid_search"]("building code upgrade costs", 3)
        self.assertTrue(hs["used_vectors"])
        self.assertEqual(hs["hits"][0]["metadata"]["title"], "Building Code Upgrade")
        # Rerank degrades gracefully when sentence-transformers is absent.
        rr = tools["hybrid_search"]("flood", 3, True)
        self.assertIn(rr["reranked"], (True, False))

    def test_no_embedding_degrades_to_fts_only(self) -> None:
        # An unresolvable embedder leaves no vector index; the server still builds.
        import os

        saved = {k: os.environ.pop(k, None) for k in ("OPENAI_API_KEY", "VOYAGE_API_KEY")}
        try:
            mcp_dir = self._export("openai:text-embedding-3-small")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        conn = sqlite3.connect(mcp_dir / "index.sqlite")
        try:
            has_vectors = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='vectors'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNone(has_vectors)
        tools = _load_server_tools(mcp_dir)
        vs = tools["vector_search"]("anything", 3)
        self.assertFalse(vs["available"])


if __name__ == "__main__":
    unittest.main()
