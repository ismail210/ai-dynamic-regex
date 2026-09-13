"""Deterministic member-candidate geometry for OCR / extraction review.

Builds ``member_candidate`` objects from retained line/polyline strokes and
associates text labels to those candidates for dual text/member bbox display.

Metadata / association evidence only — never feeds takeoff, section prediction,
catalog completion, or incomplete L/2L gates.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services.engineering.geometry_normalizer import merge_collinear_fragments

STRUCT_KINDS = frozenset({"line", "polyline", "path"})
EXCLUDED_KINDS = frozenset({"leader", "dimension", "symbol", "arc", "circle", "rectangle", "block"})

# Tuned from Burrville framing QA: short callouts stay leaders; members are longer.
DEFAULT_MIN_MEMBER_LENGTH_PT = 40.0
DEFAULT_MAX_ASSOCIATION_DISTANCE_PT = 100.0
DEFAULT_LEADER_TIP_RADIUS_PT = 80.0
DEFAULT_AMBIGUITY_MARGIN_PT = 8.0


def unresolved_member_geometry(
    *,
    reason: str = "unresolved",
) -> Dict[str, Any]:
    return {
        "available": False,
        "geometry_id": None,
        "type": "member_candidate",
        "role_hint": None,
        "bbox": None,
        "source_primitive_ids": [],
        "association_method": reason,
        "confidence": 0.0,
    }


def _union_bbox(boxes: Sequence[Sequence[float]]) -> Optional[List[float]]:
    xs0, ys0, xs1, ys1 = [], [], [], []
    for box in boxes:
        if not box or len(box) < 4:
            continue
        xs0.append(float(box[0]))
        ys0.append(float(box[1]))
        xs1.append(float(box[2]))
        ys1.append(float(box[3]))
    if not xs0:
        return None
    return [
        round(min(xs0), 2),
        round(min(ys0), 2),
        round(max(xs1), 2),
        round(max(ys1), 2),
    ]


def _point_to_segment_distance(
    px: float, py: float, x0: float, y0: float, x1: float, y1: float
) -> float:
    dx, dy = x1 - x0, y1 - y0
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def distance_point_to_geometry(
    point: Sequence[float], geometry: Dict[str, Any]
) -> float:
    """Minimum distance from a point to the geometry's polyline / axis-aligned stroke."""

    px, py = float(point[0]), float(point[1])
    points = geometry.get("points") or []
    if len(points) >= 2:
        best = 1e18
        for i in range(len(points) - 1):
            p0, p1 = points[i], points[i + 1]
            best = min(
                best,
                _point_to_segment_distance(
                    px, py, float(p0[0]), float(p0[1]), float(p1[0]), float(p1[1])
                ),
            )
        return best
    bbox = geometry.get("bbox") or []
    if len(bbox) >= 4:
        x0, y0, x1, y1 = map(float, bbox[:4])
        if abs(x0 - x1) < 1e-6 or abs(y0 - y1) < 1e-6:
            return _point_to_segment_distance(px, py, x0, y0, x1, y1)
        cx = min(max(px, min(x0, x1)), max(x0, x1))
        cy = min(max(py, min(y0, y1)), max(y0, y1))
        return math.hypot(px - cx, py - cy)
    return 1e18


