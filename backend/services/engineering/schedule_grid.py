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

from services.engineering.schedule_tables import (
    MARK_HEADERS,
    SIZE_HEADERS,
    read_ruled_tables,
)
from services.token_extractor import extract_engineering_tokens


# Optional hyphen/underscore: C-1, C_1, L-13, P-1, BP-6 — same family as C1 / L13 / P1.
_MARK_RE = re.compile(r"^(?:L|C|P)[-_]?\d+[A-Z]?$", re.IGNORECASE)
_AUX_MARK_RE = re.compile(r"^(?:BP|CL)[-_]?\d+[A-Z]?$", re.IGNORECASE)
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
# Schedule SIZE cells on dense sheets often merge neighboring note text.
# Prefer the printed plate / angle dimension embedded in that blob.
_PLATE_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?|\d+/\d+)\s*\"?\s*[xX×]\s*"
    r"(\d+(?:\.\d+)?|\d+/\d+)\s*\"?\s*[xX×]\s*"
    r"(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s*\"?"
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

    compact = re.sub(r"\s+", "", str(text or "")).upper()
    return bool(_MARK_RE.fullmatch(compact))


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


def plate_count_per_member(row: Dict[str, Any]) -> int:
    """Sidecar plate count hint from schedule notes — not a physical takeoff yet.

    Struct note: bearing plate size applies to each end unless noted otherwise.
    Empty / dash plate cells (e.g. L4 frame-to-column) count as zero.
    """

    plate_text = str(row.get("plate_text") or "").strip()
    if not plate_text or _EMPTY_PLATE_RE.fullmatch(plate_text):
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


