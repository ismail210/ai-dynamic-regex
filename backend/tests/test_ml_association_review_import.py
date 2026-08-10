"""Categories 6, 9-18: reviewer-import validation and round-trip.

Categories covered explicitly in this file:
6  dataset export/import round trip
9  unknown-ID rejection
10 project/document/page mismatch rejection
11 out-of-candidate selection rejection
12 explicit candidate-generation-miss acceptance
13 no-valid-target validation
14 single-target scope validation
15 multi-target scope validation
16 leader-support-not-target behavior
17 invalid reviewer/timestamp rejection
18 unsupported schema-version rejection
"""

from __future__ import annotations

import unittest

from services.ml_association.candidate_dataset import build_label_groups
from services.ml_association.enums import ValidationErrorCode
from services.ml_association.review_import import import_review
from services.ml_association.schemas import NO_MATCH_CANDIDATE_TOKEN

CREATED_AT = "2026-01-01T00:00:00Z"


def _token(token_id: str, text: str, page: int, x: float, y: float, w: float = 20, h: float = 10):
    return {
        "token_id": token_id,
        "text": text,
        "page": page,
        "bbox": [x, y, x + w, y + h],
        "font_size": 10,
        "rotation": 0,
        "line": {},
        "engineering_object_type": "beam",
    }


def _geom(geometry_id: str, page: int, x: float, y: float, w: float = 10, h: float = 10):
    return {
        "geometry_id": geometry_id,
        "page_number": page,
        "bbox": [x, y, x + w, y + h],
        "center": [x + w / 2.0, y + h / 2.0],
        "kind": "line",
        "length": w,
        "width": w,
        "area": w * h,
        "orientation": 0.0,
        "nearby_text": None,
    }


def _build_group_with_two_candidates():
    document = _document(
        [
            _token("token_p1_0", "W18X35", 1, 0, 0),
        ]
    )
    geometry = _geometry(
        [
            _geom("geom_a", 1, 15, 0),
            _geom("geom_b", 1, 35, 0),
        ]
    )
    groups = build_label_groups(
        document, geometry, project_id="p1", document_id="d1", created_at=CREATED_AT
    )
    return groups[0]


def _document(tokens):
    return {
        "engineering_tokens": tokens,
        "pages": [{"page_number": 1, "width": 1000, "height": 1000, "rotation": 0}],
        "lines": [],
    }


def _geometry(objects):
    return {"objects": objects, "page_summaries": []}


def _valid_payload(group, **overrides):
    real_id = next(c.geometry_entity_id for c in group.candidates if not c.is_no_match_placeholder)
    payload = {
        "export_schema_version": group.schema_version,
        "group_id": group.group_id,
        "project_id": group.project_id,
        "document_id": group.document_id,
        "page_id": group.page_id,
        "text_entity_id": group.text_entity_id,
        "review_label": "direct_target",
        "reviewed_target_geometry_ids": [real_id],
        "callout_scope": "single",
        "reviewer_id": "alice",
        "reviewed_at": "2026-02-01T00:00:00Z",
    }
    payload.update(overrides)
    return payload, real_id


def _codes(result):
    return {e.code for e in result.errors}


class RoundTripTests(unittest.TestCase):
    def test_valid_submission_round_trips_into_a_matching_outcome(self) -> None:
        group = _build_group_with_two_candidates()
        payload, real_id = _valid_payload(group)
        result = import_review(payload, group)
        self.assertTrue(result.valid, result.errors)
        self.assertIsNotNone(result.outcome)
        self.assertEqual(result.outcome.group_id, group.group_id)
        self.assertEqual(result.outcome.reviewed_target_geometry_ids, [real_id])
        self.assertEqual(result.outcome.reviewer_id, "alice")
        self.assertEqual(result.outcome.candidate_set_snapshot, group.candidate_ids())


class UnknownIdRejectionTests(unittest.TestCase):
    def test_group_id_mismatch_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, group_id="group_does_not_exist")
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.UNKNOWN_ID.value, _codes(result))

    def test_unknown_supersedes_outcome_id_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, supersedes_outcome_id="outcome_ghost")
        result = import_review(payload, group, existing_outcome_ids=set())
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.UNKNOWN_ID.value, _codes(result))


class MismatchRejectionTests(unittest.TestCase):
    def test_project_mismatch_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, project_id="wrong_project")
        result = import_review(payload, group)
        self.assertIn(ValidationErrorCode.PROJECT_MISMATCH.value, _codes(result))

    def test_document_mismatch_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, document_id="wrong_document")
        result = import_review(payload, group)
        self.assertIn(ValidationErrorCode.DOCUMENT_MISMATCH.value, _codes(result))

    def test_page_mismatch_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, page_id="wrong_page")
        result = import_review(payload, group)
        self.assertIn(ValidationErrorCode.PAGE_MISMATCH.value, _codes(result))

    def test_label_not_found_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, text_entity_id="token_p1_999")
        result = import_review(payload, group)
        self.assertIn(ValidationErrorCode.LABEL_NOT_FOUND.value, _codes(result))


class OutOfCandidateSetTests(unittest.TestCase):
    def test_target_outside_candidate_set_is_rejected_by_default(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, reviewed_target_geometry_ids=["geom_never_generated"])
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.TARGET_OUTSIDE_CANDIDATE_SET.value, _codes(result))

    def test_no_match_token_is_never_a_selectable_target(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, reviewed_target_geometry_ids=[NO_MATCH_CANDIDATE_TOKEN])
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.TARGET_OUTSIDE_CANDIDATE_SET.value, _codes(result))

    def test_geometry_not_on_page_is_more_specific_than_outside_candidate_set(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, reviewed_target_geometry_ids=["geom_never_generated"])
        result = import_review(
            payload, group, known_page_geometry_ids={"geom_a", "geom_b"}
        )
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.GEOMETRY_NOT_ON_PAGE.value, _codes(result))


