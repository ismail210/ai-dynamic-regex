"""
Unified additive TokenPrediction contract.

Canonical fields: family, section, confidence, explanation, evidence.
Legacy aliases: prediction, predicted_shape, reasoning, confidence.score.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def confidence_overall(confidence: Any) -> float:
    """Normalize confidence objects or scalars to an overall float score."""

    if isinstance(confidence, dict):
        return float(confidence.get("overall") or confidence.get("score") or 0.0)
    try:
        return float(confidence or 0.0)
    except (TypeError, ValueError):
        return 0.0


def to_token_prediction(
    *,
    token: str,
    family: Optional[str],
    section: str,
    confidence: Dict[str, Any],
    explanation: Dict[str, Any],
    evidence: Dict[str, Any],
    database_match: bool,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Serialize the additive v1 prediction contract."""

    section = str(section or "").strip()
    family = str(family).strip().upper() if family else None
    overall = float(confidence.get("overall") or 0.0)
    conf = {
        **confidence,
        "overall": round(overall, 4),
        "score": round(overall, 4),  # deprecated alias
        "level": confidence.get("level")
        or (
            "High"
            if overall >= 0.80
            else "Medium"
            if overall >= 0.55
            else "Low"
        ),
    }
    payload: Dict[str, Any] = {
        "schema_version": "2.0",
        "token": token,
        "family": family,
        "section": section,
        # Legacy aliases (additive migration).
        "prediction": section,
        "predicted_shape": section,
        "confidence": conf,
        "explanation": explanation,
        "reasoning": explanation,  # alias
        "evidence": evidence,
        "top_candidate_sections": explanation.get("top_candidate_sections") or [],
        "why_selected": explanation.get("why_selected") or [],
        "why_rejected": explanation.get("why_rejected") or [],
        "text_evidence": explanation.get("text_evidence") or {},
        "geometry_evidence": explanation.get("geometry_evidence") or {},
        "graph_evidence": explanation.get("graph_evidence") or {},
        "engineering_evidence": explanation.get("engineering_evidence") or {},
        "database_match": bool(database_match),
        "database_role": "verification_only",
        "ai_first": True,
        "database_decides_prediction": False,
    }
    if extras:
        payload.update(extras)
    return payload


def derive_family_from_section(section: str, fallback: Optional[str] = None) -> Optional[str]:
    """Derive a structural family prefix from a full section label."""

    from services.feature_extractor import extract_structural_features

    structural = {
        "W", "HSS", "L", "C", "MC", "PIPE", "WT", "M", "S", "HP", "2L", "MT", "ST",
    }
    text = str(section or "").strip().upper()
    if not text:
        return str(fallback).strip().upper() if fallback else None
    if text in structural:
        return text
    features = extract_structural_features(text)
    family = str(features.get("shape_family") or "").upper()
    if family and family not in {"OTHER", "NONE", "UNK"}:
        return family
    if fallback and str(fallback).strip().upper() in structural:
        return str(fallback).strip().upper()
    return fallback
