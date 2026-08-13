"""Classify whether an annotation is understandable before prediction."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.annotation.normalize import as_float
from services.annotation.parser import AnnotationParse
from services.annotation.taxonomy import (
    AnnotationType,
    Understandability,
    annotation_type_value,
)
from services.database_loader import is_catalog_label
from services.wildcard_matcher import has_wildcards


_GARBAGE = re.compile(r"^[^A-Za-z0-9]+$")
_HEAVY_CORRUPT = re.compile(r"[?¿]{2,}|\*{3,}|_{3,}")


def classify_understandability(
    parsed: AnnotationParse,
    *,
    extraction_confidence: Optional[float] = None,
    candidate_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return understandability state + reasons (never invents a Top-1)."""

    raw = parsed.raw_text or ""
    compact = (parsed.normalized_text or "").replace(" ", "").upper()
    candidates = [str(item) for item in (candidate_labels or []) if item]
    reasons: List[str] = []
    # Types may arrive as enums, mixed case, or unknown strings from callers.
    annotation_type = annotation_type_value(parsed.annotation_type)

    if not raw.strip() or _GARBAGE.match(raw.strip()):
        return {
            "status": Understandability.UNREADABLE.value,
            "reasons": ["Empty or non-alphanumeric annotation."],
            "continue_prediction": False,
            "route_to_review": True,
        }

    if annotation_type == AnnotationType.UNREADABLE.value or _HEAVY_CORRUPT.search(raw):
        return {
            "status": Understandability.UNREADABLE.value,
            "reasons": ["OCR/text is heavily corrupted."],
            "continue_prediction": False,
            "route_to_review": True,
        }

    if annotation_type == AnnotationType.UNSUPPORTED.value:
        return {
            "status": Understandability.UNSUPPORTED.value,
            "reasons": ["Notation is not in the supported engineering taxonomy."],
            "continue_prediction": False,
            "route_to_review": True,
        }

    if annotation_type == AnnotationType.TEXT_NOTE.value and len(compact) > 24:
        return {
            "status": Understandability.UNSUPPORTED.value,
            "reasons": ["Long free-text note — not a member annotation."],
            "continue_prediction": False,
            "route_to_review": True,
        }

    if annotation_type == AnnotationType.STANDARD_SECTION.value:
        if parsed.catalog_valid or is_catalog_label(compact):
            return {
                "status": Understandability.UNDERSTOOD.value,
                "reasons": ["Standard section designation recognized."],
                "continue_prediction": True,
                "route_to_review": False,
            }
        if has_wildcards(raw) or has_wildcards(parsed.normalized_text) or "?" in raw:
            reasons.append("Section pattern understood but characters are damaged/wildcards.")
            return {
                "status": Understandability.AMBIGUOUS.value,
                "reasons": reasons,
                "continue_prediction": True,
                "route_to_review": False,
            }
        if candidates:
            reasons.append("Section-like text with multiple catalog candidates.")
            return {
                "status": Understandability.AMBIGUOUS.value,
                "reasons": reasons,
                "continue_prediction": True,
                "route_to_review": False,
            }
        return {
            "status": Understandability.AMBIGUOUS.value,
            "reasons": ["Section-like text not confirmed in catalog."],
            "continue_prediction": True,
            "route_to_review": False,
        }

    if annotation_type in {
        AnnotationType.PLATE.value,
        AnnotationType.BENT_PLATE.value,
    }:
        if parsed.structure_confirmed and parsed.dimensions:
            return {
                "status": Understandability.UNDERSTOOD.value,
                "reasons": [
                    "Plate/bent-plate structure confirmed with context "
                    "(text head and/or geometry/graph/leader)."
                ],
                "continue_prediction": True,
                "route_to_review": False,
            }
        return {
            "status": Understandability.AMBIGUOUS.value,
            "reasons": ["Plate-like dimensions need multimodal confirmation."],
            "continue_prediction": True,
            "route_to_review": False,
        }

    if annotation_type == AnnotationType.DIMENSION.value:
        return {
            "status": Understandability.AMBIGUOUS.value,
            "reasons": [
                parsed.provenance.get("needs_context")
                or "Compound dimensions understood as numbers; semantics not confirmed."
            ],
            "continue_prediction": True,
            "route_to_review": False,
        }

    if annotation_type in {
        AnnotationType.MEMBER_MARK.value,
        AnnotationType.RANGE.value,
        AnnotationType.ANGLE.value,
        AnnotationType.GRID_REFERENCE.value,
        AnnotationType.SCHEDULE_REFERENCE.value,
    }:
        return {
            "status": Understandability.UNDERSTOOD.value,
            "reasons": [f"Recognized as {annotation_type}."],
            "continue_prediction": True,
            "route_to_review": annotation_type
            in {AnnotationType.SCHEDULE_REFERENCE.value, AnnotationType.GRID_REFERENCE.value},
        }

    confidence = as_float(extraction_confidence)
    if confidence is not None and confidence < 0.35:
        return {
            "status": Understandability.UNREADABLE.value,
            "reasons": ["Extraction confidence too low to trust the characters."],
            "continue_prediction": False,
            "route_to_review": True,
        }

    return {
        "status": Understandability.AMBIGUOUS.value,
        "reasons": ["Annotation type not fully resolved."],
        "continue_prediction": True,
        "route_to_review": True,
    }