class CandidateGenerationMissTests(unittest.TestCase):
    def test_candidate_generation_miss_true_accepts_an_out_of_set_target(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(
            group,
            reviewed_target_geometry_ids=["geom_missed_by_generator"],
            candidate_generation_miss=True,
        )
        result = import_review(payload, group)
        self.assertTrue(result.valid, result.errors)
        self.assertTrue(result.outcome.candidate_generation_miss)
        self.assertEqual(
            result.outcome.reviewed_target_geometry_ids, ["geom_missed_by_generator"]
        )


class NoValidTargetTests(unittest.TestCase):
    def test_no_valid_target_with_empty_targets_is_accepted(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(
            group, review_label="no_valid_target", reviewed_target_geometry_ids=[]
        )
        result = import_review(payload, group)
        self.assertTrue(result.valid, result.errors)

    def test_no_valid_target_combined_with_targets_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, real_id = _valid_payload(group, review_label="no_valid_target")
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(
            ValidationErrorCode.NO_VALID_TARGET_WITH_SELECTED_TARGETS.value, _codes(result)
        )


class SingleScopeTests(unittest.TestCase):
    def test_single_scope_with_one_target_is_accepted(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, callout_scope="single")
        result = import_review(payload, group)
        self.assertTrue(result.valid, result.errors)

    def test_single_scope_with_multiple_targets_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        real_ids = [c.geometry_entity_id for c in group.candidates if not c.is_no_match_placeholder]
        payload, _ = _valid_payload(
            group, callout_scope="single", reviewed_target_geometry_ids=real_ids
        )
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.SINGLE_SCOPE_MULTIPLE_TARGETS.value, _codes(result))


class MultiTargetScopeTests(unittest.TestCase):
    def test_multiple_scope_with_targets_is_accepted(self) -> None:
        group = _build_group_with_two_candidates()
        real_ids = [c.geometry_entity_id for c in group.candidates if not c.is_no_match_placeholder]
        payload, _ = _valid_payload(
            group,
            callout_scope="multiple",
            review_label="valid_secondary_target",
            reviewed_target_geometry_ids=real_ids,
        )
        result = import_review(payload, group)
        self.assertTrue(result.valid, result.errors)

    def test_multiple_scope_with_no_targets_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(
            group,
            callout_scope="multiple",
            review_label="valid_secondary_target",
            reviewed_target_geometry_ids=[],
        )
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.MULTI_TARGET_SCOPE_NO_TARGETS.value, _codes(result))

    def test_typical_scope_with_no_targets_and_no_valid_target_label_is_accepted(self) -> None:
        # "typical" scope with a NO_VALID_TARGET review is legitimate --
        # e.g. a "TYP" callout that turns out to reference nothing real.
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(
            group,
            callout_scope="typical",
            review_label="no_valid_target",
            reviewed_target_geometry_ids=[],
        )
        result = import_review(payload, group)
        self.assertTrue(result.valid, result.errors)


class LeaderSupportNotTargetTests(unittest.TestCase):
    def test_leader_support_not_target_with_no_targets_is_accepted(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(
            group, review_label="leader_support_not_target", reviewed_target_geometry_ids=[]
        )
        result = import_review(payload, group)
        self.assertTrue(result.valid, result.errors)

    def test_leader_support_not_target_with_targets_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, review_label="leader_support_not_target")
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.LEADER_SUPPORT_AS_FINAL_TARGET.value, _codes(result))


class ReviewerAndTimestampTests(unittest.TestCase):
    def test_missing_reviewer_id_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, reviewer_id=None)
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.MISSING_REVIEWER_ID.value, _codes(result))

    def test_blank_reviewer_id_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, reviewer_id="   ")
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.MISSING_REVIEWER_ID.value, _codes(result))

    def test_missing_timestamp_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, reviewed_at=None)
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.INVALID_TIMESTAMP.value, _codes(result))

    def test_malformed_timestamp_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, reviewed_at="not-a-timestamp")
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.INVALID_TIMESTAMP.value, _codes(result))


class SchemaVersionTests(unittest.TestCase):
    def test_unsupported_schema_version_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, export_schema_version="0.1")
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.UNSUPPORTED_SCHEMA_VERSION.value, _codes(result))

    def test_matching_schema_version_is_accepted(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group)
        result = import_review(payload, group, existing_outcome_ids=set())
        self.assertTrue(result.valid, result.errors)


class InvalidEnumValueTests(unittest.TestCase):
    def test_invalid_review_label_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, review_label="not_a_real_label")
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.INVALID_REVIEW_LABEL.value, _codes(result))

    def test_invalid_callout_scope_is_rejected(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group, callout_scope="not_a_real_scope")
        result = import_review(payload, group)
        self.assertFalse(result.valid)
        self.assertIn(ValidationErrorCode.INVALID_CALLOUT_SCOPE.value, _codes(result))


class DuplicateOutcomeRejectionTests(unittest.TestCase):
    def test_resubmitting_the_identical_review_is_rejected_as_duplicate(self) -> None:
        group = _build_group_with_two_candidates()
        payload, _ = _valid_payload(group)
        first = import_review(payload, group, existing_outcome_ids=set())
        self.assertTrue(first.valid, first.errors)
        second = import_review(payload, group, existing_outcome_ids={first.outcome.outcome_id})
        self.assertFalse(second.valid)
        self.assertIn(ValidationErrorCode.DUPLICATE_OUTCOME_ID.value, _codes(second))


if __name__ == "__main__":
    unittest.main()
