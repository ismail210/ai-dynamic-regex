"""Deterministic PDF geometry retrieval features (R&D only).

Reuses geometry objects already produced by production extract_geometry /
artifact geometry.json. Does not invent semantic member roles.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _center(bbox: Sequence[float]) -> Tuple[float, float]:
    return (
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    )


def _bbox_area(bbox: Sequence[float]) -> float:
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(
        0.0, float(bbox[3]) - float(bbox[1])
    )


def _intersection_area(a: Sequence[float], b: Sequence[float]) -> float:
    x0 = max(float(a[0]), float(b[0]))
    y0 = max(float(a[1]), float(b[1]))
    x1 = min(float(a[2]), float(b[2]))
    y1 = min(float(a[3]), float(b[3]))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    inter = _intersection_area(a, b)
    if inter <= 0:
        return 0.0
    union = _bbox_area(a) + _bbox_area(b) - inter
    return inter / union if union > 0 else 0.0


def _point_to_bbox_distance(px: float, py: float, bbox: Sequence[float]) -> float:
    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    dx = 0.0 if x0 <= px <= x1 else min(abs(px - x0), abs(px - x1))
    dy = 0.0 if y0 <= py <= y1 else min(abs(py - y0), abs(py - y1))
    return math.hypot(dx, dy)


def _angle_delta_deg(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    d = abs(float(a) - float(b)) % 180.0
    return min(d, 180.0 - d)


def _centerline_from_obj(obj: Dict[str, Any], bbox: Sequence[float]) -> List[List[float]]:
    points = obj.get("points") or obj.get("centerline") or []
    line: List[List[float]] = []
    for pt in points:
        if pt is not None and len(pt) >= 2:
            line.append([float(pt[0]), float(pt[1])])
            if len(line) >= 16:
                break
    if len(line) >= 2:
        return [line[0], line[-1]] if len(line) > 2 else line
    return [[float(bbox[0]), float(bbox[1])], [float(bbox[2]), float(bbox[3])]]


def geometry_candidate_record(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a production geometry object into the R&D retrieval contract."""
    bbox = obj.get("bbox") or [0, 0, 0, 0]
    center = obj.get("center") or _center(bbox)
    kind = str(obj.get("kind") or obj.get("geometry_type") or "unknown").lower()
    # Never promote raw PDF kinds to beam/column/brace here.
    role = "unknown"
    if kind == "leader":
        role = "leader"
    elif kind == "dimension":
        role = "dimension"
    return {
        "geometry_id": obj.get("geometry_id") or obj.get("object_id"),
        "page_number": int(obj.get("page_number") or obj.get("page") or 0),
        "geometry_kind": kind,
        "geometry_role": role,
        "bbox": [float(v) for v in bbox[:4]],
        "center": [float(center[0]), float(center[1])],
        "centerline": _centerline_from_obj(obj, bbox),
        "orientation": obj.get("orientation") if obj.get("orientation") is not None else obj.get("angle"),
        "length": obj.get("length"),
        "source_primitive": {
            "layer": obj.get("layer") or obj.get("drawing_layer"),
            "region_id": obj.get("region_id"),
            "source_format": obj.get("source_format") or "pdf_drawings",
        },
        "evidence_status": "retrieved",
    }


def _point_to_segment_distance(
    px: float, py: float, a: Sequence[float], b: Sequence[float]
) -> float:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _leader_far_endpoint(label_center: Sequence[float], bbox: Sequence[float]) -> Tuple[float, float]:
    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    corners = [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]
    return max(corners, key=lambda c: math.hypot(c[0] - label_center[0], c[1] - label_center[1]))


def _is_member_kind(kind: str) -> bool:
    return kind in {"line", "polyline", "path", "arc", "curve"}


def score_label_to_geometry(
    label_bbox: Sequence[float],
    label_page: int,
    label_orientation: Optional[float],
    geo: Dict[str, Any],
    *,
    region_id: Optional[str] = None,
    require_same_region: bool = False,
) -> Optional[Dict[str, Any]]:
    """Compute retrieval features between one label and one geometry object."""
    if int(geo.get("page_number") or geo.get("page") or 0) != int(label_page):
        return None
    geo_region = (geo.get("source_primitive") or {}).get("region_id") or geo.get("region_id")
    if require_same_region and region_id and geo_region and region_id != geo_region:
        return None

    gb = geo["bbox"]
    lx, ly = _center(label_bbox)
    gx, gy = geo["center"][0], geo["center"][1]
    center_dist = math.hypot(lx - gx, ly - gy)
    bbox_dist = _point_to_bbox_distance(lx, ly, gb)
    overlap = _intersection_area(label_bbox, gb)
    iou = _iou(label_bbox, gb)
    orient_delta = _angle_delta_deg(label_orientation, geo.get("orientation"))
    centerline = geo.get("centerline") or []
    perp = None
    if len(centerline) >= 2:
        perp = _point_to_segment_distance(lx, ly, centerline[0], centerline[-1])

    return {
        "geometry_id": geo["geometry_id"],
        "page_number": geo["page_number"],
        "geometry_kind": geo["geometry_kind"],
        "geometry_role": geo["geometry_role"],
        "geometry_bbox": gb,
        "centerline": centerline,
        "center_distance": round(center_dist, 2),
        "bbox_distance": round(bbox_dist, 2),
        "perpendicular_distance": None if perp is None else round(perp, 2),
        "overlap_area": round(overlap, 2),
        "iou": round(iou, 4),
        "orientation_delta_deg": None if orient_delta is None else round(orient_delta, 2),
        "same_region": (not region_id or not geo_region or region_id == geo_region),
        "geo_region_id": geo_region,
        "leader_path_ids": [],
        "candidate_generation_sources": ["direct_distance"],
        "evidence_status": "candidate",
    }


