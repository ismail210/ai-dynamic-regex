"""Read-only projection from an existing production prediction payload into
the canonical semantic model (replaces
``services.prediction.semantic_contract.project_semantic_annotation``).

This module does **not** run normalization / repair / completion /
association intelligence, does not change takeoff eligibility, and does not
require Grasshopper. Production prediction payloads already carry
``raw_text``, ``normalized_text``, ``completion_status``, ``takeoff_eligible``,
``needs_review``, etc.; this maps those fields into ``SemanticAnnotation``
without mutating producers. See ``docs/architecture/unified_semantic_contract.md``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.semantic.models import (
    EvidenceRecord,
    EvidenceStrength,
    EvidenceType,
    GeometryAssociation,
    GeometryProvider,
    OperationRecord,
    ReviewState,
    ReviewStatus,
    ScoreValue,
    SemanticAnnotation,
)

# Aligned with existing production string values (orchestrator / multimodal).
COMPLETION_STATUS_COMPLETE = "complete"
COMPLETION_STATUS_MISSING_THICKNESS = "missing_thickness"


def project_semantic_annotation(payload: Dict[str, Any]) -> SemanticAnnotation:
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
    # Do not invent NORMALIZATION/REPAIR/COMPLETION from string diffs here --
    # that would be new semantic behavior. If the raw and normalized/final
    # text differ, record it as a KEEP-shaped observation only when the
    # producer already tells us the operation kind explicitly.
    completion_raw = str(payload.get("completion_status") or COMPLETION_STATUS_COMPLETE)
    is_missing_thickness = completion_raw == COMPLETION_STATUS_MISSING_THICKNESS

    review_required = bool(
        payload.get("needs_review")
        if payload.get("needs_review") is not None
        else payload.get("review_required")
    )

    geometry_associations: List[GeometryAssociation] = []
    member_geometry = payload.get("member_geometry")
    if isinstance(member_geometry, dict) and member_geometry:
        geometry_associations.append(
            GeometryAssociation(
                geometry_id=str(member_geometry.get("object_id") or "unknown"),
                provider=GeometryProvider.PDF_VECTOR,
                score=(
                    ScoreValue(value=float(member_geometry["confidence"]), kind="deterministic")
                    if member_geometry.get("confidence") is not None
                    else None
                ),
                evidence=[
                    EvidenceRecord(
                        evidence_id=f"member_geometry:{member_geometry.get('object_id')}",
                        evidence_type=EvidenceType.PDF_GEOMETRY,
                        source="member_geometry",
                        strength=EvidenceStrength.INFERRED,
                        details=dict(member_geometry),
                    )
                ],
            )
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
    score: Optional[ScoreValue]
    if isinstance(conf, dict):
        value = conf.get("overall") or conf.get("score")
        score = ScoreValue(value=float(value), kind="raw_model_score") if value is not None else None
    elif conf is None:
        score = None
    else:
        try:
            score = ScoreValue(value=float(conf), kind="raw_model_score")
        except (TypeError, ValueError):
            score = None

    extraction_source: Optional[str] = None
    if payload.get("prediction_source"):
        extraction_source = str(payload["prediction_source"])
    else:
        source_text = payload.get("source_text")
        if isinstance(source_text, dict) and source_text.get("extraction_method"):
            extraction_source = str(source_text["extraction_method"])

    review_status = ReviewStatus.NEEDS_REVIEW if review_required else ReviewStatus.PENDING
    review_reason = str(payload["review_reason"]) if payload.get("review_reason") else None
    if is_missing_thickness and not review_reason:
        review_reason = "incomplete_angle_missing_thickness"

    return SemanticAnnotation(
        annotation_id=annotation_id,
        original_text=raw_text,
        document_id=(str(payload["document_id"]) if payload.get("document_id") else None),
        page=(int(payload["page_number"]) if payload.get("page_number") is not None else None),
        semantic_bbox=(
            list(payload["bounding_box"])
            if isinstance(payload.get("bounding_box"), (list, tuple))
            else None
        ),
        extraction_source=extraction_source,
        primary_label=normalized_text,
        operations=operations,
        takeoff_eligible=takeoff,
        evidence=(
            [
                EvidenceRecord(
                    evidence_id=f"{annotation_id}:confidence",
                    evidence_type=EvidenceType.PDF_TEXT,
                    source=extraction_source or "prediction_engine",
                    strength=EvidenceStrength.EXPLICIT,
                    score=score,
                )
            ]
            if score is not None
            else []
        ),
        geometry_associations=geometry_associations,
        review=ReviewState(status=review_status, reason=review_reason),
        created_by="project_semantic_annotation",
        structural_parse=None if family is None else _structural_parse_stub(
            str(family).upper(), is_missing_thickness
        ),
    )


def _structural_parse_stub(family: str, incomplete: bool):
    from services.semantic.models import StructuralParse

    return StructuralParse(
        is_structural=True,
        family=family,
        grammar="incomplete" if incomplete else None,
    )
