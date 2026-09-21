"""Extraction-stage text-primitive types for the semantic preprocessor
pipeline.

This module used to also re-export the semantic annotation domain model
(now canonical in ``services.semantic.models`` -- see
``docs/architecture/unified_semantic_contract.md``) plus a set of legacy
string/alias constants derived from it. That re-export block had zero
remaining internal callers (every consumer of this module only ever used
``TextPrimitive`` and the page-quality constants below) and was removed.
Import the domain model directly from ``services.semantic.models`` if
needed.

``TextPrimitive`` and the page-quality classification constants are an
extraction-stage *working* type this pipeline uses before grouping ever
produces a semantic annotation, and the partner model never had an
equivalent concept, so they were never part of the duplicated architecture
that consolidation removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Text primitives (extraction-stage only; see module docstring)
# ---------------------------------------------------------------------------

NATIVE_TEXT_HEALTHY = "native_text_healthy"
NATIVE_TEXT_GARBLED = "native_text_garbled"
NO_NATIVE_TEXT = "no_native_text"
IMAGE_DOMINANT = "image_dominant"
OUTLINED_TEXT_SUSPECTED = "outlined_text_suspected"
UNKNOWN_PAGE_CLASS = "unknown"


@dataclass
class TextPrimitive:
    """One PDF-native or OCR text fragment, before any grouping."""

    primitive_id: str
    page: int
    text: str
    bbox: List[float]
    font: Optional[str] = None
    font_size: Optional[float] = None
    rotation_deg: float = 0.0
    baseline_origin: Optional[List[float]] = None
    extraction_source: str = "native_pdf"
    confidence: Optional[float] = None
    block_id: Optional[str] = None
    line_id: Optional[str] = None
    sequence: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primitive_id": self.primitive_id,
            "page": self.page,
            "text": self.text,
            "bbox": list(self.bbox),
            "font": self.font,
            "font_size": self.font_size,
            "rotation_deg": self.rotation_deg,
            "baseline_origin": self.baseline_origin,
            "extraction_source": self.extraction_source,
            "confidence": self.confidence,
            "block_id": self.block_id,
            "line_id": self.line_id,
            "sequence": self.sequence,
        }
