"""Column schedules: per-column entries with section, locations, plate and notes.

Reads the column schedules ``schedule_tables`` finds (Revit / graphical
matrices with level rows and a ``Column Locations`` or ``MARK`` row) into one
entry per schedule column, keeping the printed text next to what was parsed.

Display and evidence only. Nothing here feeds ``schedule_mark_map``,
prediction or quantities: an entry is a definition, and a listed location is
schedule evidence, not a counted member.

Parsing never repairs drafting: text that does not read as a grid
intersection, plate size or sheet reference keeps its raw text and an
``unresolved`` / ``unreadable`` status.
"""

from __future__ import annotations

import re
from collections import Counter
from fractions import Fraction
from typing import Any, Dict, List, Optional

# One grid name: letters with optional digits/decimal (C, C.1, RA.1, R13, X4)
# or a number with optional decimal (02, 5.1, 10.7); then optional primes.
_GRID_NAME = r"(?:[A-Z]{1,3}\d{0,3}(?:\.\d{1,3})?|\d{1,3}(?:\.\d{1,3})?)"
_PRIMES = r"(?:''|\"|'|′′|″|′)?"
_OFFSET = r"\(\s*[^()]*?\s*\)"
_LOCATION_RE = re.compile(
    rf"^(?P<g1>{_GRID_NAME})(?P<p1>{_PRIMES})\s*(?P<o1>{_OFFSET})?"
    rf"\s*[-–]\s*"
    rf"(?P<g2>{_GRID_NAME})(?P<p2>{_PRIMES})\s*(?P<o2>{_OFFSET})?$"
)
# Feet-inches / inches inside an offset: -4'-4", 1'-10", 5' - 4", 6", 3 1/2"
_LENGTH_RE = re.compile(
    r"^(?P<sign>[-+−–])?\s*"
    r"(?:(?P<ft>\d+)\s*'\s*-?\s*)?"
    r"(?:(?P<in>\d+(?:\s+\d+/\d+|-\d+/\d+)?|\d+/\d+)\s*\")?$"
)
_DIMENSION_RE = re.compile(
    r"^(?:(?P<ft>\d+)\s*'\s*-?\s*)?"
    r"(?P<in>\d+(?:\s+\d+/\d+|-\d+/\d+)?|\d+/\d+|\d+\.\d+)\s*\"$"
)
_FEET_ONLY_RE = re.compile(r"^(?P<ft>\d+)\s*'\s*-?\s*0?\s*$")
_PLATE_PREFIX_RE = re.compile(r"^(?:PL|PLATE)\.?\s+", re.IGNORECASE)
_MARKER_RE = re.compile(r"\s*(\*+|\(T\)|\bT\b)\s*$")
_NOT_APPLICABLE_RE = re.compile(r"^(?:[-–—]+|N/?A|NONE)$", re.IGNORECASE)
_SHEET = r"[A-Z]{1,2}-?\d{1,4}(?:\.\d{1,3})?[A-Z]?(?:-[A-Z])?"
_REFERENCE_RE = re.compile(rf"(?<![A-Z0-9/])([A-Z0-9]{{1,3}})\s*/\s*({_SHEET})(?![A-Z0-9/])")


def _inches(value: str) -> float:
    """``1 1/4`` / ``1-1/4`` / ``3/4`` / ``18`` / ``2.5`` -> inches."""

    value = value.strip().replace("-", " ")
    total = Fraction(0)
    for part in value.split():
        total += Fraction(part)
    return float(total)


def parse_length(text: str) -> Optional[Dict[str, Any]]:
    """Signed feet-inches or inches length; ``None`` when the text is not one."""

    raw = " ".join(str(text or "").split())
    match = _LENGTH_RE.fullmatch(raw)
    if not raw or not match or not (match["ft"] or match["in"]):
        return None
    inches = float(int(match["ft"] or 0) * 12) + (_inches(match["in"]) if match["in"] else 0.0)
    negative = (match["sign"] or "") in {"-", "−", "–"}
    return {
        "raw": raw,
        "inches": -inches if negative else inches,
        "unit": "ft-in" if match["ft"] else "in",
        # A schedule offset names its grid, never the direction along it.
        "direction": None,
    }


def _grid(name: str, primes: str, offset_text: Optional[str]) -> Optional[Dict[str, Any]]:
    offset = None
    if offset_text:
        offset = parse_length(offset_text.strip()[1:-1])
        if offset is None:
            return None
    count = {"": 0, "'": 1, "′": 1, "''": 2, '"': 2, "″": 2, "′′": 2}[primes]
    return {"label": f"{name}{primes}", "name": name, "primes": count, "offset": offset}


def parse_grid_location(text: str) -> Dict[str, Any]:
    """``C.6(1'-10")-1`` -> two grids (the first with a +22" offset).

    The hyphen between grids is the separator; a sign or feet-inches hyphen
    only occurs inside the offset parentheses. Leading zeros and primes are
    part of the grid name (``02`` is not ``2``; ``A.1'`` is not ``A.1``).
    """

    raw = str(text or "")
    match = _LOCATION_RE.fullmatch(" ".join(raw.split()).upper())
    grids = []
    if match:
        grids = [
            _grid(match["g1"], match["p1"], match["o1"]),
            _grid(match["g2"], match["p2"], match["o2"]),
        ]
    if not match or None in grids:
        return {
            "raw": raw,
            "status": "unresolved",
            "grids": [],
            "reason": "not a grid intersection the schedule format supports",
        }
    return {"raw": raw, "status": "parsed", "grids": grids, "reason": None}


def split_locations(text: str) -> List[str]:
    """Comma / semicolon separated locations, never splitting inside ``( )``."""

    parts: List[str] = []
    current: List[str] = []
    depth = 0
    for char in str(text or ""):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char in ",;" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [" ".join(part.split()) for part in parts if part.strip()]


def parse_dimension(text: str) -> Optional[Dict[str, Any]]:
    raw = " ".join(str(text or "").split())
    match = _DIMENSION_RE.fullmatch(raw)
    if match:
        inches = float(int(match["ft"] or 0) * 12) + _inches(match["in"])
        return {"raw": raw, "inches": inches}
    match = _FEET_ONLY_RE.fullmatch(raw)
    if match:
        return {"raw": raw, "inches": float(int(match["ft"]) * 12)}
    return None


def parse_drawing_reference(text: str) -> Optional[Dict[str, str]]:
    """``D/S-201`` / ``7/S400`` / ``SEE S/S502`` -> detail id and sheet id."""

    match = _REFERENCE_RE.search(" ".join(str(text or "").split()).upper())
    if not match:
        return None
    return {"raw": match.group(0), "detail": match.group(1), "sheet": match.group(2)}


def parse_plate_cell(text: str) -> Dict[str, Any]:
    """A plate cell as printed: dimensions, a reference, N/A, blank or unreadable.

    Dimensions stay in printed order with their raw text; which one is the
    thickness is decided by the schedule's own headings, not here. An
    incomplete size keeps only the dimensions it prints.
    """

    raw = " ".join(str(text or "").split())
    result: Dict[str, Any] = {
        "raw": raw, "status": "blank", "dimensions": [], "markers": [], "reference": None,
    }
    if not raw:
        return result
    if _NOT_APPLICABLE_RE.fullmatch(raw):
        result["status"] = "not_applicable"
        return result
    body = raw
    marker = _MARKER_RE.search(body)
    if marker and re.search(r"[x×X]", body):
        result["markers"] = [marker.group(1)]
        body = body[: marker.start()]
    body = _PLATE_PREFIX_RE.sub("", body.strip())
    parts = [part for part in re.split(r"\s*[xX×]\s*", body) if part]
    dimensions = [parse_dimension(part) for part in parts]
    if dimensions and all(dimensions):
        result["status"] = "dimensions"
        result["dimensions"] = dimensions
        return result
    reference = parse_drawing_reference(raw)
    if reference:
        result["status"] = "reference"
        result["reference"] = reference
        return result
    result["status"] = "unreadable"
    return result


# --------------------------------------------------------------------------
# Visible text
# --------------------------------------------------------------------------
def _is_white(color: Any) -> bool:
    return bool(color) and len(color) >= 3 and all(float(v) > 0.97 for v in color[:3])


def _box(rect: Any) -> List[float]:
    return [round(float(v), 1) for v in list(rect)[:4]]


