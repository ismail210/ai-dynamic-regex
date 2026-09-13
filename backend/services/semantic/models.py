"""Canonical semantic annotation domain model (unified contract, v2).

This is the ONE authoritative representation of "a semantic annotation" for
this codebase. It replaces two previously-independent, overlapping models:

- ``services.prediction.semantic_contract`` (Pydantic; typed operation
  history, typed evidence, typed geometry-provider evidence; a read-only
  *projection* over production prediction payloads for the A8
  ``drawing_semantics.json`` sidecar).
- ``services.semantic_preprocessor.models`` (dataclasses; source-fragment
  fidelity, semantic spatial provenance, multi-candidate ranked geometry
  association; the live data model for the standalone semantic-preprocessing
  pipeline and the Semantic Review demo).

See ``docs/architecture/unified_semantic_contract.md`` for the full design
rationale, comparison, and worked examples.

Design choices (see the doc for the "why" on each):

- Plain dataclasses with hand-written ``to_dict()``, not Pydantic. Benchmarked
  at 27k-annotation scale: dataclass construct+serialize is ~3x faster than
  the Pydantic equivalent (0.16s vs 0.52s) with this repo's existing
  hand-written-``to_dict`` convention. Pydantic stays in use at the API
  request/response boundary (routers), just not as the domain model.
- ``str, Enum`` for closed vocabularies (operation kind, review status,
  geometry provider, evidence type/strength) -- keeps partner's typing
  strength; still a plain string at runtime and in JSON.
- Original observation (``original_text`` / ``source_fragments``) is never
  overwritten. Every text transformation is an appended, immutable
  ``OperationRecord`` -- never an in-place mutation of a single "correction"
  field. ``effective_text`` is a computed property, not stored state.
- ``takeoff_eligible`` is independent of "is this a semantic annotation at
  all" -- an incomplete member (``L4X4``) stays fully present with
  ``takeoff_eligible=False`` and ``review.status=NEEDS_REVIEW``.
- Geometry is evidence, never truth: multiple ``GeometryAssociation``
  candidates may coexist, each carrying its own ``provider`` and an
  independent ``review_status`` from the text's own review state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "2.0"

# ---------------------------------------------------------------------------
# Enums -- one definition per concept (Section 55). Values match the plain
# strings already used on disk/in APIs wherever a prior model already shipped
# one, so existing serialized data parses without a lossy remap.
# ---------------------------------------------------------------------------


class OperationKind(str, Enum):
    """A semantic text transformation. KEEP is a first-class decision, not
    the absence of a record (Section 14) -- it is the auditable statement
    "this was evaluated and deliberately left unchanged", distinct from
    "never evaluated" (no operations at all)."""

    KEEP = "keep"
    NORMALIZATION = "normalization"
    REPAIR = "repair"
    COMPLETION = "completion"

    @classmethod
    def _missing_(cls, value: object) -> "OperationKind":
        # Legacy compatibility: semantic_preprocessor's OP_NONE == "none".
        if value == "none":
            return cls.KEEP
        raise ValueError(f"{value!r} is not a valid {cls.__name__}")


class ReviewStatus(str, Enum):
    PENDING = "pending"
    AUTO_ACCEPTED = "auto_accepted"
    HUMAN_ACCEPTED = "human_accepted"
    HUMAN_REJECTED = "human_rejected"
    NEEDS_REVIEW = "needs_review"
    UNRESOLVED = "unresolved"

    @classmethod
    def _missing_(cls, value: object) -> "ReviewStatus":
        # Legacy compatibility: semantic_preprocessor used "accepted".
        if value == "accepted":
            return cls.HUMAN_ACCEPTED
        raise ValueError(f"{value!r} is not a valid {cls.__name__}")


class GeometryProvider(str, Enum):
    """Where a piece of geometry evidence came from. Never leave this
    implicit (Section 19/21) -- a PDF-vector candidate and a future
    Grasshopper candidate are not equivalent evidence."""

    PDF_VECTOR = "pdf_vector"
    GRASSHOPPER = "grasshopper"
    HUMAN = "human"
    UNAVAILABLE = "unavailable"

    @classmethod
    def _missing_(cls, value: object) -> "GeometryProvider":
        if value == "pdf":
            return cls.PDF_VECTOR
        raise ValueError(f"{value!r} is not a valid {cls.__name__}")


class EvidenceType(str, Enum):
    PDF_TEXT = "pdf_text"
    NEARBY_NOTE = "nearby_note"
    LEGEND = "legend"
    SCHEDULE = "schedule"
    DETAIL = "detail"
    STRUCTURAL_CONTEXT = "structural_context"
    DRAWING_RULE = "drawing_rule"
    CATALOG = "catalog"
    REPAIR_CANDIDATE = "repair_candidate"
    GEOMETRY_DISTANCE = "geometry_distance"
    GRASSHOPPER_GEOMETRY = "grasshopper_geometry"
    PDF_GEOMETRY = "pdf_geometry"
    HUMAN_REVIEW = "human_review"
    OTHER = "other"


class EvidenceStrength(str, Enum):
    """Whether the cited support is explicit on the drawing or inferred."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Score -- one typed representation for every "confidence"-shaped value in
