"""Tests for bent-plate shorthand callouts (Burrville-style non-standard annotations)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.annotation.parser import interpret_annotation
from services.annotation.taxonomy import AnnotationType
from services.engineering.document_prior import plate_context_from_prior
from services.token_extractor import extract_engineering_tokens


BURRVILLE_PRIOR = {
    "enabled": True,
    "abbreviations": {"PL": "plate", "BP": "bent_plate"},
    "plate_terms": ["PL", "BP"],
    "confirms_plates": True,
}


class BentPlateParserTests(unittest.TestCase):
    def test_bur_bp001_thickness_first(self) -> None:
        parsed = interpret_annotation(
            raw_text='1/4" BENT PL',
            document_prior=BURRVILLE_PRIOR,
            page_context="LEGEND_CONFIRMS_PLATES",
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)
        self.assertTrue(parsed.structure_confirmed)
        self.assertEqual(parsed.plate_type, "bent_plate")
        self.assertEqual(parsed.thickness, "1/4")

    def test_bur_bp002_thickness_first(self) -> None:
        parsed = interpret_annotation(
            raw_text='3/8" BENT PL',
            document_prior=BURRVILLE_PRIOR,
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)
        self.assertTrue(parsed.structure_confirmed)
        self.assertEqual(parsed.thickness, "3/8")

    def test_bur_bp003_head_first_with_suffix(self) -> None:
        parsed = interpret_annotation(
            raw_text='BENT PL 3/8" AT',
            document_prior=BURRVILLE_PRIOR,
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)
        self.assertTrue(parsed.structure_confirmed)
        self.assertEqual(parsed.thickness, "3/8")

    def test_bur_bp005_extended_callout(self) -> None:
        parsed = interpret_annotation(
            raw_text='1/2" BENT PL W/ 1/2"⌀x 9"',
            document_prior=BURRVILLE_PRIOR,
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)
        self.assertTrue(parsed.structure_confirmed)
        self.assertEqual(parsed.thickness, "1/2")

    def test_bent_pl_compact_normalized_text(self) -> None:
        parsed = interpret_annotation(
            raw_text='1/4" BENT PL',
            normalized_text='1/4"BENTPL',
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)
        self.assertTrue(parsed.structure_confirmed)

    def test_engineering_object_filter_keeps_bent_pl(self) -> None:
        from services.engineering_object_filter import classify_engineering_object

        role = classify_engineering_object(
            {
                "raw_text": '1/4" BENT PL',
                "normalized_text": '1/4"BENTPL',
                "text": '1/4"BENTPL',
                "context": {"line_text": '1/4" BENT PL'},
            }
        )
        self.assertEqual(role, "plate")

    def test_generic_bent_word_does_not_force_bent_plate(self) -> None:
        parsed = interpret_annotation(
            raw_text="6x4x5/16",
            nearby_text=["bent angle seat"],
            page_context="connection detail",
        )
        self.assertNotEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)

    def test_pl_regression_st_flat_plate(self) -> None:
        parsed = interpret_annotation(
            raw_text="PL 1x9x1'-9",
            document_prior=BURRVILLE_PRIOR,
            page_context="LEGEND_CONFIRMS_PLATES",
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertTrue(parsed.structure_confirmed)
        self.assertEqual(parsed.plate_type, "flat_plate")

    def test_w_section_regression_unchanged(self) -> None:
        parsed = interpret_annotation(raw_text="W18X35")
        self.assertEqual(parsed.annotation_type, AnnotationType.STANDARD_SECTION.value)
        self.assertTrue(parsed.structure_confirmed)

    def test_bare_compound_dims_still_dimension(self) -> None:
        parsed = interpret_annotation(raw_text="6x4x5/16")
        self.assertEqual(parsed.annotation_type, AnnotationType.DIMENSION.value)
        self.assertFalse(parsed.structure_confirmed)


class BentPlatePriorTests(unittest.TestCase):
    def test_prior_supports_bent_pl_in_normalized_text(self) -> None:
        hints = plate_context_from_prior(
            BURRVILLE_PRIOR,
            normalized='1/4" BENT PL',
            compact='1/4"BENTPL',
        )
        self.assertTrue(hints["supports_bent_plate"])
        self.assertTrue(hints["supports_plate"])


class BentPlateTokenExtractionTests(unittest.TestCase):
    def test_extracts_all_burrville_callout_shapes(self) -> None:
        cases = [
            '1/4" BENT PL',
            '3/8" BENT PL',
            'BENT PL 3/8" AT',
            '1/2" BENT PL W/ 1/2"⌀x 9"',
        ]
        for text in cases:
            with self.subTest(text=text):
                tokens = extract_engineering_tokens(text)
                self.assertTrue(tokens, msg=f"expected token from {text!r}")


class BentPlateEdgeCaseTests(unittest.TestCase):
    def test_record_edge_case_uses_bent_plates_category(self) -> None:
        from services.annotation.edge_cases import record_edge_case

        with tempfile.TemporaryDirectory() as temp, patch(
            "services.annotation.edge_cases.edge_case_path",
            return_value=Path(temp) / "annotation_edge_cases.jsonl",
        ):
            entry = record_edge_case(
                category="bent_plates",
                raw_text='1/4" BENT PL',
                normalized_text='1/4"BENTPL',
                annotation_type="BENT_PLATE",
                parsed_structure={
                    "annotation_type": "BENT_PLATE",
                    "plate_type": "bent_plate",
                },
                reviewer_decision="approve",
                reason="test:approve",
                document_id="doc_test",
                object_id="test_bent_plate_edge",
            )
        self.assertEqual(entry["category"], "bent_plates")
        self.assertTrue(entry["training_eligible"])

    def test_engineering_router_maps_bent_plate_category(self) -> None:
        from routers.engineering import _edge_case_category

        category = _edge_case_category(
            user_decision="approve",
            annotation={"annotation_type": "BENT_PLATE"},
            raw_text='3/8" BENT PL',
        )
        self.assertEqual(category, "bent_plates")


if __name__ == "__main__":
    unittest.main()
