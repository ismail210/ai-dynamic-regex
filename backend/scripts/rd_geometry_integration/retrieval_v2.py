"""Deterministic geometry retrieval v2 (R&D / shadow only).

Candidate-generation research. Does not replace ``retrieval.py``, does not
import production association, and never invents member roles or section sizes.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Linear strokes that may be structural members (role remains unknown).
_STROKE_KINDS = {"line", "polyline", "path", "arc", "curve"}
_SMALL_KINDS = _STROKE_KINDS | {"rectangle"}
_NON_MEMBER_KINDS = {"symbol"}
_CALLOUT_KINDS = {"leader", "dimension"}

# Feature thresholds — generic geometry, not project/page/token rules.
_GIANT_EXTENT = 400.0
_GIANT_AREA = 80_000.0
_GIANT_LOCAL_RATIO = 3.0
_LOCAL_WINDOW = 160.0
_LOCAL_PERP = 28.0
_ON_SEGMENT_PAD = 0.04
_LEADER_NEAR_LABEL = 90.0
_LEADER_JOIN = 12.0
_LEADER_TIP_RADIUS = 42.0
_MIN_CALLOUT_LEN = 8.0
_RECLASSIFY_MIN_LEN = 40.0
_SMALL_EXTENT = 120.0
_DEFAULT_TOP_K = 8
_DEFAULT_MAX_DIST = 180.0


def _center(bbox: Sequence[float]) -> Tuple[float, float]:
    return (
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    )


def _bbox_area(bbox: Sequence[float]) -> float:
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(
        0.0, float(bbox[3]) - float(bbox[1])
    )


def _extent(bbox: Sequence[float]) -> float:
    return math.hypot(float(bbox[2]) - float(bbox[0]), float(bbox[3]) - float(bbox[1]))


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


def _project_to_segment(
    px: float, py: float, a: Sequence[float], b: Sequence[float]
) -> Tuple[float, float, float, float]:
    """Return (clamped_dist, unbounded_t, qx, qy) for point→segment."""
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return math.hypot(px - ax, py - ay), 0.0, ax, ay
    t = ((px - ax) * dx + (py - ay) * dy) / denom
    t_clamp = max(0.0, min(1.0, t))
    qx, qy = ax + t_clamp * dx, ay + t_clamp * dy
    return math.hypot(px - qx, py - qy), t, qx, qy


def _polyline_points(obj: Dict[str, Any], bbox: Sequence[float]) -> List[List[float]]:
    points: List[List[float]] = []
    for pt in obj.get("points") or obj.get("centerline") or []:
        if pt is not None and len(pt) >= 2:
            points.append([float(pt[0]), float(pt[1])])
            if len(points) >= 64:
                break
    if len(points) >= 2:
        return points
    return [[float(bbox[0]), float(bbox[1])], [float(bbox[2]), float(bbox[3])]]


def _polyline_length(points: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for i in range(len(points) - 1):
        total += math.hypot(
            float(points[i + 1][0]) - float(points[i][0]),
            float(points[i + 1][1]) - float(points[i][1]),
        )
    return total


def _segment_bbox(a: Sequence[float], b: Sequence[float], pad: float = 1.0) -> List[float]:
    return [
        min(float(a[0]), float(b[0])) - pad,
        min(float(a[1]), float(b[1])) - pad,
        max(float(a[0]), float(b[0])) + pad,
        max(float(a[1]), float(b[1])) + pad,
    ]


def _clip_segment_window(
    a: Sequence[float], b: Sequence[float], t: float, half: float
) -> Tuple[List[float], List[float]]:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    length = math.hypot(bx - ax, by - ay)
    if length <= 1e-6:
        return [ax, ay], [bx, by]
    t0 = max(0.0, min(1.0, t - half / length))
    t1 = max(0.0, min(1.0, t + half / length))
    if t1 - t0 < 1e-6:
        t0, t1 = 0.0, 1.0
    return [ax + t0 * (bx - ax), ay + t0 * (by - ay)], [
        ax + t1 * (bx - ax),
        ay + t1 * (by - ay),
    ]


def geometry_record_v2(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a production geometry object for v2 (keeps full polyline points)."""
    bbox = obj.get("bbox") or [0, 0, 0, 0]
    bbox = [float(v) for v in bbox[:4]]
    center = obj.get("center") or _center(bbox)
    kind = str(obj.get("kind") or obj.get("geometry_type") or "unknown").lower()
    points = _polyline_points(obj, bbox)
    length = obj.get("length")
    if length is None:
        length = _polyline_length(points)
    role = "unknown"
    if kind == "leader":
        role = "leader"
    elif kind == "dimension":
        role = "dimension"
    w = abs(bbox[2] - bbox[0])
    h = abs(bbox[3] - bbox[1])
    return {
        "geometry_id": obj.get("geometry_id") or obj.get("object_id"),
        "parent_geometry_id": obj.get("geometry_id") or obj.get("object_id"),
        "page_number": int(obj.get("page_number") or obj.get("page") or 0),
        "geometry_kind": kind,
        "extracted_kind": kind,
        "geometry_role": role,
        "bbox": bbox,
        "center": [float(center[0]), float(center[1])],
        "points": points,
        "centerline": points if len(points) >= 2 else [[bbox[0], bbox[1]], [bbox[2], bbox[3]]],
        "orientation": obj.get("orientation") if obj.get("orientation") is not None else obj.get("angle"),
        "length": float(length or 0.0),
        "extent": math.hypot(w, h),
        "bbox_width": w,
        "bbox_height": h,
        "area": w * h,
        "leader_endpoints": obj.get("leader_endpoints"),
        "source_primitive": {
            "layer": obj.get("layer") or obj.get("drawing_layer"),
            "region_id": obj.get("region_id"),
            "source_format": obj.get("source_format") or "pdf_drawings",
            "extracted_kind": kind,
        },
        "evidence_status": "retrieved",
        "derived": False,
    }


