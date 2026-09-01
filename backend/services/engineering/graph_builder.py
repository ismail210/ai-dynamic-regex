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

import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.engineering.detail_regions import same_region
from services.engineering.drawing_scale import association_radius_from_geometry
from services.engineering.models import NodeKind, RelationKind


BEAM_RE = re.compile(r"^(W|S|M|HP|C|MC|WT|MT|ST|HSS|PIPE|L)\d", re.I)
COLUMN_WORD_RE = re.compile(r"\b(?:COL|COLUMN)\b", re.I)
BEAM_WORD_RE = re.compile(r"\b(?:BEAM|GIRDER|JOIST)\b", re.I)
BRACE_WORD_RE = re.compile(r"\b(?:BRACE|BRACING)\b", re.I)
LABEL_RE = re.compile(
    r"^(W\d+X\d+|HSS\d+X\d+(?:X[\d/]+)?|L\d+X\d+(?:X[\d/]+)?|PIPE\d+|PL\d+|A\d+)$",
    re.I,
)
# Longest families first so WT/MT/ST/MC/HP are not read as W/M/S/C/H. The
# optional leading count covers built-up members written as "2L3X3X1/4".
SECTION_FAMILY_RE = re.compile(
    r"^\d?(HSS|PIPE|WT|MT|ST|MC|HP|PL|W|S|M|C|L)(?=\d)", re.I
)
# An AISC shape family constrains the *section*, not always the member's
# structural role. Only families whose role is genuinely implied by the shape
# get a role kind; channels, angles, tees and tubes stay neutral instead of
# being mislabeled "beam".
_FAMILY_NODE_KIND = {
    "W": NodeKind.BEAM,
    "S": NodeKind.BEAM,
    "M": NodeKind.BEAM,
    "HP": NodeKind.COLUMN,
    "PL": NodeKind.PLATE,
    "C": NodeKind.STEEL_SECTION,
    "MC": NodeKind.STEEL_SECTION,
    "L": NodeKind.STEEL_SECTION,
    "WT": NodeKind.STEEL_SECTION,
    "MT": NodeKind.STEEL_SECTION,
    "ST": NodeKind.STEEL_SECTION,
    "HSS": NodeKind.STEEL_SECTION,
    "PIPE": NodeKind.STEEL_SECTION,
}
# Upstream detection types that name a real role. "steel_section" is
# deliberately absent: it means "a catalog member" and says nothing about the
# role, so it is resolved from the label family instead.
_OBJECT_NODE_KIND = {
    "beam": NodeKind.BEAM,
    "column": NodeKind.COLUMN,
    "column_or_brace": NodeKind.COLUMN,
    "plate": NodeKind.PLATE,
    "brace": NodeKind.BRACE,
    "bolt": NodeKind.BOLT,
    "weld": NodeKind.WELD,
    "connection": NodeKind.CONNECTION,
}


def _nid(prefix: str, *parts: Any) -> str:
    """Deterministic node/edge ID derived from stable identifying facts.

    Two builds over the same document produce byte-identical ``graph.json``
    output, which lets diagnostics, regression tests, and reviewer tooling
    diff runs meaningfully. Previously this used ``uuid.uuid4()``, which
    made every graph build of the same document produce different IDs.
    """

    seed = "|".join(str(p) for p in parts)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


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


def section_family(text: str) -> str:
    """Return the AISC shape family of a label, or "" when it is not one."""

    match = SECTION_FAMILY_RE.match((text or "").strip().upper().replace(" ", ""))
    return match.group(1).upper() if match else ""


def _classify_text_node(text: str) -> NodeKind:
    cleaned = (text or "").strip().upper().replace(" ", "")
    # An explicit role word outranks the shape family it is written next to.
    if COLUMN_WORD_RE.search(text or ""):
        return NodeKind.COLUMN
    if BRACE_WORD_RE.search(text or ""):
        return NodeKind.BRACE
    if BEAM_WORD_RE.search(text or ""):
        return NodeKind.BEAM
    family = section_family(cleaned)
    if family:
        return _FAMILY_NODE_KIND[family]
    if LABEL_RE.match(cleaned):
        return NodeKind.LABEL
    return NodeKind.TEXT


