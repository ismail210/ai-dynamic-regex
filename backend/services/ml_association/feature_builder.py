"""Per-(label, geometry) relationship/context feature computation.

Pure geometry math lives here; page-level context that requires the full
node list, graph, or region information (neighbor counts, graph degree,
same-region) is assembled by the caller (``candidate_dataset.py``) and
merged in via ``context``, since that context is naturally page-scoped
rather than pair-scoped.

Reuses ``services.engineering.spatial_index._point_to_bbox_distance``
rather than reimplementing bbox-distance math a fourth time in this
codebase (see docs/geometry_graph_audit/04_graph_audit.md's duplication
findings for the first three).
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence

from services.engineering.spatial_index import _point_to_bbox_distance
from services.ml_association.schemas import RelationshipFeatures


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _bbox_to_bbox_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Nearest-edge distance between two bboxes (0 if they overlap)."""

    ax0, ay0, ax1, ay1 = (float(v) for v in a[:4])
    bx0, by0, bx1, by1 = (float(v) for v in b[:4])
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    return math.hypot(dx, dy)


def _bbox_intersects(a: Sequence[float], b: Sequence[float]) -> bool:
    ax0, ay0, ax1, ay1 = (float(v) for v in a[:4])
    bx0, by0, bx1, by1 = (float(v) for v in b[:4])
    return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)


def _bbox_contains(outer: Sequence[float], inner: Sequence[float]) -> bool:
    ox0, oy0, ox1, oy1 = (float(v) for v in outer[:4])
    ix0, iy0, ix1, iy1 = (float(v) for v in inner[:4])
    return ox0 <= ix0 and oy0 <= iy0 and ox1 >= ix1 and oy1 >= iy1


