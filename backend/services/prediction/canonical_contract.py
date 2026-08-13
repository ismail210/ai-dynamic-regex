"""
Canonical steel-label prediction contract.

Every producer of a prediction (the token-only path in
``services.prediction.orchestrator.predict_token`` and the per-document
multimodal path in ``services.multimodal.contracts.MultiModalPrediction``)
builds one of these. It is the single source of truth for:

* what was physically extracted from the source (``source_text``, always
  distinct from the predicted label — never silently overwritten),
* what the system predicted (``prediction``),
* whether the two agree, and how (``comparison.match_status``),
* which evidence sources actually contributed (``decision``),
* the ranked, catalog-checked candidate set (``candidates``),
* and whether a human needs to look at it (``needs_review``).

Legacy top-level fields (``prediction`` as a bare string, ``predicted_shape``,
``confidence.score``, ``multimodal_confidence``, ``overall_confidence``, ...)
remain on the surrounding response dict for one migration period. They are
intentionally NOT reproduced here — see
``services.prediction.contract.apply_legacy_aliases`` for that one, clearly
named adapter, which is marked for removal once the frontend fully consumes
this contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from services.normalization import is_conservatively_equal
from services.wildcard_matcher import has_wildcards


class MatchStatus(str, Enum):
    EXACT_MATCH = "exact_match"
    NORMALIZED_MATCH = "normalized_match"
    CORRECTED_PREDICTION = "corrected_prediction"
    INCOMPLETE_LABEL = "incomplete_label"
    GEOMETRY_ONLY = "geometry_only"
    SOURCE_TEXT_NOT_FOUND = "source_text_not_found"
    UNRESOLVED = "unresolved"


class SourceText(BaseModel):
    """What was physically extracted from the source document, verbatim."""

    raw: Optional[str] = None
    normalized: Optional[str] = None
    page_number: Optional[int] = None
    bounding_box: Optional[List[float]] = None
    block_number: Optional[Any] = None
    line_number: Optional[Any] = None
    word_number: Optional[Any] = None
    extraction_method: str = "unknown"
    available: bool = False


class PredictionSummary(BaseModel):
    final_label: Optional[str] = None
    family: Optional[str] = None
    ranking_score: float = 0.0
    final_confidence: Optional[float] = None
    confidence_is_calibrated: bool = False


class Comparison(BaseModel):
    exact_match: bool = False
    normalized_match: bool = False
    prediction_required: bool = True
    match_status: MatchStatus = MatchStatus.UNRESOLVED


class Decision(BaseModel):
    source: str = "text"
    used_text: bool = False
    used_geometry: bool = False
    used_graph: bool = False
    used_engineering_rules: bool = False
    used_catalog: bool = False


class CandidateModel(BaseModel):
    label: str
    catalog_valid: bool = False
    mask_match: bool = False
    text_similarity: float = 0.0
    geometry_score: float = 0.0
    graph_score: float = 0.0
    engineering_score: float = 0.0
    combined_score: float = 0.0
    match_reasons: List[str] = Field(default_factory=list)


class CanonicalPrediction(BaseModel):
    object_id: str
    document_id: Optional[str] = None
    source_text: SourceText
    prediction: PredictionSummary
    comparison: Comparison
    decision: Decision
    candidates: List[CandidateModel] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    catalog_version: Optional[str] = None
    needs_review: bool = False
    review_reason: Optional[str] = None


def _decision_source(decision: Decision) -> str:
    used = [
        name
        for name, flag in (
            ("text", decision.used_text),
            ("geometry", decision.used_geometry),
            ("graph", decision.used_graph),
            ("engineering_rules", decision.used_engineering_rules),
        )
        if flag
    ]
    return "_and_".join(used) if used else "none"


def determine_comparison(
    *,
    raw_text: str,
    final_label: Optional[str],
    source_available: bool,
    used_wildcards: bool,
) -> Comparison:
    """
    Decide exact / normalized / corrected / incomplete / geometry-only /
    source-text-not-found / unresolved, using ONLY the conservative
    (formatting-safe) normalizer — never an OCR-correction guess.
    """

    has_prediction = bool(final_label)

    if not source_available or not raw_text:
        if has_prediction:
            return Comparison(
                exact_match=False,
                normalized_match=False,
                prediction_required=True,
                match_status=MatchStatus.GEOMETRY_ONLY,
            )
        return Comparison(
            exact_match=False,
            normalized_match=False,
            prediction_required=True,
            match_status=MatchStatus.SOURCE_TEXT_NOT_FOUND,
        )

    if not has_prediction:
        return Comparison(
            exact_match=False,
            normalized_match=False,
            prediction_required=True,
            match_status=MatchStatus.UNRESOLVED,
        )

    if raw_text.strip() == str(final_label).strip():
        return Comparison(
            exact_match=True,
            normalized_match=True,
            prediction_required=False,
            match_status=MatchStatus.EXACT_MATCH,
        )

    if is_conservatively_equal(raw_text, final_label):
        return Comparison(
            exact_match=False,
            normalized_match=True,
            prediction_required=False,
            match_status=MatchStatus.NORMALIZED_MATCH,
        )

    if used_wildcards:
        return Comparison(
            exact_match=False,
            normalized_match=False,
            prediction_required=True,
            match_status=MatchStatus.INCOMPLETE_LABEL,
        )

    return Comparison(
        exact_match=False,
        normalized_match=False,
        prediction_required=True,
        match_status=MatchStatus.CORRECTED_PREDICTION,
    )


_REVIEW_REASONS = {
    MatchStatus.CORRECTED_PREDICTION: "Source text differs from predicted label.",
    MatchStatus.INCOMPLETE_LABEL: "Source label had unknown/wildcard characters resolved by mask matching.",
    MatchStatus.GEOMETRY_ONLY: "No source text was available; prediction relies on geometry/graph context.",
    MatchStatus.SOURCE_TEXT_NOT_FOUND: "No source text or prediction could be resolved for this object.",
    MatchStatus.UNRESOLVED: "No valid candidate could be resolved.",
}


def determine_review_from_status(
    *,
    match_status: str,
    near_tie: bool,
    review_status: Optional[str],
) -> tuple[bool, Optional[str]]:
    """Combine match-status, near-tie candidates, and the confidence/conflict
    review policy (``services.prediction.review_policy.decide_review_status``)
    into one needs_review decision. Takes ``match_status`` as a plain string
    so callers refreshing an already-serialized canonical payload (e.g.
    ``predict_token``, which recomputes ``review_status`` after the
    canonical contract was first built) don't need the full ``Comparison``
    model to stay in sync."""

    if near_tie:
        return True, "Two or more candidates are near-tied; automatic selection is not reliable enough."

    reason = _REVIEW_REASONS.get(match_status)
    if reason:
        return True, reason

    if review_status and review_status not in {"auto_accepted"}:
        return True, f"Flagged by review policy: {review_status}."

    return False, None


def determine_review(
    *,
    comparison: Comparison,
    near_tie: bool,
    review_status: Optional[str],
) -> tuple[bool, Optional[str]]:
    return determine_review_from_status(
        match_status=comparison.match_status,
        near_tie=near_tie,
        review_status=review_status,
    )


def build_canonical_prediction(
    *,
    object_id: str,
    document_id: Optional[str],
    raw_text: str,
    normalized_text: str,
    page_number: Optional[int],
    bounding_box: Optional[List[float]],
    block_number: Optional[Any],
    line_number: Optional[Any],
    word_number: Optional[Any],
    extraction_method: str,
    source_available: bool,
    final_label: Optional[str],
    family: Optional[str],
    ranking_score: float,
    final_confidence: Optional[float],
    confidence_is_calibrated: bool,
    used_text: bool,
    used_geometry: bool,
    used_graph: bool,
    used_engineering_rules: bool,
    used_catalog: bool,
    candidates: List[Dict[str, Any]],
    evidence: Dict[str, Any],
    catalog_version: Optional[str],
    review_status: Optional[str],
    near_tie: bool = False,
    used_wildcards: bool = False,
) -> CanonicalPrediction:
    source_text = SourceText(
        raw=raw_text or None,
        normalized=normalized_text or None,
        page_number=page_number,
        bounding_box=list(bounding_box) if bounding_box else None,
        block_number=block_number,
        line_number=line_number,
        word_number=word_number,
        extraction_method=extraction_method,
        available=bool(source_available),
    )
    comparison = determine_comparison(
        raw_text=raw_text,
        final_label=final_label,
        source_available=source_available,
        used_wildcards=used_wildcards,
    )
    # ``final_label`` is the canonical, automatically-accepted answer -- it
    # must never carry a fuzzy-retrieved or learned-corrected guess dressed
    # up as a resolved result (resolution contract, Case B/C). Every
    # match_status other than EXACT_MATCH/NORMALIZED_MATCH already forces
    # needs_review below via _REVIEW_REASONS; reuse that same partition here
    # so "not authoritative enough to auto-accept" and "not authoritative
    # enough to review" can never drift apart. The un-nulled guess is still
    # available to reviewers via ``candidates``.
    accepted_final_label = (
        final_label if comparison.match_status not in _REVIEW_REASONS else None
    )
    prediction = PredictionSummary(
        final_label=accepted_final_label or None,
        family=family or None,
        ranking_score=round(float(ranking_score or 0.0), 4),
        final_confidence=final_confidence,
        confidence_is_calibrated=bool(confidence_is_calibrated),
    )
    decision = Decision(
        used_text=bool(used_text),
        used_geometry=bool(used_geometry),
        used_graph=bool(used_graph),
        used_engineering_rules=bool(used_engineering_rules),
        used_catalog=bool(used_catalog),
    )
    decision.source = _decision_source(decision)

    needs_review, review_reason = determine_review(
        comparison=comparison, near_tie=near_tie, review_status=review_status
    )

    return CanonicalPrediction(
        object_id=object_id,
        document_id=document_id,
        source_text=source_text,
        prediction=prediction,
        comparison=comparison,
        decision=decision,
        candidates=[CandidateModel(**item) for item in candidates],
        evidence=evidence,
        catalog_version=catalog_version,
        needs_review=needs_review,
        review_reason=review_reason,
    )
