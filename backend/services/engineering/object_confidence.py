"""
Object-level Confidence Scoring
===============================

Computes legacy extraction-quality scores for engineering objects:

- text_confidence
- geometry_confidence
- matching_confidence
- overall

Runtime prediction confidence is owned by multimodal fusion.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.engineering.models import ObjectConfidence
from services.prediction.confidence_engine import level_from_score


def score_text_object(text_obj: dict) -> float:
    """Heuristic text confidence from font size, length, and neighbors."""

    text = str(text_obj.get("text") or "").strip()
    if not text:
        return 0.1
    score = 0.45
    size = text_obj.get("font_size")
    if size and float(size) >= 6:
        score += 0.2
    if len(text) >= 3:
        score += 0.1
    if text_obj.get("neighbors"):
        score += 0.1
    if text_obj.get("drawing_references"):
        score += 0.05
    # Penalize extreme rotation uncertainty only mildly
    rot = abs(float(text_obj.get("rotation") or 0.0))
    if rot not in (0.0, 90.0, 180.0, 270.0) and rot > 5:
        score -= 0.05
    return max(0.0, min(1.0, score))


def score_geometry_object(geom: dict) -> float:
    score = 0.4
    if float(geom.get("length") or 0) > 0:
        score += 0.2
    if float(geom.get("area") or 0) > 0:
        score += 0.15
    if geom.get("kind") in {"line", "polyline", "rectangle", "circle", "dimension"}:
        score += 0.15
    if geom.get("nearby_text"):
        score += 0.1
    return max(0.0, min(1.0, score))


def score_matching_for_object(object_id: str, match_report: Optional[dict]) -> float:
    if not match_report:
        return 0.5
    best = 0.35
    for finding in match_report.get("findings") or []:
        ids = finding.get("object_ids") or []
        if object_id not in ids and not any(object_id in str(i) for i in ids):
            # also allow source id partial containment
            if object_id not in set(ids):
                continue
        status = finding.get("status")
        if status == "perfect_match":
            best = max(best, 0.95)
        elif status in {"count_mismatch", "length_mismatch", "width_mismatch"}:
            best = max(best, 0.55)
        elif status in {"wrong_label", "missing_geometry"}:
            best = max(best, 0.35)
        elif status in {"extra_label", "extra_geometry", "missing_label"}:
            best = max(best, 0.25)
    return best


def build_object_confidences(
    *,
    document_structure: dict,
    geometry: dict,
    graph: dict,
    match_report: Optional[dict] = None,
) -> List[dict]:
    """Compute confidence records for text lines and geometry objects."""

    results: List[dict] = []
    records: List[dict] = []

    for line in document_structure.get("lines") or []:
        oid = line.get("object_id")
        tc = score_text_object(line)
        mc = score_matching_for_object(oid, match_report)
        overall = 0.55 * tc + 0.15 * 0.5 + 0.30 * mc
        conf = ObjectConfidence(
            text_confidence=tc,
            geometry_confidence=0.5,
            matching_confidence=mc,
            overall=max(0.0, min(1.0, overall)),
            level=level_from_score(overall),
            reasons=["text_layout", "match_signal"],
        )
        payload = conf.to_dict()
        payload["object_id"] = oid
        payload["object_type"] = "text"
        payload["page_number"] = line.get("page_number")
        payload["text"] = line.get("text")
        records.append(payload)

    for geom in geometry.get("objects") or []:
        oid = geom.get("geometry_id")
        gc = score_geometry_object(geom)
        mc = score_matching_for_object(oid, match_report)
        # nearby text boost
        tc = 0.5
        nearby = geom.get("nearby_text")
        if nearby:
            tc = 0.65
        overall = 0.25 * tc + 0.45 * gc + 0.30 * mc
        conf = ObjectConfidence(
            text_confidence=tc,
            geometry_confidence=gc,
            matching_confidence=mc,
            overall=max(0.0, min(1.0, overall)),
            level=level_from_score(overall),
            reasons=["geometry_metrics", "match_signal"],
        )
        payload = conf.to_dict()
        payload["object_id"] = oid
        payload["object_type"] = "geometry"
        payload["page_number"] = geom.get("page_number")
        payload["geometry_kind"] = geom.get("kind")
        records.append(payload)

    return records


def score_object_bundle(
    text_confidence: float,
    geometry_confidence: float,
    matching_confidence: float,
    *,
    w_text: float = 0.35,
    w_geom: float = 0.35,
    w_match: float = 0.30,
) -> ObjectConfidence:
    """Fuse three object-level signals (mirrors token scorer style)."""

    overall = (
        w_text * float(text_confidence)
        + w_geom * float(geometry_confidence)
        + w_match * float(matching_confidence)
    )
    overall = max(0.0, min(1.0, overall))
    return ObjectConfidence(
        text_confidence=float(text_confidence),
        geometry_confidence=float(geometry_confidence),
        matching_confidence=float(matching_confidence),
        overall=overall,
        level=level_from_score(overall),
        reasons=["weighted_fusion"],
    )
