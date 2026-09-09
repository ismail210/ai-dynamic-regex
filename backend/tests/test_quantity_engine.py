"""Focused tests for conservative PDF-only quantity estimates."""

from __future__ import annotations

import unittest

from services.engineering.context_scope import reassert_prediction_scope
from services.multimodal.duplicate_detector import merge_duplicate_predictions
from services.takeoff.quantity_engine import (
    METHOD_INSUFFICIENT,
    METHOD_LABELED_CALLOUT,
    METHOD_SCHEDULE_CELL,
    quantity_engine,
)


def _prediction(
    section: str,
    *,
    source: str = "Fusion",
    object_id: str = "candidate",
    page: int = 1,
    bbox=None,
    eligible: bool = True,
    scope: str = "takeoff",
    **extra,
) -> dict:
    return {
        "object_id": object_id,
        "component_id": object_id,
        "section": section,
        "predicted_shape": section,
        "corrected_token": section,
        "original_token": section,
        "raw_text": section,
        "prediction_source": source,
        "page": page,
        "page_number": page,
        "bbox": bbox or [100, 100, 120, 110],
        "bounding_box": bbox or [100, 100, 120, 110],
        "source_text": {
            "raw": extra.get("original_token") or extra.get("raw_text") or section,
            "normalized": extra.get("original_token") or extra.get("raw_text") or section,
            "page_number": page,
            "bounding_box": bbox or [100, 100, 120, 110],
            "token_id": object_id,
        },
        "takeoff_eligible": eligible,
        "object_scope": scope,
        "confidence": 0.8,
        **extra,
    }


def _by_section(report) -> dict:
    return {result.section: result for result in report.results}


def _title_blocks(page: int, title: str) -> list[dict]:
    return [
        {
            "page_number": page,
            "bbox": [2700, 1800, 2800, 1810],
            "text": "DRAWING TITLE:",
        },
        {
            "page_number": page,
            "bbox": [2700, 1814, 2950, 1850],
            "text": title,
        },
    ]


