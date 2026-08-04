"""Conservative normalization tests (Phase 3 / Phase 10 fixtures 1-3)."""

from __future__ import annotations

import unittest

from services.normalization import is_conservatively_equal, normalize_label_text


class ConservativeNormalizationTests(unittest.TestCase):
    def test_exact_text_normalizes_to_itself(self):
        result = normalize_label_text("W18X35")
        self.assertEqual(result.raw, "W18X35")
        self.assertEqual(result.normalized, "W18X35")

    def test_spacing_and_multiplication_separator_is_formatting_safe(self):
        result = normalize_label_text("W18 x 35")
        self.assertEqual(result.normalized, "W18X35")
        self.assertIn("uppercased", result.transformations)
        self.assertIn("whitespace_removed", result.transformations)

    def test_unicode_multiplication_sign_is_unified(self):
        result = normalize_label_text("W18×35")  # × (U+00D7)
        self.assertEqual(result.normalized, "W18X35")

    def test_ocr_style_substitution_is_not_normalization(self):
        # W18X3S must NOT normalize to W18X35 — S->5 is a correction
        # hypothesis, not a formatting-safe transformation.
        result = normalize_label_text("W18X3S")
        self.assertEqual(result.normalized, "W18X3S")
        self.assertNotEqual(result.normalized, "W18X35")

    def test_wildcard_characters_are_preserved(self):
        result = normalize_label_text("W44X3**")
        self.assertEqual(result.normalized, "W44X3**")

    def test_no_unknown_character_deletion(self):
        result = normalize_label_text("W18#X35")
        self.assertIn("#", result.normalized)

    def test_is_conservatively_equal(self):
        self.assertTrue(is_conservatively_equal("W18 x 35", "W18X35"))
        self.assertFalse(is_conservatively_equal("W18X3S", "W18X35"))
        self.assertFalse(is_conservatively_equal("", "W18X35"))


if __name__ == "__main__":
    unittest.main()
