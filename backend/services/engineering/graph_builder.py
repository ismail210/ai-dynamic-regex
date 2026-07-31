"""
Graph Builder
=============

Builds a spatial / semantic graph over extracted text and geometry objects.

Nodes
-----
text, geometry, dimension, label, beam, column, other

Edges / relationships
---------------------
nearest_label, nearest_geometry, distance, intersection, containment,
touching, connected, reference

Output JSON::

    {
      "nodes": [...],
      "edges": [...],
      "stats": {...}
    }
"""

from __future__ import annotations

import math
import re
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.engineering.models import NodeKind, RelationKind


BEAM_RE = re.compile(r"^(W|S|M|HP|C|MC|WT|MT|ST|HSS|PIPE|L)\d", re.I)
COLUMN_HINT_RE = re.compile(r"\b(COL|COLUMN|W\d+X\d+)\b", re.I)
LABEL_RE = re.compile(
    r"^(W\d+X\d+|HSS\d+X\d+(?:X[\d/]+)?|L\d+X\d+(?:X[\d/]+)?|PIPE\d+|PL\d+|A\d+)$",
    re.I,
)
_OBJECT_NODE_KIND = {
    "beam": NodeKind.BEAM,
    "steel_section": NodeKind.BEAM,
    "column": NodeKind.COLUMN,
    "column_or_brace": NodeKind.COLUMN,
    "plate": NodeKind.PLATE,
    "brace": NodeKind.BRACE,
    "bolt": NodeKind.BOLT,
    "weld": NodeKind.WELD,
    "connection": NodeKind.CONNECTION,
}


def _nid(prefix: str = "node") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _intersects(a: Sequence[float], b: Sequence[float], pad: float = 1.0) -> bool:
    return not (
        a[2] + pad < b[0]
        or b[2] + pad < a[0]
        or a[3] + pad < b[1]
        or b[3] + pad < a[1]
    )


def _contains(outer: Sequence[float], inner: Sequence[float], tol: float = 1.0) -> bool:
    return (
        outer[0] - tol <= inner[0]
        and outer[1] - tol <= inner[1]
        and outer[2] + tol >= inner[2]
        and outer[3] + tol >= inner[3]
    )


def _touches(a: Sequence[float], b: Sequence[float], tol: float = 2.5) -> bool:
    if _intersects(a, b, pad=tol) and not _intersects(a, b, pad=-tol):
        return True
    return False


def _classify_text_node(text: str) -> NodeKind:
    cleaned = (text or "").strip().upper().replace(" ", "")
    if LABEL_RE.match(cleaned):
        if COLUMN_HINT_RE.search(text or ""):
            return NodeKind.COLUMN
        if BEAM_RE.match(cleaned):
            return NodeKind.BEAM
        return NodeKind.LABEL
    if COLUMN_HINT_RE.search(text or ""):
        return NodeKind.COLUMN
    return NodeKind.TEXT