def retrieve_candidates_for_label(
    label: Dict[str, Any],
    geometry_records: Sequence[Dict[str, Any]],
    *,
    top_k: int = 5,
    max_distance: float = 120.0,
    require_same_region: bool = False,
    exclude_leader_as_target: bool = False,
    resolve_leaders: bool = False,
) -> List[Dict[str, Any]]:
    """Return top-K geometry candidates by bbox_distance (then center_distance).

    When ``exclude_leader_as_target`` is True, leader/dimension strokes are
    never the associated member. When ``resolve_leaders`` is True, nearby
    leaders hop to a far-bbox-corner query (same idea as production
    ``spatial_index``, isolated here).
    """
    bbox = label.get("bbox")
    page = int(label.get("page") or label.get("page_number") or 0)
    if not bbox or len(bbox) < 4 or not page:
        return []
    region_id = label.get("region_id")
    orientation = label.get("rotation")
    if orientation is None:
        orientation = label.get("orientation")
    lx, ly = _center(bbox)

    by_id: Dict[str, Dict[str, Any]] = {}
    nearby_leaders: List[Tuple[float, Dict[str, Any]]] = []
    members = [g for g in geometry_records if _is_member_kind(str(g.get("geometry_kind") or ""))]

    def add(feat: Dict[str, Any], source: str, leader_id: Optional[str] = None) -> None:
        gid = feat.get("geometry_id")
        if not gid:
            return
        existing = by_id.get(gid)
        if existing is None:
            feat = dict(feat)
            feat["candidate_generation_sources"] = [source]
            feat["leader_path_ids"] = [leader_id] if leader_id else []
            by_id[gid] = feat
            return
        if source not in existing["candidate_generation_sources"]:
            existing["candidate_generation_sources"].append(source)
        if leader_id and leader_id not in existing["leader_path_ids"]:
            existing["leader_path_ids"].append(leader_id)
        existing["bbox_distance"] = min(existing["bbox_distance"], feat["bbox_distance"])
        existing["center_distance"] = min(existing["center_distance"], feat["center_distance"])

    for geo in geometry_records:
        kind = str(geo.get("geometry_kind") or "").lower()
        if kind in {"dimension", "symbol"}:
            continue
        feat = score_label_to_geometry(
            bbox,
            page,
            orientation,
            geo,
            region_id=region_id,
            require_same_region=require_same_region,
        )
        if feat is None:
            continue
        if feat["bbox_distance"] > max_distance and feat["overlap_area"] <= 0:
            continue
        if kind == "leader":
            nearby_leaders.append((feat["bbox_distance"], geo))
            if exclude_leader_as_target:
                continue
        add(feat, "direct_distance")

    if resolve_leaders:
        nearby_leaders.sort(key=lambda item: item[0])
        for _, leader in nearby_leaders[:3]:
            far = _leader_far_endpoint((lx, ly), leader["bbox"])
            for target in members:
                if target.get("geometry_id") == leader.get("geometry_id"):
                    continue
                gx, gy = target["center"][0], target["center"][1]
                if math.hypot(gx - far[0], gy - far[1]) > max_distance + 40:
                    continue
                tfeat = score_label_to_geometry(
                    [far[0] - 1, far[1] - 1, far[0] + 1, far[1] + 1],
                    page,
                    orientation,
                    target,
                    region_id=region_id,
                    require_same_region=require_same_region,
                )
                if tfeat is None or tfeat["bbox_distance"] > max_distance:
                    continue
                add(tfeat, "leader_endpoint_resolved", leader_id=str(leader.get("geometry_id")))

    scored = list(by_id.values())
    scored.sort(
        key=lambda r: (
            0 if "leader_endpoint_resolved" in (r.get("candidate_generation_sources") or []) else 1,
            0 if _is_member_kind(str(r.get("geometry_kind") or "")) else 1,
            r["bbox_distance"],
            r["center_distance"],
            -r["iou"],
        )
    )
    out = scored[:top_k]
    for i, row in enumerate(out):
        row["rank"] = i + 1
        row["leader_supported"] = "leader_endpoint_resolved" in (row.get("candidate_generation_sources") or [])
    return out
