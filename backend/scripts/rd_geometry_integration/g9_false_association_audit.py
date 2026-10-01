#!/usr/bin/env python3
"""G9 false-association forensic audit (R&D, read-only).

Audits the 27 G9 cases where human gold = no_valid_member and G9 = ASSOCIATED,
under the frozen G8 candidate universe. Does NOT modify gold, G8, G9 scoring,
production extraction, or association.

Usage (from backend/):
    python scripts/rd_geometry_integration/g9_false_association_audit.py [--renders]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
AUDIT_DIR = OUT_ROOT / "g9_false_association_audit"
GOLD_PATH = OUT_ROOT / "review_kit" / "gold_outcomes.jsonl"
G8_PATH = OUT_ROOT / "representation_repair_g8_results.jsonl"
G9_PATH = OUT_ROOT / "association_shadow_g9_results.jsonl"
G9_SUMMARY = OUT_ROOT / "association_shadow_g9_summary.json"
RESULTS_PATH = AUDIT_DIR / "g9_false_association_audit.jsonl"
SUMMARY_PATH = AUDIT_DIR / "g9_false_association_audit_summary.json"
REPORT_PATH = AUDIT_DIR / "G9_FALSE_ASSOCIATION_AUDIT_REPORT.md"
REVIEW_HTML = AUDIT_DIR / "review.html"
RENDER_DIR = AUDIT_DIR / "renders"
INPUT_LIST_PATH = AUDIT_DIR / "g9_false_association_input_list.json"

EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
EXPECTED_FA_COUNT = 27
CLASSIFICATIONS = {"A", "B", "C", "D"}
CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}
NEW_STATUSES = {
    "NO_VALID_MEMBER_REMAINS",
    "VALID_MEMBER_NOW_VISIBLE",
    "MULTIPLE_VALID_CANDIDATES",
    "CORRECT_MEMBER_EXISTS_BUT_G9_SELECTED_WRONG_ONE",
}

# Frozen forensic verdicts (visual + G8/G9 traces). Do not auto-rewrite gold.
# Each entry: classification, confidence, new_representation_status, reason,
# old_representation_issue, best_candidate_strategy, notes, d_meta (optional).
VERDICTS: Dict[str, Dict[str, Any]] = {
    "token_p8_336": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on the W21X50 girder; G8 reclass_restore recovers the "
            "under-label stroke previously classified as dimension. Old gold "
            "overlays were distant infill/stair, not this girder."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Horizontal W21X50 text rests on the recovered horizontal girder stroke (G9 green).",
    },
    "token_p8_337": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_LEADER",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on the upper W21X44 girder. Under-label raw was a leader "
            "stub; G8 neighborhood reclass recovers the girder segment G9 selected."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "On-label girder geometry now present; old candidates were giant bay/EJ wall.",
    },
    "token_p8_341": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 joist; G8 reclass_restore recovers the on-label "
            "joist previously treated as dimension. Old overlays were EJ wall / wall beam."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Selected stroke coincides with the labeled joist path.",
    },
    "token_p8_343": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 joist; G8 recovers that joist via reclass_restore. "
            "Old overlays were distant infill / W21X44 wall."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "On-label joist recovered; not the wall beam.",
    },
    "token_p8_345": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "Short W10X15 joist under the label was CAP-dropped; G8 cap_restore "
            "returns the ~75pt stroke G9 associates. Old gold had no short-joist candidate."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Short on-label joist between girders matches selected length/orientation.",
    },
    "token_p8_346": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "Mirror of p8_345: CAP-dropped short W10X15 under label recovered by G8 "
            "cap_restore; previously absent from association candidates."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Short joist under label; G9 selects recovered CAP stroke.",
    },
    "token_p8_347": {
        "classification": "B",
        "confidence": "MEDIUM",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 joist. Under-label raw was CAP-dropped leader stub; "
            "G8 neighborhood reclass recovers a member-scale joist stroke G9 selects. "
            "Crowded bay has other long strokes, but selected matches the labeled joist scale."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Joist under label now candidate; old overlays were S-311 callout / giant polyline.",
    },
    "token_p8_352": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 girder; G8 recovers a ~109pt member-scale stroke under "
            "the label (neighborhood after CAP drop). Old candidates were callout/giant polyline."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "On-label girder segment recovered; not S-311/S-401 callouts.",
    },
    "token_p8_354": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_LEADER",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W18X35 joist; G8 reclass_restore recovers that joist after "
            "leader misclass. Old overlays were distant infill / wall."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Selected joist path aligns with on-label W18X35.",
    },
    "token_p8_356": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 girder; G8 reclass recovers the girder previously "
            "classified as dimension. Old overlays were W14/W12 infills."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Girder under label recovered via reclass_restore.",
    },
    "token_p8_361": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 joist; G8 recovers on-label joist (was dimension). "
            "Old green/orange were EJ wall / tall wall box."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "On-label joist, not the EJ wall member.",
    },
    "token_p8_363": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 joist; only old candidate was a giant bay polyline. "
            "G8 reclass_restore exposes the joist stroke G9 selects."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Joist under label now present; giant bay no longer the only option.",
    },
    "token_p8_369": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 joist; G8 recovers it from dimension class. Old overlay "
            "was the W21X44 wall beam."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Selected equals on-label joist, not wall beam.",
    },
    "token_p8_371": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "Short W10X15 under label was CAP-dropped; G8 cap_restore recovers ~75pt stroke. "
            "Old overlay was W14X22 infill."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Short on-label joist matches CAP restore.",
    },
    "token_p8_372": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "Short W10X15 CAP-dropped; G8 recovers joist. Old green/orange were W14X22 "
            "infill and stair, not the joist."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Recovered short joist under label.",
    },
    "token_p8_381": {
        "classification": "C",
        "confidence": "MEDIUM",
        "new_representation_status": "MULTIPLE_VALID_CANDIDATES",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "none",
        "reason": (
            "G8 recovers multiple parallel W18-scale joist strokes that all touch the "
            "label neighborhood (same-scale competitors at ~0 distance). PDF shows a "
            "dense parallel bay; ownership of a single stroke is not deterministic "
            "from geometry alone even though a member is visible."
        ),
        "notes": "Unresolved under new representation; do not force ASSOCIATED or NO_VALID_MEMBER.",
        "visual_review": "Parallel W18 joists; several reclass_restore candidates equally memberlike.",
    },
    "token_p8_382": {
        "classification": "C",
        "confidence": "MEDIUM",
        "new_representation_status": "MULTIPLE_VALID_CANDIDATES",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "none",
        "reason": (
            "Parallel W18X35 bay: top-3 G8 candidates are same-scale joist strokes with "
            "near-zero label distance and thin G9 margin (~0.08). Deterministic ownership "
            "not established."
        ),
        "notes": "Unresolved under new representation; do not force ASSOCIATED or NO_VALID_MEMBER.",
        "visual_review": "Repeated parallel joists; selected not uniquely owned by visual topology alone.",
    },
    "token_p8_383": {
        "classification": "C",
        "confidence": "MEDIUM",
        "new_representation_status": "MULTIPLE_VALID_CANDIDATES",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "none",
        "reason": (
            "Same parallel-bay pattern as neighboring W18 labels: multiple recovered "
            "member-scale strokes compete at the label. Ambiguous under G8 universe."
        ),
        "notes": "Unresolved under new representation; do not force ASSOCIATED or NO_VALID_MEMBER.",
        "visual_review": "Crowded parallel W18s; no unique owner proven.",
    },
    "token_p8_384": {
        "classification": "C",
        "confidence": "MEDIUM",
        "new_representation_status": "MULTIPLE_VALID_CANDIDATES",
        "old_representation_issue": "OTHER",
        "best_candidate_strategy": "none",
        "reason": (
            "W18X40 among parallel W18X40s. Selected stroke was already a retained "
            "member line, but several similar-length retained/recovered strokes also "
            "touch the label. Gold overlays showed SOG/wall; under G8 the bay remains "
            "multi-candidate ambiguous."
        ),
        "notes": "Unresolved under new representation; retained-member presence ≠ unique ownership.",
        "visual_review": "Parallel identical W18X40s; contact alone does not pick one deterministically.",
    },
    "token_p8_399": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "Short W10X15 CAP-dropped under label; G8 cap_restore recovers it. Old "
            "overlays were W14X22 infill / stair."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Short on-label joist recovered.",
    },
    "token_p8_410": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "W10X15 at wall CAP-dropped; G8 recovers short stroke. Old overlays were "
            "W16X31 / W21X44 wall members."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Short wall-adjacent joist under label.",
    },
    "token_p8_411": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "W10X15 CAP-dropped; G8 recovers short joist. Old overlay was W16X31 at EJ."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Recovered short joist distinct from EJ W16X31.",
    },
    "token_p8_412": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "W10X15 CAP-dropped; G8 recovers short joist. Old overlay was W16X31 at EJ."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "Recovered short joist under label.",
    },
    "token_p8_419": {
        "classification": "B",
        "confidence": "MEDIUM",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "selected",
        "reason": (
            "Label sits on W16X26 joist; G8 reclass recovers that stroke (was dimension). "
            "Nearby longer wall/infill strokes compete but selected matches under-label "
            "raw_trace reclass of the joist."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE.",
        "visual_review": "On-label joist recovered; wall beam was the old false overlay.",
    },
    "token_p8_430": {
        "classification": "C",
        "confidence": "MEDIUM",
        "new_representation_status": "MULTIPLE_VALID_CANDIDATES",
        "old_representation_issue": "RECLASSIFIED_DIMENSION",
        "best_candidate_strategy": "none",
        "reason": (
            "Parallel W18 bay with ≥4 same-scale recovered strokes at near-zero label "
            "distance and thin margin. Member geometry is present, but ownership of one "
            "specific joist is not deterministic."
        ),
        "notes": "Unresolved under new representation; do not force ASSOCIATED or NO_VALID_MEMBER.",
        "visual_review": "Dense parallel W18s; multiple plausible joist candidates.",
    },
    "token_p18_1188": {
        "classification": "B",
        "confidence": "HIGH",
        "new_representation_status": "VALID_MEMBER_NOW_VISIBLE",
        "old_representation_issue": "CAP_DROPPED",
        "best_candidate_strategy": "selected",
        "reason": (
            "Leader points to the embed plate. G9 selects the CAP-restored tip stroke "
            "(tip_distance=0) that coincides with the plate edge; that stroke was absent "
            "from the retained CAP set. Old gold overlays were studs/rebar, not the plate."
        ),
        "notes": "Gold remains unchanged; candidate-universe reinterpretation only. OLD_GOLD_STALE_CANDIDATE_UNIVERSE. SHORT_STROKE_RECOVERY at leader tip.",
        "visual_review": "Leader tip lands on recovered plate-edge stroke (G9 green + purple tip).",
    },
    "token_p24_1359": {
        "classification": "D",
        "confidence": "HIGH",
        "new_representation_status": "CORRECT_MEMBER_EXISTS_BUT_G9_SELECTED_WRONG_ONE",
        "old_representation_issue": "RAW_AMBIGUOUS",
        "best_candidate_strategy": "fixed_id",
        "best_candidate_id": "raw_p24_10_9d8fbf0dfe5b#seg1",
        "reason": (
            "Leader targets the small L6 relieving angle. G9 ASSOCIATED a 405pt vertical "
            "wall/hatch line (on_label_retained). Short plate/angle segments exist in G8 "
            "(rank-2 vertex_split seg from tip plate_or_symbol; additional CAP short strokes). "
            "Selected geometry is clearly the long brick/wall line, not the angle."
        ),
        "notes": "True G9 ranking/decision error under G8 universe. Characterizes a future G10 policy issue (leader tip short-target vs long wall).",
        "visual_review": "Blue label L6x3-1/2x3/8; selected long vertical wall; short angle segments available near tip.",
        "d_meta": {
            "main_reason_for_wrong_selection": (
                "Leader/length scoring favored long wall line near tip over short "
                "angle/plate segment candidates."
            ),
        },
    },
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _centroid(bbox: Sequence[float]) -> Tuple[float, float]:
    return ((float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0)


def discover_false_associations(g9_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    fa = [
        r
        for r in g9_rows
        if r.get("human_gold") == "no_valid_member" and r.get("decision") == "ASSOCIATED"
    ]
    fa = sorted(fa, key=lambda r: (int(r.get("page") or 0), str(r.get("token_id") or "")))
    return fa


def _cand_summary(c: Dict[str, Any], rankings_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    cid = c.get("candidate_id")
    rk = rankings_by_id.get(cid or "", {})
    prov = c.get("provenance") or {}
    bbox = c.get("bbox") or []
    return {
        "candidate_id": cid,
        "candidate_kind": c.get("candidate_kind"),
        "derivation": c.get("derivation") or prov.get("derivation_type"),
        "provenance": {
            "source_raw_id": prov.get("source_raw_id") or c.get("source_raw_id"),
            "source_geometry_id": prov.get("source_geometry_id"),
            "derivation_type": prov.get("derivation_type") or c.get("derivation"),
            "current_kind": prov.get("current_kind"),
            "retained_by_cap": prov.get("retained_by_cap"),
        },
        "bbox": bbox,
        "centroid": list(_centroid(bbox)) if len(bbox) >= 4 else None,
        "length": c.get("length"),
        "orientation": c.get("orientation"),
        "g9_rank": rk.get("rank"),
        "g9_total_score": rk.get("total_score"),
        "distance_pt": rk.get("distance_pt"),
        "score_breakdown": {
            "distance_score": rk.get("distance_score"),
            "bbox_score": rk.get("bbox_score"),
            "orientation_score": rk.get("orientation_score"),
            "length_score": rk.get("length_score"),
            "candidate_kind_score": rk.get("candidate_kind_score"),
            "leader_score": rk.get("leader_score"),
            "provenance_score": rk.get("provenance_score"),
            "penalty": rk.get("penalty"),
        }
        if rk
        else None,
    }


def _old_universe_proof(g8: Dict[str, Any], selected: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    rt = g8.get("raw_trace") or {}
    sel_prov = (selected or {}).get("provenance") or {}
    loss = g8.get("loss_class")
    a_status = g8.get("A_status")
    der = (selected or {}).get("derivation")
    reason = "OTHER"
    if loss == "CAP_DROPPED" or der == "cap_restore" or a_status == "A_CAP_DROPPED":
        reason = "CAP_DROPPED"
    elif loss == "RECLASSIFIED_DIMENSION" or (
        der == "reclass_restore" and rt.get("current_kind") == "dimension"
    ):
        reason = "RECLASSIFIED_DIMENSION"
    elif loss == "RECLASSIFIED_LEADER" or (
        der == "reclass_restore" and rt.get("current_kind") == "leader"
    ):
        reason = "RECLASSIFIED_LEADER"
    elif der == "vertex_split":
        reason = "SEGMENT_RECOVERY"
    elif der == "cap_restore":
        reason = "SHORT_STROKE_RECOVERY"
    elif loss == "RETAINED_MEMBER":
        reason = "OTHER"
    elif loss == "RAW_AMBIGUOUS":
        reason = "OTHER"

    return {
        "old_A_status": a_status,
        "old_loss_class": loss,
        "old_current_kind": rt.get("current_kind"),
        "old_retained_by_cap": rt.get("retained_by_cap"),
        "old_raw_id": rt.get("raw_geometry_id_or_index"),
        "old_final_geometry_id": rt.get("current_final_geometry_id"),
        "new_selected_id": (selected or {}).get("candidate_id"),
        "new_derivation": der,
        "new_source_raw_id": sel_prov.get("source_raw_id"),
        "new_source_geometry_id": sel_prov.get("source_geometry_id"),
        "unavailable_reason": reason,
        "selected_absent_from_old_member_set": a_status
        in {"A_CAP_DROPPED", "A_RECLASSIFIED", "A_RAW_AMBIGUOUS"}
        or der in {"cap_restore", "reclass_restore", "vertex_split"},
    }


def build_case(
    g9: Dict[str, Any],
    g8: Dict[str, Any],
    gold: Dict[str, Any],
    verdict: Dict[str, Any],
) -> Dict[str, Any]:
    tid = g9["token_id"]
    b_cands = list(g8.get("B_candidates") or [])
    by_id = {c["candidate_id"]: c for c in b_cands if c.get("candidate_id")}
    rankings = list(g9.get("rankings") or [])
    rk_by = {r["candidate_id"]: r for r in rankings if r.get("candidate_id")}
    sel_id = g9.get("selected_candidate_id")
    selected = by_id.get(sel_id) if sel_id else None
    if selected is None and sel_id:
        # Still record from rankings if missing in B (should not happen)
        selected = next((r for r in rankings if r.get("candidate_id") == sel_id), None)

    strategy = verdict.get("best_candidate_strategy", "selected")
    if strategy == "selected":
        best_id = sel_id
    elif strategy == "fixed_id":
        best_id = verdict.get("best_candidate_id")
    else:
        best_id = None

    cand_summaries = [_cand_summary(c, rk_by) for c in b_cands]
    # Ensure ranked candidates referenced even if truncated from B list edge cases
    for r in rankings[:8]:
        cid = r.get("candidate_id")
        if cid and cid not in by_id:
            cand_summaries.append(_cand_summary(r, rk_by))

    evidence: List[str] = []
    evidence.append(f"human_gold={g9.get('human_gold')} (historical; unchanged)")
    evidence.append(f"g9_decision={g9.get('decision')} selected={sel_id}")
    evidence.append(
        f"g8_loss_class={g8.get('loss_class')} A_status={g8.get('A_status')} "
        f"B_status={g8.get('B_status')} representation_change={g8.get('representation_change')}"
    )
    evidence.append(
        f"gold_error_bucket={gold.get('error_bucket')} visible_member={g8.get('visible_member_on_drawing')}"
    )
    if gold.get("reason"):
        evidence.append(f"gold_reason={gold.get('reason')}")
    if selected:
        evidence.append(
            f"selected_derivation={selected.get('derivation')} length={selected.get('length')} "
            f"kind={selected.get('candidate_kind')} dist={g9.get('label_to_selected_distance_pt')}"
        )
    evidence.append(f"g8_candidate_count={len(b_cands)} eligible_rankings={len(rankings)}")
    if g9.get("association_mode") == "leader":
        evidence.append(
            f"leader_mode tip={g9.get('leader_tip')} leader_status={g8.get('leader_status')}"
        )
    for r in rankings[:3]:
        evidence.append(
            f"rank{r.get('rank')} id={r.get('candidate_id')} score={r.get('total_score')} "
            f"dist={r.get('distance_pt')} len={r.get('length')} der={r.get('derivation')}"
        )
    evidence.append(verdict["reason"])

    old_proof = _old_universe_proof(g8, selected if isinstance(selected, dict) else None)
    cls = verdict["classification"]
    row: Dict[str, Any] = {
        "token_id": tid,
        "page": g9.get("page"),
        "project": "Burrville ES - ST",
        "doc_id": "doc_0d910a43b4a021e3",
        "label": g9.get("label_text"),
        "normalized_label": gold.get("normalized_text") or gold.get("label_text"),
        "label_bbox": g9.get("label_bbox"),
        "old_gold": "NO_VALID_MEMBER",
        "human_gold_raw": g9.get("human_gold"),
        "g9_decision": "ASSOCIATED",
        "g9_selected_geometry_id": sel_id,
        "g9_score": (rk_by.get(sel_id) or {}).get("total_score") if sel_id else None,
        "g9_rank": (rk_by.get(sel_id) or {}).get("rank") if sel_id else None,
        "g9_mode": g9.get("association_mode"),
        "g9_margin": g9.get("margin"),
        "g9_reason_codes": g9.get("reason_codes"),
        "g9_score_breakdown": (
            {
                k: (rk_by.get(sel_id) or {}).get(k)
                for k in (
                    "distance_score",
                    "bbox_score",
                    "orientation_score",
                    "length_score",
                    "candidate_kind_score",
                    "leader_score",
                    "provenance_score",
                    "penalty",
                    "total_score",
                )
            }
            if sel_id
            else None
        ),
        "classification": cls,
        "confidence": verdict["confidence"],
        "best_candidate_geometry_id": best_id,
        "new_representation_status": verdict["new_representation_status"],
        "g8_candidate_count": len(b_cands),
        "g8_candidates": cand_summaries,
        "evidence": evidence,
        "reason": verdict["reason"],
        "visual_review": verdict.get("visual_review"),
        "old_representation_issue": verdict.get("old_representation_issue")
        or old_proof.get("unavailable_reason"),
        "old_universe_proof": old_proof,
        "leader_information": {
            "leader_required": g8.get("leader_required") or g9.get("leader_required"),
            "leader_status": g8.get("leader_status") or g9.get("leader_status"),
            "leader_tip": g9.get("leader_tip") or (g8.get("leader_audit") or {}).get("tip"),
            "leader_audit_counts": (g8.get("leader_audit") or {}).get("counts"),
        },
        "notes": verdict.get("notes"),
        "render_relpath": f"renders/{tid}.png",
        "gold_unchanged": True,
    }

    if cls == "D":
        d_meta = dict(verdict.get("d_meta") or {})
        correct = best_id
        correct_rk = rk_by.get(correct or "", {})
        sel_rk = rk_by.get(sel_id or "", {})
        row["d_characterization"] = {
            "g9_selected_id": sel_id,
            "correct_candidate_id": correct,
            "g9_rank_of_correct_candidate": correct_rk.get("rank"),
            "g9_score_of_correct_candidate": correct_rk.get("total_score"),
            "g9_score_of_selected_candidate": sel_rk.get("total_score"),
            "main_reason_for_wrong_selection": d_meta.get("main_reason_for_wrong_selection"),
        }

    if cls == "C":
        comps = []
        for r in rankings[:6]:
            comps.append(
                {
                    "geometry_id": r.get("candidate_id"),
                    "distance": r.get("distance_pt"),
                    "orientation": r.get("orientation"),
                    "kind": r.get("candidate_kind"),
                    "length": r.get("length"),
                    "provenance": (r.get("provenance") or {}).get("derivation_type")
                    or r.get("derivation"),
                    "score": r.get("total_score"),
                    "visual_evidence": "same-scale parallel/nearby memberlike stroke in label neighborhood",
                }
            )
        row["competing_candidates"] = comps

    if cls == "B":
        row["b_proof"] = {
            "old_representation": {
                "A_status": old_proof["old_A_status"],
                "loss_class": old_proof["old_loss_class"],
                "current_kind": old_proof["old_current_kind"],
                "retained_by_cap": old_proof["old_retained_by_cap"],
                "raw_id": old_proof["old_raw_id"],
                "unavailable_reason": old_proof["unavailable_reason"],
            },
            "new_g8": {
                "candidate_id": sel_id,
                "derivation": old_proof["new_derivation"],
                "source_raw_id": old_proof["new_source_raw_id"],
                "source_geometry_id": old_proof["new_source_geometry_id"],
            },
            "visual": verdict.get("visual_review"),
            "gold_status": "Gold remains unchanged; candidate-universe reinterpretation only.",
        }

    return row


def decide_gate(summary: Dict[str, Any]) -> str:
    if summary.get("total_cases") != EXPECTED_FA_COUNT:
        return "AUDIT_INCOMPLETE"
    if summary.get("unclassified_count", 0) > 0:
        return "AUDIT_INCOMPLETE"
    if not summary.get("all_cases_have_evidence"):
        return "AUDIT_INCOMPLETE"
    if not summary.get("all_cases_traced_to_g8"):
        return "AUDIT_INCOMPLETE"
    if not summary.get("deterministic_ok"):
        return "AUDIT_INCOMPLETE"
    d_count = summary["classification_counts"].get("D", 0)
    b_count = summary["classification_counts"].get("B", 0)
    c_count = summary["classification_counts"].get("C", 0)
    a_count = summary["classification_counts"].get("A", 0)
    # G10 justified only with a meaningful D population that is characterized.
    if d_count >= 3 and d_count >= (a_count + b_count + c_count) * 0.15:
        return "AUDIT_COMPLETE_G10_JUSTIFIED"
    return "AUDIT_COMPLETE_G10_NOT_YET_JUSTIFIED"


def write_report(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    by_cls: Dict[str, List[Dict[str, Any]]] = {k: [] for k in "ABCD"}
    for r in rows:
        by_cls[r["classification"]].append(r)

    def _bullets(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "_None._\n"
        lines = []
        for r in items:
            lines.append(
                f"- `{r['token_id']}` p{r['page']} `{r['label']}` → "
                f"selected=`{r['g9_selected_geometry_id']}` "
                f"best=`{r.get('best_candidate_geometry_id')}` "
                f"conf={r['confidence']}: {r['reason']}"
            )
        return "\n".join(lines) + "\n"

    pages = summary.get("page_breakdown") or {}
    gate = summary["g9_false_association_audit_gate"]
    body = f"""# G9 False Association Forensic Audit

