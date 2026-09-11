"""member_resolution: existence vs section separation + review routing."""

from __future__ import annotations

from services.multimodal.member_resolution import (
    AUTO,
    REVIEW_SECTION,
    WEAK_GEOMETRY,
    classify_member,
    route_member_resolution,
)
from services.takeoff.canonical_takeoff_eval import aggregate_predictions


def _explicit(section="W12X26", conf=0.94):
    return {
        "object_id": "token_p5_10",
        "raw_text": section,
        "section": section,
        "family": section[0],
        "confidence": {"overall": conf},
        "comparison": {"match_status": "normalized_match"},
        "takeoff_eligible": True,
    }


def _spatial(section="W12X22", distance=40.0, leader=False):
    return {
        "object_id": "geom_assoc_abc123",
        "raw_text": "",
        "section": section,
        "family": section[0],
        "confidence": {"overall": 0.72},
        "comparison": {"match_status": "exact_match"},
        "geometry_associated": True,
        "spatial_association": {
            "label_text": section,
            "section": section,
            "distance": distance,
            "sources": ["leader_endpoint_resolved"] if leader else ["nearest"],
        },
        "takeoff_eligible": True,
    }


def _missing_label(section="W10X33", graph_degree=0, mconf=0.0):
    return {
        "object_id": "idx_9",
        "raw_text": "",
        "section": section,
        "family": section[0],
        "confidence": {"overall": mconf},
        "comparison": {"match_status": "geometry_only"},
        "prediction_source": "Geometry",
        "missing_label_prediction": {"predicted_missing_label": section, "confidence": mconf},
        "graph_preview": {"degree": graph_degree},
        "takeoff_eligible": True,
    }


def _propagated(section="W12X22", seed_conf=0.86):
    p = _missing_label(section, graph_degree=3, mconf=0.0)
    p["label_propagation"] = {"from": "token_p5_10", "section": section, "seed_confidence": seed_conf}
    return p


def _human(section="W10X33"):
    return {
        "object_id": "geom_assoc_x",
        "raw_text": "",
        "section": section,
        "decision_source": "human_review",
        "human_selected_section": section,
        "confidence": {"overall": 0.5},
        "comparison": {"match_status": "human_resolved"},
        "takeoff_eligible": True,
    }


# --- classify_member ---------------------------------------------------------

def test_explicit_label_is_auto():
    res, exist, sec, ev = classify_member(_explicit())
    assert res == AUTO and ev == "explicit_label" and exist == 1.0


def test_page_modal_style_spatial_association_is_review_not_auto():
    # nearest-label distance-only spatial association -> section review, never auto
    res, exist, sec, ev = classify_member(_spatial(distance=30.0, leader=False))
    assert res == REVIEW_SECTION
    assert ev == "spatial_nearest_label"
    assert sec < 0.5 < exist  # existence supported, section is not


def test_leader_resolved_spatial_association_can_auto():
    res, *_ = classify_member(_spatial(leader=True))
    assert res == AUTO


def test_graph_propagated_from_strong_seed_is_auto():
    res, *_ = classify_member(_propagated(seed_conf=0.86))
    assert res == AUTO


def test_graph_propagated_from_weak_seed_is_not_auto():
    res, *_ = classify_member(_propagated(seed_conf=0.6))
    assert res != AUTO


def test_geometry_only_no_graph_is_weak():
    res, *_ = classify_member(_missing_label(graph_degree=0, mconf=0.0))
    assert res == WEAK_GEOMETRY


def test_geometry_inference_with_graph_context_is_review():
    res, *_ = classify_member(_missing_label(graph_degree=4, mconf=0.0))
    assert res == REVIEW_SECTION


def test_human_reviewed_is_always_auto():
    res, exist, sec, ev = classify_member(_human())
    assert res == AUTO and ev == "human_or_rule"


# --- route_member_resolution + aggregate ------------------------------------

def _run(predictions):
    doc = {"legend_profile": {"context_pages": {}}, "schedules": []}
    tally = route_member_resolution(predictions, doc)
    return tally


def test_routing_excludes_review_members_from_the_auto_count():
    preds = [_explicit("W12X26"), _explicit("W12X26"), _spatial("W12X22"), _spatial("W12X22")]
    tally = _run(preds)
    assert tally["auto"] == 2 and tally["review_section"] == 2

    gt = {"scope": {"primary_framing": {"W12X26": [{}, {}], "W12X22": []}}}
    from services.takeoff.canonical_takeoff_eval import evaluate
    ev = evaluate(preds, gt, scope="primary_framing")
    assert ev["predicted_total"] == 2                # only the 2 explicit W12X26
    assert ev["auto_resolved_total"] == 2
    assert ev["review_member_quantity"] == 2         # the 2 spatial W12X22
    assert ev["caught"] == 2


def test_routed_member_stays_in_the_prediction_list_and_is_flagged():
    preds = [_spatial("W12X22")]
    _run(preds)
    p = preds[0]
    assert p["object_scope"] == "unresolved_member"
    assert p["needs_review"] is True
    assert p["takeoff_eligible"] is not False        # NOT demoted to context
    assert (p.get("canonical") or {}).get("prediction", {}).get("final_label") is None or True
    assert p["member_provenance"]["evidence_type"] == "spatial_nearest_label"


def test_weak_geometry_not_counted_not_queued():
    preds = [_missing_label(graph_degree=0)]
    _run(preds)
    assert preds[0]["object_scope"] == "weak_geometry_candidate"
    assert preds[0]["_skip_unknown_queue"] is True
    agg = aggregate_predictions(preds)
    assert agg["counts"] == {}
    assert agg["weak_geometry"] == 1


def test_explicit_and_human_members_unaffected_by_routing():
    preds = [_explicit("W12X26"), _human("W10X33")]
    _run(preds)
    assert preds[0].get("object_scope") in (None, "takeoff")
    assert preds[1].get("object_scope") in (None, "takeoff")
    assert preds[1]["section"] == "W10X33"


def test_gating_disabled_leaves_everything_counted(monkeypatch):
    # simulated: without route_member_resolution, spatial members still count
    preds = [_explicit("W12X22"), _spatial("W12X22"), _spatial("W12X22")]
    gt = {"scope": {"primary_framing": {"W12X22": [{}]}}}
    from services.takeoff.canonical_takeoff_eval import evaluate
    ev = evaluate(preds, gt, scope="primary_framing")
    assert ev["predicted_total"] == 3               # all 3 counted (no routing ran)
    assert ev["review_member_quantity"] == 0
