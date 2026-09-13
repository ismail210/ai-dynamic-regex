"""DEPRECATED shim for the semantic annotation domain model.

The canonical model now lives in ``services.semantic.models`` (see
``docs/architecture/unified_semantic_contract.md``). Everything re-exported
below is the SAME class as ``services.semantic.models`` -- there is exactly
one definition, never a copy.

``TextPrimitive`` and the page-quality classification constants are the one
thing that stays here: they are an extraction-stage *working* type this
pipeline uses before grouping ever produces a semantic annotation, and the
partner model never had an equivalent concept, so they were never part of
the duplicated architecture this consolidation removes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.semantic.models import (  # noqa: F401
    CoordinateTransform,
    DrawingLanguageRule,
    EvidenceRecord as EvidenceItem,
    GeometryAssociation as AssociationCandidate,
    GeometryEvidence,
    GeometryProvider,
    Modifier,
    OperationKind,
    OperationRecord,
    ReviewState,
    ReviewStatus,
    ScoreValue,
    SemanticAnnotation,
    SemanticDocument,
    SourceFragment,
    StructuralParse,
    derive_annotation_id,
)
from services.semantic.models import SCHEMA_VERSION as SCHEMA_VERSION  # noqa: F401

# Legacy plain-string operation/review constants -- old call sites that only
# need the string value (not the enum) keep working.
OP_NONE = OperationKind.KEEP.value
OP_NORMALIZATION = OperationKind.NORMALIZATION.value
OP_REPAIR = OperationKind.REPAIR.value
OP_COMPLETION = OperationKind.COMPLETION.value

REVIEW_ACCEPTED = ReviewStatus.HUMAN_ACCEPTED.value
REVIEW_AUTO_ACCEPTED = ReviewStatus.AUTO_ACCEPTED.value
REVIEW_NEEDS_REVIEW = ReviewStatus.NEEDS_REVIEW.value
REVIEW_PENDING = ReviewStatus.PENDING.value

# Legacy dataclass alias -- Correction is gone (Section 12/45: a single
# mutable "correction" field can't hold history); nothing in this package
# constructs it anymore. Kept only in case an external caller still imports
# the name.
Correction = OperationRecord


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
