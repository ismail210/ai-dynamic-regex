"""Tests for metadata extraction, correction, fusion, and adapter contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.document_intelligence import repair_ocr_text
from services.extraction_engine import run_extraction_preflight
from services.engineering.geometry_adapters import (
    adapter_for_path,
    geometry_capabilities,
)
from services.multimodal.correction_engine import suggest_token_corrections
from services.multimodal.pipeline import run_multimodal_pipeline
from services.pdf_parser import extract_document_structure
from services.token_extractor import (
    extract_engineering_token_records,
    extract_engineering_tokens,
)


def _drawing(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 75), "STRUCTURAL FRAMING PLAN", fontsize=18)
    page.insert_text((72, 130), "W18 X 35", fontsize=12)
    page.insert_text((72, 160), "HSS8X8X1/2", fontsize=12)
    page.insert_text((400, 710), "SHEET S-101", fontsize=10)
    page.draw_line(
        fitz.Point(70, 145), fitz.Point(330, 145), color=(0, 0, 0)
    )
    page.draw_rect(fitz.Rect(390, 680, 580, 760), color=(0, 0, 0))
    document.save(path)
    document.close()


class RichExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.temp.name) / "drawing.pdf"
        _drawing(self.pdf)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_legacy_tokens_remain_available(self) -> None:
        tokens = extract_engineering_tokens("W18X35 HSS8X8X1/2 A325")
        self.assertIn("W18X35", tokens)
        self.assertIn("HSS8X8X1/2", tokens)
        self.assertIn("A325", tokens)

    def test_document_has_layout_intelligence(self) -> None:
        document = extract_document_structure(str(self.pdf))
        self.assertIn("engineering_tokens", document)
        self.assertIn("tables", document)
        self.assertIn("title_blocks", document)
        self.assertIn("annotations", document)
        self.assertIn("extraction_quality", document)
        record = next(
            token
            for token in document["engineering_tokens"]
            if token["normalized_text"] == "W18X35"
        )
        for key in (
            "text",
            "page",
            "bbox",
            "rotation",
            "font",
            "line",
            "block",
            "confidence",
            "reading_order",
            "context",
            "surrounding_text",
            "extraction_status",
            "diagnostics",
        ):
            self.assertIn(key, record)
        self.assertIn(
            record["extraction_status"],
            {"VALID", "SUSPICIOUS", "BROKEN", "INVALID"},
        )
        diagnostics = document["extraction_diagnostics"]
        self.assertIn("status_counts", diagnostics)
        self.assertIn("pages", diagnostics)
        self.assertEqual(sum(diagnostics["status_counts"].values()), len(document["engineering_tokens"]))

    def test_ocr_repair_is_conservative(self) -> None:
        repaired, changes = repair_ocr_text("W18 × 35")
        self.assertEqual(repaired, "W18X35")
        self.assertTrue(changes)

    def test_extraction_preflight_does_not_start_prediction(self) -> None:
        report = run_extraction_preflight(self.pdf)
        self.assertEqual(report["stage"], "extracted")
        self.assertFalse(report["prediction_started"])
        self.assertGreater(len(report["tokens"]), 0)
        self.assertIn("quality", report)
        self.assertIn("layout", report)


class AdapterAndCorrectionTests(unittest.TestCase):
    def test_capability_contract(self) -> None:
        capabilities = {
            item["format"]: item for item in geometry_capabilities()
        }
        self.assertTrue(capabilities["pdf"]["available"])
        self.assertFalse(capabilities["3dm"]["available"])
        self.assertFalse(capabilities["dwg"]["available"])
        self.assertEqual(
            adapter_for_path("drawing.pdf").capability().format, "pdf"
        )

    def test_ocr_shape_correction(self) -> None:
        suggestions = suggest_token_corrections(
            "W18X3S", expected_family="W"
        )
        self.assertTrue(suggestions)
        self.assertEqual(suggestions[0].corrected, "W18X35")

    def test_ai_first_fusion_does_not_require_database_to_decide(self) -> None:
        from services.multimodal.fusion_engine import FUSION_WEIGHTS, fusion_engine

        self.assertAlmostEqual(FUSION_WEIGHTS["database"], 0.0)
        self.assertEqual(
            max(FUSION_WEIGHTS, key=lambda key: FUSION_WEIGHTS[key]), "text"
        )
        prediction = fusion_engine.predict(
            {
                "token": {
                    "token_id": "token_test",
                    "text": "W18X3S",
                    "normalized_text": "W18X3S",
                    "page": 1,
                    "bbox": [10, 10, 40, 20],
                    "confidence": 0.7,
                },
                "geometry": {"objects": []},
                "graph": {"nodes": [], "edges": []},
                "source_file": "demo.pdf",
            }
        )
        payload = prediction.to_dict()
        self.assertEqual(payload["database_role"], "verification_only")
        self.assertTrue(payload["features"]["fusion"]["ai_first"])
        self.assertFalse(payload["features"]["fusion"]["database_decides_prediction"])
        # No geometry/graph evidence is provided in this fixture, so the
        # correct role is "other" (unknown) — not a fabricated "beam" default
        # — which allocate_component_id prefixes as "Component_". See
        # rule_engine._infer_role: a missing orientation signal must not
        # silently resolve to 0.0 degrees and therefore "beam".
        self.assertTrue(
            str(payload["component_id"]).startswith(
                ("Beam_", "Section_", "Member_", "Column_", "Component_")
            )
        )
        self.assertEqual(payload["section"], "W18X35")


class MultimodalPipelineTests(unittest.TestCase):
    def test_pipeline_returns_all_modalities(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "drawing.pdf"
            _drawing(pdf)
            result = run_multimodal_pipeline(pdf, persist=False)
            self.assertEqual(
                result["pipeline"], "text_geometry_graph_fusion"
            )
            self.assertGreater(result["summary"]["tokens"], 0)
            self.assertIn("geometry", result)
            self.assertIn("graph", result)
            self.assertIn("predictions", result)
            self.assertIn("validation", result)
            prediction = result["predictions"][0]
            self.assertIn("section", prediction)
            self.assertIn("alternatives", prediction)
            self.assertIn("explanation", prediction)
            self.assertIn("geometry_preview", prediction)
            self.assertIn("graph_preview", prediction)


if __name__ == "__main__":
    unittest.main()
