"""
Structural semantic graph enrichment.

Adds domain nodes and directed relationships on top of the existing spatial
graph. The resulting JSON remains framework-neutral for future NetworkX,
GraphSAGE, GCN, or graph-database adapters.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Sequence

from services.engineering.graph_builder import build_graph


_ENTITY_RULES = (
    ("bolt", re.compile(r"\b(?:A325|A490|A307|BOLT)\b", re.I)),
    ("weld", re.compile(r"\b(?:WELD|CJP|PJP|FILLET)\b", re.I)),
    ("plate", re.compile(r"\b(?:PL|PLATE|BASE\s*PLATE|STIFFENER)\b", re.I)),
    ("brace", re.compile(r"\b(?:BRACE|BRACING|HSS|2L)\b", re.I)),
    ("column", re.compile(r"\b(?:COLUMN|COL\.?)\b", re.I)),
    ("beam", re.compile(r"\b(?:BEAM|GIRDER|W\d+X\d+)\b", re.I)),
    ("connection", re.compile(r"\b(?:CONNECTION|CONN\.?|CLIP\s*ANGLE)\b", re.I)),
)


def _center(node: dict) -> Sequence[float]:
    return node.get("center") or (0.0, 0.0)


def _distance(a: dict, b: dict) -> float:
    ac, bc = _center(a), _center(b)
    return math.hypot(float(ac[0]) - float(bc[0]), float(ac[1]) - float(bc[1]))


def _semantic_kind(node: dict) -> str:
    text = str(node.get("text") or "")
    for kind, pattern in _ENTITY_RULES:
        if pattern.search(text):
            return kind
    geometry_kind = node.get("geometry_kind")
    if geometry_kind == "leader":
        return "connection"
    return str(node.get("kind") or "other")


def _edge(
    source: dict,
    target: dict,
    relationship: str,
    *,
    confidence: float,
    reason: str,
) -> dict:
    return {
        "edge_id": (
            f"semantic_{relationship}_{source['node_id']}_{target['node_id']}"
        ),
        "source": source["node_id"],
        "target": target["node_id"],
        "relationship": relationship,
        "distance": round(_distance(source, target), 2),
        "weight": round(confidence, 4),
        "page_number": source.get("page_number"),
        "meta": {"reason": reason, "semantic": True},
    }


def build_structural_graph(
    document_structure: dict,
    geometry: dict,
    *,
    max_near_distance: float = 180.0,
) -> Dict[str, Any]:
    """Build and enrich the base graph with structural semantics."""

    graph = build_graph(document_structure, geometry)
    nodes = graph["nodes"]
    edges = graph["edges"]

    for node in nodes:
        node["base_kind"] = node.get("kind")
        node["kind"] = _semantic_kind(node)
        node["features"] = {
            "length": float(node.get("length") or 0.0),
            "width": float(node.get("width") or 0.0),
            "area": float(node.get("area") or 0.0),
            "orientation": float(node.get("orientation") or 0.0),
            "font_size": float(node.get("font_size") or 0.0),
        }

    by_page: Dict[int, List[dict]] = {}
    for node in nodes:
        by_page.setdefault(int(node.get("page_number") or 0), []).append(node)

    existing = {
        (edge["source"], edge["target"], edge["relationship"]) for edge in edges
    }

    def add(source: dict, target: dict, relationship: str, confidence: float, reason: str) -> None:
        key = (source["node_id"], target["node_id"], relationship)
        if key not in existing:
            edges.append(
                _edge(
                    source,
                    target,
                    relationship,
                    confidence=confidence,
                    reason=reason,
                )
            )
            existing.add(key)

    for page_nodes in by_page.values():
        # Bound pairwise work for large vector drawings.
        candidates = page_nodes[:350]
        for index, a in enumerate(candidates):
            for b in candidates[index + 1 : index + 45]:
                distance = _distance(a, b)
                if distance > max_near_distance:
                    continue
                if distance <= max_near_distance:
                    add(a, b, "near", max(0.1, 1 - distance / max_near_distance), "spatial proximity")

                ay, by = _center(a)[1], _center(b)[1]
                vertical_gap = abs(float(ay) - float(by))
                if vertical_gap > 8:
                    if ay < by:
                        add(a, b, "above", 0.72, "center elevation")
                        add(b, a, "below", 0.72, "center elevation")
                    else:
                        add(b, a, "above", 0.72, "center elevation")
                        add(a, b, "below", 0.72, "center elevation")

                kinds = {a["kind"], b["kind"]}
                if "beam" in kinds and "column" in kinds and distance < 90:
                    beam = a if a["kind"] == "beam" else b
                    column = b if beam is a else a
                    add(beam, column, "supported_by", 0.82, "beam-column proximity")
                    add(column, beam, "supports", 0.82, "beam-column proximity")

                if "connection" in kinds and distance < 70:
                    connection = a if a["kind"] == "connection" else b
                    member = b if connection is a else a
                    add(connection, member, "connected_to", 0.78, "connection/member proximity")

                if "bolt" in kinds and (
                    "plate" in kinds or "connection" in kinds
                ) and distance < 55:
                    bolt = a if a["kind"] == "bolt" else b
                    host = b if bolt is a else a
                    add(bolt, host, "inside", 0.75, "fastener within connection zone")

    node_counts = Counter(node["kind"] for node in nodes)
    edge_counts = Counter(edge["relationship"] for edge in edges)
    graph["stats"].update(
        {
            "nodes_by_kind": dict(node_counts),
            "edges_by_relationship": dict(edge_counts),
            "semantic_edge_count": sum(
                bool((edge.get("meta") or {}).get("semantic")) for edge in edges
            ),
        }
    )
    graph["schema"] = {
        "node_kinds": [
            "steel_section",
            "connection",
            "plate",
            "bolt",
            "weld",
            "column",
            "beam",
            "brace",
            "geometry",
            "text",
        ],
        "relationships": [
            "connected_to",
            "touches",
            "supports",
            "supported_by",
            "intersects",
            "above",
            "below",
            "inside",
            "near",
        ],
        "future_models": ["GCN", "GraphSAGE", "graph_transformer"],
    }
    incident_by_node: Dict[str, List[dict]] = {
        node["node_id"]: [] for node in nodes
    }
    for edge in edges:
        incident_by_node.get(edge.get("source"), []).append(edge)
        incident_by_node.get(edge.get("target"), []).append(edge)
    structural_relations = {
        "connected_to",
        "supports",
        "supported_by",
        "inside",
        "touches",
        "intersects",
        "near",
    }
    source_features: Dict[str, dict] = {}
    for node in nodes:
        source_id = node.get("source_id")
        if not source_id:
            continue
        incident = incident_by_node.get(node["node_id"], [])
        distances = [
            float(edge["distance"])
            for edge in incident
            if edge.get("distance") is not None
        ]
        structural_count = sum(
            edge.get("relationship") in structural_relations
            for edge in incident
        )
        source_features[str(source_id)] = {
            "degree": float(len(incident)),
            "geometry_links": float(
                sum(
                    edge.get("relationship")
                    in {"nearest_geometry", "nearest_label"}
                    for edge in incident
                )
            ),
            "structural_links": float(structural_count),
            "min_distance": min(distances) if distances else 999.0,
            "graph_consistency": round(
                min(1.0, 0.35 + structural_count * 0.09), 4
            ),
        }
    graph["source_features"] = source_features
    return graph


def graph_features_for_source(graph: dict, source_id: str) -> Dict[str, float]:
    """Build model-neutral numeric graph features for one source object."""

    cached = (graph.get("source_features") or {}).get(str(source_id))
    if cached is not None:
        return dict(cached)

    node = next(
        (
            candidate
            for candidate in graph.get("nodes") or []
            if candidate.get("source_id") == source_id
        ),
        None,
    )
    if not node:
        return {
            "degree": 0.0,
            "geometry_links": 0.0,
            "structural_links": 0.0,
            "min_distance": 999.0,
            "graph_consistency": 0.35,
        }
    incident = [
        edge
        for edge in graph.get("edges") or []
        if node["node_id"] in {edge.get("source"), edge.get("target")}
    ]
    distances = [
        float(edge["distance"])
        for edge in incident
        if edge.get("distance") is not None
    ]
    structural = {
        "connected_to",
        "supports",
        "supported_by",
        "inside",
        "touches",
        "intersects",
        "near",
    }
    structural_count = sum(
        edge.get("relationship") in structural for edge in incident
    )
    consistency = min(1.0, 0.35 + structural_count * 0.09)
    return {
        "degree": float(len(incident)),
        "geometry_links": float(
            sum(
                edge.get("relationship")
                in {"nearest_geometry", "nearest_label"}
                for edge in incident
            )
        ),
        "structural_links": float(structural_count),
        "min_distance": min(distances) if distances else 999.0,
        "graph_consistency": round(consistency, 4),
    }
