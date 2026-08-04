"""Transparent ranking-stage tests (Phase 6)."""

from __future__ import annotations

import unittest

from services.prediction.ranking import build_ranking
from services.wildcard_matcher import WildcardCandidate


class BuildRankingTests(unittest.TestCase):
    def test_merges_fusion_scores_with_catalog_validity(self):
        result = build_ranking(
            fusion_candidate_scores=[
                {
                    "shape": "W18X35",
                    "score": 0.91,
                    "modality_scores": {
                        "text": 0.9,
                        "geometry": 0.8,
                        "graph": 0.7,
                        "engineering_rules": 0.6,
                    },
                },
                {
                    "shape": "NOTASHAPE9999",
                    "score": 0.2,
                    "modality_scores": {"text": 0.2},
                },
            ]
        )
        by_label = {item.label: item for item in result.candidates}
        self.assertTrue(by_label["W18X35"].catalog_valid)
        self.assertFalse(by_label["NOTASHAPE9999"].catalog_valid)
        self.assertIn(
            "Label does not exist in the loaded AISC catalog",
            by_label["NOTASHAPE9999"].match_reasons,
        )
        self.assertEqual(result.weights.get("text"), 0.32)

    def test_wildcard_candidates_merge_into_existing_fusion_candidate(self):
        result = build_ranking(
            fusion_candidate_scores=[
                {
                    "shape": "W44X335",
                    "score": 0.5,
                    "modality_scores": {"text": 0.0, "geometry": 0.4},
                }
            ],
            wildcard_candidates=[
                WildcardCandidate(
                    label="W44X335",
                    catalog_type="W",
                    catalog_valid=True,
                    mask_match=True,
                    match_reasons=["Family W matches"],
                ),
                WildcardCandidate(
                    label="W44X368",
                    catalog_type="W",
                    catalog_valid=True,
                    mask_match=True,
                    match_reasons=["Family W matches"],
                ),
            ],
        )
        by_label = {item.label: item for item in result.candidates}
        self.assertTrue(by_label["W44X335"].mask_match)
        self.assertIn("Family W matches", by_label["W44X335"].match_reasons)
        # Wildcard-only candidate (no fusion score) still appears, zeroed.
        self.assertIn("W44X368", by_label)
        self.assertEqual(by_label["W44X368"].combined_score, 0.0)

    def test_near_tie_detection(self):
        result = build_ranking(
            fusion_candidate_scores=[
                {"shape": "W44X335", "score": 0.70, "modality_scores": {}},
                {"shape": "W44X368", "score": 0.69, "modality_scores": {}},
            ]
        )
        self.assertTrue(result.near_tie)
        self.assertAlmostEqual(result.near_tie_margin, 0.01, places=4)

    def test_clear_winner_is_not_a_near_tie(self):
        result = build_ranking(
            fusion_candidate_scores=[
                {"shape": "W44X335", "score": 0.95, "modality_scores": {}},
                {"shape": "W44X368", "score": 0.40, "modality_scores": {}},
            ]
        )
        self.assertFalse(result.near_tie)

    def test_empty_input_returns_no_candidates(self):
        result = build_ranking(fusion_candidate_scores=[])
        self.assertEqual(result.candidates, [])
        self.assertFalse(result.near_tie)


if __name__ == "__main__":
    unittest.main()
