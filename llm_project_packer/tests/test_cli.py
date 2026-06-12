from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
TEST_TMP_ROOT = WORKSPACE_DIR / "test_output" / "test_cli_tmp"
sys.path.insert(0, str(PROJECT_DIR))

from packer.profiles import Profile, save_profile  # noqa: E402


def _load_cli_module():
    spec = importlib.util.spec_from_file_location(
        "packer_cli_under_test", PROJECT_DIR / "pack_project.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli_module()

ALPHA_MD = """# Title

Intro paragraph before the sections.

## Section One

Body of section one with a couple of sentences in it.

## Section Two

Body of section two with a couple of sentences in it.
"""


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.source_dir = self.tmp_dir / "source"
        self.output_dir = self.tmp_dir / "out"
        self.profiles_dir = self.tmp_dir / "profiles"
        self.source_dir.mkdir(parents=True)
        (self.source_dir / "alpha.md").write_text(ALPHA_MD, encoding="utf-8")
        (self.source_dir / "beta.txt").write_text("Plain notes.\n", encoding="utf-8")
        (self.source_dir / "skipme.txt").write_text("Should be excluded.\n", encoding="utf-8")
        self.addCleanup(shutil.rmtree, self.tmp_dir, True)

    def _save_profile(self, **overrides) -> Profile:
        fields = dict(
            profile_name="CLI Test Profile",
            target="rag",
            mode="balanced",
            exclude_files=["skipme*"],
            chunk_token_budget=64,
            chunk_strategy="headings",
            chunk_heading_level=2,
        )
        fields.update(overrides)
        profile = Profile(**fields)
        save_profile(profile, profiles_dir=self.profiles_dir)
        return profile

    def _run_main(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def _profile_argv(self, *extra: str, source: bool = True):
        argv = [] if not source else [str(self.source_dir)]
        argv += [
            "--profile",
            "CLI Test Profile",
            "--profiles-dir",
            str(self.profiles_dir),
            "--output",
            str(self.output_dir),
        ]
        argv += list(extra)
        return argv

    def _single_export_dir(self) -> Path:
        exports = [p for p in self.output_dir.iterdir() if p.is_dir()]
        self.assertEqual(len(exports), 1)
        return exports[0]

    def test_missing_required_args_without_profile_exits_2(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                cli.main([str(self.source_dir), "--target", "chatgpt"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("the following arguments are required: --mode", stderr.getvalue())

    def test_missing_all_required_lists_each_argument(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--max-bundle-tokens", "5000"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn(
            "the following arguments are required: source_dir, --target, --mode",
            stderr.getvalue(),
        )

    def test_no_args_returns_2(self) -> None:
        code, _, stderr = self._run_main([])
        self.assertEqual(code, 2)
        self.assertIn("--target", stderr)

    def test_non_profile_run_still_succeeds(self) -> None:
        code, _, _ = self._run_main(
            [
                str(self.source_dir),
                "--target",
                "chatgpt",
                "--mode",
                "balanced",
                "--output",
                str(self.output_dir),
            ]
        )
        self.assertEqual(code, 0)
        export_dir = self._single_export_dir()
        self.assertIn("_chatgpt_balanced_", export_dir.name)
        self.assertTrue((export_dir / "01_SOURCE_MANIFEST.md").exists())

    def test_profile_run_applies_chunk_settings_and_exclude_files(self) -> None:
        self._save_profile()
        code, _, _ = self._run_main(self._profile_argv())
        self.assertEqual(code, 0)
        export_dir = self._single_export_dir()
        self.assertIn("_rag_balanced_", export_dir.name)

        manifest_text = (export_dir / "manifest.json").read_text(encoding="utf-8")
        self.assertIn("alpha.md", manifest_text)
        self.assertNotIn("skipme.txt", manifest_text)

        chunk_lines = (
            (export_dir / "rag_ready" / "chunks.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        chunks = [json.loads(line) for line in chunk_lines]
        alpha_chunks = [c for c in chunks if c["source_file"] == "alpha.md"]
        self.assertGreaterEqual(len(alpha_chunks), 3)
        self.assertTrue(
            any(c["text"].startswith("## Section Two") for c in alpha_chunks)
        )

    def test_profile_default_source_folder_is_used(self) -> None:
        self._save_profile(default_source_folder=str(self.source_dir))
        code, _, _ = self._run_main(self._profile_argv(source=False))
        self.assertEqual(code, 0)
        self.assertIn("_rag_balanced_", self._single_export_dir().name)

    def test_profile_without_source_anywhere_errors(self) -> None:
        self._save_profile()
        code, _, stderr = self._run_main(self._profile_argv(source=False))
        self.assertEqual(code, 2)
        self.assertIn("source_dir is required", stderr)

    def test_missing_source_directory_errors(self) -> None:
        self._save_profile(default_source_folder=str(self.tmp_dir / "nope"))
        code, _, stderr = self._run_main(self._profile_argv(source=False))
        self.assertEqual(code, 2)
        self.assertIn("Source directory does not exist", stderr)

    def test_unknown_profile_errors_with_available_names(self) -> None:
        self._save_profile()
        code, _, stderr = self._run_main(
            [
                str(self.source_dir),
                "--profile",
                "No Such Profile",
                "--profiles-dir",
                str(self.profiles_dir),
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("Unknown profile 'No Such Profile'", stderr)
        self.assertIn("CLI Test Profile", stderr)
        self.assertIn("RAG Ready Export", stderr)

    def test_cli_flags_override_profile_values(self) -> None:
        self._save_profile()
        code, _, _ = self._run_main(
            self._profile_argv("--target", "generic", "--mode", "lean")
        )
        self.assertEqual(code, 0)
        export_dir = self._single_export_dir()
        self.assertIn("_generic_lean_", export_dir.name)
        manifest_text = (export_dir / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("skipme.txt", manifest_text)

    def test_built_in_template_resolves_by_name(self) -> None:
        code, _, _ = self._run_main(
            [
                str(self.source_dir),
                "--profile",
                "Lean One-Shot Chat",
                "--profiles-dir",
                str(self.profiles_dir),
                "--output",
                str(self.output_dir),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("_generic_lean_", self._single_export_dir().name)


if __name__ == "__main__":
    unittest.main()
