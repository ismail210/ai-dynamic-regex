"""
Unified additive TokenPrediction contract.

Canonical fields: family, section, confidence, explanation, evidence.
Legacy aliases: prediction, predicted_shape, confidence.score.
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


def apply_legacy_aliases(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    DEPRECATED MIGRATION ADAPTER — isolate here, remove once every frontend
    consumer reads the canonical contract (``services.prediction.
    canonical_contract``) instead of guessing across these bare-string /
    differently-named duplicates:

    * ``prediction`` / ``predicted_shape``   -> alias of ``section``
    * ``confidence.score``                    -> alias of ``confidence.overall``
    * ``reasoning``                           -> alias of ``explanation``

    Do not add new fields here. New fields belong on the canonical contract.
    """

    section = payload.get("section")
    payload.setdefault("prediction", section)
    payload.setdefault("predicted_shape", section)
    confidence = payload.get("confidence")
    if isinstance(confidence, dict):
        confidence.setdefault("score", confidence.get("overall"))
    payload.setdefault("reasoning", payload.get("explanation"))
    return payload


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
    """Serialize the canonical prediction contract (plus one migration-period
    legacy-alias layer, see ``apply_legacy_aliases``)."""

    section = str(section or "").strip()
    family = str(family).strip().upper() if family else None
    overall = float(confidence.get("overall") or 0.0)
    conf = {
        **confidence,
        "overall": round(overall, 4),
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
        "confidence": conf,
        # `explanation` is the only place the reasoning lives. It used to be
        # duplicated under `reasoning`, which doubled every response.
        "explanation": explanation,
        "evidence": evidence,
        "database_match": bool(database_match),
        "database_role": "verification_only",
        "ai_first": True,
        "database_decides_prediction": False,
    }
    if extras:
        payload.update(extras)
    return apply_legacy_aliases(payload)


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
