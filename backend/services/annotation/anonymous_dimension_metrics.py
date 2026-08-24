"""Metrics helpers for anonymous-dimension contextual inference."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def summarize_anonymous_dimension_predictions(
    predictions: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute extraction/abstention/promotion counts for anonymous dims."""

    anonymous = [
        p
        for p in predictions
        if str(p.get("engineering_object_type") or "") == "anonymous_dimension"
        or (p.get("semantic_candidates") and p.get("context_evidence"))
    ]
    promoted = [
        p
        for p in anonymous
        if (p.get("canonical") or {}).get("comparison", {}).get("match_status")
        == "confirmed_annotation"
    ]
    needs_context = [
        p
        for p in anonymous
        if (p.get("canonical") or {}).get("comparison", {}).get("match_status")
        == "needs_context"
    ]
    with_candidates = [p for p in anonymous if p.get("semantic_candidates")]
    return {
        "anonymous_dimension_count": len(anonymous),
        "promoted_count": len(promoted),
        "needs_context_count": len(needs_context),
        "with_semantic_candidates_count": len(with_candidates),
        "abstention_rate": round(
            len(needs_context) / len(anonymous), 4
        )
        if anonymous
        else 0.0,
        "promotion_rate": round(len(promoted) / len(anonymous), 4)
        if anonymous
        else 0.0,
    }
