"""Sheet identity per page, read from the title block.

Evidence only: the sheet index never feeds a token, prediction, mark map or
quantity. Every value is printed text from the title block, with a status;
nothing is completed or guessed.

How the title block is found, without project coordinates:

* All geometry is in **display space** (``page_space``), so a page stored
  with ``/Rotate`` is read as it is shown.
* **Slot** -- a sheet-number-shaped line (``S101A``, ``S2.01``, ``S-122-O``)
  in the outer band of the page. The largest one per page votes; the median
  position across the set is the slot, and each page takes the sheet number
  found in that slot. Detail callouts, grid bubbles and plan notes sit
  elsewhere and are not read as the sheet number.
* **Block** -- title-block boilerplate (project name, field labels) repeats
  at the same position on most sheets. Its extent bounds the title block as
  a right-hand column or a bottom strip.
* **Fields** -- a label (``DRAWING TITLE``, ``Title:``, ``SCALE:``,
  ``DATE:``) and the value beside or below it. A block without a title label
  falls back to the largest sheet-specific text in the block, marked
  ``read_unlabeled``; two equal candidates leave it ``ambiguous``.
* **Revisions** -- rows under a ``DESCRIPTION`` / ``DATE`` header, as
  printed. No revision precedence is decided here.
"""

from __future__ import annotations

import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

from services.engineering.page_space import to_display

SHEET_INDEX_VERSION = "sheet_index_v1"

_SHEET_ID_RE = re.compile(r"^[A-Z]{1,2}-?\d{1,3}(?:\.\d{1,3})?[A-Z]{0,2}(?:-[A-Z0-9]{1,2})?$")
_SHEET_LABEL_RE = re.compile(r"^(?:SHEET|DRAWING|DWG\.?)\s*(?:NO\.?|NUMBER|#)\s*:?$", re.I)
_TITLE_LABEL_RE = re.compile(r"^(?:(?:DRAWING|SHEET)\s+TITLE|TITLE)\s*:?\s*(.*)$", re.I)
_SCALE_LABEL_RE = re.compile(r"^(?:DRAWING\s+)?SCALE\s*:?$", re.I)
_SCALE_INLINE_RE = re.compile(r"^SCALE\s*:\s*(\S.*)$", re.I)
_SCALE_VALUE_RE = re.compile(
    r"\d+\s*(?:/\s*\d+)?\s*\"?\s*=\s*\d+\s*'|^\d+\s*:\s*\d+$|\bAS\s+(?:INDICATED|NOTED|SHOWN)\b|"
    r"^N\.?T\.?S\.?$|\bNOT\s+TO\s+SCALE\b|^(?:NONE|VARIES|FULL)$", re.I)
_DATE_LABEL_RE = re.compile(r"^(?:DRAWING\s+|ISSUE\s+)?DATE\s*:?$", re.I)
_LABEL_RE = re.compile(
    r"(?::$|^(?:PROJECT|DRAWING|SHEET|SCALE|DATE|DRAWN|DRWN|CHECKED|CHKD|DESIGNED|"
    r"KEY\s+PLAN|SEAL|ISSUE|REVISION|DWG|TECH|NO\.?|#)\b)", re.I)
_MONTH = r"(?:JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUNE?|JULY?|AUG(?:UST)?|SEPT?(?:EMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)"
_DATE_RE = re.compile(
    rf"^(?:\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{2,4}}|\d{{4}}[/.-]\d{{1,2}}[/.-]\d{{1,2}}|"
    rf"\d{{1,2}}\s+{_MONTH}\.?\s+\d{{4}}|{_MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}})$", re.I)
_ISSUE_RE = re.compile(
    r"\b(?:BID|PERMIT|SUBMISSION|CONSTRUCTION\s+DOCUMENTS|DESIGN\s+DEVELOPMENT|"
    r"SCHEMATIC\s+DESIGN|ISSUED\s+FOR|ADDENDUM|PRICING|CONFORMED|FOR\s+CONSTRUCTION|"
    r"IFC|RECORD\s+SET|PROGRESS\s+SET)\b", re.I)
