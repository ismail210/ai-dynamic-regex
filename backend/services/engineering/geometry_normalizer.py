"""Merge collinear CAD path fragments into a single member candidate.

PDF exporters often emit one visual beam as several short collinear
strokes. The graph then treats each fragment as an unrelated object.
This pass stitches near-collinear, endpoint-close line/polyline/path
objects on the same page. Leaders, dimensions, and closed shapes are
left alone. Provenance is kept on ``merged_from``.
"""

from __future__ import annotations

import hashlib
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from services.engineering.drawing_scale import (
    DrawingScale,
    fragment_gap_pdf_points,
    real_inches_from_pdf_points,
)


def _bbox_from_points(points: Sequence[Sequence[float]]) -> List[float]:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]


def _length_of_segments(points: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        total += math.hypot(
            float(points[i][0]) - float(points[i - 1][0]),
            float(points[i][1]) - float(points[i - 1][1]),
        )
    return round(total, 3)


def _orientation_deg(p0: Sequence[float], p1: Sequence[float]) -> float:
    return round(
        math.degrees(math.atan2(float(p1[1]) - float(p0[1]), float(p1[0]) - float(p0[0]))),
        2,
    )


def _gid(page_number: int, ordinal: int, bbox: Sequence[float], kind: str) -> str:
    seed = "|".join(
        [
            str(page_number),
            str(ordinal),
            kind,
            ",".join(f"{v:.2f}" for v in bbox),
            "merged",
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"geom_{digest}"

_MERGEABLE = {"line", "polyline", "path"}
_ANGLE_TOL_DEG = 8.0


def _endpoints(obj: dict) -> Optional[Tuple[List[float], List[float]]]:
    points = obj.get("points") or []
    if len(points) >= 2:
        return [float(points[0][0]), float(points[0][1])], [
            float(points[-1][0]),
            float(points[-1][1]),
        ]
    bbox = obj.get("bbox") or []
    if len(bbox) >= 4:
        return [float(bbox[0]), float(bbox[1])], [float(bbox[2]), float(bbox[3])]
    return None


def _angle_diff_deg(a: float, b: float) -> float:
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)


def _hypot(p: Sequence[float], q: Sequence[float]) -> float:
    return math.hypot(float(p[0]) - float(q[0]), float(p[1]) - float(q[1]))


def _point_line_distance(point: Sequence[float], p0: Sequence[float], p1: Sequence[float]) -> float:
    dx = float(p1[0]) - float(p0[0])
    dy = float(p1[1]) - float(p0[1])
    denom = math.hypot(dx, dy)
    if denom < 1e-6:
        return _hypot(point, p0)
    return abs(dy * (float(point[0]) - float(p0[0])) - dx * (float(point[1]) - float(p0[1]))) / denom


def _collinear_abutting(a: dict, b: dict, gap: float) -> bool:
    ends_a = _endpoints(a)
    ends_b = _endpoints(b)
    if ends_a is None or ends_b is None:
        return False
    a0, a1 = ends_a
    b0, b1 = ends_b
    ang = _angle_diff_deg(_orientation_deg(a0, a1), _orientation_deg(b0, b1))
    if ang > _ANGLE_TOL_DEG:
        return False
    closest = min(_hypot(a0, b0), _hypot(a0, b1), _hypot(a1, b0), _hypot(a1, b1))
    if closest > gap:
        return False
    mid_b = [(b0[0] + b1[0]) / 2.0, (b0[1] + b1[1]) / 2.0]
    lateral = _point_line_distance(mid_b, a0, a1)
    return lateral <= max(2.0, gap * 0.4)


def _union_find(n: int) -> Tuple[List[int], Any, Any]:
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    return parent, find, union


def _ordered_points(members: Sequence[dict]) -> List[List[float]]:
    remaining = list(members)
    seed = remaining.pop(0)
    ends = _endpoints(seed)
    assert ends is not None
    chain = [ends[0], ends[1]]
    for extra in seed.get("points") or []:
        pt = [float(extra[0]), float(extra[1])]
        if pt not in chain:
            chain.insert(-1, pt)
    while remaining:
        head, tail = chain[0], chain[-1]
        best_i = -1
        best_rev = False
        best_at_head = False
        best_d = 1e18
        for i, obj in enumerate(remaining):
            pair = _endpoints(obj)
            if pair is None:
                continue
            p0, p1 = pair
            for reverse, at_head, dist in (
                (False, False, _hypot(tail, p0)),
                (True, False, _hypot(tail, p1)),
                (True, True, _hypot(head, p0)),
                (False, True, _hypot(head, p1)),
            ):
                if dist < best_d:
                    best_d = dist
                    best_i = i
                    best_rev = reverse
                    best_at_head = at_head
        if best_i < 0:
            break
        obj = remaining.pop(best_i)
        pair = _endpoints(obj)
        if pair is None:
            continue
        p0, p1 = pair
        pts = [[float(p[0]), float(p[1])] for p in (obj.get("points") or [p0, p1])]
        if best_rev:
            pts = list(reversed(pts))
        if best_at_head:
            chain = pts[:-1] + chain
        else:
            chain = chain + pts[1:]
    # Deduplicate consecutive duplicates.
    cleaned: List[List[float]] = []
    for pt in chain:
        rounded = [round(pt[0], 2), round(pt[1], 2)]
        if not cleaned or cleaned[-1] != rounded:
            cleaned.append(rounded)
    return cleaned[:64]


def _merge_cluster(members: Sequence[dict], scale: Optional[DrawingScale]) -> dict:
    points = _ordered_points(members)
    bbox = _bbox_from_points(points)
    length = _length_of_segments(points) if len(points) >= 2 else 0.0
    width = round(abs(bbox[2] - bbox[0]), 3)
    height = round(abs(bbox[3] - bbox[1]), 3)
    kind = "polyline" if len(members) > 1 or len(points) > 2 else str(members[0].get("kind") or "line")
    page = int(members[0].get("page_number") or members[0].get("page") or 0)
    merged = dict(members[0])
    merged.update(
        {
            "geometry_id": _gid(page, 0, bbox, kind),
            "kind": kind,
            "geometry_type": kind,
            "bbox": bbox,
            "coordinates": bbox,
            "center": [
                round((bbox[0] + bbox[2]) / 2.0, 2),
                round((bbox[1] + bbox[3]) / 2.0, 2),
            ],
            "length": length,
            "width": width,
            "height": height,
            "area": round(width * height, 3),
            "aspect_ratio": round(width / height if height else width, 4),
            "orientation": (
                _orientation_deg(points[0], points[-1]) if len(points) >= 2 else 0.0
            ),
            "points": points,
            "merged_from": [str(m.get("geometry_id") or "") for m in members],
            "length_real_inches": real_inches_from_pdf_points(length, scale),
        }
    )
    return merged


def merge_collinear_fragments(
    objects: Iterable[dict],
    *,
    scale: Optional[DrawingScale] = None,
    gap: Optional[float] = None,
) -> Tuple[List[dict], Dict[str, int]]:
    """Return objects with collinear same-page fragments merged."""

    items = list(objects)
    max_gap = float(gap) if gap is not None else fragment_gap_pdf_points(scale)
    by_page: Dict[int, List[int]] = {}
    for idx, obj in enumerate(items):
        page = int(obj.get("page_number") or obj.get("page") or 0)
        by_page.setdefault(page, []).append(idx)

    parent, find, union = _union_find(len(items))
    merge_links = 0
    for indexes in by_page.values():
        mergeable = [
            i for i in indexes if str(items[i].get("kind") or "") in _MERGEABLE
        ]
        for pos, i in enumerate(mergeable):
            for j in mergeable[pos + 1 :]:
                if _collinear_abutting(items[i], items[j], max_gap):
                    union(i, j)
                    merge_links += 1

    clusters: Dict[int, List[int]] = {}
    for idx in range(len(items)):
        clusters.setdefault(find(idx), []).append(idx)

    merged: List[dict] = []
    clusters_merged = 0
    fragments_consumed = 0
    for group in clusters.values():
        members = [items[i] for i in group]
        mergeable_members = [
            m for m in members if str(m.get("kind") or "") in _MERGEABLE
        ]
        if len(mergeable_members) <= 1:
            merged.extend(members)
            continue
        clusters_merged += 1
        fragments_consumed += len(mergeable_members)
        merged.append(_merge_cluster(mergeable_members, scale))
        leftover = [m for m in members if m not in mergeable_members]
        merged.extend(leftover)

    stats = {
        "input_count": len(items),
        "output_count": len(merged),
        "clusters_merged": clusters_merged,
        "fragments_consumed": fragments_consumed,
        "merge_links": merge_links,
        "fragment_gap_pdf_points": round(max_gap, 3),
    }
    return merged, stats
