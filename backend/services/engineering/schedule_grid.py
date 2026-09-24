"""Column-group MARK | SIZE | PLATE rows from existing PDF words.

This is not a second text extractor. It clusters words already produced by
``pdf_parser`` under schedule headers and emits a document-local mark map.
Only a catalog-valid printed SIZE becomes a section. Plate cells stay plate
sidecars. Incomplete angles are never completed here.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from services.token_extractor import extract_engineering_tokens


_MARK_RE = re.compile(r"^(?:L|C)\d+[A-Z]?$", re.IGNORECASE)
_AUX_MARK_RE = re.compile(r"^(?:BP|CL)\d+[A-Z]?$", re.IGNORECASE)
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


def is_bare_schedule_mark(text: str) -> bool:
    """True for lintel/column marks such as ``L1``, ``C1``, ``L1A`` — not ``L4X4``."""

    compact = re.sub(r"\s+", "", str(text or "")).upper()
    return bool(_MARK_RE.fullmatch(compact))


def is_auxiliary_schedule_mark(text: str) -> bool:
    """True for bearing-plate / ICF-lintel marks such as ``BP1``, ``CL2``."""

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
        for row in grid.get("rows") or []:
            if row.get("catalog_valid") and row.get("section") and row.get("mark"):
                mapping.setdefault(str(row["mark"]).upper(), str(row["section"]))
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
        if label == "MARK":
            seen_mark = True
        elif label == "SIZE":
            seen_size = True
        if seen_mark and seen_size:
            return True
    return False


def attach_schedule_grid(document: Dict[str, Any]) -> Dict[str, Any]:
    """Store ``schedule_grid`` and ``schedule_mark_map`` on the extraction document."""

    from config import settings

    if not settings.schedule_grid_enabled:
        return document
    grids = build_schedule_grids(document.get("words") or [])
    document["schedule_grid"] = grids
    document["schedule_mark_map"] = schedule_mark_map(grids)
    return document


def resolve_schedule_mark(text: str, document: Optional[Dict[str, Any]]) -> str:
    """Catalog section for a bare mark, or ``""`` when this document has no SIZE."""

    if not document or not is_bare_schedule_mark(text):
        return ""
    mark = re.sub(r"\s+", "", str(text or "")).upper()
    grid_map = document.get("schedule_mark_map") or {}
    prior = document.get("document_prior") or {}
    prior_map = prior.get("mark_map") or {}
    section = str(grid_map.get(mark) or prior_map.get(mark) or "")
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
    mark = re.sub(r"\s+", "", str(text or "")).upper()
    for grid in document.get("schedule_grid") or []:
        for row in grid.get("rows") or []:
            if str(row.get("mark") or "").upper() == mark:
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
        bands = _header_bands(rows[index]["words"])
        if not bands or "mark" not in bands or "size" not in bands:
            index += 1
            continue
        kind, plate_role = _schedule_kind(rows, index)
        body: List[dict] = []
        last_y = rows[index]["y"]
        index += 1
        while index < len(rows):
            next_bands = _header_bands(rows[index]["words"])
            if "mark" in next_bands and "size" in next_bands:
                break
            if rows[index]["y"] - last_y > _ROW_GAP:
                break
            parsed = _parse_body_row(
                rows[index]["words"],
                bands,
                plate_role=plate_role,
                catalog_fn=catalog_fn,
            )
            if parsed:
                body.append(parsed)
            last_y = rows[index]["y"]
            index += 1
        if body:
            grids.append(
                {
                    "page": page,
                    "kind": kind,
                    "rows": body,
                }
            )
    return grids


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
        elif label == "SIZE":
            bands["size"] = x
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
    if "COLUMN" in blob and "LINTEL" not in blob:
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
    ordered = sorted(words, key=lambda word: float(word["bbox"][0]))
    for word in ordered:
        column = _column_for(float(word["bbox"][0]), bands)
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
    plate_text = " ".join(cells.get("plate") or []).strip()
    row_text = " ".join(str(word.get("text") or "") for word in ordered)
    # BP/CL marks store plate/angle SIZE text; only bare L/C marks feed the
    # steel section map via catalog-valid SIZE tokens.
    section = (
        section_from_size_text(size_text or row_text, catalog_fn)
        if is_bare_schedule_mark(mark)
        else None
    )
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
    }