_REV_DESC_RE = re.compile(r"^(?:CHANGE\s+)?DESCRIPTION:?$", re.I)
_REV_DATE_RE = re.compile(r"^(?:DATE:?|YYYY/MM/DD)$", re.I)
_REV_NO_RE = re.compile(r"^(?:NO[.:]?|#|REV\.?)$", re.I)
_REV_NUMBER_RE = re.compile(r"^[A-Z0-9]{1,3}\.?$", re.I)
_REV_LEAD_RE = re.compile(r"^(\d{1,3}|[A-Z])\s+(\S.*)$")

_OUTER_X = 0.70        # right band starts here (fraction of display width)
_OUTER_Y = 0.85        # bottom band starts here (fraction of display height)
_SLOT_TOLERANCE = 0.04
_STABLE_SHARE = 0.6    # boilerplate repeats on at least this share of sheets
_STABLE_POSITION = 0.01


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)


class _Line:
    __slots__ = ("text", "box", "size", "orientation")

    def __init__(self, text: str, box: List[float], size: float, orientation: int):
        self.text, self.box, self.size, self.orientation = text, box, size, orientation

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2

    @property
    def height(self) -> float:
        return max(self.box[3] - self.box[1], 1.0)


def _is_sheet_id(text: str) -> bool:
    return bool(_SHEET_ID_RE.match(text)) and sum(ch.isdigit() for ch in text) >= 2


def _same_row(a: _Line, b: _Line) -> bool:
    overlap = min(a.box[3], b.box[3]) - max(a.box[1], b.box[1])
    return overlap >= 0.4 * min(a.height, b.height)


def _page_lines(document: Dict[str, Any]) -> Dict[int, List[_Line]]:
    meta = {int(p.get("page_number") or 0): p for p in document.get("pages") or []}
    by_page: Dict[int, List[_Line]] = {}
    for line in document.get("lines") or []:
        page = int(line.get("page_number") or 0)
        info = meta.get(page)
        text = _norm(line.get("text"))
        if not info or not text or not line.get("bbox"):
            continue
        rotation = int(info.get("rotation") or 0)
        box = to_display(rotation, float(info["width"]), float(info["height"]), line["bbox"])
        orientation = int(round((float(line.get("rotation") or 0) + rotation) / 90.0)) * 90 % 360
        size = float(line.get("font_size") or (box[3] - box[1]))
        by_page.setdefault(page, []).append(_Line(text, box, size, orientation))
    return by_page


def _outer(line: _Line, width: float, height: float) -> bool:
    return line.box[0] >= _OUTER_X * width or line.box[1] >= _OUTER_Y * height


