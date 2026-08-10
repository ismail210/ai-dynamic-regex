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
from typing import Any, Dict, List, Optional, Sequence

from services.engineering.graph_builder import build_graph


# Only explicit structural WORDS may override the kind graph_builder already
# resolved. Shape-family patterns are deliberately excluded: matching "HSS" or
# "W16X26" here used to relabel every tube a brace and every wide flange a
# beam, overwriting better upstream evidence and reporting a role the drawing
# never stated.
_ENTITY_RULES = (
    ("bolt", re.compile(r"\b(?:A325|A490|A307|BOLT)\b", re.I)),
    ("weld", re.compile(r"\b(?:WELD|CJP|PJP|FILLET)\b", re.I)),
    ("plate", re.compile(r"\b(?:PLATE|BASE\s*PLATE|STIFFENER)\b", re.I)),
    ("brace", re.compile(r"\b(?:BRACE|BRACING)\b", re.I)),
    ("column", re.compile(r"\b(?:COLUMN|COL\.?)\b", re.I)),
    ("beam", re.compile(r"\b(?:BEAM|GIRDER|JOIST)\b", re.I)),
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

    semantic_window_cap = 350
    semantic_window_size = 44
    semantic_diagnostics_by_page: Dict[int, dict] = {}

    for page_number, page_nodes in by_page.items():
        # Bound pairwise work for large vector drawings.
        candidates = page_nodes[:semantic_window_cap]
        semantic_considered = 0
        for index, a in enumerate(candidates):
            for b in candidates[index + 1 : index + 1 + semantic_window_size]:
                semantic_considered += 1
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

        semantic_diagnostics_by_page[page_number] = {
            "semantic_node_count": len(page_nodes),
            "semantic_pairwise_window_cap": semantic_window_cap,
            "semantic_pairwise_window_size": semantic_window_size,
            "semantic_pairwise_window_triggered": len(page_nodes) > semantic_window_cap,
            "semantic_candidate_pairs_considered": semantic_considered,
        }

    # Merge the semantic-pass window diagnostics into build_graph's own
    # per-page diagnostics list (docs/ml_association_phase/) so a single
    # artifact shows both windowing regimes' coverage.
    for entry in graph.get("diagnostics") or []:
        entry.update(
            semantic_diagnostics_by_page.get(
                entry.get("page_number"),
                {
                    "semantic_node_count": 0,
                    "semantic_pairwise_window_cap": semantic_window_cap,
                    "semantic_pairwise_window_size": semantic_window_size,
                    "semantic_pairwise_window_triggered": False,
                    "semantic_candidate_pairs_considered": 0,
                },
            )
        )

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
            # Identity fields let consumers tell "this source really has a
            # graph node" apart from the not-found fallback below. Without
            # them every lookup looked like a miss.
            "source_node": node["node_id"],
            "node_kind": node.get("kind"),
            "graph_available": True,
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


def _normalized_node_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).upper()


def _bbox_key(bbox: Any) -> Optional[tuple]:
    if not bbox or len(bbox) < 4:
        return None
    try:
        return tuple(round(float(value), 1) for value in bbox[:4])
    except (TypeError, ValueError):
        return None


def build_source_lookup(graph: dict) -> Dict[str, Any]:
    """Index a graph for token→node resolution.

    Token ids are positional (``token_p3_32``), so they shift whenever
    extraction re-runs. A graph built from an earlier pass then shares no ids
    with the current document and every token silently loses its
    neighborhood. Page + bbox + text is stable across re-extraction, so it
    serves as the fallback identity.
    """

    sources: set = set()
    by_bbox: Dict[tuple, str] = {}
    by_text: Dict[tuple, List[str]] = {}
    for node in graph.get("nodes") or []:
        source_id = node.get("source_id")
        if not source_id:
            continue
        sources.add(str(source_id))
        # "txt_" prefix marks text nodes (see graph_builder.build_graph);
        # geometry nodes carry nearby_text that could collide with a label.
        if not str(node.get("node_id") or "").startswith("txt_"):
            continue
        text = _normalized_node_text(node.get("text"))
        if not text:
            continue
        page = int(node.get("page_number") or 0)
        bbox = _bbox_key(node.get("bbox"))
        if bbox is not None:
            by_bbox.setdefault((page, bbox, text), str(source_id))
        by_text.setdefault((page, text), []).append(str(source_id))
    return {"sources": sources, "by_bbox": by_bbox, "by_text": by_text}


