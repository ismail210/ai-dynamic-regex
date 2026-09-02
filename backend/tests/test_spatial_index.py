"""Tests for the experimental, non-production STRtree candidate generator.

See services/engineering/spatial_index.py's module docstring and
docs/geometry_graph_audit/08_prioritized_roadmap.md P1.2. This module is
intentionally NOT wired into the production pipeline in this phase --
test_never_wired_into_production_pipeline below is a structural guard
against that happening silently.
"""

from __future__ import annotations

import inspect
import random
import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering import spatial_index
from services.engineering.geometry_extractor import extract_geometry
from services.pdf_parser import extract_document_structure


def _geometry_node(node_id: str, x: float, y: float, *, geometry_kind: str = "line", size: float = 4.0):
    return {
        "node_id": node_id,
        "source_id": node_id,
        "kind": "geometry",
        "page_number": 1,
        "text": "",
        "bbox": [x - size, y - size, x + size, y + size],
        "center": [x, y],
        "geometry_kind": geometry_kind,
        "length": size * 2,
        "width": size * 2,
        "area": (size * 2) ** 2,
        "orientation": 0.0,
    }


def _text_node(node_id: str, x: float, y: float):
    return {
        "node_id": node_id,
        "source_id": node_id,
        "kind": "label",
        "page_number": 1,
        "text": "W12X26",
        "bbox": [x - 2, y - 2, x + 2, y + 2],
        "center": [x, y],
    }


class SpatiallyCompletePairsTests(unittest.TestCase):
    def test_spatially_complete_finds_pairs_the_windowed_loop_misses(self) -> None:
        # 70 geometry nodes in a tight cluster (so many are genuinely
        # close to each other) but with node[0] and node[65] placed right
        # next to each other while everything between them, in LIST
        # ORDER, is unrelated filler -- exactly the scenario
        # graph_builder's page_geom[:60] / next-11 window is blind to.
        nodes = [_geometry_node(f"filler_{i}", 1000 + i * 5, 1000) for i in range(64)]
        close_a = _geometry_node("close_a", 0, 0)
        close_b = _geometry_node("close_b", 5, 5)
        nodes.insert(0, close_a)
        nodes.append(close_b)  # index 65, far outside window_cap=60/window from index 0

        complete = spatial_index.spatially_complete_geometry_pairs(nodes, max_distance=50)
        windowed = spatial_index.legacy_windowed_pairs(nodes, max_distance=50)

        complete_keys = {(a, b) for a, b, _ in complete}
        windowed_keys = {(a, b) for a, b, _ in windowed}

        pair_key = tuple(sorted(("close_a", "close_b")))
        self.assertIn(pair_key, complete_keys, "STRtree must find the genuinely close pair")
        self.assertNotIn(
            pair_key,
            windowed_keys,
            "the legacy windowed loop must miss it (index 0 vs index 65, "
            "outside its next-11 window)",
        )

    def test_extraction_order_invariance(self) -> None:
        rng = random.Random(42)
        nodes = [
            _geometry_node(f"n{i}", rng.uniform(0, 500), rng.uniform(0, 500))
            for i in range(80)
        ]
        shuffled = list(nodes)
        rng.shuffle(shuffled)

        complete_original = {
            (a, b)
            for a, b, _ in spatial_index.spatially_complete_geometry_pairs(
                nodes, max_distance=60
            )
        }
        complete_shuffled = {
            (a, b)
            for a, b, _ in spatial_index.spatially_complete_geometry_pairs(
                shuffled, max_distance=60
            )
        }
        self.assertEqual(
            complete_original,
            complete_shuffled,
            "spatially-complete pairs must not depend on input list order",
        )

        windowed_original = {
            (a, b)
            for a, b, _ in spatial_index.legacy_windowed_pairs(nodes, max_distance=60)
        }
        windowed_shuffled = {
            (a, b)
            for a, b, _ in spatial_index.legacy_windowed_pairs(shuffled, max_distance=60)
        }
        self.assertNotEqual(
            windowed_original,
            windowed_shuffled,
            "the legacy windowed loop's result SHOULD change under reordering "
            "-- this is the defect being measured, not a bug in the test",
        )

    def test_coverage_report_recall_is_measurably_below_one_on_a_dense_shuffled_page(self) -> None:
        rng = random.Random(7)
        nodes = [
            _geometry_node(f"n{i}", rng.uniform(0, 1000), rng.uniform(0, 1000))
            for i in range(150)
        ]
        rng.shuffle(nodes)
        report = spatial_index.coverage_report(nodes, max_distance=80)
        self.assertGreater(report["spatially_complete_pair_count"], 0)
        self.assertLess(
            report["window_recall"],
            1.0,
            "a dense, shuffled page must show the windowed loop missing "
            "some genuinely-close pairs, matching the deep-research "
            "report's synthetic experiment (~11%-19% recall)",
        )