class QuantityEngineTests(unittest.TestCase):
    def test_basic_labeled_count(self) -> None:
        report = quantity_engine.count(
            [
                _prediction("W12X16", object_id="w1"),
                _prediction("W12X16", object_id="w2", page=2),
                _prediction("W16X26", object_id="w3"),
            ]
        )
        results = _by_section(report)
        self.assertEqual(results["W12X16"].physical_quantity, 2)
        self.assertEqual(results["W16X26"].physical_quantity, 1)
        self.assertEqual(results["W12X16"].method, METHOD_LABELED_CALLOUT)

    def test_geometry_does_not_increase_quantity(self) -> None:
        report = quantity_engine.count(
            [
                _prediction("W12X16", object_id="fusion"),
                _prediction(
                    "W12X16", source="Geometry", object_id="geometry-1"
                ),
                _prediction(
                    "W12X16",
                    source="Geometry",
                    object_id="geometry-2",
                    missing_label_prediction={"section": "W12X16"},
                ),
            ]
        )
        result = _by_section(report)["W12X16"]
        self.assertEqual(result.physical_quantity, 1)
        self.assertEqual(
            result.excluded_counts["excluded_geometry_duplicates"], 2
        )

    def test_detail_reference_is_excluded(self) -> None:
        report = quantity_engine.count(
            [
                _prediction(
                    "W12X230",
                    eligible=False,
                    scope="detail_reference",
                )
            ]
        )
        self.assertNotIn("W12X230", _by_section(report))
        self.assertEqual(report.excluded_counts["scope_ineligible"], 1)

    def test_non_member_dimension_is_excluded(self) -> None:
        report = quantity_engine.count(
            [
                _prediction(
                    "",
                    eligible=False,
                    scope="non_member_dimension",
                    raw_text='1/2"',
                    original_token='1/2"',
                )
            ]
        )
        self.assertEqual(report.results, [])
        self.assertEqual(report.excluded_counts["scope_ineligible"], 1)

    def test_existing_18_point_ocr_merge_precedes_counting(self) -> None:
        raw = [
            _prediction("W12X16", object_id="ocr-1"),
            _prediction(
                "W12X16",
                object_id="ocr-2",
                bbox=[101, 100, 121, 110],
            ),
        ]
        deduped = merge_duplicate_predictions(raw)["predictions"]
        report = quantity_engine.count(deduped)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(
            _by_section(report)["W12X16"].physical_quantity, 1
        )

    def test_repeat_count_is_ignored(self) -> None:
        report = quantity_engine.count(
            [_prediction("W12X16", repeat_count=148)]
        )
        self.assertEqual(
            _by_section(report)["W12X16"].physical_quantity, 1
        )

    def test_geometry_only_unlabeled_member_is_insufficient(self) -> None:
        report = quantity_engine.count(
            [
                _prediction(
                    "",
                    source="Geometry",
                    geometry_preview={"kind": "line"},
                    missing_label_prediction={"reason": "unlabeled line"},
                )
            ]
        )
        result = _by_section(report)[""]
        self.assertEqual(result.physical_quantity, 0)
        self.assertEqual(result.method, METHOD_INSUFFICIENT)
        self.assertEqual(result.confidence, 0.0)

    def test_typical_framing_plan_remains_countable(self) -> None:
        prediction = _prediction("W12X16")
        document = {
            "title_blocks": _title_blocks(
                1, "TYPICAL FRAMING PLAN - LEVEL 06-10"
            )
        }
        reassert_prediction_scope([prediction], document)
        self.assertEqual(
            _by_section(quantity_engine.count([prediction]))[
                "W12X16"
            ].physical_quantity,
            1,
        )

    def test_steel_sections_and_details_remains_countable(self) -> None:
        prediction = _prediction("HSS6X4X3/8")
        document = {
            "title_blocks": _title_blocks(
                1, "STEEL SECTIONS AND DETAILS"
            )
        }
        reassert_prediction_scope([prediction], document)
        self.assertEqual(
            _by_section(quantity_engine.count([prediction]))[
                "HSS6X4X3/8"
            ].physical_quantity,
            1,
        )

    def test_clip_length_is_excluded_by_existing_scope_gate(self) -> None:
        prediction = _prediction(
            "L3X3X1/4",
            raw_text="L3x3x1/4x0'-3\"",
            original_token="L3x3x1/4x0'-3\"",
        )
        reassert_prediction_scope([prediction], {})
        report = quantity_engine.count([prediction])
        self.assertNotIn("L3X3X1/4", _by_section(report))
        self.assertEqual(report.excluded_counts["scope_ineligible"], 1)

    def test_explicit_schedule_metadata_sets_schedule_method(self) -> None:
        report = quantity_engine.count(
            [
                _prediction(
                    "W10X33",
                    engineering_object_type="schedule_member",
                )
            ]
        )
        self.assertEqual(
            _by_section(report)["W10X33"].method, METHOD_SCHEDULE_CELL
        )

    def test_schedule_cell_does_not_double_count_same_page_callout(self) -> None:
        report = quantity_engine.count(
            [
                _prediction("W10X33", object_id="callout"),
                _prediction(
                    "W10X33",
                    object_id="schedule",
                    engineering_object_type="schedule_member",
                ),
            ]
        )
        result = _by_section(report)["W10X33"]
        self.assertEqual(result.physical_quantity, 1)
        self.assertEqual(result.method, METHOD_LABELED_CALLOUT)
        self.assertEqual(result.excluded_counts["excluded_schedule_duplicates"], 1)

    def test_schedule_cell_counts_when_no_callout_on_page(self) -> None:
        report = quantity_engine.count(
            [
                _prediction(
                    "W10X33",
                    object_id="schedule",
                    engineering_object_type="schedule_member",
                )
            ]
        )
        self.assertEqual(_by_section(report)["W10X33"].physical_quantity, 1)
        self.assertEqual(
            _by_section(report)["W10X33"].method, METHOD_SCHEDULE_CELL
        )

    def test_explicit_typ_multiplier_on_labeled_callout(self) -> None:
        report = quantity_engine.count(
            [
                _prediction(
                    "W12X16",
                    object_id="typ",
                    context={"line_text": "W12X16 TYP x 3"},
                )
            ]
        )
        self.assertEqual(_by_section(report)["W12X16"].physical_quantity, 3)

    def test_bare_typ_defaults_to_one(self) -> None:
        report = quantity_engine.count(
            [
                _prediction(
                    "W12X16",
                    object_id="bare",
                    context={"line_text": "W12X16 TYP"},
                )
            ]
        )
        self.assertEqual(_by_section(report)["W12X16"].physical_quantity, 1)

    def test_typ_does_not_apply_to_geometry(self) -> None:
        report = quantity_engine.count(
            [
                _prediction(
                    "W12X16",
                    source="Geometry",
                    object_id="geo",
                    context={"line_text": "W12X16 TYP x 4"},
                    missing_label=True,
                )
            ]
        )
        result = _by_section(report)["W12X16"]
        self.assertEqual(result.physical_quantity, 0)
        self.assertEqual(result.method, METHOD_INSUFFICIENT)


if __name__ == "__main__":
    unittest.main()
