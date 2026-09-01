"""Safety tests for production-aligned reconstruction training data."""

from __future__ import annotations

import unittest

from scripts.generate_label_reconstruction_production_aligned import (
    _decision_for,
    build_pairwise_rows,
)


class ProductionDecisionAlignmentTests(unittest.TestCase):
    def test_incomplete_angle_is_not_ranked(self) -> None:
        for query in ("L6x3", "L5x3", "L4x4", "2L4x4"):
            with self.subTest(query=query):
                decision, candidate_set = _decision_for(query, None)
                self.assertEqual(decision, "abstain_missing_thickness")
                if query == "L6x3":
                    # Catalog has L6X3-1/2..., not L6X3x... — do not invent L6X6.
                    self.assertEqual(candidate_set.candidates, [])
                    continue
                self.assertTrue(candidate_set.candidates)
                if query.startswith("2L"):
                    self.assertTrue(
                        all(
                            candidate.startswith("2L4X4")
                            for candidate in candidate_set.candidates
                        )
                    )
                else:
                    prefix = candidate_set.normalized + "X"
                    self.assertTrue(
                        all(
                            candidate.startswith(prefix)
                            for candidate in candidate_set.candidates
                        )
                    )

    def test_spacing_suffix_does_not_glue_weight(self) -> None:
        decision, candidate_set = _decision_for("W12x19@5'", "W12X19")
        self.assertEqual(decision, "exact_match")
        self.assertEqual(candidate_set.candidates, ["W12X19"])

    def test_invalid_hss6x8_does_not_inject_hss16(self) -> None:
        decision, candidate_set = _decision_for(
            "HSS6X8X1/2", "HSS16X8X1/2"
        )
        self.assertEqual(decision, "abstain_no_valid_candidate")
        self.assertEqual(candidate_set.candidates, [])

    def test_plates_and_anonymous_dimensions_are_ineligible(self) -> None:
        for query in (
            'PL 3 3/4"',
            'PLATE 3 3/8"',
            'CAP PL 3/8"',
            'CONN PL 1/2"',
            'BP 3/8"',
            'BENT PLATE 1/2"',
            '3/16"',
            '5/16".',
            '2"x4"x1/4"',
            '2"x2"x1/4"',
            '1/2"x1/4"',
            '1/4"x2"',
            '1/2"⌀x6"',
            '1/8"x1"',
            "4x4",
            "3/4X4X6",
            '1-1/2"',
            '14-2".',
            '1/2"x5/16"ANGLE',
            '1-1/2",',
            '1-1/4"Ø',
            'x12"',
            '(14"x52")',
            '(20"x52")',
            '(24"x30")',
            '(L52"x52"x14"T)',
            "6x6-W1.4xW1.4",
            "[6 x 6",
        ):
            with self.subTest(query=query):
                decision, candidate_set = _decision_for(query, None)
                self.assertEqual(decision, "abstain_ineligible")
                self.assertEqual(candidate_set.candidates, [])

    def test_exact_labels_bypass_ranking(self) -> None:
        for label in ("W16X26", "HSS8X8X1/2"):
            with self.subTest(label=label):
                decision, candidate_set = _decision_for(label, label)
                self.assertEqual(decision, "exact_match")
                self.assertEqual(candidate_set.candidates, [label])


class PairwiseConsistencyTests(unittest.TestCase):
    def test_only_rank_decisions_create_pairwise_rows(self) -> None:
        pointwise = [
            {
                "query": "W16X2?",
                "normalized_query": "W16X2?",
                "clean_designation": "W16X26",
                "family": "W",
                "source_designation_id": "W16X26",
                "designation_holdout": False,
                "corruption_type": ["unknown_char_single"],
                "corruption_severity": 1,
                "split": "train",
                "expected_decision": "rank",
                "candidate_labels": ["W16X26", "W16X24"],
                "generation_reasons": {
                    "W16X26": ["structural_field_match"],
                    "W16X24": ["structural_field_match"],
                },
                "fuzzy_ranks": {},
            },
            {
                "query": "HSS8X8",
                "normalized_query": "HSS8X8",
                "clean_designation": None,
                "family": "HSS",
                "source_designation_id": None,
                "designation_holdout": False,
                "corruption_type": ["production_safety_fixture"],
                "corruption_severity": 0,
                "split": "test",
                "expected_decision": "abstain_missing_thickness",
                "candidate_labels": ["HSS8X8X1/2"],
                "generation_reasons": {
                    "HSS8X8X1/2": ["structural_field_match"]
                },
                "fuzzy_ranks": {},
            },
        ]
        pairwise = build_pairwise_rows(pointwise)
        self.assertEqual(len(pairwise), 2)
        self.assertEqual(
            [(row["candidate"], row["target"]) for row in pairwise],
            [("W16X26", 1), ("W16X24", 0)],
        )
        self.assertTrue(all(row["query"] == "W16X2?" for row in pairwise))


if __name__ == "__main__":
    unittest.main()
