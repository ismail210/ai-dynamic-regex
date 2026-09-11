"""Separate *does this physical member exist* from *what section is it*.

Estima3D's synthetic tokens -- spatial association (a geometry line near a
printed label), geometry-inference "missing label", and graph label
propagation -- carry one ``confidence.overall`` scalar that conflates both
questions. A spatial-association token in particular is rehydrated into the
protected-exact-label path (``orchestrator.predict_from_context``) and is
served as ``match_status=exact_match`` with a *distance-decay* score, so the
automatic takeoff counts a guessed section as a printed one.

This module classifies each prediction into one resolution class, WITHOUT
deleting anything:

* ``AUTO``            -- explicit/high-confidence section evidence; counts in
                         the automatic takeoff.
* ``REVIEW_SECTION``  -- a member very likely exists, but its section is
                         geometry/adjacency-inferred only; route to Drawing
                         Review, do not auto-count.
* ``WEAK_GEOMETRY``   -- member existence itself is weak; developer-visible,
                         never counted, not queued.

Page-modal / nearest-common-label / local-frequency evidence by itself is
never sufficient for ``AUTO`` -- only an explicit associated label (leader
resolved), a graph propagation from a text-backed member, a verified project
rule, or a real printed designation qualifies.

Human-reviewed and project-rule-resolved predictions are always ``AUTO`` --
their precedence (see services.human_selections) is never touched here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

AUTO = "auto"
REVIEW_SECTION = "review_section"
WEAK_GEOMETRY = "weak_geometry"

OBJECT_SCOPE_UNRESOLVED_MEMBER = "unresolved_member"
OBJECT_SCOPE_WEAK_GEOMETRY = "weak_geometry_candidate"

_STRONG_PROPAGATION_SEED = 0.80


def _overall(prediction: Dict[str, Any]) -> float:
    conf = prediction.get("confidence")
    if isinstance(conf, dict):
        try:
            return float(conf.get("overall") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(conf or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_human_or_rule(prediction: Dict[str, Any]) -> bool:
    if prediction.get("decision_source") == "human_review":
        return True
    if prediction.get("human_selected_section"):
        return True
    status = (prediction.get("comparison") or {}).get("match_status") or prediction.get(
        "match_status"
    )
    return status in {"human_resolved", "project_rule_resolved"}


def _spatial(prediction: Dict[str, Any]) -> Optional[dict]:
    sa = prediction.get("spatial_association")
    return sa if isinstance(sa, dict) else None


def _is_synthetic(prediction: Dict[str, Any]) -> bool:
    if prediction.get("geometry_associated") or prediction.get("schedule_sourced"):
        return True
    if _spatial(prediction) or isinstance(prediction.get("missing_label_prediction"), dict):
        return True
    if prediction.get("prediction_source") == "Geometry":
        return True
    oid = str(prediction.get("object_id") or "")
    return oid.startswith(("geom_assoc", "geom_", "schedule_", "spatial_"))


def _leader_linked(sa: Optional[dict]) -> bool:
    if not sa:
        return False
    sources = sa.get("sources") or []
    return any("leader" in str(s).lower() for s in sources)


def _graph_degree(prediction: Dict[str, Any]) -> int:
    gp = prediction.get("graph_preview") or {}
    try:
        return int(gp.get("degree") or 0)
    except (TypeError, ValueError):
        return 0


def _strong_propagation(prediction: Dict[str, Any]) -> bool:
    lp = prediction.get("label_propagation")
    if not isinstance(lp, dict):
        return False
    try:
        return float(lp.get("seed_confidence") or 0.0) >= _STRONG_PROPAGATION_SEED
    except (TypeError, ValueError):
        return False


def classify_member(prediction: Dict[str, Any]) -> Tuple[str, float, float, str]:
    """Return ``(resolution, existence_confidence, section_confidence, evidence_type)``.

    ``resolution`` is one of AUTO / REVIEW_SECTION / WEAK_GEOMETRY.
    """

    overall = _overall(prediction)

    # 1. Human / project-rule resolutions always auto-count.
    if _is_human_or_rule(prediction):
        return AUTO, 1.0, max(overall, 0.9), "human_or_rule"

    # 2. Real printed designations (not synthetic) keep today's behaviour.
    if not _is_synthetic(prediction):
        return AUTO, 1.0, overall, "explicit_label"

    # --- synthetic from here ---
    sa = _spatial(prediction)
    missing = isinstance(prediction.get("missing_label_prediction"), dict)
    degree = _graph_degree(prediction)

    # 3a. Strong section evidence -> auto.
    if _strong_propagation(prediction):
        return AUTO, max(overall, 0.75), overall, "graph_propagated"
    if _leader_linked(sa):
        return AUTO, max(overall, 0.7), overall, "leader_resolved_label"

    # 3b. Member likely exists (geometry line, or graph agrees) but the
    #     section is nearest-label / geometry-only -> section review.
    if sa is not None:
        # spatial association: a real drawn line near a printed label. Member
        # existence is well supported; the section is the nearest label's,
        # not this line's.
        try:
            dist = float(sa.get("distance") or 0.0)
        except (TypeError, ValueError):
            dist = 0.0
        existence = max(0.55, min(0.9, 0.9 - dist / 600.0))
        return REVIEW_SECTION, existence, 0.35, "spatial_nearest_label"

    if missing:
        mlp = prediction["missing_label_prediction"]
        try:
            mconf = float(mlp.get("confidence") or 0.0)
        except (TypeError, ValueError):
            mconf = 0.0
        if degree > 0 or mconf >= 0.5:
            return REVIEW_SECTION, max(0.5, mconf), 0.3, "geometry_inference"
        return WEAK_GEOMETRY, min(0.45, mconf), 0.2, "geometry_only_weak"

    # 4. Other synthetic (schedule-only token whose section is a real catalog
    #    designation from a schedule line) -> keep auto but flag provenance;
    #    the schedule-semantics work (Phase B) refines this.
    if prediction.get("schedule_sourced"):
        return AUTO, 0.7, overall, "schedule_line"

    return REVIEW_SECTION, max(0.5, overall), min(0.4, overall), "synthetic_unclassified"


def _page_type(prediction: Dict[str, Any], context_pages: Dict[int, str],
               schedule_pages: Dict[int, str]) -> str:
    raw_page = prediction.get("page_number") or prediction.get("page")
    try:
        page = int(raw_page or 0)
    except (TypeError, ValueError):
        return "unknown"
    if not page:
        return "unknown"
    if page in context_pages:
        return f"context:{context_pages[page]}"
    if page in schedule_pages:
        return f"schedule:{schedule_pages[page]}"
    return "drawing"


def route_member_resolution(
    predictions: list, document: Dict[str, Any]
) -> Dict[str, int]:
    """Classify every prediction; demote weak-section synthetic members out of
    the automatic takeoff (``takeoff_eligible=False``) and route them to
    review. Stamps ``member_provenance`` / ``existence_confidence`` /
    ``section_confidence`` on every prediction. In-place. Returns a small
    diagnostic tally.

    Never touches a prediction that is already ``takeoff_eligible=False``
    (legend/context-page demotion) or human-reviewed.
    """

    profile = document.get("legend_profile") or {}
    context_pages = {}
    for raw, role in (profile.get("context_pages") or {}).items():
        try:
            context_pages[int(raw)] = str(role)
        except (TypeError, ValueError):
            continue
    schedule_pages = {}
    for sch in document.get("schedules") or []:
        try:
            schedule_pages[int(sch.get("page_number") or sch.get("page") or 0)] = str(
                sch.get("schedule_type") or "schedule"
            )
        except (TypeError, ValueError):
            continue

    tally = {"auto": 0, "review_section": 0, "weak_geometry": 0, "already_context": 0}
    for prediction in predictions:
        resolution, existence, section_conf, evidence = classify_member(prediction)
        prediction["existence_confidence"] = round(existence, 3)
        prediction["section_confidence"] = round(section_conf, 3)
        prediction["member_provenance"] = {
            "page_type": _page_type(prediction, context_pages, schedule_pages),
            "prediction_source": prediction.get("prediction_source"),
            "evidence_type": evidence,
            "existence_confidence": round(existence, 3),
            "section_confidence": round(section_conf, 3),
            "geometry_id": prediction.get("geometry_id")
            or (prediction.get("spatial_association") or {}).get("label_node_id"),
        }

        if prediction.get("takeoff_eligible") is False:
            tally["already_context"] += 1
            continue

        if resolution == AUTO:
            tally["auto"] += 1
            continue

        # Keep the member in the served prediction list (Drawing Review shows
        # it with a section picker), but mark it so the automatic takeoff
        # count excludes it. `takeoff_eligible` is deliberately NOT touched --
        # that flag means "legend/context definition, not a member at all".
        prediction["needs_review"] = True
        prediction["review_status"] = "pending_review"
        prediction["review_reason"] = resolution_note(evidence)
        # Section is unconfirmed -- do not present a guessed section as final.
        prediction["auto_section_withheld"] = prediction.get("section")
        canonical = prediction.get("canonical")
        if isinstance(canonical, dict) and isinstance(canonical.get("prediction"), dict):
            canonical["prediction"]["final_label"] = None
        if resolution == REVIEW_SECTION:
            prediction["object_scope"] = OBJECT_SCOPE_UNRESOLVED_MEMBER
            tally["review_section"] += 1
        else:  # WEAK_GEOMETRY
            prediction["object_scope"] = OBJECT_SCOPE_WEAK_GEOMETRY
            prediction["_skip_unknown_queue"] = True
            tally["weak_geometry"] += 1

    document["member_resolution"] = tally
    return tally


def resolution_note(evidence_type: str) -> str:
    return {
        "spatial_nearest_label": (
            "A member was detected here from drawing geometry, but its section "
            "was inferred from the nearest printed label -- confirm the section."
        ),
        "geometry_inference": (
            "Geometry and the structural graph indicate a member here with no "
            "printed label -- confirm the section."
        ),
        "geometry_only_weak": (
            "Weak geometry-only member candidate -- shown for review, not "
            "included in the takeoff."
        ),
        "synthetic_unclassified": "Synthetic member with unverified section -- confirm.",
    }.get(evidence_type, "Confirm this member's section.")
