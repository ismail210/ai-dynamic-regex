"""Deterministic normalization tests (Section 42) -- the HSS rect vs round
branch is the single highest-risk correctness requirement in this package.
"""
from __future__ import annotations

import unittest

from services.semantic.models import OperationKind
from services.semantic_preprocessor.normalization import canonicalize, format_designation_for_pdf


class HssRectangularFractionConversionTests(unittest.TestCase):
    def test_decimal_thickness_converts_to_fraction(self):
        result = canonicalize("HSS 8X8X0.375")
        self.assertEqual(result.operation.output_text, "HSS8X8X3/8")
        self.assertEqual(result.operation.operation, OperationKind.NORMALIZATION)
        self.assertTrue(result.operation.deterministic)
        self.assertTrue(result.operation.accepted)

    def test_spaced_x_and_decimal(self):
        result = canonicalize("HSS8 X 8 X .375")
        self.assertEqual(result.operation.output_text, "HSS8X8X3/8")

    def test_spaced_fraction_with_slash(self):
        result = canonicalize("HSS 8 x 8 x 3 / 8")
        self.assertEqual(result.operation.output_text, "HSS8X8X3/8")

    def test_already_bare_decimal(self):
        result = canonicalize("HSS8X8X.375")
        self.assertEqual(result.operation.output_text, "HSS8X8X3/8")


class RoundHssMustStayDecimalTests(unittest.TestCase):
    def test_round_hss_is_never_fraction_converted(self):
        result = canonicalize("HSS5.563X0.258")
        self.assertEqual(result.operation.output_text, "HSS5.563X0.258")
        self.assertEqual(result.operation.operation, OperationKind.KEEP)

    def test_round_hss_does_not_match_rectangular_grammar(self):
        from services.semantic_preprocessor.structural_parser import parse_structural_label
        parse = parse_structural_label("HSS5.563X0.258")
        self.assertEqual(parse.grammar, "hss_round")


class UnchangedDecimalWeightDesignationsTests(unittest.TestCase):
    def test_channel_weight_is_untouched(self):
        result = canonicalize("C8X11.5")
        self.assertEqual(result.operation.output_text, "C8X11.5")
        self.assertEqual(result.operation.operation, OperationKind.KEEP)

    def test_misc_channel_weight_is_untouched(self):
        result = canonicalize("MC10X8.4")
        self.assertEqual(result.operation.output_text, "MC10X8.4")
        self.assertEqual(result.operation.operation, OperationKind.KEEP)


class ArchitecturalDimensionTests(unittest.TestCase):
    def test_feet_inches_dimension_is_never_touched(self):
        result = canonicalize("3'4\"")
        self.assertFalse(result.parse.is_structural)
        self.assertEqual(result.operation.operation, OperationKind.KEEP)
        self.assertEqual(result.operation.output_text, "3'4\"")


class RepairBoundaryTests(unittest.TestCase):
    def test_ocr_corruption_is_not_deterministic_normalization(self):
        result = canonicalize("W8XI0")
        self.assertNotEqual(result.operation.operation, OperationKind.NORMALIZATION)
        self.assertEqual(result.operation.operation, OperationKind.REPAIR)

    def test_ocr_corruption_never_auto_accepts(self):
        """A repair is never silently applied without review -- expressed at
        the pipeline level (see _combine_review_status), since a bare
        canonicalize() call has no review-status concept of its own."""
        from services.semantic_preprocessor.pipeline import _combine_review_status
        from services.semantic.models import ReviewStatus, SemanticAnnotation

        result = canonicalize("W8XI0")
        ann = SemanticAnnotation(annotation_id="a", original_text="W8XI0", operations=[result.operation])
        self.assertEqual(_combine_review_status(ann), ReviewStatus.NEEDS_REVIEW)
        self.assertEqual(result.operation.score, None)  # uncalibrated, never fabricated


class CompletionBoundaryTests(unittest.TestCase):
    def test_bare_family_shorthand_is_not_completed_here(self):
        result = canonicalize("W8")
        self.assertTrue(result.parse.is_structural)
        self.assertEqual(result.parse.grammar, "incomplete")
        self.assertEqual(result.operation.operation, OperationKind.KEEP)
        self.assertEqual(result.operation.output_text, "W8")


class AngleFractionConversionTests(unittest.TestCase):
    def test_decimal_third_dimension_converts_to_fraction(self):
        result = canonicalize("L4X4X0.375")
        self.assertEqual(result.parse.grammar, "angle")
        self.assertEqual(result.operation.output_text, "L4X4X3/8")
        self.assertEqual(format_designation_for_pdf("L4X4X0.375"), "L4X4X3/8")

    def test_common_angle_thicknesses(self):
        cases = {
            "L4X4X0.25": "L4X4X1/4",
            "L3X3X0.3125": "L3X3X5/16",
            "L5X3X0.5": "L5X3X1/2",
            "2L4X4X0.375": "2L4X4X3/8",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(format_designation_for_pdf(raw), expected)

    def test_incomplete_angle_is_not_completed(self):
        # L4X4 parses as depth_weight (two-field L); never invent thickness.
        result = canonicalize("L4X4")
        self.assertEqual(result.operation.output_text, "L4X4")
        self.assertNotIn("1/4", result.operation.output_text or "")
        self.assertEqual(format_designation_for_pdf("L4X4"), "L4X4")

    def test_already_fractional_angle_unchanged(self):
        self.assertEqual(format_designation_for_pdf("L4X4X3/8"), "L4X4X3/8")


if __name__ == "__main__":
    unittest.main()
