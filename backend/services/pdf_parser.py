"""
PDF Parsing
===========

Backward-compatible text extraction plus a rich document structure parser
used by the Engineering Validation / Takeoff pipeline.

Public APIs
-----------
extract_text_from_pdf(pdf_path) -> dict
    Legacy API. Returns pages, concatenated text, and text_length.
    Signature and return keys are stable for existing upload/token flows.

extract_document_structure(pdf_path, *, persist_json=None) -> dict
    Rich JSON document model with words, lines, blocks, neighbors,
    drawing references, layers, object IDs, and reading order.

parse_pdf(pdf_path) -> dict
    Convenience wrapper that returns both legacy text fields and the
    full ``document`` structure.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import fitz


_ENGINEERING_PAGE_RE = re.compile(
    r"\b(?:W|WF|WT|HSS|TS|PIPE|HP|MC|C|L|2L|PL)\s*[-_]?\s*"
    r"\d+(?:\.\d+)?(?:\s*[X×]\s*(?:\d+(?:\.\d+)?|\d+/\d+)){0,3}\b"
    r"|\b(?:A|F)\d{3,4}M?\b"
    r"|\b(?:BEAM|COLUMN|BRACE|STEEL|MEMBER)\s+SCHEDULE\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Backward-compatible API (do not change return shape)
# ---------------------------------------------------------------------------


def extract_text_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """Extract plain text from a PDF. Preserved for existing callers."""

    from services.pdf_pages import collect_page_texts

    with fitz.open(pdf_path) as document:
        page_texts, _skipped = collect_page_texts(document)
        full_text = "\n".join(page_texts)
        page_count = document.page_count
        return {
            "pages": page_count,
            "text": full_text,
            "text_length": len(full_text),
        }


# ---------------------------------------------------------------------------
# Rich document structure
# ---------------------------------------------------------------------------


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _round_bbox(bbox: Sequence[float], ndigits: int = 2) -> List[float]:
    return [round(float(v), ndigits) for v in bbox]


def _center(bbox: Sequence[float]) -> List[float]:
    x0, y0, x1, y1 = bbox
    return [round((x0 + x1) / 2.0, 2), round((y0 + y1) / 2.0, 2)]


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _bbox_intersects(a: Sequence[float], b: Sequence[float], pad: float = 0.0) -> bool:
    return not (
        a[2] + pad < b[0]
        or b[2] + pad < a[0]
        or a[3] + pad < b[1]
        or b[3] + pad < a[1]
    )


def _layer_names(doc: fitz.Document) -> List[str]:
    """Return optional content group (layer) names when available."""

    try:
        ocgs = doc.get_ocgs() or {}
        names: List[str] = []
        for info in ocgs.values():
            name = (info or {}).get("name")
            if name:
                names.append(str(name))
        return names
    except Exception:  # pragma: no cover - PyMuPDF version variance
        return []


_DRAWING_REF_RE = re.compile(
    r"\bS-\d+\b|\bDWG[-\s]?\d+\b|\bSHT[-\s]?\d+\b|\bDET[-\s]?\d+\b|\bA-\d+\b",
    re.IGNORECASE,
)
_HAS_DIGIT_RE = re.compile(r"\d")


def _drawing_ref_hints(text: str) -> List[str]:
    """Heuristic drawing / sheet references inside text (e.g. S-101, DWG-12).

    Called once per word, line, block, and page, so the pattern is compiled
    once and text without a digit is rejected before any scanning.
    """

    value = str(text or "")
    if not _HAS_DIGIT_RE.search(value):
        return []
    seen = set()
    ordered: List[str] = []
    for item in _DRAWING_REF_RE.findall(value):
        key = item.upper().replace(" ", "")
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def _span_rotation(span: dict) -> float:
    """Derive rotation degrees from span direction vector when present."""

    direction = span.get("dir")
    if not direction or len(direction) < 2:
        return 0.0
    dx, dy = float(direction[0]), float(direction[1])
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return 0.0
    return round(math.degrees(math.atan2(dy, dx)), 2)


def _extract_page_text_objects(
    page: fitz.Page,
    page_number: int,
    *,
    textpage: Any = None,
) -> Dict[str, List[dict]]:
    """Extract words, lines, blocks with layout metadata from one page.

    A prepared ``textpage`` is reused across the words and dict passes; parsing
    the text layer once per page instead of three times is the single largest
    saving on drawing sets.
    """

    words_out: List[dict] = []
    lines_out: List[dict] = []
    blocks_out: List[dict] = []

    # Words with bbox (x0, y0, x1, y1, word, block_no, line_no, word_no)
    raw_words = page.get_text("words", textpage=textpage) or []
    for idx, w in enumerate(raw_words):
        if len(w) < 5:
            continue
        bbox = _round_bbox(w[:4])
        text = str(w[4])
        word_id = _new_id("word")
        words_out.append(
            {
                "object_id": word_id,
                "type": "word",
                "text": text,
                "bbox": bbox,
                "center": _center(bbox),
                "page_number": page_number,
                "reading_order": idx,
                "block_no": int(w[5]) if len(w) > 5 else None,
                "line_no": int(w[6]) if len(w) > 6 else None,
                "word_no": int(w[7]) if len(w) > 7 else None,
                "font_size": None,
                "rotation": 0.0,
                "layer": None,
                "drawing_references": _drawing_ref_hints(text),
                "neighbors": [],
            }
        )

    raw = page.get_text("dict", textpage=textpage) or {}
    reading_order = 0
    for block_number, block in enumerate(raw.get("blocks") or []):
        if block.get("type", 0) != 0:
            continue  # skip image blocks here
        block_id = _new_id("block")
        block_bbox = _round_bbox(block.get("bbox") or [0, 0, 0, 0])
        block_text_parts: List[str] = []
        font_sizes: List[float] = []
        rotations: List[float] = []

        for line_number, line in enumerate(block.get("lines") or []):
            line_id = _new_id("line")
            line_bbox = _round_bbox(line.get("bbox") or [0, 0, 0, 0])
            spans_out: List[dict] = []
            line_text_parts: List[str] = []
            for span in line.get("spans") or []:
                span_text = str(span.get("text") or "")
                if not span_text.strip():
                    continue
                span_bbox = _round_bbox(span.get("bbox") or line_bbox)
                size = float(span.get("size") or 0.0)
                rot = _span_rotation(span)
                font_sizes.append(size)
                rotations.append(rot)
                line_text_parts.append(span_text)
                spans_out.append(
                    {
                        "text": span_text,
                        "bbox": span_bbox,
                        "font": span.get("font"),
                        "font_size": round(size, 2),
                        "rotation": rot,
                        "color": span.get("color"),
                        "flags": span.get("flags"),
                    }
                )

            line_text = "".join(line_text_parts)
            if not line_text.strip():
                continue
            block_text_parts.append(line_text)
            avg_size = round(sum(font_sizes[-len(spans_out) :] or [0.0]) / max(len(spans_out), 1), 2)
            avg_rot = round(sum(rotations[-len(spans_out) :] or [0.0]) / max(len(spans_out), 1), 2)
            lines_out.append(
                {
                    "object_id": line_id,
                    "type": "text_line",
                    "text": line_text,
                    "bbox": line_bbox,
                    "center": _center(line_bbox),
                    "page_number": page_number,
                    "reading_order": reading_order,
                    "block_no": block_number,
                    "line_no": line_number,
                    "font_size": avg_size,
                    "rotation": avg_rot,
                    "spans": spans_out,
                    "block_id": block_id,
                    "layer": None,
                    "drawing_references": _drawing_ref_hints(line_text),
                    "neighbors": [],
                }
            )
            reading_order += 1

        block_text = "\n".join(block_text_parts).strip()
        if not block_text:
            continue
        blocks_out.append(
            {
                "object_id": block_id,
                "type": "text_block",
                "text": block_text,
                "bbox": block_bbox,
                "center": _center(block_bbox),
                "page_number": page_number,
                "reading_order": len(blocks_out),
                "block_no": block_number,
                "font_size": round(sum(font_sizes) / max(len(font_sizes), 1), 2) if font_sizes else None,
                "rotation": round(sum(rotations) / max(len(rotations), 1), 2) if rotations else 0.0,
                "layer": None,
                "drawing_references": _drawing_ref_hints(block_text),
                "neighbors": [],
                "line_ids": [ln["object_id"] for ln in lines_out if ln.get("block_id") == block_id],
            }
        )

    return {"words": words_out, "lines": lines_out, "blocks": blocks_out}


def _attach_neighbors(
    objects: List[dict],
    *,
    max_neighbors: int = 5,
    max_distance: float = 120.0,
) -> None:
    """
    Attach nearest same-page neighbors using a spatial grid.

    The previous all-pairs implementation was O(n²) and caused real drawings
    with thousands of words to appear to hang. This stays near O(n).
    """

    by_page: Dict[int, List[dict]] = {}
    for obj in objects:
        by_page.setdefault(int(obj["page_number"]), []).append(obj)

    cell_size = max(1.0, max_distance)
    for page_objs in by_page.values():
        grid: Dict[Tuple[int, int], List[dict]] = {}
        for obj in page_objs:
            center = obj.get("center") or [0.0, 0.0]
            cell = (
                int(float(center[0]) // cell_size),
                int(float(center[1]) // cell_size),
            )
            grid.setdefault(cell, []).append(obj)

        for obj in page_objs:
            scored: List[Tuple[float, dict]] = []
            center = obj.get("center") or [0.0, 0.0]
            cx = int(float(center[0]) // cell_size)
            cy = int(float(center[1]) // cell_size)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in grid.get((cx + dx, cy + dy), []):
                        if other["object_id"] == obj["object_id"]:
                            continue
                        dist = _distance(center, other["center"])
                        if dist <= max_distance:
                            scored.append((dist, other))
            scored.sort(key=lambda item: item[0])
            obj["neighbors"] = [
                {
                    "object_id": other["object_id"],
                    "distance": round(dist, 2),
                    "text": other.get("text", "")[:80],
                    "intersects": _bbox_intersects(obj["bbox"], other["bbox"]),
                }
                for dist, other in scored[:max_neighbors]
            ]


def _attach_word_neighbors(words: List[dict], *, max_neighbors: int = 4) -> None:
    """Attach adjacent reading-order words without all-pairs spatial work."""

    by_line: Dict[Tuple[int, int, int], List[dict]] = {}
    for word in words:
        key = (
            int(word.get("page_number") or 0),
            int(word.get("block_no") or 0),
            int(word.get("line_no") or 0),
        )
        by_line.setdefault(key, []).append(word)
    for line_words in by_line.values():
        line_words.sort(key=lambda item: int(item.get("reading_order") or 0))
        for index, word in enumerate(line_words):
            start = max(0, index - max_neighbors // 2)
            stop = min(len(line_words), index + max_neighbors // 2 + 1)
            word["neighbors"] = [
                {
                    "object_id": other["object_id"],
                    "distance": round(
                        _distance(word["center"], other["center"]), 2
                    ),
                    "text": other.get("text", "")[:80],
                    "intersects": _bbox_intersects(
                        word["bbox"], other["bbox"]
                    ),
                }
                for other in line_words[start:stop]
                if other["object_id"] != word["object_id"]
            ]


def extract_document_structure(
    pdf_path: str,
    *,
    persist_json: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Extract a rich, JSON-serializable PDF document model.

    Includes words, lines, text blocks, font size, rotation, page number,
    reading order, neighbors, drawing references, layers (when available),
    and stable object IDs.
    """

    from services.pdf_pages import iter_pdf_pages

    path = Path(pdf_path)
    with fitz.open(str(path)) as document:
        layers = _layer_names(document)
        pages_out: List[dict] = []
        all_words: List[dict] = []
        all_lines: List[dict] = []
        all_blocks: List[dict] = []
        page_count = int(document.page_count or 0)
        page_texts: List[str] = [""] * page_count
        page_scores: List[int] = [0] * page_count
        skipped_pages: List[dict] = []
        loaded_indices: set[int] = set()

        for page_index, page in iter_pdf_pages(document, skipped=skipped_pages):
            page_number = page_index + 1
            try:
                textpage = page.get_textpage()
                page_text = page.get_text(textpage=textpage) or ""
            except Exception as exc:  # pragma: no cover - defensive
                skipped_pages.append(
                    {
                        "page_index": page_index,
                        "page_number": page_number,
                        "error": f"get_text failed: {type(exc).__name__}: {exc}",
                    }
                )
                continue

            page_texts[page_index] = page_text
            page_scores[page_index] = len(_ENGINEERING_PAGE_RE.findall(page_text))
            loaded_indices.add(page_index)
            try:
                extracted = _extract_page_text_objects(
                    page, page_number, textpage=textpage
                )
                rich_page = True
            except Exception as exc:  # pragma: no cover - defensive
                skipped_pages.append(
                    {
                        "page_index": page_index,
                        "page_number": page_number,
                        "error": f"rich extract failed: {type(exc).__name__}: {exc}",
                    }
                )
                extracted = {"words": [], "lines": [], "blocks": []}
                rich_page = False

            all_words.extend(extracted["words"])
            all_lines.extend(extracted["lines"])
            all_blocks.extend(extracted["blocks"])

            annot_layers: List[str] = []
            try:
                for annot in page.annots() or []:
                    info = annot.info or {}
                    title = info.get("title") or info.get("content")
                    if title:
                        annot_layers.append(str(title))
            except Exception:  # pragma: no cover
                pass

            pages_out.append(
                {
                    "page_number": page_number,
                    "width": round(float(page.rect.width), 2),
                    "height": round(float(page.rect.height), 2),
                    "rotation": int(page.rotation or 0),
                    "text_length": len(page_text),
                    "word_count": len(extracted["words"]),
                    "line_count": len(extracted["lines"]),
                    "block_count": len(extracted["blocks"]),
                    "annotation_layers": annot_layers,
                    "drawing_references": _drawing_ref_hints(page_text),
                    "rich_extraction": rich_page,
                    "engineering_relevance_score": page_scores[page_index],
                    "unreadable": False,
                }
            )

        skipped_by_index = {item["page_index"]: item for item in skipped_pages}
        for page_index in range(page_count):
            if page_index in loaded_indices:
                continue
            item = skipped_by_index.get(page_index, {})
            pages_out.append(
                {
                    "page_number": page_index + 1,
                    "width": 0,
                    "height": 0,
                    "rotation": 0,
                    "text_length": 0,
                    "word_count": 0,
                    "line_count": 0,
                    "block_count": 0,
                    "annotation_layers": [],
                    "drawing_references": [],
                    "rich_extraction": False,
                    "engineering_relevance_score": 0,
                    "unreadable": True,
                    "error": item.get("error") or "unreadable page",
                }
            )

        pages_out.sort(key=lambda item: int(item.get("page_number") or 0))
        relevant_indices = [
            index for index, score in enumerate(page_scores) if score > 0
        ]
        _attach_word_neighbors(all_words)
        _attach_neighbors(all_lines)
        _attach_neighbors(all_blocks)

        full_text = "\n".join(page_texts)
        unique_skipped = len({item["page_index"] for item in skipped_pages})
        structure: Dict[str, Any] = {
            "document_id": _new_id("doc"),
            "source_path": str(path),
            "source_file": path.name,
            "page_count": page_count,
            "readable_page_count": page_count - unique_skipped,
            "skipped_page_count": unique_skipped,
            "skipped_pages": skipped_pages,
            "rich_page_count": len(loaded_indices),
            "relevant_page_count": len(relevant_indices),
            "rich_page_limit_applied": False,
            "layers": layers,
            "pages": pages_out,
            "words": all_words,
            "lines": all_lines,
            "blocks": all_blocks,
            "text": full_text,
            "text_length": len(full_text),
            "object_counts": {
                "words": len(all_words),
                "lines": len(all_lines),
                "blocks": len(all_blocks),
            },
            "drawing_references": _drawing_ref_hints(full_text),
        }


    # Add engineering layout semantics while preserving every existing field.
    from services.document_intelligence import enrich_document_structure

    structure = enrich_document_structure(str(path), structure)

    if persist_json:
        out = Path(persist_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(structure, indent=2), encoding="utf-8")
        structure["persisted_json"] = str(out)

    return structure


def parse_pdf(
    pdf_path: str,
    *,
    persist_json: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Combined parse: legacy text fields plus rich ``document`` structure.

    Keeps upload callers able to use top-level pages/text/text_length while
    also exposing the full structured model.
    """

    document = extract_document_structure(pdf_path, persist_json=persist_json)
    return {
        "pages": document["page_count"],
        "text": document["text"],
        "text_length": document["text_length"],
        "document": document,
    }
