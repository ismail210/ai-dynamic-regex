"""Review-only repeated-detail condition linker."""

from __future__ import annotations

import unittest

from services.engineering.context_scope import partition_takeoff
from services.engineering.repeated_detail_linker import (
    OBJECT_KIND_REPEATED_DETAIL,
    link_repeated_detail_members,
)
from services.takeoff.ground_truth_evaluation import evaluate_against_excel
from services.takeoff.quantity_engine import quantity_engine
from services.takeoff.takeoff_exporter import build_takeoff_rows


def _block(page: int, text: str, bbox=None) -> dict:
    return {
        "page_number": page,
        "text": text,
        "bbox": bbox or [100, 100, 200, 120],
    }


def _flange_brace_document(*, extra_blocks=None, **document_fields) -> dict:
    blocks = [
        _block(
            18,
            "L4X4X1/4 TYP",
            [2200, 270, 2300, 295],
        ),
        _block(
            18,
            "TYPICAL BEAM BOTTOM FLANGE BRACE DETAIL",
            [2100, 680, 2400, 710],
        ),
        _block(
            10,
            "BOT FLANGE BRACE, SEE TYP DET, TYP",
            [1000, 750, 1400, 780],
        ),
    ]
    if extra_blocks:
        blocks.extend(extra_blocks)
    payload = {"blocks": blocks}
    payload.update(document_fields)
    return payload


def _springhill_document(*, extra_blocks=None) -> dict:
    blocks = [
        _block(16, "L4X4X1/4 TYP", [1560, 220, 1640, 245]),
        _block(
            16,
            "TYPICAL BEAM FLANGE BRACE DETAIL",
            [1500, 620, 1750, 655],
        ),
        _block(
            9,
            "BOT FLANGE BRACE SEE TYP DET, TYP",
            [800, 1760, 1200, 1790],
        ),
    ]
    if extra_blocks:
        blocks.extend(extra_blocks)
    return {"blocks": blocks}