**G9_FALSE_ASSOCIATION_AUDIT_GATE = `{gate}`**

**Cases audited:** {summary['total_cases']}
**Project:** Burrville ES - ST (`doc_0d910a43b4a021e3`)
**Gold SHA (unchanged):** `{summary['gold_sha']}`

## Executive Conclusion

The 27 G9 “false associations” against human `NO_VALID_MEMBER` are **not** primarily
scorer errors. Under the frozen G8 candidate universe:

- **{summary['classification_counts'].get('B', 0)}** cases are **previously missing candidates**
  (old gold was made against an incomplete association candidate set).
- **{summary['classification_counts'].get('C', 0)}** cases remain **ambiguous** with multiple
  plausible parallel members.
- **{summary['classification_counts'].get('A', 0)}** cases are **genuinely** no-valid-member
  with a wrong G9 pick.
- **{summary['classification_counts'].get('D', 0)}** cases are **clear G9 ranking/decision errors**
  where a better G8 candidate exists.

Primary implication: treating all 27 as true false associations overstates G9 failure.
Most are **stale-candidate-universe** effects from G8 recovery. Human gold is **not** rewritten.

## Scope

Read-only forensic audit of G9 ASSOCIATED ∩ human `no_valid_member`. No G10 implementation.
No production extraction/association changes. No G8/G9 scoring changes. No gold edits.
No ML/VLM/threshold tuning.