def _stable_member_id(page: int, bbox: Sequence[float], source_ids: Sequence[str]) -> str:
    seed = "|".join(
        [
            str(page),
            ",".join(f"{v:.2f}" for v in bbox),
            ",".join(sorted(source_ids)),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"member_{digest}"


def role_hint_from_orientation(orientation: Optional[float], length: float) -> Optional[str]:
    """Neutral orientation hint for review only — not a takeoff entity type."""

    if orientation is None or length < DEFAULT_MIN_MEMBER_LENGTH_PT:
        return None
    ang = abs(float(orientation)) % 180.0
    ang = min(ang, 180.0 - ang)
    if ang <= 18.0:
        return "beam_like"
    if abs(ang - 90.0) <= 18.0:
        return "column_like"
    if 25.0 <= ang <= 65.0:
        return "brace_like"
    return None


def build_member_candidates(
    geometry: Dict[str, Any],
    *,
    min_length_pt: float = DEFAULT_MIN_MEMBER_LENGTH_PT,
) -> List[dict]:
    """Return member_candidate dicts from structural strokes (leaders excluded)."""

    objects = [
        obj
        for obj in (geometry.get("objects") or [])
        if str(obj.get("kind") or "").lower() in STRUCT_KINDS
        and float(obj.get("length") or 0.0) >= float(min_length_pt)
    ]
    if not objects:
        return []

    # Group per page with the same collinear/abutting rules as fragment merge.
    by_page: Dict[int, List[dict]] = {}
    for obj in objects:
        page = int(obj.get("page_number") or obj.get("page") or 0)
        by_page.setdefault(page, []).append(obj)

    candidates: List[dict] = []
    for page, group in by_page.items():
        merged, _stats = merge_collinear_fragments(group)
        for item in merged:
            kind = str(item.get("kind") or "").lower()
            if kind in EXCLUDED_KINDS:
                continue
            if kind not in STRUCT_KINDS:
                continue
            length = float(item.get("length") or 0.0)
            if length < float(min_length_pt):
                continue
            bbox = item.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            source_ids = [
                sid
                for sid in (item.get("merged_from") or [item.get("geometry_id")])
                if sid
            ]
            if not source_ids:
                source_ids = [str(item.get("geometry_id") or "")]
            source_ids = [str(s) for s in source_ids if s]
            member_id = _stable_member_id(page, bbox, source_ids)
            orientation = item.get("orientation")
            candidates.append(
                {
                    "geometry_id": member_id,
                    "type": "member_candidate",
                    "geometry_type": "member_candidate",
                    "kind": "member_candidate",
                    "member_geometry_kind": kind,
                    "page_number": page,
                    "page": page,
                    "bbox": list(bbox),
                    "coordinates": list(bbox),
                    "center": item.get("center")
                    or [
                        round((float(bbox[0]) + float(bbox[2])) / 2.0, 2),
                        round((float(bbox[1]) + float(bbox[3])) / 2.0, 2),
                    ],
                    "length": length,
                    "orientation": orientation,
                    "points": item.get("points") or [],
                    "source_primitive_ids": source_ids,
                    "role_hint": role_hint_from_orientation(
                        float(orientation) if orientation is not None else None,
                        length,
                    ),
                }
            )
    return candidates


def _text_center(bbox: Sequence[float]) -> Tuple[float, float]:
    return (
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    )


def _leader_far_point(leader: Dict[str, Any], text_center: Sequence[float]) -> Optional[List[float]]:
    endpoints = leader.get("leader_endpoints") or {}
    far = endpoints.get("far_endpoint")
    near = endpoints.get("near_endpoint")
    if far and len(far) >= 2 and near and len(near) >= 2:
        # Prefer the endpoint farther from the text as the member tip.
        d_far = math.hypot(float(far[0]) - float(text_center[0]), float(far[1]) - float(text_center[1]))
        d_near = math.hypot(float(near[0]) - float(text_center[0]), float(near[1]) - float(text_center[1]))
        return list(far) if d_far >= d_near else list(near)
    points = leader.get("points") or []
    if len(points) >= 2:
        p0, p1 = points[0], points[-1]
        d0 = math.hypot(float(p0[0]) - float(text_center[0]), float(p0[1]) - float(text_center[1]))
        d1 = math.hypot(float(p1[0]) - float(text_center[0]), float(p1[1]) - float(text_center[1]))
        return list(p1) if d1 >= d0 else list(p0)
    return None


def _rank_candidates(
    point: Sequence[float],
    candidates: Iterable[dict],
    *,
    max_distance: float,
) -> List[Tuple[float, dict]]:
    ranked: List[Tuple[float, dict]] = []
    for cand in candidates:
        d = distance_point_to_geometry(point, cand)
        if d <= max_distance:
            ranked.append((d, cand))
    ranked.sort(key=lambda item: (item[0], -float(item[1].get("length") or 0.0)))
    return ranked


def associate_text_to_member_candidate(
    *,
    text_bbox: Optional[Sequence[float]],
    page_number: int,
    geometry: Dict[str, Any],
    member_candidates: Optional[List[dict]] = None,
    page_candidates: Optional[List[dict]] = None,
    page_leaders: Optional[List[dict]] = None,
    claimed_member_ids: Optional[set] = None,
    max_distance_pt: float = DEFAULT_MAX_ASSOCIATION_DISTANCE_PT,
    leader_tip_radius_pt: float = DEFAULT_LEADER_TIP_RADIUS_PT,
    ambiguity_margin_pt: float = DEFAULT_AMBIGUITY_MARGIN_PT,
) -> Dict[str, Any]:
    """Associate annotation text to a member_candidate, or return unresolved.

    Prefer leader far-tip → nearby structural stroke; else proximity to text
    center. Never returns a leader as the member.
    """

    if not text_bbox or len(text_bbox) < 4:
        return unresolved_member_geometry(reason="missing_text_bbox")

    if page_candidates is None:
        candidates = member_candidates
        if candidates is None:
            candidates = geometry.get("member_candidates") or build_member_candidates(
                geometry
            )
        page_candidates = [
            c
            for c in candidates
            if int(c.get("page_number") or c.get("page") or 0) == int(page_number)
        ]
    if not page_candidates:
        return unresolved_member_geometry(reason="no_member_candidates")

    claimed = claimed_member_ids if claimed_member_ids is not None else set()
    text_c = _text_center(text_bbox)

    if page_leaders is None:
        page_leaders = [
            obj
            for obj in (geometry.get("objects") or [])
            if int(obj.get("page_number") or obj.get("page") or 0) == int(page_number)
            and str(obj.get("kind") or "").lower() == "leader"
        ]
    best_leader = None
    best_leader_d = 1e18
    for leader in page_leaders:
        d = distance_point_to_geometry(text_c, leader)
        if d < best_leader_d:
            best_leader_d = d
            best_leader = leader

    method = "proximity_stroke"
    query_points: List[Sequence[float]] = [text_c]
    max_d = float(max_distance_pt)
    if best_leader is not None and best_leader_d <= float(max_distance_pt):
        endpoints = best_leader.get("leader_endpoints") or {}
        tip = _leader_far_point(best_leader, text_c)
        tips: List[Sequence[float]] = []
        if tip is not None:
            tips.append(tip)
        for key in ("far_endpoint", "near_endpoint"):
            pt = endpoints.get(key)
            if pt and len(pt) >= 2:
                tips.append(pt)
        points = best_leader.get("points") or []
        if len(points) >= 2:
            tips.append(points[0])
            tips.append(points[-1])
        # Deduplicate tips
        uniq: List[Sequence[float]] = []
        for pt in tips:
            rounded = (round(float(pt[0]), 1), round(float(pt[1]), 1))
            if rounded not in {(round(float(u[0]), 1), round(float(u[1]), 1)) for u in uniq}:
                uniq.append(pt)
        if uniq:
            query_points = uniq
            max_d = float(leader_tip_radius_pt)
            method = "leader_tip_to_stroke"

    ranked: List[Tuple[float, dict]] = []
    for qp in query_points:
        ranked.extend(_rank_candidates(qp, page_candidates, max_distance=max_d))
    # Keep best distance per candidate id
    best_by_id: Dict[str, Tuple[float, dict]] = {}
    for d, cand in ranked:
        cid = str(cand.get("geometry_id") or "")
        prev = best_by_id.get(cid)
        if prev is None or d < prev[0]:
            best_by_id[cid] = (d, cand)
    ranked = sorted(best_by_id.values(), key=lambda item: (item[0], -float(item[1].get("length") or 0.0)))

    # If leader tip found nothing, fall back to text proximity.
    if not ranked and method == "leader_tip_to_stroke":
        method = "proximity_stroke"
        ranked = _rank_candidates(
            text_c, page_candidates, max_distance=float(max_distance_pt)
        )
    if not ranked:
        return unresolved_member_geometry(reason="no_stroke_in_range")

    # Optionally skip already-claimed members (OCR review allows sharing when
    # claimed_member_ids is empty/None for display-only multi-label beams).
    if claimed:
        filtered = [
            (d, c)
            for d, c in ranked
            if str(c.get("geometry_id") or "") not in claimed
        ]
        if filtered:
            ranked = filtered
        else:
            return unresolved_member_geometry(reason="member_already_claimed")

    best_d, best = ranked[0]
    if len(ranked) > 1:
        second_d = ranked[1][0]
        if abs(second_d - best_d) <= float(ambiguity_margin_pt):
            return unresolved_member_geometry(reason="ambiguous_members")

    bbox = best.get("bbox")
    if not bbox:
        return unresolved_member_geometry(reason="missing_member_bbox")

    confidence = max(0.35, min(0.95, 1.0 - best_d / max(float(max_distance_pt), 1.0)))
    return {
        "available": True,
        "geometry_id": best.get("geometry_id"),
        "type": "member_candidate",
        "role_hint": best.get("role_hint"),
        "bbox": list(bbox),
        "source_primitive_ids": list(best.get("source_primitive_ids") or []),
        "association_method": method,
        "confidence": round(confidence, 4),
        "distance": round(best_d, 3),
        "member_geometry_kind": best.get("member_geometry_kind"),
        "length": best.get("length"),
        "orientation": best.get("orientation"),
        "page_number": int(page_number),
    }


def attach_member_geometry_to_predictions(
    predictions: List[dict],
    geometry: Dict[str, Any],
    *,
    exclusive: bool = False,
) -> List[dict]:
    """Attach ``member_geometry`` metadata to each prediction (in place + return).

    By default multiple labels may share a member candidate (OCR review).
    Pass ``exclusive=True`` to claim each member for at most one label.
    """

    from collections import defaultdict

    candidates = geometry.get("member_candidates")
    if candidates is None:
        candidates = build_member_candidates(geometry)
        geometry["member_candidates"] = candidates

    cand_by_page: Dict[int, List[dict]] = defaultdict(list)
    for cand in candidates:
        cand_by_page[int(cand.get("page_number") or cand.get("page") or 0)].append(
            cand
        )
    leaders_by_page: Dict[int, List[dict]] = defaultdict(list)
    for obj in geometry.get("objects") or []:
        if str(obj.get("kind") or "").lower() == "leader":
            leaders_by_page[
                int(obj.get("page_number") or obj.get("page") or 0)
            ].append(obj)

    claimed: set = set()
    for prediction in predictions:
        page = int(prediction.get("page_number") or prediction.get("page") or 0)
        text_bbox = prediction.get("bounding_box") or prediction.get("bbox")
        # Preserve existing text bbox unchanged; only add parallel metadata.
        member = associate_text_to_member_candidate(
            text_bbox=text_bbox,
            page_number=page,
            geometry=geometry,
            page_candidates=cand_by_page.get(page) or [],
            page_leaders=leaders_by_page.get(page) or [],
            claimed_member_ids=claimed if exclusive else None,
        )
        prediction["member_geometry"] = member
        if exclusive and member.get("available") and member.get("geometry_id"):
            claimed.add(str(member["geometry_id"]))
    return predictions


def ensure_member_candidates_on_geometry(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Idempotently attach member_candidates list onto a geometry document dict."""

    if geometry.get("member_candidates") is None:
        geometry["member_candidates"] = build_member_candidates(geometry)
    return geometry