class RepeatedDetailLinkerTests(unittest.TestCase):
    def test_burrville_bottom_flange_brace_links(self) -> None:
        members = link_repeated_detail_members(_flange_brace_document())
        self.assertEqual(len(members), 1)
        member = members[0]
        self.assertEqual(member["object_kind"], OBJECT_KIND_REPEATED_DETAIL)
        self.assertEqual(member["inherited_section"], "L4X4X1/4")
        self.assertEqual(
            member["source_typical_title"],
            "TYPICAL BEAM BOTTOM FLANGE BRACE DETAIL",
        )
        self.assertEqual(
            member["target_condition_text"],
            "BOT FLANGE BRACE, SEE TYP DET, TYP",
        )
        self.assertTrue(member["requires_review"])
        self.assertFalse(member["takeoff_eligible"])
        self.assertEqual(
            [step["type"] for step in member["evidence_chain"]],
            ["thickness_bearing_seed", "typical_title", "plan_condition"],
        )
        self.assertNotIn("physical_quantity", member)
        self.assertNotIn("geometry_id", member)
        self.assertNotIn("length", member)

    def test_springhill_flange_brace_title_variant_links(self) -> None:
        members = link_repeated_detail_members(_springhill_document())
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["inherited_section"], "L4X4X1/4")
        self.assertEqual(
            members[0]["source_typical_title"],
            "TYPICAL BEAM FLANGE BRACE DETAIL",
        )

    def test_bot_flg_abbreviation_links(self) -> None:
        members = link_repeated_detail_members(
            _flange_brace_document(
                extra_blocks=[
                    _block(11, "BOT FLG BRACE SEE TYP DET, TYP"),
                ]
            )
        )
        notes = {item["target_condition_text"] for item in members}
        self.assertIn("BOT FLANGE BRACE, SEE TYP DET, TYP", notes)
        self.assertIn("BOT FLG BRACE SEE TYP DET, TYP", notes)

    def test_duplicate_typical_stamps_do_not_duplicate_notes(self) -> None:
        members = link_repeated_detail_members(
            _flange_brace_document(
                extra_blocks=[
                    _block(18, "BM SEE PLAN TYP L4X4X1/4 TYP", [2170, 560, 2480, 585]),
                ]
            )
        )
        self.assertEqual(len(members), 1)

    def test_review_and_takeoff_gates(self) -> None:
        members = link_repeated_detail_members(_flange_brace_document())
        takeoff, excluded = partition_takeoff(members)
        self.assertEqual(takeoff, [])
        self.assertEqual(excluded, members)
        report = quantity_engine.count(members)
        self.assertEqual(report.results, [])
        self.assertEqual(build_takeoff_rows(members), [])

    def test_quantity_engine_ignores_leaked_true_eligibility(self) -> None:
        members = link_repeated_detail_members(_flange_brace_document())
        leaked = dict(members[0])
        leaked["takeoff_eligible"] = True
        fusion = {
            "section": "W12X16",
            "prediction_source": "Fusion",
            "takeoff_eligible": True,
            "object_id": "w1",
            "page": 1,
            "confidence": 0.9,
        }
        report = quantity_engine.count([fusion, leaked])
        by_section = {item.section: item for item in report.results}
        self.assertEqual(by_section["W12X16"].physical_quantity, 1)
        leaked_result = by_section.get("L4X4X1/4")
        if leaked_result is not None:
            self.assertEqual(leaked_result.physical_quantity, 0)

    def test_validation_does_not_count_as_eligible_member(self) -> None:
        members = link_repeated_detail_members(_flange_brace_document())
        report = evaluate_against_excel(
            members,
            ground_truth={
                "items": [
                    {
                        "canonical_label": "L4X4X1/4",
                        "quantity": 9,
                        "metric_scope": "structural_member",
                    }
                ]
            },
        )
        self.assertEqual(report["predicted_aggregates"], [])
        missing = [
            row
            for row in report["missing_elements"]
            if row["section"] == "L4X4X1/4"
        ]
        self.assertEqual(missing[0]["expected_quantity"], 9)
        self.assertEqual(missing[0]["predicted_quantity"], 0)

    def test_relieving_angle_is_rejected(self) -> None:
        members = link_repeated_detail_members(
            _flange_brace_document(
                extra_blocks=[_block(7, "RELIEVING ANGLE, TYP")]
            )
        )
        notes = {item["target_condition_text"] for item in members}
        self.assertNotIn("RELIEVING ANGLE, TYP", notes)

    def test_hang_lintel_is_rejected(self) -> None:
        members = link_repeated_detail_members(
            _flange_brace_document(
                extra_blocks=[
                    _block(10, "HANG LINTEL ASSEMBLY, SEE TYP DET, TYP"),
                ]
            )
        )
        notes = {item["target_condition_text"] for item in members}
        self.assertNotIn("HANG LINTEL ASSEMBLY, SEE TYP DET, TYP", notes)

    def test_cross_brace_is_rejected(self) -> None:
        members = link_repeated_detail_members(
            _flange_brace_document(
                extra_blocks=[_block(9, "CROSS BRACE SEE TYP DET")]
            )
        )
        notes = {item["target_condition_text"] for item in members}
        self.assertNotIn("CROSS BRACE SEE TYP DET", notes)

    def test_l4x4x38_bracing_is_not_a_seed_or_note(self) -> None:
        members = link_repeated_detail_members(
            {
                "blocks": [
                    _block(13, "L4X4X3/8 BRACING, TYP"),
                    _block(13, "TYPICAL BEAM BOTTOM FLANGE BRACE DETAIL"),
                    _block(10, "BOT FLANGE BRACE, SEE TYP DET, TYP"),
                ]
            }
        )
        # 3/8 bracing on the typical page is a competing seed and must not
        # inherit onto the flange-brace note as L4X4X3/8. The note may still
        # link if a 1/4 seed is present; here it is not.
        self.assertEqual(members, [])

    def test_bare_l_and_incomplete_l4x4_do_not_complete(self) -> None:
        members = link_repeated_detail_members(
            {
                "blocks": [
                    _block(16, "TYPICAL BEAM FLANGE BRACE DETAIL"),
                    _block(9, "L STANDS FOR L4X3X5/16 LLH DSA, SEE TYPICAL DETAIL."),
                    _block(9, "L4x4"),
                    _block(9, "BOT FLANGE BRACE SEE TYP DET, TYP"),
                ]
            }
        )
        self.assertEqual(members, [])

    def test_arbitrary_see_typ_det_is_rejected(self) -> None:
        members = link_repeated_detail_members(
            _flange_brace_document(
                extra_blocks=[_block(10, "SEE TYP DET FOR DECK SUPT ON CMU")]
            )
        )
        notes = {item["target_condition_text"] for item in members}
        self.assertNotIn("SEE TYP DET FOR DECK SUPT ON CMU", notes)

    def test_arbitrary_brace_is_rejected(self) -> None:
        members = link_repeated_detail_members(
            _flange_brace_document(extra_blocks=[_block(10, "BRACE")])
        )
        notes = {item["target_condition_text"] for item in members}
        self.assertNotIn("BRACE", notes)

    def test_s311_reference_is_not_blanket_inheritance(self) -> None:
        members = link_repeated_detail_members(
            _flange_brace_document(
                extra_blocks=[
                    _block(18, "L4X4X1/4 CONT"),
                    _block(7, "E S-311"),
                    _block(7, "N S-311 TYP, 3 SIDES"),
                    _block(8, "K S-311 TYP @ RELIEVING ANGLE"),
                ]
            )
        )
        notes = {item["target_condition_text"] for item in members}
        self.assertNotIn("E S-311", notes)
        self.assertNotIn("N S-311 TYP, 3 SIDES", notes)
        self.assertNotIn("K S-311 TYP @ RELIEVING ANGLE", notes)

    def test_document_prior_alone_produces_nothing(self) -> None:
        members = link_repeated_detail_members(
            {
                "document_prior": {"typical_sections": ["L4X4X1/4"]},
                "blocks": [],
            }
        )
        self.assertEqual(members, [])

    def test_cmu_wall_seed_does_not_label_flange_brace_notes(self) -> None:
        members = link_repeated_detail_members(
            {
                "blocks": [
                    _block(20, "L4X4X1/4 TYP"),
                    _block(
                        20,
                        "TYPICAL CMU WALL TOP CONNECTION UNDER SOMD DETAIL",
                    ),
                    _block(10, "BOT FLANGE BRACE, SEE TYP DET, TYP"),
                ]
            }
        )
        self.assertEqual(members, [])

    def test_excel_fields_on_document_are_ignored(self) -> None:
        members = link_repeated_detail_members(
            {
                "excel_quantity": 42,
                "expected_excel": {"L4X4X1/4": 9},
                "blocks": [],
            }
        )
        self.assertEqual(members, [])

    def test_geometry_objects_do_not_create_members(self) -> None:
        members = link_repeated_detail_members(
            {
                "blocks": [
                    _block(18, "TYPICAL BEAM BOTTOM FLANGE BRACE DETAIL"),
                ],
                "geometry_objects": [
                    {"kind": "line", "page_number": 10, "bbox": [0, 0, 100, 1]},
                    {"kind": "polyline", "page_number": 10},
                ],
            }
        )
        self.assertEqual(members, [])


if __name__ == "__main__":
    unittest.main()
