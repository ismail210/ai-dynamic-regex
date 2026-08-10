"""Categories 1-2: schema validation and enum validation."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from services.ml_association.enums import AdjudicationStatus, CalloutScope, ReviewLabel, ValidationErrorCode
from services.ml_association.schemas import (
    NO_MATCH_CANDIDATE_TOKEN,
    SCHEMA_VERSION,
    AssociationCandidateRow,
    GeometryEvidence,
    HeuristicEvidence,
    LabelEvidence,
    LabelGroup,
    RelationshipFeatures,
    ReviewedOutcome,
)


def _label_evidence() -> LabelEvidence:
    return LabelEvidence(
        raw_text="W18X35",
        text_bbox=[0, 0, 10, 10],
        text_center=[5, 5],
    )


class SchemaValidationTests(unittest.TestCase):
    def test_association_candidate_row_requires_identity_fields(self) -> None:
        with self.assertRaises(ValidationError):
            AssociationCandidateRow(label=_label_evidence())  # missing project_id etc.

    def test_association_candidate_row_accepts_no_match_placeholder(self) -> None:
        row = AssociationCandidateRow(
            project_id="p1",
            document_id="d1",
            page_id="pg1",
            page_number=1,
            text_entity_id="t1",
            geometry_entity_id=None,
            association_candidate_id="assoc_x",
            candidate_generator_version="v1",
            feature_generator_version="v1",
            created_at="2026-01-01T00:00:00Z",
            is_no_match_placeholder=True,
            label=_label_evidence(),
        )
        self.assertIsNone(row.geometry)
        self.assertIsNone(row.geometry_entity_id)
        self.assertTrue(row.is_no_match_placeholder)

    def test_relationship_features_default_availability_flags_are_false_not_zero(self) -> None:
        features = RelationshipFeatures()
        self.assertIsNone(features.distance_normalized_by_scale)
        self.assertFalse(features.distance_scale_available)
        self.assertIsNone(features.same_region)
        self.assertFalse(features.region_available)

    def test_heuristic_evidence_defaults_are_unselected(self) -> None:
        heuristic = HeuristicEvidence()
        self.assertIsNone(heuristic.current_heuristic_score)
        self.assertIsNone(heuristic.current_heuristic_rank)
        self.assertFalse(heuristic.current_heuristic_selected)

    def test_label_group_helpers(self) -> None:
        candidate = AssociationCandidateRow(
            project_id="p1",
            document_id="d1",
            page_id="pg1",
            page_number=1,
            text_entity_id="t1",
            geometry_entity_id="geo_1",
            association_candidate_id="assoc_1",
            candidate_generator_version="v1",
            feature_generator_version="v1",
            created_at="2026-01-01T00:00:00Z",
            label=_label_evidence(),
            geometry=GeometryEvidence(geometry_bbox=[0, 0, 1, 1], geometry_center=[0.5, 0.5]),
            heuristic=HeuristicEvidence(current_heuristic_selected=True, current_heuristic_rank=1),
        )
        group = LabelGroup(
            group_id="group_1",
            project_id="p1",
            document_id="d1",
            page_id="pg1",
            page_number=1,
            text_entity_id="t1",
            label=_label_evidence(),
            candidates=[candidate],
            candidate_generator_version="v1",
            feature_generator_version="v1",
            created_at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(group.candidate_ids(), ["assoc_1"])
        self.assertEqual(group.selected_candidate_id(), "assoc_1")

    def test_reviewed_outcome_requires_review_label_and_callout_scope(self) -> None:
        with self.assertRaises(ValidationError):
            ReviewedOutcome(
                outcome_id="outcome_1",
                group_id="group_1",
                project_id="p1",
                document_id="d1",
                page_id="pg1",
                text_entity_id="t1",
                reviewer_id="alice",
                reviewed_at="2026-01-01T00:00:00Z",
            )

    def test_schema_version_default_matches_module_constant(self) -> None:
        row = AssociationCandidateRow(
            project_id="p1",
            document_id="d1",
            page_id="pg1",
            page_number=1,
            text_entity_id="t1",
            association_candidate_id="assoc_1",
            candidate_generator_version="v1",
            feature_generator_version="v1",
            created_at="2026-01-01T00:00:00Z",
            label=_label_evidence(),
        )
        self.assertEqual(row.schema_version, SCHEMA_VERSION)

    def test_no_match_token_is_a_reserved_non_empty_string(self) -> None:
        self.assertTrue(NO_MATCH_CANDIDATE_TOKEN)
        self.assertIsInstance(NO_MATCH_CANDIDATE_TOKEN, str)


class EnumValidationTests(unittest.TestCase):
    def test_review_label_values_match_spec(self) -> None:
        expected = {
            "direct_target",
            "valid_secondary_target",
            "leader_support_not_target",
            "not_target",
            "no_valid_target",
            "ambiguous_requires_adjudication",
        }
        self.assertEqual({v.value for v in ReviewLabel}, expected)

    def test_callout_scope_values_match_spec(self) -> None:
        expected = {
            "single",
            "multiple",
            "typical",
            "repeated",
            "detail_reference",
            "schedule_reference",
            "unknown",
        }
        self.assertEqual({v.value for v in CalloutScope}, expected)

    def test_adjudication_status_values_match_spec(self) -> None:
        expected = {
            "unreviewed",
            "reviewed",
            "needs_second_review",
            "adjudicated",
            "rejected_invalid",
        }
        self.assertEqual({v.value for v in AdjudicationStatus}, expected)

    def test_invalid_review_label_is_rejected_by_pydantic(self) -> None:
        with self.assertRaises(ValidationError):
            ReviewedOutcome(
                outcome_id="outcome_1",
                group_id="group_1",
                project_id="p1",
                document_id="d1",
                page_id="pg1",
                text_entity_id="t1",
                review_label="not_a_real_label",  # type: ignore[arg-type]
                callout_scope=CalloutScope.SINGLE,
                reviewer_id="alice",
                reviewed_at="2026-01-01T00:00:00Z",
            )

    def test_every_validation_error_code_is_a_non_empty_string(self) -> None:
        for code in ValidationErrorCode:
            self.assertTrue(code.value)
            self.assertIsInstance(code.value, str)

    def test_enums_serialize_as_plain_strings(self) -> None:
        outcome = ReviewedOutcome(
            outcome_id="outcome_1",
            group_id="group_1",
            project_id="p1",
            document_id="d1",
            page_id="pg1",
            text_entity_id="t1",
            review_label=ReviewLabel.DIRECT_TARGET,
            callout_scope=CalloutScope.SINGLE,
            reviewer_id="alice",
            reviewed_at="2026-01-01T00:00:00Z",
        )
        dumped = outcome.model_dump(mode="json")
        self.assertEqual(dumped["review_label"], "direct_target")
        self.assertEqual(dumped["callout_scope"], "single")


if __name__ == "__main__":
    unittest.main()