def visible_phrases(page: Any, drawings: Optional[List[dict]] = None) -> tuple:
    """``(visible, suppressed)`` text runs of ``page`` as drawn.

    Edited sheets keep obsolete text under opaque white boxes. A character is
    suppressed only when a white fill painted *after* it covers its center,
    or when it is drawn invisibly (render mode 3, zero opacity, white). Text
    drawn on top of a white box stays visible, and a white box drawn before
    the text (a cell background) hides nothing.

    Each run is ``{"text", "bbox", "vertical", "size"}``; runs continuing one
    baseline are joined across PDF text objects.
    """

    fills = [
        (int(d.get("seqno") or 0), d["rect"])
        for d in (drawings if drawings is not None else page.get_drawings())
        if _is_white(d.get("fill"))
        and float(1.0 if d.get("fill_opacity") is None else d["fill_opacity"]) > 0.9
        and d["rect"].width > 1 and d["rect"].height > 1
    ]
    runs: List[dict] = []
    for trace in page.get_texttrace():
        seqno = int(trace.get("seqno") or 0)
        invisible = (
            trace.get("type") == 3
            or float(trace.get("opacity", 1.0) or 0.0) == 0.0
            or _is_white(trace.get("color"))
        )
        # Only fills painted later and overlapping this text object can hide it.
        tx0, ty0, tx1, ty1 = trace["bbox"]
        later = [] if invisible else [
            rect for fseq, rect in fills
            if fseq > seqno and rect.x0 <= tx1 and rect.x1 >= tx0 and rect.y0 <= ty1 and rect.y1 >= ty0
        ]
        dx, dy = trace.get("dir") or (1.0, 0.0)
        size = float(trace.get("size") or 1.0)
        current: Optional[dict] = None
        previous = None
        previous_end = 0.0
        for code, _gid, origin, bbox in trace.get("chars") or ():
            char = chr(code)
            x0, y0, x1, y1 = bbox
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            hidden = invisible or any(r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1 for r in later)
            extent = [x0 * dx + y0 * dy, x1 * dx + y1 * dy, x0 * dx + y1 * dy, x1 * dx + y0 * dy]
            if previous is not None:
                ddx, ddy = origin[0] - previous[0], origin[1] - previous[1]
                along, perp = ddx * dx + ddy * dy, abs(ddy * dx - ddx * dy)
                if perp > 0.6 * size or along < -0.3 * size or along > 1.6 * size:
                    current = None
                elif (
                    current is not None and not char.isspace()
                    and not current["chars"][-1][0].isspace()
                    and min(extent) - previous_end > 0.2 * size
                ):
                    # Positioned glyphs with no space character (``PARKING -GCS``).
                    current["chars"].append((" ", (x0, y0, x1, y1), origin))
            previous = origin
            previous_end = max(extent)
            if current is not None and not char.isspace() and current["hidden"] != hidden:
                current = None
            if current is None:
                if char.isspace():
                    continue
                current = {"chars": [], "hidden": hidden, "dir": (dx, dy), "size": size}
                runs.append(current)
            current["chars"].append((char, (x0, y0, x1, y1), origin))
    visible: List[dict] = []
    suppressed: List[dict] = []
    for run in _join_runs(runs):
        (suppressed if run.pop("hidden") else visible).append(run)
    return visible, suppressed


def _join_runs(runs: List[dict]) -> List[dict]:
    """Join runs that continue one another on a baseline (``1'`` ``-`` ``2"``)."""

    keyed = []
    for run in runs:
        dx, dy = run["dir"]
        first = run["chars"][0]
        last = next(c for c in reversed(run["chars"]) if not c[0].isspace())
        start = first[2][0] * dx + first[2][1] * dy
        bx0, by0, bx1, by1 = last[1]
        end = max(bx0 * dx + by0 * dy, bx1 * dx + by1 * dy, bx0 * dx + by1 * dy, bx1 * dx + by0 * dy)
        base = first[2][1] * dx - first[2][0] * dy
        keyed.append(((round(dx, 2), round(dy, 2), run["hidden"]), base, start, end, run))
    keyed.sort(key=lambda k: (k[0], round(k[1]), k[2]))
    joined: List[dict] = []
    last = None
    for key, base, start, end, run in keyed:
        size = run["size"]
        if (
            last is not None
            and last[0] == key
            and abs(last[1] - base) < 0.4 * size
            # Only touching pieces: adjacent table cells sit ~half a glyph apart.
            and -0.3 * size <= start - last[3] <= 0.3 * size
        ):
            target = last[4]
            if start - last[3] > 0.15 * size:
                target["chars"].append((" ", run["chars"][0][1], run["chars"][0][2]))
            target["chars"].extend(run["chars"])
            last = (key, base, last[2], max(end, last[3]), target)
            continue
        joined.append(run)
        last = (key, base, start, end, run)
    out = []
    for run in joined:
        boxes = [c[1] for c in run["chars"] if not c[0].isspace()]
        dx, dy = run["dir"]
        out.append({
            "text": " ".join("".join(c[0] for c in run["chars"]).split()),
            "bbox": [round(min(b[0] for b in boxes), 1), round(min(b[1] for b in boxes), 1),
                     round(max(b[2] for b in boxes), 1), round(max(b[3] for b in boxes), 1)],
            "vertical": abs(dy) > abs(dx),
            "size": run["size"],
            "hidden": run["hidden"],
            "glyphs": [(c[0], c[1]) for c in run["chars"]],
        })
    return out


def _center(bbox: List[float]) -> tuple:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _inside(bbox: List[float], rect: List[float], pad: float = 0.5) -> bool:
    cx, cy = _center(bbox)
    return rect[0] - pad <= cx <= rect[2] + pad and rect[1] - pad <= cy <= rect[3] + pad


def _clip_phrase(phrase: dict, rect: List[float]) -> Optional[dict]:
    """``phrase`` cut to the glyphs whose centers fall inside ``rect``."""

    cy = _center(phrase["bbox"])[1]
    if not rect[1] - 0.5 <= cy <= rect[3] + 0.5:
        return None
    if phrase["vertical"] or (phrase["bbox"][0] >= rect[0] - 0.5 and phrase["bbox"][2] <= rect[2] + 0.5):
        return phrase if _inside(phrase["bbox"], rect) else None
    glyphs = [g for g in phrase["glyphs"] if rect[0] <= (g[1][0] + g[1][2]) / 2.0 <= rect[2]]
    text = " ".join("".join(g[0] for g in glyphs).split())
    if not text:
        return None
    boxes = [g[1] for g in glyphs]
    return {**phrase, "text": text, "bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                                             max(b[2] for b in boxes), max(b[3] for b in boxes)]}


def _reading_order(phrases: List[dict]) -> str:
    """Horizontal lines top to bottom; rotated labels left to right."""

    ordered = sorted(
        phrases,
        key=lambda p: (0, round(p["bbox"][0]), -p["bbox"][3]) if p["vertical"]
        else (1, round(p["bbox"][1] / 3.0), p["bbox"][0]),
    )
    return " ".join(p["text"] for p in ordered).strip()


# --------------------------------------------------------------------------
# Column matrices (graphical / Revit column schedules)
# --------------------------------------------------------------------------
_KEY_LOCATION_RE = re.compile(r"\bLOCATIONS?\b")
_KEY_MARK_RE = re.compile(r"^(?:COLUMN\s+)?MARK\b")
_PLATE_ROW_RE = re.compile(r"\b(BASE|BEARING|CAP)\s*PLATE")
_REMARK_ROW_RE = re.compile(r"\b(?:REMARKS?|NOTES?|COMMENTS?)\b")
_ATTRIBUTE_ROW_RE = re.compile(
    r"ANCHOR|BOLT|\bRODS?\b|PIER|REINF|LOAD|REACTION|KIPS|FOOTING|EMBED|SPLICE|WELD|TIES"
    r"|\bQTY\b|QUANTITY"
)
_PLATE_MARK_RE = re.compile(r"^(?:BP|CBP)-?\d+[A-Z]?$")
_LOAD_RE = re.compile(r"^(?:DL|LL|SL|WL|D|L)\s*=|\bKIPS?\b", re.IGNORECASE)
_PIER_RE = re.compile(r"^P-?\d+[A-Z]?\b")
_SIZE_LIKE_RE = re.compile(r"\d+\s*\"?\s*[xX×]\s*\d+")


def matrix_key_role(labels: List[str]) -> Optional[str]:
    """``location`` / ``mark`` when a label column names the schedule's key row."""

    upper = [" ".join(str(label or "").split()).upper() for label in labels]
    if any("COLUMN" in label and _KEY_LOCATION_RE.search(label) for label in upper):
        return "location"
    if any(_KEY_MARK_RE.match(label) for label in upper) and any(
        _PLATE_ROW_RE.search(label) for label in upper
    ):
        return "mark"
    return None


def _cell_rect(table: Any, row: int, column: int) -> Optional[List[float]]:
    try:
        cell = table.rows[row].cells[column]
    except (AttributeError, IndexError):
        return None
    return [float(v) for v in cell] if cell else None


def _label_column_rect(table: Any, column: int) -> Optional[List[float]]:
    # A title row is one cell spanning the table; it says nothing about the
    # label column's width.
    half = (float(table.bbox[2]) - float(table.bbox[0])) / 2.0
    rects = [_cell_rect(table, row, column) for row in range(len(table.rows))]
    rects = [r for r in rects if r and r[2] - r[0] < half]
    if not rects:
        return None
    return [min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects)]


