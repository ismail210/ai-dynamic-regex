"""Schedule tables → document-local MARK → SIZE rows.

Ruled tables are read from the PDF's drawn table lines (``schedule_tables``);
word clustering under MARK | SIZE headers is the fallback for tables without
ruling. The table title decides the kind: only steel kinds (column, beam,
lintel, plate) can yield a section. Pier / footing / wall rows are kept so a
mark listed there is never given a guessed steel section. Only a
catalog-valid printed SIZE becomes a section. Plate cells stay plate sidecars.
Incomplete angles are never completed here.
"""

from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Any, Callable, Dict, Iterable, List, Optional

from services.engineering.drawing_intelligence import _DEMO_RE, _EXISTING_RE, _NEW_RE
from services.engineering.member_geometry import _union_bbox as _union_boxes
from services.engineering.column_schedule import _NOT_PLATE_GROUP_RE as NOT_PLATE_GROUP_RE
from services.engineering.column_schedule import _band_key, band_readings, build_column_schedules, parse_dimension
from services.engineering.schedule_tables import (
    MARK_HEADERS,
    SIZE_HEADERS,
    read_display_tables,
    read_rotated_column_schedules,
    read_ruled_tables,
)
from services.token_extractor import extract_engineering_tokens


# Optional hyphen/underscore: C-1, C_1, L-13, P-1, BP-6 — same family as C1 / L13 / P1.
_MARK_RE = re.compile(r"^(?:L|C|P)[-_]?\d+[A-Z]?$", re.IGNORECASE)
_AUX_MARK_RE = re.compile(r"^(?:BP|CL)[-_]?\d+[A-Z]?$", re.IGNORECASE)
_LEGACY_ROW_MARK_RE = re.compile(r"^(?:BP|CL|L|C)\d+[A-Z]?$", re.IGNORECASE)
_MARK_SEP_RE = re.compile(r"^([A-Z]+)[-_](?=\d)", re.IGNORECASE)
# Mark-column cell of a ruled table: any letter prefix, not a fixed alphabet.
# ``F5X3`` / ``F11X6`` footing marks carry an X suffix; steel sections that
# parse from the catalog are rejected separately.
_TABLE_MARK_RE = re.compile(r"^[A-Z]{1,4}[-_]?\d{1,5}[A-Z]{0,2}(?:X\d{1,2})?$")
# Plan words that look like member marks for the cross-check (1–2 digits keeps
# sheet refs such as S-301 and grades such as A325 out).
_PLAN_MARK_RE = re.compile(r"^[A-Z]{1,3}[-_]?\d{1,2}[A-Z]?$")
# Nominal shape fragments (``W16``, ``HP12``) are not member marks.
_SHAPE_PREFIXES = frozenset({"W", "S", "M", "HP", "MC", "WT", "MT", "ST", "L", "PL", "HSS"})
_STANDARD_BODIES = frozenset({"ASTM", "AASHTO", "ACI", "AWS", "AISC", "ANSI"})
NON_STEEL_SCHEDULE_KINDS = frozenset({"pier", "footing", "grade_beam", "wall"})
_PLATE_KINDS = frozenset({"bearing_plate", "base_plate", "plate", "icf_lintel"})
_SIZE_EXCLUDE = ("PLATE", "BAR", "BOLT", "ROD", "REINF", "FOOTING")
_SKIP_HEADERS = frozenset({"REMARKS", "NOTES", "COMMENTS"})
# Ignore schedule-body words left of MARK / right of the rightmost column so
# adjacent tables on the same sheet (pier | column) do not merge into one row.
_BAND_LEFT_SLACK = 48.0
_BAND_RIGHT_SLACK = 120.0
_WITH_PLATE_RE = re.compile(r"\bWITH\s+(BOTTOM|HUNG)\s+PLATE\b", re.IGNORECASE)
_EMPTY_PLATE_RE = re.compile(r"^(?:[-–—]|N/?A)?$", re.IGNORECASE)
# Blank, a dash, and an explicit "no plate" are not a plate. NONE / NO PLATE
# are included here; the narrower pattern above stays for callers that only
# treated a dash or N/A as empty.
_NOT_APPLICABLE_PLATE_RE = re.compile(
    r"^(?:[-–—]|N/?A|NONE|NO\s+PLATE)$", re.IGNORECASE
)
# One imperial plate dimension, printed. Mixed fractions stay text: ``1 1/4``,
# ``1-1/4``, ``3/4``. No float conversion.
_DIM_ATOM = r"(?:\d+[-\s]+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
_ONE_DIM_RE = re.compile(rf"{_DIM_ATOM}\"?", re.IGNORECASE)
# Schedule SIZE cells on dense sheets often merge neighboring note text.
# Prefer the printed plate / angle dimension embedded in that blob.
# Separators are x / X / ×. Roles are not assigned: the third number is not thickness.
_PLATE_DIM_RE = re.compile(
    rf"({_DIM_ATOM})\s*\"?\s*[xX×]\s*"
    rf"({_DIM_ATOM})\s*\"?\s*[xX×]\s*"
    rf"({_DIM_ATOM})\s*\"?"
)
_BP_MARK_RE = re.compile(r"^BP[-_]?\d+[A-Z]?$", re.IGNORECASE)
_PLATE_CONTEXT_KINDS = frozenset({"base_plate", "bearing_plate", "plate"})
_KNOWN_SCHEDULE_LABELS = (
    "BENT PLATE SCHEDULE",
    "BEARING PLATE SCHEDULE",
    "BASE PLATE SCHEDULE",
    "PLATE SCHEDULE",
)
_ANGLE_THEN_DIM_RE = re.compile(
    r"\b(?:LOOSE|CONTINUOUS)?\s*ANGLES?\s+"
    r"(\d+\s*\"?\s*[xX×]\s*\d+\s*\"?\s*[xX×]\s*[\d\s/]+\"?)",
    re.IGNORECASE,
)
_ROW_GAP = 36.0
_HEADER_LOOKBACK = 80.0

CatalogFn = Callable[[str], bool]


def normalize_schedule_mark(text: str) -> str:
    """Canonical mark key so ``C-1`` / ``C_1`` / ``C1`` share one map entry."""

    compact = re.sub(r"\s+", "", str(text or "")).upper()
    return _MARK_SEP_RE.sub(r"\1", compact)


def is_bare_schedule_mark(text: str) -> bool:
    """True for lintel/column/pier marks such as ``L1``, ``C-1``, ``P-1`` — not ``L4X4``."""

    return bool(_MARK_RE.fullmatch(_compact_mark(text)))


def is_pier_schedule_mark(text: str) -> bool:
    """True for pier schedule marks such as ``P1``, ``P-1``, ``P3A``."""

    compact = re.sub(r"\s+", "", str(text or "")).upper()
    return bool(re.fullmatch(r"P[-_]?\d+[A-Z]?", compact))


def is_auxiliary_schedule_mark(text: str) -> bool:
    """True for bearing-plate / ICF-lintel marks such as ``BP1``, ``BP-1``, ``CL2``."""

    compact = re.sub(r"\s+", "", str(text or "")).upper()
    return bool(_AUX_MARK_RE.fullmatch(compact))


def is_schedule_table_mark(text: str) -> bool:
    """Any MARK-column token the schedule grid may keep as a row key."""

    return is_bare_schedule_mark(text) or is_auxiliary_schedule_mark(text)


def member_plate_roles(text: str) -> List[str]:
    """``WITH BOTTOM/HUNG PLATE`` on a size cell. Not a second rolled section."""

    roles: List[str] = []
    for match in _WITH_PLATE_RE.finditer(str(text or "")):
        kind = match.group(1).upper()
        role = "bottom_plate" if kind == "BOTTOM" else "hung_plate"
        if role not in roles:
            roles.append(role)
    return roles


def _heading_dimension_role(label: str) -> Optional[str]:
    """Length / width / thickness from a schedule header. Combined plate labels are not roles."""

    text = " ".join(str(label or "").upper().split())
    if text in {
        "BASE PLATE",
        "BASE PLATE SIZE",
        "BEARING PLATE",
        "BEARING PLATE SIZE",
        "PLATE",
        "PLATE SIZE",
    }:
        return None
    if re.search(r"(?:^|\s)(?:THK|THICKNESS)$", text):
        return "thickness"
    if re.search(r"(?:^|\s)WIDTH$", text):
        return "width"
    if re.search(r"(?:^|\s)LENGTH$", text):
        return "length"
    return None


def _plate_not_applicable(text: str) -> bool:
    return bool(_NOT_APPLICABLE_PLATE_RE.fullmatch(str(text or "").strip()))


def _blank_plate(raw: str, notes: Optional[str] = None) -> Dict[str, Any]:
    return {
        "raw": raw,
        "dimensions": {"length": None, "width": None, "thickness": None},
        "ordered_dimensions": [],
        "dimension_source": None,
        "uncertain": False,
        "notes": notes,
        "reference": None,
    }


def _token_with_quote(raw: str, match: re.Match, group: int) -> str:
    token = match.group(group).strip()
    cursor = match.end(group)
    while cursor < len(raw) and raw[cursor] == " ":
        cursor += 1
    if cursor < len(raw) and raw[cursor] in {'"', "″"}:
        return token + raw[cursor]
    return token


def _as_dimension(text: str) -> Optional[str]:
    value = " ".join(str(text or "").split())
    if value and _ONE_DIM_RE.fullmatch(value):
        return value
    return None


def _headed_plate_dimension(printed: str) -> Optional[Dict[str, Any]]:
    """A plate-schedule cell under a THICKNESS / WIDTH / LENGTH heading:
    recognised as printed (``1 1/4"``, ``3/4``, ``1'-6"``), with inches only
    where the printed form converts. The printed text is the value."""

    value = _as_dimension(printed)
    length = parse_dimension(printed)
    if value is None and length is None:
        return None
    return {"printed": printed, "inches": length["inches"] if length else None}


