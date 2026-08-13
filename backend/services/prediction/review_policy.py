"""
Review policy — confidence / conflict driven.

Database miss alone never queues a token for review.
"""

from __future__ import annotations

from typing import Iterable, Optional, Set

from config import settings


CONFLICT_ISSUES = {
    "geometry_conflict",
    "graph_conflict",
    "engineering_rule_conflict",
    "automatic_correction_suggested",
}

# Single-issue signals that always force review on their own, unlike
# CONFLICT_ISSUES above which only forces review at 2+. These come from the
# annotation-taxonomy gate (services.annotation.taxonomy) and mean the
# *reading* of the token itself is unresolved/unsupported — including when a
# protected exact label kept the text's own resolved section (see
# orchestrator.predict_from_context): the label is retained, but a human
# still needs to look at it.
FORCE_REVIEW_ISSUES = {
    "retrieval_gate_failed",
    "annotation_unreadable",
    "annotation_unsupported",
    "annotation_ambiguous",
    "annotation_requires_review",
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
    protected_label_conflict: bool = False,
) -> str:
    """
    Return review_status string.

    Priority: auto_accepted / pending_review / correction_suggested /
    accepted_unverified.

    ``protected_label_conflict`` means the final section is a clean,
    catalog-valid exact text match that fusion/graph/ranker evidence
    disagreed with. The label is never silently swapped in that case (see
    ``orchestrator._gated_exact_override`` and its caller), but the
    disagreement itself is real evidence a human should look at, so it always
    routes to review — the same way ``abstain`` does — rather than being
    diluted into the two-issue ``modality_conflict`` threshold below.
    """

    issue_set: Set[str] = set(issues or [])
    modality_conflict = len(issue_set & CONFLICT_ISSUES) >= 2
    uncertain = (
        model_probability is not None
        and model_probability < settings.auto_accept_probability_threshold
    )

    if abstain or protected_label_conflict or (issue_set & FORCE_REVIEW_ISSUES):
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


# Standardized abstention/review reason codes. A prediction that is not
# "auto_accepted" should be able to say WHY in one of these terms, instead of
# only exposing an ad-hoc issue-string bag — reviewers and downstream
# tooling can filter/prioritize by cause this way.
ABSTENTION_REASON_LOW_CONFIDENCE = "LOW_CONFIDENCE"
ABSTENTION_REASON_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
ABSTENTION_REASON_MODAL_DISAGREEMENT = "MODAL_DISAGREEMENT"
ABSTENTION_REASON_OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
ABSTENTION_REASON_PIPELINE_FAILURE = "PIPELINE_FAILURE"

_ABSTENTION_REASONS = {
    ABSTENTION_REASON_LOW_CONFIDENCE,
    ABSTENTION_REASON_INSUFFICIENT_EVIDENCE,
    ABSTENTION_REASON_MODAL_DISAGREEMENT,
    ABSTENTION_REASON_OUT_OF_DISTRIBUTION,
    ABSTENTION_REASON_PIPELINE_FAILURE,
}


def determine_abstention_reason(
    *,
    review_status: str,
    confidence: float,
    issues: Iterable[str],
    model_probability: float | None = None,
    database_verified: bool = False,
    regex_matches: bool = True,
    protected_label_conflict: bool = False,
    retrieval_gate_failed: bool = False,
    pipeline_error: bool = False,
) -> Optional[str]:
    """One canonical reason code for why a prediction is not auto-accepted.

    Returns ``None`` when the prediction was auto-accepted (nothing to
    explain). Priority order below is deliberate: a pipeline failure or an
    explicit evidence conflict is a more specific, more actionable cause than
    a generic low-confidence score, so those are checked first even though
    they usually also happen to have low confidence.
    """

    if review_status == "auto_accepted":
        return None

    if pipeline_error:
        return ABSTENTION_REASON_PIPELINE_FAILURE

    issue_set: Set[str] = set(issues or [])

    if protected_label_conflict:
        return ABSTENTION_REASON_MODAL_DISAGREEMENT
    if len(issue_set & CONFLICT_ISSUES) >= 2:
        return ABSTENTION_REASON_MODAL_DISAGREEMENT

    if "annotation_unsupported" in issue_set:
        return ABSTENTION_REASON_OUT_OF_DISTRIBUTION

    if retrieval_gate_failed or (issue_set & FORCE_REVIEW_ISSUES):
        return ABSTENTION_REASON_INSUFFICIENT_EVIDENCE

    if not database_verified and not regex_matches:
        # Neither the catalog nor any known regex pattern recognizes this
        # text at all — the closest proxy available today for "this input
        # doesn't resemble anything the system has learned," in the absence
        # of a dedicated learned OOD detector.
        return ABSTENTION_REASON_OUT_OF_DISTRIBUTION

    uncertain = (
        model_probability is not None
        and model_probability < settings.auto_accept_probability_threshold
    )
    if confidence < settings.confidence_medium_threshold or uncertain:
        return ABSTENTION_REASON_LOW_CONFIDENCE

    # review_status is not auto_accepted but none of the more specific causes
    # above matched (e.g. accepted_unverified/correction_suggested paths) —
    # still low-confidence in spirit: nothing about this prediction cleared
    # the bar for automatic acceptance.
    return ABSTENTION_REASON_LOW_CONFIDENCE
