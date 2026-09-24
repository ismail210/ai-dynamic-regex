"""Struct notation: inch angles, schedule marks, plates, shadow page gate."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

from config import settings
from services.annotation.parser import interpret_annotation
from services.annotation.plate_grammar import is_dim_first_bent_plate
from services.annotation.taxonomy import AnnotationType
from services.engineering.schedule_grid import (
    build_schedule_grids,
    is_bare_schedule_mark,
    lookup_schedule_row,
    schedule_assembly_sidecar,
    schedule_mark_map,
)
from services.engineering.shadow_page_gate import (
    filter_context_page_objects,
    filter_context_page_tokens,
)
from services.engineering_object_filter import classify_engineering_object
from services.multimodal.encoder_contracts import (
    AttentionResult,
    FusedFeatures,
    UnifiedFusionResult,
)
from services.pdf_parser import _ENGINEERING_PAGE_RE
from services.prediction.label_ranker_hook import is_incomplete_angle_missing_thickness
from services.prediction.orchestrator import predict_from_context
from services.token_extractor import extract_engineering_tokens


_BACKEND = Path(__file__).resolve().parents[1]
_STRUCT_PDF_CANDIDATES = (
    Path("/Users/hibareda/Desktop/Estima 3D/Struct.pdf"),
    Path("/Users/hibareda/Desktop/ai-dynamic-regex/backend/Testing Projects/Struct.pdf"),
)


def _struct_pdf() -> Path | None:
    for path in _STRUCT_PDF_CANDIDATES:
        if path.is_file():
            return path
    return None


def _word(text: str, x: float, y: float, page: int = 2) -> dict:
    return {
        "text": text,
        "bbox": [x, y, x + 30, y + 8],
        "page_number": page,
    }


def _accept_catalog(token: str) -> bool:
    return token in {
        "HSS6X6X1/2",
        "W8X21",
        "W8X28",
        "W10X49",
        "W16X36",
        "W24X62",
    }


def _struct_schedule_words() -> list:
    words = [
        _word("COLUMN", 100, 100),
        _word("SCHEDULE", 160, 100),
        _word("MARK", 100, 116),
        _word("SIZE", 200, 116),
        _word("BASE", 400, 116),
        _word("PLATE", 450, 116),
        _word("C1", 100, 134),
        _word("HSS", 200, 134),
        _word('6"x6"x1/2"', 250, 134),
        _word('14"x14"x3/4"', 400, 134),
        _word("LINTEL", 100, 400),
        _word("SCHEDULE", 160, 400),
        _word("MARK", 100, 420),
        _word("SIZE", 200, 420),
        _word("BEARING", 400, 420),
        _word("PLATE", 470, 420),
        _word("L1", 100, 440),
        _word("W8x21", 200, 440),
        _word("WITH", 250, 440),
        _word("BOTTOM", 400, 440),
        _word("PLATE", 460, 440),
        _word('6"x6"x1/2"', 520, 440),
        _word("L5", 100, 470),
        _word("12F16-IB", 200, 470),
        _word("PRECAST", 280, 470),
    ]
    return words


def _fake_fusion(section: str) -> UnifiedFusionResult:
    return UnifiedFusionResult(
        section=section,
        confidence=0.9,
        contributions={"text": 0.5, "geometry": 0.25, "graph": 0.25},
        attention=AttentionResult(
            weights={"text": 0.5, "geometry": 0.25, "graph": 0.25},
            logits={},
        ),
        fused_features=FusedFeatures(
            vector=[], modality_slices={}, availability={}, encoders={}
        ),
        candidate_scores=[{"shape": section, "score": 0.9}],
        reasons=["decoy"],
    )


class SafetyContractTests(unittest.TestCase):
    def test_incomplete_l_still_abstains_detector(self) -> None:
        self.assertTrue(is_incomplete_angle_missing_thickness("L4X4"))
        self.assertFalse(is_incomplete_angle_missing_thickness("L1"))
        self.assertFalse(is_incomplete_angle_missing_thickness("C1"))
        self.assertFalse(is_incomplete_angle_missing_thickness("L4X4X1/4"))

    def test_l1_is_a_mark_not_an_angle_section(self) -> None:
        self.assertTrue(is_bare_schedule_mark("L1"))
        self.assertTrue(is_bare_schedule_mark("L1A"))
        self.assertTrue(is_bare_schedule_mark("C1"))
        self.assertFalse(is_bare_schedule_mark("L4X4"))
        self.assertFalse(is_bare_schedule_mark("L4X4X1/4"))
        self.assertEqual(
            classify_engineering_object({"text": "L1", "normalized_text": "L1"}),
            "beam",
        )
        self.assertEqual(
            classify_engineering_object({"text": "C1", "normalized_text": "C1"}),
            "column",
        )
        self.assertEqual(
            classify_engineering_object(
                {"text": "L4X4", "normalized_text": "L4X4"}
            ),
            "steel_section",
        )
        parsed = interpret_annotation(raw_text="L1")
        self.assertEqual(parsed.annotation_type, AnnotationType.MEMBER_MARK.value)

    def test_geometry_inference_and_page_gate_defaults(self) -> None:
        self.assertFalse(settings.geometry_missing_label_inference_enabled)
        self.assertFalse(settings.shadow_context_page_gate_enabled)
        self.assertTrue(settings.schedule_grid_enabled)
        self.assertTrue(settings.schedule_mark_map_enabled)

    def test_orchestrator_does_not_import_excel(self) -> None:
        source = (_BACKEND / "services/prediction/orchestrator.py").read_text()
        tree = ast.parse(source)
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
        blob = " ".join(modules).lower()
        self.assertNotIn("excel", blob)
        self.assertNotIn("openpyxl", blob)
        self.assertNotIn("ground_truth", blob)


class InchAngleTokenTests(unittest.TestCase):
    def test_inch_angle_normalizes_any_size(self) -> None:
        cases = {
            '2"x2"x1/4" ANGLE': "L2X2X1/4",
            '4"x4"x1/4" ANGLE KICKER': "L4X4X1/4",
            '2 1/2"x2 1/2"x1/4" ANGLE': "L2-1/2X2-1/2X1/4",
            "L4X4X1/4": "L4X4X1/4",
            'HSS 6"x6"x1/2"': "HSS6X6X1/2",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertIn(expected, extract_engineering_tokens(raw))

    def test_bare_dims_are_not_angles(self) -> None:
        for raw in ("4x4x1/4", '14"x14"x3/4"'):
            tokens = extract_engineering_tokens(raw)
            self.assertFalse(
                any(token.startswith("L") for token in tokens),
                tokens,
            )


class ScheduleGridTests(unittest.TestCase):
    def test_struct_style_rows_build_mark_map_and_plates(self) -> None:
        grids = build_schedule_grids(
            _struct_schedule_words(),
            catalog_fn=_accept_catalog,
        )
        mapping = schedule_mark_map(grids)
        self.assertEqual(mapping["C1"], "HSS6X6X1/2")
        self.assertEqual(mapping["L1"], "W8X21")
        self.assertNotIn("L5", mapping)
        rows = {row["mark"]: row for grid in grids for row in grid["rows"]}
        self.assertEqual(rows["C1"]["plate_role"], "base_plate")
        self.assertIn("14", rows["C1"]["plate_text"])
        self.assertEqual(rows["L1"]["member_plate_roles"], ["bottom_plate"])
        self.assertEqual(rows["L1"]["plate_role"], "bearing_plate")
        self.assertFalse(rows["L5"]["catalog_valid"])
        assembly = schedule_assembly_sidecar(
            "L1",
            {"schedule_grid": grids},
        )
        self.assertEqual(assembly["primary_section"], "W8X21")
        self.assertEqual(assembly["plate_count_per_member"], 2)
        self.assertIn("6", assembly["plate_text"] or "")
        self.assertFalse(
            lookup_schedule_row("L5", {"schedule_grid": grids})["catalog_valid"]
        )

    def test_bearing_plate_and_icf_marks_parse_without_steel_map(self) -> None:
        words = [
            _word("BEARING", 100, 100),
            _word("PLATE", 160, 100),
            _word("SCHEDULE", 220, 100),
            _word("MARK", 100, 116),
            _word("SIZE", 200, 116),
            _word("BP1", 100, 134),
            _word('4"x6"x3/4"', 200, 134),
            _word("ICF", 100, 300),
            _word("LINTEL", 140, 300),
            _word("SCHEDULE", 200, 300),
            _word("MARK", 100, 316),
            _word("SIZE", 200, 316),
            _word("CL2", 100, 334),
            _word('5"x5"x3/8"', 200, 334),
        ]
        grids = build_schedule_grids(words, catalog_fn=_accept_catalog)
        kinds = {grid["kind"] for grid in grids}
        self.assertIn("bearing_plate", kinds)
        self.assertIn("icf_lintel", kinds)
        marks = {row["mark"] for grid in grids for row in grid["rows"]}
        self.assertIn("BP1", marks)
        self.assertIn("CL2", marks)
        # Auxiliary marks must not invent steel sections into the mark map.
        self.assertEqual(schedule_mark_map(grids), {})

    def test_polluted_auxiliary_size_cleans_to_plate_or_angle(self) -> None:
        from services.engineering.schedule_grid import resolve_auxiliary_schedule_mark

        document = {
            "schedule_grid": [
                {
                    "kind": "bearing_plate",
                    "page": 2,
                    "rows": [
                        {
                            "mark": "BP5",
                            "size_text": 'SI - DENOTES SPECIAL INSPECTOR 6"x10"x1"',
                            "plate_text": 'SI - DENOTES SPECIAL INSPECTOR 6"x10"x1"',
                            "plate_role": "bearing_plate",
                        }
                    ],
                },
                {
                    "kind": "icf_lintel",
                    "page": 2,
                    "rows": [
                        {
                            "mark": "CL2",
                            "size_text": (
                                'STANDARD WALL WITH 2-#5 AT HEAD '
                                'CONTINUOUS ANGLE 5"x5"x3/8"'
                            ),
                            "plate_text": (
                                'STANDARD WALL WITH 2-#5 AT HEAD '
                                'CONTINUOUS ANGLE 5"x5"x3/8"'
                            ),
                            "plate_role": "plate",
                        }
                    ],
                },
            ]
        }
        bp = resolve_auxiliary_schedule_mark("BP5", document)
        self.assertFalse(bp.get("abstain"))
        self.assertEqual(bp.get("plate_type"), "PLATE")
        self.assertIn("6", bp.get("display") or "")
        self.assertIn("10", bp.get("display") or "")
        cl = resolve_auxiliary_schedule_mark(
            "CL2", document, catalog_fn=_accept_catalog
        )
        self.assertFalse(cl.get("abstain"))
        self.assertTrue(
            str(cl.get("display") or "").upper().startswith("L5"),
            cl,
        )

    def test_cap_plate_note_is_not_a_mark_quantity(self) -> None:
        note = "ALL HSS COLUMNS SHALL RECEIVE A 5/8\" THICK CAP PLATE"
        words = [
            _word(piece, 40 + index * 40, 20)
            for index, piece in enumerate(note.split())
        ]
        self.assertEqual(
            schedule_mark_map(build_schedule_grids(words, catalog_fn=_accept_catalog)),
            {},
        )


class MarkExtractionTests(unittest.TestCase):
    def test_schedule_marks_are_extracted_not_sections(self) -> None:
        for raw, expected in (
            ("C1", "C1"),
            ("L1", "L1"),
            ("L1A", "L1A"),
            ("BP1", "BP1"),
            ("CL2", "CL2"),
            ("CL6A", "CL6A"),
            ("column callout C3 at grid", "C3"),
            ("bearing plate BP3", "BP3"),
        ):
            with self.subTest(raw=raw):
                tokens = extract_engineering_tokens(raw)
                self.assertIn(expected, tokens)

    def test_sections_are_not_truncated_to_marks(self) -> None:
        self.assertEqual(extract_engineering_tokens("L4X4X1/4"), ["L4X4X1/4"])
        self.assertIn("C12X20.7", extract_engineering_tokens("C12X20.7"))
        self.assertNotIn("C12", extract_engineering_tokens("C12X20.7"))
        self.assertNotIn("L4", extract_engineering_tokens("L4X4"))
        self.assertNotIn("CL2", extract_engineering_tokens("C12X20.7"))


class MarkResolutionTests(unittest.TestCase):
    def _predict(self, text: str, document: dict, decoy: str) -> dict:
        context = {
            "token": {
                "text": text,
                "normalized_text": text,
                "raw_text": text,
                "confidence": 0.5,
            },
            "document": document,
            "geometry": {"objects": []},
            "graph": {"nodes": [], "edges": []},
        }
        with patch(
            "services.prediction.orchestrator.predict_exact_sections",
            return_value=[],
        ) as exact, patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion(decoy),
        ), patch(
            "services.prediction.orchestrator.suggest_token_corrections",
            return_value=[],
        ), patch(
            "services.engineering.schedule_grid._catalog_accepts",
            side_effect=_accept_catalog,
        ):
            result = predict_from_context(context)
        return result, exact

    def test_unresolved_mark_does_not_invent_a_section(self) -> None:
        result, exact = self._predict("L1", {}, "L4X4X1/4")
        exact.assert_not_called()
        self.assertEqual(result["section"], "L1")
        self.assertNotEqual(result["section"], "L4X4X1/4")
        self.assertFalse(result.get("takeoff_eligible"))

    def test_precast_schedule_mark_abstains_without_angle_family(self) -> None:
        grids = build_schedule_grids(
            _struct_schedule_words(),
            catalog_fn=_accept_catalog,
        )
        document = {
            "schedule_grid": grids,
            "schedule_mark_map": schedule_mark_map(grids),
        }
        result, exact = self._predict("L5", document, "L4X4X1/4")
        exact.assert_not_called()
        self.assertTrue(result.get("schedule_non_steel_mark"))
        self.assertFalse(result.get("takeoff_eligible"))
        self.assertNotEqual(result.get("family"), "L")
        self.assertIn("PRECAST", " ".join(result.get("ai_reasons") or []).upper()
            or " ".join(
                (result.get("explanation") or {}).get("reasons") or []
            ).upper()
            or str(result.get("schedule_assembly") or {}).upper()
        )

    def test_mapped_mark_uses_printed_size(self) -> None:
        document = {"schedule_mark_map": {"C1": "HSS6X6X1/2"}}
        result, _exact = self._predict("C1", document, "W10X49")
        self.assertEqual(result["section"], "HSS6X6X1/2")
        self.assertNotEqual(result["section"], "W10X49")
        self.assertEqual(result.get("schedule_mark_resolved"), "HSS6X6X1/2")
        self.assertEqual(result.get("section_resolution"), "schedule_mark_map")
        self.assertEqual(
            (result.get("comparison") or {}).get("match_status"),
            "project_rule_resolved",
        )
        self.assertTrue(result.get("takeoff_eligible"))
        self.assertEqual(result.get("corrected_text"), "HSS6X6X1/2")
        self.assertEqual(result.get("raw_text"), "C1")

    def test_mapped_lintel_carries_plate_assembly_sidecar(self) -> None:
        grids = build_schedule_grids(
            _struct_schedule_words(),
            catalog_fn=_accept_catalog,
        )
        document = {
            "schedule_grid": grids,
            "schedule_mark_map": schedule_mark_map(grids),
        }
        result, _exact = self._predict("L1", document, "W10X49")
        self.assertEqual(result["section"], "W8X21")
        assembly = result.get("schedule_assembly") or {}
        self.assertEqual(assembly.get("primary_section"), "W8X21")
        self.assertEqual(assembly.get("member_plate_roles"), ["bottom_plate"])
        self.assertEqual(assembly.get("plate_count_per_member"), 2)
        self.assertIn("6", assembly.get("plate_text") or "")

    def test_bp_mark_resolves_to_plate_in_results_path(self) -> None:
        words = [
            _word("BEARING", 100, 100),
            _word("PLATE", 160, 100),
            _word("SCHEDULE", 220, 100),
            _word("MARK", 100, 116),
            _word("SIZE", 200, 116),
            _word("BP1", 100, 134),
            _word('4"x6"x3/4"', 200, 134),
        ]
        grids = build_schedule_grids(words, catalog_fn=_accept_catalog)
        document = {"schedule_grid": grids, "schedule_mark_map": {}}
        result, exact = self._predict("BP1", document, "W10X49")
        exact.assert_not_called()
        self.assertEqual(result.get("plate_annotation_type"), "PLATE")
        self.assertIn("4", str(result.get("corrected_text") or ""))
        self.assertTrue(result.get("takeoff_eligible"))
        self.assertEqual(result.get("prediction_source"), "Annotation")

    def test_unresolved_noisy_marks_create_no_section_or_quantity(self) -> None:
        from services.exact_section_predictor import catalog_valid_exact_section
        from services.takeoff.quantity_engine import quantity_engine

        document = {"schedule_grid": [], "schedule_mark_map": {}}
        predictions = []
        # Noise seen on real sheets (Burrville / Ketcham / Struct).
        for text in ("C216,", "C 172,", "C90.", "C216", "BP4,", "BP9", "CL7"):
            with self.subTest(text=text):
                result, _exact = self._predict(text, document, "C12X20")
                self.assertIsNone(catalog_valid_exact_section(result.get("section") or ""))
                predictions.append(result)
        report = quantity_engine.count(predictions)
        self.assertEqual(sum(r.physical_quantity for r in report.results), 0)


class PageRelevanceTests(unittest.TestCase):
    def test_bare_marks_are_not_steel_page_hits(self) -> None:
        self.assertIsNone(_ENGINEERING_PAGE_RE.search("L1"))
        self.assertIsNone(_ENGINEERING_PAGE_RE.search("C1"))
        self.assertIsNotNone(_ENGINEERING_PAGE_RE.search("L4X4"))
        self.assertIsNotNone(_ENGINEERING_PAGE_RE.search("W16X26"))
        self.assertIsNotNone(_ENGINEERING_PAGE_RE.search("C12X20"))


class PlateCalloutTests(unittest.TestCase):
    def test_dim_first_bent_plates(self) -> None:
        for raw in (
            '1/4"x2" WIDE BENT PLATE',
            '12"x4"x3/8" CONTINUOUS BENT PLATE',
        ):
            with self.subTest(raw=raw):
                self.assertTrue(is_dim_first_bent_plate(raw))
                tokens = extract_engineering_tokens(raw)
                self.assertTrue(any("BENTPL" in token for token in tokens), tokens)


class ShadowPageGateTests(unittest.TestCase):
    def test_only_context_pages_drop_and_other_is_kept(self) -> None:
        document = {
            "legend_profile": {"context_pages": {"2": "GENERAL_NOTES"}},
            "page_categories": {"4": "other"},
        }
        geometry = {
            "objects": [
                {"page_number": 2, "id": "note"},
                {"page_number": 4, "id": "other"},
                {"page_number": 5, "id": "frame"},
            ]
        }
        tokens = [
            {"page": 2, "text": "NOTE"},
            {"page": 4, "text": "W16X26"},
        ]
        kept_objects = filter_context_page_objects(document, geometry)["objects"]
        kept_tokens = filter_context_page_tokens(document, tokens)
        self.assertEqual([obj["id"] for obj in kept_objects], ["other", "frame"])
        self.assertEqual([token["text"] for token in kept_tokens], ["W16X26"])
        self.assertFalse(settings.shadow_context_page_gate_enabled)


@unittest.skipUnless(_struct_pdf(), "Struct.pdf is not on this machine")
class StructPdfProbeTests(unittest.TestCase):
    def test_page2_mark_map_and_detail_angles(self) -> None:
        import fitz

        path = _struct_pdf()
        assert path is not None
        document = fitz.open(path)
        try:
            words = [
                {
                    "text": item[4],
                    "bbox": [item[0], item[1], item[2], item[3]],
                    "page_number": 2,
                }
                for item in document[1].get_text("words")
            ]
            mapping = schedule_mark_map(
                build_schedule_grids(words, catalog_fn=_accept_catalog)
            )
            self.assertEqual(mapping.get("C1"), "HSS6X6X1/2")
            self.assertEqual(mapping.get("L1"), "W8X21")
            self.assertNotIn("L5", mapping)
            detail_text = "\n".join(
                document[index].get_text("text")
                for index in (6, 7, 8, 9, 10, 11, 12, 13, 16, 19, 20, 21, 22, 23)
                if index < document.page_count
            )
        finally:
            document.close()
        tokens = extract_engineering_tokens(detail_text)
        self.assertTrue(
            any(token.startswith("L") and token.count("X") >= 2 for token in tokens),
            tokens[:20],
        )
