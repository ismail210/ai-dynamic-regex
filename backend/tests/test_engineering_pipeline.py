"""Tests for the additive engineering validation modules."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.correction_dataset import build_training_sample, record_correction
from services.engineering.excel_loader import load_engineering_excel
from services.engineering.geometry_extractor import extract_geometry
from services.engineering.graph_builder import build_graph
from services.engineering.matching_engine import match_extraction_to_excel
from services.engineering.object_confidence import build_object_confidences, score_object_bundle
from services.engineering.suggestion_engine import generate_suggestions
from services.engineering.takeoff_interface import build_takeoff_preview
from services.engineering.validation_engine import validate_extraction
from services.pdf_parser import extract_document_structure, extract_text_from_pdf


def _make_sample_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
    page.insert_text((72, 120), "HSS8X8X1/2 COLUMN", fontsize=12)
    page.insert_text((72, 168), "See S-101", fontsize=10)
    # Simple rectangle / line drawings
    page.draw_rect(fitz.Rect(200, 200, 400, 260), color=(0, 0, 0), width=1)
    page.draw_line(fitz.Point(50, 300), fitz.Point(250, 300), color=(0, 0, 0), width=1)
    page.draw_circle(fitz.Point(450, 400), 30, color=(0, 0, 0), width=1)
    doc.save(path)
    doc.close()


class PdfParserCompatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "sample.pdf"
        _make_sample_pdf(self.pdf)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_legacy_extract_text_shape(self) -> None:
        result = extract_text_from_pdf(str(self.pdf))
        self.assertIn("pages", result)
        self.assertIn("text", result)
        self.assertIn("text_length", result)
        self.assertEqual(result["pages"], 1)
        self.assertIn("W18X35", result["text"].upper().replace(" ", ""))

    def test_rich_document_structure(self) -> None:
        doc = extract_document_structure(str(self.pdf))
        self.assertIn("document_id", doc)
        self.assertGreater(len(doc["words"]), 0)
        self.assertGreater(len(doc["lines"]), 0)
        self.assertGreater(len(doc["blocks"]), 0)
        line = doc["lines"][0]
        for key in ("object_id", "bbox", "font_size", "rotation", "page_number", "reading_order", "neighbors"):
            self.assertIn(key, line)


class EngineeringPipelineUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "sample.pdf"
        _make_sample_pdf(self.pdf)
        self.document = extract_document_structure(str(self.pdf))
        self.geometry = extract_geometry(str(self.pdf), document_structure=self.document)
        self.graph = build_graph(self.document, self.geometry)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_geometry_extraction(self) -> None:
        self.assertGreaterEqual(self.geometry["geometry_count"], 1)
        obj = self.geometry["objects"][0]
        for key in ("geometry_id", "kind", "bbox", "length", "width", "area", "center", "orientation"):
            self.assertIn(key, obj)

    def test_graph_builder(self) -> None:
        self.assertGreater(self.graph["stats"]["node_count"], 0)
        self.assertIn("nodes", self.graph)
        self.assertIn("edges", self.graph)

    def test_excel_loader_and_matching(self) -> None:
        excel_path = Path(self.tmp.name) / "schedule.xlsx"
        import pandas as pd

        pd.DataFrame(
            [
                {"Mark": "B1", "Shape": "W18X35", "Type": "Beam", "Count": 1, "Length": 20, "Weight": 35},
                {"Mark": "C1", "Shape": "HSS8X8X1/2", "Type": "Column", "Count": 1, "Length": 12, "Weight": 40},
            ]
        ).to_excel(excel_path, index=False)

        excel_json = load_engineering_excel(excel_path)
        self.assertEqual(excel_json["item_count"], 2)
        self.assertIn("W18X35", excel_json["summary"]["by_shape"])

        match = match_extraction_to_excel(
            document_structure=self.document,
            geometry=self.geometry,
            graph=self.graph,
            excel_json=excel_json,
        )
        self.assertIn("findings", match)
        self.assertIn("summary", match)

    def test_validation_confidence_suggestions_takeoff(self) -> None:
        match = match_extraction_to_excel(
            document_structure=self.document,
            geometry=self.geometry,
            graph=self.graph,
            excel_json={"items": [], "summary": {}},
        )
        confidences = build_object_confidences(
            document_structure=self.document,
            geometry=self.geometry,
            graph=self.graph,
            match_report=match,
        )
        self.assertGreater(len(confidences), 0)
        report = validate_extraction(
            document_structure=self.document,
            geometry=self.geometry,
            graph=self.graph,
            object_confidences=confidences,
        )
        self.assertIn("issues", report)
        self.assertIn("quality_score", report)

        suggestions = generate_suggestions(
            document_structure=self.document,
            geometry=self.geometry,
            graph=self.graph,
            match_report=match,
        )
        self.assertIn("suggestions", suggestions)

        preview = build_takeoff_preview(graph=self.graph)
        self.assertEqual(preview["status"], "preview_only")
        self.assertFalse(preview["export_ready"])

        bundle = score_object_bundle(0.8, 0.7, 0.6)
        self.assertIn(bundle.level, {"High", "Medium", "Low"})

    def test_correction_sample(self) -> None:
        sample = build_training_sample(
            features={"min_distance": 12},
            prediction={"expected_label": "W18X35"},
            correct_label="W21X44",
            correct_geometry=None,
            user_decision="edit",
            document_id="doc_test",
            object_id="obj_1",
        )
        self.assertTrue(sample["ready_for_training"])
        saved = record_correction(
            features=sample["input_features"],
            prediction=sample["prediction"],
            correct_label=sample["correct_label"],
            user_decision="approve",
            document_id="doc_test",
            object_id="obj_1",
        )
        self.assertIn("sample_id", saved)


if __name__ == "__main__":
    unittest.main()
