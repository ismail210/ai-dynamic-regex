"""Scale of one drawing view, and whether the drawing's own dimensions bear it out.

Evidence for the column-tracing pilot only (production keeps
``drawing_scale.resolve_page_scale``). Scale belongs to a view, not to the
sheet: Brandywine prints "SCALE : 1/8" = 1'-0"" in every title block, also
on detail sheets of 3/8" views and on S-120, whose view is titled
"LEVEL 2 FRAMING PLAN - OVERALL / 1" = 20'-0"".

Three kinds of evidence are kept apart:

* **printed** -- the scale printed under the view's title (``1/8" = 1'-0"``),
  or NTS printed there;
* **sheet** -- the title-block scale; recorded, never used on its own;
* **calibration** -- PDF points per real inch measured from the drawing: the
  distance between two adjacent parallel grid lines divided by the grid
  dimension printed between them (``29'-0"``), when several bays agree.

Status: ``validated`` (printed and calibration agree within 2 %),
``calibrated`` (no printed scale; at least three bays agree), ``printed``
(printed, nothing to check it against), ``conflicting`` (printed and
calibration disagree), ``nts``, ``unresolved``. Only ``validated`` and
``calibrated`` may place anything physically. PDF space is points; one real
inch is ``points_per_inch`` PDF points on this view (independent of /Rotate,
since rotation preserves distances).
"""

from __future__ import annotations

import math
import re
from statistics import median
from typing import Any, Dict, List, Optional

from services.engineering.column_schedule import parse_length
from services.engineering.drawing_scale import _NOT_TO_SCALE, detect_page_scales, parse_scale_text
from services.engineering.level_evidence import _clean

AGREE = 0.02
_MIN_BAYS = 3
_MIN_BAY_POINTS = 20.0
PLACES = frozenset({"validated", "calibrated"})


def _normal(angle: float) -> tuple:
    """Unit normal of a line at ``angle`` degrees; the line is ``n . p = c``."""

    rad = math.radians(angle)
    return math.sin(rad), -math.cos(rad)


def _parallel(a: Dict[str, Any], b: Dict[str, Any], tolerance: float = 1.0) -> bool:
    d = abs(a["angle"] - b["angle"]) % 180
    return min(d, 180 - d) <= tolerance


def printed_view_scale(lines: List[Dict[str, Any]], title_bbox: Optional[List[float]]) -> Optional[Dict[str, Any]]:
    """Scale printed directly under a view title (display-space lines of the page)."""

    if not title_bbox:
        return None
    x0, _y0, _x1, y1 = title_bbox
    under = [ln for ln in lines if y1 - 2 <= ln["bbox"][1] <= y1 + 40 and x0 - 40 <= ln["bbox"][0] <= x0 + 320]
    text = " ".join(_clean(ln.get("text")) for ln in sorted(under, key=lambda ln: (ln["bbox"][1], ln["bbox"][0])))
    if not text:
        return None
    parsed = parse_scale_text(text, source="view_title")
    if parsed:
        return {"raw": parsed.raw, "points_per_inch": parsed.pdf_points_per_real_inch, "nts": False}
    if nts := _NOT_TO_SCALE.search(text):
        return {"raw": nts.group(0), "points_per_inch": None, "nts": True}
    return None