def _leader_endpoints(geo: Dict[str, Any]) -> List[Tuple[float, float]]:
    eps = geo.get("leader_endpoints") or {}
    out: List[Tuple[float, float]] = []
    for key in ("near_endpoint", "far_endpoint"):
        pt = eps.get(key) if isinstance(eps, dict) else None
        if pt is not None and len(pt) >= 2:
            out.append((float(pt[0]), float(pt[1])))
    points = geo.get("points") or geo.get("centerline") or []
    if len(points) >= 2:
        out.append((float(points[0][0]), float(points[0][1])))
        out.append((float(points[-1][0]), float(points[-1][1])))
    if not out:
        bb = geo.get("bbox") or [0, 0, 0, 0]
        x0, y0, x1, y1 = (float(v) for v in bb[:4])
        out.extend([(x0, y0), (x0, y1), (x1, y0), (x1, y1)])
    # unique
    uniq: List[Tuple[float, float]] = []
    for pt in out:
        if not any(math.hypot(pt[0] - u[0], pt[1] - u[1]) < 0.5 for u in uniq):
            uniq.append(pt)
    return uniq


def _is_callout_for_label(geo: Dict[str, Any], label_center: Sequence[float]) -> bool:
    """True when this primitive behaves as a leader/callout of *this* label."""
    kind = str(geo.get("extracted_kind") or geo.get("geometry_kind") or "")
    if kind not in _CALLOUT_KINDS:
        return False
    length = float(geo.get("length") or 0.0)
    # Long linear strokes classified as dimension are usually members next to
    # numeric section text, not dimension ticks / callouts.
    if kind == "dimension" and length >= _RECLASSIFY_MIN_LEN:
        return False
    lx, ly = float(label_center[0]), float(label_center[1])
    ends = _leader_endpoints(geo)
    if not ends:
        return False
    d_near = min(math.hypot(lx - x, ly - y) for x, y in ends)
    d_far = max(math.hypot(lx - x, ly - y) for x, y in ends)
    if d_near <= _LEADER_NEAR_LABEL and d_far - d_near >= 10.0:
        return True
    if kind == "leader" and _MIN_CALLOUT_LEN <= length <= 72.0 and d_near <= 40.0:
        return True
    return False


def _looks_like_linear_stroke(geo: Dict[str, Any]) -> bool:
    """Misclassified leader/dimension that is still a linear primitive."""
    length = float(geo.get("length") or 0.0)
    w = float(geo.get("bbox_width") or 0.0)
    h = float(geo.get("bbox_height") or 0.0)
    if length < _RECLASSIFY_MIN_LEN:
        return False
    thin = min(w, h) <= max(24.0, 0.25 * max(w, h, 1.0))
    return thin or len(geo.get("points") or []) >= 3