# the system (Section 27). Never let a raw ranker score masquerade as a
# calibrated probability.
# ---------------------------------------------------------------------------

SCORE_RAW_MODEL = "raw_model_score"
SCORE_CALIBRATED = "calibrated_probability"
SCORE_RULE_CONFIDENCE = "rule_confidence"
SCORE_ASSOCIATION_DISTANCE = "association_distance"
SCORE_DETERMINISTIC = "deterministic"


@dataclass
class ScoreValue:
    value: float
    kind: str = SCORE_DETERMINISTIC
    calibrated: bool = False
    model_name: Optional[str] = None
    model_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "kind": self.kind,
            "calibrated": self.calibrated,
            "model_name": self.model_name,
            "model_version": self.model_version,
        }


# ---------------------------------------------------------------------------
# Source fragments -- the original observation. Never replaced by corrected
# text (Section 7).
# ---------------------------------------------------------------------------


@dataclass
class SourceFragment:
    """One raw PDF-native or OCR text span, before any grouping."""

    primitive_id: str
    text: str
    bbox: List[float]
    quad: Optional[List[float]] = None
    page: Optional[int] = None
    font: Optional[str] = None
    font_size: Optional[float] = None
    rotation_deg: float = 0.0
    extraction_source: str = "native_pdf"  # native_pdf | ocr
    confidence: Optional[float] = None
    block_id: Optional[str] = None
    line_id: Optional[str] = None
    word_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primitive_id": self.primitive_id,
            "text": self.text,
            "bbox": list(self.bbox),
            "quad": self.quad,
            "page": self.page,
            "font": self.font,
            "font_size": self.font_size,
            "rotation_deg": self.rotation_deg,
            "extraction_source": self.extraction_source,
            "confidence": self.confidence,
            "block_id": self.block_id,
            "line_id": self.line_id,
            "word_id": self.word_id,
        }


@dataclass
class Modifier:
    """A secondary tag attached to a primary label, e.g. a bracket mark
    number ``[24]`` next to ``W18X40``."""

    type: str
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
# Structural parse -- first-class typed interpretation (Section 9).
# ---------------------------------------------------------------------------

CATALOG_EXACT_MATCH = "exact_match"
CATALOG_NOT_IN_CATALOG = "not_in_catalog"
CATALOG_UNKNOWN = "unknown"


@dataclass
class StructuralParse:
    is_structural: bool
    family: Optional[str] = None
    grammar: Optional[str] = None
    fields: Dict[str, Any] = field(default_factory=dict)
    complete: bool = True
    catalog_status: str = CATALOG_UNKNOWN
    parser_reason: Optional[str] = None

    def __post_init__(self) -> None:
        # `complete` is derived from grammar unless a caller overrides it
        # explicitly with a non-default value up front -- "incomplete" is
        # the one grammar tag the existing parser already uses for a
        # structural-but-missing-fields label (e.g. bare "W8", "L4X4").
        if self.grammar == "incomplete":
            self.complete = False

    @property
    def catalog_exact_match(self) -> bool:
        """Back-compat convenience: semantic_preprocessor's old boolean."""
        return self.catalog_status == CATALOG_EXACT_MATCH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_structural": self.is_structural,
            "family": self.family,
            "grammar": self.grammar,
            "fields": dict(self.fields),
            "complete": self.complete,
            "catalog_status": self.catalog_status,
            "catalog_exact_match": self.catalog_exact_match,
            "parser_reason": self.parser_reason,
        }


