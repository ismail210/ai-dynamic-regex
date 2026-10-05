"""Which building / area a plan view belongs to, from what the drawing prints.

Evidence for the column-tracing pilot only. A set can hold several
buildings that share grid names and level names (OSSE: an OSSE BUILDING and
an OSSE PARKING column schedule on one sheet, plans titled "OSSE FACILITY"
and "OSSE PARKING"), and one sheet can hold several views. So scope is read
per view: the plan title printed under the view, else the sheet's
title-block drawing title.

A schedule is compared on the words that set it apart from the set's other
column schedules (BUILDING vs PARKING -- not OSSE, which both share). Status
of one plan view for one schedule:

* ``conflicting`` -- the view names another schedule's scope; not this column;
* ``consistent`` -- the view names this schedule's own scope;
* ``supported_by_datum`` -- a level the view's notes state is at an elevation
  of this schedule's levels and of no other schedule's;
* ``consistent_by_sheet_family`` -- the view's title scope is the same as that
  of views the datum notes tie to this schedule (and to no other);
* ``single_schedule`` -- the set has one column schedule; nothing to compare;
* ``unresolved`` -- nothing printed ties the view to this schedule.

Only ``consistent``, ``supported_by_datum``, ``consistent_by_sheet_family`` and
``single_schedule`` let an observation count. Same campus is never same
building: scope words must match, not just a shared project name.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from services.engineering.level_evidence import _PLAN_TITLE_RE, _clean, _wrapped_lines, parse_elevation
from services.engineering.page_space import display_boxes

COUNTS = frozenset({"consistent", "supported_by_datum", "consistent_by_sheet_family", "single_schedule"})

# Words that say which view of a building, not which building.
_VIEW_WORDS = frozenset({
    "PLAN", "PLANS", "FLOOR", "ROOF", "FOUNDATION", "FRAMING", "LEVEL", "LEVELS", "PART", "PARTIAL", "AND", "&",
    "-", "GCS", "SCHEDULE", "COLUMN", "GRAPHICAL", "T.O.", "TO", "OF", "THE", "SLAB", "DECK", "FIRST", "SECOND",
    "THIRD", "FOURTH", "FIFTH", "GROUND", "LOWER", "UPPER", "MAIN", "LOW", "HIGH", "ELEVATIONS", "ELEVATION",
    "SECTIONS", "DETAILS", "STEEL", "AREA", "ENLARGED", "OVERALL", "KEY", "SOUTH", "NORTH", "EAST", "WEST",
})
_TITLE_LABEL_RE = re.compile(r"^(?:DRAWING\s+)?TITLE\s*:?$", re.IGNORECASE)
_SHEET_NO_RE = re.compile(r"^[A-Z]{1,2}-?\d{1,4}(?:\.\d{1,3})?[A-Z]?(?:-[A-Z])?$")


def scope_terms(text: Any) -> set:
    """Words of a title that name a building / area, not a view or level."""

    words = re.split(r"[\s,/]+", _clean(text).upper())
    return {w for w in words if w and w not in _VIEW_WORDS and not re.fullmatch(r"[\d'\"().-]+", w)}


def sheet_titles(document: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """The title-block drawing title per page: the lines printed just right
    of a ``Title:`` label, in a font at least the label's size, in reading
    order (OSSE S-121-O: "OSSE FACILITY FOUNDATION" / "AND FIRST FLOOR PLAN")."""

    by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for line in document.get("lines") or []:
        if len(line.get("bbox") or []) >= 4:
            by_page[int(line.get("page_number") or 0)].append(line)
    out: Dict[int, Dict[str, Any]] = {}
    for page, lines in by_page.items():
        label = next((ln for ln in lines if _TITLE_LABEL_RE.match(_clean(ln.get("text")))), None)
        if label is None:
            continue
        _lx0, ly0, lx1, ly1 = label["bbox"][:4]
        size = float(label.get("font_size") or 0)
        near = sorted((ln for ln in lines if ln is not label and lx1 - 2 <= ln["bbox"][0] <= lx1 + 60
                       and ly0 - 8 <= ln["bbox"][1] <= ly1 + 26
                       and float(ln.get("font_size") or 0) >= size
                       and not _SHEET_NO_RE.match(_clean(ln.get("text")))),
                      key=lambda ln: (ln["bbox"][1], ln["bbox"][0]))
        text = " ".join(_clean(ln.get("text")) for ln in near)
        if text:
            out[page] = {"text": text, "lines": [ln["bbox"] for ln in near]}
    return out


class ScopeResolver:
    """Scope of plan views for the column schedules of one document."""

    def __init__(self, document: Dict[str, Any], elevations: List[Dict[str, Any]]):
        self.document = document
        self.box = display_boxes(document)
        schedules = (document.get("column_schedules") or {}).get("schedules") or []
        self.terms = {s["id"]: scope_terms(s.get("caption") or s.get("title")) for s in schedules}
        common = set.intersection(*self.terms.values()) if len(self.terms) > 1 else set()
        self.own = {sid: terms - common for sid, terms in self.terms.items()}
        self.levels = {s["id"]: {round(v["inches"], 2) for line in s.get("level_lines") or []
                                 if (v := parse_elevation(line.get("elevation_text") or ""))}
                       for s in schedules}
        self.sheet_titles = sheet_titles(document)
        self.views: Dict[int, List[tuple]] = defaultdict(list)
        meta = {int(p.get("page_number") or 0): p for p in document.get("pages") or []}
        for line, text in _wrapped_lines(_displayed_lines(document)):
            page = int(line.get("page_number") or 0)
            width = float((meta.get(page) or {}).get("width") or 0)
            if _PLAN_TITLE_RE.search(text) and len(text) <= 90 and "NOTES" not in text.upper() \
                    and not (width and line["bbox"][0] > 0.84 * width):
                self.views[page].append((text, line["bbox"]))
        # Datum / named plan elevations per page (read values only).
        self.page_levels: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for e in elevations:
            if e.get("status") == "read" and e.get("value") and e.get("name"):
                self.page_levels[e["page"]].append(e)
        self.family = self._sheet_families()

    def _view_title(self, page: int, point_pdf: List[float]) -> Optional[Dict[str, Any]]:
        point = self.box(page, point_pdf)
        if not point:
            return None
        x, y = (point[0] + point[2]) / 2, (point[1] + point[3]) / 2
        # A view's title is printed under it, at its lower left: the nearest
        # title row below the point, and in that row the nearest title starting
        # at or left of it.
        below = [(round((bbox[1] - y) / 40), x - bbox[0], text, bbox) for text, bbox in self.views.get(page, [])
                 if bbox[1] > y and bbox[0] <= x + 50]
        if not below:
            return None
        _row, _left, text, bbox = min(below, key=lambda b: (b[0], abs(b[1])))
        return {"text": text, "bbox": bbox}

    def _datum_schedules(self, page: int) -> Dict[str, List[Dict[str, Any]]]:
        """Schedules a page's read level elevations tie it to (uniquely)."""

        out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for e in self.page_levels.get(page, []):
            inches = round(e["value"]["inches"], 2)
            owners = [sid for sid, levels in self.levels.items() if inches in levels]
            if len(owners) == 1:
                out[owners[0]].append(e)
        return out

    def _sheet_families(self) -> Dict[frozenset, set]:
        """Title-block scope words -> schedules the datum notes of such sheets
        tie them to. One schedule only means the family is that schedule's."""

        family: Dict[frozenset, set] = defaultdict(set)
        for page, title in self.sheet_titles.items():
            terms = frozenset(scope_terms(title["text"]))
            if terms:
                family[terms].update(self._datum_schedules(page))
        return family

    def scope(self, schedule_id: str, page: int, point_pdf: Optional[List[float]] = None) -> Dict[str, Any]:
        """``point_pdf``: where on the page (the view under it); without one,
        the sheet's title-block title alone."""

        view = self._view_title(page, point_pdf) if point_pdf else None
        sheet = self.sheet_titles.get(page)
        title = (view or {}).get("text") or (sheet or {}).get("text")
        terms = scope_terms(title) if title else set()
        record: Dict[str, Any] = {"view_title": view and view["text"], "sheet_title": sheet and sheet["text"],
                                  "scope_words": sorted(terms), "schedule_scope": sorted(self.own.get(schedule_id, set()))}
        if view:
            record["view_title_bbox"] = view["bbox"]
        if len(self.own) <= 1:
            return {**record, "status": "single_schedule",
                    "note": "The set has one column schedule; scope is not compared."}
        others = {w for sid, own in self.own.items() if sid != schedule_id for w in own}
        if terms & others:
            return {**record, "status": "conflicting",
                    "note": f"The view is titled for {', '.join(sorted(terms & others))}, another schedule's scope."}
        if terms & self.own.get(schedule_id, set()):
            return {**record, "status": "consistent", "note": f"The view title names {', '.join(sorted(terms & self.own[schedule_id]))}."}
        datum = self._datum_schedules(page)
        if schedule_id in datum and len(datum) == 1:
            e = datum[schedule_id][0]
            return {**record, "status": "supported_by_datum",
                    "note": f"The plan's note names {e['name']} at {e['value']['display']}, a level of this schedule only.",
                    "evidence": e.get("source")}
        tied = self.family.get(frozenset(scope_terms((sheet or {}).get("text"))), set())
        if sheet and tied == {schedule_id}:
            return {**record, "status": "consistent_by_sheet_family",
                    "note": "Sheets titled with the same scope words are tied to this schedule by their datum notes."}
        return {**record, "status": "unresolved",
                "note": "Nothing printed ties this view to this schedule's building or area."}


def _displayed_lines(document: Dict[str, Any]) -> Dict[str, Any]:
    box = display_boxes(document)
    return {"lines": [{**ln, "bbox": box(int(ln.get("page_number") or 0), ln.get("bbox"))}
                      for ln in document.get("lines") or [] if len(ln.get("bbox") or []) >= 4]}
