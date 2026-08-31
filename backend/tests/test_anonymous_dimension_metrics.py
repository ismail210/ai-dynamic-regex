"""Tests for anonymous dimension metrics summarization."""

from services.annotation.anonymous_dimension_metrics import (
    summarize_anonymous_dimension_predictions,
)


def test_summarize_anonymous_dimension_predictions_counts():
    predictions = [
        {
            "engineering_object_type": "anonymous_dimension",
            "semantic_candidates": [{"type": "PLATE"}],
            "canonical": {
                "comparison": {"match_status": "needs_context"},
            },
        },
        {
            "engineering_object_type": "anonymous_dimension",
            "semantic_candidates": [{"type": "BENT_PLATE"}],
            "canonical": {
                "comparison": {"match_status": "confirmed_annotation"},
            },
        },
        {
            "engineering_object_type": "steel_section",
            "canonical": {"comparison": {"match_status": "exact_match"}},
        },
    ]
    metrics = summarize_anonymous_dimension_predictions(predictions)
    assert metrics["anonymous_dimension_count"] == 2
    assert metrics["needs_context_count"] == 1
    assert metrics["promoted_count"] == 1
    assert metrics["with_semantic_candidates_count"] == 2
    assert metrics["promotion_rate"] == 0.5
    assert metrics["abstention_rate"] == 0.5