def sheet_scales(document: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """The title-block scale of each page (``drawing_scale``), as printed."""

    return {page: {"raw": found.raw, "points_per_inch": found.pdf_points_per_real_inch}
            for page, found in detect_page_scales(document).items() if found.source == "title_block"}


def grid_calibration(axes: Dict[str, List[Dict[str, Any]]], lines: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Points per inch from printed grid dimensions (PDF-space axes and lines).

    Axes are lines ``n . p = c`` at ``angle`` degrees (``column_trace``), so
    slanted grids calibrate too: for each pair of adjacent parallel grid lines,
    a feet-inch dimension printed between them gives one ratio (perpendicular
    distance / printed inches); the ratio most bays agree on (within 1 %) is
    the calibration, with the bays it rests on."""

    dims = []
    for ln in lines:
        text = _clean(ln.get("text"))
        value = parse_length(text)
        # A full feet-inch dimension (12'-0"); a primed grid label (7') is not one.
        if value and value["unit"] == "ft-in" and value["inches"] >= 12 and re.search(r"'\s*-?\s*\d", text):
            b = ln["bbox"]
            dims.append(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, value["inches"], text))
    bays = []
    groups: Dict[float, List[tuple]] = {}
    for name, found in axes.items():
        for axis in found:
            key = next((k for k in groups if _parallel({"angle": k}, axis)), axis["angle"])
            groups.setdefault(key, []).append((axis["c"], name))
    # The same grid name twice in one direction: the sheet shows several views,
    # so the pooled ratio is not known to belong to any one of them.
    several_views = any(len({n for _c, n in members}) < len(members) for members in groups.values())
    for angle, members in groups.items():
        nx, ny = _normal(angle)
        seq = sorted(members)
        for (a, na), (b, nb) in zip(seq, seq[1:]):
            if b - a < _MIN_BAY_POINTS:
                continue
            for dim in dims:
                if a < nx * dim[0] + ny * dim[1] < b:
                    bays.append({"ratio": (b - a) / dim[2], "grids": [na, nb], "printed": dim[3], "gap_points": round(b - a, 1)})
    if not bays:
        return None
    best = max(bays, key=lambda bay: sum(abs(o["ratio"] - bay["ratio"]) <= 0.01 * bay["ratio"] for o in bays))
    agreeing = [o for o in bays if abs(o["ratio"] - best["ratio"]) <= 0.01 * best["ratio"]]
    if len(agreeing) < _MIN_BAYS:
        return {"points_per_inch": None, "bays": agreeing, "note": f"only {len(agreeing)} grid bays agree"}
    return {"points_per_inch": round(median(o["ratio"] for o in agreeing), 5), "bays": agreeing[:6],
            "bay_count": len(agreeing), "disagreeing_bays": len(bays) - len(agreeing), "several_views": several_views}


def resolve_view_scale(printed: Optional[Dict[str, Any]], sheet: Optional[Dict[str, Any]],
                       calibration: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    measured = (calibration or {}).get("points_per_inch")
    record: Dict[str, Any] = {"printed": printed, "sheet": sheet, "calibration": calibration, "points_per_inch": None}
    if printed and printed["nts"]:
        return {**record, "status": "nts", "note": "The view is marked not to scale; nothing is placed."}
    if printed and measured:
        ratio = measured / printed["points_per_inch"]
        if abs(ratio - 1) <= AGREE:
            return {**record, "status": "validated", "points_per_inch": measured,
                    "note": f"{printed['raw']} agrees with {calibration['bay_count']} printed grid dimensions."}
        return {**record, "status": "conflicting",
                "note": f"{printed['raw']} disagrees with the printed grid dimensions (×{ratio:.3f}); nothing is placed."}
    if measured and calibration["several_views"]:
        return {**record, "status": "unresolved",
                "note": "No scale is printed for the view, and the sheet's grid dimensions span several views."}
    if measured:
        return {**record, "status": "calibrated", "points_per_inch": measured,
                "note": f"Calibrated from {calibration['bay_count']} printed grid dimensions; no scale printed for the view."}
    if printed:
        note = "Printed for the view; no printed grid dimension to check it against."
        if sheet and abs(sheet["points_per_inch"] / printed["points_per_inch"] - 1) > AGREE:
            note += f" The title block says {sheet['raw']}."
        return {**record, "status": "printed", "note": note}
    note = "No scale is printed for the view and no grid dimensions calibrate it."
    if sheet:
        note += f" The title block's {sheet['raw']} is not used on its own."
    return {**record, "status": "unresolved", "note": note}

