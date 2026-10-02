"""SYNTHETIC / TEST-ONLY GeometryEvidence fixtures for the semantic contract.

These fixtures demonstrate that future GH/PDF geometry evidence can be
represented without changing semantic labels or bypassing incomplete L/2L
abstention. They are **not** production RH_OUT captures and must not be
treated as a frozen GH DataTree contract.

See ``backend/GEOMETRY_EVIDENCE_CONTRACT.md``.
"""

from __future__ import annotations

from typing import Dict, List

from services.prediction.semantic_contract import (
    CompletionStatus,
    EvidenceStrength,
    EvidenceType,
    GeometryAssociationStatus,
    GeometryEvidence,
    GeometryRelationship,
    OperationRecord,
    SemanticAnnotation,
    SemanticEvidence,
    SemanticOperationKind,
)

FIXTURE_MARK = {
    "synthetic_or_test_only": True,
    "not_production_rh_out": True,
    "beam_txt_crv_index_assumed_equal": False,
    "beam_element_id_semantics": "UNKNOWN_until_G0",
    "pdf_rhino_transform": "NOT_CALIBRATED",
    "rh_out_datatree_contract": "UNKNOWN_until_G0",
}


def _pdf_text_evidence(ref: str) -> SemanticEvidence:
    return SemanticEvidence(
        evidence_type=EvidenceType.PDF_TEXT,
        evidence_source="pdf_text",
        evidence_reference=ref,
        evidence_strength=EvidenceStrength.EXPLICIT,
    )


def fixture_agreement() -> SemanticAnnotation:
    """AGREEMENT — GH candidate and PDF association point to the same ref."""

    geom_ref = "synth_member_A"
    return SemanticAnnotation(
        annotation_id="fix_geom_agreement_w12x26",
        raw_text="W12X26",
        normalized_text="W12X26",
        structural_family="W",
        source_page=1,
        source_bbox=[100.0, 200.0, 140.0, 215.0],
        operations=[
            OperationRecord(
                operation=SemanticOperationKind.ASSOCIATION,
                input_text="W12X26",
                output_text="W12X26",
            )
        ],
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        review_required=False,
        evidence=[
            _pdf_text_evidence("W12X26"),
            SemanticEvidence(
                evidence_type=EvidenceType.PDF_GEOMETRY,
                evidence_source="pdf_member_geometry_synthetic",
                evidence_reference=geom_ref,
                evidence_strength=EvidenceStrength.INFERRED,
            ),
            SemanticEvidence(
                evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                evidence_source="grasshopper_synthetic",
                evidence_reference=geom_ref,
                evidence_strength=EvidenceStrength.INFERRED,
                notes="SYNTHETIC — not a live RH_OUT path",
            ),
        ],
        geometry_evidence=GeometryEvidence(
            available=True,
            provider="grasshopper+pdf",
            relationship=GeometryRelationship.ASSOCIATED_WITH,
            geometry_ref=geom_ref,
            geometry_type="beam_candidate_synthetic",
            confidence=0.9,
            coordinate_system="unknown",
            source="synthetic_fixture",
            association_status=GeometryAssociationStatus.AGREEMENT,
            candidate_refs=[geom_ref],
            native_metadata={
                **FIXTURE_MARK,
                "pdf_candidate_ref": geom_ref,
                "gh_candidate_ref": geom_ref,
            },
        ),
        created_by="geometry_evidence_fixtures",
    )


def fixture_gh_only() -> SemanticAnnotation:
    """GH_ONLY — GH proposes geometry; no PDF association evidence."""

    return SemanticAnnotation(
        annotation_id="fix_geom_gh_only_w16x26",
        raw_text="W16X26",
        normalized_text="W16X26",
        structural_family="W",
        source_page=2,
        source_bbox=[50.0, 50.0, 90.0, 65.0],
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        review_required=True,
        review_reason="geometry_gh_only_review_optional",
        evidence=[
            _pdf_text_evidence("W16X26"),
            SemanticEvidence(
                evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                evidence_source="grasshopper_synthetic",
                evidence_reference="synth_gh_beam_91",
                evidence_strength=EvidenceStrength.INFERRED,
                notes="SYNTHETIC GH_ONLY",
            ),
        ],
        geometry_evidence=GeometryEvidence(
            available=True,
            provider="grasshopper",
            relationship=GeometryRelationship.ASSOCIATED_WITH,
            geometry_ref="synth_gh_beam_91",
            geometry_type="beam_candidate_synthetic",
            confidence=None,
            coordinate_system="unknown",
            source="synthetic_fixture",
            association_status=GeometryAssociationStatus.GH_ONLY,
            candidate_refs=["synth_gh_beam_91"],
            native_metadata={**FIXTURE_MARK, "pdf_candidate_ref": None},
        ),
        created_by="geometry_evidence_fixtures",
    )


