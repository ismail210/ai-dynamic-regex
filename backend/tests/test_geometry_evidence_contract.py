"""Contract tests for optional GeometryEvidence (synthetic fixtures only).

Does not exercise GH adapters, PDF↔Rhino transforms, or association algorithms.
"""

from __future__ import annotations

import copy
import unittest

from services.prediction.drawing_semantics import (
    build_drawing_semantics,
    validate_drawing_semantics,
)
from services.prediction.geometry_evidence_fixtures import (
    all_fixture_annotations,
    assert_geometry_does_not_complete,
    fixture_agreement,
    fixture_ambiguous,
    fixture_conflict,
    fixture_gh_only,
    fixture_incomplete_2l_with_geometry,
    fixture_incomplete_l_with_geometry,
    fixture_multiple_annotations_one_geometry,
    fixture_pdf_only,
)
from services.prediction.semantic_contract import (
    CompletionStatus,
    GeometryAssociationStatus,
    GeometryEvidence,
    GeometryRelationship,
    SemanticAnnotation,
    project_semantic_annotation,
)


class GeometryEvidenceContractTests(unittest.TestCase):
    def test_a_geometry_optional_without_breaking_annotation(self) -> None:
        ann = SemanticAnnotation(
            annotation_id="no_geom",
            raw_text="W8X10",
            normalized_text="W8X10",
            completion_status=CompletionStatus.COMPLETE,
            takeoff_eligible=True,
        )
        self.assertIsNone(ann.geometry_evidence)
        payload = ann.to_dict()
        self.assertIsNone(payload.get("geometry_evidence"))

    def test_b_attach_geometry_without_changing_label(self) -> None:
        ann = fixture_agreement()
        before = (ann.raw_text, ann.normalized_text)
        self.assertIsNotNone(ann.geometry_evidence)
        self.assertEqual(before, (ann.raw_text, ann.normalized_text))
        self.assertEqual(ann.normalized_text, "W12X26")

    def test_c_gh_only_does_not_auto_complete(self) -> None:
        ann = fixture_gh_only()
        assert ann.geometry_evidence is not None
        self.assertEqual(
            ann.geometry_evidence.association_status,
            GeometryAssociationStatus.GH_ONLY,
        )
        self.assertEqual(ann.raw_text, ann.normalized_text)
        self.assertEqual(ann.completion_status, CompletionStatus.COMPLETE)
        # Complete label unchanged — GH did not rewrite section string
        self.assertEqual(ann.normalized_text, "W16X26")

    def test_d_pdf_only_remains_valid(self) -> None:
        ann = fixture_pdf_only()
        assert ann.geometry_evidence is not None
        self.assertEqual(
            ann.geometry_evidence.association_status,
            GeometryAssociationStatus.PDF_ONLY,
        )
        self.assertEqual(ann.geometry_evidence.provider, "pdf")
        self.assertEqual(ann.geometry_evidence.coordinate_system, "pdf_page")

    def test_e_conflict_explicitly_representable(self) -> None:
        ann = fixture_conflict()
        assert ann.geometry_evidence is not None
        self.assertEqual(
            ann.geometry_evidence.association_status,
            GeometryAssociationStatus.CONFLICT,
        )
        self.assertIsNone(ann.geometry_evidence.geometry_ref)
        self.assertEqual(len(ann.geometry_evidence.candidate_refs), 2)
        self.assertTrue(ann.review_required)

    def test_f_ambiguous_without_forced_selection(self) -> None:
        ann = fixture_ambiguous()
        assert ann.geometry_evidence is not None
        self.assertEqual(
            ann.geometry_evidence.association_status,
            GeometryAssociationStatus.AMBIGUOUS,
        )
        self.assertIsNone(ann.geometry_evidence.geometry_ref)
        self.assertGreaterEqual(len(ann.geometry_evidence.candidate_refs), 2)
        self.assertFalse(
            ann.geometry_evidence.native_metadata.get("forced_selection", True)
        )

    def test_g_multiple_annotations_share_geometry_without_dedupe(self) -> None:
        anns = fixture_multiple_annotations_one_geometry()
        self.assertEqual(len(anns), 2)
        self.assertNotEqual(anns[0].annotation_id, anns[1].annotation_id)
        self.assertNotEqual(anns[0].raw_text, anns[1].raw_text)
        ref0 = anns[0].geometry_evidence.geometry_ref if anns[0].geometry_evidence else None
        ref1 = anns[1].geometry_evidence.geometry_ref if anns[1].geometry_evidence else None
        self.assertEqual(ref0, ref1)
        self.assertIsNotNone(ref0)

    def test_h_one_annotation_retains_multiple_candidates(self) -> None:
        ann = fixture_ambiguous()
        assert ann.geometry_evidence is not None
        self.assertEqual(len(set(ann.geometry_evidence.candidate_refs)), 3)

    def test_i_incomplete_l_safety_with_geometry(self) -> None:
        ann = fixture_incomplete_l_with_geometry()
        self.assertEqual(ann.raw_text, "L4X4")
        self.assertEqual(ann.normalized_text, "L4X4")
        self.assertEqual(ann.completion_status, CompletionStatus.MISSING_THICKNESS)
        self.assertFalse(ann.takeoff_eligible)
        assert ann.geometry_evidence is not None
        self.assertTrue(ann.geometry_evidence.available)
        assert_geometry_does_not_complete(ann)
        # Forbidden inventions
        self.assertNotIn("L4X4X1/4", (ann.normalized_text or "").upper())
        self.assertNotEqual(ann.completion_status, CompletionStatus.COMPLETE)

    def test_j_incomplete_2l_safety_with_geometry(self) -> None:
        ann = fixture_incomplete_2l_with_geometry()
        self.assertEqual(ann.raw_text, "2L4X4")
        self.assertEqual(ann.normalized_text, "2L4X4")
        self.assertEqual(ann.completion_status, CompletionStatus.MISSING_THICKNESS)
        self.assertFalse(ann.takeoff_eligible)
        assert_geometry_does_not_complete(ann)

    def test_k_geometry_cannot_overwrite_normalized_label(self) -> None:
        ann = fixture_incomplete_l_with_geometry()
        mutated = copy.deepcopy(ann)
        assert mutated.geometry_evidence is not None
        # Attaching richer native_metadata must not rewrite label fields
        mutated.geometry_evidence.native_metadata["suggested_section"] = "L4X4X1/4"
        self.assertEqual(mutated.normalized_text, "L4X4")
        self.assertEqual(mutated.completion_status, CompletionStatus.MISSING_THICKNESS)

    def test_l_geometry_cannot_bypass_abstention(self) -> None:
        ann = fixture_incomplete_l_with_geometry()
        self.assertFalse(ann.takeoff_eligible)
        self.assertTrue(ann.review_required)
        self.assertEqual(ann.review_reason, "incomplete_angle_missing_thickness")

    def test_n_drawing_semantics_backward_compatible_with_geometry(self) -> None:
        # Without geometry
        plain = {
            "object_id": "p1",
            "raw_text": "W8X10",
            "normalized_text": "W8X10",
            "completion_status": "complete",
            "takeoff_eligible": True,
        }
        # With synthetic geometry_evidence bag
        with_geom = {
            "object_id": "p2",
            "raw_text": "L4X4",
            "normalized_text": "L4X4",
            "completion_status": "missing_thickness",
            "takeoff_eligible": False,
            "needs_review": True,
            "geometry_evidence": fixture_incomplete_l_with_geometry()
            .geometry_evidence.model_dump(mode="json")
            if fixture_incomplete_l_with_geometry().geometry_evidence
            else None,
        }
        payload = build_drawing_semantics(
            document_id="doc_geom_fixture",
            source_file="synthetic.pdf",
            predictions=[plain, with_geom],
        )
        self.assertEqual(validate_drawing_semantics(payload), [])
        self.assertEqual(payload["annotation_count"], 2)
        by_id = {a["annotation_id"]: a for a in payload["annotations"]}
        self.assertIsNone(by_id["p1"].get("geometry_evidence"))
        self.assertIsNotNone(by_id["p2"].get("geometry_evidence"))
        self.assertEqual(by_id["p2"]["completion_status"], "missing_thickness")
        self.assertFalse(by_id["p2"]["takeoff_eligible"])
        self.assertEqual(by_id["p2"]["normalized_text"], "L4X4")

    def test_project_passthrough_explicit_geometry_evidence(self) -> None:
        geom = fixture_gh_only().geometry_evidence
        assert geom is not None
        ann = project_semantic_annotation(
            {
                "object_id": "tok_gh",
                "raw_text": "W16X26",
                "normalized_text": "W16X26",
                "completion_status": "complete",
                "geometry_evidence": geom.model_dump(mode="json"),
            }
        )
        self.assertIsNotNone(ann.geometry_evidence)
        assert ann.geometry_evidence is not None
        self.assertEqual(
            ann.geometry_evidence.association_status,
            GeometryAssociationStatus.GH_ONLY,
        )
        self.assertEqual(ann.normalized_text, "W16X26")

    def test_unavailable_geometry_evidence_still_valid(self) -> None:
        ann = SemanticAnnotation(
            annotation_id="unavail",
            raw_text="W10X12",
            geometry_evidence=GeometryEvidence(
                available=False,
                relationship=GeometryRelationship.UNAVAILABLE,
                association_status=GeometryAssociationStatus.UNAVAILABLE,
                provider="unavailable",
            ),
        )
        self.assertFalse(ann.geometry_evidence.available)

    def test_all_named_fixtures_roundtrip_dict(self) -> None:
        for name, value in all_fixture_annotations().items():
            anns = value if isinstance(value, list) else [value]
            for ann in anns:
                dumped = ann.to_dict()
                restored = SemanticAnnotation.model_validate(dumped)
                self.assertEqual(restored.annotation_id, ann.annotation_id, name)
                self.assertEqual(restored.raw_text, ann.raw_text, name)


if __name__ == "__main__":
    unittest.main()
