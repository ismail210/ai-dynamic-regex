"""Phase C -- Structural Graph V2 augmentation (shadow only).

The production structural graph is built from real text + geometry nodes and
then frozen; synthetic members created afterwards have no graph topology
(this is the defect the ML audit identified: review-pile members are 100%
graph-degree-0). This module adds physical member candidates to an EXISTING
graph dict as first-class nodes, with only semantically meaningful edges --
never a fully-connected proximity graph. It is called ONLY from
``member_reconstruction`` in the shadow path and returns a NEW dict; it does
not mutate the production graph or its ``build_structural_graph`` output.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

_PARALLEL_ANGLE_TOL = 8.0
_SAME_BAY_MAX_PERP = 420.0      # pdf points; ~one bay of typical plan spacing
_SAME_BAY_MIN_OVERLAP = 0.45    # fraction of the shorter beam that must overlap
_LABEL_MEMBER_MAX_DIST = 90.0   # a label centre this close to a member axis
# parallel edges are only useful for adjacent framing -- cap the reach so a
# framing plan does not become a fully-connected parallel mesh
_PARALLEL_MAX_PERP = 650.0


def _mid(pt_a: Sequence[float], pt_b: Sequence[float]) -> Tuple[float, float]:
    return ((pt_a[0] + pt_b[0]) / 2.0, (pt_a[1] + pt_b[1]) / 2.0)


def _point_to_segment(p: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    px, py = float(p[0]), float(p[1])
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _angle_close(o1: float, o2: float, tol: float) -> bool:
    d = abs((o1 % 180.0) - (o2 % 180.0))
    return min(d, 180.0 - d) <= tol


def _axis_overlap_fraction(m1: Dict[str, Any], m2: Dict[str, Any]) -> float:
    """Overlap of the two axes projected onto the shared dominant direction."""
    horiz = abs((m1["orientation_deg"] % 180.0) - 90.0) > 45.0
    idx = 0 if horiz else 1
    a1, b1 = sorted((m1["axis_start"][idx], m1["axis_end"][idx]))
    a2, b2 = sorted((m2["axis_start"][idx], m2["axis_end"][idx]))
    inter = max(0.0, min(b1, b2) - max(a1, a2))
    shorter = min(b1 - a1, b2 - a2) or 1.0
    return inter / shorter


def _perp_distance(m1: Dict[str, Any], m2: Dict[str, Any]) -> float:
    return _point_to_segment(_mid(m1["axis_start"], m1["axis_end"]),
                             m2["axis_start"], m2["axis_end"])


def augment_graph_with_members(
    graph: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    *,
    label_nodes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return a shadow copy of ``graph`` with member candidate nodes and
    ``label_to_member`` / ``member_parallel_to`` / ``member_same_bay`` /
    ``member_to_support`` / ``member_to_grid`` edges added."""

    nodes: List[Dict[str, Any]] = list(graph.get("nodes") or [])
    edges: List[Dict[str, Any]] = list(graph.get("edges") or [])
    existing_by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        existing_by_page[int(node.get("page_number") or 0)].append(node)

    member_nodes: List[Dict[str, Any]] = []
    for cand in candidates:
        node_id = f"mem_{cand['member_candidate_id']}"
        cand["graph_node_id"] = node_id
        node = {
            "node_id": node_id,
            "kind": "physical_member_candidate",
            "base_kind": "member_candidate",
            "page_number": cand["page"],
            "center": list(_mid(cand["axis_start"], cand["axis_end"])),
            "bbox": cand["bbox"],
            "source_id": cand["member_candidate_id"],
            "features": {
                "length": float(cand["length_pdf"]),
                "orientation": float(cand["orientation_deg"]),
                "existence_confidence": float(cand["existence_confidence"]),
            },
            "shadow": True,
        }
        nodes.append(node)
        member_nodes.append(node)

    def add_edge(src: str, dst: str, rel: str, conf: float, reason: str, dist: float = 0.0) -> None:
        edges.append({
            "source": src, "target": dst, "relationship": rel,
            "confidence": round(conf, 3), "reason": reason,
            "distance": round(dist, 2), "shadow": True,
        })

    # member <-> member: parallel + same-bay, per page
    by_page_members: Dict[int, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = defaultdict(list)
    for cand, node in zip(candidates, member_nodes):
        by_page_members[cand["page"]].append((cand, node))

    for page, items in by_page_members.items():
        for i in range(len(items)):
            c1, n1 = items[i]
            for j in range(i + 1, len(items)):
                c2, n2 = items[j]
                if not _angle_close(c1["orientation_deg"], c2["orientation_deg"], _PARALLEL_ANGLE_TOL):
                    continue
                perp = _perp_distance(c1, c2)
                if perp > _PARALLEL_MAX_PERP:
                    continue
                overlap = _axis_overlap_fraction(c1, c2)
                if overlap < 0.15:
                    continue
                add_edge(n1["node_id"], n2["node_id"], "member_parallel_to", 0.6,
                         "same_orientation", perp)
                if perp <= _SAME_BAY_MAX_PERP and overlap >= _SAME_BAY_MIN_OVERLAP:
                    add_edge(n1["node_id"], n2["node_id"], "member_same_bay",
                             0.55 + 0.2 * overlap, "parallel_overlapping_adjacent", perp)

    # label -> member: a catalog-valid section label node whose centre lands on
    # exactly one member axis (clear separation from the runner-up).
    for label in label_nodes or []:
        centre = label.get("center") or label.get("centroid")
        page = int(label.get("page_number") or label.get("page") or 0)
        if not centre or page not in by_page_members:
            continue
        ranked: List[Tuple[float, Dict[str, Any]]] = []
        for cand, node in by_page_members[page]:
            d = _point_to_segment(centre, cand["axis_start"], cand["axis_end"])
            ranked.append((d, node))
        ranked.sort(key=lambda t: t[0])
        if not ranked or ranked[0][0] > _LABEL_MEMBER_MAX_DIST:
            continue
        nearest_d, nearest_node = ranked[0]
        margin = (ranked[1][0] - nearest_d) if len(ranked) > 1 else 999.0
        clear = margin >= 0.5 * _LABEL_MEMBER_MAX_DIST
        add_edge(
            str(label.get("node_id") or label.get("source_id")),
            nearest_node["node_id"], "label_to_member",
            0.8 if clear else 0.45,
            "unambiguous_adjacency" if clear else "nearest_only", nearest_d,
        )

    # member -> support / grid: reuse existing column/grid nodes near an endpoint
    for page, items in by_page_members.items():
        page_nodes = existing_by_page.get(page, [])
        supports = [n for n in page_nodes if n.get("kind") in ("column", "connection", "steel_section")]
        grids = [n for n in page_nodes if n.get("kind") in ("grid", "dimension") or "grid" in str(n.get("base_kind") or "")]
        for cand, node in items:
            for end_key, end_pt in (("support_start_id", cand["axis_start"]),
                                    ("support_end_id", cand["axis_end"])):
                best = None
                best_d = 60.0
                for s in supports:
                    c = s.get("center")
                    if not c:
                        continue
                    d = math.hypot(c[0] - end_pt[0], c[1] - end_pt[1])
                    if d < best_d:
                        best, best_d = s, d
                if best is not None:
                    cand[end_key] = best["node_id"]
                    add_edge(node["node_id"], best["node_id"], "member_to_support",
                             0.6, "endpoint_near_support", best_d)
            for g in grids[:80]:
                c = g.get("center")
                if not c:
                    continue
                if _point_to_segment(c, cand["axis_start"], cand["axis_end"]) < 8.0:
                    add_edge(node["node_id"], g["node_id"], "member_to_grid",
                             0.5, "member_crosses_grid", 0.0)
                    break

    new_graph = dict(graph)
    new_graph["nodes"] = nodes
    new_graph["edges"] = edges
    new_graph["member_v2"] = {
        "member_nodes": len(member_nodes),
        "member_edges": sum(1 for e in edges if e.get("shadow")),
    }
    return new_graph


def member_connectivity(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Graph-quality metrics for the member candidate nodes (Phase C section 56)."""

    member_ids = {
        n["node_id"] for n in graph.get("nodes") or []
        if n.get("kind") == "physical_member_candidate"
    }
    if not member_ids:
        return {"member_nodes": 0}
    degree: Dict[str, int] = defaultdict(int)
    by_rel: Dict[str, int] = defaultdict(int)
    for edge in graph.get("edges") or []:
        s, t, rel = edge.get("source"), edge.get("target"), edge.get("relationship")
        if s in member_ids or t in member_ids:
            by_rel[rel] += 1
        if s in member_ids:
            degree[s] += 1
        if t in member_ids:
            degree[t] += 1
    connected = sum(1 for m in member_ids if degree.get(m, 0) >= 1)
    return {
        "member_nodes": len(member_ids),
        "connected_members": connected,
        "isolated_members": len(member_ids) - connected,
        "connected_fraction": round(connected / len(member_ids), 3),
        "avg_degree": round(sum(degree.values()) / len(member_ids), 2),
        "edges_by_relationship": dict(by_rel),
    }
