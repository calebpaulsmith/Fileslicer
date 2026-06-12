from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
TEST_TMP_ROOT = WORKSPACE_DIR / "test_output" / "test_profiles_tmp"
sys.path.insert(0, str(PROJECT_DIR))

from packer import presets  # noqa: E402
from packer.profiles import (  # noqa: E402
    ACTIVE_FIELDS,
    INERT_FIELDS,
    Profile,
    default_profiles_dir,
    delete_profile,
    get_built_in_profile,
    list_built_in_profiles,
    list_profiles,
    load_profile,
    save_profile,
)


class ProfilesTestCase(unittest.TestCase):
    def make_tempdir(self) -> Path:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        path = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        return path


class ProfileDataclassTests(ProfilesTestCase):
    def test_default_profiles_dir_lives_under_user_home(self) -> None:
        path = default_profiles_dir()
        self.assertEqual(path.name, "profiles")
        self.assertEqual(path.parent.name, ".llm_project_packer")
        self.assertEqual(path.parent.parent, Path.home())

    def test_active_and_inert_field_sets_are_disjoint_and_complete(self) -> None:
        active = set(ACTIVE_FIELDS)
        inert = set(INERT_FIELDS)
        self.assertFalse(active & inert, "ACTIVE_FIELDS and INERT_FIELDS overlap")
        all_declared = {field for field in active | inert}
        # Every declared field must exist on the dataclass.
        from dataclasses import fields

        dataclass_fields = {f.name for f in fields(Profile)}
        missing = all_declared - dataclass_fields
        self.assertFalse(missing, f"Declared fields missing from Profile: {missing}")

    def test_validate_rejects_unknown_target(self) -> None:
        profile = Profile(profile_name="bad", target="nope", mode="balanced")
        with self.assertRaises(ValueError):
            profile.validate()

    def test_validate_rejects_unknown_mode(self) -> None:
        profile = Profile(profile_name="bad", target="chatgpt", mode="nope")
        with self.assertRaises(ValueError):
            profile.validate()

    def test_validate_rejects_blank_name(self) -> None:
        profile = Profile(profile_name="   ")
        with self.assertRaises(ValueError):
            profile.validate()

    def test_validate_rejects_non_positive_max_bundle_tokens(self) -> None:
        profile = Profile(profile_name="x", max_bundle_tokens=0)
        with self.assertRaises(ValueError):
            profile.validate()

    def test_validate_rejects_negative_preview_rows(self) -> None:
        profile = Profile(profile_name="x", spreadsheet_preview_rows=-1)
        with self.assertRaises(ValueError):
            profile.validate()

    def test_to_packaging_kwargs_returns_only_active_fields(self) -> None:
        profile = Profile(
            profile_name="p",
            project_name="MyProj",
            default_source_folder="C:/data",
            default_output_folder="C:/out",
            target="claude",
            mode="full",
            max_bundle_tokens=42,
            include_extensions=[".md", ".pdf"],
            exclude_dirs=["weird_dir"],
            include_assets=False,
            copy_data_files=False,
            spreadsheet_preview_rows=10,
            include_pdf_page_headers=False,
            include_source_metadata=False,
            bundle_separator_style="rule",
            create_zip=True,
        )
        kwargs = profile.to_packaging_kwargs()
        expected_keys = {
            "source_dir",
            "output_dir",
            "project_name",
            "target",
            "mode",
            "max_bundle_tokens",
            "include_extensions",
            "exclude_dirs",
            "exclude_files",
            "chunk_exclude_headings",
            "chunk_token_budget",
            "chunk_strategy",
            "chunk_heading_level",
            "chunk_min_tokens",
            "chunk_overlap_tokens",
            "chunk_split_sentences",
            "chunk_fence_aware",
        }
        self.assertEqual(set(kwargs.keys()), expected_keys)
        for inert in INERT_FIELDS:
            self.assertNotIn(inert, kwargs)

    def test_validate_rejects_negative_chunk_min_and_overlap(self) -> None:
        with self.assertRaises(ValueError):
            Profile(profile_name="x", chunk_min_tokens=-1).validate()
        with self.assertRaises(ValueError):
            Profile(profile_name="x", chunk_overlap_tokens=-1).validate()

    def test_to_packaging_kwargs_carries_chunk_min_and_overlap(self) -> None:
        profile = Profile(
            profile_name="p",
            default_source_folder="C:/data",
            chunk_min_tokens=40,
            chunk_overlap_tokens=80,
            chunk_split_sentences=True,
            chunk_fence_aware=True,
        )
        kwargs = profile.to_packaging_kwargs()
        self.assertEqual(kwargs["chunk_min_tokens"], 40)
        self.assertEqual(kwargs["chunk_overlap_tokens"], 80)
        self.assertIs(kwargs["chunk_split_sentences"], True)
        self.assertIs(kwargs["chunk_fence_aware"], True)

    def test_to_packaging_kwargs_uses_overrides(self) -> None:
        profile = Profile(
            profile_name="p",
            default_source_folder="C:/old/src",
            default_output_folder="C:/old/out",
            project_name="OldName",
        )
        kwargs = profile.to_packaging_kwargs(
            source_dir="D:/new/src",
            output_dir="D:/new/out",
            project_name="NewName",
        )
        self.assertEqual(kwargs["source_dir"], Path("D:/new/src"))
        self.assertEqual(kwargs["output_dir"], Path("D:/new/out"))
        self.assertEqual(kwargs["project_name"], "NewName")
        # Profile is unchanged.
        self.assertEqual(profile.default_source_folder, "C:/old/src")
        self.assertEqual(profile.default_output_folder, "C:/old/out")
        self.assertEqual(profile.project_name, "OldName")

    def test_to_packaging_kwargs_empty_lists_become_none(self) -> None:
        profile = Profile(profile_name="p", default_source_folder="C:/data")
        kwargs = profile.to_packaging_kwargs()
        self.assertIsNone(kwargs["include_extensions"])
        self.assertIsNone(kwargs["exclude_dirs"])
        self.assertIsNone(kwargs["exclude_files"])
        self.assertIsNone(kwargs["chunk_exclude_headings"])
        self.assertIsNone(kwargs["max_bundle_tokens"])

    def test_exclude_files_round_trip_and_kwargs(self) -> None:
        root = self.make_tempdir()
        try:
            profile = Profile(
                profile_name="Exclude Files Sample",
                default_source_folder="C:/src",
                exclude_files=["notes/draft.txt", "*.tmp"],
            )
            save_profile(profile, profiles_dir=root)
            loaded = load_profile("Exclude Files Sample", profiles_dir=root)
            self.assertEqual(loaded.exclude_files, ["notes/draft.txt", "*.tmp"])
            kwargs = loaded.to_packaging_kwargs()
            self.assertEqual(kwargs["exclude_files"], ["notes/draft.txt", "*.tmp"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.assertIsNone(kwargs["chunk_token_budget"])
        self.assertEqual(kwargs["chunk_strategy"], "tokens")
        self.assertEqual(kwargs["chunk_heading_level"], 2)

    def test_chunk_settings_round_trip_and_kwargs(self) -> None:
        root = self.make_tempdir()
        try:
            profile = Profile(
                profile_name="Chunk Settings Sample",
                default_source_folder="C:/src",
                chunk_token_budget=600,
                chunk_strategy="headings",
                chunk_heading_level=3,
            )
            save_profile(profile, profiles_dir=root)
            loaded = load_profile("Chunk Settings Sample", profiles_dir=root)
            self.assertEqual(loaded.chunk_token_budget, 600)
            self.assertEqual(loaded.chunk_strategy, "headings")
            self.assertEqual(loaded.chunk_heading_level, 3)
            kwargs = loaded.to_packaging_kwargs()
            self.assertEqual(kwargs["chunk_token_budget"], 600)
            self.assertEqual(kwargs["chunk_strategy"], "headings")
            self.assertEqual(kwargs["chunk_heading_level"], 3)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_rejects_bad_chunk_settings(self) -> None:
        with self.assertRaises(ValueError):
            Profile(profile_name="x", chunk_token_budget=0).validate()
        with self.assertRaises(ValueError):
            Profile(profile_name="x", chunk_strategy="semantic").validate()
        with self.assertRaises(ValueError):
            Profile(profile_name="x", chunk_heading_level=0).validate()

    def test_chunk_exclude_headings_round_trip_and_kwargs(self) -> None:
        root = self.make_tempdir()
        try:
            profile = Profile(
                profile_name="Rules Sample",
                default_source_folder="C:/src",
                chunk_exclude_headings=["*_html", "content_hash"],
            )
            save_profile(profile, profiles_dir=root)
            loaded = load_profile("Rules Sample", profiles_dir=root)
            self.assertEqual(
                loaded.chunk_exclude_headings, ["*_html", "content_hash"]
            )
            kwargs = loaded.to_packaging_kwargs()
            self.assertEqual(
                kwargs["chunk_exclude_headings"], ["*_html", "content_hash"]
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_rejects_non_list_chunk_exclude_headings(self) -> None:
        profile = Profile(profile_name="x")
        profile.chunk_exclude_headings = "not-a-list"  # type: ignore[assignment]
        with self.assertRaises(ValueError):
            profile.validate()

    def test_to_packaging_kwargs_requires_source(self) -> None:
        profile = Profile(profile_name="p")  # no default source, no override
        with self.assertRaises(ValueError):
            profile.to_packaging_kwargs()


class ProfileStorageTests(ProfilesTestCase):
    def test_save_load_round_trip_preserves_active_and_inert_fields(self) -> None:
        root = self.make_tempdir()
        try:
            profile = Profile(
                profile_name="Round Trip Sample",
                project_name="Project A",
                default_source_folder="C:/src",
                default_output_folder="C:/out",
                target="claude",
                mode="visual_manual",
                max_bundle_tokens=12345,
                include_extensions=[".html", ".pdf"],
                exclude_dirs=["weird_cache"],
                include_assets=False,
                copy_data_files=False,
                spreadsheet_preview_rows=7,
                include_pdf_page_headers=False,
                include_source_metadata=False,
                bundle_separator_style="rule",
                create_zip=True,
            )
            saved_path = save_profile(profile, profiles_dir=root)
            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.suffix, ".json")
            loaded = load_profile("Round Trip Sample", profiles_dir=root)
            self.assertEqual(loaded, profile)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_saved_json_is_human_readable(self) -> None:
        root = self.make_tempdir()
        try:
            profile = Profile(
                profile_name="Readable",
                project_name="Demo",
                default_source_folder="C:/src",
            )
            path = save_profile(profile, profiles_dir=root)
            text = path.read_text(encoding="utf-8")
            self.assertIn("\n  \"profile_name\": \"Readable\"", text)
            data = json.loads(text)
            self.assertEqual(data.get("profile_name"), "Readable")
            self.assertEqual(data.get("_schema_version"), 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_list_profiles_returns_sorted_display_names(self) -> None:
        root = self.make_tempdir()
        try:
            save_profile(Profile(profile_name="zeta config"), profiles_dir=root)
            save_profile(Profile(profile_name="Alpha config"), profiles_dir=root)
            save_profile(Profile(profile_name="middle config"), profiles_dir=root)
            self.assertEqual(
                list_profiles(profiles_dir=root),
                ["Alpha config", "middle config", "zeta config"],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_list_profiles_handles_missing_directory(self) -> None:
        ghost = self.make_tempdir() / "does_not_exist"
        self.assertEqual(list_profiles(profiles_dir=ghost), [])

    def test_list_profiles_skips_corrupt_json(self) -> None:
        root = self.make_tempdir()
        try:
            save_profile(Profile(profile_name="ok one"), profiles_dir=root)
            (root / "broken.json").write_text("not json", encoding="utf-8")
            self.assertEqual(list_profiles(profiles_dir=root), ["ok one"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_delete_profile_removes_file_and_returns_true(self) -> None:
        root = self.make_tempdir()
        try:
            save_profile(Profile(profile_name="kill me"), profiles_dir=root)
            self.assertTrue(delete_profile("kill me", profiles_dir=root))
            self.assertEqual(list_profiles(profiles_dir=root), [])
            # Second delete is a no-op.
            self.assertFalse(delete_profile("kill me", profiles_dir=root))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_load_missing_profile_raises(self) -> None:
        root = self.make_tempdir()
        try:
            with self.assertRaises(FileNotFoundError):
                load_profile("never saved", profiles_dir=root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_save_rejects_invalid_profile(self) -> None:
        root = self.make_tempdir()
        try:
            bad = Profile(profile_name="bad", target="nope", mode="balanced")
            with self.assertRaises(ValueError):
                save_profile(bad, profiles_dir=root)
            self.assertEqual(list_profiles(profiles_dir=root), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_load_drops_unknown_fields_for_forward_compat(self) -> None:
        root = self.make_tempdir()
        try:
            payload = {
                "_schema_version": 99,
                "profile_name": "future me",
                "target": "chatgpt",
                "mode": "balanced",
                "future_field": "ignore me",
            }
            (root / "future_me.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
            loaded = load_profile("future me", profiles_dir=root)
            self.assertEqual(loaded.profile_name, "future me")
            self.assertFalse(hasattr(loaded, "future_field"))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class BuiltInProfileTests(ProfilesTestCase):
    EXPECTED_BUILT_INS = (
        "ChatGPT Balanced Project",
        "Claude Full Project",
        "Visual Repair Manual",
        "RAG Ready Export",
        "Lean One-Shot Chat",
    )

    def test_built_in_names_match_spec(self) -> None:
        self.assertEqual(tuple(list_built_in_profiles()), self.EXPECTED_BUILT_INS)

    def test_each_built_in_validates(self) -> None:
        for name in list_built_in_profiles():
            profile = get_built_in_profile(name)
            profile.validate()
            self.assertIn(profile.target, presets.TARGETS)
            self.assertIn(profile.mode, presets.MODES)

    def test_get_built_in_returns_independent_copies(self) -> None:
        a = get_built_in_profile("ChatGPT Balanced Project")
        b = get_built_in_profile("ChatGPT Balanced Project")
        self.assertIsNot(a, b)
        a.project_name = "mutated"
        self.assertNotEqual(a.project_name, b.project_name)

    def test_built_in_unknown_name_raises(self) -> None:
        with self.assertRaises(KeyError):
            get_built_in_profile("Not A Real Template")

    def test_built_in_target_mode_pairs(self) -> None:
        expected = {
            "ChatGPT Balanced Project": ("chatgpt", "balanced"),
            "Claude Full Project": ("claude", "full"),
            "Visual Repair Manual": ("claude", "visual_manual"),
            "RAG Ready Export": ("rag", "balanced"),
            "Lean One-Shot Chat": ("generic", "lean"),
        }
        for name, (target, mode) in expected.items():
            profile = get_built_in_profile(name)
            self.assertEqual(profile.target, target, name)
            self.assertEqual(profile.mode, mode, name)

    def test_built_in_can_be_saved_and_reloaded(self) -> None:
        root = self.make_tempdir()
        try:
            profile = get_built_in_profile("RAG Ready Export")
            profile.default_source_folder = "C:/some/source"
            save_profile(profile, profiles_dir=root)
            reloaded = load_profile("RAG Ready Export", profiles_dir=root)
            self.assertEqual(reloaded.target, "rag")
            self.assertEqual(reloaded.default_source_folder, "C:/some/source")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
