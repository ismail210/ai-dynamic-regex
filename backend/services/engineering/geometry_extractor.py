"""
Geometry Extraction
===================

Extracts vector drawing primitives from PDF pages using PyMuPDF drawings
and derives engineering-oriented geometry attributes.

Inputs
------
pdf_path : path to a PDF file
document_structure : optional rich parse from ``pdf_parser.extract_document_structure``
    (used to attach nearby text as dimension/label hints)

Outputs
-------
JSON-serializable dict::

    {
      "geometry_id_prefix": "geom",
      "objects": [ GeometryObject, ... ],
      "counts_by_kind": {...},
      "page_summaries": [...]
    }

Each geometry object includes: id, kind, bbox, length, width, area, center,
orientation, page_number, points, and optional metadata.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import fitz

from services.engineering.drawing_scale import (
    association_radius_pdf_points,
    detect_drawing_scale,
    detect_page_scales,
    real_inches_from_pdf_points,
    resolve_page_scale,
)
from services.engineering.geometry_normalizer import merge_collinear_fragments
from services.engineering.models import GeometryKind

_DIGIT_RE = re.compile(r"\d+(\.\d+)?")
_BARE_LOAD_RE = re.compile(r"^\s*\d+(\.\d+)?\s*K\s*$", re.I)
_MEMBER_TOKEN_RE = re.compile(
    r"^((?:W|WT|HSS|C|MC)\d+(?:X\d+(?:X[\d/]+)?)?|L\d+X\d+X[\d/]+)",
    re.I,
)


def _drawing_bbox_area(item: dict) -> float:
    """Raw PyMuPDF drawing bbox area — the ORIGINAL (defective) cap sort key.

    Axis-aligned lines have zero width or zero height, so this is
    ``0.0`` for them, which makes them the first entities dropped once a
    page exceeds the dense-page cap. See
    docs/geometry_graph_audit/03_geometry_audit.md §7. Kept as its own
    function (rather than folded into ``_drawing_significance``) so the
    A/B diagnostic in ``extract_geometry`` can compare both strategies.
    """

    rect = item.get("rect")
    if rect is None:
        return 0.0
    return abs(float(rect.width) * float(rect.height))


def _drawing_significance(item: dict) -> float:
    """Corrected dense-page cap sort key: ``max(area, perimeter)``.

    A zero-area axis-aligned line still has a nonzero perimeter
    (``2 * length``), so a long orthogonal structural line now outranks a
    small zero-length hatch fragment instead of tying with it at zero.
    Large filled regions still rank highest via ``area``. Kept as the
    ``length_aware`` A/B strategy. Production default is
    ``structural_first`` (see ``_structural_keep_score``).
    """

    rect = item.get("rect")
    if rect is None:
        return 0.0
    width = abs(float(rect.width))
    height = abs(float(rect.height))
    return max(width * height, 2.0 * (width + height))


def _drawing_wh(item: dict) -> tuple[float, float]:
    rect = item.get("rect")
    if rect is None:
        return 0.0, 0.0
    return abs(float(rect.width)), abs(float(rect.height))


def _is_tiny_noise_drawing(item: dict) -> bool:
    width, height = _drawing_wh(item)
    return max(width, height) < 3.0


def _is_page_frame_drawing(item: dict, page_width: float, page_height: float) -> bool:
    """True for sheet-sized boxes that consume cap slots but are not members."""

    if page_width <= 0 or page_height <= 0:
        return False
    width, height = _drawing_wh(item)
    return width >= 0.40 * page_width and height >= 0.40 * page_height


def _structural_keep_score(item: dict) -> float:
    """Prefer long thin strokes over large fat fills when the cap must drop paths.

    Phase 1: ``length_aware`` (max area, perimeter) still ranked page-sized
    rectangles above beams, so the 250 survivors on ST p8 / K1200 p22 were
    dominated by furniture, not members.
    """

    width, height = _drawing_wh(item)
    min_d, max_d = min(width, height), max(width, height)
    if max_d < 3.0:
        return -1e9
    thin = min_d <= 12.0 or (max_d > 1e-6 and min_d / max_d <= 0.08)
    if thin:
        return 1_000_000.0 + max_d
    if max_d <= 160.0:
        return 10_000.0 + max_d
    return max_d - 5.0 * min_d


def _gid(page_number: int, ordinal: int, bbox: Sequence[float], kind: str) -> str:
    """Deterministic geometry ID derived from stable extraction facts.

    Two runs over the same PDF produce identical IDs (PyMuPDF's
    ``get_drawings()`` order is stable for a given file), which lets
    downstream graph/diagnostic artifacts be byte-for-byte reproducible.
    Previously this used ``uuid.uuid4()``, which made every extraction of
    the same document produce different IDs.
    """

    seed = "|".join(
        [
            str(page_number),
            str(ordinal),
            kind,
            ",".join(f"{v:.2f}" for v in bbox),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"geom_{digest}"


def _round(values: Sequence[float], nd: int = 2) -> List[float]:
    return [round(float(v), nd) for v in values]


def _bbox_from_points(points: Sequence[Sequence[float]]) -> List[float]:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return _round([min(xs), min(ys), max(xs), max(ys)])


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


def _attach_nearest_objects(
    objects: List[Dict[str, Any]],
    *,
    cell_size: float = 180.0,
    limit: int = 5,
) -> None:
    """Attach bounded spatial neighbors without an all-pairs scan."""

    grid: Dict[tuple[int, int, int], List[Dict[str, Any]]] = {}
    for obj in objects:
        center = obj.get("center") or [0.0, 0.0]
        key = (
            int(obj.get("page_number") or 0),
            int(float(center[0]) // cell_size),
            int(float(center[1]) // cell_size),
        )
        grid.setdefault(key, []).append(obj)

    for obj in objects:
        center = obj.get("center") or [0.0, 0.0]
        page = int(obj.get("page_number") or 0)
        gx = int(float(center[0]) // cell_size)
        gy = int(float(center[1]) // cell_size)
        candidates: List[tuple[float, Dict[str, Any]]] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in grid.get((page, gx + dx, gy + dy), ()):
                    if other is obj:
                        continue
                    other_center = other.get("center") or [0.0, 0.0]
                    distance = math.hypot(
                        float(center[0]) - float(other_center[0]),
                        float(center[1]) - float(other_center[1]),
                    )
                    candidates.append((distance, other))
        candidates.sort(key=lambda item: item[0])
        obj["nearest_objects"] = [
            {
                "geometry_id": other.get("geometry_id"),
                "geometry_type": other.get("geometry_type")
                or other.get("kind"),
                "distance": round(distance, 3),
            }
            for distance, other in candidates[:limit]
        ]


def _classify_path(items: List[dict], rect: Optional[fitz.Rect]) -> GeometryKind:
    """Heuristic classification of a drawing path into geometry kinds."""

    if not items:
        return GeometryKind.UNKNOWN

    types = [str(it.get("type") or "").lower() for it in items]
    has_curve = any(t in {"c", "curve", "quad", "v"} or "curve" in t for t in types)
    has_line = any(t in {"l", "line"} or t.startswith("l") for t in types)
    has_re = any(t in {"re", "rect", "rectangle"} for t in types)

    # Circle / arc heuristics from closed curved paths with near-square bbox
    if rect is not None:
        w = abs(float(rect.width))
        h = abs(float(rect.height))
        if has_curve and w > 0 and h > 0:
            ratio = max(w, h) / max(min(w, h), 1e-6)
            if ratio < 1.15 and abs(w - h) < max(2.0, 0.08 * max(w, h)):
                return GeometryKind.CIRCLE
            return GeometryKind.ARC if not _is_closed(items) else GeometryKind.CURVE

    if has_re and not has_curve:
        return GeometryKind.RECTANGLE
    if has_curve:
        return GeometryKind.CURVE
    if has_line and len(items) > 2:
        return GeometryKind.POLYLINE
    if has_line:
        return GeometryKind.LINE
    return GeometryKind.PATH


def _is_closed(items: List[dict]) -> bool:
    for it in items:
        if it.get("closePath") or it.get("close"):
            return True
        if str(it.get("type") or "").lower() in {"h", "close"}:
            return True
    return False


def _points_from_items(items: List[dict]) -> List[List[float]]:
    points: List[List[float]] = []
    for it in items:
        for key in ("p1", "p2", "p3", "p4", "to", "point"):
            pt = it.get(key)
            if pt is not None and len(pt) >= 2:
                points.append([float(pt[0]), float(pt[1])])
        pts = it.get("points")
        if isinstance(pts, (list, tuple)):
            for pt in pts:
                if pt is not None and len(pt) >= 2:
                    points.append([float(pt[0]), float(pt[1])])
    return points


def _looks_like_leader(kind: GeometryKind, length: float, bbox: List[float]) -> bool:
    if kind not in {GeometryKind.LINE, GeometryKind.POLYLINE}:
        return False
    w = abs(bbox[2] - bbox[0])
    h = abs(bbox[3] - bbox[1])
    # Short callout stubs only. Framing member strokes are typically longer;
    # classifying up to 180pt as leaders previously starved member retention.
    return 8.0 <= length <= 72.0 and min(w, h) < 24.0


def _looks_like_dimension(kind: GeometryKind, length: float, nearby_text: str) -> bool:
    if kind not in {GeometryKind.LINE, GeometryKind.POLYLINE, GeometryKind.PATH}:
        return False
    if length < 12.0:
        return False
    # Numeric callouts near the stroke strongly suggest a dimension
    return bool(_DIGIT_RE.search(nearby_text or ""))


def _strip_digits(text: str) -> str:
    return _DIGIT_RE.sub("", text or "")


def _member_designation_token(text: str) -> str:
    """Extract a structural designation token from an annotation line, if present."""
    t = (text or "").strip()
    if not t or _BARE_LOAD_RE.match(t):
        return ""
    m = _MEMBER_TOKEN_RE.match(t)
    if not m:
        return ""
    return re.sub(r"\s+", "", m.group(1).upper())


def identify_own_label_lines(
    lines: Sequence[Dict[str, Any]],
    *,
    label_bbox: Sequence[float],
    label_text: str,
    page_number: int,
) -> List[Dict[str, Any]]:
    """Mark document lines that belong to the candidate member annotation.

    Ownership is demonstrated by:
    1. line text contains the designation token, or
    2. label center lies inside the line bbox AND the line frames the label bbox.

    Bare load/reaction callouts (e.g. ``17K``) are never treated as own-label.
    Ported from the approved E3 shadow contract — proximity alone is not ownership.
    """
    own: List[Dict[str, Any]] = []
    label_norm = re.sub(r"\s+", "", (label_text or "").upper())
    cx = (float(label_bbox[0]) + float(label_bbox[2])) / 2.0
    cy = (float(label_bbox[1]) + float(label_bbox[3])) / 2.0
    for line in lines:
        if int(line.get("page_number") or 0) != page_number:
            continue
        lb = line.get("bbox")
        if not lb or len(lb) < 4:
            continue
        text = str(line.get("text") or "")
        text_norm = re.sub(r"\s+", "", text.upper())
        if _BARE_LOAD_RE.match(text.strip()):
            continue
        text_match = bool(label_norm) and label_norm in text_norm
        center_in_line = (
            float(lb[0]) <= cx <= float(lb[2]) and float(lb[1]) <= cy <= float(lb[3])
        )
        gold_inside = (
            float(lb[0]) <= float(label_bbox[0]) + 1.0
            and float(lb[1]) <= float(label_bbox[1]) + 1.0
            and float(lb[2]) >= float(label_bbox[2]) - 1.0
            and float(lb[3]) >= float(label_bbox[3]) - 1.0
        )
        if text_match or (center_in_line and (text_match or gold_inside)):
            own.append(line)
        elif gold_inside and label_norm:
            if label_norm[:4] in text_norm or label_norm in text_norm:
                own.append(line)
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for line in own:
        if id(line) in seen:
            continue
        seen.add(id(line))
        uniq.append(line)
    return uniq


def _nearby_text_for_dimension(
    *,
    nearby_text: str,
    nearby_line: Optional[Dict[str, Any]],
    page_number: int,
    document_structure: Optional[dict],
) -> str:
    """Strip digits from nearby text only when own-label ownership is proven.

    If ownership cannot be established, return ``nearby_text`` unchanged.
    """
    text = nearby_text or ""
    if not text or nearby_line is None or not document_structure:
        return text
    token = _member_designation_token(text)
    if not token:
        return text
    lb = nearby_line.get("bbox")
    if not lb or len(lb) < 4:
        return text
    lines = document_structure.get("lines") or []
    own = identify_own_label_lines(
        lines,
        label_bbox=lb,
        label_text=token,
        page_number=page_number,
    )
    own_ids = {id(x) for x in own}
    if id(nearby_line) in own_ids or any(
        str(o.get("text") or "") == text for o in own
    ):
        return _strip_digits(text)
    return text


def _nearby_text_and_line(
    center: List[float],
    page_number: int,
    document_structure: Optional[dict],
    radius: float = 48.0,
    line_grid: Optional[Dict[tuple[int, int], List[dict]]] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    if not document_structure:
        return "", None
    best = ""
    best_line: Optional[Dict[str, Any]] = None
    best_d = radius
    if line_grid is not None:
        cx = int(center[0] // radius)
        cy = int(center[1] // radius)
        lines = [
            line
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for line in line_grid.get((cx + dx, cy + dy), [])
        ]
    else:
        lines = document_structure.get("lines") or []
    for line in lines:
        if int(line.get("page_number") or 0) != page_number:
            continue
        c = line.get("center") or [0, 0]
        d = math.hypot(float(c[0]) - center[0], float(c[1]) - center[1])
        if d < best_d:
            best_d = d
            best = str(line.get("text") or "")
            best_line = line
    return best, best_line


def _nearby_text(
    center: List[float],
    page_number: int,
    document_structure: Optional[dict],
    radius: float = 48.0,
    line_grid: Optional[Dict[tuple[int, int], List[dict]]] = None,
) -> str:
    text, _line = _nearby_text_and_line(
        center,
        page_number,
        document_structure,
        radius=radius,
        line_grid=line_grid,
    )
    return text


# Framing plans are dense; 250 starved member strokes, but 1200 made Burrville
# Analyze hit the 600s multimodal timeout (~30k objects + graph). 450 keeps
# more long members than 250 while staying interactive.
_DENSE_PAGE_CAP = 450
# Within the cap, prefer strokes at least this long (PDF points) before filling
# remaining slots with short callouts/leaders.
_STRUCTURAL_MIN_SPAN_PT = 80.0
_DENSE_PAGE_CAP_STRATEGIES = {
    "legacy_area": _drawing_bbox_area,
    "length_aware": _drawing_significance,
    "structural_first": _structural_keep_score,
}


def _select_under_dense_cap(
    drawings: List[dict],
    *,
    page_width: float,
    page_height: float,
    cap: int,
    strategy: str,
) -> List[dict]:
    """Apply the dense-page retention policy for one page's drawings."""

    if strategy == "structural_first":
        pool = [
            item
            for item in drawings
            if not _is_tiny_noise_drawing(item)
            and not _is_page_frame_drawing(item, page_width, page_height)
        ]
        scored = sorted(pool, key=_structural_keep_score, reverse=True)
        long_strokes = [
            item
            for item in scored
            if max(_drawing_wh(item)) >= _STRUCTURAL_MIN_SPAN_PT
        ]
        short_strokes = [
            item
            for item in scored
            if max(_drawing_wh(item)) < _STRUCTURAL_MIN_SPAN_PT
        ]
        # Prefer member-scale strokes first; only then fill with short callouts.
        kept = long_strokes[:cap]
        if len(kept) < cap:
            kept.extend(short_strokes[: cap - len(kept)])
        return kept

    active_sort_key = _DENSE_PAGE_CAP_STRATEGIES[strategy]
    return sorted(drawings, key=active_sort_key, reverse=True)[:cap]



