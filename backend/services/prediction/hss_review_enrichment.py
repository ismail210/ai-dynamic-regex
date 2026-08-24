"""Backfill missing-thickness HSS review fields on served predictions.

Older cached analyses (pre-HSS completion workflow) may show a fusion guess as
``corrected_prediction`` without ``candidate_sections``. Re-derive catalog
constrained options from the extracted two-part HSS read at serve time so the
Results UI can offer thickness choices without a full re-analyze when possible.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.hss_completion import (
    detect_missing_thickness_hss,
    hss_completion_candidates,
)
from services.prediction.canonical_contract import MatchStatus

_MISSING_THICKNESS_REVIEW_REASON = (
    "Wall thickness is not present in the extracted designation; "
    "select the correct catalog section."
)


def enrich_missing_thickness_hss_predictions(
    predictions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for prediction in predictions:
        item = dict(prediction)
        if item.get("human_selected_section") or item.get("decision_source") == "human_review":
            enriched.append(item)
            continue

        existing = item.get("candidate_sections") or []
        if len(existing) > 1:
            enriched.append(item)
            continue

        raw = str(item.get("raw_text") or item.get("original_token") or "")
        normalized = str(
            item.get("normalized_text")
            or item.get("corrected_token")
            or item.get("corrected_text")
            or ""
        )
        dims = detect_missing_thickness_hss(normalized) or detect_missing_thickness_hss(
            raw
        )
        if not dims:
            enriched.append(item)
            continue

        completions = hss_completion_candidates(*dims)
        if len(completions) <= 1:
            enriched.append(item)
            continue

        item["candidate_sections"] = [candidate.to_dict() for candidate in completions]
        item["completion_status"] = "missing_thickness"
        item["known_dimensions"] = list(dims)
        item["needs_review"] = True
        item["review_reason"] = _MISSING_THICKNESS_REVIEW_REASON

        canonical = item.get("canonical")
        if isinstance(canonical, dict):
            canonical = dict(canonical)
            prediction_block = dict(canonical.get("prediction") or {})
            prediction_block["final_label"] = None
            canonical["prediction"] = prediction_block
            canonical["comparison"] = {
                **(canonical.get("comparison") or {}),
                "match_status": MatchStatus.MISSING_DIMENSION_FIELD.value,
                "exact_match": False,
                "normalized_match": False,
                "prediction_required": True,
            }
            canonical["needs_review"] = True
            canonical["review_reason"] = _MISSING_THICKNESS_REVIEW_REASON
            item["canonical"] = canonical
            item["comparison"] = canonical["comparison"]

        enriched.append(item)
    return enriched