def _row_category(label: str, role: str) -> str:
    upper = label.upper()
    if (role == "location" and "COLUMN" in upper and _KEY_LOCATION_RE.search(upper)) or (
        role == "mark" and _KEY_MARK_RE.match(upper)
    ):
        return "key"
    if _PLATE_ROW_RE.search(upper):
        return "plate"
    if _REMARK_ROW_RE.search(upper):
        return "remark"
    if _ATTRIBUTE_ROW_RE.search(upper):
        return "attribute"
    return "level"


def read_column_matrix(
    table: Any,
    page_number: int,
    visible: List[dict],
    suppressed: List[dict],
    *,
    catalog_fn: Any = None,
    drawings: Optional[List[dict]] = None,
) -> Optional[Dict[str, Any]]:
    """One entry per schedule column of a level/row-labelled column matrix.

    ``find_tables`` supplies only cell geometry; every value is read from the
    visible text inside the cell, so masked text never reaches an entry.
    Section labels are whole drawn labels: in graphical schedules they cross
    the level lines that split table cells.
    """

    from services.engineering.schedule_grid import _catalog_accepts, section_from_size_text

    accept = catalog_fn or _catalog_accepts
    rows = list(table.rows or [])
    column_count = len(rows[0].cells) if rows else 0
    if column_count < 3:
        return None
    table_box = [float(v) for v in table.bbox]
    in_table = [p for p in visible if _inside(p["bbox"], table_box, pad=1.0)]
    hidden = [p for p in suppressed if _inside(p["bbox"], table_box, pad=1.0)]

    def text_in(rect: Optional[List[float]], pool: Optional[List[dict]] = None) -> str:
        if not rect:
            return ""
        return _reading_order([p for p in (in_table if pool is None else pool) if _inside(p["bbox"], rect)])

    def cell_text(rect: Optional[List[float]]) -> str:
        """Text drawn in ``rect``; a label overflowing into the next cell
        (``...RA.1R13...``) is split at the cell edge by glyph position."""

        if not rect:
            return ""
        return _reading_order([p for p in (_clip_phrase(p, rect) for p in in_table) if p])

    def row_rect(index: int, x0: float, x1: float) -> List[float]:
        return [x0, float(rows[index].bbox[1]), x1, float(rows[index].bbox[3])]

    label_col = role = label_rect = None
    row_labels: List[str] = []
    for column in (0, column_count - 1):
        rect = _label_column_rect(table, column)
        if not rect:
            continue
        labels = [text_in(row_rect(i, rect[0], rect[2])) for i in range(len(rows))]
        found = matrix_key_role(labels)
        if found:
            label_col, role, label_rect, row_labels = column, found, rect, labels
            break
    if role is None:
        return None
    categories = [_row_category(label, role) for label in row_labels]
    key_rows = [i for i, c in enumerate(categories) if c == "key"]

    # Schedule columns: the text-bearing cells of the fullest key row.
    def key_cells(index: int) -> List[List[float]]:
        cells = []
        for column in range(column_count):
            rect = _cell_rect(table, index, column)
            if column == label_col or not rect:
                continue
            if rect[0] >= label_rect[0] - 0.5 and rect[2] <= label_rect[2] + 0.5:
                continue
            text = cell_text(rect)
            if text and not matrix_key_role([text]):
                cells.append([rect[0], rect[2]])
        return cells

    bands = max((key_cells(i) for i in key_rows), key=len, default=[])
    if not bands:
        return None
    bands.sort()

    def row_of(phrase: dict) -> Optional[int]:
        cy = _center(phrase["bbox"])[1]
        for index, row in enumerate(rows):
            if float(row.bbox[1]) - 0.5 <= cy <= float(row.bbox[3]) + 0.5:
                return index
        return None

    # Raw level-row labels for the later levels work. A row band pairs one
    # level line's elevation with the next line's name, so nothing is paired.
    levels = [
        {"label": row_labels[i], "bbox": _box(row_rect(i, label_rect[0], label_rect[2]))}
        for i, c in enumerate(categories) if c == "level" and row_labels[i]
    ]
    def level_line(line: Dict[str, Any]) -> bool:
        """Named from a level row, not from a BASE PLATE / LOADS row. A name in
        the key row's cell (WL ``COLUMN LOCATIONS / ROOF LEVEL``) counts only
        with a value under it, so the ``MARK / FLOOR`` header word does not."""

        if line["name"] is None:
            return line["elevation_text"] is not None
        if _row_category(line["name"], role) != "level":
            return False
        index = row_of({"bbox": line["name_bbox"]})
        category = categories[index] if index is not None else "level"
        return category == "level" or (category == "key" and line["elevation_text"] is not None)

    lines = [line for line in _level_lines(table_box, label_rect, in_table, drawings or []) if level_line(line)]
    strokes = _column_strokes(table_box, drawings or [])
    columns: List[Dict[str, Any]] = []
    for x0, x1 in bands:
        band = [
            p for p in in_table
            if x0 - 0.5 <= _center(p["bbox"])[0] <= x1 + 0.5
            and (p["bbox"][2] - p["bbox"][0]) <= 1.5 * (x1 - x0) + 2.0
            and "SCHEDULE" not in p["text"].upper()
        ]
        keys = [
            {"text": cell_text(row_rect(i, x0, x1)), "bbox": _box(row_rect(i, x0, x1))}
            for i in key_rows
        ]
        keys = [k for k in keys if k["text"]]
        if not keys:
            continue
        sections: List[Dict[str, Any]] = []
        plate_marks: List[Dict[str, Any]] = []
        notes: List[Dict[str, Any]] = []
        supports: list[dict[str, Any]] = []
        for phrase in band:
            index = row_of(phrase)
            if index is not None and categories[index] != "level":
                continue
            text = phrase["text"]
            compact = re.sub(r"\s+", "", text).upper()
            level = (row_labels[index] if index is not None else "") or None
            section = section_from_size_text(text, accept)
            if section:
                sections.append({"printed": text, "section": section, "label_band": level, "bbox": phrase["bbox"]})
            elif _PLATE_MARK_RE.fullmatch(compact):
                plate_marks.append({"text": compact, "bbox": phrase["bbox"]})
            elif _LOAD_RE.search(text):
                continue
            elif _SIZE_LIKE_RE.search(text) and not _PIER_RE.match(compact):
                sections.append({"printed": text, "section": None, "label_band": level, "bbox": phrase["bbox"]})
            elif _PIER_RE.match(compact):
                # A pier drawn under the column (OSSE C.8-8.9 "P1 - 18 x 20"):
                # what supports it, kept as printed; never a column section.
                supports.append({"printed": text, "mark": _PIER_RE.match(compact).group(0),
                                 "label_band": level, "bbox": phrase["bbox"]})
            elif re.search(r"[A-Z]{2,}", text.upper()):
                notes.append({"text": text, "bbox": phrase["bbox"]})
        plates: List[Dict[str, Any]] = []
        supplementary: Dict[str, str] = {}
        for index, category in enumerate(categories):
            if category not in ("plate", "remark", "attribute"):
                continue
            rect = row_rect(index, x0, x1)
            text = cell_text(rect)
            if category == "plate":
                # find_tables can split one ruled row into nested sub-rows.
                if not any(p["label"] == row_labels[index] and p["text"] == text for p in plates):
                    plates.append({"label": row_labels[index], "text": text, "bbox": _box(rect)})
            elif text and category == "remark":
                notes.append({"text": text, "bbox": _box(rect)})
            elif text:
                supplementary[row_labels[index]] = text
        sections.sort(key=lambda s: s["bbox"][1])
        band_rect = [x0, table_box[1], x1, table_box[3]]
        columns.append({
            "key": keys[0]["text"],
            "key_bbox": keys[0]["bbox"],
            "key_repeats": [k["text"] for k in keys[1:]],
            "sections": sections,
            "plate_marks": plate_marks,
            "plates": plates,
            "notes": notes,
            "supports": supports,
            "supplementary": supplementary,
            "suppressed_text": [p["text"] for p in hidden if _inside(p["bbox"], band_rect)],
            "bbox": _box(band_rect),
            "extent": _column_extent(x0, x1, strokes, lines),
        })
    if not columns:
        return None
    return {
        "page": page_number,
        "bbox": _box(table_box),
        "key_role": role,
        "label_side": "left" if label_col == 0 else "right",
        "layout": "graphical" if categories.count("level") >= 2 else "matrix",
        "levels": levels,
        "level_lines": lines,
        "columns": columns,
        "suppressed_text": [{"text": p["text"], "bbox": p["bbox"]} for p in hidden],
    }


