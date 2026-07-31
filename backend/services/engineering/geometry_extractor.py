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

import math
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import fitz

from services.engineering.models import GeometryKind


def _gid() -> str:
    return f"geom_{uuid.uuid4().hex[:12]}"


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
    # Short-ish strokes that are mostly linear → potential leader
    return 8.0 <= length <= 180.0 and min(w, h) < 40.0


def _looks_like_dimension(kind: GeometryKind, length: float, nearby_text: str) -> bool:
    if kind not in {GeometryKind.LINE, GeometryKind.POLYLINE, GeometryKind.PATH}:
        return False
    if length < 12.0:
        return False
    # Numeric callouts near the stroke strongly suggest a dimension
    import re

    return bool(re.search(r"\d+(\.\d+)?", nearby_text or ""))


def _nearby_text(
    center: List[float],
    page_number: int,
    document_structure: Optional[dict],
    radius: float = 48.0,
    line_grid: Optional[Dict[tuple[int, int], List[dict]]] = None,
) -> str:
    if not document_structure:
        return ""
    best = ""
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
    return best


def extract_geometry(
    pdf_path: str,
    document_structure: Optional[dict] = None,
) -> Dict[str, Any]:
    """Extract geometry objects from all pages of ``pdf_path``."""

    path = Path(pdf_path)
    objects: List[dict] = []
    page_summaries: List[dict] = []
    counts: Dict[str, int] = {}
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
                page_summaries.append(
                    {
                        "page_number": page_number,
                        "geometry_count": 0,
                        "drawing_count": 0,
                        "processed_drawing_count": 0,
                        "skipped_without_engineering_tokens": True,
                    }
                )
                continue
            line_grid: Dict[tuple[int, int], List[dict]] = {}
            for line in (document_structure or {}).get("lines") or []:
                if int(line.get("page_number") or 0) != page_number:
                    continue
                line_center = line.get("center") or [0, 0]
                key = (
                    int(float(line_center[0]) // 48.0),
                    int(float(line_center[1]) // 48.0),
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
            # Dense CAD PDFs can contain tens of thousands of tiny hatch paths.
            # Keep the most structurally significant paths so geometry and graph
            # construction remain bounded and interactive.
            if raw_drawing_count > 250:
                def _drawing_area(item: dict) -> float:
                    rect = item.get("rect")
                    if rect is None:
                        return 0.0
                    return abs(float(rect.width) * float(rect.height))

                drawings = sorted(
                    drawings, key=_drawing_area, reverse=True
                )[:250]

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
                nearby = _nearby_text(
                    center,
                    page_number,
                    document_structure,
                    line_grid=line_grid,
                )

                if _looks_like_leader(kind, length, bbox):
                    kind = GeometryKind.LEADER
                elif _looks_like_dimension(kind, length, nearby):
                    kind = GeometryKind.DIMENSION

                # Blocks / symbols: small closed shapes
                if kind in {GeometryKind.RECTANGLE, GeometryKind.CIRCLE} and area < 400:
                    kind = GeometryKind.SYMBOL

                obj = {
                    "geometry_id": _gid(),
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
                }
                objects.append(obj)
                counts[kind.value] = counts.get(kind.value, 0) + 1

            page_summaries.append(
                {
                    "page_number": page_number,
                    "geometry_count": len(objects) - page_count_before,
                    "drawing_count": raw_drawing_count,
                    "processed_drawing_count": len(drawings),
                    "drawing_cap_applied": raw_drawing_count > len(drawings),
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

    _attach_nearest_objects(objects)
    return {
        "source_file": path.name,
        "geometry_count": len(objects),
        "counts_by_kind": counts,
        "page_summaries": page_summaries,
        "skipped_pages": skipped_pages,
        "objects": objects,
    }
