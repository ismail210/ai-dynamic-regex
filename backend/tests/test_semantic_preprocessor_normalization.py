"""Deterministic normalization tests (Section 42) -- the HSS rect vs round
branch is the single highest-risk correctness requirement in this package.
"""
from __future__ import annotations

import unittest

from services.semantic_preprocessor.models import OP_NONE, OP_NORMALIZATION
from services.semantic_preprocessor.normalization import canonicalize


class HssRectangularFractionConversionTests(unittest.TestCase):
    def test_decimal_thickness_converts_to_fraction(self):
        result = canonicalize("HSS 8X8X0.375")
        self.assertEqual(result.correction.canonical, "HSS8X8X3/8")
        self.assertEqual(result.correction.operation, OP_NORMALIZATION)
        self.assertTrue(result.correction.auto_accept)

    def test_spaced_x_and_decimal(self):
        result = canonicalize("HSS8 X 8 X .375")
        self.assertEqual(result.correction.canonical, "HSS8X8X3/8")

    def test_spaced_fraction_with_slash(self):
        result = canonicalize("HSS 8 x 8 x 3 / 8")
        self.assertEqual(result.correction.canonical, "HSS8X8X3/8")

    def test_already_bare_decimal(self):
        result = canonicalize("HSS8X8X.375")
        self.assertEqual(result.correction.canonical, "HSS8X8X3/8")


class RoundHssMustStayDecimalTests(unittest.TestCase):
    def test_round_hss_is_never_fraction_converted(self):
        result = canonicalize("HSS5.563X0.258")
        self.assertEqual(result.correction.canonical, "HSS5.563X0.258")
        self.assertEqual(result.correction.operation, OP_NONE)

    def test_round_hss_does_not_match_rectangular_grammar(self):
        from services.semantic_preprocessor.structural_parser import parse_structural_label
        parse = parse_structural_label("HSS5.563X0.258")
        self.assertEqual(parse.grammar, "hss_round")


class UnchangedDecimalWeightDesignationsTests(unittest.TestCase):
    def test_channel_weight_is_untouched(self):
        result = canonicalize("C8X11.5")
        self.assertEqual(result.correction.canonical, "C8X11.5")
        self.assertEqual(result.correction.operation, OP_NONE)

    def test_misc_channel_weight_is_untouched(self):
        result = canonicalize("MC10X8.4")
        self.assertEqual(result.correction.canonical, "MC10X8.4")
        self.assertEqual(result.correction.operation, OP_NONE)


class ArchitecturalDimensionTests(unittest.TestCase):
    def test_feet_inches_dimension_is_never_touched(self):
        result = canonicalize("3'4\"")
        self.assertFalse(result.parse.is_structural)
        self.assertEqual(result.correction.operation, OP_NONE)
        self.assertEqual(result.correction.canonical, "3'4\"")


class RepairBoundaryTests(unittest.TestCase):
    def test_ocr_corruption_is_not_deterministic_normalization(self):
        result = canonicalize("W8XI0")
        self.assertNotEqual(result.correction.operation, OP_NORMALIZATION)

    def test_ocr_corruption_never_auto_accepts(self):
        result = canonicalize("W8XI0")
        self.assertFalse(result.correction.auto_accept)


class CompletionBoundaryTests(unittest.TestCase):
    def test_bare_family_shorthand_is_not_completed_here(self):
        result = canonicalize("W8")
        self.assertTrue(result.parse.is_structural)
        self.assertEqual(result.parse.grammar, "incomplete")
        self.assertEqual(result.correction.operation, OP_NONE)
        self.assertEqual(result.correction.canonical, "W8")


if __name__ == "__main__":
    unittest.main()
