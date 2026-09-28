"""P0.6 regression: schedule/detail text must not mint physical takeoff quantity.

READ-ONLY proof of the legacy ``schedule_ingestion`` defect. This file must
FAIL under current production behavior. Do not change production code to make
it pass — that is a later, explicitly approved task.

Safety property under test
--------------------------
Schedule/detail-region text that contains a catalog-valid shape, with no
verified plan occurrence (no matching engineering token / plan callout /
geometry-derived member), must not contribute ``physical_quantity``.

``takeoff_eligible`` is NOT the asserted boundary: ``member_resolution``
treats that flag as "legend/context definition, not a member at all" and
keeps schedule-sourced members AUTO. The physical-quantity gate is
``QuantityEngine`` / takeoff export.
"""

from __future__ import annotations

import unittest

from services.engineering.schedule_grid import (
    is_bare_schedule_mark,
    resolve_schedule_mark,
)
from services.multimodal.schedule_ingestion import build_schedule_tokens
from services.prediction.label_ranker_hook import (
    is_incomplete_angle_missing_thickness,
)
from services.takeoff.quantity_engine import (
    METHOD_LABELED_CALLOUT,
    METHOD_SCHEDULE_CELL,
    quantity_engine,
)
from services.takeoff.takeoff_exporter import build_takeoff_rows
from services.token_extractor import extract_engineering_tokens


# Struct-like detail/note line scraped into a schedule region (P0.5 evidence).
_DETAIL_SCHEDULE_LINE = 'C6x10.5 AT 4\'-0"o.c. INFILL'
_SECTION = "C6X10.5"


def _schedule_only_document() -> dict:
    """Schedule/detail region only — no plan tokens, no geometry members."""

    return {
        "engineering_tokens": [],
        "schedules": [
            {
                "schedule_id": "schedule_table_p22_0",
                "page_number": 22,
                # Full-page bbox mirrors Struct schedule_table regions.
                "bbox": [68.52, 26.86, 2969.33, 2140.27],
                "text": f"WALL DETAIL\n{_DETAIL_SCHEDULE_LINE}\n",
                "confidence": 0.62,
            }
        ],
        "tables": [],
        "pages": [{"page_number": 22, "width": 3000, "height": 2200}],
    }


def _prediction_from_schedule_token(token: dict) -> dict:
    """Mirror the metadata QuantityEngine sees after Fusion on a schedule token.

    Production often drops top-level ``schedule_sourced`` on the served
    prediction but retains ``source_text.extraction_method``.
    """

    section = str(token.get("text") or token.get("raw_text") or "")
    page = int(token.get("page") or 0)
    bbox = list(token.get("bbox") or [0, 0, 0, 0])
    object_id = str(token.get("token_id") or "schedule_unknown")
    return {
        "object_id": object_id,
        "component_id": object_id,
        "section": section,
        "raw_text": section,
        "original_token": section,
        "prediction_source": "Fusion",
        "takeoff_eligible": True,
        "object_scope": "takeoff",
        "page_number": page,
        "page": page,
        "bbox": bbox,
        "bounding_box": bbox,
        "confidence": float(token.get("confidence") or 0.62),
        "source_text": {
            "raw": section,
            "normalized": section,
            "page_number": page,
            "bounding_box": bbox,
            "extraction_method": "schedule_on_drawing",
            "available": True,
        },
        "engineering_object_type": "schedule_member",
        "schedule_sourced": True,
        "extraction_method": "schedule_on_drawing",
        "schedule_id": token.get("schedule_id"),
        "schedule_source_line": token.get("schedule_source_line"),
    }


def _plan_callout_prediction(section: str, *, page: int = 5) -> dict:
    """Legitimate labeled plan occurrence (Fusion, not schedule_on_drawing)."""

    return {
        "object_id": f"token_p{page}_plan",
        "component_id": f"token_p{page}_plan",
        "section": section,
        "raw_text": section,
        "original_token": section,
        "prediction_source": "Fusion",
        "takeoff_eligible": True,
        "object_scope": "takeoff",
        "page_number": page,
        "page": page,
        "bbox": [400, 400, 460, 420],
        "bounding_box": [400, 400, 460, 420],
        "confidence": 0.85,
        "source_text": {
            "raw": section,
            "normalized": section,
            "page_number": page,
            "bounding_box": [400, 400, 460, 420],
            "extraction_method": "pdf_text",
            "available": True,
        },
    }


def _qty(section: str, predictions: list) -> int:
    report = quantity_engine.count(predictions)
    for result in report.results:
        if result.section == section:
            return int(result.physical_quantity)
    return 0


def _method(section: str, predictions: list) -> str | None:
    report = quantity_engine.count(predictions)
    for result in report.results:
        if result.section == section:
            return result.method
    return None