class NearestGeometryCandidatesTests(unittest.TestCase):
    def test_one_label_with_several_valid_geometries_returns_ranked_alternatives(self) -> None:
        geometry_nodes = [
            _geometry_node("near", 10, 0),
            _geometry_node("mid", 40, 0),
            _geometry_node("far", 70, 0),
        ]
        tree, ordered = spatial_index.build_page_index(geometry_nodes)
        label = _text_node("label_1", 0, 0)
        candidates = spatial_index.nearest_geometry_candidates(
            label, tree, ordered, max_distance=100, top_k=3
        )
        self.assertEqual([c.node_id for c in candidates], ["near", "mid", "far"])
        self.assertTrue(all(c.distance >= 0 for c in candidates))

    def test_two_labels_competing_for_one_geometry_both_list_it(self) -> None:
        geometry_nodes = [_geometry_node("shared_target", 0, 0)]
        tree, ordered = spatial_index.build_page_index(geometry_nodes)
        label_a = _text_node("label_a", 5, 0)
        label_b = _text_node("label_b", -5, 0)

        candidates_a = spatial_index.nearest_geometry_candidates(
            label_a, tree, ordered, max_distance=50, top_k=5
        )
        candidates_b = spatial_index.nearest_geometry_candidates(
            label_b, tree, ordered, max_distance=50, top_k=5
        )
        # Candidate generation deliberately does not enforce exclusivity --
        # that is a downstream global-resolution concern (roadmap P1.6,
        # bipartite matching), not this module's job.
        self.assertEqual([c.node_id for c in candidates_a], ["shared_target"])
        self.assertEqual([c.node_id for c in candidates_b], ["shared_target"])

    def test_no_valid_target_returns_empty_list(self) -> None:
        geometry_nodes = [_geometry_node("far_away", 10_000, 10_000)]
        tree, ordered = spatial_index.build_page_index(geometry_nodes)
        label = _text_node("isolated_label", 0, 0)
        candidates = spatial_index.nearest_geometry_candidates(
            label, tree, ordered, max_distance=50, top_k=5
        )
        self.assertEqual(candidates, [])

    def test_leader_resolves_to_far_endpoint_target_not_the_leader_itself(self) -> None:
        # The label sits right next to a leader stroke. The leader's bbox
        # spans from near the label out to a real target member that is
        # FAR from the label directly (beyond max_distance), but close to
        # the leader's far endpoint. graph_builder.build_graph has no
        # equivalent logic (docs/geometry_graph_audit/04_graph_audit.md §4)
        # -- it would treat the leader itself as the nearest candidate and
        # never discover the real target.
        label = _text_node("label", 0, 0)
        leader = _geometry_node("leader", 100, 0, geometry_kind="leader", size=2.0)
        leader["bbox"] = [0, -1, 200, 1]  # spans from the label out to x=200
        real_target = _geometry_node("real_target", 205, 0, geometry_kind="line")
        decoy_far_line = _geometry_node("decoy", 40, 0, geometry_kind="line")

        geometry_nodes = [leader, real_target, decoy_far_line]
        tree, ordered = spatial_index.build_page_index(geometry_nodes)

        # max_distance=60 means the real target (205 units away) is NOT
        # reachable by direct label->geometry distance at all.
        candidates = spatial_index.nearest_geometry_candidates(
            label, tree, ordered, max_distance=60, top_k=5
        )
        candidate_ids = [c.node_id for c in candidates]

        self.assertIn(
            "real_target",
            candidate_ids,
            "resolving through the leader's far endpoint must surface the "
            "real target even though it is far outside max_distance from "
            "the label directly",
        )
        target_candidate = next(c for c in candidates if c.node_id == "real_target")
        self.assertIn("leader_endpoint_resolved", target_candidate.sources)
        self.assertNotIn(
            "leader",
            candidate_ids,
            "the leader stroke is a pointer, not a member target",
        )


