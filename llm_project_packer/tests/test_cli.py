from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sqlite3
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

    def _build_appeals_db(self) -> Path:
        db = self.tmp_dir / "appeals.sqlite3"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE final_appeal_authority "
            "(final_id INTEGER, html_id INTEGER, final_title TEXT, "
            "final_appellant TEXT, final_recipient TEXT, final_pa_id TEXT, "
            "final_disaster_number_raw TEXT, final_disaster_number_norm TEXT, "
            "final_decision_signed_date TEXT, final_declaration_date TEXT, "
            "final_pw_gmp_compact TEXT, final_gmp_number TEXT, final_pw_number TEXT, "
            "final_region TEXT, final_status TEXT, final_summary_text TEXT, "
            "final_analysis_text TEXT, final_conclusion_text TEXT, final_letter_text TEXT, "
            "final_headnotes_text TEXT, final_authorities_text TEXT, "
            "final_footnotes_text TEXT, final_body_text TEXT)"
        )
        conn.execute(
            "INSERT INTO final_appeal_authority (final_id, final_title, final_summary_text) "
            "VALUES (1, 'Alpha Appeal', 'Summary body.')"
        )
        conn.commit()
        conn.close()
        return db

    def test_appeals_db_standalone_run(self) -> None:
        db = self._build_appeals_db()
        code, _, _ = self._run_main(
            [
                "--appeals-db",
                str(db),
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
        self.assertIn("appeals_chatgpt_balanced_", export_dir.name)
        manifest_text = (export_dir / "manifest.json").read_text(encoding="utf-8")
        self.assertIn("appeal_1_Alpha_Appeal.md", manifest_text)
        bundle_text = (export_dir / "02_BUNDLE_001.md").read_text(encoding="utf-8")
        self.assertIn("# Alpha Appeal", bundle_text)

    def test_appeals_db_with_destination_profile(self) -> None:
        db = self._build_appeals_db()
        code, _, _ = self._run_main(
            [
                "--profile",
                "DHS / ChatGPT Enterprise",
                "--appeals-db",
                str(db),
                "--profiles-dir",
                str(self.profiles_dir),
                "--output",
                str(self.output_dir),
            ]
        )
        self.assertEqual(code, 0)
        export_dir = self._single_export_dir()
        self.assertTrue((export_dir / "00_CORPUS_OVERVIEW.md").exists())
        instr = (export_dir / "00_CHATGPT_PROJECT_INSTRUCTIONS.md").read_text(encoding="utf-8")
        self.assertIn("Packaging guidance for this destination", instr)

    def test_context_probe_generates_and_exits(self) -> None:
        code, out, _ = self._run_main(
            ["--context-probe", "3", "--output", str(self.output_dir), "--max-bundle-tokens", "1500"]
        )
        self.assertEqual(code, 0)
        self.assertIn("Context probe written", out)
        probe_dirs = [p for p in self.output_dir.iterdir() if p.is_dir() and "probe" in p.name]
        self.assertEqual(len(probe_dirs), 1)
        names = {p.name for p in probe_dirs[0].iterdir()}
        self.assertIn("PROBE_ANSWER_KEY.md", names)
        self.assertIn("00_PROBE_INSTRUCTIONS.md", names)

    def test_appeals_db_bare_flag_uses_default(self) -> None:
        from packer import presets

        parser = cli.build_parser()
        args = parser.parse_args(["--appeals-db", "--target", "rag", "--mode", "balanced"])
        self.assertEqual(str(args.appeals_db), presets.DEFAULT_APPEALS_DB)

    def test_missing_appeals_db_exits_2(self) -> None:
        code, _, stderr = self._run_main(
            [
                "--appeals-db",
                str(self.tmp_dir / "nope.sqlite3"),
                "--target",
                "rag",
                "--mode",
                "balanced",
                "--output",
                str(self.output_dir),
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("Appeals database does not exist", stderr)


if __name__ == "__main__":
    unittest.main()
