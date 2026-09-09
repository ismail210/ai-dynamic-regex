"""Family-aware projection tests for dimensions, plates, and steel members."""

from __future__ import annotations

import unittest

from services.engineering.context_scope import (
    OBJECT_SCOPE_NON_MEMBER_DIMENSION,
    partition_takeoff,
)
from services.multimodal.fusion_engine import fusion_engine
from services.takeoff.takeoff_exporter import build_takeoff_rows


def _predict(text: str, object_type: str) -> dict:
    return fusion_engine.predict(
        {
            "token": {
                "text": text,
                "raw_text": text,
                "normalized_text": text,
                "engineering_object_type": object_type,
                "page": 1,
                "bbox": [0, 0, 10, 10],
            },
            "document": {},
            "geometry": {},
            "graph": {},
            "source_file": "projection-test.pdf",
        }
    ).to_dict()


class SemanticTakeoffProjectionTests(unittest.TestCase):
    def test_anonymous_dimension_is_non_member_after_abstention(self) -> None:
        prediction = _predict('1/2"', "anonymous_dimension")

        self.assertEqual(prediction["annotation_type"], "DIMENSION")
        self.assertEqual(
            prediction["object_scope"], OBJECT_SCOPE_NON_MEMBER_DIMENSION
        )
        self.assertFalse(prediction["takeoff_eligible"])
        self.assertFalse(prediction["section_applicable"])
        self.assertEqual(prediction["section"], "")
        takeoff, excluded = partition_takeoff([prediction])
        self.assertEqual(takeoff, [])
        self.assertEqual(excluded, [prediction])
        self.assertEqual(build_takeoff_rows([prediction]), [])

    def test_confirmed_plate_keeps_existing_plate_semantics(self) -> None:
        prediction = _predict('PL 3 3/8"', "plate")

        self.assertEqual(prediction["annotation_type"], "PLATE")
        self.assertEqual(prediction["plate_annotation_type"], "PLATE")
        self.assertFalse(prediction["section_applicable"])
        self.assertTrue(prediction["takeoff_eligible"])
        self.assertEqual(partition_takeoff([prediction])[0], [prediction])

    def test_confirmed_bent_plate_is_not_generic_dimension(self) -> None:
        prediction = _predict('1/2" BENT PL', "plate")

        self.assertEqual(prediction["annotation_type"], "BENT_PLATE")
        self.assertEqual(prediction["plate_annotation_type"], "BENT_PLATE")
        self.assertFalse(prediction["section_applicable"])
        self.assertTrue(prediction["takeoff_eligible"])

    def test_valid_hss_remains_structural_member(self) -> None:
        prediction = _predict("HSS10X8X3/8", "steel_section")

        self.assertEqual(prediction["section"], "HSS10X8X3/8")
        self.assertEqual(prediction["family"], "HSS")
        self.assertTrue(prediction["section_applicable"])
        self.assertTrue(prediction["takeoff_eligible"])

    def test_valid_angle_remains_structural_member(self) -> None:
        prediction = _predict("L4X4X3/8", "steel_section")

        self.assertEqual(prediction["section"], "L4X4X3/8")
        self.assertEqual(prediction["family"], "L")
        self.assertTrue(prediction["section_applicable"])
        self.assertTrue(prediction["takeoff_eligible"])

    def test_valid_channel_and_wt_remain_structural_members(self) -> None:
        channel = _predict("C8X11.5", "steel_section")
        tee = _predict("WT7X19", "steel_section")
        self.assertEqual(channel["family"], "C")
        self.assertTrue(channel["takeoff_eligible"])
        self.assertEqual(tee["family"], "WT")
        self.assertTrue(tee["takeoff_eligible"])

    def test_unsupported_bolt_grade_remap_is_not_takeoff_eligible(self) -> None:
        prediction = _predict("A325", "steel_section")

        self.assertEqual(prediction["section"], "W14X132")
        self.assertEqual(
            (prediction.get("comparison") or {}).get("match_status"),
            "corrected_prediction",
        )
        self.assertFalse(prediction["takeoff_eligible"])
        self.assertEqual(partition_takeoff([prediction])[0], [])
        self.assertEqual(build_takeoff_rows([prediction]), [])

    def test_unsupported_zero_confidence_angle_remap_is_not_takeoff_eligible(
        self,
    ) -> None:
        from services.prediction.canonical_contract import (
            member_prediction_takeoff_eligible,
        )

        for section, token in (
            ("L4X3X5/16", "L4X3-1/2X5/16"),
            ("L6X4X3/8", "L6x3-1/2x3/8"),
        ):
            with self.subTest(token=token):
                self.assertFalse(
                    member_prediction_takeoff_eligible(
                        unresolved_anonymous_dimension=False,
                        confirmed_plate_type=None,
                        section=section,
                        match_status="corrected_prediction",
                        retrieval_gate_failed=True,
                    )
                )
                prediction = {
                    "section": section,
                    "family": "L",
                    "prediction_source": "Fusion",
                    "takeoff_eligible": False,
                    "original_token": token,
                    "confidence": 0.0,
                    "comparison": {"match_status": "corrected_prediction"},
                    "database_match": True,
                }
                self.assertEqual(partition_takeoff([prediction])[0], [])
                self.assertEqual(build_takeoff_rows([prediction]), [])

    def test_round_hss_catalog_form_is_normalized_match_and_takeoff_eligible(
        self,
    ) -> None:
        for raw, canonical in (
            ("HSS10X0.500", "HSS10.000X0.500"),
            ("HSS10X0.625", "HSS10.000X0.625"),
        ):
            with self.subTest(raw=raw):
                prediction = _predict(raw, "steel_section")
                self.assertEqual(prediction["section"], canonical)
                self.assertEqual(
                    (prediction.get("comparison") or {}).get("match_status"),
                    "normalized_match",
                )
                self.assertTrue(prediction["takeoff_eligible"])
                self.assertEqual(partition_takeoff([prediction])[0], [prediction])

    def test_valid_schedule_members_remain_eligible(self) -> None:
        for text, family in (
            ("W10X33", "W"),
            ("HSS6X6X3/8", "HSS"),
            ("W12X16", "W"),
        ):
            with self.subTest(text=text):
                prediction = _predict(text, "steel_section")
                self.assertEqual(prediction["section"], text)
                self.assertEqual(prediction["family"], family)
                self.assertTrue(prediction["takeoff_eligible"])
                self.assertIn(
                    (prediction.get("comparison") or {}).get("match_status"),
                    {"exact_match", "normalized_match"},
                )

    def test_takeoff_exporter_prefers_catalog_family_over_earlier_mismatch(
        self,
    ) -> None:
        rows = build_takeoff_rows(
            [
                {
                    "section": "W10X54",
                    "family": "HSS",
                    "prediction_source": "Fusion",
                    "takeoff_eligible": True,
                    "original_token": "HSS10X0.625",
                    "confidence": 0.145,
                    "comparison": {"match_status": "corrected_prediction"},
                    "database_match": True,
                },
                {
                    "section": "W10X54",
                    "family": "W",
                    "prediction_source": "Fusion",
                    "takeoff_eligible": True,
                    "original_token": "W10X54",
                    "confidence": 0.87,
                    "comparison": {"match_status": "exact_match"},
                    "database_match": True,
                },
                {
                    "section": "W8X40",
                    "family": "HSS",
                    "prediction_source": "Fusion",
                    "takeoff_eligible": True,
                    "original_token": "HSS10X0.625",
                    "confidence": 0.145,
                    "comparison": {"match_status": "corrected_prediction"},
                    "database_match": True,
                },
                {
                    "section": "W8X40",
                    "family": "W",
                    "prediction_source": "Fusion",
                    "takeoff_eligible": True,
                    "original_token": "W8X40",
                    "confidence": 0.87,
                    "comparison": {"match_status": "exact_match"},
                    "database_match": True,
                },
            ]
        )
        by_section = {row["Section"]: row for row in rows}
        self.assertEqual(by_section["W10X54"]["Family"], "W")
        self.assertEqual(by_section["W10X54"]["AISC Type"], "W")
        self.assertEqual(by_section["W10X54"]["Quantity"], 2)
        self.assertEqual(by_section["W8X40"]["Family"], "W")
        self.assertEqual(by_section["W8X40"]["AISC Type"], "W")
        self.assertEqual(by_section["W8X40"]["Quantity"], 2)

    def test_takeoff_exporter_never_uses_raw_token_as_section(self) -> None:
        self.assertEqual(
            build_takeoff_rows(
                [
                    {
                        "token": '1/2"',
                        "section": "",
                        "takeoff_eligible": False,
                    }
                ]
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
