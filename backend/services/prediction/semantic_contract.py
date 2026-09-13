"""
Semantic annotation contract (schema only).

Represents Bassam's four distinct operations — NORMALIZATION, REPAIR,
COMPLETION, ASSOCIATION — plus evidence, abstention, review, and optional
geometry linkage.

This module does **not**:
- run normalization / repair / completion / association intelligence
- change takeoff eligibility calculation
- require Grasshopper / RH_OUT
- rewrite PDFs or emit ``drawing_semantics.json``

Production prediction payloads already carry ``raw_text``,
``normalized_text``, ``completion_status``, ``takeoff_eligible``,
``needs_review``, etc. Use :func:`project_semantic_annotation` to map those
fields into this schema without mutating producers.

See ``backend/SEMANTIC_CONTRACT.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


SEMANTIC_CONTRACT_VERSION = "1.0"


class SemanticOperationKind(str, Enum):
    """Four distinct semantic operations — never collapse into one 'correction'."""

    NORMALIZATION = "normalization"
    REPAIR = "repair"
    COMPLETION = "completion"
    ASSOCIATION = "association"


class EvidenceType(str, Enum):
    PDF_TEXT = "pdf_text"
    NEARBY_NOTE = "nearby_note"
    LEGEND = "legend"
    SCHEDULE = "schedule"
    DETAIL = "detail"
    STRUCTURAL_CONTEXT = "structural_context"
    GRASSHOPPER_GEOMETRY = "grasshopper_geometry"
    PDF_GEOMETRY = "pdf_geometry"
    HUMAN_REVIEW = "human_review"
    OTHER = "other"


class EvidenceStrength(str, Enum):
    """Whether the cited support is explicit on the drawing or inferred."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class CompletionStatus(str, Enum):
    """Aligned with existing production string values (orchestrator / multimodal)."""

    COMPLETE = "complete"
    MISSING_THICKNESS = "missing_thickness"


class GeometryRelationship(str, Enum):
    ASSOCIATED_WITH = "associated_with"
    UNPAIRED = "unpaired"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class SemanticEvidence(BaseModel):
    """Generic evidence item — geometry association is evidence, not semantic truth."""

    evidence_type: EvidenceType
    evidence_source: str
    evidence_reference: Optional[str] = None
    evidence_strength: EvidenceStrength = EvidenceStrength.UNKNOWN
    confidence: Optional[float] = None
    page_number: Optional[int] = None
    bounding_box: Optional[List[float]] = None
    notes: Optional[str] = None

    @field_validator("bounding_box")
    @classmethod
    def _bbox_len(cls, value: Optional[List[float]]) -> Optional[List[float]]:
        if value is None:
            return None
        if len(value) != 4:
            raise ValueError("bounding_box must be [x0, y0, x1, y1]")
        return list(value)


class GeometryEvidence(BaseModel):
    """Optional geometry linkage (PDF or future GH). GH fields are never required.

    Does **not** assume BeamTxt[i] == BeamCrv[i], BeamElementID stability, or
    a calibrated PDF↔Rhino transform — those remain unresolved (Phase 0D).
    """

    available: bool = False
    provider: Optional[str] = None  # e.g. "grasshopper", "pdf", "unavailable"
    relationship: GeometryRelationship = GeometryRelationship.UNAVAILABLE
    geometry_ref: Optional[str] = None
    geometry_type: Optional[str] = None
    confidence: Optional[float] = None
    coordinate_system: Optional[str] = None
    source: Optional[str] = None
    native_metadata: Dict[str, Any] = Field(default_factory=dict)


class OperationRecord(BaseModel):
    """Provenance for one semantic operation applied to an annotation.

    ASSOCIATION must not change semantic text: ``output_text`` must be absent
    or equal to ``input_text``.
    """

    operation: SemanticOperationKind
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    evidence: List[SemanticEvidence] = Field(default_factory=list)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _association_preserves_text(self) -> "OperationRecord":
        if self.operation != SemanticOperationKind.ASSOCIATION:
            return self
        if self.output_text is None or self.output_text == self.input_text:
            return self
        raise ValueError(
            "ASSOCIATION must not change semantic text "
            "(output_text must be None or equal to input_text)"
        )


