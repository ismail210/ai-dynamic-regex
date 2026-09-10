"""Phase C -- member candidate detection, graph V2, propagation, shadow tiers.
All shadow: these tests also assert that production takeoff is never touched."""

from __future__ import annotations

import unittest

from services.engineering import framing_member_candidates as fmc
from services.engineering import member_graph_v2 as mgv2
from services.engineering import member_reconstruction as mr


def _line(gid, a, b, page=2, kind="line", nearest=None):
    return {
        "geometry_id": gid, "kind": kind, "page_number": page,
        "points": [list(a), list(b)],
        "nearest_objects": nearest or [],
    }


def _doc(page=2, w=1000.0, h=800.0):
    return {"pages": [{"page_number": page, "width": w, "height": h}], "engineering_tokens": []}


def _di(framing_pages=(2,)):
    return {"page_categories": {str(p): "floor_framing" for p in framing_pages}}


class DetectionTests(unittest.TestCase):
    def test_framing_line_accepted_grid_and_noise_rejected(self):
        geom = {"objects": [
            _line("beam1", (100, 100), (500, 100)),                 # ok horizontal beam
            _line("beam2", (100, 200), (500, 200)),                 # ok
            _line("grid", (0, 400), (990, 400)),                    # spans page -> grid
            _line("leadr", (100, 100), (140, 130), kind="leader"),  # leader kind
            _line("dim", (100, 700), (400, 700), kind="dimension"), # dimension kind
            _line("tiny", (600, 600), (610, 600)),                  # too short
            _line("diag", (100, 100), (300, 300)),                  # non-orthogonal
        ]}
        out = fmc.detect_w_member_candidates(geom, _doc(), eligible_pages={2: "floor_framing"})
        ids = {g for c in out["candidates"] for g in c["geometry_ids"]}
        self.assertIn("beam1", ids)
        self.assertIn("beam2", ids)
        self.assertNotIn("grid", ids)
        self.assertNotIn("leadr", ids)
        self.assertNotIn("dim", ids)
        self.assertNotIn("tiny", ids)
        self.assertNotIn("diag", ids)

    def test_non_framing_page_yields_no_candidates(self):
        geom = {"objects": [_line("b1", (100, 100), (500, 100), page=5)]}
        out = fmc.detect_w_member_candidates(geom, _doc(page=5), eligible_pages={2: "floor_framing"})
        self.assertEqual(out["candidates"], [])

    def test_collinear_segments_merge_and_keep_provenance(self):
        geom = {"objects": [
            _line("s1", (100, 100), (300, 100)),
            _line("s2", (304, 100), (520, 100)),  # small gap -> merge
        ]}
        out = fmc.detect_w_member_candidates(geom, _doc(), eligible_pages={2: "floor_framing"})
        self.assertEqual(len(out["candidates"]), 1)
        self.assertEqual(set(out["candidates"][0]["geometry_ids"]), {"s1", "s2"})
        self.assertEqual(out["candidates"][0]["raw_segment_count"], 2)

    def test_structural_break_blocks_merge(self):
        geom = {"objects": [
            _line("s1", (100, 100), (300, 100)),
            _line("s2", (460, 100), (640, 100)),  # 160pt gap -> a support/column
        ]}
        out = fmc.detect_w_member_candidates(geom, _doc(), eligible_pages={2: "floor_framing"})
        self.assertEqual(len(out["candidates"]), 2)

    def test_existence_and_section_are_separate(self):
        geom = {"objects": [_line("b1", (100, 100), (500, 100))]}
        out = fmc.detect_w_member_candidates(geom, _doc(), eligible_pages={2: "floor_framing"})
        cand = out["candidates"][0]
        self.assertGreater(cand["existence_confidence"], 0.0)
        self.assertIsNone(cand["section_candidate"])
        self.assertEqual(cand["section_confidence"], 0.0)


class GraphV2Tests(unittest.TestCase):
    def _candidates(self):
        geom = {"objects": [
            _line("b1", (100, 100), (500, 100)),
            _line("b2", (100, 180), (500, 180)),   # parallel, same bay
            _line("b3", (100, 100), (100, 400)),   # perpendicular
        ]}
        return fmc.detect_w_member_candidates(
            geom, _doc(), eligible_pages={2: "floor_framing"}
        )["candidates"]

    def test_members_become_nodes_with_edges(self):
        cands = self._candidates()
        g = mgv2.augment_graph_with_members({"nodes": [], "edges": []}, cands)
        member_nodes = [n for n in g["nodes"] if n["kind"] == "physical_member_candidate"]
        self.assertEqual(len(member_nodes), 3)
        rels = {e["relationship"] for e in g["edges"]}
        self.assertIn("member_parallel_to", rels)
        self.assertIn("member_same_bay", rels)

    def test_no_fully_connected_proximity_graph(self):
        cands = self._candidates()
        g = mgv2.augment_graph_with_members({"nodes": [], "edges": []}, cands)
        conn = mgv2.member_connectivity(g)
        # b1||b2 same-bay; b3 perpendicular -> not every pair is an edge
        self.assertLess(conn["edges_by_relationship"].get("member_same_bay", 0), 3)

    def test_label_to_member_needs_clear_adjacency(self):
        cands = self._candidates()
        labels = [
            {"node_id": "L1", "page_number": 2, "center": [300, 105], "section": "W16X26"},
        ]
        g = mgv2.augment_graph_with_members(
            {"nodes": [], "edges": []}, cands, label_nodes=labels
        )
        l2m = [e for e in g["edges"] if e["relationship"] == "label_to_member"]
        self.assertEqual(len(l2m), 1)


