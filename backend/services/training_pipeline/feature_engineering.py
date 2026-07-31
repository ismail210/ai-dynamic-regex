"""Separate feature engineering for text, geometry, graph, and fusion lanes."""

from __future__ import annotations

from typing import Any, Dict, List

from services.feature_extractor import extract_structural_features


def _clip(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def engineer_text_features(sample: dict) -> dict:
    token = str(sample.get("token") or "")
    structural = extract_structural_features(token)
    extraction = (sample.get("features") or {}).get("extraction") or {}
    return {
        **structural,
        "extraction_confidence": _clip(
            extraction.get("extraction_confidence")
            or extraction.get("confidence")
            or sample.get("metadata", {}).get("extraction_confidence"),
            0.5,
        ),
        "has_surrounding_text": 1.0
        if (sample.get("features") or {}).get("surrounding_text")
        else 0.0,
    }


def engineer_ocr_features(sample: dict) -> dict:
    ocr = (sample.get("features") or {}).get("ocr") or {}
    original = str(ocr.get("original") or sample.get("token") or "")
    corrected = str(ocr.get("corrected") or original)
    return {
        "confidence": _clip(ocr.get("confidence"), 0.5),
        "correction_applied": 1.0 if original != corrected else 0.0,
        "original_length": float(len(original)),
        "corrected_length": float(len(corrected)),
        "repair_count": float(len(ocr.get("repairs") or [])),
    }


def engineer_layout_features(sample: dict) -> dict:
    layout = (sample.get("features") or {}).get("layout") or {}
    bbox = layout.get("bbox") or []
    return {
        "page": _clip(layout.get("page"), 0.0),
        "reading_order": _clip(layout.get("reading_order"), 0.0),
        "rotation": _clip(layout.get("rotation"), 0.0),
        "font_size": _clip(layout.get("font_size"), 0.0),
        "has_bbox": 1.0 if len(bbox) == 4 else 0.0,
        "neighbor_count": float(len(layout.get("neighbors") or [])),
    }


def engineer_engineering_features(sample: dict) -> dict:
    rules = (sample.get("features") or {}).get("engineering_rules") or {}
    return {
        "rule_score": _clip(rules.get("score"), 0.5),
        "finding_count": float(len(rules.get("findings") or [])),
        "has_member_role": 1.0 if rules.get("member_role") else 0.0,
        "has_material_grade": 1.0 if rules.get("material_grade") else 0.0,
    }


def engineer_geometry_features(sample: dict) -> dict:
    features = sample.get("features") or {}
    geometry = features.get("geometry") or features.get("object") or {}
    preview = features.get("geometry_preview") or {}
    obj = geometry.get("object") if isinstance(geometry, dict) else {}
    if not isinstance(obj, dict):
        obj = geometry if isinstance(geometry, dict) else {}
    return {
        "available": 1.0 if geometry or preview else 0.0,
        "similarity": _clip(geometry.get("similarity") if isinstance(geometry, dict) else 0.0, 0.0),
        "orientation": _clip(obj.get("orientation") or preview.get("orientation"), 0.0),
        "length": _clip(obj.get("length") or preview.get("length"), 0.0),
        "nearest_distance": _clip(
            geometry.get("nearest_distance") if isinstance(geometry, dict) else 999.0,
            999.0,
        ),
        "has_bbox": 1.0 if (obj.get("bbox") or preview.get("bbox")) else 0.0,
    }


def engineer_graph_features(sample: dict) -> dict:
    features = sample.get("features") or {}
    graph = features.get("graph") or features.get("node") or {}
    preview = features.get("graph_preview") or {}
    if not isinstance(graph, dict):
        graph = {}
    return {
        "degree": _clip(graph.get("degree") or preview.get("degree"), 0.0),
        "structural_links": _clip(
            graph.get("structural_links") or preview.get("structural_links"), 0.0
        ),
        "graph_consistency": _clip(
            graph.get("graph_consistency") or preview.get("consistency"), 0.0
        ),
        "min_distance": _clip(graph.get("min_distance") or preview.get("min_distance"), 999.0),
        "has_neighborhood": 1.0
        if float(graph.get("degree") or preview.get("degree") or 0) > 0
        else 0.0,
    }


def engineer_fusion_features(sample: dict) -> dict:
    features = sample.get("features") or {}
    contributions = features.get("contributions") or features.get("evidence") or {}
    text = engineer_text_features(
        {**sample, "features": {"extraction": features.get("text") or {}}}
    )
    geometry = engineer_geometry_features(
        {**sample, "features": {"geometry": features.get("geometry") or {}}}
    )
    graph = engineer_graph_features(
        {**sample, "features": {"graph": features.get("graph") or {}}}
    )
    rules = features.get("engineering_rules") or {}
    return {
        "text_contrib": _clip(contributions.get("text"), 0.0),
        "ocr_contrib": _clip(contributions.get("ocr"), 0.0),
        "geometry_contrib": _clip(contributions.get("geometry"), 0.0),
        "graph_contrib": _clip(contributions.get("graph"), 0.0),
        "rules_contrib": _clip(
            contributions.get("engineering_rules")
            or contributions.get("engineering_context"),
            0.0,
        ),
        "database_contrib": _clip(contributions.get("database"), 0.0),
        "rule_score": _clip(rules.get("score"), 0.5),
        "text_confidence": _clip(text.get("extraction_confidence"), 0.5),
        "geometry_available": geometry.get("available", 0.0),
        "graph_available": graph.get("has_neighborhood", 0.0),
    }


ENGINEERS = {
    "text": engineer_text_features,
    "ocr": engineer_ocr_features,
    "layout": engineer_layout_features,
    "geometry": engineer_geometry_features,
    "graph": engineer_graph_features,
    "engineering": engineer_engineering_features,
    "fusion": engineer_fusion_features,
}


def apply_feature_engineering(samples: List[dict], modality: str) -> List[dict]:
    engineer = ENGINEERS[modality]
    enriched: List[dict] = []
    for sample in samples:
        row = dict(sample)
        engineered = engineer(sample)
        row["features"] = {
            **dict(sample.get("features") or {}),
            "engineered": engineered,
        }
        enriched.append(row)
    return enriched


def feature_schema_for(modality: str) -> List[str]:
    probes = {
        "text": engineer_text_features({"token": "W18X35", "features": {}}),
        "ocr": engineer_ocr_features({"token": "W18X35", "features": {}}),
        "layout": engineer_layout_features({"features": {}}),
        "geometry": engineer_geometry_features({"features": {}}),
        "graph": engineer_graph_features({"features": {}}),
        "engineering": engineer_engineering_features({"features": {}}),
        "fusion": engineer_fusion_features({"features": {}, "token": "W18X35"}),
    }
    return sorted(probes[modality].keys())
