"""Schema-only tests for the semantic annotation contract (Phase 2).

Does not exercise new normalization / repair / completion intelligence.
"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from services.prediction.semantic_contract import (
    CompletionStatus,
    EvidenceStrength,
    EvidenceType,
    GeometryEvidence,
    GeometryRelationship,
    OperationRecord,
    SemanticAnnotation,
    SemanticEvidence,
    SemanticOperationKind,
    example_2l4x4_abstention,
    example_association_with_optional_gh,
    example_completion_candidate_w8,
    example_l4x4_abstention,
    example_normalization_w8x10,
    example_repair_corrupted_w8,
    project_semantic_annotation,
)


class SemanticContractSchemaTests(unittest.TestCase):
    def test_raw_text_preserved_when_normalized_differs(self) -> None:
        ann = example_normalization_w8x10()
        self.assertEqual(ann.raw_text, "W8×10")
        self.assertEqual(ann.normalized_text, "W8X10")
        self.assertTrue(ann.original_text_preserved)
        payload = ann.to_dict()
        self.assertEqual(payload["raw_text"], "W8×10")
        self.assertNotEqual(payload["raw_text"], payload["normalized_text"])

    def test_normalization_represented_separately(self) -> None:
        ann = example_normalization_w8x10()
        self.assertEqual(len(ann.operations), 1)
        self.assertEqual(
            ann.operations[0].operation, SemanticOperationKind.NORMALIZATION
        )
        self.assertNotEqual(
            ann.operations[0].operation, SemanticOperationKind.REPAIR
        )
        self.assertNotEqual(
            ann.operations[0].operation, SemanticOperationKind.COMPLETION
        )

    def test_repair_represented_separately(self) -> None:
        ann = example_repair_corrupted_w8()
        self.assertEqual(ann.operations[0].operation, SemanticOperationKind.REPAIR)
        self.assertEqual(ann.raw_text, "W8XI0")
        self.assertEqual(ann.operations[0].output_text, "W8X10")

    def test_completion_represented_separately(self) -> None:
        ann = example_completion_candidate_w8()
        self.assertEqual(
            ann.operations[0].operation, SemanticOperationKind.COMPLETION
        )
        self.assertEqual(ann.raw_text, "W8")
        self.assertEqual(ann.operations[0].output_text, "W8X10")

    def test_association_represented_separately_and_preserves_text(self) -> None:
        ann = example_association_with_optional_gh()
        self.assertEqual(
            ann.operations[0].operation, SemanticOperationKind.ASSOCIATION
        )
        self.assertEqual(ann.raw_text, "W12X26")
        self.assertEqual(ann.operations[0].input_text, ann.operations[0].output_text)

    def test_association_cannot_rewrite_semantic_text(self) -> None:
        with self.assertRaises(ValidationError):
            OperationRecord(
                operation=SemanticOperationKind.ASSOCIATION,
                input_text="W8",
                output_text="W8X10",
            )

    def test_evidence_can_contain_multiple_sources(self) -> None:
        ann = SemanticAnnotation(
            annotation_id="multi_ev",
            raw_text="W12X26",
            normalized_text="W12X26",
            evidence=[
                SemanticEvidence(
                    evidence_type=EvidenceType.PDF_TEXT,
                    evidence_source="pdf_text",
                    evidence_reference="W12X26",
                    evidence_strength=EvidenceStrength.EXPLICIT,
                ),
                SemanticEvidence(
                    evidence_type=EvidenceType.LEGEND,
                    evidence_source="legend",
                    evidence_reference="W12X26 TYP",
                    evidence_strength=EvidenceStrength.EXPLICIT,
                ),
                SemanticEvidence(
                    evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                    evidence_source="grasshopper",
                    evidence_reference="optional",
                    evidence_strength=EvidenceStrength.INFERRED,
                ),
            ],
        )
        self.assertEqual(len(ann.evidence), 3)
        types = {e.evidence_type for e in ann.evidence}
        self.assertIn(EvidenceType.PDF_TEXT, types)
        self.assertIn(EvidenceType.GRASSHOPPER_GEOMETRY, types)

    def test_geometry_evidence_can_be_absent(self) -> None:
        ann = example_normalization_w8x10()
        self.assertIsNone(ann.geometry_evidence)
        self.assertIsNone(ann.to_dict().get("geometry_evidence"))

    def test_incomplete_l_abstention_representation(self) -> None:
        ann = example_l4x4_abstention()
        self.assertEqual(ann.raw_text, "L4X4,")
        self.assertEqual(ann.normalized_text, "L4X4")
        self.assertEqual(ann.completion_status, CompletionStatus.MISSING_THICKNESS)
        self.assertFalse(ann.takeoff_eligible)
        self.assertTrue(ann.review_required)

    def test_incomplete_2l_abstention_representation(self) -> None:
        ann = example_2l4x4_abstention()
        self.assertEqual(ann.raw_text, "2L4X4")
        self.assertEqual(ann.completion_status, CompletionStatus.MISSING_THICKNESS)
        self.assertFalse(ann.takeoff_eligible)
        self.assertTrue(ann.review_required)

    def test_complete_label_can_be_eligible(self) -> None:
        ann = example_normalization_w8x10()
        self.assertEqual(ann.completion_status, CompletionStatus.COMPLETE)
        self.assertTrue(ann.takeoff_eligible)
        self.assertFalse(ann.review_required)

    def test_optional_gh_geometry_does_not_imply_completion(self) -> None:
        ann = example_association_with_optional_gh()
        self.assertIsNotNone(ann.geometry_evidence)
        assert ann.geometry_evidence is not None
        self.assertTrue(ann.geometry_evidence.available)
        self.assertEqual(ann.geometry_evidence.provider, "grasshopper")
        # Association did not invent a different section string
        self.assertEqual(ann.raw_text, "W12X26")
        self.assertEqual(ann.normalized_text, "W12X26")
        self.assertFalse(
            ann.geometry_evidence.native_metadata.get(
                "beam_txt_crv_index_assumed_equal"
            )
        )

    def test_project_from_prediction_preserves_raw_and_abstention(self) -> None:
        payload = {
            "object_id": "tok_1",
            "document_id": "doc_a",
            "raw_text": "L4X4,",
            "normalized_text": "L4X4",
            "family": "L",
            "completion_status": "missing_thickness",
            "takeoff_eligible": False,
            "needs_review": True,
            "review_reason": "incomplete_angle_missing_thickness",
            "page_number": 3,
            "bounding_box": [1.0, 2.0, 3.0, 4.0],
            "confidence": {"overall": 0.4},
        }
        ann = project_semantic_annotation(payload)
        self.assertEqual(ann.raw_text, "L4X4,")
        self.assertEqual(ann.normalized_text, "L4X4")
        self.assertEqual(ann.completion_status, CompletionStatus.MISSING_THICKNESS)
        self.assertFalse(ann.takeoff_eligible)
        self.assertTrue(ann.review_required)
        self.assertTrue(ann.original_text_preserved)
        self.assertIsNone(ann.geometry_evidence)

    def test_project_without_member_geometry_leaves_geometry_absent(self) -> None:
        ann = project_semantic_annotation(
            {"object_id": "t", "raw_text": "W12X26", "normalized_text": "W12X26"}
        )
        self.assertIsNone(ann.geometry_evidence)

    def test_unavailable_geometry_evidence_is_valid(self) -> None:
        ann = SemanticAnnotation(
            annotation_id="no_geom",
            raw_text="W8X10",
            geometry_evidence=GeometryEvidence(
                available=False,
                relationship=GeometryRelationship.UNAVAILABLE,
                provider="unavailable",
            ),
        )
        self.assertFalse(ann.geometry_evidence.available)


if __name__ == "__main__":
    unittest.main()