def build_text_nodes(document_structure: dict) -> List[dict]:
    """Construct text/label graph nodes from ``document_structure``.

    Extracted from ``build_graph`` so the experimental STRtree candidate
    generator (``services.engineering.spatial_index``) can build the same
    node shape without duplicating this logic or drifting from it. Body
    prose is excluded upstream by ``engineering_object_filter``.
    """

    nodes: List[dict] = []
    for token_index, token in enumerate(document_structure.get("engineering_tokens") or []):
        text = str(token.get("text") or "").strip()
        if not text:
            continue
        kind = _OBJECT_NODE_KIND.get(
            str(token.get("engineering_object_type") or "")
        ) or _classify_text_node(text)
        line = token.get("line") or {}
        bbox = token.get("bbox") or [0, 0, 0, 0]
        token_id = token.get("token_id") or f"idx{token_index}"
        nodes.append(
            {
                "node_id": _nid("txt", token_id, token_index),
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
                "region_id": token.get("region_id"),
            }
        )
    return nodes


def build_geometry_nodes(geometry: dict) -> List[dict]:
    """Construct geometry graph nodes from a ``geometry`` extraction dict.

    See ``build_text_nodes`` docstring for why this is a standalone,
    reusable function rather than inline code in ``build_graph``.
    """

    nodes: List[dict] = []
    for geom_index, geom in enumerate(geometry.get("objects") or []):
        kind = NodeKind.DIMENSION if geom.get("kind") == "dimension" else NodeKind.GEOMETRY
        if geom.get("kind") == "leader":
            kind = NodeKind.CONNECTION
        geometry_id = geom.get("geometry_id") or f"idx{geom_index}"
        nodes.append(
            {
                "node_id": _nid("geo", geometry_id, geom_index),
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
                "region_id": geom.get("region_id"),
            }
        )
    return nodes


