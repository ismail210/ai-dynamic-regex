"""Deterministic, shadow-only schedule-region quarantine.

This module classifies already-extracted exact catalog labels inside strongly
bounded schedule regions as definition evidence. It never parses a schedule
matrix into members, never derives quantity, and never mutates its input.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from services.database_loader import catalog_form
from services.engineering import schedule_grid
from services.engineering.context_scope import OBJECT_SCOPE_CONTEXT_DEFINITION
from services.engineering.feet_inch_filter import FEET_INCH_SEGMENT_RE

SCHEMA_VERSION = "1.0"
OCCURRENCE_SCOPE_SCHEDULE_DEFINITION = "schedule_definition"
_MIN_GRID_STRIPS = 3
_MIN_LEVEL_DATUMS = 2
_MIN_EXACT_LABELS = 3
_ROTATED = 45.0


def _page(item: Dict[str, Any]) -> int:
    source = item.get("source_text") or {}
    candidate = source.get("page_number") if isinstance(source, dict) else None
    if candidate is None:
        candidate = item.get("page_number") or item.get("page")
    try:
        return int(candidate or 0)
    except (TypeError, ValueError):
        return 0


def _bbox(item: Dict[str, Any]) -> Optional[List[float]]:
    source = item.get("source_text") or {}
    candidates = (
        source.get("bounding_box") if isinstance(source, dict) else None,
        source.get("bbox") if isinstance(source, dict) else None,
        item.get("bounding_box"),
        item.get("bbox"),
    )
    for candidate in candidates:
        if isinstance(candidate, (list, tuple)) and len(candidate) >= 4:
            try:
                return [float(value) for value in candidate[:4]]
            except (TypeError, ValueError):
                continue
    return None


def _document_id(item: Dict[str, Any], fallback: str = "") -> str:
    source = item.get("source_text") or {}
    return str(
        item.get("document_id")
        or (source.get("document_id") if isinstance(source, dict) else None)
        or fallback
        or ""
    )


def _area(box: List[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _relation(token_box: List[float], region_box: List[float]) -> str:
    """Return inside, boundary, or outside using the token centre.

    A token that straddles the region edge is deliberately ambiguous rather
    than quarantined. This is the abstention rule for uncertain boundaries.
    """

    cx = (token_box[0] + token_box[2]) / 2.0
    cy = (token_box[1] + token_box[3]) / 2.0
    centre_inside = region_box[0] < cx < region_box[2] and region_box[1] < cy < region_box[3]
    fully_inside = (
        token_box[0] >= region_box[0]
        and token_box[1] >= region_box[1]
        and token_box[2] <= region_box[2]
        and token_box[3] <= region_box[3]
    )
    if centre_inside and fully_inside:
        return "inside"
    intersects = not (
        token_box[2] <= region_box[0]
        or token_box[0] >= region_box[2]
        or token_box[3] <= region_box[1]
        or token_box[1] >= region_box[3]
    )
    return "boundary" if intersects else "outside"


def _exact_section(token: Dict[str, Any]) -> Optional[str]:
    source = token.get("source_text") or {}
    candidates = (
        token.get("section"),
        token.get("final_label"),
        token.get("normalized_text"),
        token.get("text"),
        token.get("raw_text"),
        source.get("normalized") if isinstance(source, dict) else None,
        source.get("raw") if isinstance(source, dict) else None,
    )
    for candidate in candidates:
        canonical = catalog_form(str(candidate or "").strip())
        if canonical:
            return str(canonical)
    return None


def _region_key(region: Dict[str, Any]) -> tuple:
    box = [float(value) for value in region.get("region_bbox") or region.get("bbox") or []]
    return (
        int(region.get("page_number") or region.get("page") or 0),
        _area(box) if len(box) >= 4 else float("inf"),
        str(region.get("region_id") or ""),
    )


def _normalise_region(region: Dict[str, Any], document_id: str) -> Optional[Dict[str, Any]]:
    raw_box = region.get("region_bbox") or region.get("bbox") or []
    if len(raw_box) < 4:
        return None
    try:
        box = [round(float(value), 3) for value in raw_box[:4]]
        page = int(region.get("page_number") or region.get("page") or 0)
    except (TypeError, ValueError):
        return None
    if page <= 0 or _area(box) <= 0:
        return None
    return {
        **region,
        "region_id": str(region.get("region_id") or f"p{page}-schedule"),
        "page_number": page,
        "region_bbox": box,
        "source_document_id": str(region.get("source_document_id") or document_id or ""),
        "boundary_status": str(region.get("boundary_status") or "confident"),
    }


def quarantine_tokens(
    tokens: Iterable[Dict[str, Any]],
    regions: Iterable[Dict[str, Any]],
    *,
    document_id: str = "",
) -> Dict[str, Any]:
    """Return classified token copies and deterministic decisions."""

    normalised = [
        found
        for found in (_normalise_region(region, document_id) for region in regions)
        if found is not None
    ]
    normalised.sort(key=_region_key)
    output: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    for index, original in enumerate(tokens):
        token = dict(original)
        token_box = _bbox(token)
        token_page = _page(token)
        token_document_id = _document_id(token, document_id)
        candidates: List[Dict[str, Any]] = []
        boundary: List[Dict[str, Any]] = []
        cross_document: List[Dict[str, Any]] = []
        if token_box:
            for region in normalised:
                if region["page_number"] != token_page:
                    continue
                relation = _relation(token_box, region["region_bbox"])
                if relation == "outside":
                    continue
                region_document_id = str(region.get("source_document_id") or "")
                if (
                    token_document_id
                    and region_document_id
                    and token_document_id != region_document_id
                ):
                    cross_document.append(region)
                    continue
                if region.get("boundary_status") != "confident" or relation == "boundary":
                    boundary.append(region)
                else:
                    candidates.append(region)

        token_id = str(token.get("object_id") or token.get("token_id") or index)
        if not candidates:
            reason = (
                "cross_document_region"
                if cross_document
                else "ambiguous_boundary"
                if boundary
                else "no_confident_schedule_region"
            )
            decisions.append({"token_id": token_id, "action": "unchanged", "reason": reason})
            output.append(token)
            continue

        chosen = candidates[0]  # regions are pre-sorted by _region_key
        section = _exact_section(token)
        if section is None:
            decisions.append(
                {
                    "token_id": token_id,
                    "action": "unchanged",
                    "reason": "invalid_or_incomplete_catalog_text",
                    "region_id": chosen["region_id"],
                }
            )
            output.append(token)
            continue
        if token.get("object_scope") == OBJECT_SCOPE_CONTEXT_DEFINITION:
            decisions.append(
                {
                    "token_id": token_id,
                    "action": "unchanged_context_definition",
                    "reason": "existing_context_scope_precedence",
                    "region_id": chosen["region_id"],
                }
            )
            output.append(token)
            continue

        evidence_id = "schedule-region-" + hashlib.sha256(
            "|".join(
                (
                    str(chosen.get("source_document_id") or ""),
                    str(chosen["page_number"]),
                    chosen["region_id"],
                    section,
                    str(token_box),
                )
            ).encode("utf-8")
        ).hexdigest()[:16]
        token["object_scope"] = OCCURRENCE_SCOPE_SCHEDULE_DEFINITION
        token["occurrence_scope"] = OCCURRENCE_SCOPE_SCHEDULE_DEFINITION
        token["countable_occurrence"] = False
        token["takeoff_eligible"] = False
        token["evidence_only"] = True
        token["schedule_region_provenance"] = {
            "evidence_id": evidence_id,
            "source_document_id": chosen.get("source_document_id") or token_document_id or None,
            "source_page": chosen["page_number"],
            "region_id": chosen["region_id"],
            "region_bbox": chosen["region_bbox"],
            "token_bbox": token_box,
            "section": section,
            "region_source": chosen.get("region_source"),
            "overlapping_region_ids": sorted(r["region_id"] for r in candidates),
        }
        decisions.append(
            {
                "token_id": token_id,
                "action": "quarantined",
                "reason": "exact_catalog_label_inside_confident_schedule_region",
                "region_id": chosen["region_id"],
                "section": section,
            }
        )
        output.append(token)
    return {
        "tokens": output,
        "decisions": decisions,
        "quarantined_count": sum(d["action"] == "quarantined" for d in decisions),
        "ambiguous_count": sum(d["reason"] == "ambiguous_boundary" for d in decisions),
    }


def _vertical_lines(source_path: Path, page_number: int) -> List[Tuple[float, float, float]]:
    """Vertical rulings of one page; read only for pages with a matrix header."""
    import fitz

    found: List[Tuple[float, float, float]] = []
    with fitz.open(str(source_path)) as pdf:
        for drawing in pdf[page_number - 1].get_drawings():
            for item in drawing.get("items") or []:
                if item[0] == "l" and abs(item[1].x - item[2].x) < 0.5:
                    found.append(
                        (item[1].x, min(item[1].y, item[2].y), max(item[1].y, item[2].y))
                    )
                elif item[0] == "re":
                    rect = item[1]
                    found.extend(((rect.x0, rect.y0, rect.y1), (rect.x1, rect.y0, rect.y1)))
    return found


def _compact(words: Iterable[Dict[str, Any]]) -> str:
    return "".join(str(word.get("text") or "") for word in words).replace(" ", "").upper()


def _matrix_headers(words: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    rows = schedule_grid._cluster_rows(
        [word for word in words if abs(float(word.get("rotation") or 0)) < _ROTATED]
    )
    headers: List[Dict[str, float]] = []
    for row_index, row in enumerate(rows):
        ordered = sorted(row["words"], key=lambda word: float(word["bbox"][0]))
        for start, first in enumerate(ordered):
            if not str(first.get("text") or "").upper().startswith("COL"):
                continue
            head = [
                word
                for word in ordered[start:]
                if float(word["bbox"][0]) - float(first["bbox"][0]) < 80
            ]
            stacked = [
                word
                for later in rows[row_index + 1 : row_index + 4]
                for word in later["words"]
                if abs(float(word["bbox"][0]) - float(first["bbox"][0])) < 3
                and float(word["bbox"][1]) - float(first["bbox"][3]) < 12
            ]
            if _compact(head).startswith("COLUMNLOCATIONS"):
                bottom = max(float(word["bbox"][3]) for word in head)
            elif _compact(head[:1]) == "COLUMN" and _compact(stacked).startswith("LOCATIONS"):
                bottom = max(float(word["bbox"][3]) for word in stacked)
            else:
                continue
            headers.append(
                {
                    "x": float(first["bbox"][0]),
                    "y": float(row["y"]),
                    "bottom": bottom,
                }
            )
            break
    return sorted(headers, key=lambda item: item["y"])


def _grid_lines(
    lines: List[Tuple[float, float, float]], header: Dict[str, float]
) -> List[Tuple[float, float, float]]:
    y = (header["y"] + header["bottom"]) / 2.0
    crossing = sorted(
        (line for line in lines if line[1] <= y <= line[2] and line[0] > header["x"]),
        key=lambda line: line[0],
    )
    merged: List[Tuple[float, float, float]] = []
    for line in crossing:
        if not merged or line[0] - merged[-1][0] > 3.0:
            merged.append(line)
    gaps = [b[0] - a[0] for a, b in zip(merged, merged[1:]) if b[0] - a[0] >= 20]
    if len(gaps) < _MIN_GRID_STRIPS:
        return []
    pitch = sorted(gaps)[len(gaps) // 2]
    accepted_x = {
        value
        for a, b in zip(merged, merged[1:])
        if abs((b[0] - a[0]) - pitch) <= 0.25 * pitch
        for value in (a[0], b[0])
    }
    return [line for line in merged if line[0] in accepted_x]


def _level_datum_rows(
    words: List[Dict[str, Any]], *, left: float, right: float, top: float, bottom: float
) -> List[float]:
    band = [
        word
        for word in words
        if left <= float(word["bbox"][0]) < right
        and top < float(word["bbox"][1]) < bottom
        and abs(float(word.get("rotation") or 0)) < _ROTATED
    ]
    return [
        float(row["y"])
        for row in schedule_grid._cluster_rows(band)
        if FEET_INCH_SEGMENT_RE.fullmatch(schedule_grid._text(row["words"]).strip())
    ]


def _matrix_regions(
    words: List[Dict[str, Any]],
    lines_for_page: Callable[[int], List[Tuple[float, float, float]]],
    document_id: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    confident: List[Dict[str, Any]] = []
    ambiguous: List[Dict[str, Any]] = []
    words_by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for word in words:
        if _page(word):
            words_by_page[_page(word)].append(word)
    for page, page_words in sorted(words_by_page.items()):
        previous_bottom = 0.0
        page_lines: Optional[List[Tuple[float, float, float]]] = None
        for number, header in enumerate(_matrix_headers(page_words), start=1):
            if page_lines is None:
                page_lines = lines_for_page(page)
            grid = _grid_lines(page_lines, header)
            evidence = ["column_locations_header"]
            if grid:
                evidence.append("regular_vertical_grid")
            label_right = grid[0][0] if grid else header["x"] + 1.0
            datum_rows = _level_datum_rows(
                page_words,
                left=header["x"] - 15,
                right=label_right,
                top=previous_bottom,
                bottom=header["y"],
            )
            if len(datum_rows) >= _MIN_LEVEL_DATUMS:
                evidence.append("level_datum_axis")
            exact_labels = [
                word
                for word in page_words
                if abs(float(word.get("rotation") or 0)) >= _ROTATED
                and previous_bottom < float(word["bbox"][1]) < header["y"]
                and grid
                and grid[0][0] <= (float(word["bbox"][0]) + float(word["bbox"][2])) / 2.0 <= grid[-1][0]
                and catalog_form(str(word.get("text") or ""))
            ]
            if len(exact_labels) >= _MIN_EXACT_LABELS:
                evidence.append("catalog_label_density")
            title_rows = [
                row
                for row in schedule_grid._cluster_rows(page_words)
                if previous_bottom <= float(row["y"]) <= header["bottom"]
                and "SCHEDULE" in schedule_grid._text(row["words"]).upper()
                and "NOTES" not in schedule_grid._text(row["words"]).upper()
            ]
            if title_rows:
                evidence.append("schedule_title")
            # A title is useful but not mandatory: many real sheets put the
            # words "COLUMN SCHEDULE" only in the title block, well outside
            # the matrix. The four local structural signals below are
            # independently strong and avoid coupling a region decision to
            # distant page text.
            required = {
                "column_locations_header",
                "regular_vertical_grid",
                "level_datum_axis",
                "catalog_label_density",
            }
            status = "confident" if required.issubset(evidence) else "ambiguous"
            if grid:
                top = max(previous_bottom, min(datum_rows) - 60.0) if datum_rows else previous_bottom
                bottom = header["bottom"] + 20.0
                if exact_labels:
                    left = min(float(word["bbox"][0]) for word in exact_labels) - 2.0
                    right = max(float(word["bbox"][2]) for word in exact_labels) + 2.0
                else:
                    left, right = grid[0][0], grid[-1][0]
                box = [left, top, right, bottom]
            else:
                box = [header["x"] - 6.0, previous_bottom, header["x"] + 1.0, header["bottom"]]
            region = {
                "region_id": f"p{page}-matrix-{number}",
                "page_number": page,
                "region_bbox": [round(value, 3) for value in box],
                "source_document_id": document_id,
                "boundary_status": status,
                "region_source": "column_matrix_geometry",
                "evidence": evidence,
                "exact_label_count": len(exact_labels),
            }
            (confident if status == "confident" else ambiguous).append(region)
            previous_bottom = header["bottom"] + 20.0
    return confident, ambiguous


def detect_schedule_regions(
    document: Dict[str, Any],
    *,
    source_path: Optional[Path] = None,
    vector_lines_by_page: Optional[Dict[int, List[Tuple[float, float, float]]]] = None,
) -> Dict[str, Any]:
    started = time.perf_counter()
    document_id = str(document.get("document_id") or "")
    words = list(document.get("words") or [])
    structured = schedule_grid.build_schedule_evidence(words, discovery="widened")
    regions: List[Dict[str, Any]] = []
    for region in structured.get("regions") or []:
        normalised = _normalise_region(
            {
                **region,
                "page_number": region.get("page_number") or region.get("page"),
                "source_document_id": document_id,
                "boundary_status": "confident",
                "region_source": "structured_schedule_evidence",
                "evidence": ["validated_mark_size_region"],
            },
            document_id,
        )
        if normalised:
            regions.append(normalised)
    if vector_lines_by_page is not None:
        lines_for_page = lambda page: vector_lines_by_page.get(page) or []  # noqa: E731
    elif source_path is not None:
        lines_for_page = partial(_vertical_lines, Path(source_path))
    else:
        lines_for_page = lambda page: []  # noqa: E731
    matrix, ambiguous = _matrix_regions(words, lines_for_page, document_id)
    regions.extend(matrix)
    regions.sort(key=_region_key)
    ambiguous.sort(key=_region_key)
    return {
        "regions": regions,
        "ambiguous_regions": ambiguous,
        "region_runtime_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }


def build_schedule_region_quarantine(
    document: Dict[str, Any], *, source_path: Optional[Path] = None
) -> Dict[str, Any]:
    detected = detect_schedule_regions(document, source_path=source_path)
    classified = quarantine_tokens(
        document.get("engineering_tokens") or [],
        [*detected["regions"], *detected["ambiguous_regions"]],
        document_id=str(document.get("document_id") or ""),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "shadow_only",
        "source_document_id": str(document.get("document_id") or ""),
        **detected,
        **classified,
    }