def fixture_pdf_only() -> SemanticAnnotation:
    """PDF_ONLY — PDF member_geometry-style evidence; no GH."""

    return SemanticAnnotation(
        annotation_id="fix_geom_pdf_only_w21x44",
        raw_text="W21X44",
        normalized_text="W21X44",
        structural_family="W",
        source_page=3,
        source_bbox=[10.0, 10.0, 40.0, 25.0],
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        evidence=[
            _pdf_text_evidence("W21X44"),
            SemanticEvidence(
                evidence_type=EvidenceType.PDF_GEOMETRY,
                evidence_source="pdf_member_geometry_synthetic",
                evidence_reference="synth_pdf_member_7",
                evidence_strength=EvidenceStrength.INFERRED,
            ),
        ],
        geometry_evidence=GeometryEvidence(
            available=True,
            provider="pdf",
            relationship=GeometryRelationship.ASSOCIATED_WITH,
            geometry_ref="synth_pdf_member_7",
            geometry_type="member_candidate",
            confidence=0.7,
            coordinate_system="pdf_page",
            source="synthetic_fixture",
            association_status=GeometryAssociationStatus.PDF_ONLY,
            candidate_refs=["synth_pdf_member_7"],
            native_metadata={**FIXTURE_MARK, "gh_candidate_ref": None},
        ),
        created_by="geometry_evidence_fixtures",
    )


def fixture_conflict() -> SemanticAnnotation:
    """CONFLICT — GH and PDF point at different candidate refs."""

    return SemanticAnnotation(
        annotation_id="fix_geom_conflict_w14x22",
        raw_text="W14X22",
        normalized_text="W14X22",
        structural_family="W",
        source_page=4,
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        review_required=True,
        review_reason="geometry_association_conflict",
        evidence=[
            _pdf_text_evidence("W14X22"),
            SemanticEvidence(
                evidence_type=EvidenceType.PDF_GEOMETRY,
                evidence_source="pdf_member_geometry_synthetic",
                evidence_reference="synth_pdf_member_3",
                evidence_strength=EvidenceStrength.INFERRED,
            ),
            SemanticEvidence(
                evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                evidence_source="grasshopper_synthetic",
                evidence_reference="synth_gh_beam_44",
                evidence_strength=EvidenceStrength.INFERRED,
            ),
        ],
        geometry_evidence=GeometryEvidence(
            available=True,
            provider="grasshopper+pdf",
            relationship=GeometryRelationship.UNKNOWN,
            geometry_ref=None,  # no forced selection
            geometry_type="beam_candidate_synthetic",
            confidence=None,
            coordinate_system="unknown",
            source="synthetic_fixture",
            association_status=GeometryAssociationStatus.CONFLICT,
            candidate_refs=["synth_pdf_member_3", "synth_gh_beam_44"],
            native_metadata={
                **FIXTURE_MARK,
                "pdf_candidate_ref": "synth_pdf_member_3",
                "gh_candidate_ref": "synth_gh_beam_44",
                "conflict": True,
            },
        ),
        created_by="geometry_evidence_fixtures",
    )


def fixture_ambiguous() -> SemanticAnnotation:
    """AMBIGUOUS — multiple candidates; none selected."""

    cands = ["synth_cand_1", "synth_cand_2", "synth_cand_3"]
    return SemanticAnnotation(
        annotation_id="fix_geom_ambiguous_hss6x6x3_8",
        raw_text="HSS6X6X3/8",
        normalized_text="HSS6X6X3/8",
        structural_family="HSS",
        source_page=5,
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        review_required=True,
        review_reason="geometry_association_ambiguous",
        evidence=[_pdf_text_evidence("HSS6X6X3/8")],
        geometry_evidence=GeometryEvidence(
            available=True,
            provider="grasshopper",
            relationship=GeometryRelationship.UNKNOWN,
            geometry_ref=None,
            geometry_type="beam_candidate_synthetic",
            confidence=None,
            coordinate_system="unknown",
            source="synthetic_fixture",
            association_status=GeometryAssociationStatus.AMBIGUOUS,
            candidate_refs=list(cands),
            native_metadata={**FIXTURE_MARK, "forced_selection": False},
        ),
        created_by="geometry_evidence_fixtures",
    )