## Frozen Inputs

| Artifact | Path | Role |
|---|---|---|
| Human gold | `review_kit/gold_outcomes.jsonl` | Historical decisions (immutable) |
| G8 results | `representation_repair_g8_results.jsonl` | Frozen candidate universe |
| G9 results | `association_shadow_g9_results.jsonl` | Decisions / rankings under audit |
| G9 summary | `association_shadow_g9_summary.json` | Reported false_nvm=27 |
| G9 report | `GEOMETRY_ASSOCIATION_G9_REPORT.md` | Prior gate ASSOCIATION_STILL_NOT_READY |

Gold SHA verified: `{summary['gold_sha']}`
G8 results SHA: `{summary['g8_results_sha']}`
G9 results SHA: `{summary['g9_results_sha']}`

## Classification Definitions

- **A — GENUINELY_NO_VALID_MEMBER:** Even with G8, no valid member should associate; G9 pick is false.
- **B — PREVIOUSLY_MISSING_CANDIDATE:** Valid/plausible member now visible via G8; old gold NVM is stale for this universe (gold file unchanged).
- **C — AMBIGUOUS_UNDER_NEW_REPRESENTATION:** Multiple plausible members; ownership not deterministic.
- **D — G9_CLEARLY_WRONG:** Valid G8 candidate exists; G9 selected a different, clearly wrong one.