def _slot(candidates: Dict[int, List[_Line]], size: Dict[int, Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    votes = []
    for page, lines in candidates.items():
        if lines:
            best = max(lines, key=lambda l: l.size)
            width, height = size[page]
            votes.append((best.cx / width, best.cy / height))
    if not votes:
        return None
    return statistics.median(v[0] for v in votes), statistics.median(v[1] for v in votes)


def _stable_lines(outer: Dict[int, List[_Line]], size: Dict[int, Tuple[float, float]]) -> Dict[str, Tuple[float, float]]:
    """Title-block boilerplate: text with 4+ letters that repeats at the same
    relative position on most sheets. Returns ``text -> (cx, cy)`` fractions."""

    seen: Dict[Tuple[str, int, int], set] = {}
    for page, lines in outer.items():
        width, height = size[page]
        for line in lines:
            if _letters(line.text) < 4:
                continue
            key = (line.text.upper(), round(line.cx / width / _STABLE_POSITION),
                   round(line.cy / height / _STABLE_POSITION))
            seen.setdefault(key, set()).add(page)
    needed = max(2, _STABLE_SHARE * len(outer))
    return {
        text: (x * _STABLE_POSITION, y * _STABLE_POSITION)
        for (text, x, y), pages in seen.items()
        if len(pages) >= needed
    }


def _block_bounds(stable: Dict[str, Tuple[float, float]]) -> Dict[str, Any]:
    """Right-hand column or bottom strip, from where the boilerplate sits."""

    right = [p for p in stable.values() if p[0] >= _OUTER_X]
    bottom = [p for p in stable.values() if p[1] >= _OUTER_Y and p[0] < _OUTER_X]
    right_span = (max(p[1] for p in right) - min(p[1] for p in right)) if right else 0.0
    bottom_span = (max(p[0] for p in bottom) - min(p[0] for p in bottom)) if bottom else 0.0
    if right and right_span >= bottom_span:
        return {"layout": "right_column", "stable_text_count": len(right)}
    if bottom:
        return {"layout": "bottom_strip", "stable_text_count": len(bottom)}
    return {"layout": "unresolved", "stable_text_count": 0}


def _in_block(lines: List[_Line], layout: str, stable: Dict[str, Tuple[float, float]],
              width: float, height: float, sheet: Optional[_Line]) -> List[_Line]:
    """Lines inside the title block of one page. The block edge is the
    outermost boilerplate line found on this page, never a fixed fraction."""

    on_page = [l for l in lines if l.text.upper() in stable and _outer(l, width, height)]
    if layout == "right_column":
        edges = [l.box[0] for l in on_page if l.box[0] >= _OUTER_X * width]
        left = _contiguous_edge(edges, sheet.box[0] if sheet else None, 0.03 * width)
        return [l for l in lines if l.box[0] >= (left if left is not None else _OUTER_X * width) - 0.006 * width]
    if layout == "bottom_strip":
        edges = [l.box[1] for l in on_page if l.box[1] >= _OUTER_Y * height]
        top = _contiguous_edge(edges, sheet.box[1] if sheet else None, 0.03 * height)
        return [l for l in lines if l.box[1] >= (top if top is not None else _OUTER_Y * height) - 0.006 * height]
    return [l for l in lines if _outer(l, width, height)]


def _contiguous_edge(edges: List[float], start: Optional[float], gap: float) -> Optional[float]:
    """Walk from the sheet number outwards through boilerplate positions and
    stop at the first gap wider than ``gap``: text printed beside the block
    (a stamp, a viewport title) is not part of the title block."""

    if start is None and not edges:
        return None
    points = sorted(set(edges + ([start] if start is not None else [])), reverse=True)
    edge = start if start is not None else points[0]
    for value in points:
        if value >= edge:
            continue
        if edge - value > gap:
            break
        edge = value
    return edge


def _field_value(label: _Line, block: List[_Line], width: float, accept) -> Optional[_Line]:
    """Value of a label: the nearest accepted line to its right on the same
    row, else the nearest accepted line just below it in the same cell."""

    right = [
        l for l in block
        if l is not label and _same_row(l, label) and l.box[0] >= label.box[2] - 2
        and l.box[0] - label.box[2] <= 0.15 * width and accept(l)
    ]
    if right:
        return min(right, key=lambda l: l.box[0])
    below = [
        l for l in block
        if l is not label and l.box[1] >= label.box[3] - 3
        and l.box[1] - label.box[3] <= max(3 * label.height, 30)
        and label.box[0] - 0.01 * width <= l.box[0] <= label.box[0] + 0.2 * width
        and accept(l)
    ]
    return min(below, key=lambda l: l.box[1]) if below else None


def _nearest(lines: List[_Line], anchor: Optional[_Line]) -> Optional[_Line]:
    if not lines:
        return None
    if anchor is None:
        return lines[0]
    return min(lines, key=lambda l: (l.cx - anchor.cx) ** 2 + (l.cy - anchor.cy) ** 2)


def _union(lines: List[_Line]) -> List[float]:
    return [round(min(l.box[0] for l in lines), 1), round(min(l.box[1] for l in lines), 1),
            round(max(l.box[2] for l in lines), 1), round(max(l.box[3] for l in lines), 1)]


def _title(block: List[_Line], sheet: Optional[_Line], stable: Dict[str, Tuple[float, float]],
           width: float, skip: set) -> Dict[str, Any]:
    def plain(l: _Line) -> bool:
        return id(l) not in skip and l is not sheet and not _LABEL_RE.search(l.text) \
            and not _is_sheet_id(l.text) and not _DATE_RE.match(l.text)

    labels = [l for l in block if _TITLE_LABEL_RE.match(l.text) and not _REV_DESC_RE.match(l.text)]
    label = _nearest(labels, sheet)
    if label is not None:
        inline = _TITLE_LABEL_RE.match(label.text).group(1).strip()
        first = None if inline else _field_value(label, block, width, plain)
        if inline or first is not None:
            taken = [label] if inline else [first]
            parts = [inline] if inline else [first.text]
            lead = taken[-1]
            rest = sorted((l for l in block if plain(l) and l.box[1] > lead.box[1]), key=lambda l: l.box[1])
            left = min(label.box[0], lead.box[0]) - 0.01 * width
            for line in rest:
                previous = taken[-1]
                if (line.orientation != lead.orientation
                        or abs(line.size - lead.size) > 0.2 * lead.size
                        or line.box[1] - previous.box[3] > 0.8 * lead.size
                        or not (left <= line.box[0] <= label.box[0] + 0.2 * width)):
                    break
                taken.append(line)
                parts.append(line.text)
            return {"sheet_title": _norm(" ".join(parts)), "title_status": "read",
                    "title_bbox": _union(taken), "title_label": label.text, "title_candidates": []}
        return {"sheet_title": None, "title_status": "unresolved", "title_bbox": None,
                "title_label": label.text, "title_candidates": []}

    candidates = [
        l for l in block
        if plain(l) and l.text.upper() not in stable and _letters(l.text) >= 6
        and len([w for w in l.text.split() if _letters(w) >= 2]) >= 2
    ]
    candidates.sort(key=lambda l: -l.size)
    shown = [{"text": l.text, "bbox": l.box} for l in candidates[:4]]
    if not candidates:
        return {"sheet_title": None, "title_status": "unresolved", "title_bbox": None,
                "title_label": None, "title_candidates": []}
    top = candidates[0]
    if len(candidates) > 1 and candidates[1].size >= 0.85 * top.size:
        return {"sheet_title": None, "title_status": "ambiguous", "title_bbox": None,
                "title_label": None, "title_candidates": shown}
    return {"sheet_title": top.text, "title_status": "read_unlabeled", "title_bbox": top.box,
            "title_label": None, "title_candidates": shown}


def _revisions(block: List[_Line], sheet: Optional[_Line]) -> Tuple[Dict[str, Any], set]:
    headers = []
    for desc in (l for l in block if _REV_DESC_RE.match(l.text)):
        row = [l for l in block if _same_row(l, desc) and abs(l.cx - desc.cx) <= 400]
        date = [l for l in row if _REV_DATE_RE.match(l.text)]
        if date:
            number = [l for l in row if _REV_NO_RE.match(l.text)]
            headers.append((desc, date[0], number[0] if number else None))
    if not headers:
        return {"status": "not_shown", "rows": []}, set()
    desc, date, number = min(
        headers, key=lambda h: (h[0].cx - sheet.cx) ** 2 + (h[0].cy - sheet.cy) ** 2 if sheet else 0)
    head = [h for h in (desc, date, number) if h is not None]
    left = min(h.box[0] for h in head) - 15
    right = max(h.box[2] for h in head) + 60
    bottom = max(h.box[3] for h in head)
    used = {id(h) for h in head}
    below = sorted(
        (l for l in block if l.box[1] > bottom - 1 and l.box[0] >= left and l.box[2] <= right and id(l) not in used),
        key=lambda l: l.box[1])
    rows: List[List[_Line]] = []
    last = bottom
    for line in below:
        if line.box[1] - last > 2.5 * desc.height:
            break
        if rows and line.box[1] <= max(l.box[3] for l in rows[-1]) + 1:
            rows[-1].append(line)
        else:
            rows.append([line])
        last = max(last, line.box[3])
    parsed = []
    for row in rows:
        dates = [l.text for l in row if _DATE_RE.match(l.text)]
        if len(dates) != 1:
            continue
        numbers, described = [], []
        for line in sorted((l for l in row if not _DATE_RE.match(l.text)), key=lambda l: l.box[1]):
            if number is not None and _REV_NUMBER_RE.match(line.text) \
                    and abs(line.cx - number.cx) < abs(line.cx - desc.cx):
                numbers.append(line.text)
                continue
            # A number printed on the description's baseline arrives as one
            # line ("1 65% DD"); it starts left of the description column.
            split = _REV_LEAD_RE.match(line.text)
            if number is not None and not numbers and split and line.box[0] < desc.box[0]:
                numbers.append(split.group(1))
                described.append(split.group(2))
                continue
            described.append(line.text)
        used.update(id(l) for l in row)
        parsed.append({
            "number": " ".join(numbers),
            "description": _norm(" ".join(described)),
            "date": dates[0],
            "bbox": _union(row),
        })
    return {"status": "read" if parsed else "none_printed", "rows": parsed}, used


def _issue(block: List[_Line], sheet: Optional[_Line], width: float, skip: set) -> Dict[str, Any]:
    free = [l for l in block if id(l) not in skip and l is not sheet]
    phrases = [
        l for l in free
        if _ISSUE_RE.search(l.text) and not _LABEL_RE.search(l.text) and len(l.text.split()) <= 6
    ]
    phrase = _nearest(phrases, sheet)
    labels = [l for l in free if _DATE_LABEL_RE.match(l.text)]
    date, source = None, None
    for label in sorted(labels, key=lambda l: (l.cx - sheet.cx) ** 2 + (l.cy - sheet.cy) ** 2 if sheet else 0):
        value = _field_value(label, free, width, lambda l: bool(_DATE_RE.match(l.text)))
        if value is not None:
            date, source = value, f"label '{label.text}'"
            break
    if date is None and phrase is not None:
        dates = [l for l in free if _DATE_RE.match(l.text)]
        beside = [l for l in dates if _same_row(l, phrase)]
        stacked = [
            l for l in dates
            if min(l.box[2], phrase.box[2]) > max(l.box[0], phrase.box[0])
            and min(abs(l.box[1] - phrase.box[3]), abs(phrase.box[1] - l.box[3])) <= 3 * phrase.height
        ]
        pick = _nearest(beside, phrase) or _nearest(stacked, phrase)
        if pick is not None:
            date, source = pick, "beside the issue text"
    status = "read" if phrase is not None or date is not None else "not_shown"
    return {
        "issue": phrase.text if phrase is not None else None,
        "issue_date": date.text if date is not None else None,
        "issue_status": status,
        "issue_evidence": [e for e in (
            f"issue text '{phrase.text}'" if phrase is not None else None,
            f"date {source}" if source else None) if e],
    }


def _scale(block: List[_Line], width: float, skip: set) -> Dict[str, Any]:
    free = [l for l in block if id(l) not in skip]
    fields = []
    for label in (l for l in free if _SCALE_LABEL_RE.match(l.text)):
        value = _field_value(label, free, width, lambda l: bool(_SCALE_VALUE_RE.search(l.text)) and len(l.text) <= 30)
        if value is not None:
            fields.append(value.text)
    inline = [m.group(1).strip() for m in (_SCALE_INLINE_RE.match(l.text) for l in free) if m]
    candidates = [{"text": t, "form": "field"} for t in fields] + [{"text": t, "form": "caption"} for t in inline]
    distinct_fields = sorted(set(fields))
    if len(distinct_fields) == 1:
        return {"scale": distinct_fields[0], "scale_status": "read", "scale_candidates": candidates}
    if len(distinct_fields) > 1:
        return {"scale": None, "scale_status": "ambiguous", "scale_candidates": candidates}
    if len(set(inline)) == 1:
        return {"scale": inline[0], "scale_status": "read", "scale_candidates": candidates}
    if inline:
        return {"scale": None, "scale_status": "ambiguous", "scale_candidates": candidates}
    return {"scale": None, "scale_status": "not_shown", "scale_candidates": []}


def sheet_index(document: Dict[str, Any]) -> Dict[str, Any]:
    """``{"version", "layout", "pages": [sheet record per page]}``; boxes in display space."""

    meta = {int(p.get("page_number") or 0): p for p in document.get("pages") or []}
    lines = _page_lines(document)
    size = {page: (float(info.get("width") or 0), float(info.get("height") or 0)) for page, info in meta.items()}
    size = {page: dims for page, dims in size.items() if dims[0] and dims[1]}
    outer = {
        page: [l for l in lines.get(page, []) if _outer(l, *size[page])]
        for page in size
    }
    candidates = {page: [l for l in found if _is_sheet_id(l.text)] for page, found in outer.items()}
    slot = _slot(candidates, size)
    stable = _stable_lines(outer, size)
    bounds = _block_bounds(stable) if slot else {"layout": "unresolved", "stable_text_count": 0}

    records = []
    in_slot_pages = 0
    for page in sorted(size):
        width, height = size[page]
        info = meta[page]
        record: Dict[str, Any] = {
            "page": page, "source_page": page, "rotation": int(info.get("rotation") or 0),
            "sheet_id": None, "sheet_id_status": "unresolved", "source_bbox": None,
            "sheet_id_candidates": [], "evidence": [],
        }
        found = candidates.get(page) or []
        sheet = None
        if slot is not None:
            near = [
                l for l in found
                if abs(l.cx / width - slot[0]) <= _SLOT_TOLERANCE and abs(l.cy / height - slot[1]) <= _SLOT_TOLERANCE
            ]
            sheet = max(near, key=lambda l: l.size) if near else None
        if sheet is not None:
            in_slot_pages += 1
            record.update(sheet_id=sheet.text, sheet_id_status="read", source_bbox=sheet.box)
            record["evidence"].append("sheet-number slot shared by the set's title blocks")
            label = _nearest([
                l for l in outer[page]
                if _SHEET_LABEL_RE.match(l.text) and l.box[1] <= sheet.box[1] + 2
                and abs(l.cy - sheet.cy) <= 4 * sheet.height
            ], sheet)
            if label is not None:
                record["evidence"].append(f"label '{label.text}'")
        else:
            record["sheet_id_candidates"] = [
                {"text": l.text, "bbox": l.box} for l in sorted(found, key=lambda l: -l.size)[:5]
            ]
        block = _in_block(lines.get(page, []), bounds["layout"], stable, width, height, sheet)
        revision, used = _revisions(block, sheet)
        title = _title(block, sheet, stable, width, used)
        title_ids = set()
        if title.get("title_bbox"):
            tb = title["title_bbox"]
            title_ids = {id(l) for l in block if l.box[0] >= tb[0] - 1 and l.box[1] >= tb[1] - 1
                         and l.box[2] <= tb[2] + 1 and l.box[3] <= tb[3] + 1}
        record.update(title)
        record.update(_issue(block, sheet, width, used | title_ids))
        record["revision"] = revision
        record.update(_scale(block, width, used | title_ids))
        records.append(record)

    return {
        "version": SHEET_INDEX_VERSION,
        "space": "display",
        "layout": {
            **bounds,
            "slot": [round(v, 3) for v in slot] if slot else None,
            "pages_in_slot": in_slot_pages,
            "pages": len(records),
        },
        "pages": records,
    }
