"""Tests for backfilling missing-thickness HSS fields on cached predictions."""

from __future__ import annotations

import unittest

from services.prediction.hss_review_enrichment import (
    enrich_missing_thickness_hss_predictions,
)


def _stale_hss8x8_prediction() -> dict:
    """Simulate a pre-HSS-completion cached row with a fusion thickness guess."""

    return {
        "object_id": "obj-hss8x8",
        "raw_text": "HSS8x8",
        "original_token": "HSS8x8",
        "corrected_token": "HSS8X8",
        "normalized_text": "HSS8X8",
        "section": "HSS8X8X3/16",
        "needs_review": True,
        "review_reason": (
            "Two or more candidates are near-tied; automatic selection is not reliable enough."
        ),
        "canonical": {
            "prediction": {"final_label": "HSS8X8X3/16", "family": "HSS"},
            "comparison": {
                "match_status": "corrected_prediction",
                "exact_match": False,
                "normalized_match": True,
            },
            "needs_review": True,
        },
        "comparison": {
            "match_status": "corrected_prediction",
            "exact_match": False,
            "normalized_match": True,
        },
    }


class HssReviewEnrichmentTests(unittest.TestCase):
    def test_stale_cache_gains_catalog_candidates(self):
        enriched = enrich_missing_thickness_hss_predictions(
            [_stale_hss8x8_prediction()]
        )[0]
        candidates = enriched["candidate_sections"]
        self.assertGreater(len(candidates), 1)
        for item in candidates:
            self.assertTrue(item["designation"].startswith("HSS8X8X"), item)

    def test_stale_cache_clears_fusion_final_label(self):
        enriched = enrich_missing_thickness_hss_predictions(
            [_stale_hss8x8_prediction()]
        )[0]
        self.assertEqual(enriched["completion_status"], "missing_thickness")
        self.assertEqual(enriched["known_dimensions"], ["8", "8"])
        self.assertIsNone(enriched["canonical"]["prediction"]["final_label"])
        self.assertEqual(
            enriched["canonical"]["comparison"]["match_status"],
            "missing_dimension_field",
        )

    def test_complete_designation_left_untouched(self):
        complete = {
            "raw_text": "HSS8X8X3/16",
            "corrected_token": "HSS8X8X3/16",
            "section": "HSS8X8X3/16",
            "canonical": {
                "prediction": {"final_label": "HSS8X8X3/16"},
                "comparison": {"match_status": "exact_match"},
            },
        }
        enriched = enrich_missing_thickness_hss_predictions([complete])[0]
        self.assertNotIn("candidate_sections", enriched)


if __name__ == "__main__":
    unittest.main()
