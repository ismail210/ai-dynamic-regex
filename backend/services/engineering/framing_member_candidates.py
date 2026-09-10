"""Phase C -- deterministic PHYSICAL MEMBER candidate detection (shadow only).

Geometry audit (7 real projects, see the Phase C report): PDF vector geometry
on framing plans is *sparse and largely unlabelled* -- roughly one candidate
beam line per 2-4 printed section labels, ``layer`` is ``None`` everywhere,
and ``nearby_text`` is empty on ~95% of candidate lines. So this module makes
no claim to reconstruct every member. It builds the honest subset that the
extracted geometry supports, with per-candidate provenance and an explicit
existence confidence, and it is wired ONLY into the shadow path
(``member_reconstruction``) -- it never touches production predictions,
candidates, ranking or takeoff.

Contract: ``PhysicalMemberCandidate`` (a plain dict; see ``_candidate``).
Existence and section assignment are kept strictly separate -- this module
only decides *does a physical member plausibly exist here*.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --- status / evidence vocab -------------------------------------------------
STATUS_CANDIDATE = "CANDIDATE"
STATUS_REJECTED = "REJECTED"

FAMILY_W = "W"

# Geometry kinds that are never a structural member.
_NOISE_KINDS = frozenset({"leader", "dimension", "symbol", "arc", "circle", "text", "text_line"})
_MEMBER_KINDS = frozenset({"line", "polyline"})

# Orthogonal tolerance (deg) -- framing on these plans is drawn on a grid;
# diagonal lines this far off an axis are braces, not W beams (handled later).
_ORTHO_TOL_DEG = 14.0
# A line longer than this share of the page's short side is a grid line or a
# match line, not one framing member.
_GRID_LENGTH_PAGE_FRACTION = 0.82
# Absolute PDF-point bounds for a plausible single beam segment on a plan at
# typical structural scales (1/8"=1'-0" .. 1/4"=1'-0").
_MIN_MEMBER_LEN = 42.0
_MAX_MEMBER_LEN = 1500.0
# Merge two nearly-collinear segments whose facing endpoints are within this.
_MERGE_GAP = 14.0
_MERGE_PERP = 3.5
_MERGE_ANGLE_TOL = 6.0
# A candidate whose nearest neighbours are mostly dimension lines is itself a
# dimension/witness line.
_DIMENSION_NEIGHBOUR_FRAC = 0.6


def _pts(obj: Dict[str, Any]) -> List[Sequence[float]]:
    pts = obj.get("points") or obj.get("coordinates") or obj.get("centerline") or []
    return [p for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]


def _endpoints(obj: Dict[str, Any]) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    pts = _pts(obj)
    if len(pts) < 2:
        return None
    return (float(pts[0][0]), float(pts[0][1])), (float(pts[-1][0]), float(pts[-1][1]))


def _seg_len(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))


def _orientation(a: Sequence[float], b: Sequence[float]) -> float:
    deg = math.degrees(math.atan2(float(b[1]) - float(a[1]), float(b[0]) - float(a[0])))
    return deg % 180.0


def _axis_offset(orientation: float) -> float:
    """Distance in degrees from the nearest of 0/90/180."""
    o = orientation % 180.0
    return min(o, abs(90.0 - o), abs(180.0 - o))


def _is_orthogonal(orientation: float) -> bool:
    return _axis_offset(orientation) <= _ORTHO_TOL_DEG


def _page_dims(document: Dict[str, Any], page: int) -> Tuple[float, float]:
    for meta in document.get("pages") or []:
        if int(meta.get("page_number") or 0) == page:
            return float(meta.get("width") or 0.0), float(meta.get("height") or 0.0)
    return 0.0, 0.0


# --- eligibility -----------------------------------------------------------
def framing_pages(drawing_intelligence: Optional[Dict[str, Any]]) -> Dict[int, str]:
    """The pages a member detector is allowed to look at, from the deterministic
    Drawing Intelligence Profile page categories -- NOT from LLM prose.

    Eligible: roof/floor framing, column plans, bracing, and pages classified
    as framing by structural content. Excluded: notes/legend, schedules,
    details, elevations/sections, index, foundation-only, perspectives,
    unclassified, unreadable.
    """

    eligible = {
        "roof_framing", "floor_framing", "column_plan", "bracing",
        "framing_plan_unlabeled",
    }
    out: Dict[int, str] = {}
    if not drawing_intelligence:
        return out
    for page_str, category in (drawing_intelligence.get("page_categories") or {}).items():
        if category in eligible:
            out[int(page_str)] = category
    return out


# --- noise rejection -----------------------------------------------------------
def _rejection_reason(
    obj: Dict[str, Any],
    endpoints: Tuple[Tuple[float, float], Tuple[float, float]],
    *,
    page_w: float,
    page_h: float,
) -> Optional[str]:
    a, b = endpoints
    length = _seg_len(a, b)
    if length < _MIN_MEMBER_LEN:
        return "too_short_noise"
    if length > _MAX_MEMBER_LEN:
        return "too_long_grid_or_matchline"
    short_side = min(page_w, page_h) or max(page_w, page_h)
    if short_side and length >= _GRID_LENGTH_PAGE_FRACTION * short_side:
        return "spans_page_grid_line"
    orientation = _orientation(a, b)
    if not _is_orthogonal(orientation):
        # keep a diagonal only if it is clearly a brace-length diagonal;
        # otherwise it is a leader/hatch/section-cut.
        return "non_orthogonal_not_a_w_member"
    # nearest-neighbour composition: mostly dimensions -> a witness line
    neighbours = obj.get("nearest_objects") or []
    if neighbours:
        dim = sum(
            1 for n in neighbours
            if (n.get("kind") or n.get("geometry_type")) in ("dimension", "leader")
        )
        if dim / len(neighbours) >= _DIMENSION_NEIGHBOUR_FRAC and len(neighbours) >= 3:
            return "dimension_or_leader_cluster"
    return None


# --- segment merging ---------------------------------------------------------
def _try_merge(
    seg_a: Tuple[Tuple[float, float], Tuple[float, float]],
    seg_b: Tuple[Tuple[float, float], Tuple[float, float]],
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Merge two collinear, near-touching segments into one chain. Refuses to
    merge across a large gap (a support / column / expansion joint)."""

    oa = _orientation(*seg_a)
    ob = _orientation(*seg_b)
    if min(abs(oa - ob), 180.0 - abs(oa - ob)) > _MERGE_ANGLE_TOL:
        return None
    pts = [seg_a[0], seg_a[1], seg_b[0], seg_b[1]]
    # order along the dominant axis
    horiz = _axis_offset(oa) < 45.0
    key = (lambda p: p[0]) if horiz else (lambda p: p[1])
    pts_sorted = sorted(pts, key=key)
    far = (pts_sorted[0], pts_sorted[-1])
    # perpendicular spread of all four points from the fitted line must be tiny
    ax, ay = far[0]
    bx, by = far[1]
    line_len = math.hypot(bx - ax, by - ay) or 1.0
    for px, py in pts:
        cross = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / line_len
        if cross > _MERGE_PERP:
            return None
    # the internal gap between the two segments (projection order)
    mid_pts = pts_sorted[1:3]
    gap = _seg_len(mid_pts[0], mid_pts[1])
    # overlapping or touching is fine; a real gap beyond the tolerance means a
    # structural break -- do not merge through it
    seg_a_len = _seg_len(*seg_a)
    seg_b_len = _seg_len(*seg_b)
    total_span = _seg_len(*far)
    if total_span > seg_a_len + seg_b_len + _MERGE_GAP:
        return None
    if gap > _MERGE_GAP and gap > 0.35 * min(seg_a_len, seg_b_len):
        return None
    return far


