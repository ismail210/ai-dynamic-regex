"""Reviewer-package schema and independent approval-gate tests."""

from __future__ import annotations

import copy
import unittest

from scripts.build_column_schedule_gold_package import FIELDS, PAGES, REVIEW_STATES, _base_record
from scripts.validate_column_schedule_gold_package import summarize, validate_record


def _record() -> dict:
    page = PAGES[0]
    return {
        **_base_record(page, "S-501"),
        "record_id": "r1",
        "schedule_id": "s1",
        "schedule_title_raw": "COLUMN SCHEDULE",
        "schedule_class": "level_location_matrix",
        "region_bbox": [0, 0, 100, 100],
        "location_or_grid_raw": "A-1",
        "location_or_grid_normalized": "A-1",
        "level_raw": "FIRST -> ROOF",
        "level_normalized": "FIRST -> ROOF",
        "raw_cell_text": "W10X33",
        "canonical_section": "W10X33",
        "catalog_valid": True,
        "member_role": "column",
        "source_cell_bbox": [10, 10, 20, 20],
        "header_path": ["COLUMN SCHEDULE"],
        "proposal_method": "test",
    }


class ColumnScheduleGoldSchemaTests(unittest.TestCase):
    def test_builder_schema_has_two_explicit_review_statuses(self) -> None:
        self.assertIn("extraction_review_status", FIELDS)
        self.assertIn("physical_review_status", FIELDS)
        self.assertNotIn("reviewer_status", FIELDS)
        self.assertEqual(
            set(REVIEW_STATES),
            {"PENDING_REVIEW", "APPROVED", "CORRECTED", "REJECTED", "UNSURE"},
        )

    def test_prefill_is_unapproved_in_both_layers(self) -> None:
        record = _record()
        self.assertEqual(record["extraction_review_status"], "PENDING_REVIEW")
        self.assertEqual(record["physical_review_status"], "PENDING_REVIEW")
        self.assertEqual(validate_record(record), [])

    def test_extraction_can_be_approved_while_physical_is_unsure(self) -> None:
        record = _record()
        record["extraction_review_status"] = "APPROVED"
        record["physical_review_status"] = "UNSURE"
        self.assertEqual(validate_record(record), [])
        summary = summarize([record], {(record["document_id"], record["page_number"])})
        self.assertTrue(summary["matrix_parser_unblocked"])

    def test_pending_extraction_keeps_matrix_parser_blocked(self) -> None:
        record = _record()
        record["physical_review_status"] = "APPROVED"
        summary = summarize([record], {(record["document_id"], record["page_number"])})
        self.assertFalse(summary["matrix_parser_unblocked"])

    def test_legacy_or_unknown_status_is_rejected(self) -> None:
        record = _record()
        record["reviewer_status"] = "APPROVED"
        record["physical_review_status"] = "AUTO_APPROVED"
        errors = validate_record(record)
        self.assertTrue(any("legacy reviewer_status" in error for error in errors))
        self.assertTrue(any("invalid physical_review_status" in error for error in errors))

    def test_validation_does_not_mutate_prefill(self) -> None:
        record = _record()
        before = copy.deepcopy(record)
        validate_record(record)
        self.assertEqual(record, before)


if __name__ == "__main__":
    unittest.main()