# ---------------------------------------------------------------------------
# Evidence -- one typed representation for every operation/association
# (Section 18). A tagged record (evidence_type discriminates), not a dict
# dumping ground, but not a dozen near-duplicate subclasses either.
# ---------------------------------------------------------------------------


@dataclass
class EvidenceRecord:
    evidence_id: str
    evidence_type: EvidenceType
    source: str  # provenance string, e.g. "pdf_text", "drawing_rule", "exact_section_predictor", "lightgbm_repair_ranker_v2", "human"
    strength: EvidenceStrength = EvidenceStrength.UNKNOWN
    reference: Optional[str] = None  # quoted text / rule_id / geometry_id
    score: Optional[ScoreValue] = None
    page: Optional[int] = None
    bbox: Optional[List[float]] = None
    notes: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value if isinstance(self.evidence_type, Enum) else self.evidence_type,
            "source": self.source,
            "strength": self.strength.value if isinstance(self.strength, Enum) else self.strength,
            "reference": self.reference,
            "score": self.score.to_dict() if self.score else None,
            "page": self.page,
            "bbox": self.bbox,
            "notes": self.notes,
            "details": dict(self.details),
        }


# ---------------------------------------------------------------------------
# Operation history (Section 12/13/45) -- the strongest idea from the
# partner model, generalized. NORMALIZATION / REPAIR / COMPLETION / KEEP
# only: grouping is reconstruction provenance (``grouping_reasons``, not an
# operation), association lives in ``geometry_associations`` (not an
# operation), and review actions live in ``ReviewState.history``.
# ---------------------------------------------------------------------------


@dataclass
class OperationRecord:
    operation: OperationKind
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    evidence: List[EvidenceRecord] = field(default_factory=list)
    score: Optional[ScoreValue] = None
    deterministic: bool = True
    semantic_information_added: bool = False
    provenance: Optional[str] = None
    accepted: bool = True  # False once a human rejects a proposed op (Section 45) -- the record itself is never deleted
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation.value if isinstance(self.operation, Enum) else self.operation,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "reason_codes": list(self.reason_codes),
            "evidence": [e.to_dict() for e in self.evidence],
            "score": self.score.to_dict() if self.score else None,
            "deterministic": self.deterministic,
            "semantic_information_added": self.semantic_information_added,
            "provenance": self.provenance,
            "accepted": self.accepted,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Geometry (Sections 19-22) -- evidence, never truth. Multiple candidates,
# each with its own provider/rank/score, may coexist unresolved.
# ---------------------------------------------------------------------------


@dataclass
class GeometryEvidence:
    """One geometry object as reported by a provider (a beam/column/etc from
    a PDF vector scan or a future Grasshopper RH_OUT export)."""

    geometry_id: str
    provider: GeometryProvider
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
    coordinate_system: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "geometry_id": self.geometry_id,
            "provider": self.provider.value if isinstance(self.provider, Enum) else self.provider,
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
            "coordinate_system": self.coordinate_system,
            "metadata": dict(self.metadata),
        }


@dataclass
class GeometryAssociation:
    """One candidate link between an annotation and a ``GeometryEvidence``
    object. Unresolved-precision by design (Section 22): ``score`` may be
    ``None``, and ``verified`` only ever becomes ``True`` via an explicit
    human (or future ground-truth) decision -- never inferred from a
    provider's own confidence."""

    geometry_id: str
    provider: GeometryProvider
    rank: Optional[int] = None
    score: Optional[ScoreValue] = None
    evidence: List[EvidenceRecord] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    coordinate_frame: Optional[str] = None
    verified: bool = False
    review_status: ReviewStatus = ReviewStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "geometry_id": self.geometry_id,
            "provider": self.provider.value if isinstance(self.provider, Enum) else self.provider,
            "rank": self.rank,
            "score": self.score.to_dict() if self.score else None,
            "evidence": [e.to_dict() for e in self.evidence],
            "reason_codes": list(self.reason_codes),
            "coordinate_frame": self.coordinate_frame,
            "verified": self.verified,
            "review_status": self.review_status.value if isinstance(self.review_status, Enum) else self.review_status,
        }