def _merge_segments(
    segments: List[Tuple[str, Tuple[Tuple[float, float], Tuple[float, float]]]],
) -> List[Dict[str, Any]]:
    """Greedy collinear-chain merge. Returns member chains, each keeping every
    contributing geometry id."""

    remaining = list(segments)
    chains: List[Dict[str, Any]] = []
    while remaining:
        gid, seg = remaining.pop(0)
        chain_ids = [gid]
        merged = True
        while merged:
            merged = False
            for i, (other_gid, other_seg) in enumerate(remaining):
                combined = _try_merge(seg, other_seg)
                if combined is not None:
                    seg = combined
                    chain_ids.append(other_gid)
                    remaining.pop(i)
                    merged = True
                    break
        a, b = seg
        chains.append({
            "geometry_ids": chain_ids,
            "axis_start": [round(a[0], 2), round(a[1], 2)],
            "axis_end": [round(b[0], 2), round(b[1], 2)],
            "length_pdf": round(_seg_len(a, b), 2),
            "orientation_deg": round(_orientation(a, b), 2),
            "raw_segment_count": len(chain_ids),
        })
    return chains


# --- candidate assembly ----------------------------------------------------
def _candidate(
    chain: Dict[str, Any],
    *,
    page: int,
    region_category: str,
    index: int,
    existence_confidence: float,
    existence_evidence: List[str],
) -> Dict[str, Any]:
    a = chain["axis_start"]
    b = chain["axis_end"]
    bbox = [
        min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]),
    ]
    return {
        "member_candidate_id": f"mc_p{page}_{index}",
        "page": page,
        "region_id": f"page_{page}",
        "region_category": region_category,
        "geometry_ids": chain["geometry_ids"],
        "axis_start": a,
        "axis_end": b,
        "bbox": [round(v, 2) for v in bbox],
        "length_pdf": chain["length_pdf"],
        "orientation_deg": chain["orientation_deg"],
        "raw_segment_count": chain["raw_segment_count"],
        "member_family_hint": FAMILY_W,
        # existence vs section are separate; section fields are filled later
        # by member_reconstruction, never here.
        "existence_confidence": round(existence_confidence, 3),
        "existence_evidence": existence_evidence,
        "section_candidate": None,
        "section_confidence": 0.0,
        "section_evidence": [],
        "support_start_id": None,
        "support_end_id": None,
        "grid_start": None,
        "grid_end": None,
        "repeated_cluster_id": None,
        "same_bay_cluster_id": None,
        "seed_label_id": None,
        "typ_rule_id": None,
        "graph_node_id": None,
        "status": STATUS_CANDIDATE,
        "provenance": {
            "detector": "framing_member_candidates.v1",
            "region_category": region_category,
        },
    }


