"""Structural section parser tests."""

from __future__ import annotations

import unittest

from services.section_parser import (
    ocr_edit_cost,
    parse_section,
    plausible_against_ocr,
)


class ParseSectionTests(unittest.TestCase):
    def test_parses_w_shape(self):
        parsed = parse_section("W12 X 26")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.family, "W")
        self.assertEqual(parsed.depth, 12.0)
        self.assertEqual(parsed.weight, 26.0)
        self.assertEqual(parsed.normalized, "W12X26")
        self.assertTrue(parsed.catalog_valid)

    def test_parses_hss_with_thickness(self):
        parsed = parse_section("HSS6X6X1/2")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.family, "HSS")
        self.assertEqual(parsed.depth, 6.0)
        self.assertEqual(parsed.weight, 6.0)
        self.assertEqual(parsed.thickness, "1/2")

    def test_unknown_family_returns_none(self):
        self.assertIsNone(parse_section("ZZ4X4"))

    def test_round_hss_decimal_depth_and_weight_not_truncated(self):
        # Real catalog label (services.database_loader): round HSS store
        # diameter/wall as decimals. `_DEPTH_RE`/`_WEIGHT_RE` used to match
        # digits only, so "28.000X1.000" parsed as depth=28.0, weight=0.0 —
        # truncated at the decimal point instead of reading the real value.
        parsed = parse_section("HSS28.000X1.000")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.family, "HSS")
        self.assertEqual(parsed.depth, 28.0)
        self.assertEqual(parsed.weight, 1.0)
        self.assertTrue(parsed.catalog_valid)

    def test_round_hss_decimal_with_fractional_wall_not_truncated(self):
        parsed = parse_section("HSS10.750X0.188")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.depth, 10.75)
        self.assertEqual(parsed.weight, 0.188)

    def test_pipe_decimal_depth_not_truncated(self):
        parsed = parse_section("PIPE10.750X0.188")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.family, "PIPE")
        self.assertEqual(parsed.depth, 10.75)


class OcrEditCostTests(unittest.TestCase):
    def test_identical_is_zero(self):
        self.assertEqual(ocr_edit_cost("W12X26", "W12X26"), 0.0)

    def test_near_free_ocr_confusion(self):
        self.assertLess(ocr_edit_cost("W12X20", "W12X2O"), 1.0)

    def test_digit_swap_is_expensive(self):
        near = ocr_edit_cost("W12X20", "W12X2O")
        digit = ocr_edit_cost("W12X26", "W12X62")
        self.assertGreater(digit, near)


class PlausibilityTests(unittest.TestCase):
    def test_same_family_and_depth(self):
        self.assertTrue(plausible_against_ocr("W12X26", "W12X22"))

    def test_rejects_different_family(self):
        self.assertFalse(plausible_against_ocr("HSS6X6X1/2", "W12X26"))

    def test_rejects_different_depth(self):
        self.assertFalse(plausible_against_ocr("W14X26", "W12X26"))

    def test_empty_ocr_allows_candidate(self):
        self.assertTrue(plausible_against_ocr("W12X26", ""))

    def test_w_shape_weight_mismatch_still_tolerated(self):
        """Weight-per-foot is the OCR-uncertain digit for W/S/M/C; only depth
        is a hard constraint there (unlike HSS/angle second dimensions)."""

        self.assertTrue(plausible_against_ocr("W12X26", "W12X22"))

    def test_hss_rejects_wrong_second_dimension(self):
        """Both HSS outside dimensions are read directly from the text and
        are equally certain; HSS8X8 must not accept an HSS8X6 candidate."""

        self.assertFalse(plausible_against_ocr("HSS8X6X3/8", "HSS8X8"))

    def test_hss_accepts_matching_second_dimension(self):
        self.assertTrue(plausible_against_ocr("HSS8X8X3/8", "HSS8X8"))

    def test_hss_missing_thickness_still_unconstrained_on_thickness(self):
        """Depth and width known from OCR must match; thickness — never
        present in the OCR text — is not a constraint here at all."""

        self.assertTrue(plausible_against_ocr("HSS10X10X1/2", "HSS10X10"))
        self.assertTrue(plausible_against_ocr("HSS10X10X5/16", "HSS10X10"))

    def test_angle_rejects_wrong_second_dimension(self):
        self.assertFalse(plausible_against_ocr("L6X4X5/16", "L6X6"))

    def test_hss_second_dimension_unconstrained_when_ocr_only_gives_one(self):
        """A bare depth-only OCR read (no second dimension at all) must stay
        unconstrained on width, same as it already is for thickness."""

        self.assertTrue(plausible_against_ocr("HSS8X6X3/8", "HSS8"))


if __name__ == "__main__":
    unittest.main()
