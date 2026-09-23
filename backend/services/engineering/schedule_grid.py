"""Column-group MARK | SIZE | PLATE rows from existing PDF words.

This is not a second text extractor. It clusters words already produced by
``pdf_parser`` under schedule headers and emits a document-local mark map.
Only a catalog-valid printed SIZE becomes a section. Plate cells stay plate
sidecars. Incomplete angles are never completed here.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from services.engineering.drawing_intelligence import _DEMO_RE, _EXISTING_RE, _NEW_RE
from services.engineering.member_geometry import _union_bbox as _union_boxes
from services.token_extractor import extract_engineering_tokens


_MARK_RE = re.compile(r"^(?:L|C)\d+[A-Z]?$", re.IGNORECASE)
_WITH_PLATE_RE = re.compile(r"\bWITH\s+(BOTTOM|HUNG)\s+PLATE\b", re.IGNORECASE)
_ROW_GAP = 36.0
_HEADER_LOOKBACK = 80.0

CatalogFn = Callable[[str], bool]


def is_bare_schedule_mark(text: str) -> bool:
    """True for lintel/column marks such as ``L1``, ``C1``, ``L1A`` — not ``L4X4``."""

    return bool(_MARK_RE.fullmatch(_compact_mark(text)))


def member_plate_roles(text: str) -> List[str]:
    """``WITH BOTTOM/HUNG PLATE`` on a size cell. Not a second rolled section."""

    roles: List[str] = []
    for match in _WITH_PLATE_RE.finditer(str(text or "")):
        kind = match.group(1).upper()
        role = "bottom_plate" if kind == "BOTTOM" else "hung_plate"
        if role not in roles:
            roles.append(role)
    return roles


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
        for row in grid.get("rows") or []:
            if row.get("catalog_valid") and row.get("section") and row.get("mark"):
                sections.setdefault(str(row["mark"]).upper(), []).append(str(row["section"]))
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
    document["schedule_mark_map"] = schedule_mark_map(
        grids, drop_conflicts=settings.schedule_mark_conflict_guard_enabled
    )
    if settings.schedule_evidence_shadow_enabled:
        document["schedule_evidence_shadow"] = build_schedule_evidence(
            document.get("words") or [],
            discovery="widened" if settings.schedule_evidence_shadow_widened else "current",
        )
    return document


def resolve_schedule_mark(text: str, document: Optional[Dict[str, Any]]) -> str:
    """Catalog section for a bare mark, or ``""`` when this document has no SIZE."""

    if not document or not is_bare_schedule_mark(text):
        return ""
    mark = _compact_mark(text)
    grid_map = document.get("schedule_mark_map") or {}
    prior = document.get("document_prior") or {}
    prior_map = prior.get("mark_map") or {}
    section = str(grid_map.get(mark) or prior_map.get(mark) or "")
    if not section:
        return ""
    return _catalog_spelling(section)


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
        kind, plate_role, _ = _schedule_kind(rows, index)
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
    if "LINTEL" in blob:
        return "lintel", plate_role, blob
    if "COLUMN" in blob:
        return "column", plate_role, blob
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
    split = _split_row(words, bands, _MARK_RE)
    if split is None:
        return None
    cells, mark_word, size_words = split
    size_text = _text(size_words).strip()
    plate_text = _text(cells.get("plate") or []).strip()
    row_text = _text(sorted(words, key=lambda word: float(word["bbox"][0])))
    section = section_from_size_text(size_text or row_text, catalog_fn)
    return {
        "mark": _compact_mark(mark_word.get("text")),
        "size_text": size_text,
        "section": section,
        "catalog_valid": bool(section),
        "plate_text": plate_text,
        "plate_role": plate_role if plate_text else None,
        "member_plate_roles": member_plate_roles(row_text),
    }


# --------------------------------------------------------------------------
# Shadow structured evidence (SCHEDULE_EVIDENCE_SHADOW_ENABLED). Nothing in
# prediction reads it. Each MARK header column opens its own table segment,
# so side-by-side schedules (concrete PIER | steel COLUMN) do not bleed into
# each other. A definition row is evidence, never a physical occurrence.
# --------------------------------------------------------------------------

SCHEDULE_EVIDENCE_SCHEMA_VERSION = "1.0"
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

    mark_re = _WIDE_MARK_RE if discovery == "widened" else _MARK_RE
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
