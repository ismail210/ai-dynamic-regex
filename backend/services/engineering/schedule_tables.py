"""Ruled schedule tables read from the PDF's drawn table lines.

PyMuPDF ``find_tables`` returns one table per ruled grid, so adjacent tables
(pier | column) never merge and header words need no exact spelling. It costs
seconds per full sheet, so it only runs on pages whose words show a schedule
header row or a Revit ``Column Locations`` row, clipped to that region.

This module only describes table structure (title, header labels, body cells,
Revit location columns). ``schedule_grid`` decides what the rows mean.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

import fitz

from services.engineering.column_schedule import (
    matrix_key_role,
    read_column_matrix,
    schedule_captions,
    visible_phrases,
)

logger = logging.getLogger(__name__)

MARK_HEADERS = frozenset(
    {
        "MARK",
        "TYPE",
        "PIER",
        "PIER TYPE",
        "PIER MARK",
        "COLUMN MARK",
        "BEAM MARK",
        "LINTEL MARK",
        "TAG",
        "ID",
    }
)
SIZE_HEADERS = frozenset(
    {
        "SIZE",
        "COLUMN SIZE",
        "BEAM SIZE",
        "LINTEL SIZE",
        "MEMBER SIZE",
        "SECTION",
        "DESIGNATION",
        "SHAPE",
        "MEMBER",
    }
)
# Second word on a header line that marks it as a schedule header, next to
# MARK / TYPE. Concrete schedules use WIDTH / DIMENSIONS instead of SIZE.
_HEADER_PARTNERS = frozenset(
    {"SIZE", "SECTION", "DESIGNATION", "SHAPE", "WIDTH", "DIMENSIONS", "DIAMETER", "LENGTH"}
)
_LOCATION_LABEL = "COLUMNLOCATION"
_PLATE_ROW_LABEL = "BASE PLATE SIZE"
_INCHES = r'(?:\d+(?:[-\s]+\d+/\d+)?|\d+/\d+)"?'
# Whole-cell base plate size, with an optional trailing note star.
# x / X / × are the same separator. The pattern does not assign thickness.
_BASE_PLATE_SIZE_RE = re.compile(
    rf"{_INCHES}\s*[xX×]\s*{_INCHES}\s*[xX×]\s*{_INCHES}(?:\s*\*)?"
)
_MERGED_PLATE_LABEL_RE = re.compile(r"BASE PLATE (?:SIZE )?(.+?)(?: SIZE)?", re.IGNORECASE)
_GRID_LOCATION_RE = re.compile(r"(?:^|[A-Z0-9.'])-[A-Z0-9.]", re.IGNORECASE)
_MATRIX_MARK_RE = re.compile(r"[A-Z]{1,3}-?\d{1,3}[A-Z]?")
_MAX_HEADER_ROW = 4
# Largest blank gap between two words of one schedule header line, and the
# vertical reach of a stacked (two-line) header around the MARK word.
_HEADER_WORD_GAP = 150.0
_HEADER_STACK = 14.0
_TITLE_GAP = 40.0


def header_label(text: Any) -> str:
    return " ".join(str(text or "").split()).upper()


def read_ruled_tables(
    pdf_path: str,
    words: Iterable[Dict[str, Any]],
    *,
    pages: Optional[Iterable[int]] = None,
) -> List[Dict[str, Any]]:
    """Schedule table records for candidate pages of ``pdf_path``."""

    wanted = set(pages) if pages is not None else None
    by_page: Dict[int, List[tuple]] = {}
    for word in words:
        page = int(word.get("page_number") or word.get("page") or 0)
        bbox = word.get("bbox") or []
        if len(bbox) >= 4 and (wanted is None or page in wanted):
            by_page.setdefault(page, []).append((*bbox[:4], word.get("text") or ""))
    candidates = sorted(page for page, found in by_page.items() if _schedule_regions(found))
    if not candidates:
        return []
    records: List[Dict[str, Any]] = []
    with fitz.open(pdf_path) as document:
        for page_number in candidates:
            if not 1 <= page_number <= document.page_count:
                continue
            page = document[page_number - 1]
            page_words = page.get_text("words")
            drawings = page.get_drawings()
            rules = _vertical_rules(drawings, page.rect.height)
            phrases: Optional[tuple] = None
            fitted = [
                clip
                for clip in (
                    _fit_to_rules(region, anchor_y, rules)
                    for region, anchor_y in _schedule_regions(page_words)
                )
                if clip is not None
            ]
            seen: set[tuple] = set()
            for clip in _merge_overlapping(fitted, page.rect):
                try:
                    tables = page.find_tables(clip=clip).tables
                except Exception:  # third-party table finder on arbitrary vector content
                    logger.warning("find_tables failed on page %s", page_number, exc_info=True)
                    continue
                for table in tables:
                    key = tuple(round(value) for value in table.bbox)
                    if key in seen:
                        continue
                    seen.add(key)
                    record = _table_record(table, page_words, page_number)
                    if record and record["layout"] in ("transposed", "matrix"):
                        if phrases is None:
                            phrases = visible_phrases(page, drawings)
                        visible, suppressed = phrases
                        matrix = read_column_matrix(table, page_number, visible, suppressed)
                        if matrix:
                            matrix["captions"] = schedule_captions(record["bbox"], visible)
                            record["column_matrix"] = matrix
                        elif record["layout"] == "matrix":
                            record = None
                    if record:
                        records.append(record)
    return records


def _merge_overlapping(regions: List[fitz.Rect], page_rect: fitz.Rect) -> List[fitz.Rect]:
    """Clip rects: overlapping regions merge; disjoint ones stay separate.

    One bounding clip over far-apart header regions would span most of a
    sheet, and ``find_tables`` cost grows with every table inside the clip.
    """

    merged: List[fitz.Rect] = []
    for region in regions:
        rect = fitz.Rect(region) & page_rect
        if rect.is_empty:
            continue
        changed = True
        while changed:
            changed = False
            for other in merged:
                if rect.intersects(other):
                    merged.remove(other)
                    rect |= other
                    changed = True
                    break
        merged.append(rect)
    return merged


def _vertical_rules(drawings: List[dict], page_height: float) -> List[tuple]:
    """``(x, top, bottom)`` of vertical line work, sheet-height borders excluded."""

    limit = 0.8 * page_height
    rules: List[tuple] = []
    for path in drawings:
        for item in path["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                if abs(a.x - b.x) < 1.0 and 0 < abs(a.y - b.y) < limit:
                    rules.append((a.x, min(a.y, b.y), max(a.y, b.y)))
            elif item[0] == "re" and 0 < item[1].height < limit:
                rect = item[1]
                rules.append((rect.x0, rect.y0, rect.y1))
                rules.append((rect.x1, rect.y0, rect.y1))
    return rules


def _fit_to_rules(
    region: fitz.Rect, anchor_y: float, rules: Sequence[tuple]
) -> Optional[fitz.Rect]:
    """Shrink ``region`` to the vertical rules crossing its anchor row.

    Rules drawn per row (cell boxes, broken lines) are chained up and down.
    No crossing rule means the table is not ruled: ``None`` (word fallback).
    """

    inside = [rule for rule in rules if region.x0 <= rule[0] <= region.x1]
    crossing = [rule for rule in inside if rule[1] <= anchor_y <= rule[2]]
    if not crossing:
        return None
    top = min(rule[1] for rule in crossing)
    bottom = max(rule[2] for rule in crossing)
    while True:
        below = [r[2] for r in inside if r[1] <= bottom + 2.0 and r[2] > bottom + 0.5]
        if not below:
            break
        bottom = max(below)
    while True:
        above = [r[1] for r in inside if r[2] >= top - 2.0 and r[1] < top - 0.5]
        if not above:
            break
        top = min(above)
    return fitz.Rect(region.x0, max(region.y0, top - 2.0), region.x1, min(region.y1, bottom + 2.0))


def _schedule_regions(page_words: Sequence[tuple]) -> List[tuple]:
    """``(region, anchor_y)`` around schedule header rows and Revit location rows.

    ``find_tables`` costs seconds on a full dense sheet, so it only looks here.
    """

    regions: List[tuple] = []
    for x0, y0, x1, y1, text, *_ in page_words:
        label = str(text).upper()
        anchor_y = (y0 + y1) / 2.0
        if label.startswith("LOCATI") and _is_column_locations_label(x0, y0, page_words):
            # Revit schedules stack level rows above the location row.
            regions.append((fitz.Rect(x0 - 200, y0 - 1400, x0 + 3000, y1 + 300), anchor_y))
        elif label in {"MARK", "TYPE", "PIER"}:
            # Two-line headers stack WIDTH / LENGTH under DIMENSIONS beside MARK.
            line = sorted(
                (other[0], other[2], str(other[4]).upper())
                for other in page_words
                if abs(other[1] - y0) < _HEADER_STACK and other[0] >= x0
            )
            right = x1
            has_partner = False
            for left, end, word in line:
                if left - right > _HEADER_WORD_GAP:
                    break
                right = max(right, end)
                has_partner = has_partner or word in _HEADER_PARTNERS
            if has_partner:
                # Width of the header line; titles sit above, body rows below.
                regions.append(
                    (fitz.Rect(x0 - 60, y0 - 120, right + 60, y0 + 1500), anchor_y)
                )
            elif label == "MARK" and _is_matrix_mark_label(x0, y0, page_words):
                # Row labels on the right: the marks run leftwards along the row.
                regions.append((fitz.Rect(x0 - 2500, y0 - 200, x1 + 200, y0 + 1500), anchor_y))
    return regions


def _is_matrix_mark_label(x0: float, y0: float, page_words: Sequence[tuple]) -> bool:
    """``MARK`` as the row label of a mark x level column schedule: a
    ``BASE PLATE`` row label below it and marks along its row."""

    plate_label = any(
        str(other[4]).upper() == "BASE" and abs(other[0] - x0) < 40.0 and 0 < other[1] - y0 < 1500.0
        for other in page_words
    )
    if not plate_label:
        return False
    marks = sum(
        1
        for other in page_words
        if abs(other[1] - y0) < 12.0
        and other[0] < x0
        and _MATRIX_MARK_RE.fullmatch(str(other[4]).upper())
    )
    return marks >= 2


def _is_column_locations_label(x0: float, y0: float, page_words: Sequence[tuple]) -> bool:
    """``LOCATI…`` after ``COLUMN`` (same line or above; may be split), followed
    on its row by grid locations such as ``A-8`` / ``4.D-4.7``."""

    near = sorted(
        (other[1], other[0], str(other[4]))
        for other in page_words
        if (abs(other[1] - y0) < 4.0 and -60.0 < other[0] - x0 < 0)
        or (0 < y0 - other[1] < 16.0 and abs(other[0] - x0) < 20.0)
    )
    if "COLUMN" not in "".join(text for _, _, text in near).upper():
        return False
    # Revit centers the values in a tall row whose label sits at its top.
    locations = sum(
        1
        for other in page_words
        if 0 < other[0] - x0 < 600.0
        and -12.0 < other[1] - y0 < 45.0
        and _GRID_LOCATION_RE.search(str(other[4]))
    )
    return locations >= 2


def _table_record(table: Any, page_words: Sequence[tuple], page: int) -> Optional[Dict[str, Any]]:
    raw = table.extract()
    rows = [[str(cell or "") for cell in row] for row in raw]
    if len(rows) < 2:
        return None
    bbox = [round(float(value), 2) for value in table.bbox]
    for index, row in enumerate(rows):
        if _LOCATION_LABEL in re.sub(r"\s+", "", row[0]).upper():
            return _transposed_record(table, rows, index, page, bbox)
    # Column schedules whose edge column holds the row labels (MARK ... BASE
    # PLATE, or COLUMN LOCATIONS on the right), read by ``column_schedule``
    # only; ``schedule_grid`` never sees them. A MARK | SIZE table has no
    # BASE PLATE row label in its edge column, so it is not one of these.
    if matrix_key_role([row[0] for row in rows]) or matrix_key_role([row[-1] for row in rows]):
        return {"page": page, "bbox": bbox, "layout": "matrix", "title": "COLUMN SCHEDULE"}
    layout = "rows"
    header_index = _header_index(rows)
    if header_index is None:
        header_index = _location_header_index(rows)
        if header_index is None:
            return None
        # Rows keyed by grid location (location | section | plate type).
        layout = "location_rows"
    header = [header_label(cell) for cell in rows[header_index]]
    # Merged header cells come back as None: each covered column inherits the
    # heading on its left (BASE PLATE SIZE over THICKNESS | WIDTH | LENGTH).
    groups: List[str] = []
    for cell in raw[header_index]:
        groups.append(header_label(cell) if cell is not None else (groups[-1] if groups else ""))
    body_start = header_index + 1
    # Two-line headers (MARK | BASE PLATE SIZE / WIDTH | LENGTH ...).
    while body_start < len(rows) and not rows[body_start][0].strip() and not any(
        re.search(r"\d", cell) for cell in rows[body_start]
    ):
        for column, cell in enumerate(rows[body_start]):
            if cell.strip():
                header[column] = f"{header[column]} {header_label(cell)}".strip()
        body_start += 1
    title = " ".join(
        header_label(cell) for row in rows[:header_index] for cell in row if cell.strip()
    ) or _title_above(bbox, page_words)
    return {
        "page": page,
        "bbox": bbox,
        "layout": layout,
        "title": title,
        "header": header,
        "header_groups": groups,
        "body": [
            {"cells": rows[index], "bbox": _row_bbox(table, index)}
            for index in range(body_start, len(rows))
        ],
    }


def _location_header_index(rows: List[List[str]]) -> Optional[int]:
    """Header row of a table keyed by grid location (``LOCATION MARK | SECTION``)."""

    for index, row in enumerate(rows[:_MAX_HEADER_ROW]):
        labels = [header_label(cell) for cell in row if cell.strip()]
        if (
            len(labels) >= 2
            and "LOCATION" in labels[0]
            and any(re.search(r"SECTION|SIZE|PLATE", label) for label in labels[1:])
        ):
            return index
    return None


def _header_index(rows: List[List[str]]) -> Optional[int]:
    for index, row in enumerate(rows[:_MAX_HEADER_ROW]):
        labels = [header_label(cell) for cell in row if cell.strip()]
        if len(labels) >= 2 and any(
            label in MARK_HEADERS or label in SIZE_HEADERS for label in labels
        ):
            return index
    return None


def _title_above(bbox: List[float], page_words: Sequence[tuple]) -> str:
    """Schedule title printed just above a table whose ruling starts at the header."""

    top = bbox[1]
    line = [
        word
        for word in page_words
        if top - _TITLE_GAP <= word[3] <= top + 2.0
        and word[2] > bbox[0]
        and word[0] < bbox[2]
    ]
    return header_label(" ".join(str(word[4]) for word in sorted(line, key=lambda w: w[0])))


def _row_bbox(table: Any, index: int) -> Optional[List[float]]:
    try:
        return [round(float(value), 2) for value in table.rows[index].bbox]
    except (AttributeError, IndexError, TypeError):
        return None


def _cell_center_x(table: Any, row: int, column: int) -> Optional[float]:
    try:
        cell = table.rows[row].cells[column]
    except (AttributeError, IndexError):
        return None
    if not cell:
        return None
    return (float(cell[0]) + float(cell[2])) / 2.0


def _transposed_record(
    table: Any, rows: List[List[str]], location_row: int, page: int, bbox: List[float]
) -> Dict[str, Any]:
    """Revit column schedule: levels down the side, grid locations along the bottom."""

    locations = []
    for column, text in enumerate(rows[location_row][1:], start=1):
        center = _cell_center_x(table, location_row, column)
        # ``location`` stays whitespace-free so existing mark matching is unchanged.
        # ``raw`` keeps the printed spacing so feet-inch fractions and offsets
        # can be told apart from grid names.
        printed = " ".join(str(text).split())
        location = re.sub(r"\s+", "", printed)
        if location and center is not None:
            locations.append({"location": location, "raw": printed, "x": center})
    labelled_plates = any("BASE PLATE" in header_label(row[0]) for row in rows)
    inferred_rows = set() if labelled_plates else _unlabelled_plate_rows(rows, location_row)
    cells, inferred = [], []
    for row_index, row in enumerate(rows):
        if row_index == location_row:
            continue
        row_label = header_label(row[0])
        for column, text in enumerate(row[1:], start=1):
            center = _cell_center_x(table, row_index, column)
            if not text.strip() or center is None:
                continue
            if row_index in inferred_rows:
                inferred.append(
                    {"text": _strip_plate_label(text), "x": center, "row_label": _PLATE_ROW_LABEL}
                )
            else:
                cells.append({"text": text, "x": center, "row_label": row_label})
    cells.extend(_without_conflicting_plates(inferred, locations))
    return {
        "page": page,
        "bbox": bbox,
        "layout": "transposed",
        "title": "COLUMN SCHEDULE",
        "locations": locations,
        "cells": cells,
    }


def _strip_plate_label(text: str) -> str:
    """``Base Plate 1"x18"x18" Size`` -> ``1"x18"x18"`` (Revit label drawn over a value cell)."""

    text = " ".join(text.split())
    match = _MERGED_PLATE_LABEL_RE.fullmatch(text)
    return match.group(1) if match else text


def _unlabelled_plate_rows(rows: List[List[str]], location_row: int) -> set[int]:
    """Rows of the unlabelled block under Column Locations whose every value is a plate size.

    Only used when no row is labelled BASE PLATE; wrapped values spill onto
    extra unlabelled rows, so row position alone says nothing.
    """

    found: set[int] = set()
    for index in range(location_row + 1, len(rows)):
        row = rows[index]
        if row[0].strip():
            break
        values = [_strip_plate_label(cell) for cell in row[1:] if cell.strip()]
        if values and all(_BASE_PLATE_SIZE_RE.fullmatch(value) for value in values):
            found.add(index)
    return found


def _without_conflicting_plates(
    cells: List[Dict[str, Any]], locations: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Abstain for a location when inferred plate rows disagree on its value."""

    if not locations:
        return []

    def nearest(x: float) -> str:
        return min(locations, key=lambda item: abs(item["x"] - x))["location"]

    values: Dict[str, set] = {}
    for cell in cells:
        values.setdefault(nearest(cell["x"]), set()).add(cell["text"])
    return [cell for cell in cells if len(values[nearest(cell["x"])]) == 1]
