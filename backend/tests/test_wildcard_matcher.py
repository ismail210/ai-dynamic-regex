"""Deterministic wildcard/mask matching tests (Phase 4 / Phase 10 fixture 4)."""

from __future__ import annotations

import unittest

from services import database_loader, wildcard_matcher
from services.family_codes import longest_prefix_first, split_family
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
            # Exact family W — WT must not match via startswith("W").
            family, _remainder = split_family(
                item.label, wildcard_matcher._FAMILY_PREFIXES
            )
            self.assertEqual(family, "W")
            self.assertFalse(item.label.startswith("WT"))
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
            self.assertFalse(item.label.startswith("WT"))

    def test_w_mask_does_not_match_wt(self):
        for query in ("W??X?7", "W*8X50", "W**X14", "W??X45"):
            with self.subTest(query=query):
                candidates = match_wildcard_mask(query)
                for item in candidates:
                    family, _remainder = split_family(
                        item.label, wildcard_matcher._FAMILY_PREFIXES
                    )
                    self.assertEqual(family, "W")
                    self.assertFalse(item.label.startswith("WT"))
        labels = {item.label for item in match_wildcard_mask("W*8X50")}
        self.assertNotIn("WT8X50", labels)
        self.assertIn("W18X50", labels)

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

    def test_round_hss_decimal_depth_reason_not_truncated(self):
        # "Known depth 10 matches" used to be reported for a 10.750-depth
        # round HSS (digits-only regex stopped at the decimal point).
        candidates = match_wildcard_mask("HSS10.750X0.1**")
        self.assertTrue(candidates, "expected at least one real catalog match")
        for item in candidates:
            self.assertIn("Known depth 10.750 matches", item.match_reasons)


class FamilyCodesSharedSourceTests(unittest.TestCase):
    """`_FAMILY_PREFIXES` must come from one shared definition
    (services.family_codes), not an independently hardcoded literal that can
    drift out of sync with services.label_reconstruction.corruption's copy."""

    def test_longest_prefix_first_orders_by_length(self):
        self.assertEqual(
            longest_prefix_first({"W", "WT", "HSS"}), ["HSS", "WT", "W"]
        )

    def test_split_family_prefers_longest_match(self):
        self.assertEqual(split_family("WT12X51", {"W", "WT"}), ("WT", "12X51"))
        self.assertEqual(split_family("2L6X6X1", {"L", "2L"}), ("2L", "6X6X1"))

    def test_split_family_no_match_returns_empty_prefix(self):
        self.assertEqual(split_family("ZZ4X4", {"W", "L"}), ("", "ZZ4X4"))

    def tearDown(self):
        database_loader.reset_to_default()
        wildcard_matcher.refresh_family_prefixes()

    def test_refresh_family_prefixes_reflects_reloaded_catalog(self):
        default_prefixes = set(wildcard_matcher._FAMILY_PREFIXES)
        self.assertIn("W", default_prefixes)
        self.assertNotIn("WF", default_prefixes)  # not in the production XLSX catalog

        database_loader.reload_from_pairs(
            [("W12X26", "W"), ("8WF17", "WF")], source="unit-test-pairs"
        )
        refreshed = set(wildcard_matcher.refresh_family_prefixes())
        self.assertIn("WF", refreshed)  # new family from the reloaded catalog
        self.assertIn("W", refreshed)  # modern floor still present

    def test_refresh_never_drops_below_the_modern_floor(self):
        # Even a catalog swap that happens not to include every modern
        # family must not make wildcard_matcher forget how to split them —
        # the 13-family floor is unioned in, never replaced.
        database_loader.reload_from_pairs([("HSS6X6X1/4", "HSS")], source="unit-test-pairs")
        refreshed = set(wildcard_matcher.refresh_family_prefixes())
        self.assertIn("W", refreshed)
        self.assertIn("HSS", refreshed)


if __name__ == "__main__":
    unittest.main()