def _interpret_plate(
    text: str,
    *,
    headed: Optional[List[tuple]] = None,
    notes: Optional[str] = None,
    plate_schedule: bool = False,
) -> tuple:
    """``(parsed_plate, plate_status)``. Does not assign thickness by position.

    ``plate_schedule``: the headings belong to a plate schedule. Feet-inch
    cells are then dimensions too (with ``dimension_inches`` beside the
    printed text), and a heading printed twice leaves the plate unresolved
    rather than letting the later cell replace the earlier one. Other
    schedules keep their footing / pier / wall sizes as they were.
    """

    raw = " ".join(str(text or "").split())
    kept_notes = " ".join(str(notes).split()) if notes else None
    if headed:
        dims = {"length": None, "width": None, "thickness": None}
        inches: Dict[str, Optional[float]] = dict(dims)
        ordered: List[str] = []
        failed = False
        for role, cell in headed:
            printed = " ".join(str(cell or "").split())
            if not printed:
                continue
            ordered.append(printed)
            if plate_schedule:
                found = _headed_plate_dimension(printed)
                value = found and found["printed"]
                if role in dims and dims[role] is not None:
                    value = None
            else:
                value = _as_dimension(printed)
            if value is None or role not in dims:
                failed = True
                continue
            dims[role] = value
            if plate_schedule:
                inches[role] = found["inches"]
        parsed = {
            "raw": raw or " ".join(ordered),
            "dimensions": dims,
            "ordered_dimensions": ordered,
            "dimension_source": "headings",
            "uncertain": not all(dims.values()),
            "notes": kept_notes,
            "reference": None,
        }
        if plate_schedule:
            parsed["dimension_inches"] = inches
        if failed:
            parsed["uncertain"] = True
            return parsed, "unresolved"
        if not any(dims.values()):
            return _blank_plate(raw, kept_notes), "not_applicable"
        return parsed, "present"

    if not raw or _plate_not_applicable(raw):
        return _blank_plate(raw, kept_notes), "not_applicable"
    compact = re.sub(r"\s+", "", raw).upper()
    if _BP_MARK_RE.fullmatch(compact):
        parsed = _blank_plate(raw, kept_notes)
        parsed["reference"] = compact
        parsed["uncertain"] = True
        return parsed, "unresolved"
    matches = list(_PLATE_DIM_RE.finditer(raw))
    if len(matches) != 1:
        parsed = _blank_plate(raw, kept_notes)
        parsed["uncertain"] = True
        return parsed, "unresolved"
    match = matches[0]
    ordered = [_token_with_quote(raw, match, index) for index in (1, 2, 3)]
    remainder = " ".join(f"{raw[:match.start()]} {raw[match.end():]}".split())
    note_parts = [part for part in (kept_notes, remainder) if part]
    return {
        "raw": raw,
        "dimensions": {"length": None, "width": None, "thickness": None},
        "ordered_dimensions": ordered,
        "dimension_source": "combined",
        "uncertain": True,
        "notes": " ".join(note_parts) or None,
        "reference": None,
    }, "present"


def _apply_plate_metadata(
    row: Dict[str, Any], *, headed: Optional[List[tuple]] = None, plate_schedule: bool = False
) -> None:
    """Add plate status beside ``plate_text``. The printed cell is not rewritten."""

    notes = row.get("plate_notes")
    parsed, status = _interpret_plate(
        row.get("plate_text") or "", headed=headed, notes=notes, plate_schedule=plate_schedule
    )
    row["parsed_plate"] = parsed
    row["plate_status"] = status
    if status == "not_applicable":
        row["plate_role"] = None


def plate_count_per_member(row: Dict[str, Any]) -> int:
    """Sidecar plate count hint from schedule notes — not a physical takeoff yet.

    Struct note: bearing plate size applies to each end unless noted otherwise.
    Empty / dash plate cells (e.g. L4 frame-to-column) count as zero.
    """

    plate_text = str(row.get("plate_text") or "").strip()
    if (
        not plate_text
        or _plate_not_applicable(plate_text)
        or row.get("plate_status") in {"not_applicable", "unresolved", "ambiguous"}
    ):
        return 0
    if row.get("member_plate_roles") or row.get("plate_role") == "bearing_plate":
        return 2
    if row.get("plate_role") == "base_plate":
        return 1
    return 1


def section_from_size_text(text: str, catalog_fn: CatalogFn) -> Optional[str]:
    """First catalog-valid steel token in a SIZE cell, ignoring plate phrases."""

    cleaned = _WITH_PLATE_RE.sub(" ", str(text or ""))
    for token in extract_engineering_tokens(cleaned):
        if catalog_fn is _catalog_accepts:
            spelling = _catalog_spelling(token)
            if spelling:
                return spelling
        elif catalog_fn(token):
            return token
    return None


def schedule_mark_map(
    grids: Iterable[Dict[str, Any]], *, drop_conflicts: bool = False
) -> Dict[str, str]:
    """Mark → catalog section. Non-steel SIZE cells (precast, notes) are omitted.

    Legacy: a duplicated mark keeps its first row. ``drop_conflicts`` makes a
    mark with two different sections resolve to nothing, independent of row
    order (SCHEDULE_MARK_CONFLICT_GUARD_ENABLED).
    """

    sections: Dict[str, List[str]] = {}
    for grid in grids:
        for row in _mark_rows(grid):
            if row.get("catalog_valid") and row.get("section") and row.get("mark"):
                sections.setdefault(normalize_schedule_mark(row["mark"]), []).append(str(row["section"]))
    return {
        mark: found[0]
        for mark, found in sections.items()
        if not (drop_conflicts and len(set(found)) > 1)
    }


def build_schedule_grids(
    words: Iterable[Dict[str, Any]],
    *,
    catalog_fn: Optional[CatalogFn] = None,
) -> List[Dict[str, Any]]:
    """Group schedule words into rows. ``catalog_fn`` defaults to AISC lookup."""

    accept = catalog_fn or _catalog_accepts
    by_page: Dict[Any, List[dict]] = {}
    for word in words:
        page = word.get("page_number", word.get("page", 0))
        by_page.setdefault(page, []).append(word)
    grids: List[Dict[str, Any]] = []
    for page, page_words in by_page.items():
        if not _page_has_mark_size_headers(page_words):
            continue
        grids.extend(_grids_on_page(page_words, page, accept))
    return attach_resolved_plates(grids)


def _page_has_mark_size_headers(words: List[dict]) -> bool:
    """Cheap pre-filter before clustering — framing sheets have no MARK|SIZE header."""

    seen_mark = False
    seen_size = False
    for word in words:
        label = str(word.get("text") or "").upper()
        # Pier schedules title the mark column "PIER" / "PIER TYPE", not "MARK".
        if label in {"MARK", "PIER"}:
            seen_mark = True
        elif label == "SIZE":
            seen_size = True
        if seen_mark and seen_size:
            return True
    return False