def build_graph(
    document_structure: dict,
    geometry: dict,
    *,
    max_edge_distance: Optional[float] = None,
) -> Dict[str, Any]:
    """Construct node/edge graph from document text + geometry extraction."""

    from services.engineering.spatial_index import (
        build_page_index,
        nearest_geometry_candidates,
        spatially_complete_geometry_pairs,
    )

    if max_edge_distance is None:
        max_edge_distance = association_radius_from_geometry(geometry)

    edges: List[dict] = []
    id_index: Dict[str, dict] = {}
    nodes: List[dict] = build_text_nodes(document_structure) + build_geometry_nodes(geometry)
    for node in nodes:
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

    # Occurrence counter disambiguates the rare case of two edges sharing
    # the same (source, target, relation) triple, keeping edge_id
    # deterministic without ever colliding.
    edge_occurrence: Dict[Tuple[str, str, str], int] = {}

    def add_edge(
        source: dict,
        target: dict,
        relation: RelationKind,
        *,
        distance: Optional[float] = None,
        weight: float = 1.0,
        meta: Optional[dict] = None,
    ) -> None:
        edge_key = (source["node_id"], target["node_id"], relation.value)
        occurrence = edge_occurrence.get(edge_key, 0)
        edge_occurrence[edge_key] = occurrence + 1
        edges.append(
            {
                "edge_id": _nid("edge", *edge_key, occurrence),
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

    # Per-page diagnostics for the ML-association Phase 1 observability work
    # (docs/ml_association_phase/). These make the windowed pairwise loop's
    # coverage loss visible instead of silent — see
    # docs/geometry_graph_audit/04_graph_audit.md §5 and §12.
    diagnostics: List[dict] = []
    geometry_pairwise_window_cap = 60
    geometry_pairwise_window_size = 12

    for page_number_key, page_nodes in by_page.items():
        pairwise_considered = 0
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
                if not same_region(g.get("region_id"), lab.get("region_id")):
                    continue
                d = _dist(g["center"], lab["center"])
                if d > max_edge_distance:
                    continue
                if nearest is None or d < nearest[0]:
                    nearest = (d, lab)
            if nearest:
                add_edge(g, nearest[1], RelationKind.NEAREST_LABEL, distance=nearest[0], weight=1.0 / (1.0 + nearest[0]))

        # Nearest geometry for each label — leader-aware spatial index (P1.2/P1.7).
        geom_by_id = {g["node_id"]: g for g in page_geom}
        tree, ordered_geom = build_page_index(page_geom)
        leader_resolved_count = 0
        for lab in page_labels:
            if tree is None or not ordered_geom:
                continue
            candidates = nearest_geometry_candidates(
                lab,
                tree,
                ordered_geom,
                max_distance=max_edge_distance,
                top_k=3,
            )
            if not candidates:
                continue
            best = candidates[0]
            target = geom_by_id.get(best.node_id)
            if target is None:
                continue
            leader_resolved = "leader_endpoint_resolved" in best.sources
            if leader_resolved:
                leader_resolved_count += 1
            add_edge(
                lab,
                target,
                RelationKind.NEAREST_GEOMETRY,
                distance=best.distance,
                weight=1.0 / (1.0 + best.distance),
                meta={
                    "association_sources": list(best.sources),
                    "leader_resolved": leader_resolved,
                    "candidate_count": len(candidates),
                },
            )

        # Pairwise geometric relations — spatially complete via STRtree (P1.2).
        pairwise_pairs = spatially_complete_geometry_pairs(
            page_geom, max_distance=max_edge_distance
        )
        pairwise_considered = len(pairwise_pairs)
        seen_pair_keys: set = set()
        for node_a_id, node_b_id, d in pairwise_pairs:
            pair_key = tuple(sorted((node_a_id, node_b_id)))
            if pair_key in seen_pair_keys:
                continue
            seen_pair_keys.add(pair_key)
            a = geom_by_id.get(node_a_id)
            b = geom_by_id.get(node_b_id)
            if a is None or b is None or a["node_id"] == b["node_id"]:
                continue
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

        # SAME_TAG: duplicate normalized labels on the same page share identity.
        by_tag: Dict[str, List[dict]] = {}
        for tnode in page_text:
            tag = re.sub(r"\s+", "", str(tnode.get("text") or "").upper())
            if not tag:
                continue
            by_tag.setdefault(tag, []).append(tnode)
        for group in by_tag.values():
            if len(group) < 2:
                continue
            for i, a in enumerate(group):
                for b in group[i + 1 :]:
                    add_edge(
                        a,
                        b,
                        RelationKind.SAME_TAG,
                        distance=_dist(a["center"], b["center"]),
                        weight=1.0,
                    )

        candidate_pairs_possible = len(page_geom) * (len(page_geom) - 1) // 2
        diagnostics.append(
            {
                "page_number": page_number_key,
                "text_node_count": len(page_text),
                "geometry_node_count": len(page_geom),
                "geometry_pairwise_window_cap": geometry_pairwise_window_cap,
                "geometry_pairwise_window_size": geometry_pairwise_window_size,
                "geometry_pairwise_window_triggered": False,
                "spatial_index_enabled": True,
                "same_region_association": True,
                "association_radius_pdf_points": max_edge_distance,
                "leader_resolved_associations": leader_resolved_count,
                "candidate_pairs_considered": pairwise_considered,
                "candidate_pairs_possible": candidate_pairs_possible,
                "candidate_pairs_pruned": max(
                    0, candidate_pairs_possible - pairwise_considered
                ),
            }
        )

    edges_by_page: Dict[int, int] = {}
    for e in edges:
        edges_by_page[int(e.get("page_number") or 0)] = (
            edges_by_page.get(int(e.get("page_number") or 0), 0) + 1
        )
    for entry in diagnostics:
        entry["edge_count"] = edges_by_page.get(entry["page_number"], 0)
    diagnostics.sort(key=lambda entry: entry["page_number"])

    kind_counts: Dict[str, int] = {}
    for n in nodes:
        kind_counts[n["kind"]] = kind_counts.get(n["kind"], 0) + 1
    rel_counts: Dict[str, int] = {}
    for e in edges:
        rel_counts[e["relationship"]] = rel_counts.get(e["relationship"], 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "diagnostics": diagnostics,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes_by_kind": kind_counts,
            "edges_by_relationship": rel_counts,
            "label_count": len(label_nodes),
            "geometry_count": len(geom_nodes),
            "association_radius_pdf_points": max_edge_distance,
        },
    }
