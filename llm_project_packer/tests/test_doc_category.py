from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from packer.doc_category import (  # noqa: E402
    CATEGORY_APPEAL,
    CATEGORY_OTHER,
    CATEGORY_POLICY,
    guess_category,
    normalize_category,
    normalize_overrides,
    resolve_category,
)


class GuessCategoryTests(unittest.TestCase):
    def test_pappg_and_policy_names_are_policy(self) -> None:
        names = [
            "PAPPG 5 Amended PAPPG-v5.0-amended-508-cleared-FINAL_SIGNED.pdf",
            "Public Assistance Policy Guide.pdf",
            "recovery_directive_9523.pdf",
            "FEMA Procurement Guidance.pdf",
        ]
        for name in names:
            self.assertEqual(guess_category(name), CATEGORY_POLICY, name)

    def test_appeal_and_case_names_are_appeal(self) -> None:
        names = [
            "1174-DR-ND University of North Dakota DSR 41251.pdf",
            "4699-DR-CA_Madera_County_GMP_742129.pdf",
            "FEMA-3589-EM-NY Village of Dexter GMP 711626.pdf",
            "FEMA-4021-DR-NJ Township of Vernon - Multiple PWs .pdf",
            "Second Appeal - Township of Vernon.pdf",
        ]
        for name in names:
            self.assertEqual(guess_category(name), CATEGORY_APPEAL, name)

    def test_unmatched_names_are_other(self) -> None:
        for name in ("notes.txt", "data.csv", "icon.png", "README.md"):
            self.assertEqual(guess_category(name), CATEGORY_OTHER, name)

    def test_policy_wins_over_appeal_markers(self) -> None:
        # A guide that mentions appeals in its name is still policy.
        self.assertEqual(
            guess_category("Appeals Policy Guide 4021-DR.pdf"), CATEGORY_POLICY
        )


class ResolveAndNormalizeTests(unittest.TestCase):
    def test_normalize_category_falls_back_to_other(self) -> None:
        self.assertEqual(normalize_category("policy"), CATEGORY_POLICY)
        self.assertEqual(normalize_category("APPEAL"), CATEGORY_APPEAL)
        self.assertEqual(normalize_category("nonsense"), CATEGORY_OTHER)
        self.assertEqual(normalize_category(None), CATEGORY_OTHER)

    def test_override_beats_guess(self) -> None:
        overrides = normalize_overrides(
            {"PAPPG.pdf": "appeal", "1174-DR-ND DSR.pdf": "policy"}
        )
        # Overrides invert the filename-based guess.
        self.assertEqual(resolve_category("PAPPG.pdf", overrides), CATEGORY_APPEAL)
        self.assertEqual(
            resolve_category("1174-DR-ND DSR.pdf", overrides), CATEGORY_POLICY
        )

    def test_missing_override_uses_guess(self) -> None:
        overrides = normalize_overrides({"other.pdf": "policy"})
        self.assertEqual(resolve_category("PAPPG.pdf", overrides), CATEGORY_POLICY)

    def test_override_keys_are_case_insensitive(self) -> None:
        overrides = normalize_overrides({"Sub/Dir/PAPPG.pdf": "appeal"})
        self.assertEqual(
            resolve_category("sub/dir/pappg.pdf", overrides), CATEGORY_APPEAL
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
