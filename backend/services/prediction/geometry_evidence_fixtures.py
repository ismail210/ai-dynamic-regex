"""SYNTHETIC / TEST-ONLY geometry-evidence fixtures for the semantic model.

These fixtures demonstrate that future GH/PDF geometry evidence can be
represented without changing semantic labels or bypassing incomplete L/2L
abstention. They are **not** production RH_OUT captures and must not be
treated as a frozen GH DataTree contract.

Built on the unified model in ``services.semantic.models``. Association
outcomes (agreement / GH-only / PDF-only / conflict / ambiguous) are expressed
through ``geometry_associations`` -- provider, ``geometry_id`` and
``verified`` -- because the live model has no ``GeometryAssociationStatus``
enum; ``backend/GEOMETRY_EVIDENCE_CONTRACT.md`` still describes that
pre-unification shape.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from services.semantic.models import (
    EvidenceRecord,
    EvidenceStrength,
    EvidenceType,
    GeometryAssociation,
    GeometryProvider,
    OperationKind,
    ReviewState,
    ReviewStatus,
    SemanticAnnotation,
    StructuralParse,
)

FIXTURE_MARK = {
    "synthetic_or_test_only": True,
    "not_production_rh_out": True,
    "beam_txt_crv_index_assumed_equal": False,
    "beam_element_id_semantics": "UNKNOWN_until_G0",
    "pdf_rhino_transform": "NOT_CALIBRATED",
    "rh_out_datatree_contract": "UNKNOWN_until_G0",
}


def _association(
    geometry_id: str,
    provider: GeometryProvider,
    *,
    coordinate_frame: str = "unknown",
    **metadata: object,
) -> GeometryAssociation:
    evidence_type = (
        EvidenceType.GRASSHOPPER_GEOMETRY
        if provider is GeometryProvider.GRASSHOPPER
        else EvidenceType.PDF_GEOMETRY
    )
    return GeometryAssociation(
        geometry_id=geometry_id,
        provider=provider,
        coordinate_frame=coordinate_frame,
        evidence=[
            EvidenceRecord(
                evidence_id=f"{provider.value}:{geometry_id}",
                evidence_type=evidence_type,
                source=f"{provider.value}_synthetic",
                reference=geometry_id,
                strength=EvidenceStrength.INFERRED,
                notes="SYNTHETIC -- not a live RH_OUT path",
                details={**FIXTURE_MARK, **metadata},
            )
        ],
    )


def _annotation(
    annotation_id: str,
    text: str,
    family: str,
    associations: List[GeometryAssociation],
    *,
    page: Optional[int] = None,
    bbox: Optional[List[float]] = None,
    incomplete: bool = False,
    review_reason: Optional[str] = None,
) -> SemanticAnnotation:
    return SemanticAnnotation(
        annotation_id=annotation_id,
        original_text=text,
        page=page,
        semantic_bbox=bbox,
        primary_label=text,
        structural_parse=StructuralParse(
            is_structural=True,
            family=family,
            grammar="incomplete" if incomplete else None,
        ),
        takeoff_eligible=not incomplete,
        evidence=[
            EvidenceRecord(
                evidence_id=f"{annotation_id}:pdf_text",
                evidence_type=EvidenceType.PDF_TEXT,
                source="pdf_text",
                reference=text,
                strength=EvidenceStrength.EXPLICIT,
            )
        ],
        geometry_associations=associations,
        review=(
            ReviewState(status=ReviewStatus.NEEDS_REVIEW, reason=review_reason)
            if review_reason
            else ReviewState()
        ),
        created_by="geometry_evidence_fixtures",
    )


def fixture_agreement() -> SemanticAnnotation:
    """AGREEMENT -- GH candidate and PDF association point to the same ref."""

    ref = "synth_member_A"
    return _annotation(
        "fix_geom_agreement_w12x26",
        "W12X26",
        "W",
        [
            _association(ref, GeometryProvider.PDF_VECTOR),
            _association(ref, GeometryProvider.GRASSHOPPER),
        ],
        page=1,
        bbox=[100.0, 200.0, 140.0, 215.0],
    )


def fixture_gh_only() -> SemanticAnnotation:
    """GH_ONLY -- GH proposes geometry; no PDF association evidence."""

    return _annotation(
        "fix_geom_gh_only_w16x26",
        "W16X26",
        "W",
        [_association("synth_gh_beam_91", GeometryProvider.GRASSHOPPER)],
        page=2,
        bbox=[50.0, 50.0, 90.0, 65.0],
        review_reason="geometry_gh_only_review_optional",
    )


def fixture_pdf_only() -> SemanticAnnotation:
    """PDF_ONLY -- PDF member_geometry-style evidence; no GH."""

    return _annotation(
        "fix_geom_pdf_only_w21x44",
        "W21X44",
        "W",
        [
            _association(
                "synth_pdf_member_7",
                GeometryProvider.PDF_VECTOR,
                coordinate_frame="pdf_page",
            )
        ],
        page=3,
        bbox=[10.0, 10.0, 40.0, 25.0],
    )


def fixture_conflict() -> SemanticAnnotation:
    """CONFLICT -- GH and PDF point at different candidate refs; none verified."""

    return _annotation(
        "fix_geom_conflict_w14x22",
        "W14X22",
        "W",
        [
            _association("synth_pdf_member_3", GeometryProvider.PDF_VECTOR),
            _association("synth_gh_beam_44", GeometryProvider.GRASSHOPPER),
        ],
        page=4,
        review_reason="geometry_association_conflict",
    )


def fixture_ambiguous() -> SemanticAnnotation:
    """AMBIGUOUS -- multiple candidates; none selected or verified."""

    return _annotation(
        "fix_geom_ambiguous_hss6x6x3_8",
        "HSS6X6X3/8",
        "HSS",
        [
            _association(ref, GeometryProvider.GRASSHOPPER, forced_selection=False)
            for ref in ("synth_cand_1", "synth_cand_2", "synth_cand_3")
        ],
        page=5,
        review_reason="geometry_association_ambiguous",
    )


def fixture_incomplete_l_with_geometry() -> SemanticAnnotation:
    """INCOMPLETE_LABEL_WITH_GEOMETRY -- L4X4 + geometry still abstains."""

    return _annotation(
        "fix_geom_incomplete_l4x4",
        "L4X4",
        "L",
        [
            _association(
                "synth_angle_member_12",
                GeometryProvider.GRASSHOPPER,
                must_not_complete_thickness=True,
            )
        ],
        page=6,
        bbox=[200.0, 300.0, 230.0, 312.0],
        incomplete=True,
        review_reason="incomplete_angle_missing_thickness",
    )


def fixture_incomplete_2l_with_geometry() -> SemanticAnnotation:
    """Incomplete 2L + geometry still abstains."""

    return _annotation(
        "fix_geom_incomplete_2l4x4",
        "2L4X4",
        "2L",
        [
            _association(
                "synth_2l_member_5",
                GeometryProvider.GRASSHOPPER,
                must_not_complete_thickness=True,
            )
        ],
        page=7,
        incomplete=True,
        review_reason="incomplete_angle_missing_thickness",
    )


def fixture_multiple_annotations_one_geometry() -> List[SemanticAnnotation]:
    """Two distinct annotations share the same candidate geometry ref."""

    shared = "synth_shared_beam_100"
    return [
        _annotation(
            annotation_id,
            text,
            "W",
            [_association(shared, GeometryProvider.GRASSHOPPER, shared_geometry_ref=shared)],
        )
        for annotation_id, text in (
            ("fix_geom_multi_ann_a", "W18X35"),
            ("fix_geom_multi_ann_b", "W18X40"),
        )
    ]


def fixture_one_annotation_multiple_geometry_candidates() -> SemanticAnnotation:
    """ONE_ANNOTATION_MULTIPLE_GEOMETRY_CANDIDATES -- preserve ambiguity."""

    return fixture_ambiguous()


def all_fixture_annotations() -> Dict[str, SemanticAnnotation | List[SemanticAnnotation]]:
    return {
        "agreement": fixture_agreement(),
        "gh_only": fixture_gh_only(),
        "pdf_only": fixture_pdf_only(),
        "conflict": fixture_conflict(),
        "ambiguous": fixture_ambiguous(),
        "incomplete_l_with_geometry": fixture_incomplete_l_with_geometry(),
        "incomplete_2l_with_geometry": fixture_incomplete_2l_with_geometry(),
        "multiple_annotations_one_geometry": fixture_multiple_annotations_one_geometry(),
        "one_annotation_multiple_geometry_candidates": (
            fixture_one_annotation_multiple_geometry_candidates()
        ),
    }


def assert_geometry_does_not_complete(ann: SemanticAnnotation) -> None:
    """Safety helper for tests -- geometry must not invent thickness fields."""

    if ann.is_complete is False:
        assert ann.takeoff_eligible is False
        assert ann.effective_text == ann.original_text
        assert not any(
            op.operation is OperationKind.COMPLETION and op.accepted
            for op in ann.operations
        )
