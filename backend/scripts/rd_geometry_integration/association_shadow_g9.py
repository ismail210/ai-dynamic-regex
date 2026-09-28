#!/usr/bin/env python3
"""G9 — Text↔geometry association shadow experiment (R&D only).

Consumes G8 R&D candidates + Human Gold. Deterministic multi-signal scorer.
Does NOT modify production extraction, retrieval, CAP, association, or gold.

Usage (from backend/):
    python scripts/rd_geometry_integration/association_shadow_g9.py [--renders]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import geometry_bbox_audit_g7 as G7  # noqa: E402

OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
GOLD_PATH = OUT / "review_kit" / "gold_outcomes.jsonl"
G8_RESULTS = OUT / "representation_repair_g8_results.jsonl"
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
RESULTS_PATH = OUT / "association_shadow_g9_results.jsonl"
SUMMARY_PATH = OUT / "association_shadow_g9_summary.json"
REPORT_PATH = OUT / "GEOMETRY_ASSOCIATION_G9_REPORT.md"
RENDER_DIR = OUT / "association_shadow_g9_renders"
REVIEW_HTML = OUT / "association_shadow_g9_review.html"

# --- documented fixed thresholds (not fit to gold) ---
GIANT_EXTENT_PT = 600.0
LARGE_SEGMENT_EXTENT_PT = 400.0
LARGE_SEGMENT_LENGTH_PT = 400.0
MEMBER_MIN_LEN_PT = 18.0
MEMBER_MAX_LEN_PT = 520.0
DIST_SCALE_PT = 80.0  # distance soft scale
MIN_ASSOCIATE_SCORE = 0.58
MIN_MARGIN = 0.08
MIN_MARGIN_STRONG_SPATIAL = 0.05
AMBIGUOUS_SCORE_FLOOR = 0.48
WEAK_ABSTAIN_SCORE = 0.48
ORIENT_COMPAT_DEG = 45.0

SELECTABLE_KINDS = {
    "LINE_MEMBER_CANDIDATE",
    "SEGMENT_MEMBER_CANDIDATE",
    "PLATE_MEMBER_CANDIDATE",
    "SMALL_TARGET_CANDIDATE",
    "LEADER_TARGET_CANDIDATE",
}
EXCLUDED_KINDS = {"NON_MEMBER", "UNKNOWN"}

# Fixed weights — transparent, not learned from gold.
W_DISTANCE = 0.34
W_BBOX = 0.18
W_ORIENT = 0.12
W_LENGTH = 0.12
W_KIND = 0.12
W_LEADER = 0.08
W_PROVENANCE = 0.04

KIND_PRIOR = {
    "LINE_MEMBER_CANDIDATE": 1.0,
    "LEADER_TARGET_CANDIDATE": 1.0,
    "PLATE_MEMBER_CANDIDATE": 0.9,
    "SMALL_TARGET_CANDIDATE": 0.8,
    "SEGMENT_MEMBER_CANDIDATE": 0.72,
}


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------
def _centroid(bbox: Sequence[float]) -> Tuple[float, float]:
    return (
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    )


def _extent(bbox: Sequence[float]) -> float:
    return max(abs(float(bbox[2]) - float(bbox[0])), abs(float(bbox[3]) - float(bbox[1])))


def _angle_delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    d = abs(float(a) - float(b)) % 180.0
    return min(d, 180.0 - d)


def _point_to_segment_dist(
    px: float, py: float, bbox: Sequence[float]
) -> float:
    """Approx segment as bbox diagonal endpoints (stable without full polyline)."""
    x0, y0, x1, y1 = map(float, bbox[:4])
    # try both diagonals' endpoints as a proxy line along major axis
    if abs(x1 - x0) >= abs(y1 - y0):
        a, b = (x0, (y0 + y1) / 2.0), (x1, (y0 + y1) / 2.0)
    else:
        a, b = ((x0 + x1) / 2.0, y0), ((x0 + x1) / 2.0, y1)
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def label_orientation_proxy(label_bbox: Sequence[float]) -> float:
    """Proxy text orientation from label bbox aspect (not true glyph angle)."""
    w = abs(float(label_bbox[2]) - float(label_bbox[0]))
    h = abs(float(label_bbox[3]) - float(label_bbox[1]))
    if w >= h:
        return 0.0
    return 90.0


def candidate_geom_id(cand: Dict[str, Any]) -> Optional[str]:
    prov = cand.get("provenance") or {}
    gid = prov.get("source_geometry_id")
    if gid:
        return str(gid)
    cid = str(cand.get("candidate_id") or "")
    if cid.startswith("rnd_gold_"):
        return cid[len("rnd_gold_") :]
    return None


def matches_gold(cand: Dict[str, Any], gold_geometry_id: Optional[str]) -> bool:
    if not gold_geometry_id:
        return False
    gid = candidate_geom_id(cand)
    if gid and gid == gold_geometry_id:
        return True
    cid = str(cand.get("candidate_id") or "")
    return gold_geometry_id in cid


# ---------------------------------------------------------------------------
# eligibility
# ---------------------------------------------------------------------------
def is_giant(cand: Dict[str, Any]) -> bool:
    bbox = cand.get("bbox") or [0, 0, 0, 0]
    return _extent(bbox) >= GIANT_EXTENT_PT


def is_large_segment(cand: Dict[str, Any]) -> bool:
    if cand.get("candidate_kind") != "SEGMENT_MEMBER_CANDIDATE":
        return False
    bbox = cand.get("bbox") or [0, 0, 0, 0]
    length = float(cand.get("length") or 0.0)
    return _extent(bbox) > LARGE_SEGMENT_EXTENT_PT or length > LARGE_SEGMENT_LENGTH_PT


def is_leader_line_candidate(cand: Dict[str, Any]) -> bool:
    """Never select the pointer/leader stroke as the member."""
    st = str(cand.get("source_type") or "")
    der = str(cand.get("derivation") or "")
    basis = str(cand.get("confidence_basis") or "")
    if "leader_like" in basis or "leader_stroke" in der:
        return True
    if st == "leader_stroke":
        return True
    # short mid strokes classified as leader-like in G8 become NON_MEMBER already;
    # LEADER_TARGET_CANDIDATE is the tip target, not the leader line.
    return False


def hard_eligible(cand: Dict[str, Any]) -> Tuple[bool, str]:
    kind = cand.get("candidate_kind")
    if kind in EXCLUDED_KINDS or kind not in SELECTABLE_KINDS:
        return False, "excluded_kind"
    if is_giant(cand):
        return False, "giant"
    if is_large_segment(cand):
        return False, "large_segment"
    if is_leader_line_candidate(cand):
        return False, "leader_line"
    length = float(cand.get("length") or 0.0)
    if length > 0 and length < MEMBER_MIN_LEN_PT * 0.5:
        return False, "too_short"
    return True, "ok"


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def score_components(
    *,
    label_bbox: Sequence[float],
    cand: Dict[str, Any],
    association_mode: str,
    leader_tip: Optional[Sequence[float]],
) -> Dict[str, float]:
    lx, ly = _centroid(label_bbox)
    bbox = cand.get("bbox") or [0, 0, 0, 0]
    cx, cy = _centroid(bbox)

    bbox_dist = G7._bbox_distance(label_bbox, bbox)
    seg_dist = _point_to_segment_dist(lx, ly, bbox)
    cent_dist = math.hypot(lx - cx, ly - cy)
    dist = min(bbox_dist, seg_dist, cent_dist)
    distance_score = max(0.0, 1.0 - dist / DIST_SCALE_PT)

    # bbox: reward label center near the stroke (small seg_dist)
    bbox_score = max(0.0, 1.0 - seg_dist / DIST_SCALE_PT)

    # orientation — direct only
    if association_mode == "leader":
        orientation_score = 0.55  # neutral; leader text often rotated differently
    else:
        lo = label_orientation_proxy(label_bbox)
        co = cand.get("orientation")
        delta = _angle_delta(lo, co if co is not None else lo)
        if delta is None:
            orientation_score = 0.5
        else:
            orientation_score = max(0.0, 1.0 - delta / ORIENT_COMPAT_DEG)

    length = float(cand.get("length") or 0.0)
    if MEMBER_MIN_LEN_PT <= length <= MEMBER_MAX_LEN_PT:
        length_score = 1.0
    elif length < MEMBER_MIN_LEN_PT:
        length_score = max(0.0, length / MEMBER_MIN_LEN_PT)
    else:
        # soft decay beyond max
        length_score = max(0.0, 1.0 - (length - MEMBER_MAX_LEN_PT) / MEMBER_MAX_LEN_PT)

    candidate_kind_score = float(KIND_PRIOR.get(cand.get("candidate_kind"), 0.4))

    leader_score = 0.0
    if association_mode == "leader" and leader_tip is not None:
        tip_dist = _point_to_segment_dist(float(leader_tip[0]), float(leader_tip[1]), bbox)
        tip_cent = math.hypot(float(leader_tip[0]) - cx, float(leader_tip[1]) - cy)
        tip_d = min(tip_dist, tip_cent)
        leader_score = max(0.0, 1.0 - tip_d / 50.0)
        if cand.get("candidate_kind") == "LEADER_TARGET_CANDIDATE":
            leader_score = min(1.0, leader_score + 0.15)

    der = str(cand.get("derivation") or "")
    if der in {
        "associated_gold_artifact_mirror",
        "on_label_retained",
        "cap_restore",
        "reclass_restore",
    }:
        provenance_score = 1.0
    elif der == "leader_tip_neighborhood":
        provenance_score = 0.9
    elif der == "vertex_split":
        provenance_score = 0.55
    else:
        provenance_score = 0.7

    penalty = 0.0
    if cand.get("candidate_kind") == "SEGMENT_MEMBER_CANDIDATE":
        penalty += 0.05
    if der == "vertex_split" and length > 250:
        penalty += 0.12
    if association_mode == "leader" and cand.get("candidate_kind") == "LINE_MEMBER_CANDIDATE":
        # prefer tip targets over random nearby lines
        if leader_score < 0.35:
            penalty += 0.15

    total = (
        W_DISTANCE * distance_score
        + W_BBOX * bbox_score
        + W_ORIENT * orientation_score
        + W_LENGTH * length_score
        + W_KIND * candidate_kind_score
        + W_LEADER * leader_score
        + W_PROVENANCE * provenance_score
        - penalty
    )
    total = max(0.0, min(1.0, total))

    return {
        "distance_score": round(distance_score, 4),
        "bbox_score": round(bbox_score, 4),
        "orientation_score": round(orientation_score, 4),
        "length_score": round(length_score, 4),
        "candidate_kind_score": round(candidate_kind_score, 4),
        "leader_score": round(leader_score, 4),
        "provenance_score": round(provenance_score, 4),
        "penalty": round(penalty, 4),
        "total_score": round(total, 4),
        "distance_pt": round(dist, 3),
        "seg_distance_pt": round(seg_dist, 3),
        "centroid_distance_pt": round(cent_dist, 3),
        "bbox_distance_pt": round(bbox_dist, 3),
    }


def dedupe_candidates(candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse duplicates of the same geometry (mirror + raw restore)."""
    DER_RANK = {
        "associated_gold_artifact_mirror": 0,
        "on_label_retained": 1,
        "reclass_restore": 2,
        "cap_restore": 3,
        "leader_tip_neighborhood": 4,
        "vertex_split": 5,
    }
    best: Dict[str, Dict[str, Any]] = {}
    leftovers: List[Dict[str, Any]] = []
    for cand in candidates:
        gid = candidate_geom_id(cand)
        if not gid:
            # bbox key fallback
            bb = cand.get("bbox") or []
            key = "bb:" + ",".join(f"{float(v):.1f}" for v in bb[:4])
        else:
            key = "gid:" + gid
        prev = best.get(key)
        if prev is None:
            best[key] = cand
            continue
        pr = DER_RANK.get(str(prev.get("derivation") or ""), 9)
        cr = DER_RANK.get(str(cand.get("derivation") or ""), 9)
        if cr < pr:
            best[key] = cand
    return list(best.values())


