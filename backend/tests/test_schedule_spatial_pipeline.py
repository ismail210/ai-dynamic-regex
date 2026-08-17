"""Tests for schedule ingestion, spatial association, and detail regions."""

from __future__ import annotations

import tempfile
import unittest

import pandas as pd

from services.engineering.detail_regions import assign_detail_regions, same_region
from services.multimodal.schedule_ingestion import (
    build_schedule_tokens,
    parse_schedule_entries,
)
from services.multimodal.spatial_association import build_spatial_association_tokens
from services.takeoff.ground_truth_excel import parse_ground_truth_excel


class GroundTruthExcelSanityTests(unittest.TestCase):
    def test_grandtotal_rows_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/gt.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame = pd.DataFrame(
                    [
                        [None] * 6,
                        [None, "Type", "Mark", "Length", "Weight", "Count"],
                        [None, "L4X4X1/4", "B1", 120, 40, 12],
                        [None, "GRANDTOTAL:108", None, None, None, 1],
                        [None, "GRANDTOTAL:213", None, None, None, 1],
                    ]
                )
                frame.to_excel(
                    writer, sheet_name="StructuralFramingSchedule", index=False, header=False
                )
            result = parse_ground_truth_excel(path)
            labels = {item["canonical_label"] for item in result["aggregates"]}
            self.assertIn("L4X4X1/4", labels)
            self.assertNotIn("GRANDTOTAL:108", labels)
            self.assertNotIn("GRANDTOTAL:213", labels)
            by_label = {
                item["canonical_label"]: item["quantity"] for item in result["aggregates"]
            }
            self.assertEqual(by_label["L4X4X1/4"], 12)

    def test_implausible_count_treated_as_length_not_quantity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/summary.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame = pd.DataFrame(
                    [
                        [None] * 4,
                        [None, "Type", "Length", "Count"],
                        [None, "L4X4X1/4", None, 1092],
                    ]
                )
                frame.to_excel(
                    writer, sheet_name="Steel Elements Summary", index=False, header=False
                )
            result = parse_ground_truth_excel(path)
            item = next(
                row for row in result["items"] if row["canonical_label"] == "L4X4X1/4"
            )
            self.assertEqual(item["quantity"], 1)
            self.assertEqual(item["length"], "1092")

    def test_detailed_schedule_wins_over_summary_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/both.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                detailed = pd.DataFrame(
                    [
                        [None] * 4,
                        [None, "Type", "Count"],
                        [None, "L4X4X1/4", 8],
                    ]
                )
                summary = pd.DataFrame(
                    [
                        [None] * 4,
                        [None, "Type", "Count"],
                        [None, "L4X4X1/4", 999],
                    ]
                )
                detailed.to_excel(
                    writer, sheet_name="StructuralFramingSchedule", index=False, header=False
                )
                summary.to_excel(
                    writer, sheet_name="Steel Elements Summary", index=False, header=False
                )
            result = parse_ground_truth_excel(path)
            by_label = {
                item["canonical_label"]: item["quantity"] for item in result["aggregates"]
            }
            self.assertEqual(by_label["L4X4X1/4"], 8)


class ScheduleIngestionTests(unittest.TestCase):
    def test_schedule_only_shape_becomes_token(self) -> None:
        document = {
            "engineering_tokens": [
                {"token_id": "t1", "text": "W18X35", "page": 1, "bbox": [10, 10, 50, 20]},
            ],
            "schedules": [
                {
                    "schedule_id": "sched_1",
                    "page_number": 2,
                    "bbox": [100, 100, 400, 300],
                    "text": "BEAM SCHEDULE\nL4X4X1/4 12\nW18X35 2",
                    "confidence": 0.8,
                }
            ],
            "pages": [{"page_number": 2, "width": 800, "height": 600}],
        }
        tokens = build_schedule_tokens(document)
        shapes = {token["text"] for token in tokens}
        self.assertIn("L4X4X1/4", shapes)
        self.assertNotIn("W18X35", shapes)
        l_tokens = [token for token in tokens if token["text"] == "L4X4X1/4"]
        self.assertEqual(len(l_tokens), 12)
        self.assertTrue(all(token.get("schedule_sourced") for token in l_tokens))

    def test_parse_schedule_entries_extracts_quantity(self) -> None:
        document = {
            "schedules": [
                {
                    "schedule_id": "s1",
                    "page_number": 1,
                    "bbox": [0, 0, 100, 100],
                    "text": "FRAMING SCHEDULE\nHSS6X6X1/2 QTY 3",
                }
            ]
        }
        entries = parse_schedule_entries(document)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["shape"], "HSS6X6X1/2")
        self.assertEqual(entries[0]["quantity"], 3)


class DetailRegionTests(unittest.TestCase):
    def test_assigns_region_ids(self) -> None:
        document = {
            "engineering_tokens": [
                {"token_id": "a", "page": 1, "bbox": [10, 10, 30, 20]},
                {"token_id": "b", "page": 1, "bbox": [500, 10, 520, 20]},
            ],
            "pages": [{"page_number": 1, "width": 900, "height": 700}],
        }
        regions = assign_detail_regions(document, geometry={"objects": []})
        self.assertIn(1, regions)
        self.assertEqual(len(regions[1]), 2)
        region_ids = {token["region_id"] for token in document["engineering_tokens"]}
        self.assertEqual(len(region_ids), 2)

    def test_same_region_helper(self) -> None:
        self.assertTrue(same_region("p1_r0", "p1_r0"))
        self.assertFalse(same_region("p1_r0", "p1_r1"))
        self.assertTrue(same_region(None, "p1_r0"))


class SpatialAssociationTests(unittest.TestCase):
    def test_links_unlabeled_geometry_to_nearby_label(self) -> None:
        document = {
            "engineering_tokens": [
                {
                    "token_id": "lbl1",
                    "text": "L4X4X1/4",
                    "page": 1,
                    "bbox": [100, 100, 160, 112],
                    "engineering_object_type": "label",
                }
            ],
            "pages": [{"page_number": 1, "width": 1000, "height": 800}],
            "detail_regions": {
                1: [
                    {
                        "region_id": "p1_r0",
                        "page_number": 1,
                        "bbox": [0, 0, 1000, 800],
                        "item_count": 2,
                    }
                ]
            },
        }
        geometry = {
            "objects": [
                {
                    "geometry_id": "geom_line_1",
                    "page_number": 1,
                    "bbox": [180, 100, 182, 200],
                    "geometry_kind": "line",
                    "geometry_role": "member",
                }
            ]
        }
        for token in document["engineering_tokens"]:
            token["region_id"] = "p1_r0"
        geometry["objects"][0]["region_id"] = "p1_r0"

        tokens = build_spatial_association_tokens(document, geometry)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["inferred_section"], "L4X4X1/4")
        self.assertEqual(tokens[0]["geometry_id"], "geom_line_1")
        self.assertTrue(tokens[0]["geometry_associated"])


if __name__ == "__main__":
    unittest.main()
