from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.embedder import (  # noqa: E402
    EmbedderError,
    HashingEmbedder,
    _local_family,
    _local_prefix,
    build_embedder_from_meta,
    embedder_meta,
    resolve_embedder,
)


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


class EmbedderTests(unittest.TestCase):
    def test_default_is_offline_hashing(self) -> None:
        e = resolve_embedder(None)
        self.assertIsInstance(e, HashingEmbedder)
        self.assertEqual(e.backend, "hashing")

    def test_hashing_is_deterministic(self) -> None:
        e = HashingEmbedder(128)
        self.assertEqual(e.embed(["flood damage"]), e.embed(["flood damage"]))

    def test_hashing_cosine_reflects_overlap(self) -> None:
        e = HashingEmbedder(256)
        vecs = e.embed(["flood damage repair", "flood damage repair", "unrelated content"])
        self.assertAlmostEqual(_cos(vecs[0], vecs[1]), 1.0, places=5)
        self.assertLess(_cos(vecs[0], vecs[2]), 0.5)

    def test_meta_round_trip(self) -> None:
        e = resolve_embedder("hashing:64")
        meta = embedder_meta(e)
        self.assertEqual(meta["backend"], "hashing")
        rebuilt = build_embedder_from_meta(meta)
        self.assertEqual(rebuilt.dim, e.dim)
        self.assertEqual(rebuilt.embed(["x y"]), e.embed(["x y"]))

    def test_unknown_backend_raises(self) -> None:
        with self.assertRaises(EmbedderError):
            resolve_embedder("nonsense:model")

    def test_local_family_detection(self) -> None:
        self.assertEqual(_local_family("bge-small-en-v1.5"), "bge")
        self.assertEqual(_local_family("e5-base-v2"), "e5")
        self.assertEqual(_local_family("some-other-model"), "")

    def test_local_prefix_is_asymmetric(self) -> None:
        # e5 prefixes both sides; bge only instructs the query side.
        self.assertEqual(_local_prefix("road damage", True, "e5"), "query: road damage")
        self.assertEqual(_local_prefix("road damage", False, "e5"), "passage: road damage")
        self.assertTrue(_local_prefix("road damage", True, "bge").endswith("road damage"))
        self.assertNotEqual(_local_prefix("road damage", True, "bge"), "road damage")
        self.assertEqual(_local_prefix("road damage", False, "bge"), "road damage")
        self.assertEqual(_local_prefix("road damage", True, ""), "road damage")

    def test_local_backend_resolves_or_requires_dependency(self) -> None:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            with self.assertRaises(EmbedderError):
                resolve_embedder("local:bge-small-en-v1.5")
        else:
            self.skipTest("sentence-transformers installed; skip to avoid a model download")

    def test_openai_without_key_raises(self) -> None:
        import os

        saved = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with self.assertRaises(EmbedderError):
                resolve_embedder("openai:text-embedding-3-small")
        finally:
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved


if __name__ == "__main__":
    unittest.main()
