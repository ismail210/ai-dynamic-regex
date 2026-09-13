"""Deterministic normalization tests (Section 42) -- the HSS rect vs round
branch is the single highest-risk correctness requirement in this package.
"""
from __future__ import annotations

import unittest

from services.semantic.models import OperationKind
from services.semantic_preprocessor.normalization import canonicalize


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


if __name__ == "__main__":
    unittest.main()
