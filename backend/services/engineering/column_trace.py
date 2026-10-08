"""Column tracing pilot: one scheduled column, looked for on the framing plans.

Evidence for review only. Nothing here feeds prediction, quantities or
cross-drawing deduplication, and nothing is computed on extraction: a trace
is built on request for one schedule entry.

For the entry it keeps the schedule identity and source, the grid location
and offsets, the sections, and the schedule's own drawn extent (which level
lines its ends sit on). Then, for each level the schedule column spans, it
looks at plans whose title names that level:

* the two grid lines, found from their labelled bubbles (a grid name printed
  inside a circle, with its long axis line through the bubble centre);
* at their intersection, a column symbol (short heavy strokes) and any
  annotation whose leader line ends there (``POST UP``, ``COLUMN BELOW``);
* other text close by, listed as nearby only -- not associated.

What it does not do: a grid printed on several axes of one sheet gives
several candidate intersections, never one chosen; an offset is not applied
(plan scale is not read), so the point is the grid intersection, not the
column's position; a missing symbol is "not detected", never "absent"; two
plans showing the column do not make it one fabrication piece; the lowest
plan found is not the foundation. Start / end levels come only from the
schedule's drawn extent or from an explicit annotation.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

import fitz

from services.engineering.column_schedule import _union_boxes, column_schedule_view
from services.engineering.level_evidence import (
    _clean,
    displayed,
    level_keys,
    parse_elevation,
    plan_elevations,
    plan_names_by_page,
    plan_statements,
    plan_values,
    spot_elevations,
)
from services.engineering.page_space import convert_boxes, display_boxes
from services.engineering.view_scale import (
    PLACES,
    _normal,
    _parallel,
    grid_calibration,
    printed_view_scale,
    resolve_view_scale,
    sheet_scales,
)
from services.engineering.view_scope import COUNTS, ScopeResolver

_BUBBLE_MIN, _BUBBLE_MAX = 10.0, 90.0
_AXIS_MIN_LENGTH = 200.0      # a grid line runs across the plan, not a detail
_SYMBOL_REACH = 6.0           # a column symbol is drawn on the intersection
_SYMBOL_MAX = 40.0
_SYMBOL_MIN_WIDTH = 0.8       # heavy strokes; grid and dimension lines are hairlines
# A stroke within _SYMBOL_REACH of an offset point is evidence of that side
# only when the point is far enough from the grid crossing that the crossing's
# own search window cannot contain it. The windows separate at twice the
# reach. Half the detected mark's longest side is added so the mark itself,
# not only the search point, clears the crossing. A shorter offset is not placed.
_LEADER_REACH = 10.0
_TEXT_REACH = 18.0
_NEARBY_REACH = 60.0
_ANNOTATION_RE = re.compile(
    r"\b(?:POST|COL(?:UMN)?\.?)\s+(?:UP|DOWN|ABOVE|BELOW|OVER|UNDER)\b|\bTOP\s+OF\s+COL|\bT\.\s*O\.\s*COL|\bBEARS?\b",
    re.IGNORECASE)


_UP_RE = re.compile(r"\b(?:UP|ABOVE|OVER)\b", re.IGNORECASE)
_GRID_LABEL_RE = re.compile(r"^(?:[A-Z]{1,2}(?:\.\d+)?|\d{1,2}(?:\.\d+)?)['\"′″]*$")
_DOWN_RE = re.compile(r"\b(?:DOWN|BELOW|UNDER)\b|\bTOP\s+OF\s+COL|\bT\.\s*O\.\s*COL", re.IGNORECASE)


def _norm(name: str) -> str:
    return _clean(name).replace(" ", "").upper()


def _label_family(name: str) -> Optional[str]:
    """Printed shape of a grid label, used only to name a "toward" grid.

    Locate axes have no family field. The shape is read from the label text.
    None means the shape is not one of these, and no toward grid is guessed.
    """

    text = _norm(name).strip("'\"′″")
    if re.fullmatch(r"[A-Z]{1,2}", text):
        return "letter"
    if re.fullmatch(r"[A-Z]{1,2}\.\d+", text):
        return "letter-decimal"
    if re.fullmatch(r"\d{1,2}", text):
        return "number"
    if re.fullmatch(r"\d{1,2}\.\d+", text):
        return "number-decimal"
    if re.fullmatch(r"[A-Z]\d{1,2}", text):
        return "prefixed-" + text[0]
    return None


def _toward_grid(grid: str, beyond: List[tuple]) -> Optional[str]:
    """Nearest parallel axis on this side that is printed in ``grid``'s family.

    A nearer axis of another family is not named. No same-family axis, or an
    unrecognised label, leaves the side unnamed.
    """

    family = _label_family(grid)
    if family is None:
        return None
    same = [pair for pair in beyond if _label_family(pair[1]) == family]
    return min(same)[1] if same else None


def _symbol_span(symbol: Optional[dict]) -> float:
    box = (symbol or {}).get("bbox") or []
    if len(box) < 4:
        return 0.0
    return max(abs(float(box[2]) - float(box[0])), abs(float(box[3]) - float(box[1])))


def _reliable_offset(distance_pt: float, symbol: Optional[dict]) -> bool:
    """True when ``distance_pt`` clears twice the search reach plus half the mark."""

    return distance_pt >= 2 * _SYMBOL_REACH + 0.5 * _symbol_span(symbol)


def _window_limited(record: dict, distance_pt: float, symbol: Optional[dict]) -> dict:
    minimum = 2 * _SYMBOL_REACH + 0.5 * _symbol_span(symbol)
    return {**record, "status": "candidate", "search_window_limited": True,
            "note": (f"The offset is {distance_pt:.1f} pt from the grid crossing; a side is reliable "
                     f"only from {minimum:.1f} pt (twice the {_SYMBOL_REACH:.0f} pt search window, plus half "
                     f"the detected mark). The side is not established.")}


def _circles(drawings: List[dict]) -> List[Any]:
    """Rects of the page's circle-like paths (grid bubble candidates)."""

    return [path["rect"] for path in drawings
            if _BUBBLE_MIN <= path["rect"].width <= _BUBBLE_MAX
            and abs(path["rect"].width - path["rect"].height) <= 0.15 * path["rect"].width
            and any(item[0] == "c" for item in path["items"])]