class SemanticAnnotation(BaseModel):
    """Stable backend representation of one semantic annotation (schema only)."""

    schema_version: str = SEMANTIC_CONTRACT_VERSION
    annotation_id: str

    # Source — raw_text is immutable printed form; never overwrite with inferred text
    raw_text: str
    extraction_source: Optional[str] = None
    source_page: Optional[int] = None
    source_bbox: Optional[List[float]] = None

    # Semantic core (representation may differ from raw; raw stays recoverable)
    normalized_text: Optional[str] = None
    structural_family: Optional[str] = None
    parser_status: Optional[str] = None
    operations: List[OperationRecord] = Field(default_factory=list)

    # Completion / eligibility — records decisions; does not compute them here
    completion_status: CompletionStatus = CompletionStatus.COMPLETE
    original_text_preserved: bool = True
    takeoff_eligible: Optional[bool] = None

    # Evidence / confidence / review
    evidence: List[SemanticEvidence] = Field(default_factory=list)
    confidence: Optional[float] = None
    confidence_basis: Optional[str] = None
    review_required: bool = False
    review_status: Optional[str] = None
    review_reason: Optional[str] = None

    # Optional geometry (absent == unavailable; never invent GH pairing)
    geometry_evidence: Optional[GeometryEvidence] = None

    # Provenance
    pipeline_version: Optional[str] = None
    created_by: Optional[str] = None
    document_id: Optional[str] = None

    @field_validator("source_bbox")
    @classmethod
    def _source_bbox_len(cls, value: Optional[List[float]]) -> Optional[List[float]]:
        if value is None:
            return None
        if len(value) != 4:
            raise ValueError("source_bbox must be [x0, y0, x1, y1]")
        return list(value)

    @model_validator(mode="after")
    def _raw_must_remain(self) -> "SemanticAnnotation":
        if self.raw_text is None or str(self.raw_text) == "":
            # Empty raw is allowed for geometry-only tokens; still "preserved"
            return self
        if not self.original_text_preserved:
            raise ValueError(
                "original_text_preserved must be True — raw_text must stay recoverable"
            )
        return self

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


