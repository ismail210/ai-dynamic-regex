"""
Regression tests for the standardized abstention-reason taxonomy
(accuracy sprint Phase 3).

review_status alone ("pending_review", "correction_suggested", ...) says
THAT a prediction needs review but not WHY. This adds one canonical reason
code — LOW_CONFIDENCE / INSUFFICIENT_EVIDENCE / MODAL_DISAGREEMENT /
OUT_OF_DISTRIBUTION / PIPELINE_FAILURE — on top of it.
"""

from __future__ import annotations

import unittest

from services.prediction.review_policy import (
    ABSTENTION_REASON_INSUFFICIENT_EVIDENCE,
    ABSTENTION_REASON_LOW_CONFIDENCE,
    ABSTENTION_REASON_MODAL_DISAGREEMENT,
    ABSTENTION_REASON_OUT_OF_DISTRIBUTION,
    ABSTENTION_REASON_PIPELINE_FAILURE,
    determine_abstention_reason,
)


class AbstentionReasonTests(unittest.TestCase):
    def test_auto_accepted_has_no_reason(self):
        reason = determine_abstention_reason(
            review_status="auto_accepted",
            confidence=0.95,
            issues=[],
            model_probability=0.95,
            database_verified=True,
            regex_matches=True,
        )
        self.assertIsNone(reason)

    def test_pipeline_error_takes_priority(self):
        reason = determine_abstention_reason(
            review_status="pending_review",
            confidence=0.9,  # even with otherwise-fine confidence
            issues=[],
            model_probability=0.9,
            database_verified=True,
            regex_matches=True,
            pipeline_error=True,
        )
        self.assertEqual(reason, ABSTENTION_REASON_PIPELINE_FAILURE)

    def test_protected_label_conflict_is_modal_disagreement(self):
        reason = determine_abstention_reason(
            review_status="pending_review",
            confidence=0.2,
            issues=["protected_label_conflict"],
            model_probability=0.2,
            database_verified=True,
            regex_matches=True,
            protected_label_conflict=True,
        )
        self.assertEqual(reason, ABSTENTION_REASON_MODAL_DISAGREEMENT)

    def test_two_conflict_issues_is_modal_disagreement(self):
        reason = determine_abstention_reason(
            review_status="pending_review",
            confidence=0.6,
            issues=["geometry_conflict", "graph_conflict"],
            model_probability=0.6,
            database_verified=True,
            regex_matches=True,
        )
        self.assertEqual(reason, ABSTENTION_REASON_MODAL_DISAGREEMENT)

    def test_retrieval_gate_failed_is_insufficient_evidence(self):
        reason = determine_abstention_reason(
            review_status="pending_review",
            confidence=0.0,
            issues=["retrieval_gate_failed"],
            model_probability=0.0,
            database_verified=False,
            regex_matches=False,
            retrieval_gate_failed=True,
        )
        self.assertEqual(reason, ABSTENTION_REASON_INSUFFICIENT_EVIDENCE)

    def test_unrecognized_text_is_out_of_distribution(self):
        reason = determine_abstention_reason(
            review_status="correction_suggested",
            confidence=0.5,
            issues=[],
            model_probability=0.5,
            database_verified=False,
            regex_matches=False,
        )
        self.assertEqual(reason, ABSTENTION_REASON_OUT_OF_DISTRIBUTION)

    def test_low_confidence_is_the_generic_fallback(self):
        reason = determine_abstention_reason(
            review_status="pending_review",
            confidence=0.3,
            issues=[],
            model_probability=0.3,
            database_verified=True,
            regex_matches=True,
        )
        self.assertEqual(reason, ABSTENTION_REASON_LOW_CONFIDENCE)


if __name__ == "__main__":
    unittest.main()