# A level label sits against its line: the name just above, the elevation
# just below (Revit graphical schedules). Farther text is not attached.
_LEVEL_TEXT_REACH = 30.0
_ON_LINE = 3.0
# Drawn columns sit mid-band; cell rules sit on band edges and are hairlines.
_COLUMN_STROKE_MIN_WIDTH = 0.4
# An end drawn within about a text height of a line is reported as near it
# (Revit draws top offsets), but stays "between": it is never snapped.
_NEAR_LINE = 8.0


def _level_lines(table_box: List[float], label_rect: List[float], phrases: List[dict],
                 drawings: List[dict]) -> List[Dict[str, Any]]:
    """Drawn level lines across the label column, with the name printed just
    above each and the elevation (or SEE PLAN) printed just below.

    Positions are page coordinates of the drawn line; no elevation is ever
    computed from them.
    """

    from services.engineering.level_evidence import is_see_plan, parse_elevation

    x0, x1 = label_rect[0], label_rect[2]
    ys: List[float] = []
    for path in drawings:
        for item in path.get("items") or ():
            if item[0] != "l":
                continue
            a, b = item[1], item[2]
            if abs(a.y - b.y) > 0.8 or not table_box[1] + 1 < a.y < table_box[3] - 1:
                continue
            if min(a.x, b.x) <= x0 + 0.2 * (x1 - x0) and max(a.x, b.x) >= x1 - 0.2 * (x1 - x0):
                if all(abs(a.y - y) > 1.5 for y in ys):
                    ys.append(a.y)
    labels = [p for p in phrases if _inside(p["bbox"], label_rect) and not p["vertical"]]
    ys.sort()

    def nearest_below(phrase: dict) -> Optional[float]:
        return next((y for y in ys if y >= phrase["bbox"][3] - 0.5), None)

    def nearest_above(phrase: dict) -> Optional[float]:
        return next((y for y in reversed(ys) if y <= phrase["bbox"][1] + 0.5), None)

    lines = []
    for y in ys:
        # Each label belongs to one line only: a name to the line right under
        # it, an elevation to the line right over it.
        above = sorted((p for p in labels if y - _LEVEL_TEXT_REACH <= p["bbox"][3] <= y + 0.5
                        and nearest_below(p) == y), key=lambda p: -p["bbox"][3])
        below = sorted((p for p in labels if y - 0.5 <= p["bbox"][1] <= y + _LEVEL_TEXT_REACH
                        and nearest_above(p) == y), key=lambda p: p["bbox"][1])
        name_parts: List[dict] = []
        for phrase in above:
            if parse_elevation(phrase["text"]) or is_see_plan(phrase["text"]):
                break
            if name_parts and name_parts[-1]["bbox"][1] - phrase["bbox"][3] > 6.0:
                break
            name_parts.append(phrase)
        value = next((p for p in below if parse_elevation(p["text"]) or is_see_plan(p["text"])), None)
        if not name_parts and value is None:
            continue
        name_parts.reverse()
        lines.append({
            "y": round(y, 1),
            "name": " ".join(p["text"] for p in name_parts) or None,
            "name_bbox": _union_boxes(p["bbox"] for p in name_parts) if name_parts else None,
            "elevation_text": value["text"] if value else None,
            "elevation_bbox": value["bbox"] if value else None,
        })
    return lines


def _union_boxes(boxes: Any) -> List[float]:
    boxes = list(boxes)
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _column_strokes(table_box: List[float], drawings: List[dict]) -> List[tuple]:
    """``(x, top, bottom)`` of heavy vertical strokes inside the table: the
    drawn columns of a graphical schedule (table rules are hairlines)."""

    strokes = []
    for path in drawings:
        if float(path.get("width") or 0.0) < _COLUMN_STROKE_MIN_WIDTH:
            continue
        for item in path.get("items") or ():
            if item[0] == "l" and abs(item[1].x - item[2].x) < 0.8:
                top, bottom = sorted((item[1].y, item[2].y))
                if (bottom - top > 5 and table_box[0] <= item[1].x <= table_box[2]
                        and table_box[1] - 1 <= top and bottom <= table_box[3] + 1):
                    strokes.append((item[1].x, top, bottom))
    return strokes


