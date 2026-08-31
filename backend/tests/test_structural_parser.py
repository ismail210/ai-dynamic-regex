"""Tests for family-aware structural field parsing (v3 Part 3/4).

The central regression this guards is the HSS8X8X? -> HSS18X18X1 bug: a
fuzzy string-similarity ranker preferring a completely different HSS size
because "HSS18X18X1" happens to share characters with "HSS8X8X?", when the
depth/width fields make it structurally impossible.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.label_reconstruction.candidates import (  # noqa: E402
    generate_candidates,
    generate_candidates_v3,
)
from services.label_reconstruction.structural_parser import (  # noqa: E402
    AMBIGUITY_LARGE,
    AMBIGUITY_NO_MATCH,
    AMBIGUITY_SMALL,
    AMBIGUITY_UNIQUE,
    ambiguity_category,
    compatible_catalog_labels,
    field_compatible,
    generation_compatible_catalog_labels,
    parse_fields,
)


class ParseFieldsTests(unittest.TestCase):
    def test_w_shape_is_depth_weight(self) -> None:
        p = parse_fields("W18X35")
        self.assertTrue(p.ok)
        self.assertEqual(p.family, "W")
        self.assertEqual(p.grammar, "depth_weight")
        self.assertEqual(p.fields, ["18", "35"])

    def test_hss_rectangular_is_three_fields(self) -> None:
        p = parse_fields("HSS8X8X1/2")
        self.assertTrue(p.ok)
        self.assertEqual(p.grammar, "hss_rect")
        self.assertEqual(p.fields, ["8", "8", "1/2"])

    def test_hss_round_is_two_fields(self) -> None:
        p = parse_fields("HSS28.000X1.000")
        self.assertTrue(p.ok)
        self.assertEqual(p.grammar, "hss_round")
        self.assertEqual(p.fields, ["28.000", "1.000"])

    def test_pipe_has_no_x_delimiter(self) -> None:
        p = parse_fields("PIPE8STD")
        self.assertTrue(p.ok)
        self.assertEqual(p.fields, ["8", "STD"])

    def test_angle_is_three_fields(self) -> None:
        p = parse_fields("L6X6X9/16")
        self.assertTrue(p.ok)
        self.assertEqual(p.fields, ["6", "6", "9/16"])

    def test_double_angle_allows_three_or_four_fields(self) -> None:
        self.assertTrue(parse_fields("2L8X6X3/4").ok)
        self.assertTrue(parse_fields("2L8X6X3/4X1/2").ok)

    def test_separator_corruption_that_destroys_x_fails_to_parse(self) -> None:
        # "W18 35" is what generate_label_corruption_dataset's separator_space
        # corruption produces BEFORE conservative_normalize strips the space
        # entirely, collapsing the "X" delimiter -- this must report ok=False,
        # not silently guess a field split.
        p = parse_fields("W1835")
        self.assertFalse(p.ok)


class FieldCompatibleTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(field_compatible("35", "35"))

    def test_wildcard_position_matches_anything_same_length(self) -> None:
        self.assertTrue(field_compatible("3?", "35"))
        self.assertTrue(field_compatible("3?", "39"))
        self.assertFalse(field_compatible("3?", "45"))

    def test_different_length_never_compatible(self) -> None:
        self.assertFalse(field_compatible("3?", "130"))
        self.assertFalse(field_compatible("?", "1/2"))


class AmbiguityCategoryTests(unittest.TestCase):
    def test_w18x3_question_is_unique(self) -> None:
        compat = compatible_catalog_labels("W18X3?")
        self.assertEqual(compat, ["W18X35"])
        self.assertEqual(ambiguity_category(len(compat)), AMBIGUITY_UNIQUE)

    def test_w18x_double_star_is_large_ambiguous(self) -> None:
        compat = compatible_catalog_labels("W18X**")
        self.assertGreater(len(compat), 5)
        self.assertEqual(ambiguity_category(len(compat)), AMBIGUITY_LARGE)

    def test_w44x3_double_star_is_small_ambiguous(self) -> None:
        compat = compatible_catalog_labels("W44X3**")
        self.assertIn(len(compat), range(2, 6))
        self.assertEqual(ambiguity_category(len(compat)), AMBIGUITY_SMALL)
        self.assertNotIn("W44X230", compat)  # weight must start with 3

    def test_ocr_garbled_query_has_no_exact_structural_match(self) -> None:
        # "W1BX3S" -- letters in numeric fields never literally match any
        # catalog field; this is exactly the case that needs OCR-aware
        # fuzzy recovery, not literal structural matching.
        compat = compatible_catalog_labels("W1BX3S")
        self.assertEqual(compat, [])
        self.assertEqual(ambiguity_category(len(compat)), AMBIGUITY_NO_MATCH)


class GenerationCompatibleFixesHssBugTests(unittest.TestCase):
    def test_hss8x8_single_wildcard_thickness_only_returns_hss8x8_entries(self) -> None:
        candidates = generation_compatible_catalog_labels("HSS8X8X?")
        self.assertTrue(candidates)
        for label in candidates:
            self.assertTrue(label.startswith("HSS8X8X"))
        self.assertNotIn("HSS18X18X1", candidates)

    def test_partially_known_field_still_requires_exact_length(self) -> None:
        # "3?" is NOT all-wildcard, so generation must still respect length.
        candidates = generation_compatible_catalog_labels("W18X3?")
        self.assertEqual(candidates, ["W18X35"])


class V3CandidateOrderingFixesHssBugTests(unittest.TestCase):
    def test_v2_no_longer_ranks_wrong_hss_size_first(self) -> None:
        v2 = generate_candidates("HSS8X8X?", limit=8)
        self.assertTrue(v2.candidates)
        self.assertTrue(v2.candidates[0].startswith("HSS8X8X"))
        self.assertNotIn("HSS18X18X1", v2.candidates)

    def test_v3_ranks_correct_hss8x8_family_first(self) -> None:
        v3 = generate_candidates_v3("HSS8X8X?", limit=8)
        self.assertTrue(v3.candidates[0].startswith("HSS8X8X"))
        self.assertNotIn("HSS18X18X1", v3.candidates)
        self.assertEqual(
            v3.generation_reasons["HSS8X8X1/2"], ["structural_field_match"]
        )


if __name__ == "__main__":
    unittest.main()
