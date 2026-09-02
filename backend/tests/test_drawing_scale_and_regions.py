"""Scale detection, real-unit association radius, and same-detail graph links."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.detail_regions import assign_detail_regions
from services.engineering.drawing_scale import (
    association_radius_from_geometry,
    association_radius_pdf_points,
    detect_drawing_scale,
    detect_page_scales,
    page_association_radius,
    page_is_nts,
    parse_scale_text,
    resolve_page_scale,
)
from services.engineering.geometry_extractor import extract_geometry
from services.engineering.graph_builder import build_graph
from services.engineering.spatial_index import build_page_index, nearest_geometry_candidates


class DrawingScaleParseTests(unittest.TestCase):
    def test_quarter_inch_equals_one_foot(self) -> None:
        parsed = parse_scale_text('SCALE: 1/4"=1\'-0"')
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed.paper_inches, 0.25)
        self.assertAlmostEqual(parsed.real_inches, 12.0)
        self.assertAlmostEqual(parsed.pdf_points_per_real_inch, 1.5)

    def test_metric_scale(self) -> None:
        parsed = parse_scale_text("SCALE 1:50")
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed.pdf_points_per_real_inch, 72.0 / 50.0)

    def test_bare_dimension_is_not_a_scale(self) -> None:
        self.assertIsNone(parse_scale_text('1/4"'))

    def test_title_block_preferred(self) -> None:
        document = {
            "title_blocks": [
                {"text": 'PROJECT X  SCALE: 1/8"=1\'-0"  DATE'},
            ],
            "lines": [{"text": "W18X35"}],
        }
        scale = detect_drawing_scale(document)
        self.assertIsNotNone(scale)
        self.assertEqual(scale.source, "title_block")
        self.assertIn("1/8", scale.raw)

    def test_sixty_fourth_scale(self) -> None:
        parsed = parse_scale_text('3/64"=1\'-0"')
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed.paper_inches, 3.0 / 64.0)

    def test_scale_label_and_ratio_on_separate_lines(self) -> None:
        document = {
            "lines": [
                {"text": "SCALE", "page_number": 5},
                {"text": '3/64"=1\'-0"', "page_number": 5},
                {"text": "W16X26", "page_number": 5},
            ]
        }
        by_page = detect_page_scales(document)
        self.assertIn(5, by_page)
        self.assertIn("3/64", by_page[5].raw)

    def test_later_page_scale_does_not_require_page_one(self) -> None:
        document = {
            "lines": [
                {"text": "COVER SHEET", "page_number": 1},
                {"text": 'SCALE: 1/8"=1\'-0"', "page_number": 3},
            ]
        }
        self.assertIsNone(detect_page_scales(document).get(1))
        page3 = detect_page_scales(document)[3]
        self.assertIn("1/8", page3.raw)
        overall = detect_drawing_scale(document)
        self.assertIsNotNone(overall)
        self.assertIn("1/8", overall.raw)

    def test_not_to_scale_is_ignored(self) -> None:
        self.assertIsNone(parse_scale_text("NOT TO SCALE"))
        self.assertIsNone(parse_scale_text("NO SCALE"))
        self.assertEqual(association_radius_pdf_points(None), 160.0)
        self.assertEqual(association_radius_from_geometry({}), 160.0)

    def test_nts_page_does_not_inherit_another_pages_scale(self) -> None:
        document = {
            "lines": [
                {"text": "COVER SHEET NTS", "page_number": 1},
                {"text": 'SCALE: 1"=1\'-0"', "page_number": 3},
            ]
        }
        self.assertTrue(page_is_nts(document, 1))
        resolved = resolve_page_scale(document, 1)
        self.assertTrue(resolved["is_nts"])
        self.assertIsNone(resolved["scale_value"])
        self.assertEqual(resolved["scale_reason"], "nts")
        self.assertFalse(resolved["scale_fallback"])
        page3 = resolve_page_scale(document, 3)
        self.assertIn("1\"", page3["scale_value"] or page3.get("raw") or "")

    def test_nts_page_keeps_local_title_block_scale(self) -> None:
        document = {
            "title_blocks": [
                {"text": 'NOTES  NOT TO SCALE  SCALE: 1/8"=1\'-0"', "page_number": 3},
            ]
        }
        resolved = resolve_page_scale(document, 3)
        self.assertTrue(resolved["is_nts"])
        self.assertEqual(resolved["scale_reason"], "page_scale")
        self.assertIn("1/8", resolved["raw"])

    def test_page_without_scale_does_not_inherit_document_scale(self) -> None:
        document = {
            "lines": [
                {"text": "COVER", "page_number": 1},
                {"text": 'SCALE: 1/8"=1\'-0"', "page_number": 3},
            ]
        }
        resolved = resolve_page_scale(document, 1)
        self.assertFalse(resolved["is_nts"])
        self.assertIsNone(resolved["scale_value"])
        self.assertEqual(resolved["scale_reason"], "unknown")
        self.assertIsNotNone(detect_drawing_scale(document))

    def test_page_association_radius_does_not_use_document_scale(self) -> None:
        geometry = {
            "association_radius_pdf_points": 48.0,
            "page_summaries": [
                {"page_number": 1, "association_radius_pdf_points": 160.0},
            ],
        }
        self.assertEqual(page_association_radius(geometry, 1), 160.0)
        self.assertEqual(page_association_radius(geometry, 9), 160.0)

    def test_known_scale_changes_radius(self) -> None:
        eighth = parse_scale_text('1/8"=1\'-0"')
        quarter = parse_scale_text('1/4"=1\'-0"')
        r8 = association_radius_pdf_points(eighth)
        r4 = association_radius_pdf_points(quarter)
        self.assertLess(r8, r4)
        self.assertGreaterEqual(r8, 48.0)
        self.assertLessEqual(r4, 280.0)

    def test_extract_geometry_records_title_block_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "scaled.pdf"
            doc = fitz.open()
            page = doc.new_page(width=600, height=400)
            page.draw_line(fitz.Point(40, 40), fitz.Point(200, 40), color=(0, 0, 0))
            doc.save(pdf)
            doc.close()
            geometry = extract_geometry(
                str(pdf),
                document_structure={
                    "title_blocks": [
                        {"text": 'SCALE: 1/4"=1\'-0"', "page_number": 1},
                    ],
                    "engineering_tokens": [
                        {"page": 1, "text": "W12X26", "bbox": [40, 20, 80, 30]},
                    ],
                    "lines": [],
                },
            )
        self.assertEqual(geometry["scale_value"], 'SCALE: 1/4"=1\'-0"')
        self.assertEqual(geometry["scale_source"], "title_block")
        self.assertAlmostEqual(geometry["association_radius_pdf_points"], 144.0)
        obj = geometry["objects"][0]
        self.assertIsNotNone(obj.get("length_real_inches"))


class SameRegionAssociationTests(unittest.TestCase):
    def test_label_does_not_associate_across_details(self) -> None:
        document = {
            "engineering_tokens": [
                {
                    "token_id": "left",
                    "text": "W16X26",
                    "page": 1,
                    "bbox": [40, 40, 90, 52],
                },
                {
                    "token_id": "right",
                    "text": "W16X26",
                    "page": 1,
                    "bbox": [640, 40, 690, 52],
                },
            ],
            "pages": [{"page_number": 1, "width": 900, "height": 700}],
        }
        geometry = {
            "objects": [
                {
                    "geometry_id": "g_left",
                    "kind": "line",
                    "page_number": 1,
                    "bbox": [40, 80, 120, 82],
                    "center": [80.0, 81.0],
                    "length": 80.0,
                    "width": 80.0,
                    "area": 160.0,
                    "orientation": 0.0,
                    "nearby_text": "",
                },
                {
                    "geometry_id": "g_right",
                    "kind": "line",
                    "page_number": 1,
                    "bbox": [640, 80, 720, 82],
                    "center": [680.0, 81.0],
                    "length": 80.0,
                    "width": 80.0,
                    "area": 160.0,
                    "orientation": 0.0,
                    "nearby_text": "",
                },
            ],
            "association_radius_pdf_points": 160.0,
        }
        assign_detail_regions(document, geometry)
        self.assertNotEqual(
            document["engineering_tokens"][0]["region_id"],
            document["engineering_tokens"][1]["region_id"],
        )
        graph = build_graph(document, geometry)
        nearest = [
            edge
            for edge in graph["edges"]
            if edge["relationship"] == "nearest_geometry"
        ]
        nodes = {node["node_id"]: node for node in graph["nodes"]}
        self.assertEqual(len(nearest), 2)
        for edge in nearest:
            source = nodes[edge["source"]]
            target = nodes[edge["target"]]
            self.assertEqual(source.get("region_id"), target.get("region_id"))

    def test_spatial_index_skips_other_region(self) -> None:
        label = {
            "node_id": "txt_a",
            "center": [50.0, 50.0],
            "bbox": [40, 40, 60, 60],
            "region_id": "p1_r0",
        }
        geometry_nodes = [
            {
                "node_id": "geo_same",
                "center": [70.0, 50.0],
                "bbox": [68, 40, 72, 60],
                "geometry_kind": "line",
                "region_id": "p1_r0",
            },
            {
                "node_id": "geo_other",
                "center": [80.0, 50.0],
                "bbox": [78, 40, 82, 60],
                "geometry_kind": "line",
                "region_id": "p1_r1",
            },
        ]
        tree, ordered = build_page_index(geometry_nodes)
        candidates = nearest_geometry_candidates(
            label, tree, ordered, max_distance=160.0, top_k=5
        )
        ids = {item.node_id for item in candidates}
        self.assertIn("geo_same", ids)
        self.assertNotIn("geo_other", ids)


if __name__ == "__main__":
    unittest.main()
