"""Phase 2 association target policy: dimensions and sheet furniture.

Production ``nearest_geometry`` uses ``spatial_index.nearest_geometry_candidates``.
Phase 1: 210/842 labels attached to ``dimension``; K1200 attached 171 labels
to huge rectangles (example HSS6X6X3/8, dist 0, length ~3327pt).
"""

from __future__ import annotations

import unittest

from services.engineering import spatial_index


def _geom(
    node_id: str,
    x: float,
    y: float,
    *,
    geometry_kind: str = "line",
    bbox=None,
    size: float = 4.0,
):
    if bbox is None:
        bbox = [x - size, y - size, x + size, y + size]
    return {
        "node_id": node_id,
        "source_id": node_id,
        "kind": "geometry",
        "page_number": 1,
        "bbox": bbox,
        "center": [x, y],
        "geometry_kind": geometry_kind,
        "region_id": "p1_r0",
    }


def _label(x: float, y: float):
    return {
        "node_id": "label",
        "kind": "label",
        "page_number": 1,
        "text": "W21X44",
        "bbox": [x - 2, y - 2, x + 2, y + 2],
        "center": [x, y],
        "region_id": "p1_r0",
    }


def _candidates(label, nodes, max_distance=160.0):
    tree, ordered = spatial_index.build_page_index(nodes)
    return spatial_index.nearest_geometry_candidates(
        label, tree, ordered, max_distance=max_distance, top_k=5
    )


class DimensionTargetFilterTests(unittest.TestCase):
    def test_overlapping_dimension_loses_to_nearby_member(self) -> None:
        label = _label(0, 0)
        dimension = _geom(
            "dim", 0, 0, geometry_kind="dimension", bbox=[-20, -8, 40, 8]
        )
        member = _geom("member", 25, 0, geometry_kind="line", size=6)
        ids = [c.node_id for c in _candidates(label, [dimension, member])]
        self.assertEqual(ids[0], "member")
        self.assertNotIn("dim", ids)

    def test_member_farther_than_dimension_still_wins(self) -> None:
        label = _label(0, 0)
        dimension = _geom("dim", 0, 0, geometry_kind="dimension", size=10)
        member = _geom("member", 50, 0, geometry_kind="polyline", size=6)
        ids = [c.node_id for c in _candidates(label, [dimension, member])]
        self.assertEqual(ids[0], "member")

    def test_leader_to_member_skips_dimension_under_label(self) -> None:
        label = _label(0, 0)
        dimension = _geom("dim", 0, 0, geometry_kind="dimension", size=12)
        leader = _geom("leader", 80, 0, geometry_kind="leader", size=2)
        leader["bbox"] = [0, -1, 160, 1]
        member = _geom("member", 165, 0, geometry_kind="line", size=5)
        ids = [c.node_id for c in _candidates(label, [dimension, leader, member], 80)]
        self.assertIn("member", ids)
        self.assertNotIn("dim", ids)
        self.assertNotIn("leader", ids)

    def test_dimension_only_area_stays_unresolved(self) -> None:
        label = _label(0, 0)
        dimension = _geom("dim", 0, 0, geometry_kind="dimension", size=15)
        self.assertEqual(_candidates(label, [dimension]), [])

    def test_structural_line_near_dimension_remains_a_candidate(self) -> None:
        label = _label(0, 0)
        dimension = _geom("dim", 80, 0, geometry_kind="dimension", size=8)
        member = _geom("member", 12, 0, geometry_kind="line", size=5)
        ids = [c.node_id for c in _candidates(label, [dimension, member])]
        self.assertEqual(ids[0], "member")


class HugeRectangleFilterTests(unittest.TestCase):
    def test_huge_filled_strip_loses_to_member(self) -> None:
        label = _label(0, 0)
        sheet = _geom(
            "sheet",
            1000,
            100,
            geometry_kind="rectangle",
            bbox=[-10, -80, 3317, 120],
        )
        member = _geom("member", 20, 0, geometry_kind="line", size=4)
        ids = [c.node_id for c in _candidates(label, [sheet, member], 72)]
        self.assertNotIn("sheet", ids)
        self.assertEqual(ids[0], "member")

    def test_plate_like_rectangle_is_kept(self) -> None:
        label = _label(0, 0)
        plate = _geom(
            "plate", 8, 0, geometry_kind="rectangle", bbox=[2, -10, 38, 10]
        )
        ids = [c.node_id for c in _candidates(label, [plate])]
        self.assertEqual(ids, ["plate"])

    def test_page_border_excluded(self) -> None:
        label = _label(0, 0)
        border = _geom(
            "border", 500, 500, geometry_kind="rectangle", size=2000
        )
        member = _geom("member", 8, 0, geometry_kind="line", size=3)
        ids = [c.node_id for c in _candidates(label, [border, member])]
        self.assertNotIn("border", ids)
        self.assertIn("member", ids)

    def test_leader_near_huge_rect_resolves_to_member(self) -> None:
        label = _label(0, 0)
        leader = _geom("leader", 80, 0, geometry_kind="leader", size=2)
        leader["bbox"] = [0, -1, 180, 1]
        sheet = _geom(
            "sheet",
            90,
            0,
            geometry_kind="rectangle",
            bbox=[-20, -100, 3300, 100],
        )
        member = _geom("member", 185, 0, geometry_kind="line", size=4)
        ids = [c.node_id for c in _candidates(label, [leader, sheet, member], 80)]
        self.assertIn("member", ids)
        self.assertNotIn("sheet", ids)

    def test_huge_rect_only_stays_unresolved(self) -> None:
        label = _label(0, 0)
        sheet = _geom(
            "sheet",
            1000,
            0,
            geometry_kind="rectangle",
            bbox=[-50, -80, 3200, 80],
        )
        self.assertEqual(_candidates(label, [sheet], 72), [])


if __name__ == "__main__":
    unittest.main()
