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

import re
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
from services.engineering.view_scope import COUNTS, ScopeResolver

_BUBBLE_MIN, _BUBBLE_MAX = 10.0, 90.0
_AXIS_MIN_LENGTH = 200.0      # a grid line runs across the plan, not a detail
_SYMBOL_REACH = 6.0           # a column symbol is drawn on the intersection
_SYMBOL_MAX = 40.0
_SYMBOL_MIN_WIDTH = 0.8       # heavy strokes; grid and dimension lines are hairlines
_LEADER_REACH = 10.0
_TEXT_REACH = 18.0
_NEARBY_REACH = 60.0
_ANNOTATION_RE = re.compile(
    r"\b(?:POST|COL(?:UMN)?\.?)\s+(?:UP|DOWN|ABOVE|BELOW|OVER|UNDER)\b|\bTOP\s+OF\s+COL|\bT\.?O\.?\s*COL|\bBEARS?\b",
    re.IGNORECASE)


_UP_RE = re.compile(r"\b(?:UP|ABOVE|OVER)\b", re.IGNORECASE)
_DOWN_RE = re.compile(r"\b(?:DOWN|BELOW|UNDER)\b|\bTOP\s+OF\s+COL|\bT\.?O\.?\s*COL", re.IGNORECASE)


def _norm(name: str) -> str:
    return _clean(name).replace(" ", "").upper()


def _bubbles(words: List[tuple], drawings: List[dict], name: str) -> List[Dict[str, float]]:
    """Centres of circles that contain a word printed exactly as ``name``."""

    out = []
    for w in words:
        if _norm(w[4]) != name:
            continue
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        for path in drawings:
            r = path["rect"]
            if (_BUBBLE_MIN <= r.width <= _BUBBLE_MAX and abs(r.width - r.height) <= 0.15 * r.width
                    and r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1
                    and any(item[0] == "c" for item in path["items"])):
                out.append({"x": (r.x0 + r.x1) / 2, "y": (r.y0 + r.y1) / 2})
                break
    return out


def _segments(drawings: List[dict]) -> List[tuple]:
    return [(item[1].x, item[1].y, item[2].x, item[2].y, float(path.get("width") or 0.0))
            for path in drawings for item in path["items"] if item[0] == "l"]


def _axes(bubbles: List[Dict[str, float]], segments: List[tuple]) -> List[Dict[str, Any]]:
    """Distinct grid axes through the bubbles: ``{"orientation", "at"}``."""

    axes: List[Dict[str, Any]] = []
    for b in bubbles:
        vertical = sum(abs(s[3] - s[1]) for s in segments if abs(s[0] - b["x"]) < 1.0 and abs(s[2] - b["x"]) < 1.0)
        horizontal = sum(abs(s[2] - s[0]) for s in segments if abs(s[1] - b["y"]) < 1.0 and abs(s[3] - b["y"]) < 1.0)
        if max(vertical, horizontal) < _AXIS_MIN_LENGTH:
            continue
        axis = ({"orientation": "vertical", "at": b["x"]} if vertical >= horizontal
                else {"orientation": "horizontal", "at": b["y"]})
        if not any(a["orientation"] == axis["orientation"] and abs(a["at"] - axis["at"]) < 2.0 for a in axes):
            axes.append(axis)
    return axes


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


def _analyse_plan(page: Any, page_no: int, names: List[str], lines: List[Dict[str, Any]],
                  section_names: set) -> Optional[Dict[str, Any]]:
    """Grid axes and the observations at their crossings on one plan page;
    ``None`` when neither grid label is printed there (no vectors are read)."""

    words = page.get_text("words")
    if not any(_norm(w[4]) in names for w in words):
        return None
    drawings = page.get_drawings()
    segments = _segments(drawings)
    axes = [_axes(_bubbles(words, drawings, name), segments) for name in names]
    if not any(axes):
        return None
    pairs = [(a, b) for a in axes[0] for b in axes[1] if a["orientation"] != b["orientation"]]
    record: Dict[str, Any] = {"grid_axes": [len(a) for a in axes], "candidates": []}
    for a, b in pairs:
        x = a["at"] if a["orientation"] == "vertical" else b["at"]
        y = a["at"] if a["orientation"] == "horizontal" else b["at"]
        record["candidates"].append({**_observe(x, y, lines, drawings, segments, section_names), "page": page_no})
    if not pairs:
        record.update(observation="grids_not_found", note="Both grid lines were not found on this plan.")
        return record
    seen = any(c["symbol"] for c in record["candidates"])
    record["observation"] = "column_symbol" if seen else "not_detected"
    if len(pairs) > 1:
        record["note"] = (f"The grids cross at {len(pairs)} places on this sheet (for example an "
                          "enlarged or partial plan); each is listed, none is chosen.")
    elif not seen:
        record["note"] = "No column symbol was detected at the intersection; this is not evidence of absence."
    return record


