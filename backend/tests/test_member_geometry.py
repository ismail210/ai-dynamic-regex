"""Focused tests for deterministic member_candidate geometry (OCR bbox)."""

from __future__ import annotations

import unittest

from services.engineering.member_geometry import (
    associate_text_to_member_candidate,
    attach_member_geometry_to_predictions,
    build_member_candidates,
    role_hint_from_orientation,
    unresolved_member_geometry,
)


def _line(
    gid: str,
    *,
    page: int = 1,
    bbox: list,
    length: float,
    orientation: float = 0.0,
    kind: str = "line",
    points: list | None = None,
    leader_endpoints: dict | None = None,
) -> dict:
    obj = {
        "geometry_id": gid,
        "kind": kind,
        "geometry_type": kind,
        "page_number": page,
        "page": page,
        "bbox": bbox,
        "length": length,
        "orientation": orientation,
        "points": points
        or [[bbox[0], bbox[1]], [bbox[2], bbox[3]]],
        "center": [
            (bbox[0] + bbox[2]) / 2.0,
            (bbox[1] + bbox[3]) / 2.0,
        ],
    }
    if leader_endpoints:
        obj["leader_endpoints"] = leader_endpoints
    return obj


class MemberGeometryTests(unittest.TestCase):
    def test_build_candidates_excludes_leaders_and_dimensions(self) -> None:
        geometry = {
            "objects": [
                _line("geom_beam", bbox=[0, 10, 200, 10], length=200),
                _line(
                    "geom_leader",
                    bbox=[50, 50, 80, 50],
                    length=30,
                    kind="leader",
                ),
                _line(
                    "geom_dim",
                    bbox=[0, 100, 150, 100],
                    length=150,
                    kind="dimension",
                ),
                _line("geom_short", bbox=[0, 20, 20, 20], length=20),
            ]
        }
        cands = build_member_candidates(geometry)
        ids = {c["geometry_id"] for c in cands}
        self.assertTrue(any("source_primitive_ids" in c for c in cands))
        self.assertEqual(len(cands), 1)
        self.assertIn("geom_beam", cands[0]["source_primitive_ids"])
        self.assertNotIn("geom_leader", str(ids))

    def test_collinear_fragments_group_into_one_candidate(self) -> None:
        geometry = {
            "objects": [
                _line(
                    "geom_a",
                    bbox=[0, 10, 100, 10],
                    length=100,
                    points=[[0, 10], [100, 10]],
                ),
                _line(
                    "geom_b",
                    bbox=[102, 10, 200, 10],
                    length=98,
                    points=[[102, 10], [200, 10]],
                ),
            ]
        }
        cands = build_member_candidates(geometry)
        self.assertEqual(len(cands), 1)
        self.assertEqual(
            set(cands[0]["source_primitive_ids"]), {"geom_a", "geom_b"}
        )
        self.assertEqual(cands[0]["bbox"][0], 0)
        self.assertEqual(cands[0]["bbox"][2], 200)

    def test_orthogonal_strokes_are_not_grouped(self) -> None:
        geometry = {
            "objects": [
                _line(
                    "geom_h",
                    bbox=[0, 10, 200, 10],
                    length=200,
                    orientation=0.0,
                    points=[[0, 10], [200, 10]],
                ),
                _line(
                    "geom_v",
                    bbox=[100, 10, 100, 210],
                    length=200,
                    orientation=90.0,
                    points=[[100, 10], [100, 210]],
                ),
            ]
        }
        cands = build_member_candidates(geometry)
        self.assertEqual(len(cands), 2)

    def test_association_prefers_stroke_near_leader_tip(self) -> None:
        geometry = {
            "objects": [
                _line(
                    "geom_beam",
                    bbox=[0, 100, 300, 100],
                    length=300,
                    points=[[0, 100], [300, 100]],
                ),
                _line(
                    "geom_leader",
                    bbox=[140, 40, 150, 95],
                    length=55,
                    kind="leader",
                    points=[[145, 40], [145, 95]],
                    leader_endpoints={
                        "near_endpoint": [145, 40],
                        "far_endpoint": [145, 95],
                    },
                ),
                _line(
                    "geom_far",
                    bbox=[800, 800, 900, 800],
                    length=100,
                    points=[[800, 800], [900, 800]],
                ),
            ]
        }
        cands = build_member_candidates(geometry)
        text_bbox = [130, 20, 170, 35]
        result = associate_text_to_member_candidate(
            text_bbox=text_bbox,
            page_number=1,
            geometry=geometry,
            member_candidates=cands,
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["type"], "member_candidate")
        self.assertIn("geom_beam", result["source_primitive_ids"])
        self.assertNotEqual(result["association_method"], "unresolved")
        self.assertEqual(result["bbox"], [0, 100, 300, 100])

    def test_leader_is_never_returned_as_member(self) -> None:
        geometry = {
            "objects": [
                _line(
                    "geom_leader_only",
                    bbox=[10, 10, 40, 10],
                    length=30,
                    kind="leader",
                    leader_endpoints={
                        "near_endpoint": [10, 10],
                        "far_endpoint": [40, 10],
                    },
                ),
            ]
        }
        result = associate_text_to_member_candidate(
            text_bbox=[5, 5, 15, 15],
            page_number=1,
            geometry=geometry,
        )
        self.assertFalse(result["available"])
        self.assertIsNone(result["bbox"])

    def test_unresolved_when_no_stroke_nearby(self) -> None:
        geometry = {
            "objects": [
                _line(
                    "geom_far",
                    bbox=[1000, 1000, 1200, 1000],
                    length=200,
                ),
            ]
        }
        result = associate_text_to_member_candidate(
            text_bbox=[10, 10, 40, 20],
            page_number=1,
            geometry=geometry,
        )
        self.assertEqual(result, unresolved_member_geometry(reason=result["association_method"]))
        self.assertFalse(result["available"])

    def test_attach_preserves_text_bbox(self) -> None:
        geometry = {
            "objects": [
                _line("geom_beam", bbox=[0, 50, 200, 50], length=200),
            ]
        }
        predictions = [
            {
                "page_number": 1,
                "bounding_box": [10, 10, 40, 20],
                "raw_text": "W12X26",
                "section": "W12X26",
            }
        ]
        attach_member_geometry_to_predictions(predictions, geometry)
        self.assertEqual(predictions[0]["bounding_box"], [10, 10, 40, 20])
        self.assertIn("member_geometry", predictions[0])

    def test_ambiguous_members_yield_null(self) -> None:
        geometry = {
            "objects": [
                _line(
                    "geom_a",
                    bbox=[0, 40, 200, 40],
                    length=200,
                    points=[[0, 40], [200, 40]],
                ),
                _line(
                    "geom_b",
                    bbox=[0, 48, 200, 48],
                    length=200,
                    points=[[0, 48], [200, 48]],
                ),
            ]
        }
        result = associate_text_to_member_candidate(
            text_bbox=[90, 20, 110, 30],
            page_number=1,
            geometry=geometry,
            ambiguity_margin_pt=20.0,
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["association_method"], "ambiguous_members")

    def test_role_hint_orientation(self) -> None:
        self.assertEqual(role_hint_from_orientation(0.0, 200), "beam_like")
        self.assertEqual(role_hint_from_orientation(90.0, 200), "column_like")
        self.assertEqual(role_hint_from_orientation(45.0, 200), "brace_like")
        self.assertIsNone(role_hint_from_orientation(0.0, 10))

    def test_same_coordinate_system_pdf_points(self) -> None:
        text_bbox = [100.0, 200.0, 140.0, 220.0]
        member_bbox = [50.0, 250.0, 400.0, 250.0]
        geometry = {
            "objects": [
                _line(
                    "geom_beam",
                    bbox=member_bbox,
                    length=350,
                    points=[[50, 250], [400, 250]],
                ),
            ]
        }
        result = associate_text_to_member_candidate(
            text_bbox=text_bbox,
            page_number=1,
            geometry=geometry,
            max_distance_pt=80.0,
        )
        # Both boxes remain in raw PDF points (no flip / normalize).
        self.assertTrue(result["available"])
        self.assertEqual(result["bbox"], member_bbox)
        self.assertTrue(all(isinstance(v, float) for v in result["bbox"]))


if __name__ == "__main__":
    unittest.main()
