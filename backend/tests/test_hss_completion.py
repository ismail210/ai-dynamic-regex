"""Catalog-constrained HSS missing-thickness completion tests."""

from __future__ import annotations

import unittest

from services.hss_completion import (
    detect_missing_thickness_hss,
    hss_completion_candidates,
)


class DetectMissingThicknessTests(unittest.TestCase):
    def test_missing_thickness_detected(self):
        self.assertEqual(detect_missing_thickness_hss("HSS10x10"), ("10", "10"))
        self.assertEqual(detect_missing_thickness_hss("HSS8X8"), ("8", "8"))

    def test_swapped_dimension_order_preserved_as_read(self):
        self.assertEqual(detect_missing_thickness_hss("HSS6X8"), ("6", "8"))

    def test_complete_designation_is_not_missing(self):
        self.assertIsNone(detect_missing_thickness_hss("HSS10X10X1/2"))

    def test_corrupted_dimension_is_not_missing(self):
        """A wildcard/garbled dimension is a different problem (corrupted,
        not missing) and must not be handled by this path."""

        self.assertIsNone(detect_missing_thickness_hss("HSS10X?"))
        self.assertIsNone(detect_missing_thickness_hss("HSS10X10X?"))

    def test_non_hss_family_ignored(self):
        self.assertIsNone(detect_missing_thickness_hss("W16X26"))

    def test_bare_family_ignored(self):
        self.assertIsNone(detect_missing_thickness_hss("HSS"))


class CompletionCandidatesTests(unittest.TestCase):
    def test_hss10x10_returns_only_hss10x10_candidates(self):
        candidates = hss_completion_candidates("10", "10")
        designations = [c.designation for c in candidates]
        self.assertGreater(len(designations), 1)
        for d in designations:
            self.assertTrue(d.startswith("HSS10X10X"), d)

    def test_hss8x8_regression_never_drifts_to_8x6(self):
        """Direct regression for the real failure: HSS8X8 completing to
        HSS8X6X3/8 (a different, smaller cross-section) must be impossible
        once the pool is catalog-constrained by both known dimensions."""

        candidates = hss_completion_candidates("8", "8")
        designations = [c.designation for c in candidates]
        self.assertIn("HSS8X8X3/8", designations)
        self.assertNotIn("HSS8X6X3/8", designations)
        for d in designations:
            self.assertTrue(d.startswith("HSS8X8X"), d)

    def test_swapped_order_canonicalizes_to_catalog_orientation(self):
        """AISC stores rectangular HSS with the larger dimension first; a
        read of HSS6X8 must resolve to the catalog's HSS8X6X* family, not
        be silently discarded."""

        candidates = hss_completion_candidates("6", "8")
        designations = [c.designation for c in candidates]
        self.assertGreater(len(designations), 0)
        for d in designations:
            self.assertTrue(d.startswith("HSS8X6X"), d)

    def test_unknown_pair_returns_no_candidates(self):
        self.assertEqual(hss_completion_candidates("99", "99"), [])

    def test_round_hss_pair_returns_no_rect_candidates(self):
        """HSS16X0.5 is an already-complete round designation (OD x wall),
        not a missing-thickness rectangular pair; it must not be coerced
        into a fabricated rectangular completion."""

        self.assertEqual(hss_completion_candidates("16", "0.5"), [])

    def test_candidates_sorted_by_thickness_ascending(self):
        candidates = hss_completion_candidates("10", "10")
        values = [c.thickness_value for c in candidates]
        self.assertEqual(values, sorted(values))

    def test_every_candidate_is_a_real_catalog_label(self):
        from services.database_loader import lookup_shape

        for c in hss_completion_candidates("12", "12"):
            self.assertIsNotNone(lookup_shape(c.designation), c.designation)


if __name__ == "__main__":
    unittest.main()