def _endpoint(y: float, lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Where a drawn column end sits: on a level line, between two, or
    beyond all of them. Never snapped to the nearest line."""

    def ref(line: Dict[str, Any]) -> Dict[str, Any]:
        return {k: line[k] for k in ("name", "elevation_text", "y")}

    on = [line for line in lines if abs(line["y"] - y) <= _ON_LINE]
    if on:
        return {"position": "at", "y": round(y, 1), "line": ref(on[0])}
    above = [line for line in lines if line["y"] < y]
    below = [line for line in lines if line["y"] > y]
    if above and below:
        near = ("upper" if y - above[-1]["y"] <= _NEAR_LINE
                else "lower" if below[0]["y"] - y <= _NEAR_LINE else None)
        return {"position": "between", "y": round(y, 1), "upper": ref(above[-1]), "lower": ref(below[0]),
                "near": near}
    if below:
        return {"position": "above", "y": round(y, 1), "lower": ref(below[0])}
    if above:
        return {"position": "below", "y": round(y, 1), "upper": ref(above[-1])}
    return {"position": "unknown", "y": round(y, 1)}


def _column_extent(x0: float, x1: float, strokes: List[tuple], lines: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Top and bottom of the drawn column in this band, relative to the level lines."""

    if not lines:
        return None
    middle, half = (x0 + x1) / 2.0, (x1 - x0) / 2.0
    mine = [s for s in strokes if abs(s[0] - middle) <= 0.6 * half]
    if not mine:
        return None
    # The column is one collinear stroke; a pier or plate outline drawn
    # beside it in the same band is not part of it.
    axis = max(mine, key=lambda s: s[2] - s[1])[0]
    mine = [s for s in mine if abs(s[0] - axis) <= 1.5]
    top, bottom = min(s[1] for s in mine), max(s[2] for s in mine)
    return {"top": _endpoint(top, lines), "bottom": _endpoint(bottom, lines)}


def schedule_captions(bbox: List[float], visible: List[dict], *, reach: float = 90.0) -> Dict[str, Any]:
    """Title above a table, caption below it, and the NOTE lines under it."""

    above = [
        p for p in visible
        if bbox[1] - 45.0 <= p["bbox"][3] <= bbox[1] + 30.0
        and p["bbox"][2] > bbox[0] and p["bbox"][0] < bbox[2]
        and "SCHEDULE" in p["text"].upper()
    ]
    below = sorted(
        (
            p for p in visible
            if bbox[3] - 1.0 <= p["bbox"][1] <= bbox[3] + reach
            and p["bbox"][2] > bbox[0] and p["bbox"][0] < bbox[2] and not p["vertical"]
        ),
        key=lambda p: (p["bbox"][1], p["bbox"][0]),
    )
    caption = next(
        (
            p["text"] for p in below
            if not re.match(r"^(?:NOTES?\b|N\.?T\.?S\.?$|SCALE\b)", p["text"], re.IGNORECASE)
            and "SCHEDULE" not in p["text"].upper()
            and len(re.findall(r"[A-Z]{2,}", p["text"].upper())) >= 2
        ),
        None,
    )
    return {
        "title": " ".join(above[0]["text"].split()) if above else None,
        "caption": caption,
        "notes": [p["text"] for p in below if re.match(r"^NOTES?\b", p["text"], re.IGNORECASE)],
    }


# --------------------------------------------------------------------------
# Document-level schedules, plate tables and location tables
# --------------------------------------------------------------------------
_TABLE_MARK_CELL_RE = re.compile(r"^[A-Z]{1,4}-?\d{1,3}[A-Z]?$")
_DIMENSION_HEADERS = {
    "THICKNESS": "thickness", "THK": "thickness", "T": "thickness",
    "WIDTH": "width", "B": "width", "LENGTH": "length", "N": "length",
}
_NOT_PLATE_GROUP_RE = re.compile(r"WASHER|ANCHOR|\bROD|BOLT|WELD")


def _compact(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).upper()


def _plate_kind(title: Any) -> Optional[str]:
    upper = str(title or "").upper()
    for words, kind in (("BEARING PLATE", "bearing plate"), ("BASE PLATE", "base plate"),
                        ("CAP PLATE", "cap plate"), ("BENT PLATE", "bent plate")):
        if words in upper:
            return kind
    return None


def _row_text(cells: List[str]) -> str:
    return " | ".join(" ".join(c.split()) for c in cells if c and c.strip())


def _plate_table(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """BP / CBP rows of a plate schedule, dimensions labelled by its headings."""

    kind = _plate_kind(record.get("title"))
    header = record.get("header") or []
    if not kind or not header:
        return None
    groups = record.get("header_groups") or [""] * len(header)
    body = record.get("body") or []

    def mark_share(column: int) -> int:
        return sum(1 for row in body if column < len(row["cells"])
                   and _TABLE_MARK_CELL_RE.fullmatch(_compact(row["cells"][column])))

    mark_col = max(range(len(header)), key=lambda c: (mark_share(c), -c))
    if mark_share(mark_col) == 0:
        return None
    dims: List[tuple] = []
    for column, label in enumerate(header):
        group = groups[column] if column < len(groups) else ""
        if column == mark_col or _NOT_PLATE_GROUP_RE.search(f"{group} {label}"):
            continue
        last = label.split()[-1] if label.split() else ""
        if last in _DIMENSION_HEADERS:
            dims.append((column, _DIMENSION_HEADERS[last]))
    size_col = None if dims else next(
        (c for c, label in enumerate(header) if c != mark_col and re.search(r"SIZE|DIMENSION", label)), None,
    )
    remark_col = next((c for c, label in enumerate(header) if re.search(r"REMARK|COMMENT|NOTE", label)), None)
    # Plate quantity only: ANCHOR ROD QTY / WELD / WASHER columns count other parts.
    qty_col = next(
        (c for c, label in enumerate(header)
         if c != mark_col and re.search(r"\b(?:QTY|QUANTITY)\b", label)
         and not _NOT_PLATE_GROUP_RE.search(f"{groups[c] if c < len(groups) else ''} {label}")),
        None,
    )
    rows = []
    for row in body:
        cells = row["cells"] + [""] * len(header)
        mark = _compact(cells[mark_col])
        if not _TABLE_MARK_CELL_RE.fullmatch(mark):
            continue
        if dims:
            dimensions = [
                {"label": label, **(parse_dimension(cells[c]) or {"raw": " ".join(cells[c].split()), "inches": None})}
                for c, label in dims
            ]
        elif size_col is not None:
            dimensions = [{"label": None, **d} for d in parse_plate_cell(cells[size_col])["dimensions"]]
        else:
            continue
        remark = " ".join(cells[remark_col].split()) if remark_col is not None else ""
        quantity = cells[qty_col].strip() if qty_col is not None else ""
        rows.append({
            "mark": mark,
            "dimensions": dimensions,
            "quantity": int(quantity) if quantity.isdigit() else None,
            "reference": parse_drawing_reference(remark) if remark else None,
            "source_text": _row_text(row["cells"]),
            "bbox": row.get("bbox"),
        })
    if not rows:
        return None
    return {"kind": kind, "title": record.get("title"), "page": record["page"],
            "bbox": record.get("bbox"), "rows": rows}


def _location_table(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Location-keyed rows (``C.1-8.1 | W12x53 | CBP-4``)."""

    header = record.get("header") or []
    section_col = next((c for c, h in enumerate(header) if c and re.search(r"SECTION|SIZE", h)), None)
    plate_col = next((c for c, h in enumerate(header) if c and "PLATE" in h), None)
    rows = []
    for row in record.get("body") or []:
        cells = row["cells"] + [""] * len(header)
        location = " ".join(cells[0].split())
        if not location:
            continue
        rows.append({
            "location": location,
            "section_text": " ".join(cells[section_col].split()) if section_col is not None else "",
            "plate_mark": _compact(cells[plate_col]) if plate_col is not None else "",
            "source_text": _row_text(row["cells"]),
            "bbox": row.get("bbox"),
        })
    if not rows:
        return None
    return {"title": record.get("title"), "page": record["page"], "bbox": record.get("bbox"), "rows": rows}


def _table_schedules(grids: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Conventional MARK | SIZE | BASE PLATE column tables (already read by
    ``schedule_grid``) in the same schedule / column shape as the matrices."""

    schedules = []
    for grid in grids:
        rows = [r for r in grid.get("rows") or [] if r.get("mark_role") != "grid_location"]
        if grid.get("kind") != "column" or grid.get("layout") == "transposed" or not rows:
            continue
        page = int(grid.get("page") or 0)
        schedules.append({
            "title": grid.get("title") or "COLUMN SCHEDULE", "caption": None, "key_role": "mark",
            "layout": "table", "levels": [], "pages": [page], "blocks": [{"page": page, "bbox": grid.get("bbox")}],
            "notes": [], "suppressed_text": [],
            "entries": [{
                "key": row["mark"], "key_bbox": row.get("bbox"), "page": page,
                "sections": [{"printed": row["size_text"], "section": row.get("section")}] if row.get("size_text") else [],
                "plates": [{"label": "BASE PLATE", "text": row.get("plate_text") or "", "bbox": row.get("bbox")}]
                if row.get("plate_role") == "base_plate" or row.get("plate_text") else [],
            } for row in rows],
        })
    return schedules


def _continues(first: tuple, second: tuple) -> bool:
    """Same title and key, and nearly the same level words (a split label
    such as ``Base Plate`` / ``Size`` adds a word to one block only)."""

    if first[:2] != second[:2]:
        return False
    union = first[2] | second[2]
    return not union or len(first[2] & second[2]) / len(union) >= 0.8


def _band_key(text: Any) -> str:
    return " ".join(str(text or "").split()).upper()


def band_readings(column_schedules: Dict[str, Any]) -> Dict[tuple, Dict[str, Any]]:
    """What each printed level band means, from the schedule's drawn level lines.

    A graphical (Revit) schedule prints a level's name just above its line and
    its elevation just below it, so the label of the band between two lines
    reads ``<upper line's elevation> <lower line's name>`` -- ``14' - 0" FIRST
    FLOOR`` is SECOND FLOOR's elevation and FIRST FLOOR's name. Keyed by
    ``(page, printed band)``. ``pairing``:

    * ``unpaired`` -- the two parts belong to different lines (``elevation_of``
      / ``name_of`` say which, with their source boxes);
    * ``paired`` -- one line prints both (``level`` is that level);
    * ``ambiguous`` -- the same printed band reads more than one way.
    """

    readings: Dict[tuple, Dict[str, Any]] = {}

    def part(line: Dict[str, Any], text_key: str, box_key: str) -> Dict[str, Any]:
        return {"text": line[text_key], "level": line["name"], "elevation_text": line["elevation_text"],
                "page": line["page"], "bbox": line.get(box_key)}

    def add(key: tuple, reading: Dict[str, Any]) -> None:
        known = readings.get(key)
        if known is None:
            readings[key] = reading
        elif (known["pairing"], known.get("elevation_of", {}).get("level"), known.get("name_of", {}).get("level")) != \
                (reading["pairing"], reading.get("elevation_of", {}).get("level"), reading.get("name_of", {}).get("level")):
            readings[key] = {"pairing": "ambiguous", "schedule_id": reading["schedule_id"],
                             "candidates": [known, reading] if known["pairing"] != "ambiguous"
                             else known["candidates"] + [reading]}

    for schedule in (column_schedules or {}).get("schedules") or []:
        lines = schedule.get("level_lines") or []
        for line in lines:
            if line.get("name") and line.get("elevation_text"):
                add((line["page"], _band_key(f"{line['elevation_text']} {line['name']}")),
                    {"pairing": "paired", "schedule_id": schedule["id"],
                     "level": {"name": line["name"], "elevation_text": line["elevation_text"]},
                     "elevation_of": part(line, "elevation_text", "elevation_bbox"),
                     "name_of": part(line, "name", "name_bbox")})
        for upper, lower in zip(lines, lines[1:]):
            if lower.get("block") != upper.get("block") or lower["y"] <= upper["y"]:
                continue
            if upper.get("elevation_text") and lower.get("name"):
                add((upper["page"], _band_key(f"{upper['elevation_text']} {lower['name']}")),
                    {"pairing": "unpaired", "schedule_id": schedule["id"], "level": None,
                     "elevation_of": part(upper, "elevation_text", "elevation_bbox"),
                     "name_of": part(lower, "name", "name_bbox")})
    return readings


def build_column_schedules(
    records: List[Dict[str, Any]], grids: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Column schedules from ruled-table ``records`` (and the conventional
    column tables in ``grids``), plus plate and location-keyed tables.

    Matrix blocks on one page, or on consecutive pages, with the same title,
    key and level rows are one schedule printed in parts. A block is never
    read as a building level.
    """

    schedules: List[Dict[str, Any]] = []
    for record in sorted(
        (r for r in records if r.get("column_matrix")), key=lambda r: (r["page"], r["bbox"][1], r["bbox"][0])
    ):
        matrix = record["column_matrix"]
        captions = matrix.get("captions") or {}
        title = captions.get("title") or record.get("title") or "COLUMN SCHEDULE"
        # find_tables splits level bands differently per block: compare words.
        signature = (title, matrix["key_role"], frozenset(
            " ".join(level["label"] for level in matrix["levels"]).upper().split()
        ))
        target = next(
            (s for s in reversed(schedules)
             if _continues(s["_signature"], signature) and record["page"] - s["pages"][-1] <= 1),
            None,
        )
        if target is None:
            target = {
                "_signature": signature, "title": title, "caption": None, "key_role": matrix["key_role"],
                "layout": matrix["layout"], "levels": matrix["levels"], "pages": [], "blocks": [],
                "notes": [], "entries": [], "suppressed_text": [], "level_lines": [],
            }
            schedules.append(target)
        if record["page"] not in target["pages"]:
            target["pages"].append(record["page"])
        target["caption"] = target["caption"] or captions.get("caption")
        target["notes"].extend(n for n in captions.get("notes") or [] if n not in target["notes"])
        target["blocks"].append({"page": record["page"], "bbox": matrix["bbox"]})
        target["level_lines"].extend(
            {**line, "page": record["page"], "block": len(target["blocks"])}
            for line in matrix.get("level_lines") or []
        )
        target["suppressed_text"].extend({**s, "page": record["page"]} for s in matrix["suppressed_text"])
        target["entries"].extend({**column, "page": record["page"]} for column in matrix["columns"])
    for schedule in schedules:
        schedule.pop("_signature")
    schedules.extend(_table_schedules(grids or []))
    for number, schedule in enumerate(schedules, 1):
        schedule["id"] = f"S{number}"
    return {
        "schedules": schedules,
        "plate_tables": [t for t in (_plate_table(r) for r in records if r["layout"] == "rows") if t],
        "location_tables": [t for t in (_location_table(r) for r in records if r["layout"] == "location_rows") if t],
    }


# --------------------------------------------------------------------------
# Reviewable entries (Drawing Summary)
# --------------------------------------------------------------------------
_CAP_PLATE_NOTE_RE = re.compile(
    r"ALL\s+(?P<scope>HSS|STEEL|PIPE|WIDE\s+FLANGE)?\s*COLUMNS?\s+SHALL\s+RECEIVE\s+AN?\s+"
    r"(?P<thk>\d+(?:[ -]\d+/\d+|/\d+)?\s*\")\s*THICK\s+CAP\s+PLATE",
    re.IGNORECASE,
)
_LOCATION_PLAN_RE = re.compile(r"\bCOLUMN\s+LOCATION\s+PLAN\b", re.IGNORECASE)


def _sheet_key(sheet: Any) -> str:
    return re.sub(r"[^A-Z0-9.]", "", str(sheet or "").upper())


def _location_identity(parsed: Dict[str, Any]) -> tuple:
    if parsed["status"] != "parsed":
        return ("raw", _compact(parsed["raw"]))
    return tuple(
        (g["label"], g["offset"]["inches"] if g["offset"] else None) for g in parsed["grids"]
    )


def _source(kind: str, text: str, page: int, sheets: Dict[int, str], bbox: Any, title: Any = None) -> Dict[str, Any]:
    return {"kind": kind, "text": text, "title": title, "page": page, "sheet": sheets.get(page), "bbox": bbox}


def plate_index(tables: List[Dict[str, Any]]) -> Dict[str, List[tuple]]:
    """``{mark: [(table, row), ...]}`` over this document's plate schedules."""

    from services.engineering.schedule_grid import normalize_schedule_mark

    index: Dict[str, List[tuple]] = {}
    for table in tables:
        for row in table["rows"]:
            index.setdefault(normalize_schedule_mark(row["mark"]), []).append((table, row))
    return index


def lookup_plate_mark(mark: str, index: Dict[str, List[tuple]], sheets: Dict[int, str]) -> Dict[str, Any]:
    """A plate mark resolved through this document's plate schedules only.

    Two schedules defining the mark differently is a conflict, never "first
    row wins"; a mark no schedule defines stays an unresolved reference.
    """

    from services.engineering.schedule_grid import normalize_schedule_mark

    found = index.get(normalize_schedule_mark(mark), [])
    sources = [
        _source("plate schedule", row["source_text"], table["page"], sheets, row["bbox"], table["title"])
        for table, row in found
    ]
    if not found:
        return {"status": "unresolved", "reason": f"{mark} is not defined in a plate schedule in this set", "sources": []}
    if len({tuple((d["label"], d["raw"]) for d in row["dimensions"]) for _, row in found}) > 1:
        return {"status": "conflict", "sources": sources,
                "reason": f"{mark} is defined differently in {len(found)} plate schedule rows"}
    table, row = found[0]
    return {"status": "resolved", "type": table["kind"], "dimensions": row["dimensions"], "sources": sources[:1]}


def _read_plate(entry: Dict[str, Any], column: Dict[str, Any], schedule_name: str, transfer_note: Optional[str],
                index: Dict[str, List[tuple]], location_matches: List[tuple],
                pages_by_sheet: Dict[str, int], sheets: Dict[int, str]) -> Dict[str, Any]:
    """The column's plate: read from its cell, resolved through another table,
    a detail reference, or explicitly blank / not applicable / unresolved."""

    page = entry["page"]
    via: List[Dict[str, Any]] = []
    marks = list(column.get("plate_marks") or [])
    for cell in column.get("plates") or []:
        parsed = parse_plate_cell(cell["text"])
        if parsed["status"] == "blank":
            continue
        if _TABLE_MARK_CELL_RE.fullmatch(_compact(parsed["raw"])):
            marks = [{"text": _compact(parsed["raw"]), "bbox": cell["bbox"]}]
            break
        via.append(_source("schedule cell", cell["text"], page, sheets, cell["bbox"], cell["label"]))
        plate = {"type": _plate_kind(cell["label"]) or "plate", "printed": parsed["raw"],
                 "markers": parsed["markers"], "via": via, "dimensions": []}
        if parsed["status"] == "dimensions":
            return {**plate, "status": "read", "dimensions": [{"label": None, **d} for d in parsed["dimensions"]]}
        if parsed["status"] == "reference":
            ref = {**parsed["reference"], "page": pages_by_sheet.get(_sheet_key(parsed["reference"]["sheet"]))}
            return {**plate, "status": "reference", "reference": ref,
                    "note": "Dimensions are on the referenced detail; they are not read from it."}
        return {**plate, "status": parsed["status"]}   # not_applicable / unreadable

    if not marks:
        typed = [(table, row) for table, row in location_matches if row["plate_mark"]]
        via.extend(_source("location table", row["source_text"], table["page"], sheets, row["bbox"], table["title"])
                   for table, row in typed)
        names = {row["plate_mark"] for _, row in typed}
        if len(names) > 1:
            return {"type": None, "status": "conflict", "printed": ", ".join(sorted(names)), "dimensions": [],
                    "via": via, "note": "The listed locations use different plate marks."}
        marks = [{"text": name, "from_table": True} for name in names]
    if marks:
        names = sorted({m["text"] for m in marks})
        via.extend(_source("leader mark", m["text"], page, sheets, m["bbox"], schedule_name)
                   for m in marks if not m.get("from_table"))
        if len(names) > 1:
            return {"type": None, "status": "conflict", "printed": ", ".join(names), "dimensions": [],
                    "via": via, "note": "More than one plate mark is drawn on this column."}
        found = lookup_plate_mark(names[0], index, sheets)
        plate = {"printed": names[0], "via": via + found["sources"]}
        if found["status"] == "resolved":
            return {**plate, "status": "resolved", "type": found["type"], "dimensions": found["dimensions"]}
        return {**plate, "type": None, "status": found["status"], "dimensions": [], "note": found["reason"]}
    if column.get("plates"):
        return {"type": _plate_kind(column["plates"][0]["label"]) or "plate", "status": "blank", "printed": "",
                "dimensions": [], "via": [],
                "note": f"Left blank in the schedule. Schedule note: {transfer_note}" if transfer_note
                else "Left blank in the schedule."}
    return {"type": None, "status": "not_shown", "printed": "", "dimensions": [], "via": [],
            "note": "This schedule shows no plate for the column."}


# "ALL C_ COLUMNS ARE PRECAST COLUMNS ...": a schedule note naming the
# material of one family of column labels (the prefix before ``_``).
_MATERIAL_NOTE_RE = re.compile(
    r"\bALL\s+(?P<prefix>[A-Z]{1,3})_\s*COLUMNS\s+(?:ARE|SHALL\s+BE)\s+"
    r"(?P<material>PRECAST(?:\s+CONCRETE)?|CAST[- ]IN[- ]PLACE(?:\s+CONCRETE)?|CONCRETE|STEEL|TIMBER|WOOD)\b",
    re.IGNORECASE,
)
_MATERIALS = {"PRECAST": "precast concrete", "CAST IN PLACE": "cast-in-place concrete",
              "CONCRETE": "concrete", "STEEL": "steel", "TIMBER": "timber", "WOOD": "wood"}


def _material_name(printed: str) -> str:
    """``CAST-IN-PLACE CONCRETE`` / ``PRECAST`` / ... -> one normalised name."""

    words = re.sub(r"\s+CONCRETE$", "", re.sub(r"[-\s]+", " ", printed.upper()).strip())
    return _MATERIALS.get(words, words.lower())


_LABEL_SIZE_RE = re.compile(r"^(?P<mark>[A-Z]{1,3}\d+[A-Z]?)\s*[-–]\s*(?P<size>.+)$", re.IGNORECASE)


def _printed_size(text: str) -> Optional[Dict[str, Any]]:
    """``24"x24"`` -> both dimensions as printed and in inches; ``None`` when
    a part does not read as a dimension (kept as printed elsewhere)."""

    parts = [p.strip() for p in re.split(r"\s*[xX×]\s*", text.strip()) if p.strip()]
    dims = [parse_dimension(p) for p in parts]
    if len(parts) < 2 or None in dims:
        return None
    return {"raw": text.strip(), "dimensions": dims}


def _material(entry: Dict[str, Any], rules: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """What a schedule note says this entry's label is made of, only for the
    label family the note names (C_ -> C1, C2 ...). Other labels get nothing:
    a note about C_ columns says nothing about P1 piers."""

    printed = " ".join(s.get("printed") or "" for s in entry["sections"]).strip()
    match = _LABEL_SIZE_RE.match(printed)
    mark = (match["mark"] if match else printed).upper()
    for rule in rules:
        if re.fullmatch(rf"{rule['prefix']}\d+[A-Z]?", mark):
            return {"status": "read", "material": rule["material"], "mark": mark,
                    "size": _printed_size(match["size"]) if match else None,
                    "printed": printed, "source": rule["source"]}
    return None


def plate_count_checks(entries: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Plate quantity printed in a plate schedule against the column locations
    that name the mark. A warning for review: nothing here is a takeoff quantity."""

    from services.engineering.schedule_grid import normalize_schedule_mark

    listed: Dict[str, int] = {}
    for entry in entries:
        plate = entry.get("plate") or {}
        if plate.get("status") == "resolved":
            mark = normalize_schedule_mark(plate["printed"])
            listed[mark] = listed.get(mark, 0) + int(entry.get("listed_location_count") or 0)
    checks = []
    for table in tables:
        for row in table["rows"]:
            quantity, count = row.get("quantity"), listed.get(normalize_schedule_mark(row["mark"]), 0)
            checks.append({
                "mark": row["mark"], "page": table["page"], "scheduled_quantity": quantity,
                "listed_locations": count,
                "status": "no_quantity_printed" if quantity is None else "match" if quantity == count else "mismatch",
            })
    return checks


def column_schedule_view(document: Dict[str, Any], sheets: Dict[int, str]) -> Dict[str, Any]:
    """Reviewable column entries: section, locations, plate, notes, sources.

    Definitions only: ``listed_location_count`` counts locations printed for
    the entry and is never a takeoff quantity.
    """

    from services.engineering.drawing_intelligence import _catalog_designation
    from services.engineering.level_evidence import level_difference
    from services.engineering.schedule_grid import _catalog_accepts, normalize_schedule_mark, section_from_size_text

    data = document.get("column_schedules") or {}
    tables = data.get("plate_tables") or []
    index = plate_index(tables)
    pages_by_sheet = {_sheet_key(sheet): page for page, sheet in sheets.items()}

    def table_section(text: str) -> str | None:
        # A designation wrapped onto two lines in its cell (``HSS3-1/2X3-1/2``
        # / ``X3/8``) reads as one once the break is closed; an exact catalog
        # row (display only) covers fractional HSS sizes the size parser skips.
        compact = re.sub(r"\s+", "", text)
        return (section_from_size_text(text, _catalog_accepts)
                or section_from_size_text(compact, _catalog_accepts)
                or _catalog_designation(compact))

    location_tables = data.get("location_tables") or []
    location_rows: Dict[tuple, List[tuple]] = {}
    for t, table in enumerate(location_tables):
        for r, row in enumerate(table["rows"]):
            row = {**row, "section": table_section(row["section_text"]), "_key": (t, r)}
            location_rows.setdefault(_location_identity(parse_grid_location(row["location"])), []).append((table, row))
    matched_by: dict[tuple, set[str]] = {}   # location-table row -> the column schedule listing it
    plans: Dict[int, str] = {}
    cap_rules: Dict[int, List[Dict[str, Any]]] = {}
    for block in document.get("blocks") or []:
        page = int(block.get("page_number") or 0)
        text = " ".join(str(block.get("text") or "").split())
        if _LOCATION_PLAN_RE.search(text):
            plans.setdefault(page, text[:80])
        for match in _CAP_PLATE_NOTE_RE.finditer(text):
            cap_rules.setdefault(page, []).append({
                "scope": (match["scope"] or "").upper() or None,
                "thickness": parse_dimension(match["thk"]),
                "source": _source("schedule note", match.group(0), page, sheets, block.get("bbox")),
            })

    schedules_out: List[Dict[str, Any]] = []
    entries: List[Dict[str, Any]] = []
    for schedule in data.get("schedules") or []:
        name = schedule.get("caption") or schedule["title"]
        transfer_note = next((n for n in schedule["notes"] if "TRANSFER" in n.upper()), None)
        rules = [rule for page in schedule["pages"] for rule in cap_rules.get(page, [])]
        material_rules = [
            {"prefix": m["prefix"].upper(), "material": _material_name(m["material"]),
             "source": _source("schedule note", note, schedule["pages"][0], sheets, schedule["blocks"][0]["bbox"])}
            for note in schedule["notes"] for m in _MATERIAL_NOTE_RE.finditer(note)
        ]
        schedules_out.append({
            "id": schedule["id"], "name": name, "layout": schedule["layout"], "key_role": schedule["key_role"],
            "pages": schedule["pages"], "sheets": [sheets.get(p) for p in schedule["pages"]],
            "page": schedule["pages"][0], "sheet": sheets.get(schedule["pages"][0]),
            "bbox": schedule["blocks"][0]["bbox"], "block_count": len(schedule["blocks"]),
            "levels": [level["label"] for level in schedule["levels"]],
            "notes": schedule["notes"],
            "hidden_text": [s["text"] for s in schedule.get("suppressed_text") or []],
        })
        first_entry = len(entries)
        for number, column in enumerate(schedule["entries"], 1):
            entry: Dict[str, Any] = {
                "id": f"{schedule['id']}-{number}", "schedule_id": schedule["id"],
                "key_role": schedule["key_role"], "page": column["page"], "sheet": sheets.get(column["page"]),
                "bbox": column["key_bbox"], "is_definition_not_quantity": True,
                "mark": None, "location_text": None, "locations": [], "listed_location_count": 0,
                "repeated_label": False, "label_conflict": None,
            }
            matches: List[tuple] = []
            if schedule["key_role"] == "location":
                texts = split_locations(column["key"])
                seen = set()
                for text in texts:
                    parsed = parse_grid_location(text)
                    identity = _location_identity(parsed)
                    if identity not in seen:
                        seen.add(identity)
                        entry["locations"].append(parsed)
                        for match in location_rows.get(identity, []):
                            matches.append((parsed, match))
                            matched_by.setdefault(match[1]["_key"], set()).add(schedule["id"])
                repeats = [split_locations(r) for r in column.get("key_repeats") or []]
                entry.update({
                    "location_text": column["key"],
                    "listed_location_count": len(entry["locations"]),
                    "repeated_label": bool(repeats) and all(r == texts for r in repeats),
                    "label_conflict": next((" / ".join(", ".join(r) for r in repeats) for r in repeats if r != texts), None),
                })
            else:
                plan = plans.get(column["page"])
                entry["mark"] = column["key"]
                entry["location_note"] = f"{column['key']} is a column mark, not a grid intersection. " + (
                    f"Its positions are drawn on the {plan.split(' SCALE')[0].strip().title()}; they are not read yet."
                    if plan else "Its positions are not listed in the schedule."
                )
            entry["sections"] = [
                {"designation": _catalog_designation(s["section"]) if s.get("section") else None, "printed": s.get("printed")}
                for s in column["sections"]
            ]
            entry["plate"] = _read_plate(
                entry, column, name, transfer_note, index, [m for _, m in matches], pages_by_sheet, sheets,
            )
            entry["other_plates"] = [
                {"type": "cap plate", "dimensions": [{"label": "thickness", **rule["thickness"]}] if rule["thickness"] else [],
                 "via": [rule["source"]]}
                for rule in rules
                if rule["scope"] in (None, "STEEL") or any(
                    (s["designation"] or "").startswith(rule["scope"]) for s in entry["sections"]
                )
            ]
            entry["notes"] = [n["text"] for n in column.get("notes") or []] + [
                f"{label}: {text}" for label, text in (column.get("supplementary") or {}).items()
                if re.search(r"QTY|QUANTITY", label, re.IGNORECASE)
            ]
            if column.get("supports"):
                entry["supports"] = [{**support, "page": column["page"], "sheet": sheets.get(column["page"])}
                                     for support in column["supports"]]
            exact = {s["designation"] for s in entry["sections"] if s["designation"]}
            entry["conflicts"] = [
                f"{table['title'].title()} lists {location['raw']} as {row['section_text']}"
                for location, (table, row) in matches
                if row["section"] and exact and row["section"] not in exact
            ]
            entry["hidden_text"] = column.get("suppressed_text") or []
            # Where the drawn column starts and ends against the schedule's
            # level lines, and the elevation difference when both ends sit on
            # lines with printed elevations. Never a column length.
            extent = entry["extent"] = column.get("extent")
            entry["level_difference"] = level_difference(extent) if extent else None
            material = _material(entry, material_rules)
            if material:
                entry["material"] = material
            elif any(s["designation"] for s in entry["sections"]):
                entry["material"] = {"status": "catalog section", "material": "steel"}
            entries.append(entry)
        # Steel when the schedule's entries are catalog steel sections; a
        # schedule whose entries a note makes concrete is a concrete schedule.
        own = entries[first_entry:]
        materials = [(e.get("material") or {}).get("material") for e in own]
        schedules_out[-1]["material_group"] = (
            "steel" if "steel" in materials else
            "concrete" if any(m and "concrete" in m for m in materials) else "unclassified")
        schedules_out[-1]["entry_count"] = len(own)
        schedules_out[-1]["coverage"] = _schedule_coverage(own)

    # Locations a location table assigns a section and plate to that no
    # column schedule prints (OSSE S601 HSS posts): entries of their own,
    # with the table as their only source -- no levels, no column stack.
    table_records = []
    for t, table in enumerate(location_tables):
        rows = list(enumerate(table["rows"]))
        listed = Counter(sid for r, _row in rows for sid in matched_by.get((t, r), set()))
        # Shared labels across schedules do not establish one building scope.
        scope_id, shared = next(iter(listed.items())) if len(listed) == 1 else (None, 0)
        record = {"title": table.get("title"), "page": table["page"], "sheet": sheets.get(table["page"]),
                  "bbox": table.get("bbox"), "rows": len(rows), "matched": dict(listed),
                  "scope_schedule_id": scope_id,
                  "scope_basis": (f"{shared} of its {len(rows)} rows are locations of that schedule"
                                  if scope_id else None)}
        only = [row for r, row in rows if (t, r) not in matched_by]
        record["assignment_only"] = len(only)
        if only:
            sid = f"L{t + 1}"
            record["assignment_only_schedule_id"] = sid
            own = [_assignment_entry(f"{sid}-{n}", sid, table, row, table_section(row["section_text"]), index,
                                     sheets, _catalog_designation)
                   for n, row in enumerate(only, 1)]
            materials = [(e.get("material") or {}).get("material") for e in own]
            schedules_out.append({
                "id": sid, "name": f"{table.get('title') or 'Location table'} — locations not in a column schedule",
                "layout": "location_table", "key_role": "location", "source": "location_table",
                "pages": [table["page"]], "sheets": [sheets.get(table["page"])], "page": table["page"],
                "sheet": sheets.get(table["page"]), "bbox": table.get("bbox"), "block_count": 1, "levels": [],
                "notes": [], "hidden_text": [], "scope_schedule_id": scope_id, "scope_basis": record["scope_basis"],
                "material_group": "steel" if "steel" in materials else "unclassified",
                "entry_count": len(own), "coverage": _schedule_coverage(own),
            })
            entries.extend(own)
        table_records.append(record)

    # A plate shown as "not shown" says where else it was looked for.
    if location_tables:
        searched = [{"title": t.get("title"), "page": t["page"], "sheet": sheets.get(t["page"]),
                     "rows": len(t["rows"])} for t in location_tables]
        where = "; ".join(f"{t['title'] or 'location table'} ({t['sheet'] or 'p. ' + str(t['page'])}, "
                          f"{t['rows']} location rows)" for t in searched)
        for entry in entries:
            if entry["plate"]["status"] == "not_shown" and not entry.get("assignment_only"):
                entry["plate"]["note"] = f"No plate is printed for this column, and no row of {where} lists this location."
                entry["plate"]["searched"] = searched
    used = {normalize_schedule_mark(e["plate"]["printed"]) for e in entries if e["plate"].get("printed")}
    return {
        "schedules": schedules_out,
        "entries": entries,
        "location_tables": table_records,
        "plate_counts": plate_count_checks(entries, tables),
        "plate_tables": [
            {"kind": t["kind"], "title": t["title"], "page": t["page"], "sheet": sheets.get(t["page"]),
             "bbox": t.get("bbox"), "marks": [r["mark"] for r in t["rows"]],
             "rows": [{"mark": r["mark"], "dimensions": r["dimensions"], "source_text": r["source_text"], "bbox": r["bbox"]}
                      for r in t["rows"]],
             # Defined but assigned to no listed column: shown, never given a location.
             "unused_marks": [r["mark"] for r in t["rows"] if normalize_schedule_mark(r["mark"]) not in used]}
            for t in tables
        ],
    }


def _schedule_coverage(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Printed entries of one schedule and how far each is linked (counts of
    printed records, never of installed members)."""

    statuses = Counter(e["plate"]["status"] for e in entries)
    return {
        "entries": len(entries),
        "plates_linked": statuses["resolved"] + statuses["read"],
        "plates_not_shown": statuses["not_shown"],
        "plates_unresolved": sum(statuses[s] for s in ("conflict", "unresolved", "unreadable")),
        "sections_in_catalog": sum(1 for e in entries if any(s.get("designation") for s in e["sections"])),
    }


def _assignment_entry(entry_id: str, schedule_id: str, table: dict[str, Any], row: dict[str, Any],
                      section: str | None, index: dict[str, list[tuple]], sheets: dict[int, str],
                      designation_of: Any) -> dict[str, Any]:
    """A location-table row as an entry: the location, section and plate the
    table assigns. The table gives no levels, so no extent is read."""

    parsed = parse_grid_location(row["location"])
    source = _source("location table", row["source_text"], table["page"], sheets, row["bbox"], table.get("title"))
    designation = designation_of(section) if section else None
    plate: dict[str, Any] = {"type": None, "status": "not_shown", "printed": "", "dimensions": [], "via": [source],
                             "note": "The table assigns no plate to this location."}
    if row["plate_mark"]:
        found = lookup_plate_mark(row["plate_mark"], index, sheets)
        plate = {"printed": row["plate_mark"], "via": [source] + found["sources"], "status": found["status"],
                 "type": found.get("type"), "dimensions": found.get("dimensions") or []}
        if found["status"] != "resolved":
            plate["note"] = found["reason"]
    entry = {
        "id": entry_id, "schedule_id": schedule_id, "key_role": "location", "assignment_only": True,
        "page": table["page"], "sheet": sheets.get(table["page"]), "bbox": row["bbox"],
        "is_definition_not_quantity": True, "mark": None, "location_text": row["location"],
        "locations": [parsed], "listed_location_count": 1, "repeated_label": False, "label_conflict": None,
        "sections": [{"designation": designation, "printed": row["section_text"]}],
        "plate": plate, "other_plates": [], "notes": [], "conflicts": [], "hidden_text": [],
        "extent": None, "level_difference": None,
        "extent_note": "The table assigns a section and base plate only; it gives no levels, so the column's "
                       "vertical extent is not established.",
    }
    if designation:
        entry["material"] = {"status": "catalog section", "material": "steel"}
    return entry
