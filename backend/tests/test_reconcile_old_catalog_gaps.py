"""
Tests for scripts.reconcile_old_catalog_gaps's classification logic: an old
catalog label missing from the new canonical catalog must be classified by
*why*, using actual numeric content (never generic string similarity, which
scores textually-close-but-dimensionally-different designations as
"the same shape written differently").
"""

from __future__ import annotations

import unittest

from scripts.reconcile_old_catalog_gaps import _numeric_signature, classify


class NumericSignatureTests(unittest.TestCase):
    def test_mixed_fraction_parsed(self):
        self.assertEqual(_numeric_signature("L3-1/2X3X1/4"), (3.5, 3.0, 0.25))

    def test_leading_family_multiplier_digit_is_part_of_the_signature(self):
        # "2L" is a real leading digit (double-angle family), not noise —
        # both sides of any comparison carry it consistently since they
        # always share the same declared family.
        self.assertEqual(_numeric_signature("2L3-1/2X3X1/4"), (2.0, 3.5, 3.0, 0.25))

    def test_decimal_and_fraction_forms_agree(self):
        self.assertEqual(_numeric_signature("L3.5X3X0.25"), _numeric_signature("L3-1/2X3X1/4"))

    def test_different_dimension_gives_different_signature(self):
        self.assertNotEqual(
            _numeric_signature("HSS22X18X5/8"), _numeric_signature("HSS20X18X5/8")
        )


class ClassifyTests(unittest.TestCase):
    def test_textually_similar_but_different_shape_is_not_formatting_difference(self):
        # This is the bug the numeric-signature approach fixes: these two
        # strings are a 1-character edit apart, but 22 != 20 is a real,
        # different physical shape, not a spelling variant.
        full_clean = {"HSS": ["HSS20X18X5/8"]}
        reason, match = classify("HSS", "HSS22X18X5/8", "HSS22X18X5/8", full_clean, set())
        self.assertEqual(reason, "missing_from_raw_source")
        self.assertIsNone(match)

    def test_same_numbers_different_delimiter_is_formatting_difference(self):
        full_clean = {"L": ["L3.5X3X0.25"]}
        reason, match = classify("L", "L3-1/2X3X1/4", "L3-1/2X3X1/4", full_clean, set())
        self.assertEqual(reason, "formatting_difference")
        self.assertEqual(match, "L3.5X3X0.25")

    def test_conflict_wins_over_formatting_check(self):
        full_clean = {"2L": []}
        conflict_keys = {("2L", "2L6X6X1")}
        reason, match = classify("2L", "2L6X6X1", "2L6X6X1", full_clean, conflict_keys)
        self.assertEqual(reason, "excluded_conflict")

    def test_no_match_at_all_is_missing_from_raw_source(self):
        full_clean = {"W": ["W12X26"]}
        reason, match = classify("W", "W99X999", "W99X999", full_clean, set())
        self.assertEqual(reason, "missing_from_raw_source")


if __name__ == "__main__":
    unittest.main()
