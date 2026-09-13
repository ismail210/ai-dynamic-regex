"""SemanticPreprocessor orchestration (Section 15/31/40).

``process_primitives`` is the core, directly testable entry point -- it
takes already-extracted primitives so tests don't need a real PDF fixture
for every scenario. ``process_pdf`` is the real-world entry point that
wraps it around ``extraction.py``.

The one invariant every call path here must uphold: geometry evidence
(Grasshopper or otherwise) can shift which geometry an annotation is
associated with, but it can NEVER change what an annotation's label says.
Only ``normalization.canonicalize`` (deterministic) and
``drawing_language_profile.resolve_completion`` (source-verified drawing
evidence) are allowed to touch ``correction.canonical``.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from services.semantic.models import (
    EvidenceRecord,
    EvidenceStrength,
    EvidenceType,
    OperationKind,
    OperationRecord,
    ReviewStatus,
    SemanticAnnotation,
    SemanticDocument,
)
from services.semantic_preprocessor import association, normalization
from services.semantic_preprocessor.coordinate_transform import CoordinateTransform
from services.semantic_preprocessor.drawing_language_profile import resolve_completion
from services.semantic_preprocessor.geometry_evidence import (
    GeometryEvidenceProvider,
    NullGeometryEvidenceProvider,
)
from services.semantic_preprocessor.grouping import group_primitives
from services.semantic_preprocessor.models import TextPrimitive


def _combine_review_status(annotation: SemanticAnnotation) -> ReviewStatus:
    current = annotation.current_operation
    reason_codes = current.reason_codes if current else []
    if "drawing_language_conflict" in reason_codes:
        return ReviewStatus.NEEDS_REVIEW
    if current is not None and current.operation == OperationKind.REPAIR:
        return ReviewStatus.NEEDS_REVIEW
    if any(c.review_status == ReviewStatus.NEEDS_REVIEW for c in annotation.geometry_associations):
        return ReviewStatus.NEEDS_REVIEW
    if current is not None and current.operation != OperationKind.KEEP:
        return ReviewStatus.AUTO_ACCEPTED
    return ReviewStatus.PENDING


def _evidence_for_rule_ids(evidence_ids: List[str]) -> List[EvidenceRecord]:
    return [
        EvidenceRecord(
            evidence_id=rule_id,
            evidence_type=EvidenceType.DRAWING_RULE,
            source="drawing_language_rule",
            reference=rule_id,
            strength=EvidenceStrength.EXPLICIT,
        )
        for rule_id in evidence_ids
    ]


def _apply_correction(annotation: SemanticAnnotation, drawing_language_rules: List[Dict[str, Any]]) -> None:
    label = annotation.primary_label or ""
    result = normalization.canonicalize(label)
    annotation.structural_parse = result.parse
    annotation.operations.append(result.operation)

    if result.parse.is_structural and result.parse.grammar == "incomplete":
        resolution = resolve_completion(label, annotation.page, drawing_language_rules)
        if resolution.allowed and resolution.canonical:
            annotation.operations.append(
                OperationRecord(
                    operation=OperationKind.COMPLETION,
                    input_text=label,
                    output_text=resolution.canonical,
                    score=None,
                    deterministic=True,
                    semantic_information_added=True,
                    provenance="drawing_language_rule",
                    reason_codes=[resolution.reason],
                    evidence=_evidence_for_rule_ids(resolution.evidence_ids),
                )
            )
        elif resolution.reason == "conflicting_source_verified_rules":
            annotation.operations.append(
                OperationRecord(
                    operation=OperationKind.KEEP,
                    input_text=label,
                    output_text=label,
                    reason_codes=["drawing_language_conflict"],
                    evidence=_evidence_for_rule_ids(resolution.evidence_ids),
                )
            )
        # else: no rule / no source-verified rule -- the operation history
        # stays at the deterministic layer's KEEP result. A bare "W8" is
        # left exactly as "W8"; it is never completed from statistics or
        # from geometry.


def process_primitives(
    primitives: List[TextPrimitive],
    document_id: str,
    *,
    input_pdf_sha256: Optional[str] = None,
    drawing_language_rules: Optional[List[Dict[str, Any]]] = None,
    geometry_provider: Optional[GeometryEvidenceProvider] = None,
    coordinate_transform: Optional[CoordinateTransform] = None,
    ghx_text_pairs: Optional[List[Dict[str, Any]]] = None,
) -> SemanticDocument:
    drawing_language_rules = drawing_language_rules or []
    active_geometry_provider: GeometryEvidenceProvider = geometry_provider or NullGeometryEvidenceProvider()
    ghx_text_pairs = ghx_text_pairs or []

    pages = sorted({p.page for p in primitives})
    annotations: List[SemanticAnnotation] = []
    for page in pages:
        annotations.extend(group_primitives(primitives, page, document_id))

    for annotation in annotations:
        _apply_correction(annotation, drawing_language_rules)

    geometry_list = active_geometry_provider.extract_geometry({"document_id": document_id})

    discrepancies: List[Dict[str, Any]] = []
    for annotation in annotations:
        ghx_candidate, discrepancy_text = association.associate_via_ghx_pairing(
            annotation, ghx_text_pairs
        )
        pdf_candidate = association.associate_via_nearest_geometry(
            annotation, geometry_list, coordinate_transform
        )
        annotation.geometry_associations = association.fuse_candidates(ghx_candidate, pdf_candidate)
        if discrepancy_text:
            discrepancies.append({
                "annotation_id": annotation.annotation_id,
                "annotation_label": annotation.primary_label,
                "ghx_text": discrepancy_text,
                "note": (
                    "Grasshopper's paired text differs from this annotation's label. "
                    "This is geometry-association evidence only -- it does NOT change "
                    "the annotation's canonical label (see Section 28/45)."
                ),
            })
        annotation.review.status = _combine_review_status(annotation)

    document = SemanticDocument(
        document_id=document_id,
        input_pdf_sha256=input_pdf_sha256,
        annotations=annotations,
        drawing_language_rules=drawing_language_rules,
        geometry_evidence=geometry_list,
        coordinate_frames=[coordinate_transform] if coordinate_transform else [],
        diagnostics={"ghx_text_discrepancies": discrepancies},
        metrics={
            "annotation_count": len(annotations),
            "auto_accepted_count": sum(
                1 for a in annotations if a.review_status == ReviewStatus.AUTO_ACCEPTED
            ),
            "needs_review_count": sum(
                1 for a in annotations if a.review_status == ReviewStatus.NEEDS_REVIEW
            ),
        },
    )
    return document


def process_pdf(
    pdf_path: str,
    *,
    drawing_language_rules: Optional[List[Dict[str, Any]]] = None,
    geometry_provider: Optional[GeometryEvidenceProvider] = None,
    coordinate_transform: Optional[CoordinateTransform] = None,
    ghx_text_pairs: Optional[List[Dict[str, Any]]] = None,
) -> SemanticDocument:
    """Real entry point: PDF path in, SemanticDocument out.

    Runs with ``geometry_provider=None`` just as reliably as with one
    supplied (Section 31) -- Grasshopper/Rhino.Compute availability never
    blocks this call.
    """
    from services.pdf_parser import extract_document_structure
    from services.semantic_preprocessor.extraction import build_text_primitives

    structure = extract_document_structure(pdf_path)
    primitives, _page_classes = build_text_primitives(structure)

    with open(pdf_path, "rb") as f:
        pdf_sha256 = hashlib.sha256(f.read()).hexdigest()

    return process_primitives(
        primitives,
        document_id=structure.get("document_id") or pdf_sha256[:16],
        input_pdf_sha256=pdf_sha256,
        drawing_language_rules=drawing_language_rules,
        geometry_provider=geometry_provider,
        coordinate_transform=coordinate_transform,
        ghx_text_pairs=ghx_text_pairs,
    )
