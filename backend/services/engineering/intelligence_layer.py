"""Additive engineering intelligence: views, references, grids, levels, occurrences.

Display and navigation only. Nothing here is a quantity. A feet-inch string is
a dimension, never a grid. A reference whose target view is not printed stays
unresolved. Incomplete angle labels are not completed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from services.engineering.grid_intelligence import assemble_grids, classify_grid_text
from services.engineering.sheet_index import _page_lines

INTELLIGENCE_VERSION = "engineering_intelligence_v3"

_PLAN_ROLES = frozenset({"foundation_plan", "framing_plan", "roof_plan"})
_MARK_COMPONENTS = frozenset({"column", "lintel", "beam", "brace", "girder"})

_VIEW_LINE = re.compile(
    r"^(?:(?P<num>\d{1,2})\s+)?"
    r"(?P<body>(?:PARTIAL\s+|TYPICAL\s+|ENLARGED\s+)?"
    r"(?:SECTION|DETAIL|ELEVATION|SCHEDULE)S?(?:\s+[A-Z0-9]{1,3})?"
    r"|(?:PARTIAL\s+|TYPICAL\s+|ENLARGED\s+)?"
    r"(?:FOUNDATION(?:\s+AND\s+(?:1ST|FIRST)\s+FLOOR)?\s+)?"
    r"(?:ROOF\s+|FLOOR\s+|FRAMING\s+|REFLECTED\s+)?"
    r"(?:LOADING\s+|KEY\s+)?PLANS?"
    r"|(?:ROOF|FLOOR|LOW\s+ROOF|HIGH\s+ROOF)\s+FRAMING"
    r")$",
    re.I,
)
_SCALE_LINE = re.compile(
    r"^(?:SCALE\s*[:=]?\s*)?(?:"
    r"\d+\s*/\s*\d+\s*\"?\s*=\s*\d+\s*'\s*-?\s*\d+\s*\"?"
    r"|AS\s+INDICATED|NOT\s+TO\s+SCALE|N\.?T\.?S\.?"
    r")$",
    re.I,
)
_SHEET_TOKEN = r"S[-.]?\d(?:[-.0-9A-Z]{0,12})?"
_BUBBLE = re.compile(
    # ``6.1/S-103`` must not match the inner ``1/S-103``. A digit or a decimal
    # point before the label is still part of the same number.
    rf"(?<![\d.])\b(?P<label>[A-Z]{{1,2}}|\d{{1,2}})\s*/\s*(?P<sheet>{_SHEET_TOKEN})\b",
    re.I,
)
_SEE = re.compile(
    rf"\b(?:SEE|REFER\s+TO)\s+(?P<kind>DETAIL|SECTION|PLAN|SCHEDULE)"
    rf"(?:\s+(?P<label>[A-Z0-9]{{1,3}}))?"
    rf"(?:\s*/\s*(?P<sheet>{_SHEET_TOKEN}))?\b",
    re.I,
)
_PURE_DIM = re.compile(
    r"^[+\-]?\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?\s*\"?$"
    r"|^[+\-]?\d+(?:\s+\d+/\d+)?\s*\"$"
)
_INCOMPLETE_ANGLE = re.compile(
    r"\b(?P<label>(?:2L|L)\s*\d+(?:\.\d+)?\s*[xX×]\s*\d+(?:\.\d+)?)(?!\s*[xX×])\b"
)
_NOTE_LINE = re.compile(r"^(?P<num>\d{1,2})[.)]\s+(?P<text>.+)$")
_SCOPE = (
    ("existing", re.compile(r"\bEXIST(?:ING|\.)?\b", re.I)),
    ("demolition", re.compile(r"\bDEMO(?:LISH(?:ED)?|LITION)?\b", re.I)),
    ("alternate", re.compile(r"\bALTERNATE\b|\bOPTION\b", re.I)),
    ("future", re.compile(r"\bFUTURE\b", re.I)),
    ("temporary", re.compile(r"\bTEMP(?:ORARY)?\b", re.I)),
)
_NOTE_CATEGORY = (
    ("welding", re.compile(r"\bWELD", re.I)),
    ("bolting", re.compile(r"\bBOLT", re.I)),
    ("concrete", re.compile(r"\bCONCRETE\b", re.I)),
    ("steel", re.compile(r"\bSTEEL\b|\bA992\b|\bA36\b", re.I)),
    ("foundation", re.compile(r"\bFOUNDATION\b|\bFOOTING\b", re.I)),
    ("connection", re.compile(r"\bCONNECTION\b", re.I)),
    ("inspection", re.compile(r"\bINSPECT", re.I)),
    ("loading", re.compile(r"\bLOAD", re.I)),
    ("coordination", re.compile(r"\bCOORDINAT", re.I)),
    ("erection", re.compile(r"\bERECT", re.I)),
)


def compact_sheet(value: Optional[str]) -> str:
    """Hyphen-insensitive sheet id. ``S-122-O`` and ``S122-O`` both become ``S122O``."""

    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def is_dimension_text(text: str) -> bool:
    return bool(_PURE_DIM.match(str(text or "").strip()))


def classify_view_title(text: str, scale_nearby: bool = False) -> Optional[Dict[str, Any]]:
    """A whole line that is a view title, or None. A keyword inside a sentence is not a view.

    A bare word such as ``SECTION`` counts only when a scale line sits under it.
    ``SECTION A`` is a title on its own.
    """

    raw = " ".join(str(text or "").split())
    if not raw or len(raw) > 80 or len(raw.split()) > 12:
        return None
    match = _VIEW_LINE.match(raw)
    if match is None:
        return None
    body = (match.group("body") or raw).upper()
    number = match.group("num")
    label = None
    tail = re.search(r"\b(?:SECTION|DETAIL|ELEVATION)\s+([A-Z0-9]{1,3})$", body)
    if tail:
        label = tail.group(1)
    bare = re.fullmatch(
        r"(?:PARTIAL\s+|TYPICAL\s+|ENLARGED\s+)?(?:SECTIONS?|DETAILS?|ELEVATIONS?|SCHEDULES?)",
        body,
    )
    if bare and not (label or number) and not scale_nearby:
        return None
    view_type = _view_type(body)
    return {
        "view_number": label or number,
        "view_title": raw,
        "view_type": view_type,
        "status": "read",
        "evidence": "printed view title",
    }


def _view_type(body: str) -> str:
    if "LOADING" in body:
        return "loading_plan"
    if re.search(r"\bSECTIONS?\b", body):
        return "section"
    if re.search(r"\bDETAILS?\b", body):
        return "detail"
    if re.search(r"\bELEVATIONS?\b", body):
        return "elevation"
    if re.search(r"\bSCHEDULES?\b", body):
        return "schedule"
    if "FOUNDATION" in body:
        return "foundation_plan"
    if "ROOF" in body:
        return "roof_plan"
    if "REFLECTED" in body:
        return "reflected_plan"
    if "ENLARGED" in body:
        return "enlarged_plan"
    if "FRAMING" in body or "FLOOR" in body:
        return "framing_plan"
    if "KEY" in body:
        return "key_plan"
    if "PLAN" in body:
        return "plan"
    return "review"


def _role_view(role: Optional[str]) -> str:
    return {
        "foundation_plan": "foundation_plan",
        "framing_plan": "framing_plan",
        "roof_plan": "roof_plan",
        "elevation": "elevation",
        "section": "section",
        "detail": "detail",
        "foundation_details": "detail",
        "concrete_details": "detail",
        "steel_details": "detail",
        "masonry_details": "detail",
        "schedule": "schedule",
        "loading": "loading_plan",
        "general_notes": "miscellaneous",
    }.get(role or "", "review")


def _sheet_lookup(pages: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    found: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for page in pages:
        if page.get("sheet_id_status") == "read" and page.get("sheet_id"):
            found[compact_sheet(page["sheet_id"])].append(page)
    return found


def resolve_reference(label: Optional[str], sheet: Optional[str], kind: str,
                      sheets: Dict[str, List[Dict[str, Any]]],
                      views_by_page: Dict[int, List[Dict[str, Any]]],
                      source_sheet: Optional[str]) -> Dict[str, Any]:
    """Match a printed target to the sheet index and a printed view number. Never guess a view."""

    if not sheet and not label:
        return {"status": "ambiguous", "target_sheet": None, "target_page": None,
                "target_view": None, "target_number": label, "evidence": "no sheet and no view number"}
    if not sheet:
        return {"status": "ambiguous", "target_sheet": None, "target_page": None,
                "target_view": None, "target_number": label,
                "evidence": f"{kind} names no sheet"}
    owners = sheets.get(compact_sheet(sheet)) or []
    if len(owners) > 1:
        return {"status": "ambiguous", "target_sheet": sheet, "target_page": None,
                "target_view": None, "target_number": label,
                "evidence": "more than one sheet compacts to this id"}
    if not owners:
        return {"status": "target_missing", "target_sheet": sheet, "target_page": None,
                "target_view": None, "target_number": label,
                "evidence": "no sheet index id matches"}
    owner = owners[0]
    target_sheet = owner.get("sheet_id")
    page = owner.get("page")
    if label:
        hits = [
            view for view in views_by_page.get(page) or []
            if view.get("view_number") and str(view["view_number"]).upper() == str(label).upper()
            and view.get("status") == "read"
        ]
        if len(hits) == 1:
            return {"status": "target_view_found", "target_sheet": target_sheet, "target_page": page,
                    "target_view": hits[0].get("view_id"), "target_number": label,
                    "evidence": "printed view number on the target sheet"}
        if len(hits) > 1:
            return {"status": "ambiguous", "target_sheet": target_sheet, "target_page": page,
                    "target_view": None, "target_number": label,
                    "evidence": "more than one printed view uses this number"}
        status = "target_sheet_only"
        if source_sheet and compact_sheet(source_sheet) == compact_sheet(target_sheet):
            status = "target_sheet_only"
        return {"status": status, "target_sheet": target_sheet, "target_page": page,
                "target_view": None, "target_number": label,
                "evidence": "target sheet is in the index; that view number is not a printed title"}
    return {"status": "target_sheet_found", "target_sheet": target_sheet, "target_page": page,
            "target_view": None, "target_number": None,
            "evidence": "target sheet is in the index; the note names no view number"}


def _box(line) -> List[float]:
    return [round(float(v), 1) for v in line.box]


_SHEET_CALLOUT = re.compile(r"^S-?\d{2,4}[A-Z]?$")
# Same center and gap as ``_callout_reason``. The sheet token is the reference
# token, so ``S-301-O`` counts; the grid rejection above does not use it.
_STACK_CENTER = 12.0
_STACK_GAP = 8.0
_CALLOUT_LABEL = re.compile(r"^(?:[A-Z]{1,2}|\d{1,2})$")
_SHEET_LINE = re.compile(rf"^{_SHEET_TOKEN}$", re.I)
_FOOT_STATION = re.compile(r"^\d+\s*'$")
_BARE_DETAIL_OR_SECTION = re.compile(r"^(?:SECTION|DETAIL)$", re.I)
_ADJACENT_VIEW_NUMBER = re.compile(r"^(?:[A-Z]{1,2}|\d{1,2})$")
# Furley and OSSE print the letter or number on the same row, about 24–28px
# to the left of the word SECTION. A sheet id sits below that row.
_ADJACENT_NUMBER_GAP = 40.0


def _callout_reason(line, page_lines) -> Optional[str]:
    """A detail bubble stacked on a sheet id, or a digit in a foot-station chain.

    ``F`` printed above ``S401`` is a callout. ``0`` on the same baseline as ``4'``
    is a dimension station. Neither is a grid bubble.
    """

    box = line.box
    cx = (box[0] + box[2]) / 2.0
    for other in page_lines:
        if other is line:
            continue
        text = " ".join(str(other.text or "").split())
        ob = other.box
        if _SHEET_CALLOUT.fullmatch(text):
            ocx = (ob[0] + ob[2]) / 2.0
            gap = ob[1] - box[3]
            if abs(cx - ocx) <= 12 and 0 <= gap <= 8:
                return "sheet_callout"
        if re.fullmatch(r"\d{1,2}", " ".join(str(line.text or "").split())) and _FOOT_STATION.fullmatch(text):
            if abs(box[1] - ob[1]) <= 2 and 0 <= ob[0] - box[2] <= 40:
                return "dimension_station"
    return None


def _grid_label(page: int, sheet_id: Optional[str], line, width: float, height: float) -> Dict[str, Any]:
    box = _box(line)
    cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    sides = []
    if width and cx <= 0.14 * width:
        sides.append("left")
    if width and cx >= 0.86 * width:
        sides.append("right")
    if height and cy <= 0.14 * height:
        sides.append("top")
    if height and cy >= 0.86 * height:
        sides.append("bottom")
    return {
        "text": line.text, "pdf_page": page, "sheet_id": sheet_id, "bbox": box,
        "cx": cx, "cy": cy, "height": max(box[3] - box[1], 1.0), "sides": sides,
    }


def _in_title_block(line, width: float, height: float) -> bool:
    return bool(width and height and (line.box[0] >= 0.84 * width or line.box[1] >= 0.72 * height))


def _evidence(page: int, sheet: Optional[str], line, text: str, status: str) -> Dict[str, Any]:
    return {
        "pdf_page": page, "sheet_id": sheet, "view_id": None,
        "bbox": _box(line) if line is not None else None,
        "source_text": text, "source_type": "pdf_text", "status": status,
    }


def build_engineering_intelligence(document: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """One additive object. Existing profile keys are not modified."""

    index_pages = (profile.get("sheet_index") or {}).get("pages") or []
    by_page = {p.get("page"): p for p in index_pages}
    sheets = _sheet_lookup(index_pages)
    meta = {int(p.get("page_number") or 0): p for p in document.get("pages") or []}
    lines = _page_lines(document)

    views: List[Dict[str, Any]] = []
    view_seq = 0
    for page in sorted(by_page):
        record = by_page[page]
        info = meta.get(page) or {}
        width, height = float(info.get("width") or 0), float(info.get("height") or 0)
        sheet_id = record.get("sheet_id") if record.get("sheet_id_status") == "read" else None
        interior = []
        page_lines = lines.get(page) or []
        for line in page_lines:
            # The right strip is the title block. The bottom band on these
            # sheets is still drawing: Furley prints SECTION N there.
            if width and line.box[0] >= 0.84 * width:
                continue
            if sheet_id and line.text.upper() == str(record.get("sheet_title") or "").upper():
                continue
            in_bottom = bool(height and line.box[1] >= 0.72 * height)
            scale = _nearby_scale(line, page_lines)
            classified = classify_view_title(line.text, scale_nearby=bool(scale))
            number_line = _paired_view_number(line, page_lines, classified)
            if in_bottom and number_line is None:
                continue
            if number_line is not None:
                if classified is None:
                    classified = classify_view_title(line.text, scale_nearby=True)
                if classified is not None and not classified.get("view_number"):
                    classified = {
                        **classified,
                        "view_number": number_line.text,
                        "evidence": "printed view number beside the title",
                    }
            if classified is None:
                continue
            view_seq += 1
            interior.append({
                "view_id": f"V{view_seq}",
                "sheet_id": sheet_id,
                "pdf_page": page,
                "view_number": classified["view_number"],
                "view_title": classified["view_title"],
                "view_type": classified["view_type"],
                "scale": scale,
                "bbox": _union_box(line, number_line) if number_line is not None else _box(line),
                "boundary_status": "title_only",
                "source_text": line.text,
                "evidence": classified["evidence"],
                "status": "read",
            })
        if interior:
            views.extend(interior)
        elif record.get("sheet_title") and record.get("title_status") in ("read", "read_unlabeled"):
            view_seq += 1
            views.append({
                "view_id": f"V{view_seq}",
                "sheet_id": sheet_id,
                "pdf_page": page,
                "view_number": None,
                "view_title": record.get("sheet_title"),
                "view_type": _role_view(record.get("sheet_role")),
                "scale": record.get("scale"),
                "bbox": record.get("title_bbox"),
                "boundary_status": "sheet_title",
                "source_text": record.get("sheet_title"),
                "evidence": "sheet title; no separate viewport title on this sheet",
                "status": "sheet_title",
            })

    views_by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for view in views:
        views_by_page[view["pdf_page"]].append(view)

    references: List[Dict[str, Any]] = []
    dimensions: List[Dict[str, Any]] = []
    grid_labels: List[Dict[str, Any]] = []
    grid_rejections: List[Dict[str, Any]] = []
    grid_marks: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    scope_flags: List[Dict[str, Any]] = []
    incomplete: List[Dict[str, Any]] = []
    dim_total = 0
    scope_counts: Dict[str, int] = defaultdict(int)

    for page, page_lines in lines.items():
        record = by_page.get(page) or {}
        info = meta.get(page) or {}
        width, height = float(info.get("width") or 0), float(info.get("height") or 0)
        sheet_id = record.get("sheet_id") if record.get("sheet_id_status") == "read" else None
        role = record.get("sheet_role")
        far_labels = []
        for line in page_lines:
            text = line.text
            if role in _PLAN_ROLES and width:
                kind = classify_grid_text(text)
                in_plan = line.box[0] < 0.82 * width
                in_repeat_band = 0.82 * width <= line.box[0] < 0.94 * width
                if kind == "label" and (in_plan or in_repeat_band):
                    callout = _callout_reason(line, page_lines)
                    if callout:
                        grid_rejections.append({
                            "text": text, "pdf_page": page, "sheet_id": sheet_id,
                            "bbox": _box(line), "reason": callout,
                        })
                    elif in_plan:
                        grid_labels.append(_grid_label(page, sheet_id, line, width, height))
                    else:
                        far_labels.append(line)
                elif in_plan and kind == "member_mark":
                    grid_marks.append(_grid_label(page, sheet_id, line, width, height))
                    grid_rejections.append({
                        "text": text, "pdf_page": page, "sheet_id": sheet_id,
                        "bbox": _box(line), "reason": "member_mark",
                    })
                elif in_plan and kind in {"dimension", "sheet_reference", "joist_mark"}:
                    grid_rejections.append({
                        "text": text, "pdf_page": page, "sheet_id": sheet_id,
                        "bbox": _box(line), "reason": kind,
                    })
            if _in_title_block(line, width, height):
                continue
            if is_dimension_text(text):
                dim_total += 1
                if len(dimensions) < 200:
                    dimensions.append({
                        "value": text, "dimension_type": "elevation" if text[:1] in "+-" else "linear",
                        "sheet_id": sheet_id, "pdf_page": page, "view_id": None,
                        "bbox": _box(line), "nearby_context": None,
                        "evidence": "whole line is a printed dimension", "status": "read",
                    })
                continue
            for match in _BUBBLE.finditer(text):
                references.append(_reference_record(
                    page, sheet_id, line, match.group(0), "bubble", match.group("label"),
                    match.group("sheet"), sheets, views_by_page,
                ))
            if not _BUBBLE.search(text):
                for match in _SEE.finditer(text):
                    label = match.group("label")
                    sheet = match.group("sheet")
                    if label and not _CALLOUT_LABEL.fullmatch(label):
                        label = None
                    if not sheet and not label:
                        continue
                    references.append(_reference_record(
                        page, sheet_id, line, match.group(0), match.group("kind").lower(),
                        label, sheet, sheets, views_by_page,
                    ))
            for match in _INCOMPLETE_ANGLE.finditer(text):
                printed = re.sub(r"\s+", "", match.group("label").upper().replace("×", "X"))
                if len(incomplete) < 40:
                    incomplete.append({
                        "printed_fact": printed,
                        "candidate_cross_reference": None,
                        "resolved_definition": None,
                        "sheet_id": sheet_id, "pdf_page": page, "bbox": _box(line),
                        "evidence": "printed label has no thickness",
                        "status": "review_required",
                    })
            if record.get("sheet_role") == "general_notes":
                note = _NOTE_LINE.match(text)
                if note and len(notes) < 80:
                    body = note.group("text")
                    notes.append({
                        "note_number": note.group("num"), "note_text": body,
                        "category": _note_category(body), "sheet_id": sheet_id,
                        "pdf_page": page, "view_id": None, "bbox": _box(line),
                        "evidence": "numbered line on a general-notes sheet", "status": "read",
                    })
            for flag, pattern in _SCOPE:
                if pattern.search(text):
                    scope_counts[flag] += 1
                    if sum(1 for item in scope_flags if item["flag"] == flag) < 12:
                        scope_flags.append({
                            "flag": flag, "source_text": text[:160], "sheet_id": sheet_id,
                            "pdf_page": page, "bbox": _box(line),
                            "evidence": "printed word; not an exclusion", "status": "review",
                        })
        for line in far_labels:
            box = _box(line)
            cx = (box[0] + box[2]) / 2.0
            cy = (box[1] + box[3]) / 2.0
            row = sum(1 for item in grid_labels if item["pdf_page"] == page and abs(item["cy"] - cy) <= 20)
            column = sum(1 for item in grid_labels if item["pdf_page"] == page and abs(item["cx"] - cx) <= 20)
            if row >= 3 or column >= 3:
                grid_labels.append(_grid_label(page, sheet_id, line, width, height))
        for label, sheet in _stacked_callouts(page_lines, width):
            text = f"{label.text}/{sheet.text}"
            references.append(_reference_record(
                page, sheet_id, label, text, "bubble", label.text, sheet.text,
                sheets, views_by_page, bbox=_union_box(label, sheet), stacked=True,
            ))

    levels = _levels(profile)
    occurrences = _occurrences(profile, lines, by_page)
    schedules = _schedules(profile)
    objects = _objects(profile)
    relationships = _relationships(views, references, occurrences)
    warnings = _warnings(profile, index_pages, references, incomplete, levels, occurrences)
    multi_view_pages = [
        page for page, group in views_by_page.items()
        if sum(1 for view in group if view.get("status") == "read") >= 2
    ]
    grid_layer = assemble_grids(
        document, grid_labels, grid_rejections,
        multi_view_pages=multi_view_pages, meta=meta, marks=grid_marks,
    )

    return {
        "version": INTELLIGENCE_VERSION,
        "views": views,
        "references": references[:400],
        "reference_count": len(references),
        "relationships": relationships[:400],
        "grids": grid_layer["grids"],
        "grid_intersections": grid_layer["grid_intersections"],
        "grid_allocations": grid_layer["grid_allocations"],
        "grid_diagnostics": grid_layer["grid_diagnostics"],
        "grid_rejections": grid_layer["grid_rejections"],
        "grid_status": "confirmed" if grid_layer["grid_diagnostics"]["confirmed_grid_labels"] else "candidate",
        "levels": levels,
        "objects": objects,
        "occurrences": occurrences,
        "schedules": schedules,
        "dimensions": dimensions,
        "dimension_count": dim_total,
        "notes": notes,
        "incomplete_labels": incomplete,
        "scope_flags": scope_flags,
        "scope_counts": dict(scope_counts),
        "warnings": warnings,
    }


def _paired_view_number(title, page_lines, classified: Optional[Dict[str, Any]]):
    """The one short line beside a bare DETAIL or SECTION title, or None.

    Zero neighbors leave the title unchanged. Two or more neighbors are not a
    view number: the caller keeps ``target_sheet_only`` rather than picking one.
    A number already printed on the title line is left as it is.
    """

    if classified is not None and classified.get("view_number"):
        return None
    if not _BARE_DETAIL_OR_SECTION.fullmatch(str(title.text or "").strip()):
        return None
    found = []
    for other in page_lines:
        if other is title or not _ADJACENT_VIEW_NUMBER.fullmatch(str(other.text or "").strip()):
            continue
        overlap = min(title.box[3], other.box[3]) - max(title.box[1], other.box[1])
        if overlap < 0.4 * min(title.height, other.height):
            continue
        gap_left = title.box[0] - other.box[2]
        gap_right = other.box[0] - title.box[2]
        gap = gap_left if gap_left >= 0 else gap_right
        if 0 <= gap <= _ADJACENT_NUMBER_GAP:
            found.append(other)
    return found[0] if len(found) == 1 else None


def _union_box(title, number_line) -> List[float]:
    boxes = (title.box, number_line.box)
    return [
        round(min(box[0] for box in boxes), 1),
        round(min(box[1] for box in boxes), 1),
        round(max(box[2] for box in boxes), 1),
        round(max(box[3] for box in boxes), 1),
    ]


def _nearby_scale(title, page_lines) -> Optional[str]:
    below = [
        line for line in page_lines
        if line is not title and line.box[1] >= title.box[1]
        and line.box[1] - title.box[3] <= 2.5 * title.height
        and abs(line.box[0] - title.box[0]) <= 80
        and _SCALE_LINE.match(line.text)
    ]
    return below[0].text if below else None


def _stacked_callouts(page_lines, width):
    """``(label, sheet)`` pairs. One label and one sheet id, or nothing.

    The label sits directly above the sheet id, within the same center and
    gap ``_callout_reason`` uses. Two labels on one sheet, or one label on
    two sheets, produce no pair. A dimension is not a label.
    """

    # The right strip is the title block. The bottom band is still drawing:
    # Burrville prints 7 / S-301 there. Inline notes keep the wider skip.
    usable = [line for line in page_lines if not (width and line.box[0] >= 0.84 * width)]
    labels = [line for line in usable if _CALLOUT_LABEL.fullmatch(line.text) and not is_dimension_text(line.text)]
    sheets = [line for line in usable if _SHEET_LINE.fullmatch(line.text)]
    pairs = []
    for sheet in sheets:
        center = (sheet.box[0] + sheet.box[2]) / 2.0
        above = []
        for label in labels:
            gap = sheet.box[1] - label.box[3]
            label_center = (label.box[0] + label.box[2]) / 2.0
            if abs(label_center - center) <= _STACK_CENTER and 0 <= gap <= _STACK_GAP:
                above.append(label)
        if len(above) == 1:
            pairs.append((above[0], sheet))
    label_count: Dict[int, int] = defaultdict(int)
    sheet_count: Dict[int, int] = defaultdict(int)
    for label, sheet in pairs:
        label_count[id(label)] += 1
        sheet_count[id(sheet)] += 1
    return [
        (label, sheet) for label, sheet in pairs
        if label_count[id(label)] == 1 and sheet_count[id(sheet)] == 1
    ]


def _callout_evidence(text, resolved, view) -> str:
    status = resolved["status"]
    sheet = resolved.get("target_sheet")
    number = resolved.get("target_number")
    if status == "target_view_found" and view is not None:
        kind = {"section": "Section", "detail": "Detail"}.get(view.get("view_type"), "View")
        return f"Printed callout {text}; target sheet {sheet} contains one printed {kind} {number} view."
    if status == "target_sheet_only":
        return f"Printed callout {text}; target sheet {sheet} is in the index; view {number} is not a printed title."
    if status == "target_missing":
        return f"Printed callout {text}; no sheet with that id."
    if status == "ambiguous" and sheet:
        return f"Printed callout {text}; more than one printed view uses {number}."
    return resolved["evidence"]


def _reference_record(page, sheet_id, line, text, kind, label, target, sheets, views_by_page,
                      bbox=None, stacked=False):
    resolved = resolve_reference(label, target, kind, sheets, views_by_page, sheet_id)
    view = None
    if resolved["status"] == "target_view_found":
        view = next((
            item for item in views_by_page.get(resolved["target_page"]) or []
            if item.get("view_id") == resolved["target_view"] and item.get("bbox")
        ), None)
    record = {
        "reference_text": text,
        "reference_type": kind,
        "source_sheet": sheet_id,
        "source_page": page,
        "source_view": None,
        "target_sheet": resolved["target_sheet"],
        "target_page": resolved["target_page"],
        "target_view": resolved["target_view"],
        "target_number": resolved["target_number"],
        "status": resolved["status"],
        "bbox": bbox if bbox is not None else _box(line),
        "evidence": _callout_evidence(text, resolved, view) if stacked else resolved["evidence"],
        "source_text": text if stacked else line.text,
    }
    if view is not None:
        record["target_bbox"] = list(view["bbox"])
        record["target_view_type"] = view.get("view_type")
    return record


def _note_category(text: str) -> str:
    for name, pattern in _NOTE_CATEGORY:
        if pattern.search(text):
            return name
    return "general"


def _levels(profile: Dict[str, Any]) -> Dict[str, Any]:
    building = []
    for level in (profile.get("levels") or {}).get("schedule_levels") or []:
        sources = [{
            "kind": "schedule", "value": level.get("printed"), "sheet_id": level.get("sheet"),
            "pdf_page": level.get("page"), "name": level.get("name"),
        }]
        conflict = False
        for match in level.get("plan_matches") or []:
            if match.get("comparison") != "differs":
                continue
            conflict = True
            for value in match.get("values") or []:
                sources.append({
                    "kind": "plan", "value": value.get("raw") or value.get("display"),
                    "sheet_id": match.get("sheet"), "pdf_page": match.get("page"),
                    "name": value.get("name") or level.get("name"),
                    "surface": value.get("surface"),
                })
        building.append({
            "name": level.get("name"), "status": "conflict" if conflict else "read",
            "sources": sources, "evidence": "schedule level; plan values kept when they differ",
        })
    local = []
    for item in (profile.get("levels") or {}).get("plan_elevations") or []:
        if len(local) >= 40:
            break
        local.append({
            "name": item.get("name") or item.get("surface"),
            "value": item.get("raw") or item.get("printed") or item.get("text"),
            "sheet_id": item.get("sheet"), "pdf_page": item.get("page"),
            "kind": "local", "status": item.get("status") or "read",
            "evidence": "printed on a plan; not treated as a building level",
        })
    return {"building_levels": building, "local_elevations": local}


def _marks(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    found = []
    seen = set()
    for item in profile.get("definitions") or []:
        mark = str(item.get("mark") or "").upper()
        if not mark or mark in seen:
            continue
        seen.add(mark)
        found.append({
            "mark": mark, "page": item.get("page"), "sheet_id": item.get("sheet"),
            "component": item.get("component"), "designation": item.get("designation"),
            "definition_id": item.get("id"),
        })
    for entry in (profile.get("column_schedule") or {}).get("entries") or []:
        mark = str(entry.get("mark") or "").upper()
        if not mark or mark in seen:
            continue
        seen.add(mark)
        found.append({
            "mark": mark, "page": entry.get("page"), "sheet_id": entry.get("sheet"),
            "component": "column", "designation": entry.get("section") or entry.get("designation"),
            "definition_id": entry.get("schedule_id"),
        })
    return found


def _occurrences(profile, lines, by_page) -> List[Dict[str, Any]]:
    ledger = []
    for spec in _marks(profile):
        pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(spec['mark'])}(?![A-Z0-9])", re.I)
        hits = []
        for page, page_lines in lines.items():
            if page == spec.get("page"):
                continue
            record = by_page.get(page) or {}
            sheet_id = record.get("sheet_id") if record.get("sheet_id_status") == "read" else None
            for line in page_lines:
                if pattern.search(line.text):
                    hits.append({
                        "sheet_id": sheet_id, "pdf_page": page, "bbox": _box(line),
                        "source_text": line.text[:80], "view_id": None,
                        "grid_reference": None, "level_reference": None,
                    })
                    break
        status = "defined_and_seen" if hits else "defined_but_not_seen"
        ledger.append({
            "mark": spec["mark"], "object_type": spec.get("component"),
            "definition_reference": spec.get("definition_id"),
            "printed_designation": spec.get("designation"),
            "status": status, "occurrence_count": len(hits),
            "occurrences": hits[:12],
            "evidence": "whole-word mark text outside the definition sheet",
            "quantity": None,
        })
    return ledger


def _schedules(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for schedule in (profile.get("column_schedule") or {}).get("schedules") or []:
        rows.append({
            "schedule_type": "concrete_column" if schedule.get("material_group") == "concrete" else "column",
            "title": schedule.get("title") or schedule.get("name"),
            "sheet_id": schedule.get("sheet"), "pdf_page": schedule.get("page"),
            "evidence": "existing column schedule reader", "status": "read",
        })
    for schedule in profile.get("supporting_schedules") or []:
        rows.append({
            "schedule_type": schedule.get("kind") or "supporting",
            "title": schedule.get("title"),
            "sheet_id": schedule.get("sheet"), "pdf_page": schedule.get("page"),
            "evidence": "existing supporting schedule reader", "status": "read",
        })
    return rows


def _objects(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    objects = []
    for item in (profile.get("definitions") or [])[:80]:
        objects.append({
            "object_type": item.get("component") or item.get("status"),
            "printed_label": item.get("mark"),
            "normalized_label": item.get("designation") or item.get("printed"),
            "sheet_id": item.get("sheet"), "pdf_page": item.get("page"),
            "status": "read" if item.get("designation") or item.get("printed") else "review",
            "evidence": "existing schedule definition",
        })
    return objects


def _relationships(views, references, occurrences) -> List[Dict[str, Any]]:
    edges = []
    for view in views:
        edges.append({
            "type": "sheet_view", "source": view.get("sheet_id"), "target": view["view_id"],
            "status": "resolved" if view["status"] == "read" else "candidate",
            "evidence": view["evidence"], "confidence": 0.9 if view["status"] == "read" else 0.6,
        })
    for ref in references:
        status = "resolved" if ref["status"] == "target_view_found" else (
            "candidate" if ref["status"] in ("target_sheet_found", "target_sheet_only") else "unresolved"
        )
        edges.append({
            "type": "reference_target", "source": ref.get("source_sheet"),
            "target": ref.get("target_view") or ref.get("target_sheet"),
            "status": status, "evidence": ref["evidence"],
            "confidence": 0.9 if status == "resolved" else 0.4,
        })
    for item in occurrences:
        if item["status"] != "defined_and_seen":
            continue
        edges.append({
            "type": "occurrence_definition", "source": item["mark"],
            "target": item.get("definition_reference"), "status": "candidate",
            "evidence": "same mark text; grid and level not attached", "confidence": 0.5,
        })
    return edges


def _warnings(profile, pages, references, incomplete, levels, occurrences) -> List[Dict[str, Any]]:
    warnings = []
    for level in levels["building_levels"]:
        if level["status"] != "conflict":
            continue
        values = ", ".join(f"{s.get('sheet_id') or 'plan'}: {s.get('value')}" for s in level["sources"] if s.get("value"))
        warnings.append({
            "type": "level_conflict", "severity": "high", "status": "open",
            "message": f"{level['name']} has more than one printed value ({values}). Neither is selected.",
            "sheet_id": None, "view_id": None, "evidence": level["evidence"],
        })
    for page in pages:
        if page.get("classification_status") == "review":
            warnings.append({
                "type": "ambiguous_sheet", "severity": "medium", "status": "open",
                "message": f"{page.get('sheet_id') or 'sheet'} title needs review: {page.get('classification_evidence')}",
                "sheet_id": page.get("sheet_id"), "view_id": None, "pdf_page": page.get("page"),
                "evidence": page.get("sheet_title"),
            })
    for ref in references:
        if ref["status"] in ("target_missing", "target_sheet_only", "ambiguous"):
            if len([w for w in warnings if w["type"] == "unresolved_reference"]) >= 30:
                break
            warnings.append({
                "type": "unresolved_reference", "severity": "medium" if ref["status"] == "target_missing" else "low",
                "status": "open",
                "message": f"{ref['reference_text']} is {ref['status'].replace('_', ' ')}",
                "sheet_id": ref.get("source_sheet"), "pdf_page": ref.get("source_page"),
                "view_id": None, "evidence": ref["evidence"],
            })
    for label in incomplete[:12]:
        warnings.append({
            "type": "incomplete_label", "severity": "medium", "status": "open",
            "message": f"{label['printed_fact']} is printed without a thickness. It is not completed.",
            "sheet_id": label.get("sheet_id"), "pdf_page": label.get("pdf_page"),
            "view_id": None, "evidence": label["evidence"],
        })
    unseen = [item["mark"] for item in occurrences if item["status"] == "defined_but_not_seen" and item.get("object_type") in _MARK_COMPONENTS]
    if unseen:
        warnings.append({
            "type": "defined_but_not_seen", "severity": "low", "status": "open",
            "message": "Marks defined on a schedule and not found as whole words on another sheet: " + ", ".join(unseen[:12]),
            "sheet_id": None, "view_id": None,
            "evidence": "text search only; absence is not a quantity of zero",
        })
    return warnings
