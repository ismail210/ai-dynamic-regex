"""Collinear CAD fragment merging and scale-aware gap."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.drawing_scale import (
    fragment_gap_pdf_points,
    parse_scale_text,
)
from services.engineering.geometry_extractor import extract_geometry
from services.engineering.geometry_normalizer import merge_collinear_fragments


def _line(page: int, x0: float, y0: float, x1: float, y1: float, gid: str) -> dict:
    return {
        "geometry_id": gid,
        "kind": "line",
        "page_number": page,
        "page": page,
        "bbox": [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)],
        "points": [[x0, y0], [x1, y1]],
        "orientation": 0.0,
        "length": abs(x1 - x0) + abs(y1 - y0),
    }


class FragmentMergeTests(unittest.TestCase):
    def test_three_collinear_fragments_become_one(self) -> None:
        objects = [
            _line(1, 10, 40, 40, 40, "a"),
            _line(1, 42, 40, 80, 40, "b"),
            _line(1, 82, 40, 120, 40, "c"),
        ]
        merged, stats = merge_collinear_fragments(objects, gap=8.0)
        self.assertEqual(stats["clusters_merged"], 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["merged_from"], ["a", "b", "c"])
        self.assertGreaterEqual(merged[0]["length"], 100)

    def test_parallel_offset_lines_stay_separate(self) -> None:
        objects = [
            _line(1, 10, 40, 80, 40, "a"),
            _line(1, 10, 55, 80, 55, "b"),
        ]
        merged, stats = merge_collinear_fragments(objects, gap=8.0)
        self.assertEqual(stats["clusters_merged"], 0)
        self.assertEqual(len(merged), 2)

    def test_leaders_are_not_merged(self) -> None:
        a = _line(1, 10, 10, 40, 10, "a")
        b = _line(1, 42, 10, 80, 10, "b")
        a["kind"] = "leader"
        b["kind"] = "leader"
        merged, stats = merge_collinear_fragments([a, b], gap=8.0)
        self.assertEqual(stats["clusters_merged"], 0)
        self.assertEqual(len(merged), 2)

    def test_scale_shrinks_gap_on_small_plot(self) -> None:
        quarter = parse_scale_text('1/4"=1\'-0"')
        eighth = parse_scale_text('1/8"=1\'-0"')
        self.assertIsNotNone(quarter)
        self.assertIsNotNone(eighth)
        self.assertLess(
            fragment_gap_pdf_points(eighth),
            fragment_gap_pdf_points(quarter) + 1e-6,
        )

    def test_pdf_collinear_strokes_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "frag.pdf"
            doc = fitz.open()
            page = doc.new_page(width=700, height=200)
            page.draw_line(fitz.Point(20, 80), fitz.Point(220, 80))
            page.draw_line(fitz.Point(226, 80), fitz.Point(420, 80))
            page.draw_line(fitz.Point(426, 80), fitz.Point(620, 80))
            doc.save(pdf)
            doc.close()
            geometry = extract_geometry(str(pdf), document_structure={"engineering_tokens": []})
        stats = geometry.get("fragment_merge") or {}
        self.assertGreaterEqual(stats.get("clusters_merged", 0), 1)
        merged = [o for o in geometry["objects"] if o.get("merged_from")]
        self.assertTrue(merged)
        self.assertGreaterEqual(len(merged[0]["merged_from"]), 2)


if __name__ == "__main__":
    unittest.main()