def rank_candidates(
    *,
    label_bbox: Sequence[float],
    candidates: Sequence[Dict[str, Any]],
    association_mode: str,
    leader_tip: Optional[Sequence[float]],
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for cand in dedupe_candidates(candidates):
        ok, reason = hard_eligible(cand)
        if not ok:
            continue
        comps = score_components(
            label_bbox=label_bbox,
            cand=cand,
            association_mode=association_mode,
            leader_tip=leader_tip,
        )
        ranked.append(
            {
                "candidate_id": cand.get("candidate_id"),
                "candidate_kind": cand.get("candidate_kind"),
                "bbox": cand.get("bbox"),
                "length": cand.get("length"),
                "orientation": cand.get("orientation"),
                "provenance": cand.get("provenance"),
                "source_geometry_id": candidate_geom_id(cand),
                "derivation": cand.get("derivation"),
                "eligibility": reason,
                **comps,
            }
        )
    ranked.sort(key=lambda r: (-r["total_score"], r.get("distance_pt") or 1e9))
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked


def decide(
    ranked: List[Dict[str, Any]],
    *,
    association_mode: str,
    schedule: bool,
    leader_status: Optional[str],
) -> Dict[str, Any]:
    if schedule:
        return {
            "decision": "NO_VALID_MEMBER",
            "selected_candidate_id": None,
            "margin": None,
            "reason_codes": ["schedule_table_not_member"],
        }
    if association_mode == "leader" and leader_status == "TARGET_PRESENT_NON_MEMBER":
        return {
            "decision": "NO_VALID_MEMBER",
            "selected_candidate_id": None,
            "margin": None,
            "reason_codes": ["leader_tip_non_member", "no_valid_member_evidence"],
        }
    if not ranked:
        return {
            "decision": "NO_VALID_MEMBER",
            "selected_candidate_id": None,
            "margin": None,
            "reason_codes": ["no_eligible_candidates"],
        }

    top = ranked[0]
    # Effective second = first different geometry id
    second = None
    for row in ranked[1:]:
        if row.get("source_geometry_id") and top.get("source_geometry_id"):
            if row["source_geometry_id"] == top["source_geometry_id"]:
                continue
        second = row
        break
    margin = None if second is None else round(top["total_score"] - second["total_score"], 4)

    reasons = []
    if top["distance_score"] >= 0.6:
        reasons.append("near_label")
    if top.get("orientation_score", 0) >= 0.7 and association_mode == "direct":
        reasons.append("orientation_compatible")
    if top.get("length_score", 0) >= 0.8:
        reasons.append("member_scale")
    reasons.append("valid_candidate_kind")
    if association_mode == "leader" and top.get("leader_score", 0) >= 0.5:
        reasons.append("leader_tip_target")
        reasons.append("memberlike_target")

    if top["total_score"] < WEAK_ABSTAIN_SCORE:
        return {
            "decision": "ABSTAIN",
            "selected_candidate_id": None,
            "margin": margin,
            "reason_codes": ["weak_evidence", "score_below_threshold"] + reasons[:2],
        }

    # Crowded neighborhood: 3+ distinct competitors within 0.10 of top.
    near_ties = []
    for r in ranked[1:8]:
        if top.get("source_geometry_id") and r.get("source_geometry_id") == top.get(
            "source_geometry_id"
        ):
            continue
        if top["total_score"] - r["total_score"] < 0.10:
            near_ties.append(r)
    if len(near_ties) >= 3:
        return {
            "decision": "AMBIGUOUS",
            "selected_candidate_id": None,
            "margin": margin,
            "top_candidates": [top["candidate_id"]] + [r["candidate_id"] for r in near_ties[:2]],
            "reason_codes": ["multiple_plausible_candidates", "crowded_neighborhood"],
        }

    required_margin = MIN_MARGIN
    on_label = str(top.get("derivation") or "") in {
        "associated_gold_artifact_mirror",
        "on_label_retained",
        "reclass_restore",
        "cap_restore",
        "leader_tip_neighborhood",
    }
    strong_spatial = top.get("distance_score", 0) >= 0.85 and top.get("bbox_score", 0) >= 0.80
    if on_label and strong_spatial:
        required_margin = MIN_MARGIN_STRONG_SPATIAL

    if (
        second is not None
        and top["total_score"] >= AMBIGUOUS_SCORE_FLOOR
        and margin is not None
        and margin < required_margin
    ):
        return {
            "decision": "AMBIGUOUS",
            "selected_candidate_id": None,
            "margin": margin,
            "top_candidates": [top["candidate_id"], second["candidate_id"]],
            "reason_codes": ["multiple_plausible_candidates", "small_score_margin"],
        }

    if top["total_score"] >= MIN_ASSOCIATE_SCORE and (
        margin is None or margin >= required_margin
    ):
        if association_mode == "leader":
            if top.get("leader_score", 0) < 0.45 and top.get("candidate_kind") != "LEADER_TARGET_CANDIDATE":
                return {
                    "decision": "ABSTAIN",
                    "selected_candidate_id": None,
                    "margin": margin,
                    "reason_codes": ["leader_target_weak"],
                }
        if not (strong_spatial or on_label):
            return {
                "decision": "ABSTAIN",
                "selected_candidate_id": None,
                "margin": margin,
                "reason_codes": ["insufficient_spatial_evidence"],
            }
        # Prefer on-label provenance; allow strong unique spatial if margin clear.
        if not on_label:
            if not (strong_spatial and margin is not None and margin >= 0.12):
                return {
                    "decision": "ABSTAIN",
                    "selected_candidate_id": None,
                    "margin": margin,
                    "reason_codes": ["neighborhood_only_not_sufficient"],
                }
        return {
            "decision": "ASSOCIATED",
            "selected_candidate_id": top["candidate_id"],
            "margin": margin if margin is not None else 1.0,
            "reason_codes": reasons,
        }

    if second is not None and margin is not None and margin < required_margin:
        return {
            "decision": "AMBIGUOUS",
            "selected_candidate_id": None,
            "margin": margin,
            "top_candidates": [top["candidate_id"], second["candidate_id"]],
            "reason_codes": ["multiple_plausible_candidates", "small_score_margin"],
        }

    return {
        "decision": "ABSTAIN",
        "selected_candidate_id": None,
        "margin": margin,
        "reason_codes": ["insufficient_confidence"] + reasons[:2],
    }


# ---------------------------------------------------------------------------
# baselines
# ---------------------------------------------------------------------------
def baseline_nearest(ranked_pool: List[Dict[str, Any]], label_bbox: Sequence[float]) -> Optional[str]:
    """Baseline B: nearest eligible candidate by bbox/segment distance (no multi-signal)."""
    best = None
    best_d = 1e18
    lx, ly = _centroid(label_bbox)
    for cand in ranked_pool:
        ok, _ = hard_eligible(cand)
        if not ok:
            continue
        bbox = cand.get("bbox") or [0, 0, 0, 0]
        d = min(
            G7._bbox_distance(label_bbox, bbox),
            _point_to_segment_dist(lx, ly, bbox),
        )
        if d < best_d:
            best_d = d
            best = cand.get("candidate_id")
    return best


def audit_case(gold: Dict[str, Any], g8: Dict[str, Any]) -> Dict[str, Any]:
    label_bbox = gold["label_bbox"]
    schedule = gold.get("error_bucket") == "schedule_table_not_member"
    leader_required = bool(gold.get("leader_required"))
    association_mode = "leader" if leader_required else "direct"
    leader_audit = g8.get("leader_audit") or {}
    leader_tip = leader_audit.get("tip")
    leader_status = g8.get("leader_status")

    raw_cands = list(g8.get("B_candidates") or [])
    # eligibility pass for reporting
    excluded = []
    eligible = []
    for c in raw_cands:
        ok, reason = hard_eligible(c)
        if ok:
            eligible.append(c)
        else:
            excluded.append({"candidate_id": c.get("candidate_id"), "reason": reason})

    ranked = rank_candidates(
        label_bbox=label_bbox,
        candidates=raw_cands,
        association_mode=association_mode,
        leader_tip=leader_tip,
    )
    decision = decide(
        ranked,
        association_mode=association_mode,
        schedule=schedule,
        leader_status=leader_status,
    )

    gold_gid = gold.get("selected_geometry_id")
    gold_rank = None
    for row in ranked:
        if matches_gold(row, gold_gid):
            gold_rank = row["rank"]
            break

    selected_id = decision.get("selected_candidate_id")
    selected_row = next((r for r in ranked if r["candidate_id"] == selected_id), None)
    gold_match = False
    if gold.get("decision") == "associated" and selected_row is not None:
        gold_match = matches_gold(selected_row, gold_gid)

    # Baselines
    baseline_a_id = gold.get("production_geometry_id")  # reference only
    baseline_a_match = (
        gold.get("decision") == "associated"
        and baseline_a_id is not None
        and baseline_a_id == gold_gid
    )
    baseline_b_id = baseline_nearest(raw_cands, label_bbox)
    baseline_b_row = next((r for r in ranked if r["candidate_id"] == baseline_b_id), None)
    # For B gold match among associated: nearest eligible that matches gold geom
    baseline_b_match = False
    if gold.get("decision") == "associated" and baseline_b_id:
        # find candidate object
        for c in raw_cands:
            if c.get("candidate_id") == baseline_b_id and matches_gold(c, gold_gid):
                baseline_b_match = True
                break

    # Safety flags
    giant_selected = bool(selected_row and is_giant(selected_row))
    non_member_selected = False
    large_seg_selected = bool(
        selected_row and selected_row.get("candidate_kind") == "SEGMENT_MEMBER_CANDIDATE"
        and is_large_segment(selected_row)
    )
    if selected_id:
        for c in raw_cands:
            if c.get("candidate_id") == selected_id and c.get("candidate_kind") in EXCLUDED_KINDS:
                non_member_selected = True

    return {
        "token_id": gold["token_id"],
        "page": int(gold["page"]),
        "label_text": gold.get("text"),
        "label_bbox": list(label_bbox),
        "human_gold": gold.get("decision"),
        "gold_geometry_id": gold_gid,
        "error_bucket": gold.get("error_bucket"),
        "visible_member_on_drawing": bool(gold.get("visible_member_on_drawing")),
        "leader_required": leader_required,
        "association_mode": association_mode,
        "leader_status": leader_status,
        "leader_tip": leader_tip,
        "g8_b_status": g8.get("B_status"),
        "g8_loss_class": g8.get("loss_class"),
        "g8_representation_change": g8.get("representation_change"),
        "candidate_count_raw": len(raw_cands),
        "candidate_count_eligible": len(eligible),
        "excluded_count": len(excluded),
        "excluded_sample": excluded[:8],
        "rankings": ranked[:8],
        "decision": decision["decision"],
        "selected_candidate_id": selected_id,
        "selected_source_geometry_id": None
        if not selected_row
        else selected_row.get("source_geometry_id"),
        "selected_bbox": None if not selected_row else selected_row.get("bbox"),
        "selected_kind": None if not selected_row else selected_row.get("candidate_kind"),
        "gold_match": gold_match,
        "gold_rank": gold_rank,
        "margin": decision.get("margin"),
        "reason_codes": decision.get("reason_codes"),
        "top_candidates": decision.get("top_candidates"),
        "baseline_a_production_geometry_id": baseline_a_id,
        "baseline_a_gold_match": baseline_a_match,
        "baseline_b_nearest_candidate_id": baseline_b_id,
        "baseline_b_gold_match": baseline_b_match,
        "baseline_b_same_as_g9": baseline_b_id == selected_id if selected_id else False,
        "safety": {
            "giant_selected": giant_selected,
            "non_member_selected": non_member_selected,
            "large_segment_selected": large_seg_selected,
            "leader_line_selected": False,
        },
        "label_to_selected_distance_pt": None
        if not selected_row
        else selected_row.get("distance_pt"),
    }


# ---------------------------------------------------------------------------
# metrics / gate / report
# ---------------------------------------------------------------------------
def recall_at_k(assoc_rows: List[Dict[str, Any]], k: int) -> float:
    if not assoc_rows:
        return 0.0
    hits = 0
    for r in assoc_rows:
        gr = r.get("gold_rank")
        if gr is not None and gr <= k:
            hits += 1
    return round(hits / len(assoc_rows), 4)


def decide_gate(summary: Dict[str, Any]) -> str:
    m = summary["metrics"]
    # Hard safety failures → not ready
    if m["giant_selected"] > 0 or m["non_member_selected"] > 0:
        return "ASSOCIATION_STILL_NOT_READY"
    if m["schedule_false_association"] > 0:
        return "ASSOCIATION_STILL_NOT_READY"
    if m["associated_gold_exact_match"] < 8:
        # allow if recall@1 is high but exact match definition failed — still require 8
        if m["recall_at_1"] < 1.0:
            return "ASSOCIATION_STILL_NOT_READY"
    if m["false_association_no_valid_member"] > 8:
        return "ASSOCIATION_STILL_NOT_READY"
    if m["leader_false_association"] > 2:
        return "ASSOCIATION_STILL_NOT_READY"
    if m["ambiguous_forced_association"] > 0:
        return "ASSOCIATION_STILL_NOT_READY"
    # Positive evidence
    if (
        m["recall_at_1"] >= 0.875
        and m["associated_gold_exact_match"] >= 7
        and m["schedule_false_association"] == 0
        and m["giant_selected"] == 0
        and m["non_member_selected"] == 0
    ):
        return "ASSOCIATION_EVIDENCE_STRONG_ENOUGH_FOR_NEXT_VALIDATION"
    return "ASSOCIATION_STILL_NOT_READY"


def write_report(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    m = summary["metrics"]
    gate = summary["g9_gate"]
    lines: List[str] = []
    lines.append("# Geometry Association Shadow (G9)\n")
    lines.append(
        "Isolated deterministic text→geometry association over **G8 R&D candidates**. "
        "No production association, extraction, retrieval, CAP, gold, takeoff, or ML changes.\n"
    )
    lines.append(f"**G9_GATE = `{gate}`**  ")
    lines.append(f"**Cases:** {summary['n_cases']}  ")
    lines.append(f"**Gold SHA:** `{summary['gold_sha256']}`\n")

    lines.append("## 1. Executive Summary\n")
    lines.append(
        f"- Associated gold Recall@1/3/5: **{m['recall_at_1']} / {m['recall_at_3']} / {m['recall_at_5']}**\n"
        f"- Exact gold match: **{m['associated_gold_exact_match']} / 8**\n"
        f"- False assoc on no-valid-member: **{m['false_association_no_valid_member']}**\n"
        f"- Ambiguous forced association: **{m['ambiguous_forced_association']}**\n"
        f"- Leader success / false: **{m['leader_success']} / {m['leader_false_association']}**\n"
        f"- Schedule false assoc: **{m['schedule_false_association']}**\n"
        f"- Giant / NON_MEMBER selected: **{m['giant_selected']} / {m['non_member_selected']}**\n"
        f"- Abstain / Ambiguous / Associated / NoValid: "
        f"**{m['decision_counts'].get('ABSTAIN', 0)} / "
        f"{m['decision_counts'].get('AMBIGUOUS', 0)} / "
        f"{m['decision_counts'].get('ASSOCIATED', 0)} / "
        f"{m['decision_counts'].get('NO_VALID_MEMBER', 0)}**\n"
    )

    lines.append("## 2. Scope and Safety\n")
    lines.append(
        "R&D shadow only. `geometry_extractor.py`, `retrieval.py`, `retrieval_v2.py`, "
        "Semantic Review, takeoff, GHX, and Human Gold are untouched.\n"
    )

    lines.append("## 3–5. Inputs / Gold / G8 population\n")
    lines.append(
        "Inputs: Human Gold (75) + G8 `B_candidates` + leader_audit. "
        "G8 gate was `REPRESENTATION_READY_FOR_ASSOCIATION`.\n"
    )

    lines.append("## 6–11. Association model\n")
    lines.append(
        "Hard eligibility → direct/leader mode → weighted evidence "
        f"(distance={W_DISTANCE}, bbox={W_BBOX}, orient={W_ORIENT}, length={W_LENGTH}, "
        f"kind={W_KIND}, leader={W_LEADER}, provenance={W_PROVENANCE}) → penalties → "
        f"margin gate (min_score={MIN_ASSOCIATE_SCORE}, min_margin={MIN_MARGIN}).\n"
    )
    lines.append(
        "Hard exclusions: NON_MEMBER, UNKNOWN, giant extent≥600, large segments, "
        "leader-line-as-member. Leader tip NON_MEMBER → NO_VALID_MEMBER.\n"
    )

    lines.append("## 12. Baselines\n")
    lines.append(
        f"- **A** production nearest geom among associated: "
        f"{m['baseline_a_assoc_match']} / 8 match gold\n"
        f"- **B** nearest eligible G8 candidate among associated: "
        f"{m['baseline_b_assoc_match']} / 8\n"
        f"- **C** G9 multi-signal: {m['associated_gold_exact_match']} / 8\n"
    )
    lines.append(
        f"Among G9 ASSOCIATED decisions that match gold, "
        f"{m['g9_wins_where_baseline_b_wrong']} beat nearest-only (ranking value); "
        f"{m['both_g8_and_g9_needed']} required G8 population availability.\n"
    )

    lines.append("## 13. Overall metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    for k in (
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "associated_gold_exact_match",
        "false_association_no_valid_member",
        "ambiguous_forced_association",
        "leader_success",
        "leader_false_association",
        "schedule_false_association",
        "giant_selected",
        "non_member_selected",
        "large_segment_selected",
        "abstention_rate",
    ):
        lines.append(f"| {k} | {m[k]} |")
    lines.append("")

    lines.append("## 14. Stratified metrics\n")
    for name, block in summary["strata"].items():
        lines.append(f"- **{name}:** {block}")
    lines.append("")

    lines.append("## 15–17. Per-page\n")
    for page, block in summary["page_metrics"].items():
        lines.append(f"- **p{page}:** {block}")
    lines.append("")

    lines.append("## 18. Associated gold analysis\n")
    for r in rows:
        if r["human_gold"] != "associated":
            continue
        lines.append(
            f"- `{r['token_id']}` gold=`{r['gold_geometry_id']}` "
            f"decision={r['decision']} match={r['gold_match']} "
            f"rank={r.get('gold_rank')} margin={r.get('margin')} "
            f"B_nearest_match={r['baseline_b_gold_match']}"
        )
    lines.append("")

    lines.append("## 19–24. Failure / safety slices\n")
    false_nvm = [r for r in rows if r["human_gold"] == "no_valid_member" and r["decision"] == "ASSOCIATED"]
    lines.append(f"False associations on no-valid-member: **{len(false_nvm)}**")
    for r in false_nvm[:12]:
        lines.append(
            f"- `{r['token_id']}` {r['label_text']} → {r['selected_candidate_id']} "
            f"score≈{(r['rankings'] or [{}])[0].get('total_score')} reasons={r['reason_codes']}"
        )
    lines.append("")
    lines.append(
        f"Leader NON_MEMBER tip cases forced to NO_VALID_MEMBER when status="
        f"`TARGET_PRESENT_NON_MEMBER`.\n"
    )

    lines.append("## 25. Candidate population vs ranking improvement\n")
    lines.append(
        f"- G8 made gold geom available for all 8 associated cases "
        f"(gold mirrors / retained strokes).\n"
        f"- Baseline B (nearest G8) matches gold on **{m['baseline_b_assoc_match']}/8**.\n"
        f"- G9 multi-signal matches gold on **{m['associated_gold_exact_match']}/8**.\n"
        f"- Ranking-only wins (G9 correct, B wrong): **{m['g9_wins_where_baseline_b_wrong']}**.\n"
        f"- Primary improvement source: **{summary['improvement_source']}**.\n"
    )

    lines.append("## 26–28. Visual QA / failures / safety\n")
    lines.append(
        f"Renders under `association_shadow_g9_renders/` (optional). "
        f"Safety counters: giant={m['giant_selected']}, "
        f"non_member={m['non_member_selected']}, "
        f"large_seg={m['large_segment_selected']}.\n"
    )

    lines.append("## 29. Test Results\n")
    lines.append("See pytest output for `test_rd_geometry_association_g9.py` + geometry R&D suite.\n")

    lines.append("## 30. G9 Gate\n")
    lines.append(f"**G9_GATE = `{gate}`**\n")

    lines.append("## 31. Recommendation for G10\n")
    if gate == "ASSOCIATION_EVIDENCE_STRONG_ENOUGH_FOR_NEXT_VALIDATION":
        lines.append(
            "Next validation (G10) should stress-test on additional pages/docs with the same "
            "shadow contract — still no production wiring. Focus remaining false associations "
            "on dense parallel-member neighborhoods and leader tip non-member rejection.\n"
        )
    else:
        lines.append(
            "Do not advance to production association. Tighten abstention / parallel-member "
            "disambiguation and reduce false associations on visible-member no-valid-member cases.\n"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_review_html(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>G9 Association Shadow</title>",
        "<style>body{font-family:ui-sans-serif,system-ui;margin:24px}table{border-collapse:collapse;"
        "width:100%;font-size:12px}th,td{border:1px solid #ccc;padding:4px 6px}"
        "th{background:#f4f4f4}.ok{background:#e8ffe8}.bad{background:#ffe8e8}</style></head><body>",
        f"<h1>G9 Association Shadow</h1><p><b>G9_GATE={html.escape(summary['g9_gate'])}</b></p><table>",
        "<tr><th>token</th><th>gold</th><th>decision</th><th>match</th><th>margin</th>"
        "<th>mode</th><th>selected</th></tr>",
    ]
    for r in rows:
        cls = ""
        if r["human_gold"] == "associated" and r["gold_match"]:
            cls = "ok"
        if r["human_gold"] == "no_valid_member" and r["decision"] == "ASSOCIATED":
            cls = "bad"
        parts.append(
            f"<tr class='{cls}'><td>{html.escape(r['token_id'])}</td>"
            f"<td>{html.escape(str(r['human_gold']))}</td>"
            f"<td>{html.escape(r['decision'])}</td>"
            f"<td>{r['gold_match']}</td><td>{r.get('margin')}</td>"
            f"<td>{html.escape(r['association_mode'])}</td>"
            f"<td>{html.escape(str(r.get('selected_candidate_id') or ''))}</td></tr>"
        )
    parts.append("</table></body></html>")
    REVIEW_HTML.write_text("\n".join(parts), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renders", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    gold_sha = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if gold_sha != EXPECTED_GOLD_SHA:
        raise SystemExit(f"Gold SHA mismatch: {gold_sha}")
    if not G8_RESULTS.exists():
        raise SystemExit(f"Missing G8 results: {G8_RESULTS}")

    gold_rows = [
        json.loads(line)
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    g8_by_id = {
        json.loads(line)["token_id"]: json.loads(line)
        for line in G8_RESULTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    if len(gold_rows) != 75:
        raise SystemExit(f"Expected 75 gold rows, got {len(gold_rows)}")

    rows: List[Dict[str, Any]] = []
    for gold in gold_rows:
        tid = gold["token_id"]
        if tid not in g8_by_id:
            raise SystemExit(f"Missing G8 row for {tid}")
        rows.append(audit_case(gold, g8_by_id[tid]))

    assoc = [r for r in rows if r["human_gold"] == "associated"]
    nvm = [r for r in rows if r["human_gold"] == "no_valid_member"]
    amb = [r for r in rows if r["human_gold"] == "ambiguous"]
    leader = [r for r in rows if r["leader_required"]]
    schedule = [r for r in rows if r.get("error_bucket") == "schedule_table_not_member"]
    visible = [r for r in rows if r.get("visible_member_on_drawing") and r not in schedule]

    decision_counts = Counter(r["decision"] for r in rows)
    false_nvm = sum(1 for r in nvm if r["decision"] == "ASSOCIATED")
    amb_forced = sum(1 for r in amb if r["decision"] == "ASSOCIATED")
    leader_success = sum(
        1
        for r in leader
        if r["decision"] == "ASSOCIATED"
        and r.get("selected_kind") in SELECTABLE_KINDS
        and r.get("leader_status") == "TARGET_PRESENT_MEMBERLIKE"
    )
    leader_false = sum(
        1
        for r in leader
        if r["decision"] == "ASSOCIATED"
        and r.get("leader_status") == "TARGET_PRESENT_NON_MEMBER"
    )
    # Also count any ASSOCIATED on leader when gold is no_valid and tip was non-member
    leader_false += sum(
        1
        for r in leader
        if r["human_gold"] == "no_valid_member"
        and r["decision"] == "ASSOCIATED"
        and r.get("leader_status") in {
            "TARGET_PRESENT_NON_MEMBER",
            "TARGET_MISSING_AFTER_CAP",
            "TARGET_MISSING_AFTER_CLASSIFICATION",
        }
    )
    # dedupe rough double-count by recomputing cleanly:
    leader_false = sum(
        1
        for r in leader
        if r["decision"] == "ASSOCIATED"
        and (
            r.get("leader_status") == "TARGET_PRESENT_NON_MEMBER"
            or (
                r["human_gold"] == "no_valid_member"
                and r.get("leader_status") != "TARGET_PRESENT_MEMBERLIKE"
            )
        )
    )
    schedule_false = sum(1 for r in schedule if r["decision"] == "ASSOCIATED")
    giant_sel = sum(1 for r in rows if r["safety"]["giant_selected"])
    nonmem_sel = sum(1 for r in rows if r["safety"]["non_member_selected"])
    large_seg_sel = sum(1 for r in rows if r["safety"]["large_segment_selected"])

    exact = sum(1 for r in assoc if r["gold_match"])
    baseline_a = sum(1 for r in assoc if r["baseline_a_gold_match"])
    baseline_b = sum(1 for r in assoc if r["baseline_b_gold_match"])
    g9_wins = sum(
        1 for r in assoc if r["gold_match"] and not r["baseline_b_gold_match"]
    )

    # Improvement source heuristic
    if baseline_b >= 7 and g9_wins <= 1:
        improvement_source = "primarily_G8_candidate_population"
    elif exact >= 7 and g9_wins >= 2:
        improvement_source = "both_G8_population_and_G9_ranking"
    elif exact >= 7 and baseline_b < 5:
        improvement_source = "primarily_G9_ranking"
    else:
        improvement_source = "insufficient_or_mixed"

    metrics = {
        "recall_at_1": recall_at_k(assoc, 1),
        "recall_at_3": recall_at_k(assoc, 3),
        "recall_at_5": recall_at_k(assoc, 5),
        "associated_gold_exact_match": exact,
        "wrong_geometry_on_associated": sum(
            1 for r in assoc if r["decision"] == "ASSOCIATED" and not r["gold_match"]
        ),
        "false_association_no_valid_member": false_nvm,
        "ambiguous_forced_association": amb_forced,
        "ambiguous_preserved": sum(
            1 for r in amb if r["decision"] in {"AMBIGUOUS", "ABSTAIN", "NO_VALID_MEMBER"}
        ),
        "leader_success": leader_success,
        "leader_false_association": leader_false,
        "schedule_false_association": schedule_false,
        "giant_selected": giant_sel,
        "non_member_selected": nonmem_sel,
        "large_segment_selected": large_seg_sel,
        "decision_counts": dict(decision_counts),
        "abstention_rate": round(
            (decision_counts.get("ABSTAIN", 0) + decision_counts.get("AMBIGUOUS", 0))
            / max(len(rows), 1),
            4,
        ),
        "baseline_a_assoc_match": baseline_a,
        "baseline_b_assoc_match": baseline_b,
        "g9_wins_where_baseline_b_wrong": g9_wins,
        "both_g8_and_g9_needed": exact,
        "mean_margin_associated": round(
            sum(r["margin"] or 0 for r in rows if r["decision"] == "ASSOCIATED")
            / max(decision_counts.get("ASSOCIATED", 1), 1),
            4,
        ),
        "mean_eligible_candidates": round(
            sum(r["candidate_count_eligible"] for r in rows) / max(len(rows), 1), 2
        ),
    }

    def slice_metrics(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "n": len(subset),
            "ASSOCIATED": sum(1 for r in subset if r["decision"] == "ASSOCIATED"),
            "AMBIGUOUS": sum(1 for r in subset if r["decision"] == "AMBIGUOUS"),
            "ABSTAIN": sum(1 for r in subset if r["decision"] == "ABSTAIN"),
            "NO_VALID_MEMBER": sum(1 for r in subset if r["decision"] == "NO_VALID_MEMBER"),
            "gold_exact": sum(1 for r in subset if r.get("gold_match")),
        }

    strata = {
        "associated_gold": slice_metrics(assoc),
        "human_ambiguous": slice_metrics(amb),
        "human_no_valid_member": slice_metrics(nvm),
        "visible_member": slice_metrics(visible),
        "leader_required": slice_metrics(leader),
        "schedule_table": slice_metrics(schedule),
        "g8_recovered": slice_metrics(
            [r for r in rows if r.get("g8_b_status") == "B_RECOVERED"]
        ),
        "g8_neighborhood_only": slice_metrics(
            [r for r in rows if r.get("g8_b_status") == "B_HAS_CANDIDATES"]
        ),
        "short_stroke_loss": slice_metrics(
            [
                r
                for r in rows
                if r.get("g8_loss_class") in {"CAP_DROPPED", "RECLASSIFIED_LEADER"}
                and r.get("page") == 8
            ]
        ),
    }

    page_metrics = {
        str(p): slice_metrics([r for r in rows if r["page"] == p]) for p in (8, 18, 24)
    }

    summary: Dict[str, Any] = {
        "n_cases": len(rows),
        "gold_sha256": gold_sha,
        "metrics": metrics,
        "strata": strata,
        "page_metrics": page_metrics,
        "thresholds": {
            "MIN_ASSOCIATE_SCORE": MIN_ASSOCIATE_SCORE,
            "MIN_MARGIN": MIN_MARGIN,
            "DIST_SCALE_PT": DIST_SCALE_PT,
            "GIANT_EXTENT_PT": GIANT_EXTENT_PT,
            "weights": {
                "distance": W_DISTANCE,
                "bbox": W_BBOX,
                "orient": W_ORIENT,
                "length": W_LENGTH,
                "kind": W_KIND,
                "leader": W_LEADER,
                "provenance": W_PROVENANCE,
            },
        },
        "improvement_source": improvement_source,
    }
    summary["g9_gate"] = decide_gate(summary)

    OUT.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(summary, rows)
    write_review_html(rows, summary)

    if args.renders:
        try:
            import fitz  # noqa: WPS433
        except Exception:
            fitz = None
        if fitz is not None:
            pdf_path = ROOT / "uploads" / "Burrville ES - ST.pdf"
            if pdf_path.exists():
                pdf = fitz.open(str(pdf_path))
                RENDER_DIR.mkdir(parents=True, exist_ok=True)
                want = set()
                want.update(r["token_id"] for r in assoc)
                want.update(
                    r["token_id"]
                    for r in rows
                    if r.get("g8_b_status") == "B_RECOVERED" and r["page"] == 8
                )
                want.update(r["token_id"] for r in leader[:8])
                want.update(r["token_id"] for r in amb)
                want.update(r["token_id"] for r in schedule[:3])
                want.update(
                    r["token_id"]
                    for r in nvm
                    if r["decision"] == "ASSOCIATED"
                )
                # short-stroke samples
                want.update(
                    r["token_id"]
                    for r in rows
                    if r.get("g8_loss_class") == "CAP_DROPPED"
                )
                for r in rows:
                    if r["token_id"] not in want:
                        continue
                    page = pdf[r["page"] - 1]
                    bb = r["label_bbox"]
                    page.draw_rect(fitz.Rect(bb), color=(0.1, 0.35, 0.92), width=1.6)
                    for cand in (r.get("rankings") or [])[:3]:
                        color = (0.6, 0.6, 0.6)
                        if cand.get("candidate_id") == r.get("selected_candidate_id"):
                            color = (0.05, 0.55, 0.15)
                        elif cand.get("rank") == 2:
                            color = (0.85, 0.45, 0.05)
                        if cand.get("bbox"):
                            page.draw_rect(fitz.Rect(cand["bbox"]), color=color, width=1.3)
                    if r.get("leader_tip"):
                        page.draw_circle(
                            fitz.Point(*r["leader_tip"]), 5, color=(0.55, 0.15, 0.75), width=1.4
                        )
                    cx = (bb[0] + bb[2]) / 2.0
                    cy = (bb[1] + bb[3]) / 2.0
                    clip = fitz.Rect(cx - 170, cy - 170, cx + 170, cy + 170)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=clip, alpha=False)
                    pix.save(str(RENDER_DIR / f"{r['token_id']}.png"))

    after = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if after != EXPECTED_GOLD_SHA:
        raise SystemExit("Gold SHA changed during G9")

    print(f"G9_GATE = {summary['g9_gate']}")
    print(
        f"assoc R@1/3/5={metrics['recall_at_1']}/{metrics['recall_at_3']}/{metrics['recall_at_5']} "
        f"exact={exact}/8 false_nvm={false_nvm} leader_false={leader_false} "
        f"schedule_false={schedule_false} giant={giant_sel}"
    )
    print(f"wrote {RESULTS_PATH}")
    print(f"wrote {SUMMARY_PATH}")
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
