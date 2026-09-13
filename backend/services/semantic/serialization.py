"""``drawing_semantics.json`` sidecar serialization -- the one canonical
serialization path for ``SemanticDocument`` (Section 29/30).

``load_semantic_document`` accepts payloads from either legacy schema this
consolidation replaces (Section 31): the old semantic_preprocessor sidecar
(no ``schema`` key, ``schema_version`` like ``"0.1.x"``) and the old A8
``drawing_semantics_v1`` row-list emitted by
``services.prediction.drawing_semantics``. New writes always use
``SCHEMA_VERSION`` ("2.0"). This module does not keep two model types alive
-- every legacy shape is converted into today's ``SemanticDocument`` /
``SemanticAnnotation`` on load; nothing downstream ever sees the old shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from services.semantic.models import (
    SCHEMA_VERSION,
    DrawingLanguageRule,
    EvidenceRecord,
    EvidenceStrength,
    EvidenceType,
    GeometryAssociation,
    GeometryEvidence,
    GeometryProvider,
    Modifier,
    OperationKind,
    OperationRecord,
    RepairCandidate,
    ReviewState,
    ReviewStatus,
    ScoreValue,
    SemanticAnnotation,
    SemanticDocument,
    SourceFragment,
    StructuralParse,
)


def _score_from_dict(raw: Optional[Dict[str, Any]]) -> Optional[ScoreValue]:
    if not raw:
        return None
    return ScoreValue(
        value=float(raw["value"]),
        kind=raw.get("kind", "deterministic"),
        calibrated=bool(raw.get("calibrated", False)),
        model_name=raw.get("model_name"),
        model_version=raw.get("model_version"),
    )


def _evidence_from_dict(raw: Dict[str, Any]) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=raw.get("evidence_id", ""),
        evidence_type=EvidenceType(raw.get("evidence_type", "other")),
        source=raw.get("source", ""),
        strength=EvidenceStrength(raw.get("strength", "unknown")),
        reference=raw.get("reference"),
        score=_score_from_dict(raw.get("score")),
        page=raw.get("page"),
        bbox=raw.get("bbox"),
        notes=raw.get("notes"),
        details=raw.get("details") or {},
    )


def _repair_candidate_from_dict(raw: Dict[str, Any]) -> RepairCandidate:
    return RepairCandidate(
        candidate_text=raw["candidate_text"],
        rank=raw.get("rank", 0),
        family=raw.get("family"),
        catalog_valid=bool(raw.get("catalog_valid", True)),
        scores=[_score_from_dict(s) for s in raw.get("scores") or [] if s],
        evidence=[_evidence_from_dict(e) for e in raw.get("evidence") or []],
        reason_codes=list(raw.get("reason_codes") or []),
        source=raw.get("source", ""),
        model_version=raw.get("model_version"),
    )

DRAWING_SEMANTICS_SCHEMA = "drawing_semantics_v2"


def to_dict(document: SemanticDocument) -> Dict[str, Any]:
    return document.to_dict()


def to_json(document: SemanticDocument, *, indent: int = 2) -> str:
    return json.dumps(document.to_dict(), indent=indent, sort_keys=False)


def write_document(path: Union[str, Path], document: SemanticDocument) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = document.to_dict()
    payload.setdefault("schema", DRAWING_SEMANTICS_SCHEMA)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def validate_document(payload: Dict[str, Any]) -> List[str]:
    """Return a list of schema problems (empty => OK)."""

    errors: List[str] = []
    if not payload.get("document_id"):
        errors.append("missing_document_id")
    anns = payload.get("annotations")
    if not isinstance(anns, list):
        errors.append("annotations_not_list")
        return errors
    for i, ann in enumerate(anns):
        if not isinstance(ann, dict):
            errors.append(f"annotation_{i}_not_object")
            continue
        if "original_text" not in ann:
            errors.append(f"annotation_{i}_missing_original_text")
        if ann.get("original_text_preserved") is False:
            errors.append(f"annotation_{i}_original_not_preserved")
    return errors


# ---------------------------------------------------------------------------
# Legacy loaders (Section 31) -- backward READING only. The runtime object
# coming out of every branch below is the one current SemanticDocument.
# ---------------------------------------------------------------------------


def load_semantic_document(data: Dict[str, Any]) -> SemanticDocument:
    version = str(data.get("schema_version") or "")
    if version.startswith("2."):
        return _load_current(data)
    if data.get("schema") == "drawing_semantics_v1" or "semantic_contract_version" in data:
        return _load_legacy_a8_rows(data)
    return _load_legacy_preprocessor(data)


def _load_current(data: Dict[str, Any]) -> SemanticDocument:
    annotations = [_annotation_from_current(a) for a in data.get("annotations", [])]
    rules = [
        DrawingLanguageRule(
            rule_id=r.get("rule_id", ""),
            trigger=r.get("trigger", ""),
            result=r.get("result", ""),
            status=r.get("rule_status", "source_verified"),
            scope=r.get("scope") or {},
        )
        for r in data.get("drawing_language_rules", [])
    ]
    geometry = [
        GeometryEvidence(
            geometry_id=g["geometry_id"],
            provider=GeometryProvider(g.get("provider", "unavailable")),
            geometry_type=g.get("geometry_type", "unknown"),
            bbox=g.get("bbox"),
            centroid=g.get("centroid"),
            metadata=g.get("metadata") or {},
        )
        for g in (data.get("geometry_evidence") or data.get("grasshopper_geometry") or [])
    ]
    return SemanticDocument(
        document_id=data.get("document_id", ""),
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        input_pdf_sha256=data.get("input_pdf_sha256"),
        pipeline_version=data.get("pipeline_version") or SCHEMA_VERSION,
        catalog_version=data.get("catalog_version"),
        annotations=annotations,
        drawing_language_rules=rules,
        geometry_evidence=geometry,
        diagnostics=data.get("diagnostics") or {},
        metrics=data.get("metrics") or {},
    )


def _annotation_from_current(a: Dict[str, Any]) -> SemanticAnnotation:
    ops = [
        OperationRecord(
            operation=OperationKind(o.get("operation", "keep")),
            input_text=o.get("input_text"),
            output_text=o.get("output_text"),
            reason_codes=list(o.get("reason_codes") or []),
            evidence=[_evidence_from_dict(e) for e in o.get("evidence") or []],
            score=_score_from_dict(o.get("score")),
            deterministic=bool(o.get("deterministic", True)),
            semantic_information_added=bool(o.get("semantic_information_added", False)),
            provenance=o.get("provenance"),
            accepted=bool(o.get("accepted", True)),
            notes=o.get("notes"),
        )
        for o in a.get("operations", [])
    ]
    review_raw = a.get("review") or {}
    review = ReviewState(
        status=ReviewStatus(review_raw.get("status", a.get("review_status", "pending"))),
        resolved_text=review_raw.get("resolved_text"),
        reason=review_raw.get("reason"),
        comment=review_raw.get("comment"),
        reviewed_at=review_raw.get("reviewed_at"),
        reviewed_by=review_raw.get("reviewed_by"),
        history=list(review_raw.get("history") or []),
    )
    geometry_assocs = [
        GeometryAssociation(
            geometry_id=g["geometry_id"],
            provider=GeometryProvider(g.get("provider", "unavailable")),
            rank=g.get("rank"),
            verified=bool(g.get("verified", False)),
            review_status=ReviewStatus(g.get("review_status", "pending")),
        )
        for g in a.get("geometry_associations", [])
    ]
    return SemanticAnnotation(
        annotation_id=a["annotation_id"],
        original_text=a.get("original_text", ""),
        document_id=a.get("document_id"),
        page=a.get("page"),
        source_fragment_ids=list(a.get("source_fragment_ids") or []),
        source_fragments=[
            SourceFragment(primitive_id=f["primitive_id"], text=f["text"], bbox=f["bbox"])
            for f in a.get("source_fragments", [])
        ],
        semantic_bbox=a.get("semantic_bbox"),
        original_anchor=a.get("original_anchor"),
        original_axis=a.get("original_axis"),
        primary_label=a.get("primary_label"),
        modifiers=[
            Modifier(type=m["type"], raw_text=m["raw_text"], value=m["value"])
            for m in a.get("modifiers", [])
        ],
        grouping_reasons=list(a.get("grouping_reasons") or []),
        structural_parse=(
            StructuralParse(
                is_structural=a["structural_parse"]["is_structural"],
                family=a["structural_parse"].get("family"),
                grammar=a["structural_parse"].get("grammar"),
                fields=a["structural_parse"].get("fields") or {},
                complete=bool(a["structural_parse"].get("complete", True)),
                catalog_status=a["structural_parse"].get("catalog_status", "unknown"),
                parser_reason=a["structural_parse"].get("parser_reason"),
            )
            if a.get("structural_parse")
            else None
        ),
        operations=ops,
        evidence=[_evidence_from_dict(e) for e in a.get("evidence") or []],
        repair_candidates=[_repair_candidate_from_dict(c) for c in a.get("repair_candidates") or []],
        takeoff_eligible=a.get("takeoff_eligible"),
        geometry_associations=geometry_assocs,
        review=review,
        pipeline_version=a.get("pipeline_version"),
        created_by=a.get("created_by"),
    )


def _load_legacy_preprocessor(data: Dict[str, Any]) -> SemanticDocument:
    """Old ``services.semantic_preprocessor.models`` sidecar shape: a single
    ``correction`` object per annotation instead of an ``operations`` list."""

    annotations: List[SemanticAnnotation] = []
    for a in data.get("annotations", []):
        correction = a.get("correction") or {}
        op_raw = correction.get("operation", "none")
        ops: List[OperationRecord] = []
        if op_raw != "none" or correction.get("canonical"):
            ops.append(
                OperationRecord(
                    operation=OperationKind(op_raw),
                    input_text=correction.get("original"),
                    output_text=correction.get("canonical"),
                    reason_codes=list(correction.get("reason_codes") or []),
                    deterministic=not correction.get("confidence_is_calibrated", False),
                    accepted=True,
                )
            )
        geometry_assocs = [
            GeometryAssociation(
                geometry_id=g["geometry_id"],
                provider=GeometryProvider.PDF_VECTOR,
                verified=bool(g.get("verified", False)),
                review_status=ReviewStatus(g.get("review_status", "pending")),
            )
            for g in a.get("geometry_associations", [])
        ]
        annotations.append(
            SemanticAnnotation(
                annotation_id=a["annotation_id"],
                original_text=a.get("original_text", ""),
                page=a.get("page"),
                source_fragment_ids=list(a.get("source_fragment_ids") or []),
                source_fragments=[
                    SourceFragment(primitive_id=f["primitive_id"], text=f["text"], bbox=f["bbox"])
                    for f in a.get("source_fragments", [])
                ],
                semantic_bbox=a.get("semantic_bbox"),
                primary_label=a.get("primary_label"),
                grouping_reasons=list(a.get("grouping_reasons") or []),
                operations=ops,
                geometry_associations=geometry_assocs,
                review=ReviewState(status=ReviewStatus(a.get("review_status", "pending"))),
            )
        )
    return SemanticDocument(
        document_id=data.get("document_id", ""),
        input_pdf_sha256=data.get("input_pdf_sha256"),
        annotations=annotations,
        diagnostics=data.get("diagnostics") or {},
        metrics=data.get("metrics") or {},
    )


def _load_legacy_a8_rows(data: Dict[str, Any]) -> SemanticDocument:
    """Old ``services.prediction.semantic_contract`` A8 row-list shape."""

    annotations: List[SemanticAnnotation] = []
    for row in data.get("annotations", []):
        takeoff = row.get("takeoff_eligible")
        annotations.append(
            SemanticAnnotation(
                annotation_id=row.get("annotation_id", "unknown"),
                original_text=row.get("raw_text", ""),
                document_id=row.get("document_id"),
                page=row.get("source_page"),
                semantic_bbox=row.get("source_bbox"),
                primary_label=row.get("normalized_text"),
                takeoff_eligible=bool(takeoff) if takeoff is not None else None,
                review=ReviewState(
                    status=ReviewStatus.NEEDS_REVIEW
                    if row.get("review_required")
                    else ReviewStatus.PENDING,
                    reason=row.get("review_reason"),
                ),
            )
        )
    return SemanticDocument(
        document_id=data.get("document_id", ""),
        annotations=annotations,
    )
