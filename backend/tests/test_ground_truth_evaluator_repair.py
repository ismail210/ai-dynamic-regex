"""Evaluator-only ground-truth repairs: member scope, imperial length, tons."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from config import settings
from services.takeoff.ground_truth_evaluation import (
    evaluate_against_excel,
    length_to_feet,
)
from services.takeoff.ground_truth_excel import parse_ground_truth_excel


def _burrville_excel() -> Path | None:
    candidates = [
        settings.training_excel_dir / "burrville_es.xlsm",
        Path(__file__).resolve().parents[1]
        / "uploads"
        / "engineering"
        / "Burrville-update Project Estimate1.xlsm",
        Path(__file__).resolve().parents[1]
        / "uploads"
        / "Burrville-update Project Estimate1__eeeb28b4ad36.xlsm",
        settings.training_dir / "excels" / "Burrville-update Project Estimate1.xlsm",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


class ImperialLengthTests(unittest.TestCase):
    def test_feet_inch_examples(self) -> None:
        self.assertAlmostEqual(length_to_feet("10'-6\""), 10.5)
        self.assertAlmostEqual(length_to_feet("9\""), 0.75)
        self.assertAlmostEqual(length_to_feet("6\""), 0.5)
        self.assertAlmostEqual(length_to_feet("13' - 1 3/16\""), 13 + (1 + 3 / 16) / 12)
        self.assertAlmostEqual(length_to_feet("12'-0\""), 12.0)
        self.assertAlmostEqual(length_to_feet("10.5"), 10.5)
        self.assertIsNone(length_to_feet(""))
        self.assertIsNone(length_to_feet(None))


class SyntheticWorkbookTests(unittest.TestCase):
    def test_connections_excluded_and_tonnage_uses_overall_weight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                framing = pd.DataFrame(
                    [
                        [None] * 6,
                        [None, "Type", "Comments", "Length", "Weight", "Overall Weight"],
                        [None, "W16X26", "S-101", "10'-6\"", 26, 0.1365],
                        [None, "L4X4X1/4", "S-101", "12'-0\"", 6.6, 0.0396],
                        [None, "1/2\"", "S-101", "6\"", 0, 0],
                    ]
                )
                framing.to_excel(
                    writer, sheet_name="StructuralFramingSchedule", index=False, header=False
                )
                connections = pd.DataFrame(
                    [
                        [None] * 6,
                        [None, "Type", "Comments", "Length", "Weight", "Overall Weight"],
                        [None, "L4X4X1/4", "S-101", "9\"", 6.6, 0.00247],
                        [None, "L4X4X1/4", "S-101", "9\"", 6.6, 0.00247],
                    ]
                )
                connections.to_excel(
                    writer,
                    sheet_name="StructuralConnectionSchedule",
                    index=False,
                    header=False,
                )
                plates = pd.DataFrame(
                    [
                        [None] * 5,
                        [None, "Type", "Comments", "area", "Weight"],
                        [None, "PL1/2", "S-101", 2.0, 40.8],
                    ]
                )
                plates.to_excel(
                    writer, sheet_name="StructuralPlateSchedule", index=False, header=False
                )
                home = pd.DataFrame(
                    [
                        [None, None, None, None, "Type", "Count", "Total Length", "Total Weight"],
                        [None, None, None, None, "W16X26", 1, "10'-6\"", 0.1365],
                        [None, None, None, None, "L4X4X1/4", 1, "12'-0\"", 0.0396],
                    ]
                )
                home.to_excel(writer, sheet_name="ProjectHome", index=False, header=False)

            gt = parse_ground_truth_excel(path)
            by_label = {
                item["canonical_label"]: item["quantity"] for item in gt["aggregates"]
            }
            self.assertEqual(by_label.get("L4X4X1/4"), 1)
            self.assertEqual(by_label.get("W16X26"), 1)
            self.assertNotIn("1/2\"", by_label)
            self.assertNotIn("1/2\"", {_norm_safe(k) for k in by_label})
            self.assertEqual(len(gt["connection_items"]), 2)
            self.assertEqual(
                {item["canonical_label"] for item in gt["plate_items"]}, {"PL1/2"}
            )
            self.assertNotIn("PL1/2", by_label)

            w16 = next(item for item in gt["aggregates"] if item["canonical_label"] == "W16X26")
            self.assertAlmostEqual(w16["tons"], 0.1365)
            self.assertEqual(w16["tonnage_source"], "overall_weight")
            occ = w16["occurrences"][0]
            self.assertEqual(occ["weight_plf"], 26)
            self.assertNotEqual(occ["weight_plf"], occ["overall_weight_tons"])

            report = evaluate_against_excel(
                [
                    {"section": "W16X26", "quantity": 1, "length": 10.5, "tons": 0.1365},
                    {"section": "L4X4X1/4", "quantity": 1, "length": 12.0, "tons": 0.0396},
                    {
                        "section": "",
                        "original_token": "1/2\"",
                        "object_scope": "non_member_dimension",
                        "takeoff_eligible": False,
                    },
                ],
                ground_truth=gt,
            )
            self.assertEqual(report["metrics"]["section"]["true_positive"], 2)
            self.assertEqual(report["metrics"]["section"]["false_positive"], 0)
            self.assertEqual(report["metrics"]["quantity"]["definition"], "schedule_row_vs_token")
            self.assertAlmostEqual(report["metrics"]["tonnage"]["gt_tons"], 0.1761, places=3)
            self.assertNotEqual(report["metrics"]["tonnage"]["gt_tons"], 26)
            extras = {row["section"] for row in report["extra_elements"]}
            self.assertNotIn("1/2\"", extras)
            self.assertNotIn("1/2\"", {_norm_safe(s) for s in extras})

    def test_families_remain_in_member_gt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "families.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame = pd.DataFrame(
                    [
                        [None, "Type", "Length", "Weight", "Overall Weight"],
                        [None, "W18X35", "10'-0\"", 35, 0.175],
                        [None, "HSS6X6X1/2", "8'-0\"", 40, 0.16],
                        [None, "L4X4X1/4", "6'-0\"", 6.6, 0.02],
                        [None, "C8X11.5", "12'-0\"", 11.5, 0.069],
                        [None, "WT8X13", "4'-0\"", 13, 0.026],
                    ]
                )
                frame.to_excel(
                    writer, sheet_name="StructuralFramingSchedule", index=False, header=False
                )
            gt = parse_ground_truth_excel(path)
            labels = {item["canonical_label"] for item in gt["aggregates"]}
            self.assertEqual(
                labels, {"W18X35", "HSS6X6X1/2", "L4X4X1/4", "C8X11.5", "WT8X13"}
            )


def _norm_safe(value: str) -> str:
    return str(value or "").upper().replace(" ", "").replace("-", "")


class RealBurrvilleTests(unittest.TestCase):
    def test_l4_quantity_is_framing_only(self) -> None:
        path = _burrville_excel()
        if path is None:
            self.skipTest("Burrville estimate workbook not available")
        gt = parse_ground_truth_excel(path)
        by_label = {
            item["canonical_label"]: item["quantity"] for item in gt["aggregates"]
        }
        self.assertEqual(by_label.get("L4X4X1/4"), 9)
        self.assertGreaterEqual(len(gt["connection_items"]), 1000)
        self.assertIn("W16X26", by_label)
        self.assertIn("HSS10X6X3/8", by_label)
        self.assertTrue(all(item.get("metric_scope") != "connection" for item in gt["items"]))
        l4 = next(item for item in gt["aggregates"] if item["canonical_label"] == "L4X4X1/4")
        self.assertEqual(l4["tonnage_source"], "overall_weight")
        self.assertGreater(l4["tons"], 0)
        self.assertLess(l4["tons"], 1)
        occ = l4["occurrences"][0]
        self.assertEqual(occ["weight_plf"], 6.6)
        self.assertLess(occ["overall_weight_tons"], 1)
        home = gt["section_rollups"].get("W12X16") or {}
        self.assertAlmostEqual(float(home.get("total_weight_tons") or 0), 9.45, places=1)
        report = evaluate_against_excel([], ground_truth=gt)
        missing = next(
            row for row in report["missing_elements"] if row["section"] == "L4X4X1/4"
        )
        self.assertEqual(missing["expected_quantity"], 9)
        self.assertGreater(report["metrics"]["tonnage"]["gt_tons"], 50)
        self.assertLess(report["metrics"]["tonnage"]["gt_tons"], 500)


if __name__ == "__main__":
    unittest.main()
