"""Deterministic wildcard/mask matching tests (Phase 4 / Phase 10 fixture 4)."""

from __future__ import annotations

import unittest

from services.wildcard_matcher import has_wildcards, match_wildcard_mask


class WildcardDetectionTests(unittest.TestCase):
    def test_detects_star_and_question_mark(self):
        self.assertTrue(has_wildcards("W44X3**"))
        self.assertTrue(has_wildcards("HSS6X6X1/?"))
        self.assertFalse(has_wildcards("W18X35"))


class WildcardMaskMatchingTests(unittest.TestCase):
    def test_no_wildcards_returns_empty(self):
        self.assertEqual(match_wildcard_mask("W18X35"), [])

    def test_w44x3_star_star_resolves_deterministically(self):
        candidates = match_wildcard_mask("W44X3**")
        labels = {item.label for item in candidates}

        # The real AISC catalog has exactly W44X335 and W44X368 for this mask.
        self.assertIn("W44X335", labels)
        self.assertIn("W44X368", labels)

        for item in candidates:
            # Stays in family W — no cross-family leakage.
            self.assertTrue(item.label.startswith("W"))
            # Preserves the known "W44X3" prefix.
            self.assertTrue(item.label.startswith("W44X3"))
            self.assertTrue(item.catalog_valid)
            self.assertTrue(item.mask_match)
            self.assertIn("Family W matches", item.match_reasons)
            self.assertIn("Known depth 44 matches", item.match_reasons)
            self.assertIn("Two wildcard positions matched", item.match_reasons)

    def test_unrelated_w_sections_are_excluded(self):
        candidates = match_wildcard_mask("W44X3**")
        labels = {item.label for item in candidates}
        self.assertNotIn("W18X35", labels)
        self.assertNotIn("W44X262", labels)  # wrong length / prefix mismatch

    def test_other_families_are_excluded(self):
        candidates = match_wildcard_mask("W44X3**")
        for item in candidates:
            self.assertFalse(item.label.startswith("HSS"))
            self.assertFalse(item.label.startswith("C"))

    def test_single_question_mark_wildcard(self):
        candidates = match_wildcard_mask("HSS6X6X1/?")
        labels = {item.label for item in candidates}
        self.assertTrue(any(label.startswith("HSS6X6X1/") for label in labels))
        for item in candidates:
            self.assertTrue(item.catalog_valid)

    def test_unknown_family_returns_empty(self):
        self.assertEqual(match_wildcard_mask("ZZ4X4**"), [])

    def test_mask_with_no_catalog_match_returns_empty(self):
        # A physically impossible depth should not fabricate a candidate.
        self.assertEqual(match_wildcard_mask("W99999X**"), [])


if __name__ == "__main__":
    unittest.main()