def _bubbles(words: List[tuple], circles: List[Any], name: str) -> List[Dict[str, float]]:
    """Centres of circles that contain a word printed exactly as ``name``."""

    out = []
    for w in words:
        if _norm(w[4]) != name:
            continue
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        r = next((r for r in circles if r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1), None)
        if r is not None:
            out.append({"x": (r.x0 + r.x1) / 2, "y": (r.y0 + r.y1) / 2})
    return out


def _segments(drawings: List[dict]) -> List[tuple]:
    return [(item[1].x, item[1].y, item[2].x, item[2].y, float(path.get("width") or 0.0))
            for path in drawings for item in path["items"] if item[0] == "l"]


_ANGLE_STEP = 0.5   # degrees per angle bucket


_CELL = 100.0       # PDF points per cell of the segment-endpoint grid
_LOCAL_REACH = 60.0  # a grid line starts at its bubble


def _segment_index(segments: List[tuple]) -> tuple:
    """``(lines, near)``: total segment length per (direction, line position)
    -- angle bucket -> round(c) -> length, with ``c = n . p`` -- and the
    segments by endpoint cell. Grid lines at any angle (slanted building
    wings) are found without rescanning every segment."""

    lines: Dict[int, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    near: Dict[tuple, List[tuple]] = defaultdict(list)
    for x0, y0, x1, y1, _w in segments:
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 2.0:
            continue
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180.0
        key = round(angle / _ANGLE_STEP) % round(180 / _ANGLE_STEP)
        nx, ny = _normal(key * _ANGLE_STEP)
        lines[key][round(nx * x0 + ny * y0)] += length
        for px, py in ((x0, y0), (x1, y1)):
            near[(int(px // _CELL), int(py // _CELL))].append((x0, y0, x1, y1, key))
    return lines, near


def _axes(bubbles: List[Dict[str, float]], index: Dict[int, Dict[int, float]]) -> List[Dict[str, Any]]:
    """Distinct grid axes through the bubbles. An axis is the line ``n . p = c``
    at ``angle`` degrees (PDF space), labelled vertical / horizontal (with
    ``at`` = its x / y) or angled."""

    buckets = round(180 / _ANGLE_STEP)
    lines, near = index
    axes: List[Dict[str, Any]] = []
    for b in bubbles:
        # Directions of segments that start next to the bubble and point through its centre.
        cell = (int(b["x"] // _CELL), int(b["y"] // _CELL))
        local = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for x0, y0, x1, y1, key in near.get((cell[0] + dx, cell[1] + dy), ()):
                    if min(math.hypot(x0 - b["x"], y0 - b["y"]), math.hypot(x1 - b["x"], y1 - b["y"])) > _LOCAL_REACH:
                        continue
                    nx, ny = _normal(key * _ANGLE_STEP)
                    if abs(nx * (b["x"] - x0) + ny * (b["y"] - y0)) <= 1.5:
                        local.add(key)
        best = (0.0, None)
        for key in local:
            nx, ny = _normal(key * _ANGLE_STEP)
            c = round(nx * b["x"] + ny * b["y"])
            total = sum(lines[(key + dk) % buckets].get(c + k, 0.0) for dk in (-1, 0, 1) for k in (-1, 0, 1)
                        if (key + dk) % buckets in lines)
            if total > best[0]:
                best = (total, key)
        if best[0] < _AXIS_MIN_LENGTH:
            continue
        angle = best[1] * _ANGLE_STEP
        nx, ny = _normal(angle)
        axis: Dict[str, Any] = {"angle": angle, "c": nx * b["x"] + ny * b["y"]}
        if abs(angle - 90.0) <= 1.0:
            axis.update(orientation="vertical", at=b["x"])
        elif min(angle, 180.0 - angle) <= 1.0:
            axis.update(orientation="horizontal", at=b["y"])
        else:
            axis.update(orientation="angled", at=None)
        if not any(_parallel(a, axis) and abs(a["c"] - axis["c"]) < 2.0 for a in axes):
            axes.append(axis)
    return axes


def _crossing(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[tuple]:
    """Where two grid lines cross (None when they are within 10 degrees of parallel)."""

    if _parallel(a, b, 10.0):
        return None
    (ax, ay), (bx, by) = _normal(a["angle"]), _normal(b["angle"])
    det = ax * by - ay * bx
    return (a["c"] * by - ay * b["c"]) / det, (ax * b["c"] - a["c"] * bx) / det


def _near(box: Any, x: float, y: float, reach: float) -> bool:
    return box[0] - reach <= x <= box[2] + reach and box[1] - reach <= y <= box[3] + reach


def _leader_ends(target: List[float], segments: List[tuple]) -> List[tuple]:
    """Far ends of thin leader lines that start on ``target``, followed
    through connected segments (a leader with a knee is two segments)."""

    thin = [s for s in segments if s[4] < _SYMBOL_MIN_WIDTH and abs(s[2] - s[0]) + abs(s[3] - s[1]) > 2.0]
    frontier = []
    for s in thin:
        a, b = _near(target, s[0], s[1], _LEADER_REACH), _near(target, s[2], s[3], _LEADER_REACH)
        if a != b:
            frontier.append((s[2], s[3]) if a else (s[0], s[1]))
    ends = list(frontier)
    for _hop in range(2):
        nxt = []
        for ex, ey in frontier:
            for s in thin:
                if abs(s[0] - ex) < 1.5 and abs(s[1] - ey) < 1.5:
                    nxt.append((s[2], s[3]))
                elif abs(s[2] - ex) < 1.5 and abs(s[3] - ey) < 1.5:
                    nxt.append((s[0], s[1]))
        nxt = [p for p in nxt if p not in ends and not _near(target, p[0], p[1], _LEADER_REACH)]
        ends.extend(nxt)
        frontier = nxt
    return ends


def _observe(x: float, y: float, lines: List[Dict[str, Any]], drawings: List[dict],
             segments: List[tuple], section_names: set) -> Dict[str, Any]:
    point = [round(x - 3, 1), round(y - 3, 1), round(x + 3, 1), round(y + 3, 1)]
    symbol = [path["rect"] for path in drawings
              if float(path.get("width") or 0.0) >= _SYMBOL_MIN_WIDTH
              and max(path["rect"].width, path["rect"].height) <= _SYMBOL_MAX
              and _near(path["rect"], x, y, _SYMBOL_REACH)]
    symbol_box = [round(v, 1) for v in _union_boxes(tuple(r) for r in symbol)] if symbol else None
    target = symbol_box or point
    ends = _leader_ends(target, segments)
    annotations, nearby = [], []
    for line in lines:
        box = line["bbox"]
        text = " ".join(str(line.get("text") or "").split())
        if not text:
            continue
        led = any(_near(box, ex, ey, 6.0) for ex, ey in ends)
        if led or _near(box, x, y, _TEXT_REACH):
            entry = {"text": text, "bbox": [round(float(v), 1) for v in box[:4]],
                     "how": "leader ends at the column" if led else "printed at the column"}
            if _ANNOTATION_RE.search(text) or _norm(text) in section_names:
                annotations.append(entry)
            else:
                nearby.append(entry)
        elif _near(box, x, y, _NEARBY_REACH):
            nearby.append({"text": text, "bbox": [round(float(v), 1) for v in box[:4]], "how": "nearby"})
    return {
        "point_bbox": point,
        "symbol": {"bbox": symbol_box} if symbol_box else None,
        "annotations": annotations,
        "nearby_text": nearby[:12],
    }


def _plan_pages(level: Dict[str, Any], plan_names: Dict[int, List[str]], elevations: List[Dict[str, Any]],
                schedule_pages: set, block_levels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Plans for one schedule level: a plan name with the same level key, or
    a level the plan's own notes name at the same elevation (``TOP OF OFFICE
    ROOF SLAB ELEVATION 69' - 4"`` for ``T.O. ROOF 69' - 4"``)."""

    keys = level_keys(level["name"])
    kinds = {key[0] for key in keys}
    inches = (parse_elevation(level.get("elevation_text") or "") or {}).get("inches")
    out: Dict[int, Dict[str, Any]] = {}
    for page, names in sorted(plan_names.items()):
        named = next((n for n in names if level_keys(n) & keys), None)
        if named and page not in schedule_pages:
            # A plan name that fits another level of this schedule too is not specific.
            also = [o["name"] for o in block_levels
                    if o["name"] != level["name"] and level_keys(o["name"]) & level_keys(named)]
            out[page] = {"page": page, "title": named, "ambiguous": bool(also),
                         "matched_by": "plan name" + (f" (also fits {', '.join(also)})" if also else "")}
    for e in elevations:
        if (inches is None or e["page"] in out or e["page"] in schedule_pages or e["status"] != "read"
                or not e.get("name") or not e.get("value")):
            continue
        if {key[0] for key in level_keys(e["name"])} & kinds and abs(e["value"]["inches"] - inches) < 0.01:
            out[e["page"]] = {"page": e["page"], "title": (plan_names.get(e["page"]) or [e.get("plan")])[0],
                              "ambiguous": False,
                              "matched_by": f"the plan's note names {e['name']} at the same elevation"}
    return [out[page] for page in sorted(out)]


def _block_lines(entry: Dict[str, Any], schedule: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Level lines of the schedule block the entry is printed in."""

    box = entry.get("bbox") or []
    if len(box) < 4:
        return []
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for index, block in enumerate(schedule.get("blocks") or [], start=1):
        b = block.get("bbox") or []
        if block["page"] == entry["page"] and len(b) >= 4 and b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            return [line for line in schedule.get("level_lines") or [] if line.get("block") == index]
    return []


def _spanned(entry: Dict[str, Any], lines: List[Dict[str, Any]]) -> tuple:
    """Level lines of the entry's schedule block in drawn order, and the ends."""

    extent = entry.get("extent") or {}
    names: List[Dict[str, Any]] = []
    for line in lines:
        if line.get("name") and not any(n["name"] == line["name"] for n in names):
            names.append(line)
    names.sort(key=lambda line: line["y"])
    top, bottom = extent.get("top") or {}, extent.get("bottom") or {}

    def end_state(end: Dict[str, Any], which: str) -> Dict[str, Any]:
        if end.get("position") == "at":
            return {"state": "established", "level": end["line"]["name"],
                    "elevation": end["line"].get("elevation_text"), "by": "drawn on the schedule's level line"}
        return {"state": "unresolved", "position": end.get("position") or "unknown",
                "note": f"The schedule draws the {which} end "
                        + ({"between": "between two level lines", "above": "above every level line",
                            "below": "below every level line"}.get(end.get("position"), "where no level line is read"))
                        + "; it is not moved to the nearest line."}

    ends = {"top": end_state(top, "top"), "bottom": end_state(bottom, "bottom")}
    top_y, bottom_y = top.get("y"), bottom.get("y")
    spanned = [line for line in names if top_y is not None and bottom_y is not None
               and top_y - 3.0 <= line["y"] <= bottom_y + 3.0]
    return spanned, ends, names


def plan_geometry(page: Any, lines: list[dict[str, Any]]) -> dict[str, Any]:
    """One plan page's vectors and labelled grid axes, read once and reusable
    for every location looked for on that page."""

    words = page.get_text("words")
    drawings = page.get_drawings()
    segments = _segments(drawings)
    index = _segment_index(segments)
    circles = _circles(drawings)
    by_name: dict[str, list[tuple]] = defaultdict(list)
    for w in words:
        by_name[_norm(w[4])].append(w)
    labels = {name for name in by_name if _GRID_LABEL_RE.match(name)}
    all_axes = {name: found for name in labels if (found := _axes(_bubbles(by_name[name], circles, name), index))}
    return {"words": words, "drawings": drawings, "segments": segments, "index": index, "circles": circles,
            "by_name": by_name, "all_axes": all_axes, "calibration": grid_calibration(all_axes, lines)}


def _analyse_plan(page: Any, page_no: int, names: list[str], lines: list[dict[str, Any]],
                  section_names: set, geometry: dict[str, Any] | None = None) -> tuple | None:
    """``(record, context)`` for one plan page: the grid axes, the observations
    at their crossings, and (context, not output) every labelled grid axis,
    the grid-dimension calibration and the vectors for offset placement.
    ``None`` when neither grid label is printed there (no vectors are read).
    ``geometry`` (``plan_geometry``) reuses a page already read."""

    if geometry is None:
        if not any(_norm(w[4]) in names for w in page.get_text("words")):
            return None
        geometry = plan_geometry(page, lines)
    drawings, segments, by_name = geometry["drawings"], geometry["segments"], geometry["by_name"]
    if not any(name in by_name for name in names):
        return None
    all_axes = dict(geometry["all_axes"])
    for name in names:
        if name not in all_axes:
            found = _axes(_bubbles(by_name.get(name, []), geometry["circles"], name), geometry["index"])
            if found:
                all_axes[name] = found
    axes = [all_axes.get(name, []) for name in names]
    if not any(axes):
        return None
    pairs = [(a, b, at) for a in axes[0] for b in axes[1] if (at := _crossing(a, b))]
    # Per candidate (same order): its crossing and the two axes, for offset placement.
    context = {"axes": all_axes, "calibration": geometry["calibration"], "drawings": drawings,
               "segments": segments, "lines": lines,
               "crossings": [((x, y), {names[0]: a, names[1]: b}) for a, b, (x, y) in pairs]}
    record: dict[str, Any] = {"grid_axes": [len(a) for a in axes], "candidates": [
        {**_observe(x, y, lines, drawings, segments, section_names), "page": page_no} for _a, _b, (x, y) in pairs]}
    if not pairs:
        record.update(observation="grids_not_found", note="Both grid lines were not found on this plan.")
        return record, context
    seen = any(c["symbol"] for c in record["candidates"])
    record["observation"] = "column_symbol" if seen else "not_detected"
    if len(pairs) > 1:
        record["note"] = (f"The grids cross at {len(pairs)} places on this sheet (for example an "
                          "enlarged or partial plan); each is listed, none is chosen.")
    elif not seen:
        record["note"] = "No column symbol was detected at the intersection; this is not evidence of absence."
    return record, context


def _place_offset(crossing: tuple, grid: str, offset: Dict[str, Any], scale: Dict[str, Any],
                  context: Dict[str, Any], section_names: set) -> Dict[str, Any]:
    """Where a column printed as offset from ``grid`` can be on this view.

    The offset runs perpendicular to its own grid line. Its printed sign is
    not a screen direction, so both sides are measured and looked at; a side
    is named by the grid it heads toward. A side is established only when the
    view's scale is validated or calibrated and the column is drawn on exactly
    one side."""

    record: Dict[str, Any] = {"grid": grid, "printed": offset.get("raw"), "inches": abs(float(offset["inches"])),
                              "scale_status": scale["status"], "sides": []}
    usable = scale["points_per_inch"] or ((scale.get("printed") or {}).get("points_per_inch")
                                         if scale["status"] == "printed" else None)
    if not usable:
        return {**record, "status": "unresolved_scale",
                "note": f"The offset is not placed: {scale['note']}"}
    distance = record["inches"] * usable
    (x, y), axes = crossing
    axis = axes[grid]
    nx, ny = _normal(axis["angle"])
    # Other grid lines parallel to the offset grid, by their position along its normal.
    parallel = [(a["c"], name) for name, found in context["axes"].items() for a in found
                if name != grid and _parallel(a, axis)]
    for sign in (-1, 1):
        px, py = x + sign * distance * nx, y + sign * distance * ny
        beyond = [(abs(c - axis["c"]), name) for c, name in parallel if (c - axis["c"]) * sign > 0]
        seen = _observe(px, py, context["lines"], context["drawings"], context["segments"], section_names)
        record["sides"].append({"toward": _toward_grid(grid, beyond), "point_bbox": seen["point_bbox"],
                                "symbol": seen["symbol"], "annotations": seen["annotations"]})
    record["points"] = round(distance, 1)
    drawn = [side for side in record["sides"] if side["symbol"]]
    if len(drawn) == 1:
        side = drawn[0]
        if not _reliable_offset(distance, side.get("symbol")):
            return _window_limited(record, distance, side.get("symbol"))
        toward = f"toward grid {side['toward']}" if side["toward"] else "on one side"
        if scale["status"] in PLACES:
            return {**record, "status": "placed", "placed_bbox": side["point_bbox"],
                    "note": f"The column is drawn {record['printed']} from grid {grid}, {toward}, at the view's "
                            f"{scale['status']} scale."}
        return {**record, "status": "candidate", "placed_bbox": side["point_bbox"],
                "note": f"A column is drawn {toward} at the offset, but the view's scale is only printed, not validated."}
    return {**record, "status": "unresolved_direction",
            "note": ("A column is drawn on both sides; the side is not established." if drawn
                     else "No column symbol is drawn at the offset on either side; the side is not established.")}


def _column_annotations(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Notes at the column itself: at the crossing, or -- for an offset column
    -- at the side the column is drawn on (none while that side is unknown)."""

    offset = candidate.get("offset")
    if not offset:
        return candidate["annotations"]
    placed = offset.get("placed_bbox")
    if not placed:
        return []
    return next((side["annotations"] for side in offset.get("sides") or [] if side["point_bbox"] == placed), [])


def trace_column(document: Dict[str, Any], pdf_path: str, location: str,
                 schedule_id: Optional[str] = None) -> Dict[str, Any]:
    """Trace one schedule entry (printed location or mark) across the plans."""

    from services.engineering.drawing_intelligence import _sheet_ids

    sheets = _sheet_ids(document)
    view = column_schedule_view(document, sheets)
    wanted = _norm(location)
    # One schedule entry can list several locations (Brandywine S-600:
    # "A.4'-14, B-4.9, E-8(-4'-4"), C'-15.6"); each is traced on its own.
    def printed(e: Dict[str, Any]) -> set:
        return {_norm(e.get("location_text") or e.get("mark") or "")} | {_norm(loc.get("raw")) for loc in e.get("locations") or []}

    entries = [e for e in view.get("entries") or []
               if wanted in printed(e) and (schedule_id is None or e.get("schedule_id") == schedule_id)]
    if not entries:
        return {"status": "not_found", "location": location,
                "note": "No column-schedule entry prints this location or mark."}
    if len(entries) > 1:
        return {"status": "ambiguous", "location": location,
                "candidates": [{"schedule_id": e["schedule_id"], "page": e["page"], "sheet": e.get("sheet")}
                               for e in entries],
                "note": "Several schedules print this location; choose one schedule."}
    entry = entries[0]
    schedule = next(s for s in (document.get("column_schedules") or {}).get("schedules") or []
                    if s["id"] == entry["schedule_id"])
    location_record = next((loc for loc in entry.get("locations") or [] if _norm(loc.get("raw")) == wanted),
                           (entry.get("locations") or [{}])[0])
    grids = location_record.get("grids") or []
    spanned, ends, block_levels = _spanned(entry, _block_lines(entry, schedule))
    sections = [s.get("designation") or s.get("printed") for s in entry.get("sections") or []]
    section_names = {_norm(name) for name in sections}
    trace: Dict[str, Any] = {
        "status": "traced",
        "pilot": True,
        "schedule": {"id": schedule["id"], "title": schedule.get("caption") or schedule.get("title"),
                     "page": entry["page"], "sheet": entry.get("sheet"), "bbox": entry.get("bbox")},
        "location_text": entry.get("location_text") or entry.get("mark"),
        "location": location_record.get("raw") or entry.get("mark"),
        "grids": [{"name": g["label"], "offset": (g.get("offset") or {}).get("raw")} for g in grids],
        "sections": sections,
        "ends": ends,
        "levels": [],
        "notes": [],
    }
    if len(grids) != 2:
        trace["notes"].append("The location is not two grids, so no intersection can be looked for on plans.")
        return convert_boxes(trace, display_boxes(document))
    offsets = {_norm(g["label"]): g["offset"] for g in grids if g.get("offset")}
    two_offsets = len(offsets) > 1
    if not spanned:
        trace["notes"].append("The schedule's drawn extent does not sit on level lines, so no level is spanned "
                              "with certainty; plans are not searched.")
    names = [_norm(g["label"]) for g in grids]
    schedule_pages = set(schedule.get("pages") or [])
    if spanned:
        shown = displayed(document)
        statements = plan_statements(shown, sheets)
        plan_names = plan_names_by_page(shown, statements)
        elevations = plan_elevations(statements, spot_elevations(shown, sheets),
                                     plan_values(shown, statements, sheets))
        lines_by_page: Dict[int, List[Dict[str, Any]]] = {}
        for ln in document.get("lines") or []:
            if len(ln.get("bbox") or []) >= 4:
                lines_by_page.setdefault(int(ln.get("page_number") or 0), []).append(ln)
        scopes = ScopeResolver(document, elevations, shown)
        shown_lines: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for ln in shown.get("lines") or []:
            if ln.get("bbox"):
                shown_lines[int(ln.get("page_number") or 0)].append(ln)
        title_block_scale = sheet_scales(document)
        view_scales: Dict[tuple, Dict[str, Any]] = {}
        with fitz.open(pdf_path) as pdf:
            analysed: Dict[int, Optional[Dict[str, Any]]] = {}
            for line in spanned:
                level = {"name": line["name"], "elevation": line.get("elevation_text"), "plans": [],
                         "other_titled_sheets": [], "other_scope_views": []}
                plans = _plan_pages(line, plan_names, elevations, schedule_pages, block_levels)
                if not plans:
                    level["note"] = "No plan names this level or states its elevation."
                for plan in plans:
                    page_no = plan["page"]
                    if page_no not in analysed:
                        analysed[page_no] = _analyse_plan(pdf[page_no - 1], page_no, names,
                                                          lines_by_page.get(page_no, []), section_names)
                    found, context = analysed[page_no] or (None, None)
                    if found is None:
                        # Neither grid is labelled here: a titled sheet that is not this plan view.
                        level["other_titled_sheets"].append(sheets.get(page_no) or f"p. {page_no}")
                        continue
                    record = {"page": page_no, "sheet": sheets.get(page_no), "plan": plan["title"],
                              "matched_by": plan["matched_by"], "ambiguous_match": plan["ambiguous"],
                              **found, "candidates": []}
                    for candidate, crossing in zip(found["candidates"], context["crossings"]):
                        scope = scopes.scope(schedule["id"], page_no, candidate["point_bbox"])
                        if scope["status"] == "conflicting":
                            # Another building's view with the same grid and level names.
                            level["other_scope_views"].append({"page": page_no, "sheet": sheets.get(page_no),
                                                              "view_title": scope["view_title"],
                                                              "sheet_title": scope["sheet_title"],
                                                              "note": scope["note"]})
                            continue
                        view_key = (page_no, tuple(scope.get("view_title_bbox") or ()))
                        if view_key not in view_scales:
                            view_scales[view_key] = resolve_view_scale(
                                printed_view_scale(shown_lines.get(page_no, []), scope.get("view_title_bbox")),
                                title_block_scale.get(page_no), context["calibration"])
                        scale = view_scales[view_key]
                        observed = {**candidate, "scope": scope, "scale": scale}
                        if two_offsets:
                            observed["offset"] = {"status": "unresolved_two_offsets", "sides": [],
                                                  "note": "Both grids carry an offset; not placed."}
                        elif offsets:
                            (grid_name, offset), = offsets.items()
                            observed["offset"] = _place_offset(crossing, grid_name, offset, scale, context,
                                                               section_names)
                        # An offset column is the one placed at the offset, not whatever sits on the crossing.
                        observed["column_observed"] = (observed["offset"]["status"] == "placed" if offsets
                                                       else bool(candidate["symbol"]))
                        record["candidates"].append(observed)
                    if not found["candidates"]:
                        # No grid crossing here: the sheet's own scope decides whether to list it.
                        sheet_scope = scopes.scope(schedule["id"], page_no)
                        if sheet_scope["status"] == "conflicting":
                            level["other_scope_views"].append({"page": page_no, "sheet": sheets.get(page_no),
                                                              "view_title": None,
                                                              "sheet_title": sheet_scope["sheet_title"],
                                                              "note": sheet_scope["note"]})
                            continue
                        record["scope"] = sheet_scope
                    elif not record["candidates"]:
                        continue
                    scopes_here = [c["scope"] for c in record["candidates"]] or [record["scope"]]
                    if not any(scope["status"] in COUNTS for scope in scopes_here):
                        record["scope_unresolved"] = True
                    if record["candidates"]:
                        observed = any(c["column_observed"] for c in record["candidates"])
                        if offsets:
                            record["observation"] = "column_symbol_at_offset" if observed else "not_detected_at_offset"
                        elif found["observation"] == "column_symbol" and not observed:
                            record["observation"] = "not_detected"
                    level["plans"].append(record)
                trace["levels"].append(level)
    # One plan page matched to several spanned levels is not specific to any.
    levels_of_page: Dict[int, List[str]] = {}
    for lvl in trace["levels"]:
        for plan in lvl["plans"]:
            levels_of_page.setdefault(plan["page"], []).append(lvl["name"])
    for lvl in trace["levels"]:
        for plan in lvl["plans"]:
            others = [name for name in levels_of_page[plan["page"]] if name != lvl["name"]]
            if others:
                plan["ambiguous_match"] = True
                plan["matched_by"] += f"; also matched to {', '.join(others)}"
    # Every note whose leader ends at the column, by level and direction. Evidence
    # about continuation, kept apart from the end states: "COL UP" says a column
    # continues upward from that plan, not where it stops.
    trace["directional_evidence"] = [
        {"level": lvl["name"], "sheet": plan["sheet"], "page": plan["page"], "text": note["text"], "bbox": note["bbox"],
         "direction": "up" if _UP_RE.search(note["text"]) else "down" if _DOWN_RE.search(note["text"]) else None,
         "scope_counts": candidate["scope"]["status"] in COUNTS}
        for lvl in trace["levels"] for plan in lvl["plans"] for candidate in plan["candidates"]
        for note in _column_annotations(candidate) if note["how"] == "leader ends at the column"
    ]
    # Such a note on an end's own level supports that end only in its own
    # direction: ``POST UP`` starts a column (bottom end), ``COLUMN BELOW`` /
    # ``DOWN`` ends one (top end). Quoted, not parsed further.
    for which, end in trace["ends"].items():
        words = _UP_RE if which == "bottom" else _DOWN_RE
        end["plan_annotations"] = [{k: d[k] for k in ("sheet", "page", "text", "bbox")}
                                   for d in trace["directional_evidence"]
                                   if d["level"] == end.get("level") and d["scope_counts"] and words.search(d["text"])]
    # A symbol counts only on a plan specific to the level, in this schedule's scope.
    observed_levels = [lvl["name"] for lvl in trace["levels"]
                       if any(not p["ambiguous_match"] and c["column_observed"] and c["scope"]["status"] in COUNTS
                              for p in lvl["plans"] for c in p["candidates"])]
    trace["summary"] = {
        "levels_spanned": [lvl["name"] for lvl in trace["levels"]],
        "levels_with_symbol": observed_levels,
        "logical_stack_only": True,
        "note": "Observations describe one logical column stack at this location; they do not establish "
                "how many fabricated pieces it is made of.",
    }
    return convert_boxes(trace, display_boxes(document))


# --------------------------------------------------------------------------
# Locate on plan: one printed location, on every plan view that prints both
# of its grid labels -- independent of levels, so a location a table assigns
# (no schedule extent) or a stair part plan (no level in its title) is found
# too. The grid names are literal axes: C.1-5.1 is where the axis labelled
# C.1 crosses the axis labelled 5.1; a decimal is part of the name, never an
# offset. Scale matters only for a parenthesized offset.
# --------------------------------------------------------------------------


def locate_context(document: dict[str, Any], pdf_path: str) -> dict[str, Any]:
    """Document-level evidence a location lookup reuses: sheet ids, display
    space, plan scope, scales and each page's grid labels. Built once per
    document revision (the caller caches it); plan pages are analysed lazily
    and remembered here."""

    from services.engineering.drawing_intelligence import _sheet_ids

    shown = displayed(document)
    sheets = _sheet_ids(document)
    statements = plan_statements(shown, sheets)
    elevations = plan_elevations(statements, spot_elevations(shown, sheets), plan_values(shown, statements, sheets))
    # Every short printed word per page: a page is a candidate when it prints
    # both grid names exactly (R13, D2.5 and RA.1 included).
    labels: dict[int, set] = defaultdict(set)
    for word in document.get("words") or []:
        name = _norm(word.get("text") or "")
        if 0 < len(name) <= 10:
            labels[int(word.get("page_number") or 0)].add(name)
    lines_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ln in document.get("lines") or []:
        if len(ln.get("bbox") or []) >= 4:
            lines_by_page[int(ln.get("page_number") or 0)].append(ln)
    shown_lines: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ln in shown.get("lines") or []:
        if ln.get("bbox"):
            shown_lines[int(ln.get("page_number") or 0)].append(ln)
    schedule_pages = {p for s in (document.get("column_schedules") or {}).get("schedules") or [] for p in s.get("pages") or []}
    return {
        "pdf_path": pdf_path, "sheets": sheets, "box": display_boxes(document),
        "scopes": ScopeResolver(document, elevations, shown), "labels": labels,
        "lines_by_page": lines_by_page, "shown_lines": shown_lines, "title_block_scale": sheet_scales(document),
        "schedule_pages": schedule_pages, "analysed": {}, "geometry": {}, "view_scales": {},
        "schedule_names": {s["id"]: s.get("caption") or s.get("title")
                           for s in (document.get("column_schedules") or {}).get("schedules") or []},
    }


def _place_two_offsets(crossing: tuple, offsets: dict[str, dict[str, Any]], scale: dict[str, Any],
                       context: dict[str, Any]) -> dict[str, Any]:
    """A column offset from both of its grids (``C.4(1' - 7 3/8")-7.5(-2' - 4 1/2")``):
    each offset runs perpendicular to its own grid. Printed signs are not
    screen directions, so all four combinations are looked at; one is
    established only when the view's scale is validated or calibrated and a
    column is drawn at exactly one of them."""

    record: dict[str, Any] = {"grids": [{"grid": g, "printed": o.get("raw"), "inches": abs(float(o["inches"]))}
                                        for g, o in offsets.items()], "scale_status": scale["status"], "sides": []}
    usable = scale["points_per_inch"] or ((scale.get("printed") or {}).get("points_per_inch")
                                         if scale["status"] == "printed" else None)
    if not usable:
        return {**record, "status": "unresolved_scale", "note": f"The offsets are not placed: {scale['note']}"}
    (x, y), axes = crossing
    shifts = []
    for g, o in offsets.items():
        nx, ny = _normal(axes[g]["angle"])
        shifts.append((g, abs(float(o["inches"])) * usable, nx, ny))
    for s1 in (-1, 1):
        for s2 in (-1, 1):
            (_g1, d1, n1x, n1y), (_g2, d2, n2x, n2y) = shifts
            determinant = n1x * n2y - n1y * n2x
            if abs(determinant) < 0.01:
                return {**record, "status": "unresolved_direction",
                        "note": "The grid axes are too nearly parallel to place both offsets reliably."}
            # Solve both perpendicular-distance constraints, including skew grids.
            px = x + (s1 * d1 * n2y - s2 * d2 * n1y) / determinant
            py = y + (n1x * s2 * d2 - n2x * s1 * d1) / determinant
            seen = _observe(px, py, context["lines"], context["drawings"], context["segments"], set())
            record["sides"].append({"toward": None, "signs": [s1, s2], "point_bbox": seen["point_bbox"],
                                    "symbol": seen["symbol"], "annotations": seen["annotations"]})
    drawn = [side for side in record["sides"] if side["symbol"]]
    if len(drawn) == 1:
        box = drawn[0]["point_bbox"]
        apart = math.hypot((box[0] + box[2]) / 2 - x, (box[1] + box[3]) / 2 - y)
        if not _reliable_offset(apart, drawn[0].get("symbol")):
            return _window_limited(record, apart, drawn[0].get("symbol"))
        if scale["status"] in PLACES:
            return {**record, "status": "placed", "placed_bbox": box,
                    "note": f"A column is drawn at one of the four offset positions, at the view's {scale['status']} scale."}
        return {**record, "status": "candidate", "placed_bbox": box,
                "note": "A column is drawn at one offset position, but the view's scale is only printed, not validated."}
    return {**record, "status": "unresolved_direction",
            "note": (f"A column is drawn at {len(drawn)} of the four offset positions; the directions are not established."
                     if drawn else "No column symbol is drawn at any of the four offset positions; the directions "
                                   "are not established.")}


def _view_scale(context: dict[str, Any], page: int, scope: dict[str, Any], plan_context: dict[str, Any]) -> dict[str, Any]:
    key = (page, tuple(scope.get("view_title_bbox") or ()))
    if key not in context["view_scales"]:
        context["view_scales"][key] = resolve_view_scale(
            printed_view_scale(context["shown_lines"].get(page, []), scope.get("view_title_bbox")),
            context["title_block_scale"].get(page), plan_context["calibration"])
    return context["view_scales"][key]


def locate_location(context: dict[str, Any], location: str, schedule_id: str | None = None) -> dict[str, Any]:
    """Where one printed grid location is on the plans.

    Every plan view printing both grid labels is analysed: the two labelled
    axes, their crossing(s), a column symbol there and, for a printed offset,
    the offset placed perpendicular to its own grid at the view's scale.
    ``schedule_id`` scopes views by building / area (``view_scope``); a view
    titled for another schedule's scope is listed apart, never dropped
    silently. Results are ordered: in scope with a column first."""

    from services.engineering.column_schedule import parse_grid_location

    parsed = parse_grid_location(location)
    grids = parsed.get("grids") or []
    result: dict[str, Any] = {"location": location, "grids": [{"name": g["label"], "offset": (g.get("offset") or {}).get("raw")}
                                                              for g in grids],
                              "schedule_id": schedule_id, "views": [], "other_scope_views": []}
    if parsed["status"] != "parsed" or len(grids) != 2:
        return {**result, "status": "not_a_grid_location",
                "note": "The printed location is not two grid names, so there is no intersection to look for."}
    names = [_norm(g["label"]) for g in grids]
    offsets = {_norm(g["label"]): g["offset"] for g in grids if g.get("offset")}
    sheets = context["sheets"]
    pages = sorted(p for p, found in context["labels"].items()
                   if all(n in found for n in names) and p not in context["schedule_pages"])
    if not pages:
        return {**result, "status": "plan_not_found",
                "note": f"No plan in the set prints both grid labels {grids[0]['label']} and {grids[1]['label']}."}
    scopes: ScopeResolver = context["scopes"]
    with fitz.open(context["pdf_path"]) as pdf:
        for page_no in pages:
            key = (page_no, tuple(names))
            if key not in context["analysed"]:
                lines = context["lines_by_page"].get(page_no, [])
                if page_no not in context["geometry"]:
                    context["geometry"][page_no] = plan_geometry(pdf[page_no - 1], lines)
                context["analysed"][key] = _analyse_plan(pdf[page_no - 1], page_no, names, lines, set(),
                                                         context["geometry"][page_no])
            found, plan_context = context["analysed"][key] or (None, None)
            if found is None or not found["candidates"]:
                continue
            for candidate, crossing in zip(found["candidates"], plan_context["crossings"]):
                if schedule_id:
                    scope = scopes.scope(schedule_id, page_no, candidate["point_bbox"])
                else:
                    view = scopes._view_title(page_no, candidate["point_bbox"])
                    scope = {"status": "not_compared", "view_title": view and view["text"],
                             "view_title_bbox": view and view["bbox"],
                             "sheet_title": (scopes.sheet_titles.get(page_no) or {}).get("text"),
                             "note": "No schedule given; the view's building / area is not compared."}
                item = {"page": page_no, "sheet": sheets.get(page_no), "view_title": scope.get("view_title"),
                        "sheet_title": scope.get("sheet_title"), "scope": {k: scope.get(k) for k in ("status", "note")},
                        **candidate}
                if scope["status"] == "conflicting":
                    result["other_scope_views"].append(item)
                    continue
                scale = _view_scale(context, page_no, scope, plan_context)
                item["scale"] = {"status": scale["status"], "note": scale.get("note")}
                if len(offsets) == 2:
                    placed = _place_two_offsets(crossing, offsets, scale, plan_context)
                elif offsets:
                    (grid_name, offset), = offsets.items()
                    placed = _place_offset(crossing, grid_name, offset, scale, plan_context, set())
                else:
                    placed = None
                if placed:
                    item["offset"] = placed
                    # A mark inside the search window is not a side. Leave the
                    # highlight on the crossing and do not name a direction.
                    if placed.get("search_window_limited"):
                        item["state"] = "offset_unresolved"
                        item["target_bbox"] = candidate["point_bbox"]
                    else:
                        item["state"] = {"placed": "column_symbol_at_offset", "candidate": "offset_candidate"}.get(
                            placed["status"], "offset_unresolved")
                        item["target_bbox"] = placed.get("placed_bbox") or candidate["point_bbox"]
                else:
                    item["state"] = "column_symbol" if candidate["symbol"] else "intersection_only"
                    item["target_bbox"] = (candidate["symbol"] or {}).get("bbox") or candidate["point_bbox"]
                result["views"].append(item)
    rank = {"column_symbol": 0, "column_symbol_at_offset": 0, "offset_candidate": 1, "intersection_only": 2,
            "offset_unresolved": 2}
    result["views"].sort(key=lambda v: (v["scope"]["status"] not in COUNTS and v["scope"]["status"] != "not_compared",
                                        rank.get(v["state"], 3), v["page"]))
    observed = [v for v in result["views"] if v["state"] in ("column_symbol", "column_symbol_at_offset")]
    pages_observed = {v["page"] for v in observed}
    if not result["views"]:
        status = "plan_not_found"
        result["note"] = ("Plans printing both grid labels were found, but none in this schedule's building / area."
                          if result["other_scope_views"] else "The two grid lines do not cross on any plan that prints them.")
    elif observed:
        status = "column_symbol"
    elif any(v["state"] == "offset_unresolved" for v in result["views"]):
        status = "offset_unresolved"
    else:
        status = "intersection_only"
    if len(observed) > len(pages_observed):
        result["note"] = "On some plans the grids cross at more than one place; every candidate is listed, none is chosen."
    result["status"] = status
    result["default"] = 0 if result["views"] else None
    return convert_boxes(result, context["box"])