def fixture_incomplete_l_with_geometry() -> SemanticAnnotation:
    """INCOMPLETE_LABEL_WITH_GEOMETRY — L4X4 + geometry still abstains."""

    return SemanticAnnotation(
        annotation_id="fix_geom_incomplete_l4x4",
        raw_text="L4X4",
        normalized_text="L4X4",
        structural_family="L",
        source_page=6,
        source_bbox=[200.0, 300.0, 230.0, 312.0],
        completion_status=CompletionStatus.MISSING_THICKNESS,
        takeoff_eligible=False,
        review_required=True,
        review_reason="incomplete_angle_missing_thickness",
        evidence=[
            _pdf_text_evidence("L4X4"),
            SemanticEvidence(
                evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                evidence_source="grasshopper_synthetic",
                evidence_reference="synth_angle_member_12",
                evidence_strength=EvidenceStrength.INFERRED,
                notes="geometry must not invent L4X4X1/4",
            ),
        ],
        geometry_evidence=GeometryEvidence(
            available=True,
            provider="grasshopper",
            relationship=GeometryRelationship.ASSOCIATED_WITH,
            geometry_ref="synth_angle_member_12",
            geometry_type="member_candidate_synthetic",
            confidence=0.8,
            coordinate_system="unknown",
            source="synthetic_fixture",
            association_status=GeometryAssociationStatus.GH_ONLY,
            candidate_refs=["synth_angle_member_12"],
            native_metadata={
                **FIXTURE_MARK,
                "must_not_complete_thickness": True,
            },
        ),
        created_by="geometry_evidence_fixtures",
    )


def fixture_incomplete_2l_with_geometry() -> SemanticAnnotation:
    """Incomplete 2L + geometry still abstains."""

    return SemanticAnnotation(
        annotation_id="fix_geom_incomplete_2l4x4",
        raw_text="2L4X4",
        normalized_text="2L4X4",
        structural_family="2L",
        source_page=7,
        completion_status=CompletionStatus.MISSING_THICKNESS,
        takeoff_eligible=False,
        review_required=True,
        review_reason="incomplete_angle_missing_thickness",
        evidence=[
            _pdf_text_evidence("2L4X4"),
            SemanticEvidence(
                evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                evidence_source="grasshopper_synthetic",
                evidence_reference="synth_2l_member_5",
                evidence_strength=EvidenceStrength.INFERRED,
            ),
        ],
        geometry_evidence=GeometryEvidence(
            available=True,
            provider="grasshopper",
            relationship=GeometryRelationship.ASSOCIATED_WITH,
            geometry_ref="synth_2l_member_5",
            geometry_type="member_candidate_synthetic",
            confidence=None,
            coordinate_system="unknown",
            source="synthetic_fixture",
            association_status=GeometryAssociationStatus.GH_ONLY,
            candidate_refs=["synth_2l_member_5"],
            native_metadata={
                **FIXTURE_MARK,
                "must_not_complete_thickness": True,
            },
        ),
        created_by="geometry_evidence_fixtures",
    )


def fixture_multiple_annotations_one_geometry() -> List[SemanticAnnotation]:
    """Two distinct annotations share the same candidate geometry ref."""

    shared = "synth_shared_beam_100"
    common_geom = GeometryEvidence(
        available=True,
        provider="grasshopper",
        relationship=GeometryRelationship.ASSOCIATED_WITH,
        geometry_ref=shared,
        geometry_type="beam_candidate_synthetic",
        confidence=0.75,
        coordinate_system="unknown",
        source="synthetic_fixture",
        association_status=GeometryAssociationStatus.GH_ONLY,
        candidate_refs=[shared],
        native_metadata={**FIXTURE_MARK, "shared_geometry_ref": shared},
    )
    a = SemanticAnnotation(
        annotation_id="fix_geom_multi_ann_a",
        raw_text="W18X35",
        normalized_text="W18X35",
        structural_family="W",
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        geometry_evidence=common_geom.model_copy(deep=True),
        evidence=[_pdf_text_evidence("W18X35")],
        created_by="geometry_evidence_fixtures",
    )
    b = SemanticAnnotation(
        annotation_id="fix_geom_multi_ann_b",
        raw_text="W18X40",
        normalized_text="W18X40",
        structural_family="W",
        completion_status=CompletionStatus.COMPLETE,
        takeoff_eligible=True,
        geometry_evidence=common_geom.model_copy(deep=True),
        evidence=[_pdf_text_evidence("W18X40")],
        created_by="geometry_evidence_fixtures",
    )
    return [a, b]


def fixture_one_annotation_multiple_geometry_candidates() -> SemanticAnnotation:
    """ONE_ANNOTATION_MULTIPLE_GEOMETRY_CANDIDATES — preserve ambiguity."""

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
    """Safety helper for tests — geometry must not invent thickness fields."""

    raw = (ann.raw_text or "").upper().replace(" ", "").replace("×", "X")
    norm = (ann.normalized_text or "").upper().replace(" ", "").replace("×", "X")
    if ann.completion_status == CompletionStatus.MISSING_THICKNESS:
        assert ann.takeoff_eligible is False
        assert raw.count("X") == norm.count("X")
        assert "X" in norm
        # Incomplete L/2L cores have exactly one X separator between legs.
        assert not (
            norm.startswith(("L", "2L"))
            and norm.count("X") >= 2
            and ann.geometry_evidence
            and ann.geometry_evidence.available
            and ann.completion_status == CompletionStatus.COMPLETE
        )