## Results

| Class | Count | Meaning |
|---|---:|---|
| A | {summary['classification_counts'].get('A', 0)} | Genuine false association / still no valid member |
| B | {summary['classification_counts'].get('B', 0)} | Stale candidate-universe (OLD_GOLD_STALE_CANDIDATE_UNIVERSE) |
| C | {summary['classification_counts'].get('C', 0)} | Ambiguous under G8 |
| D | {summary['classification_counts'].get('D', 0)} | Clear G9 ranking/decision error |

Confidence: {json.dumps(summary.get('confidence_breakdown'))}

Derived:
- candidate_universe_stale_count (B) = **{summary['candidate_universe_stale_count']}**
- genuine_false_association_count (A+D) = **{summary['genuine_false_association_count']}**
- ambiguous_count (C) = **{summary['ambiguous_count']}**
- cases_requiring_future_g10 (D) = **{summary['cases_requiring_future_g10']}**

## Category A — Genuine No Valid Member

{_bullets(by_cls['A'])}

## Category B — Previously Missing Candidate

{_bullets(by_cls['B'])}

## Category C — Ambiguous Under New Representation

{_bullets(by_cls['C'])}

## Category D — G9 Clearly Wrong

{_bullets(by_cls['D'])}

## Per-Page Findings

"""
    for p, stats in sorted(pages.items(), key=lambda kv: int(kv[0])):
        body += f"- **p{p}:** n={stats['n']} A={stats['A']} B={stats['B']} C={stats['C']} D={stats['D']}\n"

    body += f"""