def project_semantic_annotation(payload: Dict[str, Any]) -> SemanticAnnotation:
    """Read-only projection from an existing prediction payload into this schema.

    Does not invent repair/completion/association operations. Maps only fields
    already present on production responses (orchestrator / MultiModalPrediction).
    """

    raw = payload.get("raw_text")
    if raw is None:
        raw = payload.get("original_token") or payload.get("token") or ""
    raw_text = str(raw)

    normalized = payload.get("normalized_text")
    if normalized is None:
        source_text = payload.get("source_text") or {}
        if isinstance(source_text, dict):
            normalized = source_text.get("normalized")
    normalized_text = str(normalized) if normalized is not None else None

    operations: List[OperationRecord] = []
    # Do not invent NORMALIZATION/REPAIR/COMPLETION from string diffs — that
    # would be new semantic behavior. Callers attach OperationRecord explicitly.

    completion_raw = str(payload.get("completion_status") or "complete")
    try:
        completion_status = CompletionStatus(completion_raw)
    except ValueError:
        completion_status = CompletionStatus.COMPLETE

    review_required = bool(
        payload.get("needs_review")
        if payload.get("needs_review") is not None
        else payload.get("review_required")
    )

    geometry_evidence: Optional[GeometryEvidence] = None
    member_geometry = payload.get("member_geometry")
    if isinstance(member_geometry, dict) and member_geometry:
        geometry_evidence = GeometryEvidence(
            available=True,
            provider="pdf",
            relationship=GeometryRelationship.ASSOCIATED_WITH,
            geometry_ref=str(member_geometry.get("object_id") or "") or None,
            geometry_type=str(member_geometry.get("kind") or "member") or None,
            confidence=(
                float(member_geometry["confidence"])
                if member_geometry.get("confidence") is not None
                else None
            ),
            coordinate_system="pdf_page",
            source="member_geometry",
            native_metadata=dict(member_geometry),
        )

    family = payload.get("family")
    if family is None:
        canonical = payload.get("canonical") or {}
        if isinstance(canonical, dict):
            family = (canonical.get("prediction") or {}).get("family")

    takeoff = payload.get("takeoff_eligible")
    if takeoff is not None:
        takeoff = bool(takeoff)

    annotation_id = str(
        payload.get("object_id")
        or payload.get("component_id")
        or payload.get("annotation_id")
        or "unknown"
    )

    conf = payload.get("confidence")
    confidence: Optional[float]
    if isinstance(conf, dict):
        confidence = float(conf.get("overall") or conf.get("score") or 0.0)
    elif conf is None:
        confidence = None
    else:
        try:
            confidence = float(conf)
        except (TypeError, ValueError):
            confidence = None

    extraction_source: Optional[str] = None
    if payload.get("prediction_source"):
        extraction_source = str(payload["prediction_source"])
    else:
        source_text = payload.get("source_text")
        if isinstance(source_text, dict) and source_text.get("extraction_method"):
            extraction_source = str(source_text["extraction_method"])

    return SemanticAnnotation(
        annotation_id=annotation_id,
        document_id=(
            str(payload["document_id"]) if payload.get("document_id") else None
        ),
        raw_text=raw_text,
        extraction_source=extraction_source,
        source_page=(
            int(payload["page_number"])
            if payload.get("page_number") is not None
            else None
        ),
        source_bbox=(
            list(payload["bounding_box"])
            if isinstance(payload.get("bounding_box"), (list, tuple))
            else None
        ),
        normalized_text=normalized_text,
        structural_family=str(family).upper() if family else None,
        operations=operations,
        completion_status=completion_status,
        original_text_preserved=True,
        takeoff_eligible=takeoff,
        confidence=confidence,
        confidence_basis=(
            str(payload["confidence_basis"])
            if payload.get("confidence_basis")
            else None
        ),
        review_required=review_required,
        review_status=(
            str(payload["review_status"]) if payload.get("review_status") else None
        ),
        review_reason=(
            str(payload["review_reason"]) if payload.get("review_reason") else None
        ),
        geometry_evidence=geometry_evidence,
        created_by="project_semantic_annotation",
    )


# ---------------------------------------------------------------------------
# Schema examples (documentation / tests only — not production intelligence)
# ---------------------------------------------------------------------------


def example_normalization_w8x10() -> SemanticAnnotation:
    return SemanticAnnotation(
        annotation_id="ex_norm_w8x10",
        raw_text="W8×10",
        normalized_text="W8X10",
        structural_family="W",
        operations=[
            OperationRecord(
                operation=SemanticOperationKind.NORMALIZATION,
                input_text="W8×10",
                output_text="W8X10",
            )
        ],
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        review_required=False,
        evidence=[
            SemanticEvidence(
                evidence_type=EvidenceType.PDF_TEXT,
                evidence_source="pdf_text",
                evidence_reference="W8×10",
                evidence_strength=EvidenceStrength.EXPLICIT,
            )
        ],
    )