def _existence_score(chain: Dict[str, Any], page_line_lengths: List[float]) -> Tuple[float, List[str]]:
    """Interpretable existence confidence from geometry alone (no section
    evidence). Positive: a beam-plausible length, orthogonal, part of a
    multi-segment chain, a length near the page's modal framing span.
    """

    evidence: List[str] = []
    score = 0.35
    length = chain["length_pdf"]
    if _MIN_MEMBER_LEN * 2 <= length <= _MAX_MEMBER_LEN * 0.7:
        score += 0.18
        evidence.append("beam_plausible_length")
    if _axis_offset(chain["orientation_deg"]) <= 4.0:
        score += 0.12
        evidence.append("axis_aligned")
    if chain["raw_segment_count"] >= 2:
        score += 0.1
        evidence.append("collinear_chain")
    # length regularity: close to the page's median candidate length == part of
    # a regular framing field
    if page_line_lengths:
        srt = sorted(page_line_lengths)
        median = srt[len(srt) // 2]
        if median and abs(length - median) <= 0.35 * median:
            score += 0.12
            evidence.append("regular_framing_span")
    return min(0.9, score), evidence


def detect_w_member_candidates(
    geometry: Dict[str, Any],
    document: Dict[str, Any],
    *,
    eligible_pages: Dict[int, str],
) -> Dict[str, Any]:
    """Return ``{"candidates": [...], "rejected": {reason: n}, "by_page": {...}}``.

    Only W-family orthogonal beam/girder candidates on eligible framing pages.
    """

    objects = geometry.get("objects") or []
    rejected: Counter = Counter()
    by_page_segments: Dict[int, List[Tuple[str, Any]]] = defaultdict(list)
    by_page_lengths: Dict[int, List[float]] = defaultdict(list)

    for obj in objects:
        page = int(obj.get("page_number") or obj.get("page") or 0)
        if page not in eligible_pages:
            continue
        kind = str(obj.get("kind") or obj.get("geometry_type") or "")
        if kind in _NOISE_KINDS:
            rejected[f"kind:{kind}"] += 1
            continue
        if kind not in _MEMBER_KINDS:
            rejected[f"kind:{kind or 'unknown'}"] += 1
            continue
        endpoints = _endpoints(obj)
        if endpoints is None:
            rejected["no_endpoints"] += 1
            continue
        page_w, page_h = _page_dims(document, page)
        reason = _rejection_reason(obj, endpoints, page_w=page_w, page_h=page_h)
        if reason:
            rejected[reason] += 1
            continue
        gid = str(obj.get("geometry_id") or obj.get("object_id") or f"g{len(by_page_segments[page])}")
        by_page_segments[page].append((gid, endpoints))
        by_page_lengths[page].append(_seg_len(*endpoints))

    candidates: List[Dict[str, Any]] = []
    by_page_counts: Dict[int, int] = {}
    for page, segments in by_page_segments.items():
        chains = _merge_segments(segments)
        for idx, chain in enumerate(chains):
            score, evidence = _existence_score(chain, by_page_lengths[page])
            candidates.append(_candidate(
                chain,
                page=page,
                region_category=eligible_pages.get(page, "framing_plan_unlabeled"),
                index=idx,
                existence_confidence=score,
                existence_evidence=evidence,
            ))
        by_page_counts[page] = len(chains)

    return {
        "candidates": candidates,
        "rejected": dict(rejected),
        "by_page": by_page_counts,
        "eligible_pages": sorted(eligible_pages),
        "raw_segments_kept": sum(len(v) for v in by_page_segments.values()),
    }
