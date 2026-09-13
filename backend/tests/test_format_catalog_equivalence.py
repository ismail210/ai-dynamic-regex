"""Format-only catalog equivalence — never invents missing dimensions."""

from __future__ import annotations

import unittest

from services.database_loader import catalog_form
from services.exact_section_predictor import (
    catalog_valid_exact_section,
    normalize_section_text,
)
from services.prediction.label_ranker_hook import is_incomplete_angle_missing_thickness


class FormatCatalogEquivalenceTests(unittest.TestCase):
    def test_w_spacing_and_multiply_sign_variants(self) -> None:
        for raw in ("W8X10", "W8 x 10", "W 8 X 10", "W8×10", "w8x10"):
            with self.subTest(raw=raw):
                self.assertEqual(catalog_valid_exact_section(raw), "W8X10")
                self.assertEqual(catalog_form(raw) or catalog_form(normalize_section_text(raw)), "W8X10")

    def test_l_spacing_variants_complete(self) -> None:
        for raw in ("L4X4X1/4", "L4 x 4 x 1/4", "l4x4x1/4"):
            with self.subTest(raw=raw):
                self.assertEqual(catalog_valid_exact_section(raw), "L4X4X1/4")

    def test_complete_l_trailing_list_punct(self) -> None:
        self.assertEqual(catalog_valid_exact_section("L3X3X5/16,"), "L3X3X5/16")
        self.assertEqual(catalog_form("L4X4X5/16;"), "L4X4X5/16")
        self.assertFalse(is_incomplete_angle_missing_thickness("L3X3X5/16,"))

    def test_hss_decimal_equivalence(self) -> None:
        self.assertEqual(catalog_form("HSS10X0.625"), "HSS10.000X0.625")
        self.assertEqual(
            catalog_valid_exact_section("HSS10X0.625"), "HSS10.000X0.625"
        )

    def test_incomplete_l_not_catalog_completed(self) -> None:
        """Catalog existence of neighbors is NOT evidence for thickness."""

        self.assertEqual(catalog_form("L4X4"), "")
        self.assertIsNone(catalog_valid_exact_section("L4X4"))
        self.assertEqual(catalog_form("L4X4,"), "")
        self.assertIsNone(catalog_valid_exact_section("L4X4,"))
        self.assertTrue(is_incomplete_angle_missing_thickness("L4X4"))
        self.assertTrue(is_incomplete_angle_missing_thickness("L4X4,"))

    def test_non_catalog_not_invented(self) -> None:
        self.assertEqual(catalog_form("L2X2X10"), "")
        self.assertIsNone(catalog_valid_exact_section("L2X2X10"))
        self.assertEqual(catalog_form("NOTASHAPE"), "")
        # Complete-looking but non-catalog: not incomplete (has 3 fields) and
        # must not resolve to a different catalog angle via nearest-neighbor.
        self.assertFalse(is_incomplete_angle_missing_thickness("L2x2x10"))
        self.assertIsNone(catalog_valid_exact_section("L2x2x10"))

    def test_half_leg_complete_angle_not_incomplete(self) -> None:
        self.assertEqual(catalog_form("L5X3-1/2X5/16"), "L5X3-1/2X5/16")
        self.assertEqual(
            catalog_valid_exact_section("L5X3-1/2X5/16"), "L5X3-1/2X5/16"
        )
        self.assertFalse(is_incomplete_angle_missing_thickness("L5X3-1/2X5/16"))


if __name__ == "__main__":
    unittest.main()
