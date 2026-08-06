"""
Layout-aware document intelligence for structural engineering PDFs.

The service enriches the existing PyMuPDF document structure without changing
the legacy text extraction contract. It performs deterministic cleanup,
hierarchy inference, table/title-block/callout detection, and emits engineering
tokens with source coordinates and extraction confidence.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence

import fitz

from services.token_extractor import extract_engineering_token_records


_DECORATIVE_RE = re.compile(r"^[\W_]{2,}$")
# Drawing callouts are short annotations that reference another view or sheet.
# Matching bare words such as "SECTION" or "SEE" also captures general notes,
# which inflated callout counts by an order of magnitude.
_CALLOUT_RE = re.compile(
    r"\b[A-Z]?\d{1,3}\s*/\s*(?:S|A|M|E)[- ]?\d{2,4}\b"
    r"|\bSEE\s+(?:DETAIL|SECTION|SHEET|PLAN|DWG|DRAWING)\b"
    r"|\bDETAIL\s+[A-Z0-9](?:[-.][A-Z0-9]{1,3})?\b"
    r"|\bSECTION\s+[A-Z]\s*[-–]\s*[A-Z]\b"
    r"|\b(?:TYP|SIM)\.?$",
    re.IGNORECASE,
)
# Dimension annotations use feet-inch notation or an explicit unit suffix.
# A bare "M" unit matched ordinary prose, so it is excluded.
_DIMENSION_RE = re.compile(
    r"\d{1,4}\s*['′]\s*-?\s*\d{0,2}(?:\s+\d+/\d+)?\s*[\"″]?"
    r"|\d{1,4}(?:\.\d+)?(?:\s+\d+/\d+)?\s*[\"″]"
    r"|\d{1,4}(?:\.\d+)?\s*(?:MM|CM|FT|IN)\b",
    re.IGNORECASE,
)
# Prose blocks (notes, specifications, legends) never become layout objects.
_PROSE_RE = re.compile(
    r"\b(?:NOTES?|SPECIFICATIONS?|GENERAL|LEGEND|REVISIONS?|"
    r"SHALL|CONTRACTOR|ACCORDANCE|ASTM|AISC\s+SPECIFICATION)\b",
    re.IGNORECASE,
)


def _is_prose(text: str) -> bool:
    """Detect note/specification text that must not become a layout object."""

    cleaned = str(text or "").strip()
    return (
        len(cleaned) > 110
        or len(cleaned.split()) > 16
        or bool(_PROSE_RE.search(cleaned))
    )


def _layout_objects(
    lines: List[dict],
    pattern: re.Pattern[str],
    *,
    id_prefix: str,
    id_field: str,
) -> List[dict]:
    """Collect deduplicated short annotations matching a layout pattern."""

    objects: List[dict] = []
    seen: set[tuple] = set()
    for line in lines:
        text = str(line.get("text") or "").strip()
        if not text or _is_prose(text) or not pattern.search(text):
            continue
        bbox = line.get("bbox") or [0, 0, 0, 0]
        key = (
            line.get("page_number"),
            re.sub(r"\s+", "", text.upper()),
            tuple(round(float(value), 1) for value in bbox),
        )
        if key in seen:
            continue
        seen.add(key)
        objects.append(
            {
                id_field: f"{id_prefix}_{line['object_id']}",
                "page_number": line["page_number"],
                "bbox": bbox,
                "text": text,
                "source_line_id": line["object_id"],
            }
        )
    return objects


def _bbox_area(bbox: Sequence[float]) -> float:
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(
        0.0, float(bbox[3]) - float(bbox[1])
    )


def _intersection_ratio(a: Sequence[float], b: Sequence[float]) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return ((x1 - x0) * (y1 - y0)) / max(min(_bbox_area(a), _bbox_area(b)), 1.0)


def repair_ocr_text(text: str) -> tuple[str, List[str]]:
    """
    Apply conservative OCR cleanup without guessing a final steel shape.

    Shape correction remains the responsibility of the correction/fusion
    engines, where AISC and spatial evidence are available.
    """

    original = str(text or "")
    repaired = (
        original.replace("\u00a0", " ")
        .replace("×", "X")
        .replace("✕", "X")
        .replace("–", "-")
        .replace("—", "-")
    )
    repaired = re.sub(r"(?<=\w)\s+X\s+(?=\w)", "X", repaired, flags=re.I)
    repaired = re.sub(r"(?<=\d)\s*/\s*(?=\d)", "/", repaired)
    # Frequent OCR substitutions only where neighboring characters make the
    # intent unambiguous; exact section correction remains a model concern.
    repaired = re.sub(r"(?<=[A-Z])O(?=\d)", "0", repaired, flags=re.I)
    repaired = re.sub(r"(?<=\d)O(?=\d)", "0", repaired, flags=re.I)
    repaired = re.sub(r"(?<=\d)[|I](?=\d)", "1", repaired)
    repaired = re.sub(r"[ \t]+", " ", repaired).strip()
    changes: List[str] = []
    if repaired != original.strip():
        changes.append("normalized_ocr_spacing_and_symbols")
    return repaired, changes


def _reading_order_key(item: dict) -> tuple:
    """Stable layout order for horizontal and rotated drawing text."""

    bbox = item.get("bbox") or [0, 0, 0, 0]
    rotation = abs(float(item.get("rotation") or 0.0)) % 180
    if 55 <= rotation <= 125:
        return (
            int(item.get("page_number") or 0),
            round(float(bbox[0]), 1),
            round(float(bbox[1]), 1),
        )
    return (
        int(item.get("page_number") or 0),
        round(float(bbox[1]), 1),
        round(float(bbox[0]), 1),
    )


def _assign_reading_order(items: List[dict]) -> None:
    for index, item in enumerate(sorted(items, key=_reading_order_key)):
        item["reading_order"] = index


def _font_for_word(word: dict, lines: Iterable[dict]) -> Dict[str, Any]:
    best: Dict[str, Any] = {"font": None, "font_size": None, "rotation": 0.0}
    best_overlap = 0.0
    for line in lines:
        if line.get("page_number") != word.get("page_number"):
            continue
        overlap = _intersection_ratio(word["bbox"], line["bbox"])
        if overlap <= best_overlap:
            continue
        best_overlap = overlap
        spans = line.get("spans") or []
        span = max(
            spans,
            key=lambda item: _intersection_ratio(
                word["bbox"], item.get("bbox") or line["bbox"]
            ),
            default={},
        )
        best = {
            "font": span.get("font"),
            "font_size": span.get("font_size", line.get("font_size")),
            "rotation": span.get("rotation", line.get("rotation", 0.0)),
        }
    return best


def _text_confidence(word: dict) -> float:
    """Score how reliably a word was recovered from the page.

    Repeated text is not penalized: a member label legitimately appears on
    every framing bay it applies to.
    """

    text = str(word.get("text") or "")
    score = 0.45
    if len(text) >= 2:
        score += 0.12
    if word.get("font_size"):
        score += 0.12
    if word.get("line_id"):
        score += 0.1
    if word.get("block_id"):
        score += 0.08
    if word.get("ocr_repairs"):
        score -= 0.05
    if _DECORATIVE_RE.fullmatch(text):
        score -= 0.35
    return round(max(0.05, min(0.99, score)), 4)


def _infer_hierarchy(blocks: List[dict]) -> None:
    sizes = [
        float(block["font_size"])
        for block in blocks
        if block.get("font_size") is not None
    ]
    if not sizes:
        return
    ordered = sorted(sizes)
    median = ordered[len(ordered) // 2]
    for block in blocks:
        size = float(block.get("font_size") or median)
        text = str(block.get("text") or "").strip()
        if size >= median * 1.55 and len(text) < 100:
            role = "heading"
        elif size >= median * 1.2 and len(text) < 140:
            role = "subheading"
        elif _CALLOUT_RE.search(text):
            role = "callout"
        else:
            role = "body"
        block["hierarchy_role"] = role


def _extract_tables(page_number: int, lines: List[dict]) -> List[dict]:
    """Detect schedule regions from already-extracted lines in bounded time."""

    page_lines = [
        line for line in lines if line.get("page_number") == page_number
    ]
    page_text = "\n".join(
        str(line.get("text") or "") for line in page_lines
    ).upper()
    table_hints = (
        "SCHEDULE",
        "TAKEOFF",
        "QUANTITY",
        "QTY",
        "MEMBER SIZE",
        "BEAM MARK",
        "COLUMN MARK",
    )
    if not any(hint in page_text for hint in table_hints):
        return []

    relevant = [
        line
        for line in page_lines
        if str(line.get("text") or "").strip()
    ]
    if not relevant:
        return []
    x0 = min(float(line["bbox"][0]) for line in relevant)
    y0 = min(float(line["bbox"][1]) for line in relevant)
    x1 = max(float(line["bbox"][2]) for line in relevant)
    y1 = max(float(line["bbox"][3]) for line in relevant)
    row_texts = [str(line.get("text") or "").strip() for line in relevant]
    header_index = next(
        (
            index
            for index, text in enumerate(row_texts)
            if any(hint in text.upper() for hint in table_hints)
        ),
        0,
    )
    takeoff = any(
        hint in page_text
        for hint in ("SHAPE", "QTY", "QUANTITY", "LENGTH", "WEIGHT")
    )
    return [
        {
            "table_id": f"table_p{page_number}_0",
            "page_number": page_number,
            "bbox": [round(value, 2) for value in (x0, y0, x1, y1)],
            "header": [row_texts[header_index]],
            "rows": [[text] for text in row_texts[:500]],
            "row_count": min(len(row_texts), 500),
            "column_count": 1,
            "table_type": "takeoff" if takeoff else "engineering",
            "confidence": 0.72 if takeoff else 0.62,
            "detection_method": "layout_lines",
        }
    ]


def _extract_schedules(tables: List[dict], lines: List[dict]) -> List[dict]:
    schedules: List[dict] = []
    schedule_re = re.compile(
        r"\b(?:BEAM|COLUMN|MEMBER|STEEL|JOIST|DECK|CONNECTION)?\s*SCHEDULE\b",
        re.IGNORECASE,
    )
    for table in tables:
        text = "\n".join(
            str(cell)
            for row in (table.get("rows") or [])
            for cell in row
        )
        if schedule_re.search(text) or table.get("table_type") == "takeoff":
            schedules.append(
                {
                    "schedule_id": f"schedule_{table['table_id']}",
                    "page_number": table["page_number"],
                    "bbox": table["bbox"],
                    "table_id": table["table_id"],
                    "text": text[:4000],
                    "confidence": table.get("confidence", 0.6),
                    "schedule_type": (
                        schedule_re.search(text).group(0).strip().lower()
                        if schedule_re.search(text)
                        else "takeoff"
                    ),
                }
            )
    # Preserve schedule headings even when a full table was not detected.
    existing_pages = {item["page_number"] for item in schedules}
    for line in lines:
        if not schedule_re.search(str(line.get("text") or "")):
            continue
        if line.get("page_number") in existing_pages:
            continue
        schedules.append(
            {
                "schedule_id": f"schedule_{line['object_id']}",
                "page_number": line["page_number"],
                "bbox": line["bbox"],
                "table_id": None,
                "text": line["text"],
                "confidence": 0.55,
                "schedule_type": "schedule_heading",
            }
        )
    return schedules


def build_extraction_diagnostics(
    *,
    document: Dict[str, Any],
    tokens: List[dict],
    word_count_before_cleanup: int,
    word_count_after_cleanup: int,
    ocr_repairs: int,
    tables: List[dict],
    schedules: List[dict],
    callouts: List[dict],
    dimensions: List[dict],
    title_blocks: List[dict],
) -> Dict[str, Any]:
    status_counts = Counter(
        token.get("extraction_status") or "INVALID" for token in tokens
    )
    issue_counts = Counter(
        issue
        for token in tokens
        for issue in (token.get("diagnostics") or {}).get("issues", [])
    )
    confidences = [float(token.get("confidence") or 0.0) for token in tokens]
    average = sum(confidences) / max(len(confidences), 1)
    valid_ratio = (
        (status_counts["VALID"] + 0.6 * status_counts["SUSPICIOUS"])
        / max(len(tokens), 1)
    )
    document_score = max(0.0, min(1.0, 0.55 * average + 0.45 * valid_ratio))
    if not tokens:
        grade = "INVALID"
    elif document_score >= 0.82:
        grade = "VALID"
    elif document_score >= 0.65:
        grade = "SUSPICIOUS"
    elif document_score >= 0.4:
        grade = "BROKEN"
    else:
        grade = "INVALID"

    page_diagnostics = []
    for page in document.get("pages") or []:
        page_number = page["page_number"]
        page_tokens = [t for t in tokens if t.get("page") == page_number]
        page_diagnostics.append(
            {
                "page": page_number,
                "token_count": len(page_tokens),
                "average_confidence": round(
                    sum(float(t.get("confidence") or 0) for t in page_tokens)
                    / max(len(page_tokens), 1),
                    4,
                ),
                "rotated_tokens": sum(
                    abs(float(t.get("rotation") or 0)) > 2 for t in page_tokens
                ),
                "broken_tokens": sum(
                    t.get("extraction_status") in {"BROKEN", "INVALID"}
                    for t in page_tokens
                ),
                "rich_extraction": bool(page.get("rich_extraction")),
            }
        )

    return {
        "status": grade,
        "score": round(document_score, 4),
        "average_token_confidence": round(average, 4),
        "status_counts": {
            status: int(status_counts.get(status, 0))
            for status in ("VALID", "SUSPICIOUS", "BROKEN", "INVALID")
        },
        "issue_counts": dict(issue_counts),
        "token_count": len(tokens),
        "word_count_before_cleanup": int(word_count_before_cleanup),
        "word_count_after_cleanup": int(word_count_after_cleanup),
        "noise_removed": max(
            0, int(word_count_before_cleanup) - int(word_count_after_cleanup)
        ),
        "ocr_repairs": int(ocr_repairs),
        "split_labels_reconstructed": sum(bool(t.get("was_merged")) for t in tokens),
        "repeated_labels": sum(
            1 for count in Counter(t["normalized_text"] for t in tokens).values()
            if count > 1
        ),
        "rotated_tokens": sum(abs(float(t.get("rotation") or 0)) > 2 for t in tokens),
        "layout": {
            "tables": len(tables),
            "schedules": len(schedules),
            "callouts": len(callouts),
            "dimensions": len(dimensions),
            "title_blocks": len(title_blocks),
        },
        "pages": page_diagnostics,
        "warnings": [
            message
            for condition, message in (
                (not tokens, "No engineering tokens extracted"),
                (status_counts["INVALID"] > 0, "Invalid token extractions require review"),
                (
                    status_counts["BROKEN"] > max(2, len(tokens) * 0.15),
                    "High broken-token rate",
                ),
                (
                    any(not page["rich_extraction"] for page in page_diagnostics),
                    "One or more pages did not receive rich extraction",
                ),
            )
            if condition
        ],
    }


def _title_blocks(page: dict, blocks: List[dict]) -> List[dict]:
    width, height = float(page["width"]), float(page["height"])
    candidates: List[dict] = []
    for block in blocks:
        if block.get("page_number") != page.get("page_number"):
            continue
        x0, y0, x1, y1 = block["bbox"]
        in_lower_band = y0 >= height * 0.72
        in_right_band = x0 >= width * 0.62
        text = str(block.get("text") or "")
        has_title_hint = bool(
            re.search(
                r"\b(?:PROJECT|DRAWING|SHEET|TITLE|REVISION|SCALE|DATE|DESIGNED|DRAWN)\b",
                text,
                re.IGNORECASE,
            )
        )
        if (in_lower_band and in_right_band) or has_title_hint:
            candidates.append(
                {
                    "title_block_id": f"title_{block['object_id']}",
                    "page_number": page["page_number"],
                    "bbox": block["bbox"],
                    "text": text,
                    "source_block_id": block["object_id"],
                    "confidence": 0.88 if has_title_hint else 0.65,
                }
            )
    return candidates


def enrich_document_structure(
    pdf_path: str,
    document: Dict[str, Any],
) -> Dict[str, Any]:
    """Add layout semantics and metadata-rich engineering tokens in-place."""

    words = document.get("words") or []
    lines = document.get("lines") or []
    blocks = document.get("blocks") or []
    _infer_hierarchy(blocks)

    line_by_numbers = {
        (
            line.get("page_number"),
            line.get("block_no"),
            line.get("line_no"),
        ): line
        for line in lines
    }
    block_by_id = {block["object_id"]: block for block in blocks}

    filtered_words: List[dict] = []
    for word in words:
        repaired, changes = repair_ocr_text(word.get("text", ""))
        word["raw_text"] = word.get("text", "")
        word["text"] = repaired
        line = line_by_numbers.get(
            (
                word.get("page_number"),
                word.get("block_no"),
                word.get("line_no"),
            )
        )
        if line:
            word["line_id"] = line.get("object_id")
            word["block_id"] = line.get("block_id")
            spans = line.get("spans") or []
            span = max(
                spans,
                key=lambda item: _intersection_ratio(
                    word["bbox"], item.get("bbox") or line["bbox"]
                ),
                default={},
            )
            word.update(
                {
                    "font": span.get("font"),
                    "font_size": span.get(
                        "font_size", line.get("font_size")
                    ),
                    "rotation": span.get(
                        "rotation", line.get("rotation", 0.0)
                    ),
                }
            )
        block = block_by_id.get(word.get("block_id"))
        word["hierarchy_role"] = (block or {}).get("hierarchy_role", "body")
        word["ocr_repairs"] = changes
        word["is_decorative"] = bool(_DECORATIVE_RE.fullmatch(repaired))
        word["confidence"] = _text_confidence(word)
        if repaired and not word["is_decorative"]:
            filtered_words.append(word)

    _assign_reading_order(filtered_words)
    _assign_reading_order(lines)
    _assign_reading_order(blocks)

    annotations: List[dict] = []
    tables: List[dict] = []
    with fitz.open(pdf_path) as source:
        from services.pdf_pages import iter_pdf_pages

        for page_index, fitz_page in iter_pdf_pages(source):
            page_number = page_index + 1
            tables.extend(_extract_tables(page_number, lines))
            try:
                for index, annotation in enumerate(fitz_page.annots() or []):
                    annotations.append(
                        {
                            "annotation_id": f"annotation_p{page_number}_{index}",
                            "page_number": page_number,
                            "type": annotation.type[1],
                            "bbox": [
                                round(float(value), 2)
                                for value in annotation.rect
                            ],
                            "content": (annotation.info or {}).get("content"),
                            "title": (annotation.info or {}).get("title"),
                        }
                    )
            except RuntimeError:
                continue

    callouts = _layout_objects(
        lines, _CALLOUT_RE, id_prefix="callout", id_field="callout_id"
    )
    dimensions = _layout_objects(
        lines, _DIMENSION_RE, id_prefix="dimension", id_field="dimension_id"
    )
    title_blocks = [
        title
        for page in document.get("pages") or []
        for title in _title_blocks(page, blocks)
    ]
    schedules = _extract_schedules(tables, lines)
    tokens = extract_engineering_token_records(
        filtered_words,
        lines=lines,
        blocks=blocks,
    )

    document["words"] = filtered_words
    document["tables"] = tables
    document["title_blocks"] = title_blocks
    document["schedules"] = schedules
    document["callouts"] = callouts
    document["dimensions"] = dimensions
    document["annotations"] = annotations
    document["engineering_tokens"] = tokens
    document["object_counts"].update(
        {
            "tables": len(tables),
            "title_blocks": len(title_blocks),
            "schedules": len(schedules),
            "callouts": len(callouts),
            "dimensions": len(dimensions),
            "annotations": len(annotations),
            "engineering_tokens": len(tokens),
        }
    )
    diagnostics = build_extraction_diagnostics(
        document=document,
        tokens=tokens,
        word_count_before_cleanup=len(words),
        word_count_after_cleanup=len(filtered_words),
        ocr_repairs=sum(bool(word.get("ocr_repairs")) for word in filtered_words),
        tables=tables,
        schedules=schedules,
        callouts=callouts,
        dimensions=dimensions,
        title_blocks=title_blocks,
    )
    document["extraction_diagnostics"] = diagnostics
    document["extraction_quality"] = {
        **diagnostics,
        "decorative_words_removed": len(words) - len(filtered_words),
        "duplicate_tokens_removed": sum(
            max(0, count - 1)
            for count in Counter(token["normalized_text"] for token in tokens).values()
        ),
    }
    return document