class LegacyScheduleQuantitySafetyTests(unittest.TestCase):
    def test_detail_schedule_text_without_plan_must_not_create_physical_quantity(
        self,
    ) -> None:
        """Case A — Struct-like detail line, no plan occurrence → qty must be 0.

        CURRENT BEHAVIOR (unsafe): build_schedule_tokens emits a schedule_*
        member; QuantityEngine counts METHOD_SCHEDULE_CELL with
        physical_quantity == 1. This assertion is the intended safety
        property and is expected to FAIL until an approved fix lands.
        """

        document = _schedule_only_document()
        self.assertEqual(document["engineering_tokens"], [])

        schedule_tokens = build_schedule_tokens(document)
        self.assertTrue(
            schedule_tokens,
            "precondition: legacy ingestion must emit a synthetic token "
            "for the detail line so the quantity defect is observable",
        )
        self.assertEqual({t["text"] for t in schedule_tokens}, {_SECTION})
        self.assertTrue(all(t.get("schedule_sourced") for t in schedule_tokens))
        self.assertEqual(
            schedule_tokens[0].get("schedule_source_line"),
            _DETAIL_SCHEDULE_LINE,
        )

        # No plan / geometry occurrence — only the synthetic schedule token.
        predictions = [_prediction_from_schedule_token(t) for t in schedule_tokens]
        self.assertEqual(len(predictions), 1)
        self.assertTrue(str(predictions[0]["object_id"]).startswith("schedule_"))
        self.assertNotIn(
            "geometry",
            str(predictions[0].get("prediction_source") or "").lower(),
        )

        qty = _qty(_SECTION, predictions)
        export = build_takeoff_rows(predictions)
        export_qty = sum(
            int(row.get("Quantity") or 0)
            for row in export
            if str(row.get("Section") or "") == _SECTION
        )

        self.assertEqual(
            qty,
            0,
            f"schedule/detail-only '{_DETAIL_SCHEDULE_LINE}' must not create "
            f"physical_quantity; got qty={qty} method={_method(_SECTION, predictions)!r} "
            f"export_qty={export_qty} export={export!r}",
        )
        self.assertEqual(export_qty, 0)

    def test_plan_callout_remains_distinguishable_from_schedule_only(
        self,
    ) -> None:
        """Case B — real plan Fusion callout may count under existing QE rules.

        When the shape already exists as an engineering token, schedule
        ingestion must not mint a second schedule_* instance. The plan
        callout alone is then a normal labeled_callout candidate.
        """

        document = {
            "engineering_tokens": [
                {
                    "token_id": "token_p5_plan",
                    "text": _SECTION,
                    "raw_text": _SECTION,
                    "page": 5,
                    "bbox": [400, 400, 460, 420],
                }
            ],
            "schedules": [
                {
                    "schedule_id": "schedule_table_p22_0",
                    "page_number": 22,
                    "bbox": [68.52, 26.86, 2969.33, 2140.27],
                    "text": f"WALL DETAIL\n{_DETAIL_SCHEDULE_LINE}\n",
                    "confidence": 0.62,
                }
            ],
            "tables": [],
        }
        schedule_tokens = build_schedule_tokens(document)
        self.assertEqual(
            schedule_tokens,
            [],
            "plan engineering token must suppress schedule_* minting for the same shape",
        )

        plan = _plan_callout_prediction(_SECTION, page=5)
        qty = _qty(_SECTION, [plan])
        self.assertEqual(qty, 1)
        self.assertEqual(_method(_SECTION, [plan]), METHOD_LABELED_CALLOUT)
        self.assertNotEqual(_method(_SECTION, [plan]), METHOD_SCHEDULE_CELL)

    def test_schedule_qty_three_without_plan_is_zero(self) -> None:
        """Case E — schedule qty N with no plan still contributes 0 physical qty."""

        document = {
            "engineering_tokens": [],
            "schedules": [
                {
                    "schedule_id": "s1",
                    "page_number": 1,
                    "bbox": [0, 0, 100, 100],
                    "text": "FRAMING SCHEDULE\nL4X4X1/4 QTY 3",
                    "confidence": 0.8,
                }
            ],
            "tables": [],
        }
        tokens = build_schedule_tokens(document)
        self.assertEqual(len(tokens), 3)
        predictions = [_prediction_from_schedule_token(t) for t in tokens]
        self.assertEqual(_qty("L4X4X1/4", predictions), 0)
        self.assertEqual(build_takeoff_rows(predictions), [])

    def test_two_plan_callouts_count_under_existing_semantics(self) -> None:
        """Case D — two real plan Fusion callouts still count (2)."""

        preds = [
            _plan_callout_prediction(_SECTION, page=5),
            {
                **_plan_callout_prediction(_SECTION, page=6),
                "object_id": "token_p6_plan",
                "component_id": "token_p6_plan",
            },
        ]
        self.assertEqual(_qty(_SECTION, preds), 2)
        self.assertEqual(_method(_SECTION, preds), METHOD_LABELED_CALLOUT)

    def test_schedule_plus_same_page_plan_no_double_count(self) -> None:
        """Case F — schedule + same-page plan → plan qty only."""

        plan = _plan_callout_prediction(_SECTION, page=22)
        schedule = _prediction_from_schedule_token(
            {
                "token_id": "schedule_dup",
                "text": _SECTION,
                "page": 22,
                "bbox": [68.52, 26.86, 2969.33, 2140.27],
                "confidence": 0.62,
                "schedule_id": "schedule_table_p22_0",
                "schedule_source_line": _DETAIL_SCHEDULE_LINE,
            }
        )
        qty = _qty(_SECTION, [plan, schedule])
        self.assertEqual(qty, 1)
        self.assertEqual(_method(_SECTION, [plan, schedule]), METHOD_LABELED_CALLOUT)
        report = quantity_engine.count([plan, schedule])
        result = next(r for r in report.results if r.section == _SECTION)
        self.assertEqual(result.excluded_counts.get("excluded_schedule_duplicates"), 1)


if __name__ == "__main__":
    unittest.main()
