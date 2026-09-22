"""Canonical result-category tags for the Analysis/Results filter system.

Backend-computed, once, from the same provenance fields the rest of the
prediction contract already carries (``services.prediction.canonical_
contract.MatchStatus``, ``project_rule_resolution``, ``final_confidence``,
``needs_review``) -- never re-derived by the frontend from display strings.
See ``frontend/src/lib/predictionContract.js::getStatusTags``, which reads
``status_tags`` directly.

Category definitions (deliberately strict -- see the task's own Section 17):

* ``perfect_match`` -- the source text was ALREADY a complete, catalog-valid
  section and the final section is that exact same designation
  (``MatchStatus.EXACT_MATCH``). A project-rule resolution is never
  "perfect", however high its confidence -- the OCR text did not carry the
  full designation.
* ``formatting_only`` -- the source required only a lossless
  formatting/canonicalization rewrite (case, spacing, catalog-form spelling)
  and nothing else (``MatchStatus.NORMALIZED_MATCH``).
* ``project_rule`` -- an incomplete/shorthand label was resolved via a
  verified project-specific rule (``MatchStatus.PROJECT_RULE_RESOLVED``).
* ``llm_assisted`` -- co-occurs with ``project_rule`` when the winning rule
  came from a validated LLM extraction rather than the deterministic
  ``"X" = Y`` legend reader (``project_rule_resolution.extraction_method ==
  "llm_assisted"``). Never applied to a purely deterministic resolution.
* ``needs_review`` -- the final section still needs human resolution.
* ``low_confidence`` -- an INFERRED section (candidate/ranker/fusion path)
  below the configured high-confidence threshold. Deterministic exact,
  formatting, and project-rule resolutions are never tagged low-confidence
  merely because a leftover generic fusion score happens to be low -- those
  paths do not run through the statistical fusion confidence at all.
* ``human_reviewed`` -- a reviewer supplied the final value.
* ``warning`` -- resolved (not needs_review) but carries an actionable
  non-fatal issue (a review_reason left over, or a geometry/graph
  association conflict).
* ``unresolved`` -- no valid final section could be produced at all.
* ``inferred`` -- the final section came from candidate/ranker/fusion
  inference rather than an exact/formatting/project-rule/human source.
"""

from __future__ import annotations

from typing import Any, Dict, Set

from config import settings

_EXACT = "exact_match"
_NORMALIZED = "normalized_match"
_PROJECT_RULE = "project_rule_resolved"
_HUMAN = "human_resolved"
_MISSING_DIM = "missing_dimension_field"
_INCOMPLETE = "incomplete_label"
_UNRESOLVED = "unresolved"
_SOURCE_NOT_FOUND = "source_text_not_found"
_GEOMETRY_ONLY = "geometry_only"
_NEEDS_CONTEXT = "needs_context"
_CORRECTED = "corrected_prediction"
_CONFIRMED_ANNOTATION = "confirmed_annotation"

_NEEDS_REVIEW_STATUSES = {
    _MISSING_DIM,
    _INCOMPLETE,
    _UNRESOLVED,
    _SOURCE_NOT_FOUND,
    _GEOMETRY_ONLY,
    _NEEDS_CONTEXT,
}


def _match_status(prediction: Dict[str, Any]) -> str:
    canonical = prediction.get("canonical")
    if isinstance(canonical, dict):
        status = (canonical.get("comparison") or {}).get("match_status")
        if status:
            return str(status)
    return str((prediction.get("comparison") or {}).get("match_status") or "")


def _confidence(prediction: Dict[str, Any]) -> float:
    canonical = prediction.get("canonical")
    if isinstance(canonical, dict):
        pred_block = canonical.get("prediction") or {}
        if pred_block.get("confidence_is_calibrated") and pred_block.get("final_confidence") is not None:
            try:
                return float(pred_block["final_confidence"])
            except (TypeError, ValueError):
                pass
    try:
        return float(prediction.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def classify_prediction_status(prediction: Dict[str, Any]) -> Set[str]:
    """Return the set of canonical status tags for one served prediction.

    Never raises -- an unrecognised/absent match_status degrades to
    ``{"needs_review", "unresolved"}`` rather than throwing, since a served
    prediction missing its own provenance is itself something a reviewer
    needs to look at.
    """

    status = _match_status(prediction)
    needs_review = bool(prediction.get("needs_review"))
    tags: Set[str] = set()

    if prediction.get("human_selected_section") or prediction.get("decision_source") == "human_review" or status == _HUMAN:
        tags.add("human_reviewed")

    if status == _EXACT:
        tags.add("perfect_match")
    elif status == _NORMALIZED:
        tags.add("formatting_only")
    elif status == _PROJECT_RULE:
        tags.add("project_rule")
        rule = prediction.get("project_rule_resolution") or {}
        if rule.get("extraction_method") == "llm_assisted":
            tags.add("llm_assisted")
    elif status == _CORRECTED:
        tags.add("inferred")
    elif status == _CONFIRMED_ANNOTATION:
        tags.add("perfect_match")
    elif status in _NEEDS_REVIEW_STATUSES:
        tags.add("needs_review")
        if status in {_UNRESOLVED, _SOURCE_NOT_FOUND}:
            tags.add("unresolved")
        if status == _MISSING_DIM:
            tags.add("missing_dimension")
    elif not status:
        tags.add("needs_review")
        tags.add("unresolved")

    if needs_review:
        tags.add("needs_review")

    # Low confidence only applies to the statistical inference path -- an
    # exact/formatting/project-rule/human resolution never runs through
    # fusion confidence, so a stale/irrelevant low score there must not
    # mislabel an otherwise-verified result (task Section 17).
    if (
        "perfect_match" not in tags
        and "formatting_only" not in tags
        and "project_rule" not in tags
        and "human_reviewed" not in tags
        and status not in _NEEDS_REVIEW_STATUSES
        and not status == ""
        and _confidence(prediction) < settings.confidence_high_threshold
    ):
        tags.add("low_confidence")

    # Warning: resolved (not needs_review) but an actionable note survives --
    # e.g. a graph/geometry association conflict recorded alongside an
    # otherwise-settled label.
    if (
        "needs_review" not in tags
        and prediction.get("review_reason")
    ):
        tags.add("warning")

    return tags


def status_tags_list(prediction: Dict[str, Any]) -> list:
    """JSON-friendly, stably-ordered wrapper around
    ``classify_prediction_status`` for attaching to a served prediction."""

    return sorted(classify_prediction_status(prediction))