def schedule_mark_map(grids: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Mark → catalog section. Non-steel SIZE cells (precast, notes) are omitted."""

    mapping: Dict[str, str] = {}
    for grid in grids:
        for row in _mark_rows(grid):
            if row.get("catalog_valid") and row.get("section") and row.get("mark"):
                key = normalize_schedule_mark(row["mark"])
                mapping.setdefault(key, str(row["section"]))
    return mapping


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
    return grids


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
) -> List[Dict[str, Any]]:
    """Ruled-table grids first; word-cluster rows only for marks they missed."""

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
    ruled = _ruled_grids(
        read_ruled_tables(pdf_path, word_list, pages=page_filter), accept
    )
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
    return merged


def attach_schedule_grid(
    document: Dict[str, Any], *, pdf_path: Optional[str] = None
) -> Dict[str, Any]:
    """Store ``schedule_grid``, ``schedule_mark_map`` and the plan cross-check."""

    from config import settings

    if not settings.schedule_grid_enabled:
        return document
    grids = build_document_schedule_grids(
        document.get("words") or [],
        pdf_path=pdf_path if settings.schedule_ruled_tables_enabled else None,
    )
    document["schedule_grid"] = grids
    document["schedule_mark_map"] = schedule_mark_map(grids)
    document["schedule_crosscheck"] = schedule_mark_crosscheck(document)
    return document


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
        else:
            grid = _ruled_rows_grid(record, catalog_fn)
        if grid and grid["rows"]:
            grids.append(grid)
    return grids


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
    size_col = next(
        (
            column
            for column, label in enumerate(header)
            if column != mark_col and label in SIZE_HEADERS
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
            ),
            None,
        )
    plate_cols, diameter_cols, other_cols = [], [], []
    for column, label in enumerate(header):
        if column in (mark_col, size_col):
            continue
        if "PLATE" in label:
            plate_cols.append(column)
        elif label.startswith("DIA"):
            diameter_cols.append(column)
        elif label in _SKIP_HEADERS or "ANCHOR" in label or "BOLT" in label:
            continue
        else:
            other_cols.append(column)
    kind = schedule_kind_from_title(record["title"])
    if kind == "schedule":
        kind = schedule_kind_from_title(header[mark_col])
    plate_labels = " ".join(header[column] for column in plate_cols)
    if kind == "bearing_plate" or "BEARING" in plate_labels:
        plate_role = "bearing_plate"
    elif "BASE" in plate_labels:
        plate_role = "base_plate"
    else:
        plate_role = "plate"

    rows: List[Dict[str, Any]] = []
    for body_row in body:
        cells = (body_row["cells"] + [""] * width)[:width]
        mark = re.sub(r"\s+", "", cells[mark_col]).upper()
        if not mark or not _is_table_mark(mark, catalog_fn):
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
        plate_mark = kind in _PLATE_KINDS or is_auxiliary_schedule_mark(mark)
        if not plate_text and plate_mark:
            plate_text = size_text
        section = None
        if kind not in NON_STEEL_SCHEDULE_KINDS and not plate_mark:
            section = section_from_size_text(size_text, catalog_fn)
        rows.append(
            {
                "mark": mark,
                "size_text": size_text,
                "section": section,
                "catalog_valid": bool(section),
                "plate_text": plate_text,
                "plate_role": plate_role if plate_text else None,
                "member_plate_roles": member_plate_roles(" ".join(cells)),
                "bbox": body_row.get("bbox"),
            }
        )
    return {
        "page": record["page"],
        "kind": kind,
        "rows": rows,
        "source": "ruled_table",
        "layout": "rows",
        "title": record["title"],
        "bbox": record["bbox"],
    }


def _transposed_grid(
    record: Dict[str, Any], catalog_fn: CatalogFn
) -> Optional[Dict[str, Any]]:
    """One row per (grid location, section) of a Revit column schedule."""

    locations = sorted(record["locations"], key=lambda item: item["x"])
    if not locations:
        return None
    gaps = [b["x"] - a["x"] for a, b in zip(locations, locations[1:]) if b["x"] > a["x"]]
    tolerance = max(0.6 * median(gaps), 12.0) if gaps else 40.0

    def nearest(x: float) -> Optional[str]:
        best = min(locations, key=lambda item: abs(item["x"] - x))
        return best["location"] if abs(best["x"] - x) <= tolerance else None

    plates: Dict[str, str] = {}
    rows: List[Dict[str, Any]] = []
    seen: set[tuple] = set()
    for cell in record["cells"]:
        location = nearest(cell["x"])
        if location is None:
            continue
        text = " ".join(cell["text"].split())
        if "BASE PLATE" in cell["row_label"]:
            plates.setdefault(location, text)
            continue
        section = section_from_size_text(text, catalog_fn)
        if not section or (location, section) in seen:
            continue
        seen.add((location, section))
        rows.append(
            {
                "mark": location,
                "mark_role": "grid_location",
                "size_text": text,
                "section": section,
                "catalog_valid": True,
                "level": cell["row_label"],
                "plate_text": "",
                "plate_role": None,
                "member_plate_roles": [],
                "bbox": None,
            }
        )
    for row in rows:
        plate = plates.get(row["mark"], "")
        if plate:
            row["plate_text"] = plate
            row["plate_role"] = "base_plate"
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
    if plate_text and _EMPTY_PLATE_RE.fullmatch(plate_text):
        plate_text = ""
    return {
        "mark": row.get("mark"),
        "primary_section": row.get("section"),
        "size_text": row.get("size_text"),
        "catalog_valid": bool(row.get("catalog_valid")),
        "plate_text": plate_text or None,
        "plate_role": row.get("plate_role") if plate_text else None,
        "member_plate_roles": list(row.get("member_plate_roles") or []),
        "plate_count_per_member": plate_count_per_member(row),
    }


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
    if mark.startswith("BP"):
        return {
            "mark": mark,
            "abstain": False,
            "kind": "bearing_plate",
            "display": display,
            "plate_type": "PLATE",
            "section": None,
            "size_text": size_text,
            "plate_text": display,
            "plate_role": row.get("plate_role") or "bearing_plate",
        }

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
            _kind, plate_role = _schedule_kind(rows, header_index)
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


def _schedule_kind(rows: List[dict], header_index: int) -> tuple:
    header_y = rows[header_index]["y"]
    header_labels = " ".join(
        str(word.get("text") or "") for word in rows[header_index]["words"]
    ).upper()
    blob_parts = [header_labels]
    for row in rows[: header_index + 1]:
        if header_y - _HEADER_LOOKBACK <= row["y"] <= header_y:
            blob_parts.append(
                " ".join(str(word.get("text") or "") for word in row["words"])
            )
    blob = " ".join(blob_parts).upper()
    if "BEARING" in header_labels:
        plate_role = "bearing_plate"
    elif "BASE" in header_labels:
        plate_role = "base_plate"
    else:
        plate_role = "plate"
    # Title phrases before column headers — a lintel table with a BEARING PLATE
    # column must stay kind=lintel, not bearing_plate.
    if re.search(r"BEARING\s+PLATE\s+SCHEDULE", blob):
        return "bearing_plate", plate_role
    if re.search(r"\bPIER\s+SCHEDULE\b", blob) or (
        "PIER" in header_labels and "DIAMETER" in header_labels
    ):
        return "pier", plate_role
    if "COLUMN" in blob and "LINTEL" not in blob and "PIER" not in blob:
        return "column", plate_role
    if "ICF" in blob or "CONCRETE CORE" in blob:
        return "icf_lintel", plate_role
    if "LINTEL" in blob:
        return "lintel", plate_role
    if "BEARING PLATE" in blob:
        return "bearing_plate", plate_role
    return "schedule", plate_role


def _column_for(x: float, bands: Dict[str, float]) -> str:
    chosen = min(bands, key=lambda name: bands[name])
    for name, origin in sorted(bands.items(), key=lambda item: item[1]):
        if x + 4.0 >= origin:
            chosen = name
    return chosen


def _parse_body_row(
    words: List[dict],
    bands: Dict[str, float],
    *,
    plate_role: str,
    catalog_fn: CatalogFn,
) -> Optional[dict]:
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
    return {
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