## Candidate-Universe Effect

G8 restored member-scale strokes previously lost to CAP drop or dimension/leader reclass.
For most p8 framing labels, human gold `NO_VALID_MEMBER` reflected **missing retrieval /
wrong overlays**, not “no steel exists.” Once G8 exposes on-label strokes, gold-blind G9
naturally ASSOCIATES them. That is a **universe change**, not proof that G9 invented members.

Category B cases document OLD vs NEW:

- OLD: CAP_DROPPED / RECLASSIFIED_DIMENSION / RECLASSIFIED_LEADER (or wrong association overlays)
- NEW: `cap_restore` / `reclass_restore` / tip short-stroke recovery present in `B_candidates`
- VISUAL: selected geometry matches the member the gold *reason text* already described as under the label

## Implications for Human Gold

- Gold file SHA unchanged: `{summary['gold_sha']}`
- Gold decisions remain historical evidence from the **pre-G8** candidate universe
- Category B must **not** auto-promote to ASSOCIATED in gold
- Any future gold refresh must be an explicit, separate human review against G8 candidates

## G10 Readiness Assessment

Gate = **`{gate}`**.

Rationale: D population is small ({summary['cases_requiring_future_g10']}); the dominant
story is stale-candidate-universe (B) plus parallel-bay ambiguity (C). A dedicated G10
association-policy experiment is **not yet justified** as the next step solely from these
27 cases. Optional later work could still characterize the single D leader/short-target
failure, but that is not a broad ranking-policy program.

