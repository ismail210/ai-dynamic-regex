"""Contract tests for optional geometry evidence (synthetic fixtures only).

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
from services.semantic.models import (
    SCHEMA_VERSION,
    GeometryProvider,
    ReviewStatus,
    SemanticAnnotation,
)
from services.semantic.serialization import load_semantic_document


def _providers(ann: SemanticAnnotation) -> set:
    return {a.provider for a in ann.geometry_associations}


class GeometryEvidenceContractTests(unittest.TestCase):
    def test_a_geometry_optional_without_breaking_annotation(self) -> None:
        ann = SemanticAnnotation(
            annotation_id="no_geom",
            original_text="W8X10",
            primary_label="W8X10",
            takeoff_eligible=True,
        )
        self.assertEqual(ann.geometry_associations, [])
        self.assertIsNone(ann.primary_geometry_association)
        self.assertEqual(ann.to_dict()["geometry_associations"], [])

    def test_b_attach_geometry_without_changing_label(self) -> None:
        ann = fixture_agreement()
        self.assertEqual(
            _providers(ann), {GeometryProvider.PDF_VECTOR, GeometryProvider.GRASSHOPPER}
        )
        self.assertEqual({a.geometry_id for a in ann.geometry_associations}, {"synth_member_A"})
        self.assertEqual(ann.operations, [])
        self.assertEqual(ann.effective_text, "W12X26")
        self.assertEqual(ann.original_text, "W12X26")

    def test_c_gh_only_does_not_auto_complete(self) -> None:
        ann = fixture_gh_only()
        self.assertEqual(_providers(ann), {GeometryProvider.GRASSHOPPER})
        self.assertEqual(ann.effective_text, ann.original_text)
        self.assertTrue(ann.is_complete)
        # Complete label unchanged -- GH did not rewrite section string
        self.assertEqual(ann.effective_text, "W16X26")

    def test_d_pdf_only_remains_valid(self) -> None:
        ann = fixture_pdf_only()
        self.assertEqual(_providers(ann), {GeometryProvider.PDF_VECTOR})
        self.assertEqual(ann.geometry_associations[0].coordinate_frame, "pdf_page")

    def test_e_conflict_explicitly_representable(self) -> None:
        ann = fixture_conflict()
        self.assertEqual(len(ann.geometry_associations), 2)
        self.assertEqual(
            _providers(ann), {GeometryProvider.PDF_VECTOR, GeometryProvider.GRASSHOPPER}
        )
        self.assertEqual(len({a.geometry_id for a in ann.geometry_associations}), 2)
        self.assertFalse(any(a.verified for a in ann.geometry_associations))
        self.assertEqual(ann.review_status, ReviewStatus.NEEDS_REVIEW)
        self.assertEqual(ann.review.reason, "geometry_association_conflict")

    def test_f_ambiguous_without_forced_selection(self) -> None:
        ann = fixture_ambiguous()
        self.assertGreaterEqual(len(ann.geometry_associations), 2)
        for assoc in ann.geometry_associations:
            self.assertFalse(assoc.verified)
            self.assertEqual(assoc.review_status, ReviewStatus.PENDING)
            self.assertIsNone(assoc.score)
            self.assertFalse(assoc.evidence[0].details.get("forced_selection", True))

    def test_g_multiple_annotations_share_geometry_without_dedupe(self) -> None:
        anns = fixture_multiple_annotations_one_geometry()
        self.assertEqual(len(anns), 2)
        self.assertNotEqual(anns[0].annotation_id, anns[1].annotation_id)
        self.assertNotEqual(anns[0].original_text, anns[1].original_text)
        ref0 = anns[0].geometry_associations[0].geometry_id
        ref1 = anns[1].geometry_associations[0].geometry_id
        self.assertEqual(ref0, ref1)

    def test_h_one_annotation_retains_multiple_candidates(self) -> None:
        ann = fixture_ambiguous()
        self.assertEqual(len({a.geometry_id for a in ann.geometry_associations}), 3)

    def test_i_incomplete_l_safety_with_geometry(self) -> None:
        ann = fixture_incomplete_l_with_geometry()
        self.assertEqual(ann.original_text, "L4X4")
        self.assertEqual(ann.effective_text, "L4X4")
        self.assertIs(ann.is_complete, False)
        self.assertFalse(ann.takeoff_eligible)
        self.assertTrue(ann.geometry_associations)
        assert_geometry_does_not_complete(ann)
        # Forbidden inventions
        self.assertNotIn("L4X4X1/4", ann.effective_text.upper())

    def test_j_incomplete_2l_safety_with_geometry(self) -> None:
        ann = fixture_incomplete_2l_with_geometry()
        self.assertEqual(ann.original_text, "2L4X4")
        self.assertEqual(ann.effective_text, "2L4X4")
        self.assertIs(ann.is_complete, False)
        self.assertFalse(ann.takeoff_eligible)
        assert_geometry_does_not_complete(ann)

    def test_k_geometry_cannot_overwrite_normalized_label(self) -> None:
        ann = fixture_incomplete_l_with_geometry()
        mutated = copy.deepcopy(ann)
        # Attaching richer geometry metadata must not rewrite label fields
        mutated.geometry_associations[0].evidence[0].details["suggested_section"] = "L4X4X1/4"
        self.assertEqual(mutated.effective_text, "L4X4")
        self.assertEqual(mutated.to_dict()["primary_label"], "L4X4")
        self.assertIs(mutated.is_complete, False)
        assert_geometry_does_not_complete(mutated)

    def test_l_geometry_cannot_bypass_abstention(self) -> None:
        ann = fixture_incomplete_l_with_geometry()
        self.assertFalse(ann.takeoff_eligible)
        self.assertEqual(ann.review_status, ReviewStatus.NEEDS_REVIEW)
        self.assertEqual(ann.review.reason, "incomplete_angle_missing_thickness")

    def test_n_drawing_semantics_backward_compatible_with_geometry(self) -> None:
        # Without geometry
        plain = {
            "object_id": "p1",
            "raw_text": "W8X10",
            "normalized_text": "W8X10",
            "completion_status": "complete",
            "takeoff_eligible": True,
        }
        # With PDF member geometry on an incomplete angle
        with_geom = {
            "object_id": "p2",
            "raw_text": "L4X4",
            "normalized_text": "L4X4",
            "family": "L",
            "completion_status": "missing_thickness",
            "takeoff_eligible": False,
            "needs_review": True,
            "member_geometry": {"object_id": "synth_angle_member_12", "confidence": 0.8},
        }
        payload = build_drawing_semantics(
            document_id="doc_geom_fixture",
            source_file="synthetic.pdf",
            predictions=[plain, with_geom],
        )
        self.assertEqual(validate_drawing_semantics(payload), [])
        self.assertEqual(payload["annotation_count"], 2)
        by_id = {a["annotation_id"]: a for a in payload["annotations"]}
        self.assertEqual(by_id["p1"]["geometry_associations"], [])
        self.assertTrue(by_id["p2"]["geometry_associations"])
        self.assertEqual(by_id["p2"]["completion_status"], "missing_thickness")
        self.assertFalse(by_id["p2"]["takeoff_eligible"])
        self.assertEqual(by_id["p2"]["primary_label"], "L4X4")
        self.assertEqual(by_id["p2"]["effective_text"], "L4X4")
        self.assertFalse(by_id["p2"]["structural_parse"]["complete"])

    def test_all_named_fixtures_roundtrip_dict(self) -> None:
        for name, value in all_fixture_annotations().items():
            anns = value if isinstance(value, list) else [value]
            document = load_semantic_document(
                {
                    "schema_version": SCHEMA_VERSION,
                    "document_id": "doc_geom_fixture",
                    "annotations": [ann.to_dict() for ann in anns],
                }
            )
            for ann, restored in zip(anns, document.annotations):
                self.assertEqual(restored.annotation_id, ann.annotation_id, name)
                self.assertEqual(restored.original_text, ann.original_text, name)
                self.assertEqual(restored.primary_label, ann.primary_label, name)
                self.assertEqual(restored.takeoff_eligible, ann.takeoff_eligible, name)
                self.assertEqual(restored.is_complete, ann.is_complete, name)
                self.assertEqual(
                    [(g.geometry_id, g.provider) for g in restored.geometry_associations],
                    [(g.geometry_id, g.provider) for g in ann.geometry_associations],
                    name,
                )


if __name__ == "__main__":
    unittest.main()
