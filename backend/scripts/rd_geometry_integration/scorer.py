"""Shadow deterministic association scorer (R&D). Does not change production."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

TIE_MARGIN = 0.15


def score_candidate(candidate: Dict[str, Any]) -> float:
    """Lower is better. Explainable weighted distance, not a probability."""
    bbox_d = float(candidate.get("bbox_distance") or 0.0)
    perp = candidate.get("perpendicular_distance")
    dist = min(bbox_d, float(perp)) if perp is not None else bbox_d
    score = dist
    if candidate.get("leader_supported"):
        score *= 0.7
    if candidate.get("same_region") is False:
        score *= 1.25
    kind = str(candidate.get("geometry_kind") or "").lower()
    if kind in {"leader", "dimension"}:
        score += 80.0
    return score


def decide_association(candidates: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {
            "status": "unavailable",
            "selected": None,
            "abstain_reason": "no_candidates",
            "scores": [],
        }
    ranked = sorted(
        [{**c, "shadow_score": score_candidate(c)} for c in candidates],
        key=lambda r: r["shadow_score"],
    )
    best = ranked[0]
    if len(ranked) >= 2:
        s0 = float(ranked[0]["shadow_score"])
        s1 = float(ranked[1]["shadow_score"])
        if s1 > 0 and (s1 - s0) / s1 < TIE_MARGIN:
            return {
                "status": "ambiguous",
                "selected": None,
                "abstain_reason": "near_tie",
                "scores": ranked,
            }
    kind = str(best.get("geometry_kind") or "").lower()
    if kind in {"leader", "dimension"}:
        return {
            "status": "ambiguous",
            "selected": None,
            "abstain_reason": "top_is_leader_or_dimension",
            "scores": ranked,
        }
    return {
        "status": "associated",
        "selected": best,
        "abstain_reason": None,
        "scores": ranked,
    }


def evaluate_against_production(
    rows: Sequence[Dict[str, Any]],
    gold_by_token: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    gold_by_token = gold_by_token or {}
    n = len(rows)
    agree = 0
    disagree = 0
    abstain = 0
    leader_as_target = 0
    recall_hits = 0
    gold_n = 0
    for row in rows:
        cands = row.get("new_candidates") or []
        decision = row.get("shadow_decision") or decide_association(cands)
        prod_id = (row.get("current_association") or {}).get("geometry_id")
        selected = (decision.get("selected") or {}).get("geometry_id")
        if decision.get("status") != "associated":
            abstain += 1
        elif prod_id and selected == prod_id:
            agree += 1
        elif prod_id and selected:
            disagree += 1
        top_kind = str((cands[0] if cands else {}).get("geometry_kind") or "").lower()
        if top_kind == "leader":
            leader_as_target += 1
        gold_ids = gold_by_token.get(row.get("token_id") or "")
        if gold_ids:
            gold_n += 1
            cand_ids = {c.get("geometry_id") for c in cands}
            if cand_ids.intersection(gold_ids):
                recall_hits += 1
    return {
        "label_count": n,
        "shadow_agree_production": agree,
        "shadow_disagree_production": disagree,
        "shadow_abstain": abstain,
        "leader_as_unconstrained_top": leader_as_target,
        "gold_groups": gold_n,
        "candidate_recall_at_k": (recall_hits / gold_n) if gold_n else None,
        "note": (
            "agree/disagree are vs production nearest_geometry (reference), "
            "not ground truth. recall@K is None until human gold exists."
        ),
    }
