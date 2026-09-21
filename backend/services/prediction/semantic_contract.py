"""DEPRECATED shim -- the semantic annotation contract now lives in
``services.semantic`` (see ``docs/architecture/unified_semantic_contract.md``
for why this module and ``services.semantic_preprocessor.models`` were
unified into one domain model).

Kept for two things only, neither of which has a canonical replacement:
(1) the ``example_*`` schema-demonstration functions below, referenced by
``tests/test_semantic_contract.py``; (2) the two legacy
``COMPLETION_STATUS_*`` string constants. Every class this module still
imports (``SemanticAnnotation``, ``EvidenceType``, ``EvidenceStrength``,
``ReviewStatus``, ``GeometryProvider``) is used only internally by the
functions below -- there is exactly ONE definition of each, in
``services.semantic.models``, never a second one; see
``tests/test_deprecated_import_compatibility.py`` for the identity proof.
All previously re-exported symbols with no remaining caller
(``SEMANTIC_CONTRACT_VERSION``, ``SemanticEvidence``, ``GeometryAssociation``,
``SemanticOperationKind``, ``OperationRecord``, ``SemanticDocument``,
``project_semantic_annotation``) were removed from this module -- import
them from ``services.semantic.models`` / ``services.semantic.projection``
directly.
"""

from __future__ import annotations

from services.semantic.models import (
    EvidenceStrength,
    EvidenceType,
    GeometryProvider,
    ReviewStatus,
    SemanticAnnotation,
)

# Legacy enum aliases -- old names for concepts the unified model expresses
# differently now. CompletionStatus / GeometryRelationship no longer exist
# as their own types: completeness lives on ``StructuralParse.complete`` and
# geometry availability is just "geometry_associations is empty or not",
# but old call sites that only need the two legacy string values keep working.
COMPLETION_STATUS_COMPLETE = "complete"
COMPLETION_STATUS_MISSING_THICKNESS = "missing_thickness"


def example_normalization_w8x10() -> SemanticAnnotation:
    from services.semantic.models import EvidenceRecord as _Evidence
    from services.semantic.models import OperationRecord as _Op
    from services.semantic.models import OperationKind as _Kind

    ann = SemanticAnnotation(
        annotation_id="ex_norm_w8x10",
        original_text="W8×10",
        primary_label="W8X10",
    )
    ann.operations.append(
        _Op(operation=_Kind.NORMALIZATION, input_text="W8×10", output_text="W8X10")
    )
    ann.takeoff_eligible = True
    ann.evidence.append(
        _Evidence(
            evidence_id="ex_norm_w8x10:pdf_text",
            evidence_type=EvidenceType.PDF_TEXT,
            source="pdf_text",
            reference="W8×10",
            strength=EvidenceStrength.EXPLICIT,
        )
    )
    return ann


def example_repair_corrupted_w8() -> SemanticAnnotation:
    from services.semantic.models import OperationRecord as _Op
    from services.semantic.models import OperationKind as _Kind

    ann = SemanticAnnotation(annotation_id="ex_repair_w8xi0", original_text="W8XI0")
    ann.operations.append(
        _Op(operation=_Kind.REPAIR, input_text="W8XI0", output_text="W8X10", accepted=False)
    )
    ann.review.status = ReviewStatus.NEEDS_REVIEW
    ann.review.reason = "schema_example_only_not_implemented"
    return ann


def example_completion_candidate_w8() -> SemanticAnnotation:
    from services.semantic.models import OperationRecord as _Op
    from services.semantic.models import OperationKind as _Kind

    ann = SemanticAnnotation(annotation_id="ex_completion_w8", original_text="W8")
    ann.operations.append(
        _Op(
            operation=_Kind.COMPLETION,
            input_text="W8",
            output_text="W8X10",
            semantic_information_added=True,
            accepted=False,
            notes="candidate_only_requires_drawing_local_evidence",
        )
    )
    ann.review.status = ReviewStatus.NEEDS_REVIEW
    ann.review.reason = "schema_example_only_not_implemented"
    return ann


def example_l4x4_abstention() -> SemanticAnnotation:
    from services.semantic.models import StructuralParse

    return SemanticAnnotation(
        annotation_id="ex_abstain_l4x4",
        original_text="L4X4,",
        primary_label="L4X4",
        structural_parse=StructuralParse(is_structural=True, family="L", grammar="incomplete"),
        takeoff_eligible=False,
        review=_needs_review("incomplete_angle_missing_thickness"),
    )


def example_2l4x4_abstention() -> SemanticAnnotation:
    from services.semantic.models import StructuralParse

    return SemanticAnnotation(
        annotation_id="ex_abstain_2l4x4",
        original_text="2L4X4",
        primary_label="2L4X4",
        structural_parse=StructuralParse(is_structural=True, family="2L", grammar="incomplete"),
        takeoff_eligible=False,
        review=_needs_review("incomplete_angle_missing_thickness"),
    )


def example_association_with_optional_gh() -> SemanticAnnotation:
    from services.semantic.models import EvidenceRecord as _Evidence
    from services.semantic.models import GeometryAssociation as _Assoc

    ann = SemanticAnnotation(
        annotation_id="ex_assoc_w12x26",
        original_text="W12X26",
        primary_label="W12X26",
        takeoff_eligible=True,
    )
    ann.geometry_associations.append(
        _Assoc(
            geometry_id="unresolved",
            provider=GeometryProvider.GRASSHOPPER,
            evidence=[
                _Evidence(
                    evidence_id="ex_assoc_w12x26:ghx",
                    evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                    source="grasshopper",
                    reference="RH_OUT:BeamCrv unresolved_index",
                    strength=EvidenceStrength.INFERRED,
                    notes="GH optional; BeamTxt/BeamCrv pairing unproven",
                    details={"beam_txt_crv_index_assumed_equal": False},
                )
            ],
        )
    )
    ann.evidence.append(
        _Evidence(
            evidence_id="ex_assoc_w12x26:pdf_text",
            evidence_type=EvidenceType.PDF_TEXT,
            source="pdf_text",
            reference="W12X26",
            strength=EvidenceStrength.EXPLICIT,
        )
    )
    return ann


def _needs_review(reason: str):
    from services.semantic.models import ReviewState

    return ReviewState(status=ReviewStatus.NEEDS_REVIEW, reason=reason)
