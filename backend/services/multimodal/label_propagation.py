"""Propagate high-confidence section labels across structural graph edges."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

from services.engineering.detail_regions import same_region

_PROPAGATION_RELATIONS = {
    "same_tag",
    "connected_to",
    "connected",
    "supports",
    "reference",
}
_SEED_MIN_CONFIDENCE = 0.8


def _overall_confidence(prediction: Dict[str, Any]) -> float:
    confidence = prediction.get("confidence")
    if isinstance(confidence, dict):
        return float(confidence.get("overall") or 0.0)
    return float(confidence or prediction.get("ranking_score") or 0.0)


def _section(prediction: Dict[str, Any]) -> str:
    return str(
        prediction.get("section")
        or prediction.get("predicted_shape")
        or prediction.get("prediction")
        or ((prediction.get("canonical") or {}).get("prediction") or {}).get(
            "final_label"
        )
        or ""
    ).strip()


def _is_geometry_only(prediction: Dict[str, Any]) -> bool:
    comparison = prediction.get("comparison") or {}
    if comparison.get("match_status") == "geometry_only":
        return True
    if prediction.get("missing_label_prediction"):
        return True
    if prediction.get("prediction_source") == "Geometry":
        return True
    source = prediction.get("source_text") or {}
    return not bool(source.get("available") or prediction.get("raw_text"))


def _token_keys(prediction: Dict[str, Any]) -> Set[str]:
    keys = {
        str(prediction.get("object_id") or ""),
        str(prediction.get("component_id") or ""),
        str(prediction.get("token_id") or ""),
    }
    return {key for key in keys if key}


def _adjacency(graph: Dict[str, Any]) -> Dict[str, Set[str]]:
    adjacency: Dict[str, Set[str]] = {}
    nodes = {str(node.get("node_id") or ""): node for node in graph.get("nodes") or []}
    source_ids: Dict[str, str] = {}
    for node_id, node in nodes.items():
        source = str(node.get("source_id") or "")
        if source:
            source_ids[node_id] = source
            adjacency.setdefault(source, set())
        adjacency.setdefault(node_id, set())

    for edge in graph.get("edges") or []:
        relation = str(edge.get("relationship") or edge.get("relation") or "")
        if relation not in _PROPAGATION_RELATIONS:
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            continue
        left = source_ids.get(source, source)
        right = source_ids.get(target, target)
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
        # Also keep node-id links so geometry nodes can receive labels.
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
    return adjacency


def propagate_section_labels(
    predictions: List[Dict[str, Any]],
    graph: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Copy high-confidence text-backed sections onto low-confidence neighbors.

    Never overwrites a high-confidence OCR exact / normalized match.
    """

    if not predictions or not graph:
        return predictions

    adjacency = _adjacency(graph)
    by_key: Dict[str, Dict[str, Any]] = {}
    for prediction in predictions:
        for key in _token_keys(prediction):
            by_key[key] = prediction

    seeds: List[tuple[str, str, float]] = []
    for prediction in predictions:
        section = _section(prediction)
        confidence = _overall_confidence(prediction)
        if (
            not section
            or confidence < _SEED_MIN_CONFIDENCE
            or _is_geometry_only(prediction)
        ):
            continue
        comparison = (prediction.get("comparison") or {}).get("match_status")
        if comparison in {"exact_match", "normalized_match"} or confidence >= _SEED_MIN_CONFIDENCE:
            for key in _token_keys(prediction):
                seeds.append((key, section, confidence))

    for seed_key, section, seed_confidence in seeds:
        for neighbor_key in adjacency.get(seed_key) or ():
            neighbor = by_key.get(neighbor_key)
            if neighbor is None:
                continue
            if not same_region(
                prediction.get("region_id"),
                neighbor.get("region_id"),
            ):
                continue
            neighbor_confidence = _overall_confidence(neighbor)
            comparison = (neighbor.get("comparison") or {}).get("match_status")
            if (
                comparison in {"exact_match", "normalized_match"}
                and neighbor_confidence >= _SEED_MIN_CONFIDENCE
            ):
                continue
            if neighbor_confidence >= seed_confidence:
                continue
            current = _section(neighbor)
            if current == section:
                neighbor["propagated_section"] = section
                continue
            if neighbor_confidence >= 0.8 and current and not _is_geometry_only(neighbor):
                continue
            neighbor["propagated_section"] = section
            neighbor["section"] = section
            neighbor["predicted_shape"] = section
            neighbor["prediction"] = section
            neighbor["label_propagation"] = {
                "from": seed_key,
                "section": section,
                "seed_confidence": round(seed_confidence, 4),
            }
            confidence = neighbor.get("confidence")
            if isinstance(confidence, dict):
                confidence["overall"] = max(
                    float(confidence.get("overall") or 0.0),
                    min(0.85, seed_confidence * 0.9),
                )
            if neighbor.get("canonical") and isinstance(neighbor["canonical"], dict):
                prediction_block = neighbor["canonical"].setdefault("prediction", {})
                prediction_block["final_label"] = section
    return predictions
