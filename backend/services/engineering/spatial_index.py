"""Spatially-complete candidate generator used by production graph_builder.

``graph_builder.build_graph`` uses this module for leader-aware label→geometry
association (P1.2/P1.7) and spatially-complete pairwise geometry relations.
See docs/geometry_graph_audit/08_prioritized_roadmap.md.

``graph_builder.py``'s pairwise relationship loop takes only
``page_geom[:60]`` and compares each item to the next 11 in *PDF
extraction order* -- not spatial order. Two geometrically adjacent
objects that happen to be far apart in extraction order are silently
never compared. This module replaces that windowing with a real
``shapely.strtree.STRtree`` spatial index, so candidate generation is
independent of extraction order by construction.

This module deliberately reuses ``graph_builder.build_text_nodes`` /
``build_geometry_nodes`` for node construction, so the node *shape* here
is identical to the production graph's -- only the candidate-search
mechanism differs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shapely.geometry import box as shapely_box
from shapely.strtree import STRtree

from services.engineering.detail_regions import same_region
from services.engineering.graph_builder import build_geometry_nodes, build_text_nodes

DEFAULT_MAX_DISTANCE = 160.0
LEGACY_WINDOW_CAP = 60
LEGACY_WINDOW_SIZE = 12


@dataclass
class SpatialCandidate:
    """One label->geometry (or geometry->geometry) candidate found via the
    spatial index, with provenance describing *why* it was proposed."""

    node_id: str
    distance: float
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "distance": round(self.distance, 3),
            "sources": list(self.sources),
        }


def _node_box(node: dict):
    bbox = node.get("bbox") or node.get("center")
    if bbox is None:
        return None
    if len(bbox) == 2:
        x, y = float(bbox[0]), float(bbox[1])
        return shapely_box(x, y, x, y)
    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    return shapely_box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def build_page_index(nodes: Sequence[dict]) -> Tuple[Optional[STRtree], List[dict]]:
    """Build an STRtree over ``nodes``' bounding boxes.

    Returns ``(tree, ordered_nodes)`` where ``ordered_nodes[i]``
    corresponds to the geometry at index ``i`` in the tree -- this is how
    shapely's ``STRtree.query`` reports matches (integer indices into the
    array passed at construction), so callers must always resolve
    matches through the returned ``ordered_nodes`` list, not ``nodes``
    itself if it was reordered.
    """

    ordered = [n for n in nodes if n.get("center") is not None]
    if not ordered:
        return None, []
    boxes = [_node_box(n) for n in ordered]
    return STRtree(boxes), ordered


def _point_to_bbox_distance(point: Sequence[float], bbox: Sequence[float]) -> float:
    """Distance from ``point`` to the nearest point on ``bbox`` (0 if
    ``point`` is inside/on the box). Used so a long, thin shape (e.g. a
    leader whose near end touches a label but whose centroid is far
    away) is still found as "near" -- centroid-to-centroid distance
    would otherwise miss it entirely.
    """

    px, py = float(point[0]), float(point[1])
    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def query_within_radius(
    tree: STRtree,
    ordered_nodes: Sequence[dict],
    center: Sequence[float],
    *,
    max_distance: float,
    use_bbox_distance: bool = False,
) -> List[Tuple[int, float]]:
    """All ``(index, distance)`` pairs in ``ordered_nodes`` within
    ``max_distance`` of ``center``, found via the spatial index rather
    than a linear scan or a windowed loop.

    ``use_bbox_distance=False`` (default) measures centroid-to-centroid
    distance, matching ``graph_builder.build_graph``'s metric exactly --
    this keeps ``spatially_complete_geometry_pairs`` a fair, apples-to-
    apples comparison against ``legacy_windowed_pairs`` for the coverage
    report. ``use_bbox_distance=True`` measures point-to-bbox distance
    instead, which ``nearest_geometry_candidates`` uses for label
    searches so elongated shapes like leaders are found by their nearest
    edge, not their potentially-distant centroid.
    """

    cx, cy = float(center[0]), float(center[1])
    query_box = shapely_box(
        cx - max_distance, cy - max_distance, cx + max_distance, cy + max_distance
    )
    matches: List[Tuple[int, float]] = []
    for raw_index in tree.query(query_box):
        index = int(raw_index)
        node = ordered_nodes[index]
        if use_bbox_distance and node.get("bbox"):
            d = _point_to_bbox_distance(center, node["bbox"])
        else:
            d = _dist(center, node["center"])
        if d <= max_distance:
            matches.append((index, d))
    matches.sort(key=lambda item: item[1])
    return matches


def _leader_far_endpoint(label_center: Sequence[float], bbox: Sequence[float]) -> Tuple[float, float]:
    """Approximate a leader's far (non-label) endpoint as the bbox corner
    farthest from the label.

    This is a coarse approximation: it uses the leader's bounding box,
    not its true polyline points (which are not carried onto graph nodes
    -- see ``graph_builder.build_geometry_nodes``). A leader that is not
    a simple straight 2-point segment (e.g. a dog-legged/multi-segment
    leader) would not be perfectly represented by its far bbox corner.
    Flagged as a known limitation rather than silently treated as exact;
    full point-level leader resolution is future work
    (docs/geometry_graph_audit/08_prioritized_roadmap.md P1.7).
    """

    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    corners = [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]
    return max(corners, key=lambda corner: _dist(label_center, corner))


def _is_area_shaped(bbox: Sequence[float], max_distance: float, *, multiplier: float = 4.0) -> bool:
    """True when ``bbox`` is large in BOTH dimensions relative to
    ``max_distance`` -- i.e. it describes a filled region (title-block
    border, large hatch fill), not a linear member or leader.
    """

    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    width = abs(x1 - x0)
    height = abs(y1 - y0)
    threshold = max_distance * multiplier
    return width > threshold and height > threshold


def _is_oversized_sheet_furniture(
    node: dict, max_distance: float
) -> bool:
    """Page-sized or long filled strips that Phase 1 associated as members.

    ``_is_area_shaped`` requires BOTH sides > 4 * radius, so a 3327 x 200
    sheet rectangle still wins at distance 0. Rectangles/paths/symbols
    that are fat *and* longer than 8 * radius are not members or plates.
    """

    bbox = node.get("bbox")
    if not bbox or len(bbox) < 4:
        return False
    if _is_area_shaped(bbox, max_distance):
        return True
    kind = str(node.get("geometry_kind") or "").lower()
    if kind not in {"rectangle", "path", "symbol"}:
        return False
    width = abs(float(bbox[2]) - float(bbox[0]))
    height = abs(float(bbox[3]) - float(bbox[1]))
    return min(width, height) > 24.0 and max(width, height) > 8.0 * max_distance


def _is_structural_member_kind(node: dict) -> bool:
    kind = str(node.get("geometry_kind") or "").lower()
    return kind in {"line", "polyline", "path", "arc", "curve"}


def nearest_geometry_candidates(
    label_node: dict,
    tree: STRtree,
    ordered_geometry_nodes: Sequence[dict],
    *,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    top_k: int = 5,
) -> List[SpatialCandidate]:
    """Spatially-complete top-K geometry candidates for one label node.

    Unlike ``graph_builder.build_graph``'s ``nearest_geometry`` edge
    (which keeps only the single closest match), this returns up to
    ``top_k`` alternatives with distances, matching the report's
    recommendation to retain alternative hypotheses at the candidate-
    generation layer instead of collapsing to one choice immediately.

    Also resolves *through* leader candidates: if a nearby candidate is
    leader-kind geometry, this additionally queries near the leader's
    estimated far endpoint for a real target member, and surfaces that
    target (not the leader itself) as a higher-priority candidate. The
    production graph (``graph_builder.build_graph``) has no equivalent
    logic -- a leader competes as an ordinary node on raw centroid
    distance, so a label can end up "nearest" to the leader stroke
    itself instead of the member it points at. See
    docs/geometry_graph_audit/04_graph_audit.md §4 worked example.
    """

    matches = query_within_radius(
        tree,
        ordered_geometry_nodes,
        label_node["center"],
        max_distance=max_distance,
        use_bbox_distance=True,
    )

    by_node: Dict[str, SpatialCandidate] = {}

    def add(node_id: str, distance: float, source: str) -> None:
        existing = by_node.get(node_id)
        if existing is None:
            by_node[node_id] = SpatialCandidate(
                node_id=node_id, distance=distance, sources=[source]
            )
        else:
            existing.sources.append(source)
            existing.distance = min(existing.distance, distance)

    for index, distance in matches:
        node = ordered_geometry_nodes[index]
        if not same_region(label_node.get("region_id"), node.get("region_id")):
            continue
        kind = str(node.get("geometry_kind") or "").lower()
        if kind == "leader" and node.get("bbox"):
            far_point = _leader_far_endpoint(label_node["center"], node["bbox"])
            for r_index, r_distance in query_within_radius(
                tree,
                ordered_geometry_nodes,
                far_point,
                max_distance=max_distance,
                use_bbox_distance=True,
            ):
                target = ordered_geometry_nodes[r_index]
                if target["node_id"] == node["node_id"]:
                    continue  # a leader is not its own target
                if not same_region(label_node.get("region_id"), target.get("region_id")):
                    continue
                target_kind = str(target.get("geometry_kind") or "").lower()
                if target_kind in {"leader", "dimension"}:
                    continue
                if _is_oversized_sheet_furniture(target, max_distance):
                    continue
                add(target["node_id"], r_distance, "leader_endpoint_resolved")
            continue
        if kind == "dimension":
            continue
        if _is_oversized_sheet_furniture(node, max_distance):
            continue
        add(node["node_id"], distance, "direct_distance")

    kind_by_id = {
        str(node["node_id"]): node for node in ordered_geometry_nodes
    }
    ranked = sorted(
        by_node.values(),
        key=lambda c: (
            0 if "leader_endpoint_resolved" in c.sources else 1,
            0 if _is_structural_member_kind(kind_by_id.get(c.node_id) or {}) else 1,
            c.distance,
        ),
    )
    return ranked[:top_k]


def spatially_complete_geometry_pairs(
    geometry_nodes: Sequence[dict], *, max_distance: float = DEFAULT_MAX_DISTANCE
) -> List[Tuple[str, str, float]]:
    """Every unordered pair of geometry nodes within ``max_distance`` of
    each other, found via the spatial index -- independent of the order
    ``geometry_nodes`` happens to be in.

    This is the direct spatially-complete counterpart to
    ``graph_builder.build_graph``'s ``page_geom[:60]`` /
    ``candidates[i+1:i+12]`` windowed loop (see ``legacy_windowed_pairs``
    below for that loop reproduced verbatim, for comparison).
    """

    tree, ordered = build_page_index(geometry_nodes)
    if tree is None:
        return []
    seen: set = set()
    pairs: List[Tuple[str, str, float]] = []
    for i, node in enumerate(ordered):
        for j, distance in query_within_radius(
            tree, ordered, node["center"], max_distance=max_distance
        ):
            if j == i:
                continue
            key = tuple(sorted((node["node_id"], ordered[j]["node_id"])))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((key[0], key[1], distance))
    return pairs


def legacy_windowed_pairs(
    geometry_nodes: Sequence[dict],
    *,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    window_cap: int = LEGACY_WINDOW_CAP,
    window_size: int = LEGACY_WINDOW_SIZE,
) -> List[Tuple[str, str, float]]:
    """Reproduces ``graph_builder.build_graph``'s pairwise loop exactly
    (``page_geom[:window_cap]``, compare each item to the next
    ``window_size`` in list order), for direct A/B comparison against
    ``spatially_complete_geometry_pairs`` on the same input.
    """

    candidates = list(geometry_nodes[:window_cap])
    seen: set = set()
    pairs: List[Tuple[str, str, float]] = []
    for i, a in enumerate(candidates):
        for b in candidates[i + 1 : i + 1 + window_size]:
            if a["node_id"] == b["node_id"]:
                continue
            d = _dist(a["center"], b["center"])
            if d > max_distance:
                continue
            key = tuple(sorted((a["node_id"], b["node_id"])))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((key[0], key[1], d))
    return pairs


def coverage_report(
    geometry_nodes: Sequence[dict],
    *,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    window_cap: int = LEGACY_WINDOW_CAP,
    window_size: int = LEGACY_WINDOW_SIZE,
) -> Dict[str, Any]:
    """Measures how much spatial-relationship recall the production
    windowed loop actually has on a given page's geometry nodes,
    relative to the spatially-complete STRtree result.

    This operationalizes the deep-research report's synthetic
    experiment (10.8%-11.4% recall for the 60/12 window on randomized
    extraction order) directly against this repository's real node
    construction and real production windowing logic, rather than a
    standalone simulation script.
    """

    complete_pairs = spatially_complete_geometry_pairs(
        geometry_nodes, max_distance=max_distance
    )
    windowed = legacy_windowed_pairs(
        geometry_nodes,
        max_distance=max_distance,
        window_cap=window_cap,
        window_size=window_size,
    )
    complete_keys = {(a, b) for a, b, _ in complete_pairs}
    windowed_keys = {(a, b) for a, b, _ in windowed}
    found = complete_keys & windowed_keys
    recall = (len(found) / len(complete_keys)) if complete_keys else 1.0
    return {
        "geometry_node_count": len(geometry_nodes),
        "max_distance": max_distance,
        "window_cap": window_cap,
        "window_size": window_size,
        "spatially_complete_pair_count": len(complete_keys),
        "windowed_pair_count": len(windowed_keys),
        "pairs_found_by_window": len(found),
        "window_recall": round(recall, 4),
    }


def generate_spatial_candidates(
    document_structure: dict,
    geometry: dict,
    *,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    top_k: int = 5,
) -> Dict[str, Any]:
    """Top-level, non-production entry point: spatially-complete
    label -> geometry candidate generation for every page, plus a
    per-page coverage report comparing this result against the current
    production windowed loop.

    Returns::

        {
          "pages": {
             page_number: {
                "label_candidates": {label_node_id: [SpatialCandidate.to_dict(), ...], ...},
                "coverage": coverage_report(...),
             },
             ...
          }
        }

    This function does not read from or write to any production
    artifact path, and nothing in the live pipeline calls it.
    """

    text_nodes = build_text_nodes(document_structure)
    geometry_nodes = build_geometry_nodes(geometry)

    by_page_text: Dict[int, List[dict]] = {}
    by_page_geometry: Dict[int, List[dict]] = {}
    for node in text_nodes:
        by_page_text.setdefault(int(node.get("page_number") or 0), []).append(node)
    for node in geometry_nodes:
        by_page_geometry.setdefault(int(node.get("page_number") or 0), []).append(node)

    pages: Dict[int, dict] = {}
    all_page_numbers = sorted(set(by_page_text) | set(by_page_geometry))
    for page_number in all_page_numbers:
        page_text = by_page_text.get(page_number, [])
        page_geometry = by_page_geometry.get(page_number, [])

        label_candidates: Dict[str, List[dict]] = {}
        if page_geometry:
            tree, ordered = build_page_index(page_geometry)
            for label in page_text:
                if tree is None:
                    label_candidates[label["node_id"]] = []
                    continue
                candidates = nearest_geometry_candidates(
                    label,
                    tree,
                    ordered,
                    max_distance=max_distance,
                    top_k=top_k,
                )
                label_candidates[label["node_id"]] = [c.to_dict() for c in candidates]
        else:
            for label in page_text:
                label_candidates[label["node_id"]] = []

        pages[page_number] = {
            "label_candidates": label_candidates,
            "coverage": coverage_report(page_geometry, max_distance=max_distance),
        }

    return {"pages": pages}
