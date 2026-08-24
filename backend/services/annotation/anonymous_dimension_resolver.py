"""Deterministic resolver for anonymous dimensions with explainable abstention."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

PROMOTION_THRESHOLD = 0.75
MARGIN_THRESHOLD = 0.15

_BENT_RE = re.compile(r"\b(?:BENT\s*PL(?:ATE)?|BP)\b", re.I)
_PLATE_RE = re.compile(r"\b(?:PL(?:ATE)?|GUSSET|STIFFENER)\b", re.I)
_ANGLE_RE = re.compile(r"\b(?:L|2L|ANGLE|ANGLE\s+SEAT)\b", re.I)
_CONN_RE = re.compile(
    r"\b(?:CONN(?:ECTION)?|SHEAR|MOMENT|CLIP|SEAT)\b",
    re.I,
)
_FRACTIONAL_THICKNESS_RE = re.compile(r"^\d+/\d+\"?$", re.I)


def _environment_penalty(evidence: Dict[str, Any]) -> tuple[float, List[str]]:
    """Penalties for title block / layout-dimension contexts."""

    penalty = 0.0
    reasons: List[str] = []
    if evidence.get("in_title_block"):
        penalty += 0.6
        reasons.append("title_block_penalty")
    if evidence.get("layout_dimension_is_non_steel"):
        penalty += 0.55
        reasons.append("layout_dimension_penalty")
    if evidence.get("in_notes_region"):
        penalty += 0.5
        reasons.append("notes_region_penalty")
    return penalty, reasons


def _fractional_thickness_boost(evidence: Dict[str, Any]) -> tuple[float, List[str]]:
    thickness = str(evidence.get("thickness_value") or "")
    if not _FRACTIONAL_THICKNESS_RE.match(thickness.strip()):
        return 0.0, []
    if int(evidence.get("nearby_structural_count") or 0) >= 1:
        return 0.1, ["fractional_near_structural"]
    return 0.0, []


def _has_promotion_context(evidence: Dict[str, Any]) -> bool:
    if (evidence.get("leader") or {}).get("present"):
        return True
    if evidence.get("region_kind") == "connection_detail":
        return True
    if int(evidence.get("nearby_structural_count") or 0) >= 1:
        return True
    return False


def _score_bent_plate(evidence: Dict[str, Any], thickness: str) -> tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0
    leader = evidence.get("leader") or {}
    if leader.get("present"):
        score += 0.35
        reasons.append("leader_present")
    targets = evidence.get("target_geometry") or []
    if any(t.get("plate_like") for t in targets):
        score += 0.25
        reasons.append("plate_like_geometry")
    blob = " ".join(evidence.get("nearby_text") or []).upper()
    if _BENT_RE.search(blob):
        score += 0.35
        reasons.append("local_bent_pl_callout")
    if evidence.get("region_kind") == "connection_detail":
        score += 0.15
        reasons.append("connection_detail_region")
    dlp = evidence.get("dlp_hints") or {}
    if dlp.get("supports_bent_plate"):
        score += 0.05
        reasons.append("dlp_bent_plate_hint")
    penalty, penalty_reasons = _environment_penalty(evidence)
    if penalty:
        score -= penalty
        reasons.extend(penalty_reasons)
    boost, boost_reasons = _fractional_thickness_boost(evidence)
    if boost:
        score += boost
        reasons.extend(boost_reasons)
    return min(1.0, max(0.0, score)), reasons


def _score_plate(evidence: Dict[str, Any], thickness: str) -> tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0
    blob = " ".join(evidence.get("nearby_text") or []).upper()
    if _PLATE_RE.search(blob):
        score += 0.4
        reasons.append("local_plate_callout")
    targets = evidence.get("target_geometry") or []
    if any(t.get("plate_like") for t in targets):
        score += 0.25
        reasons.append("plate_like_geometry")
    if (evidence.get("leader") or {}).get("present"):
        score += 0.2
        reasons.append("leader_present")
    dlp = evidence.get("dlp_hints") or {}
    if dlp.get("supports_plate"):
        score += 0.05
        reasons.append("dlp_plate_hint")
    penalty, penalty_reasons = _environment_penalty(evidence)
    if penalty:
        score -= penalty
        reasons.extend(penalty_reasons)
    boost, boost_reasons = _fractional_thickness_boost(evidence)
    if boost:
        score += boost
        reasons.extend(boost_reasons)
    return min(1.0, max(0.0, score)), reasons


def _score_angle(evidence: Dict[str, Any], thickness: str) -> tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0
    blob = " ".join(evidence.get("nearby_text") or "").upper()
    if _ANGLE_RE.search(blob):
        score += 0.45
        reasons.append("angle_callout_nearby")
    for item in evidence.get("nearby_tokens") or []:
        text = str(item.get("text") or "").upper()
        if text.startswith(("L", "2L")) and "X" in text:
            score += 0.25
            reasons.append(f"nearby_section={text}")
            break
    penalty, penalty_reasons = _environment_penalty(evidence)
    if penalty:
        score -= penalty
        reasons.extend(penalty_reasons)
    boost, boost_reasons = _fractional_thickness_boost(evidence)
    if boost:
        score += boost
        reasons.extend(boost_reasons)
    return min(1.0, max(0.0, score)), reasons


def _score_connection(evidence: Dict[str, Any], thickness: str) -> tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0
    blob = " ".join(evidence.get("nearby_text") or []).upper()
    if _CONN_RE.search(blob) or evidence.get("detail_callout"):
        score += 0.3
        reasons.append("connection_context")
    if evidence.get("region_kind") == "connection_detail":
        score += 0.25
        reasons.append("connection_detail_region")
    if (evidence.get("leader") or {}).get("present"):
        score += 0.25
        reasons.append("leader_present")
    if any(t.get("plate_like") for t in (evidence.get("target_geometry") or [])):
        score += 0.15
        reasons.append("plate_like_target")
    if _BENT_RE.search(blob) or _PLATE_RE.search(blob):
        score -= 0.2
        reasons.append("explicit_callout_elsewhere")
    penalty, penalty_reasons = _environment_penalty(evidence)
    if penalty:
        score -= penalty
        reasons.extend(penalty_reasons)
    boost, boost_reasons = _fractional_thickness_boost(evidence)
    if boost:
        score += boost
        reasons.extend(boost_reasons)
    return min(1.0, max(0.0, score)), reasons


def _label_for(type_name: str, thickness: str) -> str:
    thick = thickness.strip()
    if not thick.endswith('"') and type_name in {"BENT_PLATE", "PLATE", "CONNECTION_THICKNESS"}:
        thick = f'{thick}"' if thick else thick
    mapping = {
        "BENT_PLATE": f"{thick} BENT PLATE".strip(),
        "PLATE": f"{thick} PLATE".strip(),
        "ANGLE": f"{thick} ANGLE".strip(),
        "CONNECTION_THICKNESS": f"{thick} CONNECTION PLATE".strip(),
        "DIMENSION": thick or "DIMENSION",
    }
    return mapping.get(type_name, thick)


def resolve_anonymous_dimension(
    evidence: Dict[str, Any],
    *,
    raw_text: str = "",
) -> Dict[str, Any]:
    """Return ranked semantic candidates and optional promotion."""

    thickness = str(
        evidence.get("thickness_value") or raw_text or ""
    ).strip()
    scorers = [
        ("BENT_PLATE", _score_bent_plate),
        ("PLATE", _score_plate),
        ("ANGLE", _score_angle),
        ("CONNECTION_THICKNESS", _score_connection),
    ]
    candidates: List[Dict[str, Any]] = []
    for type_name, scorer in scorers:
        score, reasons = scorer(evidence, thickness)
        if score <= 0.05:
            continue
        candidates.append(
            {
                "type": type_name,
                "label": _label_for(type_name, thickness),
                "score": round(score, 4),
                "evidence": reasons,
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["type"]))
    abstain_score, abstain_reasons = 0.35, ["default_abstain"]
    if not (evidence.get("leader") or {}).get("present") and not candidates:
        abstain_score = 0.9
        abstain_reasons.append("no_leader_no_signals")
    if evidence.get("in_notes_region"):
        abstain_score = 0.95
        abstain_reasons.append("general_notes_region")
    if evidence.get("in_title_block") or evidence.get("layout_dimension_is_non_steel"):
        abstain_score = 0.98
        abstain_reasons.append("title_or_layout_dimension")
    candidates.append(
        {
            "type": "DIMENSION",
            "label": thickness or raw_text,
            "score": round(abstain_score, 4),
            "evidence": abstain_reasons,
        }
    )
    candidates.sort(key=lambda item: (-item["score"], item["type"]))

    recommended: Optional[Dict[str, Any]] = None
    abstain = True
    review_reason = (
        "Anonymous dimension; select the correct semantic interpretation or leave as dimension."
    )
    top = candidates[0] if candidates else None
    second = candidates[1] if len(candidates) > 1 else None
    if top and top["type"] != "DIMENSION":
        margin = top["score"] - (second["score"] if second else 0.0)
        can_promote = _has_promotion_context(evidence) and not evidence.get(
            "in_title_block"
        ) and not evidence.get("layout_dimension_is_non_steel")
        if (
            can_promote
            and top["score"] >= PROMOTION_THRESHOLD
            and margin >= MARGIN_THRESHOLD
        ):
            recommended = top
            abstain = False
            review_reason = ""
        elif not can_promote:
            review_reason = (
                "Insufficient structural context for automatic promotion; "
                "select the correct type."
            )
        elif margin < MARGIN_THRESHOLD:
            review_reason = (
                "Multiple semantic interpretations are similarly supported; "
                "select the correct type."
            )
    elif top and top["type"] == "DIMENSION":
        review_reason = (
            "Insufficient local context to infer plate, angle, or connection semantics."
        )

    evidence_summary = str(evidence.get("evidence_summary") or "").strip()
    if not evidence_summary:
        evidence_bits = []
        leader = evidence.get("leader") or {}
        if leader.get("present"):
            evidence_bits.append("leader path detected")
        if evidence.get("detail_callout"):
            evidence_bits.append(f"detail: {evidence['detail_callout']}")
        if evidence.get("region_kind"):
            evidence_bits.append(f"region: {evidence['region_kind']}")
        evidence_summary = "; ".join(evidence_bits) or "No strong local context."

    return {
        "semantic_candidates": candidates,
        "recommended": recommended,
        "abstain": abstain,
        "review_reason": review_reason,
        "evidence_summary": evidence_summary,
    }