def _bbox_overlap_ratio(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection area over the smaller bbox's area (0 if disjoint)."""

    ax0, ay0, ax1, ay1 = (float(v) for v in a[:4])
    bx0, by0, bx1, by1 = (float(v) for v in b[:4])
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(ax1 - ax0, 0.0) * max(ay1 - ay0, 0.0)
    area_b = max(bx1 - bx0, 0.0) * max(by1 - by0, 0.0)
    smaller = min(area_a, area_b)
    if smaller <= 0.0:
        return 0.0
    return round(intersection / smaller, 4)


def compute_pairwise_geometry_features(
    label_node: dict, geometry_node: dict
) -> Dict[str, Any]:
    """Pure pairwise geometry math between one label and one geometry node.

    Both nodes must carry ``center`` and ``bbox`` in the shape produced
    by ``graph_builder.build_text_nodes`` / ``build_geometry_nodes``.
    """

    label_center = label_node["center"]
    label_bbox = label_node["bbox"]
    geometry_center = geometry_node["center"]
    geometry_bbox = geometry_node["bbox"]

    centroid_distance = _dist(label_center, geometry_center)
    bbox_distance = _bbox_to_bbox_distance(label_bbox, geometry_bbox)
    # Real endpoint-level distance would need raw line points, which are
    # not carried onto graph nodes (docs/geometry_graph_audit/04_graph_audit.md
    # §13's "raw/inferred mixing" finding). Point-to-bbox distance from the
    # label's center is the same approximation Phase 1's leader-resolution
    # logic uses, and is flagged here for the same reason.
    nearest_endpoint_distance = _point_to_bbox_distance(label_center, geometry_bbox)

    horizontal_offset = float(geometry_center[0]) - float(label_center[0])
    vertical_offset = float(geometry_center[1]) - float(label_center[1])

    label_rotation = float(label_node.get("rotation") or 0.0)
    geometry_orientation = float(geometry_node.get("orientation") or 0.0)
    relative_orientation = (geometry_orientation - label_rotation) % 360.0

    return {
        "centroid_distance": round(centroid_distance, 3),
        "bbox_distance": round(bbox_distance, 3),
        "nearest_endpoint_distance": round(nearest_endpoint_distance, 3),
        "horizontal_offset": round(horizontal_offset, 3),
        "vertical_offset": round(vertical_offset, 3),
        "relative_orientation": round(relative_orientation, 3),
        "bbox_intersects": _bbox_intersects(label_bbox, geometry_bbox),
        "bbox_contains": _bbox_contains(geometry_bbox, label_bbox)
        or _bbox_contains(label_bbox, geometry_bbox),
        "bbox_overlap_ratio": _bbox_overlap_ratio(label_bbox, geometry_bbox),
    }


def normalize_distance(
    raw_distance: float,
    *,
    page_diagonal: Optional[float] = None,
    text_height: Optional[float] = None,
    scale_value: Optional[float] = None,
) -> Dict[str, Any]:
    """Scale-aware distance normalization, where the inputs exist.

    Every ``*_available`` flag is explicit: absence of a page diagonal,
    text height, or drawing scale means the corresponding normalized
    field stays ``None``, never a misleading ``0.0``.
    """

    result: Dict[str, Any] = {
        "distance_normalized_by_page": None,
        "distance_normalized_by_text_height": None,
        "distance_normalized_by_scale": None,
        "distance_scale_available": False,
    }
    if page_diagonal and page_diagonal > 0:
        result["distance_normalized_by_page"] = round(raw_distance / page_diagonal, 6)
    if text_height and text_height > 0:
        result["distance_normalized_by_text_height"] = round(
            raw_distance / text_height, 4
        )
    if scale_value and scale_value > 0:
        result["distance_normalized_by_scale"] = round(raw_distance * scale_value, 4)
        result["distance_scale_available"] = True
    return result


def build_relationship_features(
    label_node: dict,
    geometry_node: Optional[dict],
    *,
    page_width: Optional[float] = None,
    page_height: Optional[float] = None,
    text_height: Optional[float] = None,
    scale_value: Optional[float] = None,
    context: Optional[Dict[str, Any]] = None,
) -> RelationshipFeatures:
    """Assemble the full ``RelationshipFeatures`` model for one candidate row.

    ``geometry_node=None`` builds the (mostly-empty) features for the
    synthetic no-valid-target placeholder row. ``context`` carries
    page-level facts assembled by ``candidate_dataset.py`` (graph degree,
    neighbor counts, region membership, leader evidence, extraction
    quality flags, candidate-generation provenance) — anything that is
    not a pure pairwise computation between exactly these two nodes.
    """

    context = context or {}

    if geometry_node is None:
        return RelationshipFeatures(
            same_region=context.get("same_region"),
            region_available=bool(context.get("region_available", False)),
            extraction_quality_flags=list(context.get("extraction_quality_flags", [])),
            candidate_generation_sources=["no_match_placeholder"],
        )

    pairwise = compute_pairwise_geometry_features(label_node, geometry_node)

    page_diagonal = None
    if page_width and page_height:
        page_diagonal = math.hypot(float(page_width), float(page_height))

    normalized = normalize_distance(
        pairwise["centroid_distance"],
        page_diagonal=page_diagonal,
        text_height=text_height,
        scale_value=scale_value,
    )

    return RelationshipFeatures(
        centroid_distance=pairwise["centroid_distance"],
        bbox_distance=pairwise["bbox_distance"],
        nearest_endpoint_distance=pairwise["nearest_endpoint_distance"],
        distance_normalized_by_page=normalized["distance_normalized_by_page"],
        distance_normalized_by_text_height=normalized["distance_normalized_by_text_height"],
        distance_normalized_by_scale=normalized["distance_normalized_by_scale"],
        distance_scale_available=normalized["distance_scale_available"],
        horizontal_offset=pairwise["horizontal_offset"],
        vertical_offset=pairwise["vertical_offset"],
        relative_orientation=pairwise["relative_orientation"],
        bbox_intersects=pairwise["bbox_intersects"],
        bbox_contains=pairwise["bbox_contains"],
        bbox_overlap_ratio=pairwise["bbox_overlap_ratio"],
        same_region=context.get("same_region"),
        region_available=bool(context.get("region_available", False)),
        local_line_density=context.get("local_line_density"),
        endpoint_degree=context.get("endpoint_degree"),
        intersection_count=context.get("intersection_count"),
        parallel_neighbor_count=context.get("parallel_neighbor_count"),
        perpendicular_neighbor_count=context.get("perpendicular_neighbor_count"),
        nearby_steel_label_count=context.get("nearby_steel_label_count"),
        leader_support_evidence=bool(context.get("leader_support_evidence", False)),
        leader_path_ids=list(context.get("leader_path_ids", [])),
        graph_degree=context.get("graph_degree"),
        graph_relation_summary=dict(context.get("graph_relation_summary", {})),
        extraction_quality_flags=list(context.get("extraction_quality_flags", [])),
        candidate_generation_sources=list(context.get("candidate_generation_sources", [])),
    )
