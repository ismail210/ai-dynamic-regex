"""Canonical semantic data model for the upstream drawing preprocessor.

These are plain dataclasses (matching this repo's existing convention in
``services.normalization`` / ``services.prediction.canonical_contract``
rather than introducing Pydantic as a new dependency). Every dataclass here
supports ``to_dict()`` so the whole tree round-trips to the
``drawing_semantics.json`` sidecar (see ``serialization.py``).

Confidence fields are ``Optional[float]``: ``None`` means "not calibrated /
not evaluated", never a fabricated ``0.5``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Text primitives
# ---------------------------------------------------------------------------

# Page/extraction-quality classes (Section 19 of the brief).
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
    bbox: List[float]  # [x0, y0, x1, y1] in PDF page points, unrotated frame
    font: Optional[str] = None
    font_size: Optional[float] = None
    rotation_deg: float = 0.0
    baseline_origin: Optional[List[float]] = None
    extraction_source: str = "native_pdf"  # native_pdf | ocr
    confidence: Optional[float] = None  # None for native PDF text (exact), OCR engine score otherwise
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


# ---------------------------------------------------------------------------
# Structural parse
# ---------------------------------------------------------------------------


@dataclass
class StructuralParse:
    is_structural: bool
    family: Optional[str] = None
    grammar: Optional[str] = None
    fields: Dict[str, Any] = field(default_factory=dict)
    catalog_exact_match: bool = False
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_structural": self.is_structural,
            "family": self.family,
            "grammar": self.grammar,
            "fields": dict(self.fields),
            "catalog_exact_match": self.catalog_exact_match,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Correction (the four operations stay structurally distinct -- Section 18)
# ---------------------------------------------------------------------------

OP_NONE = "none"
OP_NORMALIZATION = "normalization"
OP_REPAIR = "repair"
OP_COMPLETION = "completion"


@dataclass
class Correction:
    operation: str = OP_NONE
    original: str = ""
    canonical: str = ""
    confidence: Optional[float] = None
    confidence_is_calibrated: bool = False
    auto_accept: bool = False
    reason_codes: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "original": self.original,
            "canonical": self.canonical,
            "confidence": self.confidence,
            "confidence_is_calibrated": self.confidence_is_calibrated,
            "auto_accept": self.auto_accept,
            "reason_codes": list(self.reason_codes),
            "evidence_ids": list(self.evidence_ids),
        }


# ---------------------------------------------------------------------------
# Modifiers (bracket tags etc attached to a primary label)
# ---------------------------------------------------------------------------


@dataclass
class Modifier:
    type: str  # e.g. "bracket_tag"
    raw_text: str
    value: str
    primitive_ids: List[str] = field(default_factory=list)
    bbox: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "raw_text": self.raw_text,
            "value": self.value,
            "primitive_ids": list(self.primitive_ids),
            "bbox": self.bbox,
        }


# ---------------------------------------------------------------------------
# Geometry association
# ---------------------------------------------------------------------------

REVIEW_ACCEPTED = "accepted"
REVIEW_AUTO_ACCEPTED = "auto_accepted"
REVIEW_NEEDS_REVIEW = "needs_review"
REVIEW_PENDING = "pending"


@dataclass
class EvidenceItem:
    type: str
    value: Any
    weight: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "value": self.value, "weight": self.weight}


@dataclass
class AssociationCandidate:
    annotation_id: str
    geometry_id: str
    score: Optional[float]
    evidence: List[EvidenceItem] = field(default_factory=list)
    association_reason: List[str] = field(default_factory=list)
    review_status: str = REVIEW_PENDING
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "annotation_id": self.annotation_id,
            "geometry_id": self.geometry_id,
            "score": self.score,
            "evidence": [e.to_dict() for e in self.evidence],
            "association_reason": list(self.association_reason),
            "review_status": self.review_status,
            "verified": self.verified,
        }


# ---------------------------------------------------------------------------
# Semantic annotation
# ---------------------------------------------------------------------------


@dataclass
class SourceFragment:
    """One raw text primitive's own geometry, preserved after grouping.

    Grouping must never destroy this (Section 21) -- ``semantic_bbox`` is a
    union derived FROM these, not a replacement for them.
    """

    primitive_id: str
    text: str
    bbox: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return {"primitive_id": self.primitive_id, "text": self.text, "bbox": self.bbox}


@dataclass
class SemanticAnnotation:
    annotation_id: str
    page: int
    original_text: str
    source_fragment_ids: List[str] = field(default_factory=list)
    source_fragments: List[SourceFragment] = field(default_factory=list)
    semantic_bbox: Optional[List[float]] = None
    original_anchor: Optional[List[float]] = None
    original_axis: Optional[List[float]] = None
    primary_label: Optional[str] = None
    modifiers: List[Modifier] = field(default_factory=list)
    grouping_reasons: List[str] = field(default_factory=list)
    structural_parse: Optional[StructuralParse] = None
    correction: Correction = field(default_factory=Correction)
    geometry_associations: List[AssociationCandidate] = field(default_factory=list)
    review_status: str = REVIEW_PENDING
    rewrite_applied: bool = False
    rendered_bbox: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "annotation_id": self.annotation_id,
            "page": self.page,
            "original_text": self.original_text,
            "source_fragment_ids": list(self.source_fragment_ids),
            "source_fragments": [f.to_dict() for f in self.source_fragments],
            "semantic_bbox": self.semantic_bbox,
            "original_anchor": self.original_anchor,
            "original_axis": self.original_axis,
            "primary_label": self.primary_label,
            "modifiers": [m.to_dict() for m in self.modifiers],
            "grouping_reasons": list(self.grouping_reasons),
            "structural_parse": self.structural_parse.to_dict() if self.structural_parse else None,
            "correction": self.correction.to_dict(),
            "geometry_associations": [a.to_dict() for a in self.geometry_associations],
            "review_status": self.review_status,
            "rewrite": {"applied": self.rewrite_applied, "rendered_bbox": self.rendered_bbox},
        }


# ---------------------------------------------------------------------------
# Coordinate frame
# ---------------------------------------------------------------------------


@dataclass
class CoordinateTransform:
    """A fitted mapping between two 2D spatial frames (e.g. PDF page <-> Rhino).

    Never assume PDF and Rhino coordinates are interchangeable (Section 13).
    ``valid`` is the load-bearing field: association code must refuse to use
    a transform whose ``valid`` is False rather than silently proceeding.
    """

    id: str
    source_frame: str
    target_frame: str
    scale_x: float
    scale_y: float
    rotation_deg: float
    translation: List[float]
    flip_y: bool
    residual_mean: Optional[float] = None
    residual_median: Optional[float] = None
    residual_p95: Optional[float] = None
    residual_max: Optional[float] = None
    sample_count: int = 0
    valid: bool = False
    invalid_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_frame": self.source_frame,
            "target_frame": self.target_frame,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "rotation_deg": self.rotation_deg,
            "translation": list(self.translation),
            "flip_y": self.flip_y,
            "residual_mean": self.residual_mean,
            "residual_median": self.residual_median,
            "residual_p95": self.residual_p95,
            "residual_max": self.residual_max,
            "sample_count": self.sample_count,
            "valid": self.valid,
            "invalid_reason": self.invalid_reason,
        }


# ---------------------------------------------------------------------------
# Geometry evidence (kept separate from PDF geometry -- Section 16)
# ---------------------------------------------------------------------------


@dataclass
class GeometryEvidence:
    geometry_id: str
    source: str  # "grasshopper" | "pdf_vector" | "human"
    geometry_type: str  # beam_curve | curved_beam | column | moment | misc | unknown
    source_geometry_id: Optional[str] = None
    source_definition_sha256: Optional[str] = None
    source_output: Optional[str] = None  # e.g. "RH_OUT:BeamCrv"
    sheet: Optional[str] = None
    points: Optional[List[List[float]]] = None
    bbox: Optional[List[float]] = None
    centroid: Optional[List[float]] = None
    start: Optional[List[float]] = None
    end: Optional[List[float]] = None
    length: Optional[float] = None
    orientation: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "geometry_id": self.geometry_id,
            "source": self.source,
            "geometry_type": self.geometry_type,
            "source_geometry_id": self.source_geometry_id,
            "source_definition_sha256": self.source_definition_sha256,
            "source_output": self.source_output,
            "sheet": self.sheet,
            "points": self.points,
            "bbox": self.bbox,
            "centroid": self.centroid,
            "start": self.start,
            "end": self.end,
            "length": self.length,
            "orientation": self.orientation,
            "metadata": dict(self.metadata),
            "provenance": dict(self.provenance),
        }


# ---------------------------------------------------------------------------
# Document root
# ---------------------------------------------------------------------------


@dataclass
class SemanticDocument:
    document_id: str
    input_pdf_sha256: Optional[str] = None
    pipeline_version: str = SCHEMA_VERSION
    catalog_version: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    annotations: List[SemanticAnnotation] = field(default_factory=list)
    drawing_language_rules: List[Dict[str, Any]] = field(default_factory=list)
    grasshopper_geometry: List[GeometryEvidence] = field(default_factory=list)
    coordinate_frames: List[CoordinateTransform] = field(default_factory=list)

    diagnostics: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "schema_version": self.schema_version,
            "input_pdf_sha256": self.input_pdf_sha256,
            "pipeline_version": self.pipeline_version,
            "catalog_version": self.catalog_version,
            "annotations": [a.to_dict() for a in self.annotations],
            "drawing_language_rules": list(self.drawing_language_rules),
            "grasshopper_geometry": [g.to_dict() for g in self.grasshopper_geometry],
            "coordinate_frames": [c.to_dict() for c in self.coordinate_frames],
            "diagnostics": dict(self.diagnostics),
            "metrics": dict(self.metrics),
        }
