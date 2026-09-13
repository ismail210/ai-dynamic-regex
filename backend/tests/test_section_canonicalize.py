"""Accuracy Track A4 — deterministic family grammar / format-only canonicalize."""

from __future__ import annotations

import unittest

from services.prediction.section_canonicalize import (
    canonicalize_section_text,
    is_format_only_change,
    round_vs_rect_hss_class,
)


class SectionCanonicalizeTests(unittest.TestCase):
    def test_incomplete_l_unchanged(self):
        self.assertEqual(canonicalize_section_text("L4x4"), "L4X4")
        self.assertEqual(canonicalize_section_text("2L5X3"), "2L5X3")
        self.assertTrue(is_format_only_change("L4x4", "L4X4"))

    def test_times_and_spacing_format_only(self):
        raw = "W 16 × 26"
        canon = canonicalize_section_text(raw)
        self.assertTrue(is_format_only_change(raw, canon))
        self.assertEqual(canon.count("X"), 1)

    def test_round_vs_rect_hss(self):
        self.assertEqual(round_vs_rect_hss_class("HSS5.563X0.258"), "round")
        self.assertEqual(round_vs_rect_hss_class("HSS6X6X3/8"), "rectangular")
        self.assertIsNone(round_vs_rect_hss_class("W16X26"))

    def test_does_not_add_l_thickness(self):
        canon = canonicalize_section_text("L4X4")
        self.assertEqual(canon, "L4X4")
        self.assertFalse(canon.upper().count("X") >= 2)


if __name__ == "__main__":
    unittest.main()
