"""Section 36 status-tag scenario coverage for
services.prediction.status_classification.classify_prediction_status.

Each test name states the exact scenario from the task brief so the mapping
is directly traceable back to the brief's own requirements.
"""

from __future__ import annotations

import unittest

from services.prediction.status_classification import classify_prediction_status


def _pred(match_status, **extra):
    return {
        "comparison": {"match_status": match_status},
        **extra,
    }


class StatusClassificationTests(unittest.TestCase):
    def test_w18x35_exact_is_perfect_match_only(self):
        tags = classify_prediction_status(_pred("exact_match"))
        self.assertEqual(tags, {"perfect_match"})

    def test_lowercase_w18x35_normalized_is_formatting_only(self):
        tags = classify_prediction_status(_pred("normalized_match"))
        self.assertEqual(tags, {"formatting_only"})

    def test_hss8x4_deterministic_project_rule_is_project_rule_only(self):
        tags = classify_prediction_status(
            _pred(
                "project_rule_resolved",
                project_rule_resolution={"extraction_method": "deterministic"},
            )
        )
        self.assertEqual(tags, {"project_rule"})

    def test_hss8x4_llm_assisted_project_rule_is_both_tags(self):
        tags = classify_prediction_status(
            _pred(
                "project_rule_resolved",
                project_rule_resolution={"extraction_method": "llm_assisted"},
            )
        )
        self.assertEqual(tags, {"project_rule", "llm_assisted"})

    def test_unresolved_hss8x4_is_needs_review_and_unresolved(self):
        tags = classify_prediction_status(_pred("unresolved", needs_review=True))
        self.assertEqual(tags, {"needs_review", "unresolved"})

    def test_missing_dimension_is_needs_review_with_specific_tag(self):
        tags = classify_prediction_status(_pred("missing_dimension_field", needs_review=True))
        self.assertEqual(tags, {"needs_review", "missing_dimension"})

    def test_low_confidence_inferred_prediction_is_low_confidence(self):
        tags = classify_prediction_status(_pred("corrected_prediction", confidence=0.4))
        self.assertIn("low_confidence", tags)
        self.assertIn("inferred", tags)

    def test_human_corrected_is_human_reviewed(self):
        tags = classify_prediction_status(_pred("human_resolved", decision_source="human_review"))
        self.assertEqual(tags, {"human_reviewed"})

    def test_project_rule_resolution_is_never_tagged_low_confidence(self):
        # Even with a stale/irrelevant low generic confidence score left over
        # from an earlier fusion pass, a verified project-rule resolution
        # must never be tagged low_confidence (task Section 17).
        tags = classify_prediction_status(
            _pred(
                "project_rule_resolved",
                confidence=0.0,
                project_rule_resolution={"extraction_method": "deterministic"},
            )
        )
        self.assertNotIn("low_confidence", tags)

    def test_perfect_match_is_never_tagged_low_confidence(self):
        tags = classify_prediction_status(_pred("exact_match", confidence=0.0))
        self.assertNotIn("low_confidence", tags)

    def test_canonical_match_status_takes_precedence_over_top_level(self):
        pred = {
            "comparison": {"match_status": "missing_dimension_field"},
            "canonical": {"comparison": {"match_status": "exact_match"}},
        }
        tags = classify_prediction_status(pred)
        self.assertEqual(tags, {"perfect_match"})

    def test_resolved_item_with_leftover_review_reason_is_a_warning(self):
        tags = classify_prediction_status(
            _pred("normalized_match", needs_review=False, review_reason="Graph/geometry association ambiguous")
        )
        self.assertIn("formatting_only", tags)
        self.assertIn("warning", tags)
        self.assertNotIn("needs_review", tags)

    def test_missing_status_degrades_to_needs_review_unresolved_never_raises(self):
        tags = classify_prediction_status({})
        self.assertEqual(tags, {"needs_review", "unresolved"})


if __name__ == "__main__":
    unittest.main()