def trace_column(document: Dict[str, Any], pdf_path: str, location: str,
                 schedule_id: Optional[str] = None) -> Dict[str, Any]:
    """Trace one schedule entry (printed location or mark) across the plans."""

    from services.engineering.drawing_intelligence import _sheet_ids

    sheets = _sheet_ids(document)
    view = column_schedule_view(document, sheets)
    wanted = _norm(location)
    entries = [e for e in view.get("entries") or []
               if _norm(e.get("location_text") or e.get("mark") or "") == wanted
               and (schedule_id is None or e.get("schedule_id") == schedule_id)]
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
    location_record = (entry.get("locations") or [{}])[0]
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
        "grids": [{"name": g["label"], "offset": (g.get("offset") or {}).get("raw")} for g in grids],
        "sections": sections,
        "ends": ends,
        "levels": [],
        "notes": [],
    }
    if len(grids) != 2:
        trace["notes"].append("The location is not two grids, so no intersection can be looked for on plans.")
        return convert_boxes(trace, display_boxes(document))
    if any(g.get("offset") for g in grids):
        trace["notes"].append("An offset from a grid is printed; it is not applied (plan scale is not read), "
                              "so plan observations are at the grid intersection, not the offset position.")
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
                    found = analysed[page_no]
                    if found is None:
                        # Neither grid is labelled here: a titled sheet that is not this plan view.
                        level["other_titled_sheets"].append(sheets.get(page_no) or f"p. {page_no}")
                        continue
                    record = {"page": page_no, "sheet": sheets.get(page_no), "plan": plan["title"],
                              "matched_by": plan["matched_by"], "ambiguous_match": plan["ambiguous"],
                              **found, "candidates": []}
                    for candidate in found["candidates"]:
                        scope = scopes.scope(schedule["id"], page_no, candidate["point_bbox"])
                        if scope["status"] == "conflicting":
                            # Another building's view with the same grid and level names.
                            level["other_scope_views"].append({"page": page_no, "sheet": sheets.get(page_no),
                                                              "view_title": scope["view_title"],
                                                              "sheet_title": scope["sheet_title"],
                                                              "note": scope["note"]})
                            continue
                        record["candidates"].append({**candidate, "scope": scope})
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
                    if found["observation"] == "column_symbol" and not any(c["symbol"] for c in record["candidates"]):
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
    # A plan annotation at the column on an end's own level supports that end
    # only in its own direction: ``POST UP`` starts a column (bottom end),
    # ``COLUMN BELOW`` / ``DOWN`` ends one (top end). Quoted, not parsed further.
    for which, end in trace["ends"].items():
        words = _UP_RE if which == "bottom" else _DOWN_RE
        end["plan_annotations"] = [
            {"sheet": plan["sheet"], "page": plan["page"], "text": note["text"], "bbox": note["bbox"]}
            for lvl in trace["levels"] if lvl["name"] == end.get("level")
            for plan in lvl["plans"] for candidate in plan["candidates"] for note in candidate["annotations"]
            if note["how"] == "leader ends at the column" and words.search(note["text"])
            and candidate["scope"]["status"] in COUNTS
        ]
    # A symbol counts only on a plan specific to the level, in this schedule's scope.
    observed_levels = [lvl["name"] for lvl in trace["levels"]
                       if any(not p["ambiguous_match"] and c["symbol"] and c["scope"]["status"] in COUNTS
                              for p in lvl["plans"] for c in p["candidates"])]
    trace["summary"] = {
        "levels_spanned": [lvl["name"] for lvl in trace["levels"]],
        "levels_with_symbol": observed_levels,
        "logical_stack_only": True,
        "note": "Observations describe one logical column stack at this location; they do not establish "
                "how many fabricated pieces it is made of.",
    }
    return convert_boxes(trace, display_boxes(document))