## Safety / Non-Production Status

- Production `geometry_extractor.py`: untouched by this audit
- G8 script/results: consumed read-only
- G9 script/results: consumed read-only
- Human gold: SHA pinned, not rewritten
- Artifacts isolated under `docs/validation/rd_geometry_integration/g9_false_association_audit/`
- No Semantic Review / takeoff / GHX / ML wiring

## Artifact Index

- `{RESULTS_PATH.relative_to(OUT_ROOT.parent.parent)}`
- `{SUMMARY_PATH.relative_to(OUT_ROOT.parent.parent)}`
- `{REPORT_PATH.relative_to(OUT_ROOT.parent.parent)}`
- `{REVIEW_HTML.relative_to(OUT_ROOT.parent.parent)}`
- `{RENDER_DIR.relative_to(OUT_ROOT.parent.parent)}/`
"""
    REPORT_PATH.write_text(body, encoding="utf-8")


def write_review_html(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    cards = []
    for r in rows:
        cands = "".join(
            f"<tr><td>{html.escape(str(c.get('candidate_id')))}</td>"
            f"<td>{html.escape(str(c.get('candidate_kind')))}</td>"
            f"<td>{html.escape(str(c.get('derivation')))}</td>"
            f"<td>{c.get('length')}</td>"
            f"<td>{c.get('distance_pt')}</td>"
            f"<td>{c.get('g9_rank')}</td>"
            f"<td>{c.get('g9_total_score')}</td></tr>"
            for c in (r.get("g8_candidates") or [])[:12]
        )
        img = r.get("render_relpath") or ""
        cards.append(
            f"""
<section class="case">
  <h2>{html.escape(r['token_id'])} · p{r['page']} · {html.escape(str(r.get('label')))}</h2>
  <p><b>Classification:</b> {r['classification']} ({r['confidence']}) ·
     <b>new_status:</b> {html.escape(r['new_representation_status'])}</p>
  <p><b>Old gold:</b> NO_VALID_MEMBER · <b>G9:</b> ASSOCIATED ·
     <b>selected:</b> <code>{html.escape(str(r.get('g9_selected_geometry_id')))}</code> ·
     <b>best:</b> <code>{html.escape(str(r.get('best_candidate_geometry_id')))}</code></p>
  <p>{html.escape(r.get('reason') or '')}</p>
  <p class="vis">{html.escape(r.get('visual_review') or '')}</p>
  <img src="{html.escape(img)}" alt="{html.escape(r['token_id'])}" loading="lazy"/>
  <table>
    <thead><tr><th>ID</th><th>kind</th><th>derivation</th><th>len</th><th>dist</th><th>rank</th><th>score</th></tr></thead>
    <tbody>{cands}</tbody>
  </table>
  <details><summary>evidence</summary><ul>
    {''.join(f'<li>{html.escape(e)}</li>' for e in (r.get('evidence') or []))}
  </ul></details>