@dataclass
class CoordinateTransform:
    """A fitted mapping between two 2D spatial frames (e.g. PDF page <->
    Rhino). ``valid`` is load-bearing: association code must refuse to use a
    transform whose ``valid`` is False rather than silently proceeding."""

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
# Review (Section 23/73) -- text review and geometry-association review can
# progress independently; this is the annotation-level text/overall state,
# each GeometryAssociation carries its own review_status separately.
# ---------------------------------------------------------------------------


@dataclass
class ReviewState:
    status: ReviewStatus = ReviewStatus.PENDING
    resolved_text: Optional[str] = None
    reason: Optional[str] = None
    comment: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "resolved_text": self.resolved_text,
            "reason": self.reason,
            "comment": self.comment,
            "reviewed_at": self.reviewed_at,
            "reviewed_by": self.reviewed_by,
            "history": [dict(h) for h in self.history],
        }


# ---------------------------------------------------------------------------
# Annotation identity (Section 24) -- deterministic, content-derived, never
# from loop position or from post-correction text.
# ---------------------------------------------------------------------------


def derive_annotation_id(document_id: str, page: int, source_fragment_ids: List[str]) -> str:
    """Stable annotation identity from (document, page, contributing source
    fragments) -- independent of iteration order and of any correction
    later applied to the text."""

    key = f"{document_id}|{page}|{'|'.join(sorted(source_fragment_ids))}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"ann_{digest}"


# ---------------------------------------------------------------------------
# Semantic annotation -- the central object.
# ---------------------------------------------------------------------------


@dataclass
class SemanticAnnotation:
    annotation_id: str
    original_text: str

    schema_version: str = SCHEMA_VERSION
    document_id: Optional[str] = None
    page: Optional[int] = None

    # WHAT WAS OBSERVED, WHERE IT CAME FROM, WHERE IT IS ON THE DRAWING
    source_fragment_ids: List[str] = field(default_factory=list)
    source_fragments: List[SourceFragment] = field(default_factory=list)
    extraction_source: Optional[str] = None
    semantic_bbox: Optional[List[float]] = None
    original_anchor: Optional[List[float]] = None
    original_axis: Optional[List[float]] = None
    rendered_bbox: Optional[List[float]] = None

    # WHAT IT MEANS
    primary_label: Optional[str] = None
    modifiers: List[Modifier] = field(default_factory=list)
    grouping_reasons: List[str] = field(default_factory=list)
    structural_parse: Optional[StructuralParse] = None

    # WHAT CHANGED / WHY (full history; never mutated in place)
    operations: List[OperationRecord] = field(default_factory=list)

    # Annotation-level evidence not tied to a single operation
    evidence: List[EvidenceRecord] = field(default_factory=list)

    # WHETHER SAFE FOR DOWNSTREAM TAKEOFF (independent of semantic validity)
    takeoff_eligible: Optional[bool] = None

    # WHAT GEOMETRY MAY BE ASSOCIATED (evidence, not truth)
    geometry_associations: List[GeometryAssociation] = field(default_factory=list)

    # WHETHER A HUMAN HAS REVIEWED IT
    review: ReviewState = field(default_factory=ReviewState)

    # Provenance
    pipeline_version: Optional[str] = None
    created_by: Optional[str] = None

    # -- invariant --------------------------------------------------------
    original_text_preserved: bool = True

    def __post_init__(self) -> None:
        if not self.original_text_preserved:
            raise ValueError(
                "original_text_preserved must be True -- original_text must stay recoverable"
            )

    # -- computed / derived views (Section 43/46: one source of truth) ----

    @property
    def effective_text(self) -> str:
        """The text downstream consumers should use *now*. The output of the
        latest *accepted* operation, or the original text if none exist /
        none were accepted."""

        for op in reversed(self.operations):
            if op.accepted and op.output_text:
                return op.output_text
        return self.original_text

    @property
    def review_status(self) -> ReviewStatus:
        return self.review.status

    @property
    def current_operation(self) -> Optional[OperationRecord]:
        """Most recent accepted operation, or None if the text has never
        been evaluated at all (distinct from "evaluated and kept")."""

        for op in reversed(self.operations):
            if op.accepted:
                return op
        return None

    @property
    def is_complete(self) -> Optional[bool]:
        if self.structural_parse is None:
            return None
        return self.structural_parse.complete

    @property
    def primary_geometry_association(self) -> Optional[GeometryAssociation]:
        if not self.geometry_associations:
            return None
        return max(
            self.geometry_associations,
            key=lambda a: (a.score.value if a.score else -1.0),
        )

    def to_dict(self) -> Dict[str, Any]:
        current = self.current_operation
        return {
            "schema_version": self.schema_version,
            "annotation_id": self.annotation_id,
            "document_id": self.document_id,
            "page": self.page,
            "original_text": self.original_text,
            "original_text_preserved": self.original_text_preserved,
            "source_fragment_ids": list(self.source_fragment_ids),
            "source_fragments": [f.to_dict() for f in self.source_fragments],
            "extraction_source": self.extraction_source,
            "semantic_bbox": self.semantic_bbox,
            "original_anchor": self.original_anchor,
            "original_axis": self.original_axis,
            "rendered_bbox": self.rendered_bbox,
            "primary_label": self.primary_label,
            "modifiers": [m.to_dict() for m in self.modifiers],
            "grouping_reasons": list(self.grouping_reasons),
            "structural_parse": self.structural_parse.to_dict() if self.structural_parse else None,
            "operations": [o.to_dict() for o in self.operations],
            "evidence": [e.to_dict() for e in self.evidence],
            "takeoff_eligible": self.takeoff_eligible,
            "geometry_associations": [a.to_dict() for a in self.geometry_associations],
            "review": self.review.to_dict(),
            "review_status": self.review.status.value if isinstance(self.review.status, Enum) else self.review.status,
            "pipeline_version": self.pipeline_version,
            "created_by": self.created_by,
            "effective_text": self.effective_text,
            # Back-compat convenience view for existing UI/tests: the shape
            # of the old semantic_preprocessor `correction` object, derived
            # from `operations` rather than stored independently.
            "correction": {
                "operation": (current.operation.value if current else OperationKind.KEEP.value),
                "original": (current.input_text if current else self.original_text) or self.original_text,
                "canonical": self.effective_text,
                "confidence": (current.score.value if current and current.score else None),
                "confidence_is_calibrated": bool(current.score.calibrated) if current and current.score else False,
                "auto_accept": bool(current.accepted) if current else False,
                "reason_codes": list(current.reason_codes) if current else [],
                "evidence_ids": [e.evidence_id for e in current.evidence] if current else [],
            },
        }


