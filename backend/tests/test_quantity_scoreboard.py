"""Phase 0 quantity scoreboard: separate from section precision."""

from __future__ import annotations

import unittest

from services.takeoff.quantity_engine import QuantityResult, QuantityReport, quantity_engine
from services.takeoff.quantity_scoreboard import (
    build_quantity_scoreboard,
    build_scoreboards,
)
from services.takeoff.takeoff_exporter import build_takeoff_rows


def _gt(*pairs: tuple[str, int]) -> dict:
    return {
        "items": [
            {
                "canonical_label": section,
                "quantity": quantity,
                "metric_scope": "structural_member",
            }
            for section, quantity in pairs
        ]
    }


class QuantityScoreboardTests(unittest.TestCase):
    def test_undercount_mae_does_not_change_section_precision(self) -> None:
        report = quantity_engine.count(
            [
                {
                    "section": "W12X16",
                    "prediction_source": "Fusion",
                    "takeoff_eligible": True,
                    "confidence": 0.9,
                    "object_id": f"w12-{index}",
                }
                for index in range(59)
            ]
        )
        scoreboard = build_quantity_scoreboard(
            report,
            _gt(("W12X16", 119), ("W10X33", 81)),
        )
        self.assertEqual(scoreboard["predicted_total"], 59)
        self.assertEqual(scoreboard["expected_total"], 200)
        self.assertEqual(scoreboard["undercount"], 141)
        self.assertEqual(scoreboard["overcount"], 0)
        by_section = {row["section"]: row for row in scoreboard["rows"]}
        self.assertEqual(by_section["W12X16"]["delta"], -60)
        self.assertEqual(by_section["W12X16"]["bias"], "undercount")
        self.assertEqual(by_section["W10X33"]["bias"], "missing")
        self.assertTrue(scoreboard["does_not_affect_section_precision"])
        self.assertFalse(scoreboard["is_true_physical_quantity"])
        self.assertNotIn("precision", scoreboard)
        self.assertNotIn("recall", scoreboard)

    def test_geometry_does_not_inflate_quantity_scoreboard(self) -> None:
        predictions = [
            {
                "section": "HSS6X6X3/8",
                "prediction_source": "Fusion",
                "takeoff_eligible": True,
                "confidence": 0.87,
                "object_id": "hss-1",
                "page_number": 7,
            },
            {
                "section": "HSS6X6X3/8",
                "prediction_source": "Geometry",
                "takeoff_eligible": True,
                "missing_label_prediction": True,
                "confidence": 0.8,
                "object_id": "hss-geo",
                "page_number": 7,
            },
        ]
        report = quantity_engine.count(predictions)
        self.assertEqual(report.results[0].physical_quantity, 1)
        scoreboard = build_quantity_scoreboard(report, _gt(("HSS6X6X3/8", 48)))
        self.assertEqual(scoreboard["predicted_total"], 1)
        self.assertEqual(scoreboard["undercount"], 47)

    def test_scoreboards_keep_section_recognition_untouched(self) -> None:
        section = {
            "true_positive": 40,
            "false_positive": 2,
            "false_negative": 1,
            "precision": 0.9524,
            "recall": 0.9756,
            "f1": 0.9639,
        }
        report = QuantityReport(
            results=[
                QuantityResult(
                    section="W10X33",
                    physical_quantity=79,
                    method="labeled_callout",
                    confidence=0.99,
                )
            ]
        )
        boards = build_scoreboards(
            section_recognition=section,
            quantity_report=report,
            ground_truth=_gt(("W10X33", 81)),
        )
        self.assertEqual(boards["section_recognition"], section)
        self.assertEqual(boards["quantity"]["predicted_total"], 79)
        self.assertEqual(boards["quantity"]["undercount"], 2)
        self.assertEqual(boards["section_recognition"]["precision"], 0.9524)

    def test_exporter_includes_quantity_method_without_changing_count(self) -> None:
        rows = build_takeoff_rows(
            [
                {
                    "section": "W18X35",
                    "family": "W",
                    "prediction_source": "Fusion",
                    "takeoff_eligible": True,
                    "confidence": 0.9,
                    "database_match": True,
                },
                {
                    "section": "W18X35",
                    "family": "W",
                    "prediction_source": "Fusion",
                    "takeoff_eligible": True,
                    "confidence": 0.8,
                    "database_match": True,
                },
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Quantity"], 2)
        self.assertEqual(rows[0]["Quantity Method"], "labeled_callout")


if __name__ == "__main__":
    unittest.main()
