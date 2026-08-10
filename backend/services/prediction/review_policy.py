"""
Review policy — confidence / conflict driven.

Database miss alone never queues a token for review.
"""

from __future__ import annotations

from typing import Iterable, Set

from config import settings


CONFLICT_ISSUES = {
    "geometry_conflict",
    "graph_conflict",
    "engineering_rule_conflict",
    "automatic_correction_suggested",
}


def decide_review_status(
    *,
    confidence: float,
    issues: Iterable[str],
    corrected: bool = False,
    regex_matches: bool = True,
    model_probability: float | None = None,
    database_verified: bool = False,
    abstain: bool = False,
) -> str:
    """
    Return review_status string.

    Priority: auto_accepted / pending_review / correction_suggested /
    accepted_unverified.
    """

    issue_set: Set[str] = set(issues or [])
    modality_conflict = len(issue_set & CONFLICT_ISSUES) >= 2
    uncertain = (
        model_probability is not None
        and model_probability < settings.auto_accept_probability_threshold
    )

    if abstain or "retrieval_gate_failed" in issue_set:
        return "pending_review"

    if (
        confidence >= settings.confidence_high_threshold
        and not modality_conflict
        and "low_extraction_confidence" not in issue_set
        and not uncertain
        and regex_matches
    ):
        return "auto_accepted"

    if corrected or modality_conflict or confidence < settings.confidence_medium_threshold or uncertain:
        return "pending_review"

    # Medium confidence path — database miss does NOT force a queue.
    if not database_verified:
        return "accepted_unverified" if regex_matches else "correction_suggested"
    return "auto_accepted"


def should_enqueue(review_status: str) -> bool:
    return review_status in {"pending_review", "queued"}