# ---------------------------------------------------------------------------
# Drawing-language rule -- document-level knowledge, referenced by
# completion operations' evidence rather than duplicated per-annotation
# (Section 26).
# ---------------------------------------------------------------------------


@dataclass
class DrawingLanguageRule:
    rule_id: str
    trigger: str
    result: str
    status: str = "source_verified"
    scope: Dict[str, Any] = field(default_factory=dict)
    source_evidence: List[EvidenceRecord] = field(default_factory=list)
    confidence: Optional[ScoreValue] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "trigger": self.trigger,
            "result": self.result,
            "rule_status": self.status,
            "scope": dict(self.scope),
            "source_evidence": [e.to_dict() for e in self.source_evidence],
            "confidence": self.confidence.to_dict() if self.confidence else None,
        }


# ---------------------------------------------------------------------------
# Document root.
# ---------------------------------------------------------------------------


@dataclass
class SemanticDocument:
    document_id: str
    schema_version: str = SCHEMA_VERSION
    input_pdf_sha256: Optional[str] = None
    pipeline_version: str = SCHEMA_VERSION
    catalog_version: Optional[str] = None

    annotations: List[SemanticAnnotation] = field(default_factory=list)
    drawing_language_rules: List[DrawingLanguageRule] = field(default_factory=list)
    geometry_evidence: List[GeometryEvidence] = field(default_factory=list)
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
            "drawing_language_rules": [
                r.to_dict() if isinstance(r, DrawingLanguageRule) else dict(r)
                for r in self.drawing_language_rules
            ],
            "geometry_evidence": [g.to_dict() for g in self.geometry_evidence],
            # Back-compat alias: semantic_preprocessor's old document key.
            "grasshopper_geometry": [g.to_dict() for g in self.geometry_evidence],
            "coordinate_frames": [c.to_dict() for c in self.coordinate_frames],
            "diagnostics": dict(self.diagnostics),
            "metrics": dict(self.metrics),
        }
