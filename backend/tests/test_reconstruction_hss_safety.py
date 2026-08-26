"""Regression tests for reconstruction HSS field safety and eligibility."""

from __future__ import annotations

import unittest

from config import settings
from services.database_loader import is_catalog_label
from services.label_reconstruction.candidates import (
    conservative_normalize,
    generate_candidates,
)
from services.label_reconstruction.shadow import reconstruct
from services.label_reconstruction.structural_parser import (
    MISSING_FIELD,
    parse_fields,
)
from services.prediction.label_ranker_hook import apply_label_ranker_for_analyze


class HssTwoFieldParseTests(unittest.TestCase):
    def test_hss8x8_is_rect_with_missing_thickness(self) -> None:
        parsed = parse_fields("HSS8X8")
        self.assertTrue(parsed.ok)
        self.assertEqual(parsed.grammar, "hss_rect")
        self.assertEqual(parsed.fields, ["8", "8", MISSING_FIELD])

    def test_hss10x10_is_rect_with_missing_thickness(self) -> None:
        parsed = parse_fields("HSS10X10")
        self.assertEqual(parsed.fields, ["10", "10", MISSING_FIELD])

    def test_hss3x3_is_rect_with_missing_thickness(self) -> None:
        parsed = parse_fields("HSS3X3")
        self.assertEqual(parsed.fields, ["3", "3", MISSING_FIELD])

    def test_three_field_hss_unchanged(self) -> None:
        parsed = parse_fields("HSS6X8X1/2")
        self.assertEqual(parsed.grammar, "hss_rect")
        self.assertEqual(parsed.fields, ["6", "8", "1/2"])

    def test_round_hss_still_two_decimal_fields(self) -> None:
        parsed = parse_fields("HSS28.000X1.000")
        self.assertEqual(parsed.grammar, "hss_round")
        self.assertEqual(parsed.fields, ["28.000", "1.000"])


class HssCandidateSafetyTests(unittest.TestCase):
    def test_hss8x8_only_same_depth_width(self) -> None:
        cs = generate_candidates("HSS8x8")
        self.assertTrue(cs.candidates)
        for label in cs.candidates:
            self.assertTrue(label.startswith("HSS8X8X"))
        self.assertNotIn("HSS18X18X1", cs.candidates)
        self.assertNotIn("HSS10X10X1/2", cs.candidates)

    def test_hss6x8x1_2_abstains_when_absent(self) -> None:
        self.assertFalse(is_catalog_label("HSS6X8X1/2"))
        cs = generate_candidates("HSS6x8x1/2")
        self.assertEqual(cs.candidates, [])
        result = reconstruct("HSS6x8x1/2")
        self.assertIsNone(result.selected_prediction)
        self.assertEqual(result.reason, "no_candidates")
        self.assertNotEqual(result.selected_prediction, "HSS16X8X1/2")

    def test_repeated_hss_does_not_glue_88(self) -> None:
        self.assertEqual(conservative_normalize("HSS 8X8 8X8"), "HSS8X8")
        cs = generate_candidates("HSS 8X8 8X8")
        self.assertNotIn("HSS18X18X3/8", cs.candidates)
        for label in cs.candidates:
            self.assertTrue(label.startswith("HSS8X8X"))

    def test_missing_thickness_is_not_unique_selection(self) -> None:
        for raw in ("HSS8x8", "HSS10x10", "HSS3x3"):
            with self.subTest(raw=raw):
                result = reconstruct(raw)
                self.assertIsNone(result.selected_prediction)
                self.assertEqual(result.reason, "no_candidates")
                self.assertTrue(result.candidate_labels)
                prefix = conservative_normalize(raw) + "X"
                for label in result.candidate_labels:
                    self.assertTrue(label.startswith(prefix))


class EligibilityTests(unittest.TestCase):
    def test_plates_and_anonymous_yield_no_rolled_candidates(self) -> None:
        for raw in (
            'PL 3 3/4"',
            'PLATE 3 3/8"',
            '3/16"',
            '5/16"',
            '5/16".',
        ):
            with self.subTest(raw=raw):
                cs = generate_candidates(raw)
                self.assertEqual(cs.candidates, [])
                result = reconstruct(raw)
                self.assertEqual(result.candidate_labels, [])
                self.assertIsNone(result.selected_prediction)
                self.assertEqual(result.reason, "no_candidates")


class ExactLabelAndHookTests(unittest.TestCase):
    def test_exact_w16x26_unchanged(self) -> None:
        result = reconstruct("W16X26")
        self.assertEqual(result.reason, "exact_match")
        self.assertEqual(result.selected_prediction, "W16X26")
        self.assertEqual(result.raw_text, "W16X26")

    def test_exact_hss8x8x1_2_unchanged(self) -> None:
        result = reconstruct("HSS8X8X1/2")
        self.assertEqual(result.reason, "exact_match")
        self.assertEqual(result.selected_prediction, "HSS8X8X1/2")

    def test_enabled_flag_remains_false_and_hook_does_not_apply(self) -> None:
        self.assertFalse(settings.ml_label_ranker_enabled)
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            meta = apply_label_ranker_for_analyze(
                raw_text="HSS8x8",
                live_section="HSS8X8X1/2",
            )
        finally:
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)
        self.assertTrue(meta["invoked"])
        self.assertFalse(meta["applied"])
        self.assertFalse(settings.ml_label_ranker_enabled)


if __name__ == "__main__":
    unittest.main()
