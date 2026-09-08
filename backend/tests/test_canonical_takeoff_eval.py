"""Canonical takeoff evaluator: scope, metric math, and harness/production parity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from services.takeoff.canonical_takeoff_eval import (
    CONNECTION_MISC,
    OUT_OF_SCOPE,
    PLATES,
    PRIMARY_FRAMING,
    aggregate_predictions,
    canonical_section,
    evaluate,
    parse_workbook_ground_truth,
)
from services.takeoff.ground_truth_evaluation import evaluate_against_excel
from services.takeoff.ground_truth_excel import parse_ground_truth_excel


def _framing_sheet(rows):
    return pd.DataFrame([[None] * 6, [None, "Type", "Mark", "Length", "Weight", "Count"], *rows])


class CanonicalSectionTests(unittest.TestCase):
    def test_folds_separators_and_cross(self):
        self.assertEqual(canonical_section("w 10 x 33"), "W10X33")
        self.assertEqual(canonical_section("HSS6X6X3/8"), "HSS6X6X3/8")
        self.assertEqual(canonical_section("HSS 6x6x3/8"), "HSS6X6X3/8")

    def test_round_hss_shorthand_resolves(self):
        self.assertEqual(canonical_section("HSS14X0.500"), "HSS14.000X0.500")

    def test_non_catalog_is_none(self):
        self.assertIsNone(canonical_section("HSS12X12X1/3"))   # not a real wall
        self.assertIsNone(canonical_section("W12X999"))
        self.assertIsNone(canonical_section("GRANDTOTAL:108"))


class ScopeTests(unittest.TestCase):
    def _wb(self, sheets: dict) -> Path:
        tmp = Path(tempfile.mkdtemp()) / "wb.xlsx"
        with pd.ExcelWriter(tmp, engine="openpyxl") as w:
            for name, frame in sheets.items():
                frame.to_excel(w, sheet_name=name, index=False, header=False)
        return tmp

    def test_connection_schedule_is_not_primary(self):
        wb = self._wb({
            "StructuralFramingSchedule": _framing_sheet([[None, "W16X26", "B1", 10, 26, 4]]),
            "StructuralConnectionSchedule": _framing_sheet(
                [[None, "L4X4X1/4", "Cx", 1, 6, 900]]),
        })
        gt = parse_workbook_ground_truth(wb)
        self.assertEqual(gt["scope_quantity"][PRIMARY_FRAMING], 4)
        self.assertEqual(gt["scope_quantity"][CONNECTION_MISC], 900)
        self.assertNotIn("L4X4X1/4", {a["canonical_label"] for a in gt["aggregates"]})
        self.assertEqual(gt["total_quantity"], 4)  # legacy key = primary only

    def test_bracing_schedule_is_primary(self):
        wb = self._wb({
            "StructuralBracingSchedule": _framing_sheet(
                [[None, "HSS10X10X3/8", "BR1", 20, 47, 6]]),
        })
        gt = parse_workbook_ground_truth(wb)
        self.assertEqual(gt["scope_quantity"][PRIMARY_FRAMING], 6)
        self.assertIn("HSS10X10X3/8", {a["canonical_label"] for a in gt["aggregates"]})

    def test_non_catalog_rows_dropped_with_reason_not_silently(self):
        wb = self._wb({
            "StructuralBracingSchedule": _framing_sheet([
                [None, "HSS12X12X1/2", "B1", 20, 76, 2],
                [None, "HSS12X12X1/3", "B2", 20, 58, 2],
            ]),
        })
        gt = parse_workbook_ground_truth(wb)
        self.assertEqual(gt["scope_quantity"][PRIMARY_FRAMING], 2)
        self.assertEqual([d["raw"] for d in gt["dropped"]], ["HSS12X12X1/3"])
        self.assertEqual(gt["dropped"][0]["reason"], "not_an_exact_aisc_label")


class MetricTests(unittest.TestCase):
    def _gt(self, counts):
        return {"scope": {PRIMARY_FRAMING: {s: [{"sheet": "S", "row": i, "raw": s}] * n
                                            for i, (s, n) in enumerate(counts.items())}},
                "scope_quantity": {PRIMARY_FRAMING: sum(counts.values()),
                                   PLATES: 0, CONNECTION_MISC: 0, OUT_OF_SCOPE: 0},
                "dropped_quantity": 0}

    def test_caught_is_min_and_never_over_100(self):
        gt = self._gt({"W12X26": 10, "HSS6X6X1/4": 5})
        preds = ([{"section": "W12X26"}] * 40) + ([{"section": "HSS6X6X1/4"}] * 5)
        ev = evaluate(preds, gt)
        self.assertEqual(ev["caught"], 15)            # min(40,10) + min(5,5)
        self.assertEqual(ev["ground_truth_total"], 15)
        self.assertEqual(ev["overall_success_pct"], 100.0)   # never > 100
        self.assertEqual(ev["false_positives"], 30)
        self.assertAlmostEqual(ev["precision_pct"], round(100 * 15 / 45, 2))

    def test_abstention_and_plate_not_counted_as_section_prediction(self):
        gt = self._gt({"W12X26": 4})
        preds = [
            {"section": "W12X26"},
            {"section": "", "review_status": "pending_review"},
            {"section": "", "plate_annotation_type": "PLATE"},
            {"section": "1/2\""},                       # not a catalog label
        ]
        agg = aggregate_predictions(preds)
        self.assertEqual(agg["counts"], {"W12X26": 1})
        self.assertEqual(agg["abstained"], 1)
        self.assertEqual(agg["plate_or_dimension"], 1)
        self.assertEqual(agg["catalog_invalid"], 1)


class HarnessProductionParityTests(unittest.TestCase):
    """The research harness (bench/) and production evaluate_against_excel must
    compute identical numbers from identical inputs."""

    def _real_pairs(self):
        root = Path(
            r"C:/Users/Bassam/AppData/Local/Temp/claude/"
            r"C--Users-Bassam-git-ai-dynamic-regex/"
            r"72f9ee78-682c-4ff9-9cd0-cde36eedf1cb/scratchpad/bench/PDF & Excel"
        )
        return [
            root / "Burrville" / "Burrville-update Project Estimate1.xlsm",
            root / "GCDC Building" / "GCDC Building 4-1 Project Estimate1.xlsm",
        ]

    def test_ground_truth_excel_wrapper_matches_canonical(self):
        for xls in self._real_pairs():
            if not xls.exists():
                self.skipTest("benchmark workbooks not present")
            a = parse_ground_truth_excel(xls)
            b = parse_workbook_ground_truth(xls)
            self.assertEqual(a["total_quantity"], b["total_quantity"])
            self.assertEqual(a["scope_quantity"], b["scope_quantity"])
            self.assertEqual(
                {x["canonical_label"]: x["quantity"] for x in a["aggregates"]},
                {x["canonical_label"]: x["quantity"] for x in b["aggregates"]},
            )

    def test_production_evaluator_matches_canonical_evaluate(self):
        xls = self._real_pairs()[0]
        if not xls.exists():
            self.skipTest("benchmark workbooks not present")
        gt = parse_workbook_ground_truth(xls)
        preds = [{"section": s, "takeoff_eligible": True}
                 for s, occ in list(gt["scope"][PRIMARY_FRAMING].items())[:5]
                 for _ in range(len(occ) // 2 or 1)]
        direct = evaluate(preds, gt)
        prod = evaluate_against_excel(preds, ground_truth=gt)
        self.assertEqual(prod["metrics"]["caught"], direct["caught"])
        self.assertEqual(prod["metrics"]["ground_truth_total"], direct["ground_truth_total"])
        self.assertEqual(prod["metrics"]["false_positives"], direct["false_positives"])
        self.assertEqual(prod["overall_success_pct"], direct["overall_success_pct"])