def build_graph(
    document_structure: dict,
    geometry: dict,
    *,
    max_edge_distance: float = 160.0,
) -> Dict[str, Any]:
    """Construct node/edge graph from document text + geometry extraction."""

    nodes: List[dict] = []
    edges: List[dict] = []
    id_index: Dict[str, dict] = {}
    # Prediction-ready engineering objects become semantic graph nodes. Body
    # prose is excluded upstream by ``engineering_object_filter``.
    for token in document_structure.get("engineering_tokens") or []:
        text = str(token.get("text") or "").strip()
        if not text:
            continue
        kind = _OBJECT_NODE_KIND.get(
            str(token.get("engineering_object_type") or ""),
            _classify_text_node(text),
        )
        line = token.get("line") or {}
        bbox = token.get("bbox") or [0, 0, 0, 0]
        node = {
            "node_id": _nid("txt"),
            "source_id": token.get("token_id"),
            "kind": kind.value,
            "page_number": token.get("page"),
            "text": text,
            "bbox": bbox,
            "center": [
                round((float(bbox[0]) + float(bbox[2])) / 2.0, 3),
                round((float(bbox[1]) + float(bbox[3])) / 2.0, 3),
            ],
            "font_size": token.get("font_size"),
            "rotation": token.get("rotation"),
            "drawing_references": line.get("drawing_references") or [],
            "engineering_object_type": token.get("engineering_object_type"),
        }
        nodes.append(node)
        id_index[node["node_id"]] = node

    # Geometry nodes
    for geom in geometry.get("objects") or []:
        kind = NodeKind.DIMENSION if geom.get("kind") == "dimension" else NodeKind.GEOMETRY
        if geom.get("kind") == "leader":
            kind = NodeKind.CONNECTION
        node = {
            "node_id": _nid("geo"),
            "source_id": geom.get("geometry_id"),
            "kind": kind.value,
            "page_number": geom.get("page_number"),
            "text": geom.get("nearby_text") or "",
            "bbox": geom.get("bbox"),
            "center": geom.get("center"),
            "geometry_kind": geom.get("kind"),
            "length": geom.get("length"),
            "width": geom.get("width"),
            "area": geom.get("area"),
            "orientation": geom.get("orientation"),
        }
        nodes.append(node)
        id_index[node["node_id"]] = node

    semantic_kinds = {
        NodeKind.TEXT.value,
        NodeKind.LABEL.value,
        NodeKind.BEAM.value,
        NodeKind.COLUMN.value,
        NodeKind.PLATE.value,
        NodeKind.BRACE.value,
        NodeKind.BOLT.value,
        NodeKind.WELD.value,
        NodeKind.CONNECTION.value,
    }
    text_nodes = [
        n
        for n in nodes
        if n["kind"] in semantic_kinds
        and str(n.get("node_id") or "").startswith("txt_")
    ]
    geom_nodes = [n for n in nodes if n["kind"] in {NodeKind.GEOMETRY.value, NodeKind.DIMENSION.value, NodeKind.CONNECTION.value}]
    label_nodes = list(text_nodes)

    def add_edge(
        source: dict,
        target: dict,
        relation: RelationKind,
        *,
        distance: Optional[float] = None,
        weight: float = 1.0,
        meta: Optional[dict] = None,
    ) -> None:
        edges.append(
            {
                "edge_id": _nid("edge"),
                "source": source["node_id"],
                "target": target["node_id"],
                "relationship": relation.value,
                "distance": None if distance is None else round(distance, 2),
                "weight": round(weight, 4),
                "page_number": source.get("page_number"),
                "meta": meta or {},
            }
        )

    # Spatial relationships page-wise
    by_page: Dict[int, List[dict]] = {}
    for n in nodes:
        by_page.setdefault(int(n.get("page_number") or 0), []).append(n)

    for page_nodes in by_page.values():
        page_text = [
            n
            for n in page_nodes
            if n["kind"] in semantic_kinds
            and str(n.get("node_id") or "").startswith("txt_")
        ]
        page_geom = [
            n
            for n in page_nodes
            if n["kind"]
            in {
                NodeKind.GEOMETRY.value,
                NodeKind.DIMENSION.value,
                NodeKind.CONNECTION.value,
            }
        ]
        page_labels = [
            n
            for n in page_nodes
            if n["kind"] in semantic_kinds
            and str(n.get("node_id") or "").startswith("txt_")
        ]
        label_grid: Dict[Tuple[int, int], List[dict]] = {}
        geometry_grid: Dict[Tuple[int, int], List[dict]] = {}
        for item, grid in [
            *((label, label_grid) for label in (page_labels or page_text)),
            *((geometry_node, geometry_grid) for geometry_node in page_geom),
        ]:
            center = item.get("center") or [0, 0]
            key = (
                int(float(center[0]) // max_edge_distance),
                int(float(center[1]) // max_edge_distance),
            )
            grid.setdefault(key, []).append(item)

        def nearby(grid: Dict[Tuple[int, int], List[dict]], center: list) -> List[dict]:
            cx = int(float(center[0]) // max_edge_distance)
            cy = int(float(center[1]) // max_edge_distance)
            return [
                item
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                for item in grid.get((cx + dx, cy + dy), [])
            ]

        # Nearest label for each geometry
        for g in page_geom:
            nearest: Optional[Tuple[float, dict]] = None
            for lab in nearby(label_grid, g["center"]):
                d = _dist(g["center"], lab["center"])
                if d > max_edge_distance:
                    continue
                if nearest is None or d < nearest[0]:
                    nearest = (d, lab)
            if nearest:
                add_edge(g, nearest[1], RelationKind.NEAREST_LABEL, distance=nearest[0], weight=1.0 / (1.0 + nearest[0]))

        # Nearest geometry for each label
        for lab in page_labels:
            nearest = None
            for g in nearby(geometry_grid, lab["center"]):
                d = _dist(lab["center"], g["center"])
                if d > max_edge_distance:
                    continue
                if nearest is None or d < nearest[0]:
                    nearest = (d, g)
            if nearest:
                add_edge(lab, nearest[1], RelationKind.NEAREST_GEOMETRY, distance=nearest[0], weight=1.0 / (1.0 + nearest[0]))

        # Pairwise geometric relations (sampled for large pages)
        candidates = page_geom[:60]
        for i, a in enumerate(candidates):
            for b in candidates[i + 1 : i + 12]:
                if a["node_id"] == b["node_id"]:
                    continue
                d = _dist(a["center"], b["center"])
                if d <= max_edge_distance:
                    add_edge(a, b, RelationKind.DISTANCE, distance=d, weight=1.0 / (1.0 + d))
                    add_edge(a, b, RelationKind.ADJACENT, distance=d)
                    dx = float(b["center"][0]) - float(a["center"][0])
                    dy = float(b["center"][1]) - float(a["center"][1])
                    if abs(dx) >= abs(dy):
                        add_edge(
                            a,
                            b,
                            RelationKind.LEFT_OF
                            if dx >= 0
                            else RelationKind.RIGHT_OF,
                            distance=d,
                        )
                    else:
                        add_edge(
                            a,
                            b,
                            RelationKind.ABOVE
                            if dy >= 0
                            else RelationKind.BELOW,
                            distance=d,
                        )
                    angle_delta = abs(
                        float(a.get("orientation") or 0.0)
                        - float(b.get("orientation") or 0.0)
                    ) % 180.0
                    angle_delta = min(angle_delta, 180.0 - angle_delta)
                    if angle_delta <= 8.0:
                        add_edge(a, b, RelationKind.PARALLEL, distance=d)
                    elif abs(angle_delta - 90.0) <= 8.0:
                        add_edge(a, b, RelationKind.PERPENDICULAR, distance=d)
                if _intersects(a["bbox"], b["bbox"]):
                    add_edge(a, b, RelationKind.INTERSECTION, distance=d)
                    add_edge(a, b, RelationKind.INTERSECTS, distance=d)
                if _contains(a["bbox"], b["bbox"]):
                    add_edge(a, b, RelationKind.CONTAINMENT, distance=d)
                    add_edge(b, a, RelationKind.INSIDE, distance=d)
                elif _contains(b["bbox"], a["bbox"]):
                    add_edge(b, a, RelationKind.CONTAINMENT, distance=d)
                    add_edge(a, b, RelationKind.INSIDE, distance=d)
                if _touches(a["bbox"], b["bbox"]):
                    add_edge(a, b, RelationKind.TOUCHING, distance=d)
                # Connected: touching or intersecting with similar orientation
                if _intersects(a["bbox"], b["bbox"], pad=3.0):
                    add_edge(a, b, RelationKind.CONNECTED, distance=d)
                    add_edge(a, b, RelationKind.CONNECTED_TO, distance=d)
                    horizontal_overlap = not (
                        float(a["bbox"][2]) < float(b["bbox"][0])
                        or float(b["bbox"][2]) < float(a["bbox"][0])
                    )
                    if horizontal_overlap:
                        lower, upper = (
                            (a, b)
                            if float(a["center"][1]) >= float(b["center"][1])
                            else (b, a)
                        )
                        add_edge(lower, upper, RelationKind.SUPPORTS, distance=d)

        # Drawing references from text
        for tnode in page_text:
            refs = tnode.get("drawing_references") or []
            if not refs:
                continue
            for other in page_text:
                if other["node_id"] == tnode["node_id"]:
                    continue
                other_refs = set(other.get("drawing_references") or [])
                shared = set(refs) & other_refs
                if shared:
                    add_edge(
                        tnode,
                        other,
                        RelationKind.REFERENCE,
                        distance=_dist(tnode["center"], other["center"]),
                        meta={"shared_references": sorted(shared)},
                    )

    kind_counts: Dict[str, int] = {}
    for n in nodes:
        kind_counts[n["kind"]] = kind_counts.get(n["kind"], 0) + 1
    rel_counts: Dict[str, int] = {}
    for e in edges:
        rel_counts[e["relationship"]] = rel_counts.get(e["relationship"], 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes_by_kind": kind_counts,
            "edges_by_relationship": rel_counts,
            "label_count": len(label_nodes),
            "geometry_count": len(geom_nodes),
        },
    }