def example_repair_corrupted_w8() -> SemanticAnnotation:
    return SemanticAnnotation(
        annotation_id="ex_repair_w8xi0",
        raw_text="W8XI0",
        normalized_text="W8X10",
        structural_family="W",
        operations=[
            OperationRecord(
                operation=SemanticOperationKind.REPAIR,
                input_text="W8XI0",
                output_text="W8X10",
                evidence=[
                    SemanticEvidence(
                        evidence_type=EvidenceType.NEARBY_NOTE,
                        evidence_source="nearby_note",
                        evidence_reference="W8X10 TYP",
                        evidence_strength=EvidenceStrength.EXPLICIT,
                    )
                ],
            )
        ],
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=None,
        review_required=True,
        review_reason="schema_example_only_not_implemented",
        evidence=[
            SemanticEvidence(
                evidence_type=EvidenceType.NEARBY_NOTE,
                evidence_source="nearby_note",
                evidence_reference="W8X10 TYP",
                evidence_strength=EvidenceStrength.EXPLICIT,
            )
        ],
    )


def example_completion_candidate_w8() -> SemanticAnnotation:
    return SemanticAnnotation(
        annotation_id="ex_completion_w8",
        raw_text="W8",
        normalized_text="W8",
        structural_family="W",
        operations=[
            OperationRecord(
                operation=SemanticOperationKind.COMPLETION,
                input_text="W8",
                output_text="W8X10",
                notes="candidate_only_requires_drawing_local_evidence",
                evidence=[
                    SemanticEvidence(
                        evidence_type=EvidenceType.SCHEDULE,
                        evidence_source="schedule",
                        evidence_reference="W8X10",
                        evidence_strength=EvidenceStrength.EXPLICIT,
                    )
                ],
            )
        ],
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=None,
        review_required=True,
        review_reason="schema_example_only_not_implemented",
    )


def example_l4x4_abstention() -> SemanticAnnotation:
    return SemanticAnnotation(
        annotation_id="ex_abstain_l4x4",
        raw_text="L4X4,",
        normalized_text="L4X4",
        structural_family="L",
        operations=[
            OperationRecord(
                operation=SemanticOperationKind.NORMALIZATION,
                input_text="L4X4,",
                output_text="L4X4",
                notes="punctuation_stripped_for_core_form_raw_preserved",
            )
        ],
        completion_status=CompletionStatus.MISSING_THICKNESS,
        takeoff_eligible=False,
        review_required=True,
        review_reason="incomplete_angle_missing_thickness",
    )


def example_2l4x4_abstention() -> SemanticAnnotation:
    return SemanticAnnotation(
        annotation_id="ex_abstain_2l4x4",
        raw_text="2L4X4",
        normalized_text="2L4X4",
        structural_family="2L",
        operations=[],
        completion_status=CompletionStatus.MISSING_THICKNESS,
        takeoff_eligible=False,
        review_required=True,
        review_reason="incomplete_angle_missing_thickness",
    )


def example_association_with_optional_gh() -> SemanticAnnotation:
    return SemanticAnnotation(
        annotation_id="ex_assoc_w12x26",
        raw_text="W12X26",
        normalized_text="W12X26",
        structural_family="W",
        operations=[
            OperationRecord(
                operation=SemanticOperationKind.ASSOCIATION,
                input_text="W12X26",
                output_text="W12X26",
                evidence=[
                    SemanticEvidence(
                        evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                        evidence_source="grasshopper",
                        evidence_reference="RH_OUT:BeamCrv unresolved_index",
                        evidence_strength=EvidenceStrength.INFERRED,
                        notes="GH optional; BeamTxt/BeamCrv pairing unproven",
                    )
                ],
            )
        ],
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        review_required=False,
        geometry_evidence=GeometryEvidence(
            available=True,
            provider="grasshopper",
            relationship=GeometryRelationship.ASSOCIATED_WITH,
            geometry_ref="unresolved",
            geometry_type="beam",
            confidence=None,
            coordinate_system="unknown",
            source="rh_out_optional",
            native_metadata={
                "beam_txt_crv_index_assumed_equal": False,
                "beam_element_id_stability": "unknown",
            },
        ),
        evidence=[
            SemanticEvidence(
                evidence_type=EvidenceType.PDF_TEXT,
                evidence_source="pdf_text",
                evidence_reference="W12X26",
                evidence_strength=EvidenceStrength.EXPLICIT,
            )
        ],
    )