def resolve_source_id(
    graph: dict,
    token: Dict[str, Any],
    *,
    lookup: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[str], str]:
    """Resolve a prediction token to a graph source id.

    Returns ``(source_id, how)`` where ``how`` records which identity matched,
    so a fallback match is never mistaken for an exact id hit.
    """

    index = lookup or build_source_lookup(graph)
    sources = index["sources"]
    for candidate, how in (
        (token.get("token_id"), "token_id"),
        ((token.get("line") or {}).get("id"), "line_id"),
        *((word_id, "word_id") for word_id in token.get("source_word_ids") or []),
    ):
        if candidate and str(candidate) in sources:
            return str(candidate), how

    text = _normalized_node_text(token.get("text") or token.get("raw_text"))
    if not text:
        return None, "unresolved"
    page = int(token.get("page") or 0)
    bbox = _bbox_key(token.get("bbox"))
    if bbox is not None:
        # Same text at the same place: a re-keyed token, safe to accept.
        matched = index["by_bbox"].get((page, bbox, text))
        if matched:
            return matched, "page_bbox_text"
    candidates = index["by_text"].get((page, text)) or []
    if len(candidates) == 1:
        # Only when unambiguous; duplicate tags on a page would otherwise
        # hand back some other member's neighborhood as if it were this one's.
        return candidates[0], "page_text"
    return None, "unresolved"


def graph_features_for_token(
    graph: dict,
    token: Dict[str, Any],
    *,
    lookup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Graph features for a prediction token, with id-drift fallbacks."""

    source_id, how = resolve_source_id(graph, token, lookup=lookup)
    features = graph_features_for_source(graph, source_id or "")
    features["source_match"] = how if source_id else "unresolved"
    return features


def graph_matches_document(graph: dict, document: Dict[str, Any]) -> bool:
    """True when a cached graph still covers the document's token ids.

    Guards artifact reuse: re-running extraction renumbers positional token
    ids, so a stale graph would leave those tokens without a neighborhood.
    """

    sources = {
        str(node.get("source_id"))
        for node in graph.get("nodes") or []
        if node.get("source_id")
    }
    if not sources:
        return False
    tokens = [
        token
        for token in document.get("engineering_tokens") or []
        if str(token.get("text") or "").strip()
    ]
    return all(str(token.get("token_id")) in sources for token in tokens)


def _node_for_source(graph: dict, source_id: Any) -> Optional[dict]:
    """Find the graph node for a source object id, comparing as strings.

    Node ``source_id`` values round-trip through JSON artifacts, so a raw
    ``==`` against a non-string caller id can miss a node that exists.
    """

    wanted = str(source_id)
    return next(
        (
            candidate
            for candidate in graph.get("nodes") or []
            if str(candidate.get("source_id")) == wanted
        ),
        None,
    )


def graph_features_for_source(graph: dict, source_id: str) -> Dict[str, Any]:
    """Build model-neutral numeric graph features for one source object.

    Always reports ``graph_available`` / ``source_node`` so callers can
    distinguish a real graph neighborhood from the not-found fallback.
    """

    cached = (graph.get("source_features") or {}).get(str(source_id))
    if cached is not None:
        features = dict(cached)
        if not features.get("source_node"):
            # Graph artifacts written before identity fields existed are
            # reused on re-analysis; backfill from the node list instead of
            # reporting a spurious miss.
            cached_node = _node_for_source(graph, source_id)
            if cached_node:
                features["source_node"] = cached_node["node_id"]
                features.setdefault("node_kind", cached_node.get("kind"))
        features["graph_available"] = bool(features.get("source_node"))
        return features

    node = _node_for_source(graph, source_id)
    if not node:
        return {
            "source_node": None,
            "node_kind": None,
            "graph_available": False,
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
        "source_node": node["node_id"],
        "node_kind": node.get("kind"),
        "graph_available": True,
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