def _eligible_member_stroke(geo: Dict[str, Any], label_center: Sequence[float]) -> bool:
    kind = str(geo.get("extracted_kind") or geo.get("geometry_kind") or "")
    if kind in _NON_MEMBER_KINDS:
        return False
    if kind in _SMALL_KINDS:
        return True
    if kind in _CALLOUT_KINDS:
        if _is_callout_for_label(geo, label_center):
            return False
        return _looks_like_linear_stroke(geo)
    return False


def derive_local_segments(geo: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Split a primitive into consecutive segments (and keep the parent)."""
    points = geo.get("points") or geo.get("centerline") or []
    if len(points) < 2:
        return [geo]
    parent_id = geo.get("parent_geometry_id") or geo.get("geometry_id")
    out = [geo]
    if len(points) == 2:
        return out
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        seg_len = math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
        if seg_len < 4.0:
            continue
        rec = dict(geo)
        rec["geometry_id"] = f"{parent_id}::seg_{i}"
        rec["parent_geometry_id"] = parent_id
        rec["derived"] = True
        rec["derived_kind"] = "segment"
        rec["points"] = [list(a), list(b)]
        rec["centerline"] = rec["points"]
        rec["bbox"] = _segment_bbox(a, b)
        rec["center"] = list(_center(rec["bbox"]))
        rec["length"] = seg_len
        rec["extent"] = _extent(rec["bbox"])
        rec["bbox_width"] = abs(rec["bbox"][2] - rec["bbox"][0])
        rec["bbox_height"] = abs(rec["bbox"][3] - rec["bbox"][1])
        rec["area"] = rec["bbox_width"] * rec["bbox_height"]
        rec["geometry_role"] = "unknown"
        out.append(rec)
    return out


def giant_features(
    geo: Dict[str, Any],
    local_pool: Sequence[Dict[str, Any]],
    *,
    perp: Optional[float],
    bbox_dist: float,
    on_segment: bool,
) -> Dict[str, Any]:
    extent = float(geo.get("extent") or _extent(geo.get("bbox") or [0, 0, 0, 0]))
    area = float(geo.get("area") or _bbox_area(geo.get("bbox") or [0, 0, 0, 0]))
    local_extents = sorted(
        float(g.get("extent") or 0.0)
        for g in local_pool
        if float(g.get("extent") or 0.0) > 8.0
    )
    median = local_extents[len(local_extents) // 2] if local_extents else extent
    ratio = extent / max(median, 1.0)
    containment = bbox_dist <= 0.5 and (perp is None or perp > _LOCAL_PERP)
    smaller_local = any(
        float(g.get("extent") or 0.0) > 8.0
        and float(g.get("extent") or 0.0) * _GIANT_LOCAL_RATIO < extent
        for g in local_pool
        if g.get("parent_geometry_id") != geo.get("parent_geometry_id")
    )
    is_giant = (
        extent >= _GIANT_EXTENT
        or area >= _GIANT_AREA
        or (ratio >= _GIANT_LOCAL_RATIO and extent >= 250.0)
    )
    suppress = bool(
        is_giant
        and (containment or (smaller_local and (perp is None or perp > 18.0)))
        and not (on_segment and perp is not None and perp <= 18.0)
    )
    return {
        "is_giant": is_giant,
        "suppress": suppress,
        "extent": round(extent, 2),
        "area": round(area, 2),
        "local_extent_ratio": round(ratio, 3),
        "containment_without_stroke": containment,
        "smaller_local_exists": smaller_local,
    }


def _closest_on_polyline(
    px: float, py: float, points: Sequence[Sequence[float]]
) -> Tuple[float, float, int, List[float], List[float], float, float]:
    best = (1e12, 0.0, 0, [px, py], [px, py], px, py)
    if len(points) < 2:
        return best
    for i in range(len(points) - 1):
        dist, t, qx, qy = _project_to_segment(px, py, points[i], points[i + 1])
        if dist < best[0]:
            best = (dist, t, i, list(points[i]), list(points[i + 1]), qx, qy)
    return best


def _score_stroke(
    label_bbox: Sequence[float],
    label_orientation: Optional[float],
    geo: Dict[str, Any],
) -> Dict[str, Any]:
    lx, ly = _center(label_bbox)
    gb = geo["bbox"]
    bbox_dist = _point_to_bbox_distance(lx, ly, gb)
    points = geo.get("points") or geo.get("centerline") or []
    perp, t, _i, a, b, qx, qy = _closest_on_polyline(lx, ly, points)
    on_segment = -_ON_SEGMENT_PAD <= t <= 1.0 + _ON_SEGMENT_PAD
    overlap = 0.0
    x0 = max(float(label_bbox[0]), float(gb[0]))
    y0 = max(float(label_bbox[1]), float(gb[1]))
    x1 = min(float(label_bbox[2]), float(gb[2]))
    y1 = min(float(label_bbox[3]), float(gb[3]))
    if x1 > x0 and y1 > y0:
        overlap = (x1 - x0) * (y1 - y0)
    orient_delta = _angle_delta_deg(label_orientation, geo.get("orientation"))
    gx, gy = geo["center"][0], geo["center"][1]
    return {
        "geometry_id": geo["geometry_id"],
        "parent_geometry_id": geo.get("parent_geometry_id") or geo["geometry_id"],
        "page_number": geo["page_number"],
        "geometry_kind": (
            "line"
            if str(geo.get("extracted_kind") or "") in _CALLOUT_KINDS
            else geo.get("geometry_kind")
        ),
        "extracted_kind": geo.get("extracted_kind") or geo.get("geometry_kind"),
        "geometry_role": "unknown",
        "geometry_bbox": list(gb),
        "centerline": [list(a), list(b)] if a and b else list(points[:2]),
        "center_distance": round(math.hypot(lx - gx, ly - gy), 2),
        "bbox_distance": round(bbox_dist, 2),
        "perpendicular_distance": None if perp >= 1e12 else round(perp, 2),
        "projection_t": round(t, 4),
        "on_segment": on_segment,
        "projected_point": [round(qx, 2), round(qy, 2)],
        "overlap_area": round(overlap, 2),
        "orientation_delta_deg": None if orient_delta is None else round(orient_delta, 2),
        "extent": round(float(geo.get("extent") or _extent(gb)), 2),
        "length": round(float(geo.get("length") or 0.0), 2),
        "derived": bool(geo.get("derived")),
        "reclassified_from": (
            geo.get("extracted_kind")
            if str(geo.get("extracted_kind") or "") in _CALLOUT_KINDS
            else None
        ),
        "leader_path_ids": [],
        "candidate_generation_sources": [],
        "leader_evidence": None,
        "evidence_status": "candidate",
    }


def _chain_leader_targets(
    label_center: Sequence[float],
    leaders: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """BFS from label-adjacent leaders only. Do not union a whole-page graph."""
    lx, ly = float(label_center[0]), float(label_center[1])
    ends_by = [_leader_endpoints(g) for g in leaders]
    nearby_idx: List[int] = []
    for i, geo in enumerate(leaders):
        ends = ends_by[i]
        d = min(math.hypot(lx - x, ly - y) for x, y in ends) if ends else 1e9
        bbox_d = _point_to_bbox_distance(lx, ly, geo.get("bbox") or [0, 0, 0, 0])
        if min(d, bbox_d) <= _LEADER_NEAR_LABEL:
            nearby_idx.append(i)
    if not nearby_idx:
        return []

    adj: List[List[int]] = [[] for _ in leaders]
    for i, ei in enumerate(ends_by):
        for j in range(i + 1, len(ends_by)):
            connected = False
            for ax, ay in ei:
                for bx, by in ends_by[j]:
                    if math.hypot(ax - bx, ay - by) <= _LEADER_JOIN:
                        connected = True
                        break
                if connected:
                    break
            if connected:
                adj[i].append(j)
                adj[j].append(i)

    max_chain = 8
    max_span = 220.0
    used = set()
    chains: List[Dict[str, Any]] = []
    nearby_set = set(nearby_idx)
    for seed in nearby_idx:
        if seed in used:
            continue
        queue = [seed]
        members_i: List[int] = []
        seen = set()
        while queue and len(members_i) < max_chain:
            i = queue.pop(0)
            if i in seen:
                continue
            seen.add(i)
            members_i.append(i)
            used.add(i)
            for j in adj[i]:
                if j in seen:
                    continue
                xs = [p[0] for k in members_i + [j] for p in ends_by[k]]
                ys = [p[1] for k in members_i + [j] for p in ends_by[k]]
                span = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
                if span > max_span:
                    continue
                queue.append(j)
        members = [leaders[i] for i in members_i]
        all_ends: List[Tuple[float, float]] = []
        for i in members_i:
            all_ends.extend(ends_by[i])
        if not all_ends:
            continue
        target = max(all_ends, key=lambda p: math.hypot(p[0] - lx, p[1] - ly))
        near = min(all_ends, key=lambda p: math.hypot(p[0] - lx, p[1] - ly))
        if math.hypot(target[0] - lx, target[1] - ly) < 16.0:
            continue
        seed_geo = leaders[seed]
        chains.append(
            {
                "leader_geometry_id": str(seed_geo.get("geometry_id")),
                "leader_path_ids": [str(m.get("geometry_id")) for m in members],
                "target_point": [round(target[0], 2), round(target[1], 2)],
                "label_end": [round(near[0], 2), round(near[1], 2)],
                "n_leaders_in_chain": len(members),
                "touches_label_leaders": [
                    str(leaders[i].get("geometry_id")) for i in members_i if i in nearby_set
                ],
            }
        )
    return chains


def _mechanism_for(feat: Dict[str, Any]) -> str:
    sources = feat.get("candidate_generation_sources") or []
    if "leader_target" in sources:
        return "leader_target"
    if feat.get("derived") or "local_segment" in sources:
        return "local_segment"
    extent = float(feat.get("extent") or 0.0)
    if extent <= _SMALL_EXTENT and "direct_segment" in sources:
        return "small_detail"
    if "direct_segment" in sources:
        return "direct_segment"
    return "other"


def retrieve_candidates_v2(
    label: Dict[str, Any],
    geometry_records: Sequence[Dict[str, Any]],
    *,
    top_k: int = _DEFAULT_TOP_K,
    max_distance: float = _DEFAULT_MAX_DIST,
) -> List[Dict[str, Any]]:
    """Return a shortlist of geometry candidates for one label.

    Leaders/callouts of this label are never returned as the member.
    Giant primitives may be replaced by a local window; they are not
    deleted globally.
    """
    bbox = label.get("bbox") or label.get("label_bbox")
    page = int(label.get("page") or label.get("page_number") or 0)
    if not bbox or len(bbox) < 4 or not page:
        return []
    orientation = label.get("rotation")
    if orientation is None:
        orientation = label.get("orientation")
    lx, ly = _center(bbox)

    page_geos = [
        g
        for g in geometry_records
        if int(g.get("page_number") or g.get("page") or 0) == page
    ]
    leaders = [
        g
        for g in page_geos
        if str(g.get("extracted_kind") or g.get("geometry_kind") or "") == "leader"
    ]

    expanded: List[Dict[str, Any]] = []
    for geo in page_geos:
        if not _eligible_member_stroke(geo, (lx, ly)):
            continue
        expanded.extend(derive_local_segments(geo))

    local_pool = []
    for geo in expanded:
        bb = geo.get("bbox") or [0, 0, 0, 0]
        if _point_to_bbox_distance(lx, ly, bb) <= max_distance or _bbox_area(bb) <= 0:
            local_pool.append(geo)

    by_parent: Dict[str, Dict[str, Any]] = {}

    def consider(feat: Dict[str, Any], source: str, *, leader_ev: Optional[Dict[str, Any]] = None) -> None:
        pid = feat.get("parent_geometry_id") or feat.get("geometry_id")
        feat = dict(feat)
        feat["candidate_generation_sources"] = [source]
        if leader_ev:
            feat["leader_path_ids"] = list(leader_ev.get("leader_path_ids") or [])
            feat["leader_evidence"] = {
                "leader_geometry_id": leader_ev.get("leader_geometry_id"),
                "target_point": leader_ev.get("target_point"),
                "target_geometry_ids": [feat["geometry_id"]],
                "leader_path_ids": leader_ev.get("leader_path_ids"),
            }
        existing = by_parent.get(pid)
        if existing is None:
            by_parent[pid] = feat
            return
        if _rank_key(feat) < _rank_key(existing):
            sources = list(existing.get("candidate_generation_sources") or [])
            if source not in sources:
                sources.append(source)
            feat["candidate_generation_sources"] = sources
            if leader_ev and not existing.get("leader_evidence"):
                feat["leader_evidence"] = feat.get("leader_evidence")
            elif existing.get("leader_evidence"):
                feat["leader_evidence"] = existing["leader_evidence"]
                feat["leader_path_ids"] = existing.get("leader_path_ids") or feat.get("leader_path_ids")
            by_parent[pid] = feat
        else:
            if source not in existing["candidate_generation_sources"]:
                existing["candidate_generation_sources"].append(source)
            if leader_ev and not existing.get("leader_evidence"):
                existing["leader_evidence"] = {
                    "leader_geometry_id": leader_ev.get("leader_geometry_id"),
                    "target_point": leader_ev.get("target_point"),
                    "target_geometry_ids": [existing["geometry_id"]],
                    "leader_path_ids": leader_ev.get("leader_path_ids"),
                }
                existing["leader_path_ids"] = list(leader_ev.get("leader_path_ids") or [])

    # Direct / local-segment scoring
    for geo in expanded:
        feat = _score_stroke(bbox, orientation, geo)
        perp = feat.get("perpendicular_distance")
        bbox_dist = float(feat.get("bbox_distance") or 0.0)
        if bbox_dist > max_distance and float(feat.get("overlap_area") or 0.0) <= 0:
            if perp is None or perp > max_distance:
                continue
        gf = giant_features(
            geo,
            local_pool,
            perp=perp,
            bbox_dist=bbox_dist,
            on_segment=bool(feat.get("on_segment")),
        )
        feat["giant"] = gf
        if gf["suppress"]:
            # Replace with a local window when the label actually sits on a stroke.
            if feat.get("on_segment") and perp is not None and perp <= _LOCAL_PERP:
                cl = feat.get("centerline") or []
                if len(cl) >= 2:
                    t = float(feat.get("projection_t") or 0.5)
                    a, b = _clip_segment_window(cl[0], cl[-1], t, _LOCAL_WINDOW / 2.0)
                    window = dict(geo)
                    window["geometry_id"] = f"{geo.get('parent_geometry_id') or geo.get('geometry_id')}::local"
                    window["parent_geometry_id"] = geo.get("parent_geometry_id") or geo.get("geometry_id")
                    window["derived"] = True
                    window["derived_kind"] = "local_window"
                    window["points"] = [a, b]
                    window["centerline"] = [a, b]
                    window["bbox"] = _segment_bbox(a, b, pad=2.0)
                    window["center"] = list(_center(window["bbox"]))
                    window["length"] = math.hypot(b[0] - a[0], b[1] - a[1])
                    window["extent"] = _extent(window["bbox"])
                    wfeat = _score_stroke(bbox, orientation, window)
                    wfeat["giant"] = dict(gf)
                    wfeat["giant"]["suppress"] = False
                    wfeat["giant"]["replaced_with_local_window"] = True
                    consider(wfeat, "local_segment")
            continue
        source = "local_segment" if geo.get("derived") else "direct_segment"
        consider(feat, source)

    # Leader → tip → nearby small geometry (leader never becomes the member)
    chains = _chain_leader_targets((lx, ly), leaders)
    for chain in chains:
        tx, ty = chain["target_point"]
        for geo in page_geos:
            gid = str(geo.get("geometry_id") or "")
            if gid in set(chain.get("leader_path_ids") or []):
                continue
            kind = str(geo.get("extracted_kind") or geo.get("geometry_kind") or "")
            if kind in {"leader", "dimension", "symbol"}:
                # Allow small rectangles/strokes only; skip callout kinds.
                continue
            if kind not in _SMALL_KINDS:
                continue
            if float(geo.get("extent") or 0.0) >= _GIANT_EXTENT:
                continue
            tip_d = _point_to_bbox_distance(tx, ty, geo.get("bbox") or [0, 0, 0, 0])
            points = geo.get("points") or []
            if len(points) >= 2:
                tip_d = min(tip_d, _closest_on_polyline(tx, ty, points)[0])
            if tip_d > _LEADER_TIP_RADIUS:
                continue
            feat = _score_stroke(bbox, orientation, geo)
            feat["tip_distance"] = round(tip_d, 2)
            feat["giant"] = giant_features(
                geo,
                local_pool,
                perp=feat.get("perpendicular_distance"),
                bbox_dist=float(feat.get("bbox_distance") or 0.0),
                on_segment=bool(feat.get("on_segment")),
            )
            if feat["giant"]["suppress"]:
                continue
            ev = dict(chain)
            ev["target_geometry_ids"] = [feat["geometry_id"]]
            consider(feat, "leader_target", leader_ev=ev)

    scored = list(by_parent.values())
    scored.sort(key=_rank_key)
    out = scored[:top_k]
    for i, row in enumerate(out):
        row["rank"] = i + 1
        row["retrieval_mechanism"] = _mechanism_for(row)
        row["leader_supported"] = "leader_target" in (row.get("candidate_generation_sources") or [])
        if row.get("leader_evidence"):
            row["leader_evidence"]["target_geometry_ids"] = [
                c["parent_geometry_id"]
                for c in out
                if "leader_target" in (c.get("candidate_generation_sources") or [])
            ]
    return out


def _rank_key(feat: Dict[str, Any]) -> Tuple[Any, ...]:
    perp = feat.get("perpendicular_distance")
    bbox_d = float(feat.get("bbox_distance") or 1e6)
    tip = feat.get("tip_distance")
    on_seg = 0 if feat.get("on_segment") else 1
    sources = feat.get("candidate_generation_sources") or []
    is_leader_target = "leader_target" in sources
    giant_pen = 1 if (feat.get("giant") or {}).get("is_giant") and not feat.get("derived") else 0
    extent = float(feat.get("extent") or 0.0)
    strong_local = bool(
        feat.get("on_segment") and perp is not None and float(perp) <= 18.0 and not is_leader_target
    )
    if is_leader_target and tip is not None:
        dist = float(tip)
    elif perp is not None:
        dist = float(perp) + (0.0 if feat.get("on_segment") else 25.0)
    else:
        dist = bbox_d
    # On-stroke local members outrank leader hops. Leader hops still win when
    # the label is not sitting on a stroke (detail/callout cases).
    local_band = 0 if strong_local else 1
    leader_band = 0 if is_leader_target else 1
    return (local_band, giant_pen, on_seg if local_band else 0, dist, leader_band, extent, bbox_d)


def candidate_id_set(candidates: Iterable[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for c in candidates:
        gid = str(c.get("parent_geometry_id") or c.get("geometry_id") or "")
        if gid and gid not in ids:
            ids.append(gid)
        raw = str(c.get("geometry_id") or "")
        if raw and raw not in ids:
            ids.append(raw)
    return ids


def gold_rank(candidates: Sequence[Dict[str, Any]], gold_id: Optional[str]) -> Optional[int]:
    if not gold_id:
        return None
    for i, c in enumerate(candidates):
        if gold_id in {
            str(c.get("geometry_id") or ""),
            str(c.get("parent_geometry_id") or ""),
        }:
            return i + 1
    return None


def has_local_member_candidate(
    candidates: Sequence[Dict[str, Any]],
    *,
    perp_max: float = _LOCAL_PERP,
    tip_max: float = _LEADER_TIP_RADIUS,
) -> bool:
    """Proxy: a non-giant, non-callout stroke is locally near the label or leader tip."""
    for c in candidates:
        kind = str(c.get("extracted_kind") or c.get("geometry_kind") or "")
        if kind == "leader" and not c.get("reclassified_from"):
            # Should not happen; treat as not a member.
            continue
        if (c.get("giant") or {}).get("is_giant") and not c.get("derived"):
            continue
        perp = c.get("perpendicular_distance")
        if (
            perp is not None
            and float(perp) <= perp_max
            and c.get("on_segment")
            and float(c.get("extent") or 0.0) < _GIANT_EXTENT
        ):
            return True
        if c.get("retrieval_mechanism") == "leader_target" or "leader_target" in (
            c.get("candidate_generation_sources") or []
        ):
            tip = c.get("tip_distance")
            if tip is not None and float(tip) <= tip_max:
                return True
            if perp is not None and float(perp) <= 80.0 and float(c.get("extent") or 0.0) <= 220.0:
                return True
    return False