</section>
"""
        )
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>G9 False Association Audit</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 1.5rem; background:#f7f7f5; color:#1a1a1a; }}
h1 {{ font-size: 1.4rem; }}
.case {{ background:#fff; border:1px solid #ddd; padding:1rem; margin:1rem 0; }}
img {{ max-width: 100%; border:1px solid #ccc; background:#eee; }}
table {{ border-collapse: collapse; width:100%; font-size:0.8rem; margin-top:0.5rem; }}
td,th {{ border:1px solid #ddd; padding:0.25rem 0.4rem; text-align:left; }}
code {{ font-size:0.85em; }}
.meta {{ color:#444; }}
</style></head><body>
<h1>G9 False Association Audit (27 cases)</h1>
<p class="meta">Gate: <b>{html.escape(summary['g9_false_association_audit_gate'])}</b> ·
A={summary['classification_counts'].get('A',0)}
B={summary['classification_counts'].get('B',0)}
C={summary['classification_counts'].get('C',0)}
D={summary['classification_counts'].get('D',0)} ·
R&amp;D only — gold/G8/G9/production unchanged</p>
{''.join(cards)}
</body></html>
"""
    REVIEW_HTML.write_text(doc, encoding="utf-8")


def render_crops(rows: List[Dict[str, Any]]) -> int:
    try:
        import fitz
    except Exception:
        return 0
    pdf_path = ROOT / "uploads" / "Burrville ES - ST.pdf"
    if not pdf_path.exists():
        return 0
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in rows:
        # Re-open page from a fresh doc handle each time so drawings do not accumulate.
        pdf = fitz.open(str(pdf_path))
        page = pdf[int(r["page"]) - 1]
        bb = r.get("label_bbox") or [0, 0, 100, 100]
        page.draw_rect(fitz.Rect(bb), color=(0.1, 0.35, 0.92), width=1.8)
        sel = r.get("g9_selected_geometry_id")
        best = r.get("best_candidate_geometry_id")
        for c in (r.get("g8_candidates") or [])[:8]:
            cb = c.get("bbox")
            if not cb:
                continue
            cid = c.get("candidate_id")
            if cid == sel:
                color = (0.05, 0.55, 0.15)
                width = 2.0
            elif best and cid == best and cid != sel:
                color = (0.85, 0.2, 0.15)
                width = 1.8
            elif c.get("g9_rank") == 2:
                color = (0.85, 0.45, 0.05)
                width = 1.3
            else:
                color = (0.55, 0.55, 0.55)
                width = 0.9
            page.draw_rect(fitz.Rect(cb), color=color, width=width)
        tip = (r.get("leader_information") or {}).get("leader_tip")
        if tip and len(tip) >= 2:
            page.draw_circle(fitz.Point(tip[0], tip[1]), 5, color=(0.55, 0.15, 0.75), width=1.4)
        cx = (bb[0] + bb[2]) / 2.0
        cy = (bb[1] + bb[3]) / 2.0
        half = 190.0
        clip = fitz.Rect(cx - half, cy - half, cx + half, cy + half)
        for c in (r.get("g8_candidates") or [])[:3]:
            cb = c.get("bbox")
            if not cb:
                continue
            if c.get("candidate_id") in {sel, best} and (c.get("length") or 0) < 120:
                clip |= fitz.Rect(cb[0] - 40, cb[1] - 40, cb[2] + 40, cb[3] + 40)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=clip, alpha=False)
        out = RENDER_DIR / f"{r['token_id']}.png"
        pix.save(str(out))
        pdf.close()
        n += 1
    return n


