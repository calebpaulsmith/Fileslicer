from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.context_probe import _canary_code, build_context_probe  # noqa: E402


class ContextProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_canary_codes_are_deterministic_and_unique(self) -> None:
        self.assertEqual(_canary_code(1), _canary_code(1))
        codes = {_canary_code(i) for i in range(1, 50)}
        self.assertEqual(len(codes), 49)
        self.assertTrue(all(c.startswith("PROBE-") for c in codes))

    def test_build_probe_structure(self) -> None:
        folder = build_context_probe(self.tmp, bundle_tokens=1500, bundles=4)
        names = sorted(p.name for p in folder.iterdir())
        self.assertIn("00_PROBE_INSTRUCTIONS.md", names)
        self.assertIn("01_PROBE_DEPTH_FILE.md", names)
        self.assertIn("PROBE_ANSWER_KEY.md", names)
        probe_bundles = [n for n in names if n.startswith("02_PROBE_BUNDLE") or "_PROBE_BUNDLE_" in n]
        self.assertEqual(len(probe_bundles), 4)

    def test_each_bundle_holds_its_canary_and_key_lists_all(self) -> None:
        folder = build_context_probe(self.tmp, bundle_tokens=1200, bundles=3)
        key = (folder / "PROBE_ANSWER_KEY.md").read_text(encoding="utf-8")
        for i in range(1, 4):
            code = _canary_code(i)
            self.assertIn(code, key)
            bundle = folder / f"{i + 1:02d}_PROBE_BUNDLE_{i:03d}.md"
            self.assertIn(code, bundle.read_text(encoding="utf-8"))
        # The answer key must not be something you'd upload (it has the answers).
        self.assertIn("do NOT upload", key)

    def test_answer_key_excluded_from_upload_instructions(self) -> None:
        folder = build_context_probe(self.tmp, bundle_tokens=1000, bundles=2)
        instructions = (folder / "00_PROBE_INSTRUCTIONS.md").read_text(encoding="utf-8")
        self.assertIn("Do **not** upload `PROBE_ANSWER_KEY.md`", instructions)


if __name__ == "__main__":
    unittest.main()
