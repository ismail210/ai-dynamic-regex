"""Thin adapter from the existing PyMuPDF-based extractor to canonical
``TextPrimitive`` objects (Section 19).

Reuses ``services.pdf_parser.extract_document_structure`` -- the repo's
existing PyMuPDF word/line/block extraction with bbox/font/rotation
already captured (verified this session; see docs/ghx_geometry_audit.md /
the earlier codebase audit) -- rather than opening the PDF a second time.
No OCR is wired in here: every real project in this system's own benchmark
corpus is natively vector/text (verified this session), so a real OCR
dependency stays out of the critical path until page classification below
actually finds a page that needs it (Section 57: do not OCR every page).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from services.semantic_preprocessor.models import (
    IMAGE_DOMINANT,
    NATIVE_TEXT_GARBLED,
    NATIVE_TEXT_HEALTHY,
    NO_NATIVE_TEXT,
    UNKNOWN_PAGE_CLASS,
    TextPrimitive,
)


def classify_page(page_stats: Dict[str, Any]) -> str:
    if page_stats.get("unreadable"):
        return NO_NATIVE_TEXT
    word_count = page_stats.get("word_count") or 0
    text_length = page_stats.get("text_length") or 0
    if word_count > 0 and page_stats.get("rich_extraction"):
        return NATIVE_TEXT_HEALTHY
    if text_length > 0 and not page_stats.get("rich_extraction"):
        return NATIVE_TEXT_GARBLED
    if word_count == 0 and text_length == 0:
        return IMAGE_DOMINANT
    return UNKNOWN_PAGE_CLASS


def build_text_primitives(structure: Dict[str, Any]) -> Tuple[List[TextPrimitive], Dict[int, str]]:
    """Convert an ``extract_document_structure`` result into TextPrimitives.

    Returns (primitives, page_classes) so callers can decide whether a given
    page's primitives are trustworthy without re-deriving that from scratch.
    """
    page_classes = {
        page["page_number"]: classify_page(page) for page in structure.get("pages", [])
    }
    primitives: List[TextPrimitive] = []
    for word in structure.get("words", []):
        page = word.get("page_number")
        primitives.append(TextPrimitive(
            primitive_id=word.get("object_id") or f"word_{len(primitives)}",
            page=page,
            text=word.get("text", ""),
            bbox=list(word.get("bbox") or [0, 0, 0, 0]),
            font=None,
            font_size=word.get("font_size"),
            rotation_deg=float(word.get("rotation") or 0.0),
            baseline_origin=None,
            extraction_source="native_pdf",
            confidence=None,
            block_id=str(word.get("block_no")) if word.get("block_no") is not None else None,
            line_id=str(word.get("line_no")) if word.get("line_no") is not None else None,
            sequence=word.get("reading_order") or 0,
        ))
    return primitives, page_classes