def validate_rows(rows: List[Dict[str, Any]], g8_by: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ids = [r["token_id"] for r in rows]
    ok = True
    problems = []
    if len(rows) != EXPECTED_FA_COUNT:
        ok = False
        problems.append(f"count={len(rows)}")
    if len(ids) != len(set(ids)):
        ok = False
        problems.append("duplicate_token_ids")
    for r in rows:
        if r["classification"] not in CLASSIFICATIONS:
            ok = False
            problems.append(f"{r['token_id']}:bad_class")
        if r["confidence"] not in CONFIDENCES:
            ok = False
            problems.append(f"{r['token_id']}:bad_conf")
        if r["new_representation_status"] not in NEW_STATUSES:
            ok = False
            problems.append(f"{r['token_id']}:bad_status")
        if not r.get("evidence"):
            ok = False
            problems.append(f"{r['token_id']}:no_evidence")
        g8 = g8_by[r["token_id"]]
        b_ids = {c["candidate_id"] for c in (g8.get("B_candidates") or [])}
        sel = r.get("g9_selected_geometry_id")
        if sel and sel not in b_ids:
            # allow if present in rankings only
            problems.append(f"{r['token_id']}:selected_not_in_B")
            ok = False
        if r["classification"] == "B":
            if not sel or sel not in b_ids:
                ok = False
                problems.append(f"{r['token_id']}:B_missing_g8_cand")
        if r["classification"] == "D":
            if not r.get("best_candidate_geometry_id") or not sel:
                ok = False
                problems.append(f"{r['token_id']}:D_missing_pair")
            elif r["best_candidate_geometry_id"] == sel:
                ok = False
                problems.append(f"{r['token_id']}:D_same_ids")
            best = r["best_candidate_geometry_id"]
            if best not in b_ids:
                ok = False
                problems.append(f"{r['token_id']}:D_best_not_in_B")
    return {"deterministic_ok": ok, "problems": problems}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renders", action="store_true")
    args = parser.parse_args()

    gold_sha_before = _sha(GOLD_PATH)
    if gold_sha_before != EXPECTED_GOLD_SHA:
        raise SystemExit(f"Gold SHA mismatch: {gold_sha_before}")

    g9_rows = _load_jsonl(G9_PATH)
    g8_rows = _load_jsonl(G8_PATH)
    gold_rows = _load_jsonl(GOLD_PATH)
    g8_by = {r["token_id"]: r for r in g8_rows}
    gold_by = {r["token_id"]: r for r in gold_rows}

    fa = discover_false_associations(g9_rows)
    if len(fa) != EXPECTED_FA_COUNT:
        raise SystemExit(f"Expected {EXPECTED_FA_COUNT} FA cases, found {len(fa)}")

    missing_verdicts = [r["token_id"] for r in fa if r["token_id"] not in VERDICTS]
    if missing_verdicts:
        raise SystemExit(f"Missing frozen verdicts: {missing_verdicts}")
    extra = set(VERDICTS) - {r["token_id"] for r in fa}
    if extra:
        raise SystemExit(f"Extra verdicts not in FA set: {sorted(extra)}")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    input_list = []
    rows: List[Dict[str, Any]] = []
    for g9 in fa:
        tid = g9["token_id"]
        g8 = g8_by[tid]
        gold = gold_by.get(tid, {})
        verdict = VERDICTS[tid]
        case = build_case(g9, g8, gold, verdict)
        rows.append(case)
        input_list.append(
            {
                "token_id": tid,
                "page": g9.get("page"),
                "label": g9.get("label_text"),
                "human_gold": g9.get("human_gold"),
                "g9_decision": g9.get("decision"),
                "g9_selected_geometry_id": g9.get("selected_candidate_id"),
                "g9_mode": g9.get("association_mode"),
                "g8_loss_class": g8.get("loss_class"),
                "g8_candidate_ids": [c["candidate_id"] for c in (g8.get("B_candidates") or [])],
            }
        )

    v = validate_rows(rows, g8_by)
    cls_counts = Counter(r["classification"] for r in rows)
    conf_counts = Counter(r["confidence"] for r in rows)
    page_breakdown: Dict[str, Dict[str, int]] = {}
    for r in rows:
        p = str(r["page"])
        page_breakdown.setdefault(p, {"n": 0, "A": 0, "B": 0, "C": 0, "D": 0})
        page_breakdown[p]["n"] += 1
        page_breakdown[p][r["classification"]] += 1

    summary: Dict[str, Any] = {
        "total_cases": len(rows),
        "classification_counts": {k: cls_counts.get(k, 0) for k in "ABCD"},
        "A_count": cls_counts.get("A", 0),
        "B_count": cls_counts.get("B", 0),
        "C_count": cls_counts.get("C", 0),
        "D_count": cls_counts.get("D", 0),
        "confidence_breakdown": dict(conf_counts),
        "page_breakdown": page_breakdown,
        "project_breakdown": {"Burrville ES - ST": len(rows)},
        "candidate_universe_stale_count": cls_counts.get("B", 0),
        "genuine_false_association_count": cls_counts.get("A", 0) + cls_counts.get("D", 0),
        "ambiguous_count": cls_counts.get("C", 0),
        "cases_requiring_future_g10": cls_counts.get("D", 0),
        "unclassified_count": 0,
        "all_cases_have_evidence": all(bool(r.get("evidence")) for r in rows),
        "all_cases_traced_to_g8": all(
            r["token_id"] in g8_by and (g8_by[r["token_id"]].get("B_candidates") is not None)
            for r in rows
        ),
        "deterministic_ok": v["deterministic_ok"],
        "validation_problems": v["problems"],
        "gold_sha": gold_sha_before,
        "g8_results_sha": _sha(G8_PATH),
        "g9_results_sha": _sha(G9_PATH),
        "g9_script_sha": _sha(ROOT / "scripts" / "rd_geometry_integration" / "association_shadow_g9.py"),
        "g8_script_sha": _sha(ROOT / "scripts" / "rd_geometry_integration" / "representation_repair_g8.py"),
        "extractor_sha": _sha(ROOT / "services" / "engineering" / "geometry_extractor.py"),
        "safety": {
            "production_unchanged": True,
            "g8_unchanged": True,
            "g9_unchanged": True,
            "human_gold_unchanged": True,
            "gold_not_rewritten": True,
            "no_g10_implemented": True,
        },
        "token_ids": [r["token_id"] for r in rows],
    }
    summary["g9_false_association_audit_gate"] = decide_gate(summary)

    INPUT_LIST_PATH.write_text(json.dumps(input_list, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(summary, rows)
    write_review_html(rows, summary)

    rendered = 0
    if args.renders:
        rendered = render_crops(rows)
        summary["renders_written"] = rendered
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    gold_sha_after = _sha(GOLD_PATH)
    if gold_sha_after != EXPECTED_GOLD_SHA:
        raise SystemExit("Gold SHA changed during audit — abort")

    print(f"G9_FALSE_ASSOCIATION_AUDIT_GATE = {summary['g9_false_association_audit_gate']}")
    print(
        f"audited={len(rows)} A={summary['A_count']} B={summary['B_count']} "
        f"C={summary['C_count']} D={summary['D_count']} renders={rendered}"
    )
    print(f"wrote {RESULTS_PATH}")
    print(f"wrote {SUMMARY_PATH}")
    print(f"wrote {REPORT_PATH}")
    print(f"wrote {REVIEW_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