class AreaShapedFalsePositiveTests(unittest.TestCase):
    """Regression tests for a real-project pilot defect (Phase 2.5): a
    page-spanning filled rectangle (sheet border / title block) was
    returned as a candidate -- and even as a leader-resolved target --
    for nearly every label on a real page, because it is large in both
    dimensions and ``use_bbox_distance=True`` reports 0 distance for any
    point inside a bbox. See ``spatial_index._is_area_shaped``'s
    docstring for the full real-data story.
    """

    def test_page_spanning_rectangle_is_excluded_as_a_direct_candidate(self) -> None:
        label = _text_node("label", 0, 0)
        # A "border" bbox large in both width and height, well beyond
        # max_distance in every direction -- but the label's centroid is
        # geometrically inside it, so naive bbox-distance would say 0.
        border = _geometry_node("border", 500, 500, geometry_kind="rectangle", size=2000)
        real_member = _geometry_node("real_member", 10, 0, geometry_kind="line", size=3.0)

        geometry_nodes = [border, real_member]
        tree, ordered = spatial_index.build_page_index(geometry_nodes)
        candidates = spatial_index.nearest_geometry_candidates(
            label, tree, ordered, max_distance=160, top_k=5
        )
        candidate_ids = [c.node_id for c in candidates]
        self.assertNotIn(
            "border", candidate_ids, "a page-spanning filled region must not be offered as a candidate"
        )
        self.assertIn("real_member", candidate_ids)

    def test_leader_resolution_does_not_land_on_a_page_spanning_rectangle(self) -> None:
        label = _text_node("label", 0, 0)
        leader = _geometry_node("leader", 100, 0, geometry_kind="leader", size=2.0)
        leader["bbox"] = [0, -1, 200, 1]
        # The leader's far endpoint (200, ~0) is geometrically inside this
        # huge border, exactly like the real pilot page.
        border = _geometry_node("border", 500, 500, geometry_kind="rectangle", size=2000)

        geometry_nodes = [leader, border]
        tree, ordered = spatial_index.build_page_index(geometry_nodes)
        candidates = spatial_index.nearest_geometry_candidates(
            label, tree, ordered, max_distance=160, top_k=5
        )
        candidate_ids = [c.node_id for c in candidates]
        self.assertNotIn(
            "border",
            candidate_ids,
            "leader-endpoint resolution must not surface a page-spanning "
            "filled region as the resolved target",
        )

    def test_a_genuinely_long_thin_member_is_not_excluded(self) -> None:
        # A real long beam: large in ONE dimension (length) but thin in
        # the other (member width) -- must NOT be caught by the
        # area-shaped filter, which only excludes objects large in BOTH
        # dimensions.
        label = _text_node("label", 0, 0)
        long_beam = _geometry_node("long_beam", 400, 0, geometry_kind="line", size=1.0)
        long_beam["bbox"] = [0, -1, 800, 1]  # 800 units long, 2 units wide
        geometry_nodes = [long_beam]
        tree, ordered = spatial_index.build_page_index(geometry_nodes)
        candidates = spatial_index.nearest_geometry_candidates(
            label, tree, ordered, max_distance=160, top_k=5
        )
        self.assertEqual([c.node_id for c in candidates], ["long_beam"])


class GenerateSpatialCandidatesIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "sample.pdf"
        doc = fitz.open()
        page = doc.new_page(width=600, height=800)
        page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
        page.insert_text((72, 120), "HSS8X8X1/2 COLUMN", fontsize=12)
        page.draw_rect(fitz.Rect(200, 200, 400, 260), color=(0, 0, 0), width=1)
        page.draw_line(fitz.Point(50, 300), fitz.Point(250, 300), color=(0, 0, 0), width=1)
        page.draw_circle(fitz.Point(450, 400), 30, color=(0, 0, 0), width=1)
        doc.save(self.pdf)
        doc.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_generate_spatial_candidates_smoke_on_real_extracted_document(self) -> None:
        document = extract_document_structure(str(self.pdf))
        geometry = extract_geometry(str(self.pdf), document)
        result = spatial_index.generate_spatial_candidates(document, geometry)

        self.assertIn("pages", result)
        self.assertTrue(result["pages"], "fixture should produce at least one page")
        for page_number, page_result in result["pages"].items():
            self.assertIsInstance(page_number, int)
            self.assertIn("label_candidates", page_result)
            self.assertIn("coverage", page_result)
            coverage = page_result["coverage"]
            for key in (
                "geometry_node_count",
                "spatially_complete_pair_count",
                "windowed_pair_count",
                "window_recall",
            ):
                self.assertIn(key, coverage)

    def test_output_is_reproducible_across_two_runs(self) -> None:
        document = extract_document_structure(str(self.pdf))
        geometry = extract_geometry(str(self.pdf), document)
        result_a = spatial_index.generate_spatial_candidates(document, geometry)
        result_b = spatial_index.generate_spatial_candidates(document, geometry)
        self.assertEqual(result_a, result_b)


class NotWiredIntoProductionTests(unittest.TestCase):
    def test_graph_builder_uses_spatial_index(self) -> None:
        from services.engineering import graph_builder

        source = inspect.getsource(graph_builder)
        self.assertIn(
            "nearest_geometry_candidates",
            source,
            "graph_builder should use leader-aware spatial index association",
        )


if __name__ == "__main__":
    unittest.main()