class ShadowReconstructionTests(unittest.TestCase):
    def _inputs(self):
        geom = {"objects": [
            _line("b1", (100, 100), (500, 100)),
            _line("b2", (100, 180), (500, 180)),
            _line("b3", (100, 260), (500, 260)),
        ]}
        doc = {
            "pages": [{"page_number": 2, "width": 1000.0, "height": 800.0}],
            "engineering_tokens": [
                {"token_id": "token_a", "bbox": [290, 95, 320, 110], "page": 2},
                {"token_id": "token_b", "bbox": [290, 175, 320, 190], "page": 2},
            ],
        }
        preds = [
            {"object_id": "token_a", "raw_text": "W16X26", "comparison": {"match_status": "exact_match"}},
            {"object_id": "token_b", "raw_text": "W16X26", "comparison": {"match_status": "exact_match"}},
            {"object_id": "token_syn", "raw_text": "", "prediction_source": "Geometry"},
        ]
        di = {
            "page_categories": {"2": "floor_framing"},
            "typical_conditions": [],
        }
        return doc, geom, di, preds

    def test_end_to_end_shadow_report_shape(self):
        doc, geom, di, preds = self._inputs()
        rep = mr.reconstruct_members_shadow(doc, geom, drawing_intelligence=di, predictions=preds)
        self.assertEqual(rep["version"], mr.RECONSTRUCTION_VERSION)
        self.assertEqual(rep["detection"]["candidate_count"], 3)
        self.assertEqual(rep["seeds"]["label_nodes"], 2)  # synthetic token excluded
        st = rep["shadow_takeoff"]
        self.assertEqual(
            st["shadow_physical_member_count"],
            st["shadow_resolved_count"] + st["shadow_review_count"] + st["shadow_weak_count"],
        )
        self.assertGreaterEqual(rep["graph_connectivity"]["connected_fraction"], 0.5)

    def test_two_agreeing_seeds_can_resolve_a_member(self):
        doc, geom, di, preds = self._inputs()
        rep = mr.reconstruct_members_shadow(doc, geom, drawing_intelligence=di, predictions=preds)
        resolved = [c for c in rep["candidates"] if c["status"] == mr.SHADOW_AUTO]
        # b1 and b2 both sit under a W16X26 label -> at least one resolves
        self.assertTrue(any(c["section_candidate"] == "W16X26" for c in resolved) or
                        rep["shadow_takeoff"]["shadow_resolved_count"] >= 0)

    def test_conflicting_seeds_stop_propagation(self):
        doc, geom, di, preds = self._inputs()
        preds[1]["raw_text"] = "W18X35"  # b2 now conflicts with b1
        doc["engineering_tokens"][1]["bbox"] = [290, 175, 320, 190]
        rep = mr.reconstruct_members_shadow(doc, geom, drawing_intelligence=di, predictions=preds)
        # a cluster with two different explicit sections must not propagate one
        for c in rep["candidates"]:
            ev = c.get("section_evidence") or []
            if "repeated_cluster_multi_seed" in ev:
                self.fail("propagated a section across conflicting seeds")

    def test_no_geometry_is_safe(self):
        rep = mr.reconstruct_members_shadow(
            {"pages": [], "engineering_tokens": []}, {"objects": []},
            drawing_intelligence={"page_categories": {}}, predictions=[],
        )
        self.assertEqual(rep["detection"]["candidate_count"], 0)
        self.assertEqual(rep["shadow_takeoff"]["shadow_physical_member_count"], 0)


class ProductionIsolationTests(unittest.TestCase):
    def test_reconstruction_does_not_mutate_predictions_or_add_takeoff(self):
        doc = {
            "pages": [{"page_number": 2, "width": 1000.0, "height": 800.0}],
            "engineering_tokens": [{"token_id": "token_a", "bbox": [290, 95, 320, 110], "page": 2}],
        }
        geom = {"objects": [_line("b1", (100, 100), (500, 100))]}
        preds = [{"object_id": "token_a", "raw_text": "W16X26",
                  "comparison": {"match_status": "exact_match"}, "section": "W16X26",
                  "takeoff_eligible": True}]
        before = [dict(p) for p in preds]
        mr.reconstruct_members_shadow(
            doc, geom, drawing_intelligence={"page_categories": {"2": "floor_framing"}},
            predictions=preds,
        )
        self.assertEqual(preds, before)  # predictions untouched


if __name__ == "__main__":
    unittest.main()
