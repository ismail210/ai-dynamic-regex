"""Schema-only tests for the unified semantic annotation contract.

Migrated from the old Pydantic ``services.prediction.semantic_contract``
model onto the canonical ``services.semantic`` model (see
``docs/architecture/unified_semantic_contract.md``). Every behavioral
guarantee the old tests checked is preserved; field names changed because
the domain model changed, not because the guarantee did.

Does not exercise new normalization / repair / completion intelligence.
"""

from __future__ import annotations

import unittest

from services.semantic.models import (
    EvidenceStrength,
    EvidenceType,
    GeometryAssociation,
    GeometryProvider,
    OperationKind,
    ReviewStatus,
)
from services.semantic.projection import project_semantic_annotation
from services.prediction.semantic_contract import (
    example_2l4x4_abstention,
    example_association_with_optional_gh,
    example_completion_candidate_w8,
    example_l4x4_abstention,
    example_normalization_w8x10,
    example_repair_corrupted_w8,
)


class SemanticContractSchemaTests(unittest.TestCase):
    def test_raw_text_preserved_when_normalized_differs(self) -> None:
        ann = example_normalization_w8x10()
        self.assertEqual(ann.original_text, "W8×10")
        self.assertEqual(ann.effective_text, "W8X10")
        self.assertTrue(ann.original_text_preserved)
        payload = ann.to_dict()
        self.assertEqual(payload["original_text"], "W8×10")
        self.assertNotEqual(payload["original_text"], payload["effective_text"])

    def test_normalization_represented_separately(self) -> None:
        ann = example_normalization_w8x10()
        self.assertEqual(len(ann.operations), 1)
        self.assertEqual(ann.operations[0].operation, OperationKind.NORMALIZATION)
        self.assertNotEqual(ann.operations[0].operation, OperationKind.REPAIR)
        self.assertNotEqual(ann.operations[0].operation, OperationKind.COMPLETION)

    def test_repair_represented_separately(self) -> None:
        ann = example_repair_corrupted_w8()
        self.assertEqual(ann.operations[0].operation, OperationKind.REPAIR)
        self.assertEqual(ann.original_text, "W8XI0")
        self.assertEqual(ann.operations[0].output_text, "W8X10")

    def test_completion_represented_separately(self) -> None:
        ann = example_completion_candidate_w8()
        self.assertEqual(ann.operations[0].operation, OperationKind.COMPLETION)
        self.assertEqual(ann.original_text, "W8")
        self.assertEqual(ann.operations[0].output_text, "W8X10")
        self.assertTrue(ann.operations[0].semantic_information_added)

    def test_association_is_not_a_text_operation(self) -> None:
        """Section 13: association must never be representable as a text
        transformation. In the unified model this is a structural guarantee
        (GeometryAssociation has no output_text field at all), not a
        runtime validator on a generic OperationRecord."""

        ann = example_association_with_optional_gh()
        self.assertEqual(ann.operations, [])
        self.assertEqual(len(ann.geometry_associations), 1)
        self.assertFalse(hasattr(ann.geometry_associations[0], "output_text"))
        # The association evidence carries no text-changing capability.
        self.assertEqual(ann.original_text, "W12X26")
        self.assertEqual(ann.effective_text, "W12X26")

    def test_evidence_can_contain_multiple_sources(self) -> None:
        from services.semantic.models import EvidenceRecord, SemanticAnnotation

        ann = SemanticAnnotation(
            annotation_id="multi_ev",
            original_text="W12X26",
            primary_label="W12X26",
            evidence=[
                EvidenceRecord(
                    evidence_id="e1",
                    evidence_type=EvidenceType.PDF_TEXT,
                    source="pdf_text",
                    reference="W12X26",
                    strength=EvidenceStrength.EXPLICIT,
                ),
                EvidenceRecord(
                    evidence_id="e2",
                    evidence_type=EvidenceType.LEGEND,
                    source="legend",
                    reference="W12X26 TYP",
                    strength=EvidenceStrength.EXPLICIT,
                ),
                EvidenceRecord(
                    evidence_id="e3",
                    evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                    source="grasshopper",
                    reference="optional",
                    strength=EvidenceStrength.INFERRED,
                ),
            ],
        )
        self.assertEqual(len(ann.evidence), 3)
        types = {e.evidence_type for e in ann.evidence}
        self.assertIn(EvidenceType.PDF_TEXT, types)
        self.assertIn(EvidenceType.GRASSHOPPER_GEOMETRY, types)

    def test_geometry_associations_can_be_absent(self) -> None:
        ann = example_normalization_w8x10()
        self.assertEqual(ann.geometry_associations, [])
        self.assertEqual(ann.to_dict()["geometry_associations"], [])

    def test_incomplete_l_abstention_representation(self) -> None:
        ann = example_l4x4_abstention()
        self.assertEqual(ann.original_text, "L4X4,")
        self.assertEqual(ann.primary_label, "L4X4")
        self.assertFalse(ann.is_complete)
        self.assertFalse(ann.takeoff_eligible)
        self.assertEqual(ann.review_status, ReviewStatus.NEEDS_REVIEW)
        # Still a real, visible semantic annotation -- not removed.
        self.assertIsNotNone(ann.structural_parse)
        self.assertTrue(ann.structural_parse.is_structural)

    def test_incomplete_2l_abstention_representation(self) -> None:
        ann = example_2l4x4_abstention()
        self.assertEqual(ann.original_text, "2L4X4")
        self.assertFalse(ann.is_complete)
        self.assertFalse(ann.takeoff_eligible)
        self.assertEqual(ann.review_status, ReviewStatus.NEEDS_REVIEW)

    def test_complete_label_can_be_eligible(self) -> None:
        ann = example_normalization_w8x10()
        self.assertTrue(ann.takeoff_eligible)
        self.assertNotEqual(ann.review_status, ReviewStatus.NEEDS_REVIEW)

    def test_optional_gh_geometry_does_not_imply_completion(self) -> None:
        ann = example_association_with_optional_gh()
        self.assertEqual(len(ann.geometry_associations), 1)
        candidate = ann.geometry_associations[0]
        self.assertEqual(candidate.provider, GeometryProvider.GRASSHOPPER)
        self.assertFalse(candidate.verified)
        # Association did not invent a different section string.
        self.assertEqual(ann.original_text, "W12X26")
        self.assertEqual(ann.effective_text, "W12X26")
        self.assertFalse(
            candidate.evidence[0].details.get("beam_txt_crv_index_assumed_equal")
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
        self.assertEqual(ann.original_text, "L4X4,")
        self.assertEqual(ann.primary_label, "L4X4")
        self.assertFalse(ann.is_complete)
        self.assertFalse(ann.takeoff_eligible)
        self.assertEqual(ann.review_status, ReviewStatus.NEEDS_REVIEW)
        self.assertTrue(ann.original_text_preserved)
        self.assertEqual(ann.geometry_associations, [])

    def test_project_without_member_geometry_leaves_geometry_absent(self) -> None:
        ann = project_semantic_annotation(
            {"object_id": "t", "raw_text": "W12X26", "normalized_text": "W12X26"}
        )
        self.assertEqual(ann.geometry_associations, [])

    def test_unavailable_geometry_is_an_empty_candidate_list(self) -> None:
        from services.semantic.models import SemanticAnnotation

        ann = SemanticAnnotation(annotation_id="no_geom", original_text="W8X10")
        self.assertEqual(ann.geometry_associations, [])
        self.assertIsNone(ann.primary_geometry_association)


if __name__ == "__main__":
    unittest.main()
