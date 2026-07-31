"""Tests for takeoff ground-truth Excel parsing and paired dataset scaffolding."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz
import pandas as pd

from config import settings
from services.entity_taxonomy import classify_category
from services.takeoff.ground_truth_evaluation import (
    evaluate_against_excel,
    persist_evaluation_report,
)
from services.takeoff.ground_truth_excel import parse_ground_truth_excel
from services.takeoff.paired_dataset_builder import build_pair_rows, list_training_pairs
from services.takeoff.takeoff_exporter import build_takeoff_rows
from services.takeoff.takeoff_validation import (
    _register_uploaded_pair,
    validate_takeoff,
)


class EntityTaxonomyTests(unittest.TestCase):
    def test_expanded_entities(self) -> None:
        self.assertEqual(classify_category("W18X35").category, "structural_section")
        self.assertEqual(classify_category("A325").category, "bolt")
        self.assertEqual(classify_category("PL1/2").category, "plate")
        self.assertIn(classify_category("JOIST24K").category, {"joist", "unknown", "miscellaneous"})


class GroundTruthExcelTests(unittest.TestCase):
    def test_parse_real_estimate_if_present(self) -> None:
        sample = settings.training_excel_dir / "burrville_es.xlsm"
        if not sample.exists():
            sample = settings.training_dir / "excels" / "Ketcham ES Project Estimate1.xlsm"
        if not sample.exists():
            self.skipTest("No sample Excel available")
        result = parse_ground_truth_excel(sample)
        self.assertGreater(result["unique_labels"], 0)
        self.assertGreater(result["total_quantity"], 0)
        self.assertTrue(result["aggregates"])
        self.assertFalse(result.get("excel_is_prediction"))
        self.assertEqual(result.get("role"), "ground_truth")

    def test_aisc_flexible_takeoff_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aisc_takeoff.xlsx"
            pd.DataFrame(
                [
                    {
                        "AISC_Manual_Label": "W18X35",
                        "Type": "W",
                        "Count": 3,
                        "Length": 12.0,
                        "Weight": 35.0,
                        "Mark": "B1",
                    },
                    {
                        "AISC_Manual_Label": "HSS6X6X5/8",
                        "Type": "HSS",
                        "Count": 1,
                        "Length": 8.0,
                        "Weight": 40.0,
                        "Mark": "C1",
                    },
                ]
            ).to_excel(path, index=False)
            result = parse_ground_truth_excel(path)
            self.assertEqual(result["parser"], "engineering_excel_loader")
            self.assertFalse(result["excel_is_prediction"])
            self.assertGreaterEqual(result["unique_labels"], 2)
            labels = {item["canonical_label"] for item in result["aggregates"]}
            self.assertIn("W18X35", labels)
            self.assertIn("HSS6X6X5/8", labels)

    def test_schedule_sheet_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schedule.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame = pd.DataFrame(
                    [
                        [None] * 6,
                        [None, "Type", "Mark", "Length", "Weight", "Count"],
                        [None, "W18X35", "B1", "10'-0\"", 35, 2],
                        [None, "W21X44", "B2", "12'-0\"", 44, 1],
                    ]
                )
                frame.to_excel(
                    writer, sheet_name="StructuralFramingSchedule", index=False, header=False
                )
            result = parse_ground_truth_excel(path)
            self.assertEqual(result["parser"], "ground_truth_excel")
            by_label = {
                item["canonical_label"]: item["quantity"] for item in result["aggregates"]
            }
            self.assertEqual(by_label.get("W18X35"), 2)
            self.assertEqual(by_label.get("W21X44"), 1)


class GroundTruthEvaluationTests(unittest.TestCase):
    def test_precision_recall_missing_extra(self) -> None:
        ground_truth = {
            "source_file": "demo.xlsx",
            "parser": "test",
            "items": [
                {
                    "canonical_label": "W18X35",
                    "quantity": 2,
                    "length": 10.0,
                    "weight": 35.0,
                    "mark": "B1",
                    "member_type": "beam",
                    "entity_class": "steel_section",
                },
                {
                    "canonical_label": "W21X44",
                    "quantity": 1,
                    "length": 12.0,
                    "weight": 44.0,
                    "mark": "B2",
                    "member_type": "beam",
                    "entity_class": "steel_section",
                },
            ],
            "aggregates": [],
            "unique_labels": 2,
            "total_quantity": 3,
        }
        predictions = [
            {"section": "W18X35", "length": 10.0, "weight": 35.0, "component_id": "B1"},
            {"section": "W18X35", "length": 10.1, "weight": 35.0, "component_id": "B1"},
            {"section": "HSS6X6X1/2", "length": 8.0, "weight": 20.0, "component_id": "C9"},
        ]
        report = evaluate_against_excel(predictions, ground_truth=ground_truth)
        metrics = report["metrics"]
        self.assertEqual(metrics["section"]["true_positive"], 1)
        self.assertEqual(metrics["section"]["false_positive"], 1)
        self.assertEqual(metrics["section"]["false_negative"], 1)
        self.assertAlmostEqual(metrics["precision"], 0.5)
        self.assertAlmostEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["quantity_accuracy"], 1.0)
        self.assertEqual(len(report["missing_elements"]), 1)
        self.assertEqual(report["missing_elements"][0]["section"], "W21X44")
        self.assertEqual(len(report["extra_elements"]), 1)
        self.assertEqual(report["extra_elements"][0]["section"], "HSS6X6X1/2")
        self.assertFalse(report["excel_is_prediction"])

    def test_persist_evaluation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            fake_settings = mock.MagicMock(takeoff_exports_dir=dest)
            with mock.patch(
                "services.takeoff.ground_truth_evaluation.settings", fake_settings
            ):
                report = evaluate_against_excel(
                    [{"section": "W18X35"}],
                    ground_truth={
                        "source_file": "gt.xlsx",
                        "items": [{"canonical_label": "W18X35", "quantity": 1}],
                        "aggregates": [],
                    },
                )
                path = persist_evaluation_report(
                    report, pdf_name="demo.pdf", excel_name="gt.xlsx"
                )
                self.assertTrue(path.exists())
                self.assertTrue(path.with_suffix(".md").exists())
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["pdf_file"], "demo.pdf")
                self.assertIn("precision", payload["metrics"])


class PairRegistrationTests(unittest.TestCase):
    def test_register_uploaded_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_dir = root / "pdf"
            excel_dir = root / "excel"
            pdf_dir.mkdir()
            excel_dir.mkdir()
            pdf = root / "upload.pdf"
            excel = root / "upload.xlsx"
            pdf.write_bytes(b"%PDF-1.4")
            excel.write_bytes(b"PK")
            manifest = root / "pair_manifest.json"
            fake_settings = mock.MagicMock(
                training_pdf_dir=pdf_dir,
                training_excel_dir=excel_dir,
                pair_manifest_path=manifest,
            )
            with mock.patch(
                "services.takeoff.takeoff_validation.settings", fake_settings
            ):
                pair_id = _register_uploaded_pair(pdf, excel)
                self.assertEqual(pair_id, "upload")
                self.assertTrue((pdf_dir / "upload.pdf").exists())
                self.assertTrue((excel_dir / "upload.xlsx").exists())
                data = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(data["pairs"][0]["id"], "upload")
                self.assertEqual(data["pairs"][0]["role"], "ground_truth_pair")

    def test_validate_takeoff_auto_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "pair_demo.pdf"
            excel = root / "pair_demo.xlsx"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "W18X35", fontsize=14)
            doc.save(pdf)
            doc.close()
            with pd.ExcelWriter(excel, engine="openpyxl") as writer:
                frame = pd.DataFrame(
                    [
                        [None, "Type", "Length", "Weight", "Count"],
                        [None, "W18X35", "10", 35, 1],
                    ]
                )
                frame.to_excel(
                    writer, sheet_name="StructuralFramingSchedule", index=False, header=False
                )

            fake_pipeline = {
                "predictions": [
                    {
                        "section": "W18X35",
                        "original_token": "W18X35",
                        "confidence": {"overall": 0.9, "level": "High"},
                        "geometry_preview": {"length": 10},
                        "features": {"database": {"exact_match": {"W": 35}}},
                    }
                ],
                "summary": {"pages": 1, "inference_time_ms": 1},
                "validation": {"summary": {"pass": 1, "warning": 0, "fail": 0}},
                "document_id": "demo",
            }
            exports = root / "exports"
            exports.mkdir()
            pdf_dir = root / "training_pdf"
            excel_dir = root / "training_excel"
            pdf_dir.mkdir()
            excel_dir.mkdir()
            manifest = root / "pair_manifest.json"
            fake_settings = mock.MagicMock(
                takeoff_exports_dir=exports,
                training_pdf_dir=pdf_dir,
                training_excel_dir=excel_dir,
                pair_manifest_path=manifest,
            )
            with mock.patch(
                "services.multimodal.pipeline.run_multimodal_pipeline",
                return_value=fake_pipeline,
            ), mock.patch(
                "services.takeoff.takeoff_validation.settings", fake_settings
            ), mock.patch(
                "services.takeoff.ground_truth_evaluation.settings", fake_settings
            ), mock.patch(
                "services.takeoff.paired_dataset_builder.build_paired_training_dataset",
                return_value={"built": True, "row_count": 1},
            ):
                result = validate_takeoff(
                    pdf_path=pdf,
                    excel_path=excel,
                    run_ai=True,
                    auto_register_pair=True,
                    auto_build_dataset=True,
                    persist_report=True,
                )
            self.assertEqual(result["excel_role"], "ground_truth_only")
            self.assertFalse(result["excel_is_prediction"])
            self.assertIn("precision", result["metrics"])
            self.assertEqual(result["registered_pair_id"], "pair_demo")
            self.assertTrue(result["dataset_build"].get("built"))
            self.assertTrue(Path(result["report_path"]).exists())


class PairedDatasetTests(unittest.TestCase):
    def test_list_pairs(self) -> None:
        pairs = list_training_pairs()
        self.assertIsInstance(pairs, list)

    def test_build_pair_rows_synthetic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "demo.pdf"
            xls = Path(tmp) / "demo.xlsx"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "W18X35 BEAM HSS6X6X5/8", fontsize=14)
            doc.save(pdf)
            doc.close()
            pd.DataFrame(
                [
                    [None, None],
                    [None, "Type", "Length", "Weight", "Count"],
                    [None, "W18X35", "10'-0\"", 35, 2],
                    [None, "HSS6X6X5/8", "8'-0\"", 40, 1],
                ]
            ).to_excel(xls, index=False, header=False)
            with pd.ExcelWriter(xls, engine="openpyxl") as writer:
                frame = pd.DataFrame(
                    [
                        [None] * 5,
                        [None, "Project", "Demo", None, None],
                        [None] * 5,
                        [None, "StructuralFramingSchedule", None, None, None],
                        [None, "Type", "Comments", "Length", "Weight"],
                        [None, "W18X35", "S01", "10'-0\"", 35],
                        [None, "HSS6X6X5/8", "S01", "8'-0\"", 40],
                    ]
                )
                frame.to_excel(
                    writer, sheet_name="StructuralFramingSchedule", index=False, header=False
                )

            report = build_pair_rows(pdf, xls, pair_id="demo")
            self.assertGreaterEqual(report["pdf_token_count"], 1)
            self.assertGreater(report["row_count"], 0)


class TakeoffExporterTests(unittest.TestCase):
    def test_build_rows(self) -> None:
        rows = build_takeoff_rows(
            [
                {
                    "token": "W18X35",
                    "prediction": "W18X35",
                    "database_match": True,
                    "confidence": {"overall": 0.9, "level": "High"},
                },
                {
                    "token": "W18X35",
                    "prediction": "W18X35",
                    "database_match": True,
                    "confidence": {"overall": 0.8, "level": "High"},
                },
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Quantity"], 2)


if __name__ == "__main__":
    unittest.main()