def build_document_schedule_grids(
    words: Iterable[Dict[str, Any]],
    *,
    pdf_path: Optional[str] = None,
    pages: Optional[Iterable[int]] = None,
    catalog_fn: Optional[CatalogFn] = None,
    ruled_records: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Ruled-table grids first; word-cluster rows only for marks they missed.

    ``ruled_records`` passes tables already read from ``pdf_path``.
    """

    accept = catalog_fn or _catalog_accepts
    page_filter = set(pages) if pages is not None else None
    word_list = [
        word
        for word in words
        if page_filter is None
        or int(word.get("page_number", word.get("page", 0)) or 0) in page_filter
    ]
    fallback = build_schedule_grids(word_list, catalog_fn=accept)
    if not pdf_path:
        return fallback
    if ruled_records is None:
        ruled_records = read_ruled_tables(pdf_path, word_list, pages=page_filter)
    ruled = _ruled_grids(ruled_records, accept)
    # BP/CL resolution consumes the legacy row wording, including angle/type
    # order and N/A context. A word-cluster row for the same page and mark
    # stays authoritative. A ruled auxiliary row remains when clustering
    # missed that mark.
    fallback_auxiliary = {
        (grid["page"], normalize_schedule_mark(row["mark"]))
        for grid in fallback
        for row in _mark_rows(grid)
        if is_auxiliary_schedule_mark(row["mark"])
    }
    ruled = [
        {**grid, "rows": [
            row for row in grid["rows"]
            if not is_auxiliary_schedule_mark(row["mark"])
            or (grid["page"], normalize_schedule_mark(row["mark"])) not in fallback_auxiliary
        ]}
        for grid in ruled
    ]
    ruled = [grid for grid in ruled if grid["rows"]]
    covered = {
        (grid["page"], normalize_schedule_mark(row["mark"]))
        for grid in ruled
        for row in _mark_rows(grid)
    }
    merged = list(ruled)
    for grid in fallback:
        rows = [
            row
            for row in grid["rows"]
            if (grid["page"], normalize_schedule_mark(row["mark"])) not in covered
        ]
        if rows:
            merged.append({**grid, "rows": rows})
    return attach_resolved_plates(merged)


def attach_schedule_grid(
    document: Dict[str, Any], *, pdf_path: Optional[str] = None
) -> Dict[str, Any]:
    """Store ``schedule_grid``, ``schedule_mark_map`` and the plan cross-check."""

    from config import settings

    if not settings.schedule_grid_enabled:
        return document
    words = document.get("words") or []
    pdf_path = pdf_path if settings.schedule_ruled_tables_enabled else None
    records = read_ruled_tables(pdf_path, words) if pdf_path else []
    grids = build_document_schedule_grids(words, pdf_path=pdf_path, ruled_records=records)
    document["schedule_grid"] = grids
    # Display-only: SLAB/DECK, MAT FOUNDATION and similar tables for the
    # Drawing Summary. Never part of ``schedule_grid`` or the mark map.
    document["display_schedule_grid"] = _display_grids(grids, records, pdf_path, words) if pdf_path else []
    # Display/evidence only: never read by prediction or quantities.
    rotated = read_rotated_column_schedules(pdf_path, words) if pdf_path else []
    document["column_schedules"] = build_column_schedules(records + rotated, grids)
    attach_level_bands(grids, document["column_schedules"])
    if pdf_path:
        from services.engineering.level_evidence import masked_spot_labels

        document["masked_text"] = masked_spot_labels(document, pdf_path)
    document["schedule_mark_map"] = schedule_mark_map(
        grids, drop_conflicts=settings.schedule_mark_conflict_guard_enabled
    )
    if settings.schedule_evidence_shadow_enabled:
        document["schedule_evidence_shadow"] = build_schedule_evidence(
            document.get("words") or [],
            discovery="widened" if settings.schedule_evidence_shadow_widened else "current",
        )
    document["schedule_crosscheck"] = schedule_mark_crosscheck(document)
    return document


def _display_grids(grids: list[dict[str, Any]], records: list[dict[str, Any]], pdf_path: str,
                   words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Printed schedules the production grid leaves out, for the Drawing
    Summary only: ruled tables with printed rows none of which reads as a
    mark (OSSE FOOTING SCHEDULE ``F3.0``, CONCRETE SCHEDULE ``RC1 - 24" x 24"``)
    and tables only the display reader looks for (SLAB/DECK, MAT FOUNDATION)."""

    shown = {(g.get("page"), g.get("title")) for g in grids}
    out = []
    for record in records:
        if record.get("layout") != "rows" or (record["page"], record.get("title")) in shown:
            continue
        grid = _ruled_rows_grid(record, _catalog_accepts)
        if grid and not grid["rows"] and grid.get("unread_rows"):
            out.append(grid)
    for record in read_display_tables(pdf_path, words, records):
        grid = _ruled_rows_grid(record, _catalog_accepts)
        if grid and (grid["rows"] or grid.get("unread_rows")):
            out.append(grid)
    # A table of catalog steel sections is a member schedule: not shown as a
    # supporting schedule the production grid does not read.
    return [{**grid, "display_only": True} for grid in out if not any(r.get("section") for r in grid["rows"])]


def schedule_kind_from_title(title: str) -> str:
    """Schedule kind from its printed title. Non-steel kinds are checked first."""

    text = str(title or "").upper()
    if re.search(r"\bPIERS?\b", text):
        return "pier"
    if re.search(r"FOOTING|\bPILE|FOUNDATION", text):
        return "footing"
    if re.search(r"\b(?:GRADE|TIE)\s+BEAM", text):
        return "grade_beam"
    if re.search(r"\bWALL|\bSLAB", text):
        return "wall"
    if "BEARING PLATE" in text:
        return "bearing_plate"
    if "BASE PLATE" in text:
        return "base_plate"
    if "ICF" in text or "CONCRETE CORE" in text:
        return "icf_lintel"
    if "LINTEL" in text:
        return "lintel"
    if "COLUMN" in text:
        return "column"
    if re.search(r"\bBEAM|GIRDER|JOIST", text):
        return "beam"
    if "BRAC" in text:
        return "brace"
    # Bent-plate schedules stay generic plates. They are not base or bearing plates.
    if "BENT PLATE" in text or re.search(r"\bBENT\s+PL\b", text):
        return "plate"
    if "PLATE" in text:
        return "plate"
    return "schedule"


def _mark_rows(grid: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Rows keyed by a type mark. Revit grid-location rows are instances."""

    return [
        row
        for row in grid.get("rows") or []
        if row.get("mark_role") != "grid_location"
    ]


def _ruled_grids(
    records: Iterable[Dict[str, Any]], catalog_fn: CatalogFn
) -> List[Dict[str, Any]]:
    grids: List[Dict[str, Any]] = []
    for record in records:
        if record["layout"] == "transposed":
            grid = _transposed_grid(record, catalog_fn)
        elif record["layout"] == "rows":
            grid = _ruled_rows_grid(record, catalog_fn)
        else:
            # Mark-keyed matrices and location-keyed rows are column-schedule
            # evidence only: a location such as C-6 must never become mark C6.
            continue
        if grid and grid["rows"]:
            grids.append(grid)
    return attach_resolved_plates(grids)


def _is_table_mark(text: str, catalog_fn: CatalogFn) -> bool:
    return bool(_TABLE_MARK_RE.fullmatch(text)) and not section_from_size_text(
        text, catalog_fn
    )


def _ruled_rows_grid(
    record: Dict[str, Any], catalog_fn: CatalogFn
) -> Optional[Dict[str, Any]]:
    header: List[str] = record["header"]
    body = record["body"]
    width = len(header)
    mark_col = next(
        (
            column
            for column, label in enumerate(header)
            if label in MARK_HEADERS or label.endswith(" MARK")
        ),
        None,
    )
    if mark_col is None:
        # Unlabeled first column: a mark column only if its cells look like marks.
        first = [re.sub(r"\s+", "", row["cells"][0]).upper() for row in body]
        filled = [cell for cell in first if cell]
        if not filled or sum(_is_table_mark(c, catalog_fn) for c in filled) * 2 < len(filled):
            return None
        mark_col = 0
    kind = schedule_kind_from_title(record["title"])
    if kind == "schedule":
        kind = schedule_kind_from_title(header[mark_col])
    # In a plate schedule the headings say what each cell is: a column under
    # another part's group (PLATE WASHER, ANCHOR ROD, COLUMN WELD) is that
    # part's, never a plate dimension (same rule as the Drawing Summary plate
    # table); ``SIZE WIDTH`` under a SIZE group is the width, not a size cell.
    plate_schedule = kind in _PLATE_CONTEXT_KINDS and not _is_bent_plate_schedule(record)
    groups = record.get("header_groups") or []
    paths = record.get("header_paths") or []
    trailing = record.get("trailing_column")

    def group_of(column: int) -> str:
        return groups[column] if column < len(groups) else ""

    def display_cells(cells: list[str], index: int) -> list[dict[str, Any]]:
        # Display only: each printed cell under its full printed heading
        # (REINFORCEMENT > BOTTOM > SHORT WAY), so equal values in two columns
        # stay two values; a column outside the ruling read (REMARKS) last.
        out = [
            {"heading": header[column], "group": group_of(column) or None,
             "path": (paths[column] if column < len(paths) else None) or [header[column]],
             "text": " ".join(cells[column].split())}
            for column in range(width) if column != mark_col
        ]
        if trailing:
            texts = trailing["cells"]
            boxes = trailing.get("bboxes") or []
            out.append({"heading": trailing["heading"], "group": None, "path": [trailing["heading"]],
                        "text": texts[index] if index < len(texts) else "",
                        **({"bbox": boxes[index]} if index < len(boxes) and boxes[index] else {})})
        return out

    def other_part(column: int) -> bool:
        return plate_schedule and bool(NOT_PLATE_GROUP_RE.search(f"{group_of(column)} {header[column]}"))

    def dimension_heading(column: int) -> bool:
        return plate_schedule and _heading_dimension_role(header[column]) is not None

    size_col = next(
        (
            column
            for column, label in enumerate(header)
            if column != mark_col and label in SIZE_HEADERS and not dimension_heading(column)
        ),
        None,
    )
    if size_col is None:
        size_col = next(
            (
                column
                for column, label in enumerate(header)
                if column != mark_col
                and re.search(r"SIZE|SECTION|DIMENSION", label)
                and not any(word in label for word in _SIZE_EXCLUDE)
                and not dimension_heading(column)
            ),
            None,
        )
    plate_cols, dim_cols, note_cols, diameter_cols, other_cols = [], [], [], [], []
    accessory_cols: List[int] = []
    for column, label in enumerate(header):
        if column in (mark_col, size_col):
            continue
        if other_part(column):
            accessory_cols.append(column)
            continue
        role = _heading_dimension_role(label)
        if role:
            dim_cols.append((column, role))
        elif "PLATE" in label:
            plate_cols.append(column)
        elif label.startswith("DIA"):
            diameter_cols.append(column)
        elif label in _SKIP_HEADERS or "ANCHOR" in label or "BOLT" in label:
            if label in _SKIP_HEADERS:
                note_cols.append(column)
            continue
        else:
            other_cols.append(column)
    plate_labels = " ".join(header[column] for column in plate_cols)
    if kind == "bearing_plate" or "BEARING" in plate_labels:
        plate_role = "bearing_plate"
    elif kind == "base_plate" or "BASE" in plate_labels:
        plate_role = "base_plate"
    else:
        plate_role = "plate"

    rows: List[Dict[str, Any]] = []
    unread: list[dict[str, Any]] = []
    for index, body_row in enumerate(body):
        cells = (body_row["cells"] + [""] * width)[:width]
        mark = re.sub(r"\s+", "", cells[mark_col]).upper()
        if not mark or not _is_table_mark(mark, catalog_fn):
            if mark:
                # Printed but not taken as a schedule mark (16RB32): kept for
                # the summary's coverage, never resolved.
                unread.append({"printed_mark": " ".join(cells[mark_col].split()),
                               "cells": display_cells(cells, index), "bbox": body_row.get("bbox")})
            continue

        def joined(columns: Iterable[Optional[int]]) -> str:
            return " ".join(
                " ".join(cells[column].split())
                for column in columns
                if column is not None and cells[column].strip()
            )

        size_text = joined([size_col, *other_cols])
        diameter_text = joined(diameter_cols)
        if not size_text and diameter_text:
            size_text = diameter_text
        elif diameter_text:
            size_text = f"{size_text} DIA {diameter_text}"
        plate_text = joined(plate_cols)
        if not plate_text and dim_cols:
            plate_text = joined(column for column, _role in dim_cols)
        plate_mark = kind in _PLATE_KINDS or is_auxiliary_schedule_mark(mark)
        if not plate_text and plate_mark:
            plate_text = size_text
        section = None
        if kind not in NON_STEEL_SCHEDULE_KINDS and not plate_mark:
            section = section_from_size_text(size_text, catalog_fn)
        notes = joined(note_cols)
        row = {
            "mark": mark,
            "size_text": size_text,
            "section": section,
            "catalog_valid": bool(section),
            "plate_text": plate_text,
            "plate_role": plate_role if plate_text else None,
            "member_plate_roles": member_plate_roles(" ".join(cells)),
            "bbox": body_row.get("bbox"),
        }
        if notes:
            row["plate_notes"] = notes
        accessories = [
            {"part": group_of(column) or header[column], "heading": header[column],
             "role": _heading_dimension_role(header[column]), "text": " ".join(cells[column].split())}
            for column in accessory_cols if cells[column].strip()
        ]
        if accessories:
            # Printed as given; kept apart from the plate's own dimensions.
            row["plate_accessories"] = accessories
        if kind in NON_STEEL_SCHEDULE_KINDS or not (section or plate_mark):
            row["cells"] = display_cells(cells, index)   # ``size_text`` is unchanged
        _apply_plate_metadata(
            row,
            headed=[(role, cells[column]) for column, role in dim_cols] or None,
            plate_schedule=plate_schedule,
        )
        rows.append(row)
    return {
        "page": record["page"],
        "kind": kind,
        "rows": rows,
        "source": "ruled_table",
        "layout": "rows",
        "title": record["title"],
        "bbox": record["bbox"],
        # Printed rows with a mark cell, read or not (coverage).
        "printed_rows": len(rows) + len(unread),
        **({"unread_rows": unread} if unread else {}),
    }


# A dash in a location cell is not always a grid intersection.
# ``A-6`` splits into grids. ``- 2'-0"`` is a signed offset. ``41'-9 5/8"``
# is a feet-inch measurement and is never a pair of grids. A prime on a
# letter (``A'``, ``B'``) is part of the grid name. A prime on a number
# (``6'``) is kept as printed and marked uncertain — that shape is also a
# feet mark, and this parser does not invent a correction.
_FOOT_MARK = r"['′’]"
_INCH_MARK = r"[\"″]"
_INCH_BODY = r"\d{1,2}(?:\s+\d+/\d+)?"
_LOCATION_DIMENSION_RE = re.compile(
    rf"^(?:"
    rf"\d{{1,4}}\s*{_FOOT_MARK}\s*-\s*{_INCH_BODY}\s*{_INCH_MARK}?"
    rf"|\d{{1,4}}\s*{_FOOT_MARK}\s*{_INCH_BODY}\s*{_INCH_MARK}"
    rf"|\d+(?:\s+\d+/\d+)?\s*{_INCH_MARK}"
    rf")$"
)
_GRID_ATOM = (
    rf"(?:[A-Z][A-Z0-9]*(?:\.[A-Z0-9]+)*|\d+(?:\.[A-Z0-9]+)*)(?:{_FOOT_MARK}+)?"
)
_ONE_GRID_RE = re.compile(rf"^{_GRID_ATOM}$", re.IGNORECASE)
_TWO_GRID_RE = re.compile(
    rf"^(?P<a>{_GRID_ATOM})\s*-\s*(?P<b>{_GRID_ATOM})$", re.IGNORECASE
)
_SIGNED_OFFSET_RE = re.compile(
    rf"\s*(?P<signed>[+-]\s*(?:"
    rf"\d{{1,4}}\s*{_FOOT_MARK}\s*-\s*{_INCH_BODY}\s*{_INCH_MARK}?"
    rf"|\d+(?:\s+\d+/\d+)?\s*{_INCH_MARK}"
    rf"))\s*$",
    re.IGNORECASE,
)
_NUMERIC_PRIME_RE = re.compile(rf"^\d+{_FOOT_MARK}+$")
_OFFSET_LABELS = frozenset({"OFFSET", "OFFSETS", "GRID OFFSET"})


def parse_column_location(text: str) -> Dict[str, Any]:
    """Structure one column-location cell without changing the printed text.

    List separators are comma and semicolon only. Repeated copies of the same
    grid inside that one cell become one occurrence. Nothing here is a schedule
    mark, a plate, or a quantity.
    """

    raw = " ".join(str(text or "").split())
    if not raw:
        return {"raw": "", "kind": "unparsed", "occurrences": [], "uncertain": True}
    if _LOCATION_DIMENSION_RE.fullmatch(raw):
        return {"raw": raw, "kind": "dimension", "occurrences": [], "uncertain": False}
    pieces = (
        [part.strip() for part in re.split(r"\s*[,;]\s*", raw) if part.strip()]
        if re.search(r"[,;]", raw)
        else [raw]
    )
    occurrences = [_dedupe_location_piece(piece) for piece in pieces]
    occurrences = _dedupe_location_occurrences(occurrences)
    uncertain = any(item["uncertain"] for item in occurrences) or not occurrences
    kind = "grid" if any(item["grids"] for item in occurrences) else "unparsed"
    return {"raw": raw, "kind": kind, "occurrences": occurrences, "uncertain": uncertain}


def _dedupe_location_piece(piece: str) -> Dict[str, Any]:
    """``A-6 A-6`` printed twice in one cell is one logical location."""

    parts = piece.split()
    if len(parts) >= 2 and len(set(parts)) == 1 and _grids_of(parts[0])[1]:
        parsed = _parse_location_piece(parts[0])
        parsed["raw"] = piece
        return parsed
    return _parse_location_piece(piece)


def _parse_location_piece(piece: str) -> Dict[str, Any]:
    if _LOCATION_DIMENSION_RE.fullmatch(piece):
        return {"raw": piece, "grids": [], "offset": None, "uncertain": True}
    offset = None
    body = piece
    match = _SIGNED_OFFSET_RE.search(piece)
    if match:
        offset = match.group("signed").strip()
        body = piece[: match.start()].strip()
    grids, ok = _grids_of(body)
    uncertain = (not ok) or any(_NUMERIC_PRIME_RE.fullmatch(grid) for grid in grids)
    return {
        "raw": piece,
        "grids": grids if ok else [],
        "offset": offset,
        "uncertain": uncertain,
    }


def _grids_of(body: str) -> tuple:
    if not body or _LOCATION_DIMENSION_RE.fullmatch(body):
        return [], False
    one = _ONE_GRID_RE.fullmatch(body)
    if one:
        return [one.group(0)], True
    two = _TWO_GRID_RE.fullmatch(body)
    if two:
        return [two.group("a"), two.group("b")], True
    return [], False


def _dedupe_location_occurrences(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    seen: set = set()
    for item in items:
        if not item["grids"]:
            kept.append(item)
            continue
        key = (tuple(item["grids"]), item["offset"], item["uncertain"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return kept


def _apply_location_offset(
    parsed: Dict[str, Any], offset_text: str
) -> Dict[str, Any]:
    """Attach one neighboring OFFSET cell when this entry has a single grid."""

    occurrences = parsed.get("occurrences") or []
    if (
        not offset_text
        or len(occurrences) != 1
        or occurrences[0].get("offset")
    ):
        return parsed
    return {
        **parsed,
        "occurrences": [{**occurrences[0], "offset": offset_text}],
    }


# Leading datum on a transposed column-schedule row label, as printed:
# ``14' - 6" GROUND LEVEL``. A datum later in the label is not a prefix.
_TRANSPOSED_LEVEL_DATUM_RE = re.compile(r"\d+' - \d+\"")


def _split_transposed_level_label(level: str) -> Dict[str, Any]:
    """``level_band``: the printed parts of a transposed ``level`` label.

    The printed elevation and name are *not* a level: in a graphical schedule
    the label between two drawn lines is the upper line's elevation and the
    lower line's name. ``pairing`` stays ``unresolved`` until
    :func:`attach_level_bands` reads the drawn lines; ``level`` is set only
    when one line prints both parts.
    """

    text = str(level or "")
    found = list(_TRANSPOSED_LEVEL_DATUM_RE.finditer(text))
    band = {"raw": text, "printed_elevation": None, "printed_name": None, "prefix_status": "absent",
            "pairing": "unresolved", "level": None, "elevation_of": None, "name_of": None}
    if not text.strip() or (found and (found[0].start() != 0 or len(found) != 1)):
        band["prefix_status"] = "unresolved"
    elif not found:
        band["printed_name"] = text
    else:
        band.update(printed_elevation=found[0].group(0), printed_name=text[found[0].end():].lstrip() or None,
                    prefix_status="present")
    return {"level_band": band}


def attach_level_bands(grids: List[Dict[str, Any]], column_schedules: Dict[str, Any]) -> None:
    """Resolve each row's ``level_band`` pairing from the drawn level lines of
    the same page's column schedule (metadata only; rows are not selected,
    added or removed)."""

    readings = band_readings(column_schedules)
    for grid in grids:
        for row in grid.get("rows") or []:
            band = row.get("level_band")
            reading = band and readings.get((grid.get("page"), _band_key(band["raw"])))
            if not reading:
                continue
            band["pairing"] = reading["pairing"]
            if reading["pairing"] == "ambiguous":
                band["candidates"] = reading["candidates"]
            else:
                band.update(level=reading["level"], elevation_of=reading["elevation_of"], name_of=reading["name_of"])


def _transposed_grid(
    record: Dict[str, Any], catalog_fn: CatalogFn
) -> Optional[Dict[str, Any]]:
    """One row per source cell that names a section at a grid location.

    Two cells with the same location and section stay two rows when both
    were printed. ``mark`` remains the compacted location string and
    ``mark_role`` remains ``grid_location``, so it is not a schedule mark.
    ``parsed_location`` is metadata beside that string.
    """

    locations = sorted(record["locations"], key=lambda item: item["x"])
    if not locations:
        return None
    gaps = [b["x"] - a["x"] for a, b in zip(locations, locations[1:]) if b["x"] > a["x"]]
    tolerance = max(0.6 * median(gaps), 12.0) if gaps else 40.0

    def nearest(x: float) -> Optional[Dict[str, Any]]:
        best = min(locations, key=lambda item: abs(item["x"] - x))
        return best if abs(best["x"] - x) <= tolerance else None

    plates: Dict[str, str] = {}
    offsets: Dict[str, str] = {}
    rows: List[Dict[str, Any]] = []
    for cell in record["cells"]:
        found = nearest(cell["x"])
        if found is None:
            continue
        location = str(found["location"])
        text = " ".join(cell["text"].split())
        label = " ".join(str(cell.get("row_label") or "").split()).upper()
        if "BASE PLATE" in label:
            plates.setdefault(location, text)
            continue
        if label in _OFFSET_LABELS or label.startswith("OFFSET "):
            if text:
                offsets.setdefault(location, text)
            continue
        section = section_from_size_text(text, catalog_fn)
        if not section:
            continue
        level = cell["row_label"]
        rows.append(
            {
                "mark": location,
                "mark_role": "grid_location",
                "size_text": text,
                "section": section,
                "catalog_valid": True,
                "level": level,
                **_split_transposed_level_label(level),
                "plate_text": "",
                "plate_role": None,
                "member_plate_roles": [],
                "bbox": None,
                "parsed_location": parse_column_location(
                    str(found.get("raw") or location)
                ),
            }
        )
    for row in rows:
        plate = plates.get(row["mark"], "")
        if plate:
            row["plate_text"] = plate
            row["plate_role"] = "base_plate"
        extra = offsets.get(row["mark"])
        if extra:
            row["parsed_location"] = _apply_location_offset(row["parsed_location"], extra)
        _apply_plate_metadata(row)
    return {
        "page": record["page"],
        "kind": "column",
        "rows": rows,
        "source": "ruled_table",
        "layout": "transposed",
        "title": record["title"],
        "bbox": record["bbox"],
    }


def schedule_mark_crosscheck(document: Dict[str, Any]) -> Dict[str, Any]:
    """Compare schedule marks with mark-shaped words outside the tables.

    Diagnostic only. A plan mark whose prefix is scheduled but whose mark is
    not points to a missed row or table; a scheduled mark never used outside
    its table is likely noise; a repeated unscheduled prefix (``BF-1..4``)
    points to a schedule sheet that was not read.
    """

    grids = document.get("schedule_grid") or []
    boxes: Dict[int, List[List[float]]] = {}
    scheduled: set[str] = set()
    for grid in grids:
        page = int(grid.get("page") or 0)
        for box in [grid.get("bbox")] + [row.get("bbox") for row in grid.get("rows") or []]:
            if box:
                boxes.setdefault(page, []).append(box)
        scheduled.update(normalize_schedule_mark(row["mark"]) for row in _mark_rows(grid))
    prefixes = {_mark_prefix(mark) for mark in scheduled}

    plan_counts: Counter = Counter()
    previous = ""
    for word in document.get("words") or []:
        text = str(word.get("text") or "").strip("()[],.;:").upper()
        # ``ASTM C90`` / ``ACI 318`` cite standards, not members.
        after_standard, previous = previous in _STANDARD_BODIES, text
        if after_standard or not _PLAN_MARK_RE.fullmatch(text):
            continue
        page = int(word.get("page_number") or word.get("page") or 0)
        bbox = word.get("bbox") or []
        if len(bbox) >= 4 and _inside_any(bbox, boxes.get(page, [])):
            continue
        plan_counts[normalize_schedule_mark(text)] += 1

    families: Dict[str, set[str]] = {}
    for mark in plan_counts:
        prefix = _mark_prefix(mark)
        if prefix not in prefixes and prefix not in _SHAPE_PREFIXES:
            families.setdefault(prefix, set()).add(mark)
    return {
        "scheduled_marks": len(scheduled),
        "missing_from_schedule": sorted(
            mark
            for mark in plan_counts
            if _mark_prefix(mark) in prefixes and mark not in scheduled
        ),
        "unused_schedule_marks": sorted(scheduled - set(plan_counts)),
        "unscheduled_mark_families": {
            prefix: sorted(marks)
            for prefix, marks in sorted(families.items())
            if len(marks) >= 3
        },
    }


def _mark_prefix(mark: str) -> str:
    match = re.match(r"[A-Z]+", mark)
    return match.group(0) if match else ""


def _inside_any(bbox: List[float], boxes: List[List[float]], pad: float = 2.0) -> bool:
    cx = (float(bbox[0]) + float(bbox[2])) / 2.0
    cy = (float(bbox[1]) + float(bbox[3])) / 2.0
    return any(
        box[0] - pad <= cx <= box[2] + pad and box[1] - pad <= cy <= box[3] + pad
        for box in boxes
    )


def resolve_schedule_mark(text: str, document: Optional[Dict[str, Any]]) -> str:
    """Catalog section for a bare mark, or ``""`` when this document has no SIZE."""

    if not document or not is_bare_schedule_mark(text):
        return ""
    mark = normalize_schedule_mark(text)
    grid_map = document.get("schedule_mark_map") or {}
    prior = document.get("document_prior") or {}
    prior_map = prior.get("mark_map") or {}
    # Prior maps may still use hyphenated keys from older extractions.
    section = str(
        grid_map.get(mark)
        or prior_map.get(mark)
        or prior_map.get(re.sub(r"\s+", "", str(text or "")).upper())
        or ""
    )
    if not section:
        return ""
    return _catalog_spelling(section)


def schedule_grid_pages(document: Optional[Dict[str, Any]]) -> set[int]:
    """Pages that host a parsed MARK|SIZE schedule grid."""

    pages: set[int] = set()
    if not document:
        return pages
    for grid in document.get("schedule_grid") or []:
        try:
            page = int(grid.get("page") or 0)
        except (TypeError, ValueError):
            continue
        if page:
            pages.add(page)
    return pages


def _recognized_schedule_title(text: str) -> Optional[str]:
    """A schedule name present in nearby header text, or nothing if it is not unique."""

    upper = str(text or "").upper()
    if "BENT PLATE SCHEDULE" in upper:
        return "BENT PLATE SCHEDULE"
    specific = [
        label for label in ("BEARING PLATE SCHEDULE", "BASE PLATE SCHEDULE")
        if label in upper
    ]
    if len(specific) == 1 and "BENT PLATE" not in upper:
        return specific[0]
    if "PLATE SCHEDULE" in upper and not specific and "BENT PLATE" not in upper:
        return "PLATE SCHEDULE"
    return None


def _is_bent_plate_schedule(grid: Dict[str, Any]) -> bool:
    return "BENT PLATE" in str(grid.get("title") or "").upper()


def _source_schedule(grid: Dict[str, Any]) -> Optional[str]:
    title = " ".join(str(grid.get("title") or "").split())
    upper = title.upper()
    if "BENT PLATE" in upper:
        return title or None
    specific = [
        label for label in _KNOWN_SCHEDULE_LABELS
        if label in upper and label != "PLATE SCHEDULE"
    ]
    if len(specific) == 1:
        return specific[0]
    if "PLATE SCHEDULE" in upper and not specific:
        return "PLATE SCHEDULE"
    return title or None


def _context_plate_role(grid: Dict[str, Any], row: Dict[str, Any]) -> str:
    """Plate type from the schedule title or header. The BP prefix is not a type."""

    kind = grid.get("kind")
    if kind in {"base_plate", "bearing_plate"}:
        return str(kind)
    role = row.get("plate_role")
    if role in {"base_plate", "bearing_plate", "plate"}:
        return str(role)
    return "plate"


def _resolved_plate(grid: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mark": row.get("mark"),
        "plate_role": _context_plate_role(grid, row),
        "source_schedule": _source_schedule(grid),
        "source_page": grid.get("page"),
        "source_kind": grid.get("kind"),
        "parsed_plate": row.get("parsed_plate"),
    }


def _plate_definition_rows(grids: Iterable[Dict[str, Any]]) -> Dict[str, List[tuple]]:
    grouped: Dict[str, List[tuple]] = {}
    for grid in grids:
        if _is_bent_plate_schedule(grid) or grid.get("kind") not in _PLATE_CONTEXT_KINDS:
            continue
        for row in grid.get("rows") or []:
            mark = re.sub(r"\s+", "", str(row.get("mark") or "")).upper()
            if not _BP_MARK_RE.fullmatch(mark):
                continue
            grouped.setdefault(normalize_schedule_mark(mark), []).append((grid, row))
    return grouped


def attach_resolved_plates(grids: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Link a column plate reference to its schedule definition. Duplicate marks stay unresolved."""

    grouped = _plate_definition_rows(grids)
    for grid in grids:
        for row in grid.get("rows") or []:
            compact = re.sub(r"\s+", "", str(row.get("plate_text") or "")).upper()
            if not _BP_MARK_RE.fullmatch(compact):
                continue
            matches = grouped.get(normalize_schedule_mark(compact), [])
            others = [(source_grid, source_row) for source_grid, source_row in matches if source_row is not row]
            if len(matches) > 1:
                row["plate_status"] = "ambiguous"
                row["resolved_plate"] = None
                row["plate_candidates"] = [_resolved_plate(source_grid, source_row) for source_grid, source_row in matches]
                continue
            row.pop("plate_candidates", None)
            if len(others) == 1:
                source_grid, source_row = others[0]
                row["resolved_plate"] = _resolved_plate(source_grid, source_row)
                source_status = source_row.get("plate_status")
                row["plate_status"] = source_status if source_status in {"present", "unresolved"} else "present"
                continue
            row["resolved_plate"] = None
            if row.get("mark_role") == "grid_location" or grid.get("kind") not in _PLATE_CONTEXT_KINDS:
                row["plate_status"] = "unresolved"
    return grids


def lookup_schedule_row(
    text: str, document: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """First schedule_grid row for a MARK, or ``None`` when the mark is absent."""

    if not document or not is_schedule_table_mark(text):
        return None
    mark = normalize_schedule_mark(text)
    for grid in document.get("schedule_grid") or []:
        for row in _mark_rows(grid):
            if normalize_schedule_mark(row.get("mark") or "") == mark:
                return dict(row)
    return None


def schedule_assembly_sidecar(
    text: str, document: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Plate / role sidecar for a resolved schedule mark — never invents thickness."""

    row = lookup_schedule_row(text, document)
    if not row:
        return None
    plate_text = str(row.get("plate_text") or "").strip()
    if plate_text and (
        _EMPTY_PLATE_RE.fullmatch(plate_text)
        or _plate_not_applicable(plate_text)
        or row.get("plate_status") == "not_applicable"
    ):
        plate_text = ""
    sidecar = {
        "mark": row.get("mark"),
        "primary_section": row.get("section"),
        "size_text": row.get("size_text"),
        "catalog_valid": bool(row.get("catalog_valid")),
        "plate_text": plate_text or None,
        "plate_role": row.get("plate_role") if plate_text else None,
        "member_plate_roles": list(row.get("member_plate_roles") or []),
        "plate_count_per_member": plate_count_per_member(row),
    }
    if isinstance(row.get("parsed_plate"), dict):
        sidecar["parsed_plate"] = row["parsed_plate"]
    if row.get("plate_status"):
        sidecar["plate_status"] = row["plate_status"]
    if isinstance(row.get("resolved_plate"), dict):
        sidecar["resolved_plate"] = row["resolved_plate"]
    return sidecar


def _auxiliary_size_display(text: str) -> str:
    """Extract the printable plate/angle dim from a possibly polluted SIZE cell."""

    raw = str(text or "").strip()
    if not raw or _EMPTY_PLATE_RE.fullmatch(raw):
        return ""
    angle_first = _ANGLE_THEN_DIM_RE.search(raw)
    if angle_first:
        for token in extract_engineering_tokens(f"{angle_first.group(1)} ANGLE"):
            if token.startswith(("L", "2L")):
                return token
    for token in extract_engineering_tokens(raw):
        if token.startswith(("L", "2L")):
            return token
    matches = list(_PLATE_DIM_RE.finditer(raw))
    if matches:
        a, b, c = matches[-1].groups()
        return f'{a}"x{b}"x{re.sub(r"\s+", " ", c.strip())}"'
    if len(raw) <= 40 and _PLATE_DIM_RE.search(raw):
        return raw
    return ""


def resolve_auxiliary_schedule_mark(
    text: str,
    document: Optional[Dict[str, Any]],
    *,
    catalog_fn: Optional[CatalogFn] = None,
) -> Optional[Dict[str, Any]]:
    """Map BP/CL marks to plate or angle SIZE from ``schedule_grid``.

    Returns a small dict for the orchestrator. Never invents thickness or a
    rolled section that is not printed / catalog-valid in the SIZE cell.
    """

    if not document or not is_auxiliary_schedule_mark(text):
        return None
    compact_mark = re.sub(r"\s+", "", str(text or "")).upper()
    if _BP_MARK_RE.fullmatch(compact_mark):
        found = _plate_definition_rows(document.get("schedule_grid") or []).get(
            normalize_schedule_mark(compact_mark), []
        )
        if len(found) > 1:
            return {
                "mark": compact_mark,
                "abstain": True,
                "ambiguous": True,
                "display": compact_mark,
                "size_text": "",
                "plate_text": compact_mark,
                "plate_role": None,
                "kind": None,
            }
        if len(found) != 1:
            return None
        grid, row = found[0]
        role = _context_plate_role(grid, row)
        size_text = str(row.get("size_text") or "").strip()
        plate_text = str(row.get("plate_text") or "").strip()
        if plate_text and (
            _EMPTY_PLATE_RE.fullmatch(plate_text) or _plate_not_applicable(plate_text)
        ):
            plate_text = ""
        raw_display = plate_text or size_text
        display = _auxiliary_size_display(raw_display) or (
            raw_display if raw_display and len(raw_display) <= 40 else ""
        )
        kind = role if role in {"base_plate", "bearing_plate"} else "plate"
        if not display or _EMPTY_PLATE_RE.fullmatch(display) or _plate_not_applicable(display):
            return {
                "mark": compact_mark,
                "abstain": True,
                "display": compact_mark,
                "kind": kind,
                "size_text": size_text,
                "plate_text": plate_text or None,
                "plate_role": role,
                "parsed_plate": row.get("parsed_plate"),
                "source_schedule": _source_schedule(grid),
                "source_page": grid.get("page"),
            }
        return {
            "mark": compact_mark,
            "abstain": False,
            "kind": kind,
            "display": display,
            "plate_type": "PLATE",
            "section": None,
            "size_text": size_text,
            "plate_text": display,
            "plate_role": role,
            "parsed_plate": row.get("parsed_plate"),
            "source_schedule": _source_schedule(grid),
            "source_page": grid.get("page"),
        }

    row = lookup_schedule_row(text, document)
    if row is None:
        return None
    mark = str(row.get("mark") or "").upper()
    size_text = str(row.get("size_text") or "").strip()
    plate_text = str(row.get("plate_text") or "").strip()
    if plate_text and _EMPTY_PLATE_RE.fullmatch(plate_text):
        plate_text = ""
    raw_display = plate_text or size_text
    display = _auxiliary_size_display(raw_display) or (
        raw_display if raw_display and len(raw_display) <= 40 else ""
    )
    if not display or _EMPTY_PLATE_RE.fullmatch(display):
        return {
            "mark": mark,
            "abstain": True,
            "display": mark,
            "size_text": size_text,
            "plate_text": plate_text or None,
            "plate_role": row.get("plate_role"),
        }

    accept = catalog_fn or _catalog_accepts

    # CL* — prefer a catalog-valid angle in the SIZE cell when present.
    section = section_from_size_text(display, accept) or section_from_size_text(
        size_text or raw_display, accept
    )
    if section:
        return {
            "mark": mark,
            "abstain": False,
            "kind": "icf_lintel",
            "display": section,
            "plate_type": None,
            "section": section,
            "size_text": size_text,
            "plate_text": plate_text or None,
            "plate_role": row.get("plate_role"),
        }
    if display.startswith(("L", "2L")):
        return {
            "mark": mark,
            "abstain": False,
            "kind": "icf_lintel",
            "display": display,
            "plate_type": None,
            "section": display if accept(display) else None,
            "size_text": size_text,
            "plate_text": plate_text or None,
            "plate_role": row.get("plate_role"),
        }
    return {
        "mark": mark,
        "abstain": False,
        "kind": "icf_lintel",
        "display": display,
        "plate_type": "PLATE",
        "section": None,
        "size_text": size_text,
        "plate_text": display,
        "plate_role": row.get("plate_role"),
    }


def _catalog_spelling(section: str) -> str:
    from services.database_loader import catalog_form, lookup_shape

    form = catalog_form(section) or ""
    if form and lookup_shape(form):
        return form
    return ""


def _catalog_accepts(section: str) -> bool:
    return bool(_catalog_spelling(section))


def _grids_on_page(
    words: List[dict],
    page: Any,
    catalog_fn: CatalogFn,
) -> List[Dict[str, Any]]:
    rows = _cluster_rows(words)
    grids: List[Dict[str, Any]] = []
    index = 0
    while index < len(rows):
        band_groups = _header_band_groups(rows[index]["words"])
        if not band_groups:
            index += 1
            continue
        header_index = index
        header_y = rows[index]["y"]
        all_groups = list(band_groups)
        index += 1
        # Adjacent pier | column headers often sit a few points apart on y.
        while index < len(rows):
            more = _header_band_groups(rows[index]["words"])
            if more and abs(rows[index]["y"] - header_y) <= 10.0:
                all_groups.extend(more)
                index += 1
                continue
            break
        body_rows: List[dict] = []
        last_y = rows[index - 1]["y"]
        while index < len(rows):
            if _header_band_groups(rows[index]["words"]):
                break
            if rows[index]["y"] - last_y > _ROW_GAP:
                break
            body_rows.append(rows[index])
            last_y = rows[index]["y"]
            index += 1
        for bands, kind_hint in all_groups:
            _kind, plate_role, title = _schedule_kind(rows, header_index)
            if kind_hint:
                kind = kind_hint
            elif "diameter" in bands:
                kind = "pier"
            elif _kind == "pier" and "diameter" not in bands:
                # Neighboring "PIER SCHEDULE" title can poison MARK|SIZE bands from
                # the column schedule on the same strip. Only remapa when this
                # band group's mark header is literally MARK.
                mark_is_mark_keyword = any(
                    str(word.get("text") or "").upper() == "MARK"
                    and abs(float(word["bbox"][0]) - float(bands["mark"])) < 40.0
                    for word in rows[header_index]["words"]
                )
                kind = "column" if mark_is_mark_keyword else "pier"
            else:
                kind = _kind
            body: List[dict] = []
            for body_row in body_rows:
                parsed = _parse_body_row(
                    body_row["words"],
                    bands,
                    plate_role=plate_role,
                    catalog_fn=catalog_fn,
                )
                if parsed:
                    body.append(parsed)
            if body:
                grids.append(
                    {
                        "page": page,
                        "kind": kind,
                        "rows": body,
                        "source": "word_cluster",
                        "title": _recognized_schedule_title(title),
                    }
                )
    return grids


def _header_band_groups(
    words: List[dict],
) -> List[tuple]:
    """One band map per schedule header, split on MARK/PIER anchors.

    Pier and column schedules often share a y-band on foundation sheets. Splitting
    only on large x-gaps would also detach BASE/BEARING PLATE columns from their
    MARK|SIZE headers, so anchors are the table starts instead.
    """

    ordered = sorted(words, key=lambda word: float(word["bbox"][0]))
    if not ordered:
        return []
    anchors = [
        index
        for index, word in enumerate(ordered)
        if str(word.get("text") or "").upper() in {"MARK", "PIER"}
    ]
    if not anchors:
        bands = _header_bands(ordered)
        if "mark" in bands and "size" in bands:
            return [(bands, "pier" if "diameter" in bands else None)]
        return []
    groups: List[tuple] = []
    for anchor_i, start in enumerate(anchors):
        end = anchors[anchor_i + 1] if anchor_i + 1 < len(anchors) else len(ordered)
        cluster = ordered[start:end]
        bands = _header_bands(cluster)
        if "mark" not in bands or "size" not in bands:
            continue
        labels = " ".join(str(word.get("text") or "") for word in cluster).upper()
        if "PIER" in labels or "DIAMETER" in labels:
            kind_hint = "pier"
        else:
            kind_hint = None
        groups.append((bands, kind_hint))
    return groups


def _cluster_rows(words: List[dict]) -> List[dict]:
    placed = []
    for word in words:
        bbox = word.get("bbox") or []
        if len(bbox) < 2 or not str(word.get("text") or "").strip():
            continue
        placed.append(word)
    placed.sort(key=lambda word: (float(word["bbox"][1]), float(word["bbox"][0])))
    rows: List[dict] = []
    for word in placed:
        y = float(word["bbox"][1])
        if not rows or abs(y - rows[-1]["y"]) > 3.0:
            rows.append({"y": y, "words": [word]})
        else:
            rows[-1]["words"].append(word)
    return rows


def _header_bands(words: List[dict]) -> Dict[str, float]:
    ordered = sorted(words, key=lambda word: float(word["bbox"][0]))
    bands: Dict[str, float] = {}
    labels = [(word, str(word.get("text") or "").upper()) for word in ordered]
    for index, (word, label) in enumerate(labels):
        x = float(word["bbox"][0])
        nxt = labels[index + 1][1] if index + 1 < len(labels) else ""
        if label == "MARK":
            bands["mark"] = x
        elif label == "PIER":
            # "PIER TYPE" mark column on EXISTING PIER SCHEDULE tables.
            bands["mark"] = min(bands.get("mark", x), x)
        elif label == "TYPE" and "mark" in bands:
            # Second word of "PIER TYPE" — keep the earlier PIER x origin.
            pass
        elif label == "SIZE":
            bands["size"] = x
        elif label == "DIAMETER":
            bands["diameter"] = x
        elif label == "REMARKS":
            bands["remarks"] = x
        elif label in {"ANCHOR", "BOLTS"}:
            bands["anchor"] = min(bands.get("anchor", x), x)
        elif "PLATE" in label or (label in {"BASE", "BEARING"} and "PLATE" in nxt):
            bands["plate"] = min(bands.get("plate", x), x)
    return bands


def _schedule_kind(
    rows: List[dict], header_index: int, span: Optional[tuple] = None
) -> tuple:
    blob = _title_blob(rows, header_index, span)
    header_labels = _text(_in_span(rows[header_index]["words"], span)).upper()
    if "BEARING" in header_labels:
        plate_role = "bearing_plate"
    elif "BASE" in header_labels:
        plate_role = "base_plate"
    else:
        plate_role = "plate"
    # Title phrases before column headers — a lintel table with a BEARING PLATE
    # column must stay kind=lintel, not bearing_plate.
    if re.search(r"BEARING\s+PLATE\s+SCHEDULE", blob):
        return "bearing_plate", plate_role, blob
    if re.search(r"BASE\s+PLATE\s+SCHEDULE", blob):
        return "base_plate", plate_role, blob
    if re.search(r"\bPIER\s+SCHEDULE\b", blob) or (
        "PIER" in header_labels and "DIAMETER" in header_labels
    ):
        return "pier", plate_role, blob
    if "COLUMN" in blob and "LINTEL" not in blob and "PIER" not in blob:
        return "column", plate_role, blob
    if "ICF" in blob or "CONCRETE CORE" in blob:
        return "icf_lintel", plate_role, blob
    if "LINTEL" in blob:
        return "lintel", plate_role, blob
    if "BEARING PLATE" in blob:
        return "bearing_plate", plate_role, blob
    return "schedule", plate_role, blob


def _in_span(words: List[dict], span: Optional[tuple]) -> List[dict]:
    if span is None:
        return words
    left, right = span
    return [word for word in words if left <= float(word["bbox"][0]) < right]


def _title_blob(rows: List[dict], header_index: int, span: Optional[tuple] = None) -> str:
    """Header row plus rows up to ``_HEADER_LOOKBACK`` above it."""

    def text(row: dict) -> str:
        return _text(_in_span(row["words"], span))

    header_y = rows[header_index]["y"]
    parts = [text(rows[header_index])]
    for row in rows[: header_index + 1]:
        if header_y - _HEADER_LOOKBACK <= row["y"] <= header_y:
            parts.append(text(row))
    return " ".join(parts).upper()


def _column_for(x: float, bands: Dict[str, float]) -> str:
    chosen = min(bands, key=lambda name: bands[name])
    for name, origin in sorted(bands.items(), key=lambda item: item[1]):
        if x + 4.0 >= origin:
            chosen = name
    return chosen


def _text(words: Iterable[dict]) -> str:
    return " ".join(str(word.get("text") or "") for word in words)


def _compact_mark(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).upper()


def _split_row(
    words: List[dict], bands: Dict[str, float], mark_re: "re.Pattern[str]"
) -> Optional[tuple]:
    """``(cells, mark_word, size_words)`` in x order, or ``None`` without a mark.

    Leftover MARK-cell words (a SIZE that drifted left) join the SIZE cell.
    """

    cells: Dict[str, List[dict]] = {name: [] for name in bands}
    for word in sorted(words, key=lambda word: float(word["bbox"][0])):
        cells.setdefault(_column_for(float(word["bbox"][0]), bands), []).append(word)
    mark_cell = cells.get("mark") or []
    mark_word = next(
        (word for word in mark_cell if mark_re.fullmatch(_compact_mark(word.get("text")))),
        None,
    )
    if mark_word is None:
        return None
    size_words = [word for word in mark_cell if word is not mark_word] + (cells.get("size") or [])
    return cells, mark_word, size_words


def _parse_body_row(
    words: List[dict],
    bands: Dict[str, float],
    *,
    plate_role: str,
    catalog_fn: CatalogFn,
) -> Optional[dict]:
    # Preserve the pre-ruled-table BP/CL input contract. These rows are also
    # used by the Results resolver, whose behavior this integration retains.
    auxiliary = _split_row(words, bands, _LEGACY_ROW_MARK_RE)
    if auxiliary is not None and is_auxiliary_schedule_mark(auxiliary[1].get("text")):
        cells, mark_word, size_words = auxiliary
        size_text = _text(size_words).strip()
        plate_text = _text(cells.get("plate") or []).strip() or size_text
        row = {
            "mark": _compact_mark(mark_word.get("text")),
            "size_text": size_text,
            "section": None,
            "catalog_valid": False,
            "plate_text": plate_text,
            "plate_role": plate_role if plate_text else None,
            "member_plate_roles": member_plate_roles(_text(words)),
        }
        remarks = " ".join(str(word.get("text") or "") for word in (cells.get("remarks") or [])).strip()
        if remarks:
            row["plate_notes"] = remarks
        _apply_plate_metadata(row)
        return row
    cells: Dict[str, List[str]] = {name: [] for name in bands}
    mark_x = float(bands["mark"]) if "mark" in bands else None
    right_x = max(bands.values()) if bands else None
    ordered = sorted(words, key=lambda word: float(word["bbox"][0]))
    scoped: List[dict] = []
    for word in ordered:
        x = float(word["bbox"][0])
        if mark_x is not None and x < mark_x - _BAND_LEFT_SLACK:
            continue
        if right_x is not None and x > right_x + _BAND_RIGHT_SLACK:
            continue
        scoped.append(word)
        column = _column_for(x, bands)
        cells.setdefault(column, []).append(str(word.get("text") or ""))
    mark = ""
    mark_rest: List[str] = []
    for piece in cells.get("mark") or []:
        compact = re.sub(r"\s+", "", piece).upper()
        if not mark and is_schedule_table_mark(compact):
            mark = compact
        else:
            mark_rest.append(piece)
    if not mark:
        return None
    size_text = " ".join(mark_rest + (cells.get("size") or [])).strip()
    diameter_text = " ".join(cells.get("diameter") or []).strip()
    if not size_text and diameter_text:
        size_text = diameter_text
    elif diameter_text and diameter_text not in size_text:
        size_text = f"{size_text} DIA {diameter_text}".strip()
    plate_text = " ".join(cells.get("plate") or []).strip()
    row_text = " ".join(str(word.get("text") or "") for word in scoped)
    # BP/CL marks store plate/angle SIZE text; L/C marks feed the steel map.
    # Pier marks are concrete footing sizes — never invent a rolled section.
    section = None
    if is_bare_schedule_mark(mark) and not is_pier_schedule_mark(mark):
        section = section_from_size_text(size_text or row_text, catalog_fn)
    if is_auxiliary_schedule_mark(mark) and not plate_text:
        plate_text = size_text
    row = {
        "mark": mark,
        "size_text": size_text,
        "section": section,
        "catalog_valid": bool(section),
        "plate_text": plate_text,
        "plate_role": plate_role if plate_text else None,
        "member_plate_roles": member_plate_roles(row_text),
        "bbox": [
            min(float(word["bbox"][0]) for word in scoped),
            min(float(word["bbox"][1]) for word in scoped),
            max(float(word["bbox"][2]) for word in scoped),
            max(float(word["bbox"][3]) for word in scoped),
        ],
    }
    remarks = " ".join(cells.get("remarks") or []).strip()
    if remarks:
        row["plate_notes"] = remarks
    _apply_plate_metadata(row)
    return row


# --------------------------------------------------------------------------
# Shadow structured evidence (SCHEDULE_EVIDENCE_SHADOW_ENABLED). Nothing in
# prediction reads it. Each MARK header column opens its own table segment,
# so side-by-side schedules (concrete PIER | steel COLUMN) do not bleed into
# each other. A definition row is evidence, never a physical occurrence.
# --------------------------------------------------------------------------

SCHEDULE_EVIDENCE_SCHEMA_VERSION = "1.0"
_LEGACY_SHADOW_MARK_RE = re.compile(r"^(?:L|C)\d+[A-Z]?$", re.IGNORECASE)
# Hyphen / multi-letter marks (C-1, LB-1, BP1). Accepted only as the MARK
# cell of a validated row; the family always comes from the SIZE cell.
_WIDE_MARK_RE = re.compile(r"^[A-Z]{1,3}-?\d{1,3}[A-Z]?$", re.IGNORECASE)
_SEGMENT_REACH = 300.0
# Fabricated-component schedules: no rolled section is expected.
_COMPONENT_KINDS = frozenset({"bearing_plate"})
_KIND_ROLES = frozenset({"lintel", "column", "bearing_plate"})
# Lifecycle only when the schedule title prints it (first match wins).
# Existing / new / demolition reuse drawing_intelligence's patterns.
_LIFECYCLE_TITLE_RES = (
    (_DEMO_RE, "demolition"),
    (re.compile(r"\bREINF", re.IGNORECASE), "reinforcing"),
    (_EXISTING_RE, "existing"),
    (_NEW_RE, "new"),
)


def build_schedule_evidence(
    words: Iterable[Dict[str, Any]],
    *,
    discovery: str = "current",
    catalog_fn: Optional[CatalogFn] = None,
) -> Dict[str, Any]:
    """Structured schedule rows with provenance. ``current`` = legacy marks."""

    mark_re = _WIDE_MARK_RE if discovery == "widened" else _LEGACY_SHADOW_MARK_RE
    accept = catalog_fn or _catalog_accepts
    by_page: Dict[Any, List[dict]] = {}
    for word in words:
        by_page.setdefault(word.get("page_number", word.get("page", 0)), []).append(word)
    regions: List[dict] = []
    records: List[dict] = []
    rejections: List[dict] = []
    for page, page_words in by_page.items():
        if not _page_has_mark_size_headers(page_words):
            continue
        rows = _cluster_rows(page_words)
        for index, row in enumerate(rows):
            for bands, span in _header_segments(row["words"]):
                segment = _segment_evidence(rows, index, page, bands, span, mark_re, accept)
                if segment["records"]:
                    regions.append(segment["region"])
                    records.extend(segment["records"])
                rejections.extend(segment["rejections"])
    definitions, conflicts = _definitions(records)
    return {
        "schema_version": SCHEDULE_EVIDENCE_SCHEMA_VERSION,
        "discovery": discovery,
        "regions": regions,
        "records": records,
        "rejections": rejections,
        "definitions": definitions,
        "conflicts": sorted(conflicts),
        "mark_map": {d["mark_normalized"]: d["primary_section"] for d in definitions},
    }


def _header_segments(words: List[dict]) -> List[tuple]:
    """One ``(bands, (left, right))`` per MARK word that has a SIZE to its right."""

    ordered = sorted(words, key=lambda word: float(word["bbox"][0]))
    marks = [float(w["bbox"][0]) for w in ordered if str(w.get("text") or "").upper() == "MARK"]
    segments = []
    for position, mark_x in enumerate(marks):
        right = marks[position + 1] if position + 1 < len(marks) else float("inf")
        bands = _header_bands([w for w in ordered if mark_x <= float(w["bbox"][0]) < right])
        if bands.get("size", mark_x) <= mark_x:
            continue
        right = min(right, max(bands.values()) + _SEGMENT_REACH)
        segments.append((bands, (mark_x - 8.0, right)))
    return segments


def _segment_evidence(rows, header_index, page, bands, span, mark_re, accept) -> dict:
    kind, plate_role, title = _schedule_kind(rows, header_index, span)
    region_id = f"p{page}-y{int(rows[header_index]['y'])}-x{int(span[0])}"
    region_words = list(_in_span(rows[header_index]["words"], span))
    records: List[dict] = []
    rejections: List[dict] = []
    last_y = rows[header_index]["y"]
    for row in rows[header_index + 1:]:
        if row["y"] - last_y > _ROW_GAP:
            break
        cell_words = _in_span(row["words"], span)
        if not cell_words:
            continue
        if "MARK" in {str(w.get("text") or "").upper() for w in cell_words}:
            break
        last_y = row["y"]
        region_words.extend(cell_words)
        record = _evidence_row(cell_words, bands, kind, plate_role, title, mark_re, accept)
        if record is None:
            rejections.append({
                "page_number": page,
                "region_id": region_id,
                "text": _text(cell_words),
                "reason": "mark_not_recognized",
            })
            continue
        records.append(record)
    region_bbox = _union_bbox(region_words)
    for record in records:
        record.update({
            "schema_version": SCHEDULE_EVIDENCE_SCHEMA_VERSION,
            "page_number": page,
            "region_id": region_id,
            "region_bbox": region_bbox,
        })
    return {
        "region": {
            "region_id": region_id,
            "page_number": page,
            "kind": kind,
            "region_bbox": region_bbox,
            "header_bands": dict(bands),
        },
        "records": records,
        "rejections": rejections,
    }


def _evidence_row(words, bands, kind, plate_role, title, mark_re, accept) -> Optional[dict]:
    split = _split_row(words, bands, mark_re)
    if split is None:
        return None
    cells, mark_word, size_words = split
    mark_raw = str(mark_word.get("text") or "")
    size_text = _text(size_words).strip()
    plate_text = _text(cells.get("plate") or []).strip()
    row_text = _text(words)
    # SIZE cell only: unlike the legacy row, never fall back to the whole row.
    section = section_from_size_text(size_text, accept) if size_text else None
    roles = ([kind] if kind in _KIND_ROLES else []) + member_plate_roles(row_text)
    components = []
    if plate_text:
        roles.append(plate_role)
        components.append({"role": plate_role, "text": plate_text, "quantity": None})
    if kind in _COMPONENT_KINDS and size_text:
        components.append({"role": kind, "text": size_text, "quantity": None})
    lifecycle = _lifecycle(title)
    # A reinforcing schedule's SIZE cell names the host member, not the
    # mark's identity (H5 RI-1).
    if lifecycle == "reinforcing":
        status, reason, section = "rejected", "host_member_schedule", None
    elif kind in _COMPONENT_KINDS and not section:
        status, reason = "rejected", "component_schedule"
    elif not section:
        status, reason = "rejected", "size_not_catalog_valid"
    else:
        status, reason = "resolved", None
    return {
        "mark_raw": mark_raw,
        "mark_normalized": _compact_mark(mark_raw),
        "size_text_raw": size_text,
        "primary_section": section,
        "catalog_valid": bool(section),
        "role_tags": list(dict.fromkeys(roles)),
        "components": components,
        "row_bbox": _union_bbox(words),
        "source_cells": [
            {
                "column": name,
                "text": _text(cell),
                "bbox": _union_bbox(cell),
            }
            for name, cell in cells.items()
            if cell
        ],
        "countable_occurrence": False,
        "resolution_status": status,
        "rejection_reason": reason,
        "lifecycle_status": lifecycle,
    }


def _lifecycle(title: str) -> str:
    """Lifecycle printed in the schedule title; never inferred otherwise."""

    for pattern, status in _LIFECYCLE_TITLE_RES:
        if pattern.search(title):
            return status
    return "unknown"


def _definitions(records: List[dict]) -> tuple:
    """Group resolved rows by mark, independent of row order.

    Same section + lifecycle -> one definition keeping every source row;
    different section or lifecycle -> every such row becomes a conflict and
    the mark resolves to nothing. Same section with different component text
    keeps the section (contracts carry the section only) but is flagged for
    review rather than silently picking one component.
    """

    by_mark: Dict[str, List[dict]] = {}
    for record in records:
        if record["resolution_status"] == "resolved":
            by_mark.setdefault(record["mark_normalized"], []).append(record)
    definitions: List[dict] = []
    conflicts = set()
    for mark in sorted(by_mark):
        rows = by_mark[mark]
        if len({r["primary_section"] for r in rows}) > 1:
            reason = "conflicting_duplicate_mark"
        elif len({r["lifecycle_status"] for r in rows}) > 1:
            reason = "conflicting_lifecycle"
        else:
            reason = None
        if reason:
            conflicts.add(mark)
            for row in rows:
                row["resolution_status"] = "conflict"
                row["rejection_reason"] = reason
            continue
        components = sorted(
            {(c["role"], c["text"]) for r in rows for c in r["components"]}
        )
        component_sets = {
            tuple(sorted((c["role"], c["text"]) for c in r["components"])) for r in rows
        }
        attribute_conflicts = ["components"] if len(component_sets) > 1 else []
        definitions.append({
            "duplicate_group_id": f"{mark}|{rows[0]['primary_section']}|{rows[0]['lifecycle_status']}",
            "mark_normalized": mark,
            "primary_section": rows[0]["primary_section"],
            "lifecycle_status": rows[0]["lifecycle_status"],
            "role_tags": sorted({tag for r in rows for tag in r["role_tags"]}),
            "components": [{"role": role, "text": text, "quantity": None} for role, text in components],
            "attribute_conflicts": attribute_conflicts,
            "review_required": bool(attribute_conflicts),
            "countable_occurrence": False,
            "sources": sorted(
                (
                    {"page_number": r["page_number"], "region_id": r["region_id"], "row_bbox": r["row_bbox"]}
                    for r in rows
                ),
                key=lambda s: (str(s["page_number"]), s["region_id"], s["row_bbox"] or []),
            ),
        })
    return definitions, conflicts


def _union_bbox(words: Iterable[dict]) -> Optional[List[float]]:
    return _union_boxes([word.get("bbox") or [] for word in words])