def _local_page_scale(
    document_structure: Optional[dict],
    page_number: int,
    page_scales: Dict[int, Any],
) -> tuple[Any, Dict[str, Any]]:
    resolved = resolve_page_scale(
        document_structure, page_number, page_scales=page_scales
    )
    if resolved.get("scale_reason") == "page_scale":
        return page_scales.get(int(page_number)), resolved
    return None, resolved


def extract_geometry(
    pdf_path: str,
    document_structure: Optional[dict] = None,
    *,
    dense_page_cap_strategy: str = "structural_first",
) -> Dict[str, Any]:
    """Extract geometry objects from all pages of ``pdf_path``.

    ``dense_page_cap_strategy`` controls which sort key the dense-page
    cap (``_DENSE_PAGE_CAP``) uses to decide what to keep. Production
    default is ``"structural_first"``: drop page-frame boxes and specks,
    then keep long thin strokes. ``"length_aware"`` is the prior default
    (perimeter vs area). Pass ``"legacy_area"`` only for A/B comparison.
    """

    if dense_page_cap_strategy not in _DENSE_PAGE_CAP_STRATEGIES:
        raise ValueError(
            "dense_page_cap_strategy must be one of "
            f"{sorted(_DENSE_PAGE_CAP_STRATEGIES)}, got {dense_page_cap_strategy!r}"
        )

    path = Path(pdf_path)
    objects: List[dict] = []
    page_summaries: List[dict] = []
    counts: Dict[str, int] = {}
    drawing_scale = detect_drawing_scale(document_structure)
    page_scales = detect_page_scales(document_structure)
    active_pages = {
        int(token.get("page") or token.get("page_number") or 0)
        for token in (document_structure or {}).get("engineering_tokens") or []
    }
    skipped_pages: List[dict] = []

    with fitz.open(str(path)) as doc:
        from services.pdf_pages import iter_pdf_pages

        for page_index, page in iter_pdf_pages(doc, skipped=skipped_pages):
            page_number = page_index + 1
            if active_pages and page_number not in active_pages:
                page_scale, scale_meta = _local_page_scale(
                    document_structure, page_number, page_scales
                )
                page_summaries.append(
                    {
                        "page_number": page_number,
                        "geometry_count": 0,
                        "drawing_count": 0,
                        "processed_drawing_count": 0,
                        "skipped_without_engineering_tokens": True,
                        "scale_value": page_scale.raw if page_scale else None,
                        "scale_source": (
                            page_scale.source
                            if page_scale
                            else scale_meta.get("scale_source")
                        ),
                        "is_nts": scale_meta.get("is_nts"),
                        "scale_fallback": scale_meta.get("scale_fallback"),
                        "scale_reason": scale_meta.get("scale_reason"),
                        "association_radius_pdf_points": association_radius_pdf_points(
                            page_scale
                        ),
                    }
                )
                continue
            page_scale, scale_meta = _local_page_scale(
                document_structure, page_number, page_scales
            )
            nearby_radius = association_radius_pdf_points(page_scale) * (48.0 / 160.0)
            nearby_radius = max(24.0, min(96.0, nearby_radius))
            line_grid: Dict[tuple[int, int], List[dict]] = {}
            for line in (document_structure or {}).get("lines") or []:
                if int(line.get("page_number") or 0) != page_number:
                    continue
                line_center = line.get("center") or [0, 0]
                key = (
                    int(float(line_center[0]) // nearby_radius),
                    int(float(line_center[1]) // nearby_radius),
                )
                line_grid.setdefault(key, []).append(line)
            page_count_before = len(objects)
            try:
                drawings = page.get_drawings() or []
            except Exception as exc:
                skipped_pages.append(
                    {
                        "page_index": page_index,
                        "page_number": page_number,
                        "error": f"get_drawings failed: {type(exc).__name__}: {exc}",
                    }
                )
                page_summaries.append(
                    {
                        "page_number": page_number,
                        "geometry_count": 0,
                        "drawing_count": 0,
                        "processed_drawing_count": 0,
                        "unreadable": True,
                        "error": str(exc),
                    }
                )
                continue
            raw_drawing_count = len(drawings)
            zero_area_path_count = sum(
                1 for item in drawings if _drawing_bbox_area(item) == 0.0
            )
            # Dense CAD PDFs can contain tens of thousands of tiny hatch paths.
            # Keep the most structurally significant paths so geometry and graph
            # construction remain bounded and interactive.
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            drawings_excluded_tiny = sum(
                1 for item in drawings if _is_tiny_noise_drawing(item)
            )
            drawings_excluded_page_frame = sum(
                1 for item in drawings if _is_page_frame_drawing(item, page_width, page_height)
            )
            drawing_cap_applied = raw_drawing_count > _DENSE_PAGE_CAP
            cap_strategy_agreement: Optional[dict] = None
            if drawing_cap_applied:
                active_sort_key = _DENSE_PAGE_CAP_STRATEGIES[dense_page_cap_strategy]
                legacy_kept_ids = {
                    id(item)
                    for item in sorted(
                        drawings, key=_drawing_bbox_area, reverse=True
                    )[:_DENSE_PAGE_CAP]
                }
                length_aware_kept_ids = {
                    id(item)
                    for item in sorted(
                        drawings, key=_drawing_significance, reverse=True
                    )[:_DENSE_PAGE_CAP]
                }
                zero_area_dropped_by_legacy = sum(
                    1
                    for item in drawings
                    if id(item) not in legacy_kept_ids
                    and _drawing_bbox_area(item) == 0.0
                )
                zero_area_dropped_by_length_aware = sum(
                    1
                    for item in drawings
                    if id(item) not in length_aware_kept_ids
                    and _drawing_bbox_area(item) == 0.0
                )
                cap_strategy_agreement = {
                    "legacy_area_kept_count": len(legacy_kept_ids),
                    "length_aware_kept_count": len(length_aware_kept_ids),
                    "strategies_agree_count": len(
                        legacy_kept_ids & length_aware_kept_ids
                    ),
                    "zero_area_paths_dropped_by_legacy_area": zero_area_dropped_by_legacy,
                    "zero_area_paths_dropped_by_length_aware": zero_area_dropped_by_length_aware,
                }
                if dense_page_cap_strategy == "structural_first":
                    drawings = _select_under_dense_cap(
                        drawings,
                        page_width=page_width,
                        page_height=page_height,
                        cap=_DENSE_PAGE_CAP,
                        strategy="structural_first",
                    )
                else:
                    drawings = sorted(
                        drawings, key=active_sort_key, reverse=True
                    )[:_DENSE_PAGE_CAP]
            drawings_dropped_by_cap = raw_drawing_count - len(drawings)
            dropped_degenerate_count = 0

            for drawing in drawings:
                items = list(drawing.get("items") or [])
                rect = drawing.get("rect")

                # Normalize PyMuPDF drawing item tuples: ("l", p1, p2), ("c", ...), ("re", rect), …
                points: List[List[float]] = []
                item_dicts: List[dict] = []
                for it in items:
                    if not isinstance(it, (list, tuple)) or not it:
                        continue
                    kind = str(it[0]).lower()
                    entry: Dict[str, Any] = {"type": kind}
                    if kind == "re" and len(it) > 1:
                        r = it[1]
                        entry["rect"] = r
                        try:
                            points.extend(
                                [
                                    [float(r.x0), float(r.y0)],
                                    [float(r.x1), float(r.y0)],
                                    [float(r.x1), float(r.y1)],
                                    [float(r.x0), float(r.y1)],
                                ]
                            )
                        except Exception:
                            continue
                    else:
                        for idx, key in enumerate(("p1", "p2", "p3", "p4"), start=1):
                            if len(it) > idx and it[idx] is not None:
                                pt = it[idx]
                                if hasattr(pt, "x") and hasattr(pt, "y"):
                                    entry[key] = [float(pt.x), float(pt.y)]
                                    points.append([float(pt.x), float(pt.y)])
                                elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                    try:
                                        entry[key] = [float(pt[0]), float(pt[1])]
                                        points.append([float(pt[0]), float(pt[1])])
                                    except (TypeError, ValueError):
                                        continue
                    item_dicts.append(entry)

                if rect is not None:
                    bbox = _round([rect.x0, rect.y0, rect.x1, rect.y1])
                elif points:
                    bbox = _bbox_from_points(points)
                else:
                    dropped_degenerate_count += 1
                    continue

                kind = _classify_path(item_dicts, rect)
                length = _length_of_segments(points) if len(points) >= 2 else round(
                    math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]), 3
                )
                width = round(abs(bbox[2] - bbox[0]), 3)
                height = round(abs(bbox[3] - bbox[1]), 3)
                area = round(width * height, 3)
                center = [round((bbox[0] + bbox[2]) / 2.0, 2), round((bbox[1] + bbox[3]) / 2.0, 2)]
                orientation = (
                    _orientation_deg(points[0], points[-1]) if len(points) >= 2 else 0.0
                )
                nearby, nearby_line = _nearby_text_and_line(
                    center,
                    page_number,
                    document_structure,
                    radius=nearby_radius,
                    line_grid=line_grid,
                )
                nearby_for_dimension = _nearby_text_for_dimension(
                    nearby_text=nearby,
                    nearby_line=nearby_line,
                    page_number=page_number,
                    document_structure=document_structure,
                )

                if _looks_like_leader(kind, length, bbox):
                    kind = GeometryKind.LEADER
                elif _looks_like_dimension(kind, length, nearby_for_dimension):
                    kind = GeometryKind.DIMENSION

                leader_endpoints: Optional[Dict[str, List[float]]] = None
                if kind == GeometryKind.LEADER and len(points) >= 2:
                    near_pt = points[0]
                    far_pt = points[-1]
                    leader_endpoints = {
                        "near_endpoint": [round(near_pt[0], 2), round(near_pt[1], 2)],
                        "far_endpoint": [round(far_pt[0], 2), round(far_pt[1], 2)],
                    }
                elif kind == GeometryKind.LEADER:
                    x0, y0, x1, y1 = bbox
                    corners = [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]
                    far = max(corners, key=lambda c: math.hypot(c[0] - center[0], c[1] - center[1]))
                    near = min(corners, key=lambda c: math.hypot(c[0] - center[0], c[1] - center[1]))
                    leader_endpoints = {
                        "near_endpoint": [round(near[0], 2), round(near[1], 2)],
                        "far_endpoint": [round(far[0], 2), round(far[1], 2)],
                    }

                # Blocks / symbols: small closed shapes
                if kind in {GeometryKind.RECTANGLE, GeometryKind.CIRCLE} and area < 400:
                    kind = GeometryKind.SYMBOL

                ordinal = len(objects) - page_count_before
                obj = {
                    "geometry_id": _gid(page_number, ordinal, bbox, kind.value),
                    "kind": kind.value,
                    "geometry_type": kind.value,
                    "page_number": page_number,
                    "page": page_number,
                    "bbox": bbox,
                    "coordinates": bbox,
                    "center": center,
                    "length": length,
                    "width": width,
                    "height": height,
                    "area": area,
                    "aspect_ratio": round(
                        width / height if height else width, 4
                    ),
                    "orientation": orientation,
                    "points": [[round(p[0], 2), round(p[1], 2)] for p in points[:64]],
                    "stroke_opacity": drawing.get("stroke_opacity"),
                    "fill_opacity": drawing.get("fill_opacity"),
                    "color": drawing.get("color"),
                    "fill": drawing.get("fill"),
                    "nearby_text": nearby[:120],
                    "layer": None,
                    "drawing_layer": None,
                    "block_name": None,
                    "length_real_inches": real_inches_from_pdf_points(
                        length, page_scale
                    ),
                }
                if leader_endpoints:
                    obj["leader_endpoints"] = leader_endpoints
                objects.append(obj)
                counts[kind.value] = counts.get(kind.value, 0) + 1

            page_summaries.append(
                {
                    "page_number": page_number,
                    "geometry_count": len(objects) - page_count_before,
                    "drawing_count": raw_drawing_count,
                    "processed_drawing_count": len(drawings),
                    "drawing_cap_applied": drawing_cap_applied,
                    # --- diagnostics added for the ML-association Phase 1
                    # observability work (docs/ml_association_phase/) ---
                    "raw_drawing_count": raw_drawing_count,
                    "retained_drawing_count": len(drawings),
                    "drawings_dropped_by_cap": drawings_dropped_by_cap,
                    "drawing_cap_threshold": _DENSE_PAGE_CAP,
                    "drawings_excluded_tiny": drawings_excluded_tiny,
                    "drawings_excluded_page_frame": drawings_excluded_page_frame,
                    "zero_area_path_count": zero_area_path_count,
                    "dropped_degenerate_count": dropped_degenerate_count,
                    "dense_page_cap_strategy": dense_page_cap_strategy,
                    "cap_strategy_agreement": cap_strategy_agreement,
                    "page_rotation": int(page.rotation or 0),
                    "scale_value": page_scale.raw if page_scale else None,
                    "scale_source": (
                        page_scale.source if page_scale else scale_meta.get("scale_source")
                    ),
                    "scale_confidence": (
                        page_scale.confidence if page_scale else None
                    ),
                    "is_nts": scale_meta.get("is_nts"),
                    "scale_fallback": scale_meta.get("scale_fallback"),
                    "scale_reason": scale_meta.get("scale_reason"),
                    "association_radius_pdf_points": association_radius_pdf_points(
                        page_scale
                    ),
                }
            )

        for item in skipped_pages:
            page_summaries.append(
                {
                    "page_number": item["page_number"],
                    "geometry_count": 0,
                    "drawing_count": 0,
                    "processed_drawing_count": 0,
                    "unreadable": True,
                    "error": item.get("error"),
                }
            )
        page_summaries.sort(key=lambda item: int(item.get("page_number") or 0))

    merged_objects: List[dict] = []
    fragment_stats = {
        "input_count": 0,
        "output_count": 0,
        "clusters_merged": 0,
        "fragments_consumed": 0,
        "merge_links": 0,
        "fragment_gap_pdf_points": None,
    }
    objects_by_page: Dict[int, List[dict]] = defaultdict(list)
    for obj in objects:
        objects_by_page[int(obj.get("page_number") or obj.get("page") or 0)].append(obj)
    for page_number_key, group in objects_by_page.items():
        page_scale, _scale_meta = _local_page_scale(
            document_structure, page_number_key, page_scales
        )
        part, stats = merge_collinear_fragments(group, scale=page_scale)
        merged_objects.extend(part)
        fragment_stats["input_count"] += stats["input_count"]
        fragment_stats["output_count"] += stats["output_count"]
        fragment_stats["clusters_merged"] += stats["clusters_merged"]
        fragment_stats["fragments_consumed"] += stats["fragments_consumed"]
        fragment_stats["merge_links"] += stats["merge_links"]
        fragment_stats["fragment_gap_pdf_points"] = stats["fragment_gap_pdf_points"]
    objects = merged_objects
    counts = {}
    for obj in objects:
        kind = str(obj.get("kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    _attach_nearest_objects(objects)
    scale_payload = drawing_scale.to_dict() if drawing_scale else None
    return {
        "source_file": path.name,
        "geometry_count": len(objects),
        "counts_by_kind": counts,
        "page_summaries": page_summaries,
        "skipped_pages": skipped_pages,
        "objects": objects,
        "units": "pdf_points",
        "scale": scale_payload,
        "scale_value": drawing_scale.raw if drawing_scale else None,
        "scale_source": drawing_scale.source if drawing_scale else None,
        "scale_confidence": drawing_scale.confidence if drawing_scale else None,
        "association_radius_pdf_points": association_radius_pdf_points(
            drawing_scale
        ),
        "page_scales": {
            str(page): scale.to_dict() for page, scale in sorted(page_scales.items())
        },
        "fragment_merge": fragment_stats,
    }
