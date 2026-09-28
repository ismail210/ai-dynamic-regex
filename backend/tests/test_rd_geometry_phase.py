"""Isolated geometry-phase R&D helpers — not production association."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts" / "rd_geometry_integration"))

from region_frames import bbox_iou
from retrieval import retrieve_candidates_for_label
from scorer import decide_association, score_candidate
from workflow_verify import attach_geometry_sidecar, sidecar_preserves_semantics


class ScorerTests(unittest.TestCase):
    def test_near_tie_abstains(self) -> None:
        cands = [
            {"geometry_id": "a", "geometry_kind": "line", "bbox_distance": 10.0, "leader_supported": False, "same_region": True},
            {"geometry_id": "b", "geometry_kind": "line", "bbox_distance": 10.5, "leader_supported": False, "same_region": True},
        ]
        decision = decide_association(cands)
        self.assertEqual(decision["status"], "ambiguous")
        self.assertEqual(decision["abstain_reason"], "near_tie")
        self.assertIsNone(decision["selected"])

    def test_leader_top_is_not_associated(self) -> None:
        cands = [
            {"geometry_id": "lead", "geometry_kind": "leader", "bbox_distance": 1.0, "leader_supported": False, "same_region": True},
        ]
        decision = decide_association(cands)
        self.assertEqual(decision["status"], "ambiguous")
        self.assertEqual(decision["abstain_reason"], "top_is_leader_or_dimension")

    def test_clear_winner_associates(self) -> None:
        cands = [
            {"geometry_id": "m", "geometry_kind": "line", "bbox_distance": 4.0, "leader_supported": True, "same_region": True},
            {"geometry_id": "n", "geometry_kind": "line", "bbox_distance": 40.0, "leader_supported": False, "same_region": True},
        ]
        decision = decide_association(cands)
        self.assertEqual(decision["status"], "associated")
        self.assertEqual(decision["selected"]["geometry_id"], "m")
        self.assertLess(score_candidate(cands[0]), score_candidate(cands[1]))


class RetrievalLeaderTests(unittest.TestCase):
    def test_excludes_leader_as_target(self) -> None:
        label = {"bbox": [0, 0, 10, 10], "page": 1, "token_id": "t"}
        geos = [
            {
                "geometry_id": "lead",
                "page_number": 1,
                "geometry_kind": "leader",
                "geometry_role": "leader",
                "bbox": [0, 0, 8, 8],
                "center": [4, 4],
                "centerline": [[0, 0], [8, 8]],
                "orientation": 0,
                "source_primitive": {},
            },
            {
                "geometry_id": "mem",
                "page_number": 1,
                "geometry_kind": "line",
                "geometry_role": "unknown",
                "bbox": [20, 0, 80, 4],
                "center": [50, 2],
                "centerline": [[20, 2], [80, 2]],
                "orientation": 0,
                "source_primitive": {},
            },
        ]
        cands = retrieve_candidates_for_label(
            label, geos, top_k=5, max_distance=200, exclude_leader_as_target=True
        )
        ids = [c["geometry_id"] for c in cands]
        self.assertNotIn("lead", ids)
        self.assertIn("mem", ids)


class RegionIouTests(unittest.TestCase):
    def test_identical_boxes_iou_one(self) -> None:
        self.assertEqual(bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)

    def test_disjoint_iou_zero(self) -> None:
        self.assertEqual(bbox_iou([0, 0, 1, 1], [5, 5, 6, 6]), 0.0)

    def test_title_frames_from_lines(self) -> None:
        from region_frames import seed_title_frames

        document = {
            "pages": [{"page_number": 18, "width": 3000, "height": 2000}],
            "engineering_tokens": [],
            "lines": [
                {
                    "page_number": 18,
                    "text": "TYPICAL COLUMN SPLICE DETAIL",
                    "bbox": [100, 100, 400, 120],
                }
            ],
        }
        geometry = {
            "objects": [
                {"page_number": 18, "bbox": [80, 40, 420, 180], "kind": "line"},
            ]
        }
        frames = seed_title_frames(document, geometry, 18, grow=80)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["provenance"], "research_proposed_frame")
        self.assertGreater(frames[0]["contained_geometry_count"], 0)


class WorkflowSidecarTests(unittest.TestCase):
    def test_geometry_sidecar_does_not_complete_label(self) -> None:
        before = {
            "original_text": "L4X4",
            "primary_label": "L4X4",
            "takeoff_eligible": False,
            "completion_status": "missing_thickness",
        }
        after = attach_geometry_sidecar(
            before,
            [{"geometry_id": "geom_x", "geometry_kind": "line"}],
            status="associated",
        )
        self.assertTrue(sidecar_preserves_semantics(before, after))
        self.assertEqual(after["primary_label"], "L4X4")
        self.assertFalse(after["takeoff_eligible"])
        self.assertIn("geometry_sidecar", after)
        self.assertNotIn("L4X4X1/4", str(after["geometry_sidecar"]))


class ReviewKitGoldPreserveTests(unittest.TestCase):
    def test_write_review_kit_does_not_clobber_existing_gold(self) -> None:
        import tempfile

        from review_kit import write_review_kit

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            gold = out / "gold_outcomes.jsonl"
            gold.write_text('{"token_id":"keep"}\n')
            write_review_kit([], out)
            self.assertEqual(gold.read_text(), '{"token_id":"keep"}\n')


class HumanGoldIntegrityTests(unittest.TestCase):
    def test_burrville_gold_has_75_unique_decisions(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "docs/validation/rd_geometry_integration/review_kit/gold_outcomes.jsonl"
        )
        self.assertTrue(path.exists(), path)
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        self.assertEqual(len(records), 75)
        ids = [r["token_id"] for r in records]
        self.assertEqual(len(ids), len(set(ids)))
        associated = [r for r in records if r.get("decision") == "associated"]
        for rec in associated:
            gid = rec.get("selected_geometry_id")
            self.assertTrue(gid)
            self.assertIn(gid, rec.get("candidate_geometry_ids") or [])
            self.assertEqual(rec.get("reviewed_target_geometry_ids"), [gid])
            self.assertEqual(rec.get("review_label"), "direct_target")
        for rec in records:
            if rec.get("decision") in {"ambiguous", "no_valid_member", "unavailable"}:
                self.assertIsNone(rec.get("selected_geometry_id"))
                self.assertEqual(rec.get("reviewed_target_geometry_ids") or [], [])


if __name__ == "__main__":
    unittest.main()
