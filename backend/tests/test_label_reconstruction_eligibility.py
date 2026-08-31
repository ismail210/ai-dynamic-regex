"""Safety boundary between dimensions and rolled-section reconstruction."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from config import settings
from services.annotation.parser import interpret_annotation
from services.label_reconstruction.candidates import (
    conservative_normalize,
    generate_candidates,
    ineligible_for_section_reconstruction,
)
from services.label_reconstruction.shadow import reconstruct


DIMENSION_ONLY_QUERIES = (
    '2"x4"x1/4"',
    '2"x2"x1/4"',
    '1/2"x1/4"',
    '1/4"x2"',
    '1/2"⌀x6"',
    '1/8"x1"',
    '5/16"',
    '3/16"',
    'PL 3 3/4"',
    'PLATE 3 3/8"',
    'CAP PL 3/8"',
    'CONN PL 1/2"',
)


class AnonymousDimensionEligibilityTests(unittest.TestCase):
    def test_dimension_only_queries_are_ineligible_and_have_no_candidates(self) -> None:
        for query in DIMENSION_ONLY_QUERIES:
            with self.subTest(query=query):
                normalized = conservative_normalize(query)
                self.assertTrue(
                    ineligible_for_section_reconstruction(query, normalized)
                )
                self.assertEqual(generate_candidates(query).candidates, [])
                result = reconstruct(query)
                self.assertIsNone(result.selected_prediction)
                self.assertEqual(result.candidate_labels, [])
                self.assertEqual(result.reason, "no_candidates")

    def test_familyless_compounds_follow_existing_dimension_parser_semantics(self) -> None:
        # These are intentionally not guessed into L/HSS/etc. without drawing
        # context.  The context resolver may assign plate/angle semantics
        # elsewhere, but generic rolled-section reconstruction must abstain.
        for query in ("4x4", "3/4X4X6"):
            with self.subTest(query=query):
                parsed = interpret_annotation(
                    raw_text=query,
                    normalized_text=conservative_normalize(query),
                )
                self.assertEqual(parsed.annotation_type, "DIMENSION")
                self.assertFalse(parsed.structure_confirmed)
                self.assertTrue(ineligible_for_section_reconstruction(query))
                self.assertEqual(generate_candidates(query).candidates, [])

    def test_shadow_never_loads_ranker_for_ineligible_dimensions(self) -> None:
        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker"
            ) as get_ranker:
                for query in DIMENSION_ONLY_QUERIES + ("4x4", "3/4X4X6"):
                    with self.subTest(query=query):
                        result = reconstruct(query)
                        self.assertIsNone(result.selected_prediction)
                        self.assertIsNone(result.shadow)
                        self.assertEqual(result.candidate_labels, [])
            get_ranker.assert_not_called()
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)


class DamagedSectionPreservationTests(unittest.TestCase):
    def test_explicit_section_families_remain_eligible(self) -> None:
        queries = (
            "W16X26",
            "HSS8X8X1/2",
            "HSS8X8",
            "HSS6X8X1/2",
            "L4X4X5/16",
            "2L8X4X5/8X3/8LLBB",
            "PIPE6STD",
            "W??X?7",
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertFalse(ineligible_for_section_reconstruction(query))

    def test_damaged_family_letters_are_not_mistaken_for_dimensions(self) -> None:
        # Existing corruption data contains labels whose family prefix gained
        # an OCR character.  They retain alphabetic section evidence and are
        # distinct from numeric-only anonymous dimensions.
        for query in ("ZL10X10X1", "F2L10X10X1", "I0X10X11/8X1-1/2"):
            with self.subTest(query=query):
                self.assertFalse(ineligible_for_section_reconstruction(query))
                self.assertTrue(generate_candidates(query).candidates)

    def test_valid_and_damaged_section_behavior_is_preserved(self) -> None:
        self.assertEqual(reconstruct("W16X26").selected_prediction, "W16X26")
        self.assertEqual(
            reconstruct("HSS8X8X1/2").selected_prediction,
            "HSS8X8X1/2",
        )
        self.assertIsNone(reconstruct("HSS8X8").selected_prediction)
        self.assertIsNone(reconstruct("HSS6X8X1/2").selected_prediction)
        self.assertEqual(
            reconstruct("L4X4X5/16").selected_prediction,
            "L4X4X5/16",
        )
        self.assertIn(
            "2L8X4X5/8X3/8LLBB",
            generate_candidates("2L8X4X5/8X3/8LLBB").candidates,
        )
        self.assertIn("PIPE6STD", generate_candidates("PIPE6STD").candidates)
        wildcard_candidates = generate_candidates("W??X?7").candidates
        self.assertTrue(wildcard_candidates)
        self.assertTrue(all(not label.startswith("WT") for label in wildcard_candidates))


if __name__ == "__main__":
    unittest.main()
