"""Isolated tests for R&D retrieval_v2 — not production association."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts" / "rd_geometry_integration"))

from retrieval_v2 import (  # noqa: E402
    geometry_record_v2,
    retrieve_candidates_v2,
)


FORBIDDEN_IMPORTS = {
    "services.prediction",
    "services.prediction.orchestrator",
    "services.ml_association",
    "services.label_reconstruction",
    "services.engineering.graph_builder",
    "routers",
}


def _label(bbox, page=1, token_id="t"):
    return {"bbox": bbox, "page": page, "token_id": token_id, "text": "W12X19"}


def _geo(**kwargs):
    bbox = kwargs.get("bbox", [0, 0, 10, 10])
    obj = {
        "geometry_id": kwargs.get("geometry_id", "g"),
        "page_number": kwargs.get("page_number", 1),
        "kind": kwargs.get("kind", "line"),
        "bbox": bbox,
        "center": [
            (bbox[0] + bbox[2]) / 2.0,
            (bbox[1] + bbox[3]) / 2.0,
        ],
        "points": kwargs.get("points"),
        "centerline": kwargs.get("centerline"),
        "length": kwargs.get("length"),
        "orientation": kwargs.get("orientation", 0),
        "leader_endpoints": kwargs.get("leader_endpoints"),
    }
    return geometry_record_v2(obj)


class GiantVsLocalTests(unittest.TestCase):
    def test_giant_primitive_does_not_automatically_dominate_local_segment(self) -> None:
        label = _label([48, 48, 56, 54])
        giant = _geo(
            geometry_id="giant",
            kind="polyline",
            bbox=[0, 0, 800, 800],
            points=[[0, 0], [800, 0], [800, 800], [0, 800]],
            length=2400,
        )
        local = _geo(
            geometry_id="local",
            kind="line",
            bbox=[0, 50, 120, 52],
            points=[[0, 51], [120, 51]],
            length=120,
        )
        cands = retrieve_candidates_v2(label, [giant, local], top_k=5)
        ids = [c.get("parent_geometry_id") or c.get("geometry_id") for c in cands]
        self.assertIn("local", ids)
        self.assertTrue(cands)
        self.assertEqual(cands[0].get("parent_geometry_id") or cands[0].get("geometry_id"), "local")
        self.assertNotEqual(cands[0].get("parent_geometry_id"), "giant")

    def test_local_segment_can_be_retrieved_from_polyline(self) -> None:
        label = _label([95, 8, 105, 14])
        poly = _geo(
            geometry_id="poly",
            kind="polyline",
            bbox=[0, 0, 400, 20],
            points=[[0, 10], [80, 10], [160, 10], [400, 10]],
            length=400,
        )
        cands = retrieve_candidates_v2(label, [poly], top_k=5)
        self.assertTrue(cands)
        top = cands[0]
        self.assertEqual(top.get("parent_geometry_id"), "poly")
        self.assertTrue(
            top.get("derived")
            or top.get("retrieval_mechanism") in {"local_segment", "direct_segment"}
        )
        self.assertLessEqual(float(top.get("perpendicular_distance") or 999), 12.0)


class LeaderTests(unittest.TestCase):
    def test_leader_itself_is_not_returned_as_member(self) -> None:
        label = _label([0, 0, 10, 8])
        leader = _geo(
            geometry_id="lead",
            kind="leader",
            bbox=[8, 4, 80, 6],
            points=[[9, 5], [80, 5]],
            length=71,
            leader_endpoints={"near_endpoint": [9, 5], "far_endpoint": [80, 5]},
        )
        target = _geo(
            geometry_id="clip",
            kind="line",
            bbox=[78, 0, 92, 12],
            points=[[80, 0], [80, 12]],
            length=12,
        )
        cands = retrieve_candidates_v2(label, [leader, target], top_k=5)
        ids = [c.get("parent_geometry_id") or c.get("geometry_id") for c in cands]
        self.assertNotIn("lead", ids)
        for c in cands:
            self.assertNotEqual(c.get("extracted_kind"), "leader")
            self.assertNotEqual(c.get("geometry_kind"), "leader")

    def test_leader_target_can_become_candidate(self) -> None:
        label = _label([0, 0, 10, 8])
        leader = _geo(
            geometry_id="lead",
            kind="leader",
            bbox=[8, 4, 80, 6],
            points=[[9, 5], [80, 5]],
            length=71,
            leader_endpoints={"near_endpoint": [9, 5], "far_endpoint": [80, 5]},
        )
        target = _geo(
            geometry_id="clip",
            kind="rectangle",
            bbox=[76, 2, 88, 14],
            points=[[76, 2], [88, 2], [88, 14], [76, 14]],
            length=40,
        )
        cands = retrieve_candidates_v2(label, [leader, target], top_k=5)
        ids = [c.get("parent_geometry_id") or c.get("geometry_id") for c in cands]
        self.assertIn("clip", ids)
        hit = next(c for c in cands if (c.get("parent_geometry_id") or c.get("geometry_id")) == "clip")
        self.assertIn("leader_target", hit.get("candidate_generation_sources") or [])
        self.assertIsNotNone(hit.get("leader_evidence"))
        self.assertEqual(hit["leader_evidence"]["leader_geometry_id"], "lead")
        self.assertNotIn("lead", ids)


class SmallGeometryTests(unittest.TestCase):
    def test_small_geometry_remains_retrievable(self) -> None:
        label = _label([10, 10, 20, 16])
        small = _geo(
            geometry_id="angle",
            kind="line",
            bbox=[8, 18, 22, 20],
            points=[[8, 19], [22, 19]],
            length=14,
        )
        cands = retrieve_candidates_v2(label, [small], top_k=5)
        ids = [c.get("parent_geometry_id") or c.get("geometry_id") for c in cands]
        self.assertIn("angle", ids)


class SafetyTests(unittest.TestCase):
    def test_no_section_size_completion_occurs(self) -> None:
        src = (BACKEND / "scripts/rd_geometry_integration/retrieval_v2.py").read_text()
        self.assertNotIn("L4X4X", src)
        self.assertNotIn("primary_label", src)
        self.assertNotIn("takeoff_eligible", src)
        label = _label([0, 0, 10, 8])
        label["text"] = "L4X4"
        mem = _geo(
            geometry_id="m",
            kind="line",
            bbox=[0, 20, 80, 22],
            points=[[0, 21], [80, 21]],
            length=80,
        )
        cands = retrieve_candidates_v2(label, [mem], top_k=3)
        blob = json.dumps(cands)
        self.assertNotIn("L4X4X1/4", blob)
        self.assertNotIn("thickness", blob.lower())

    def test_no_production_module_imported(self) -> None:
        path = BACKEND / "scripts/rd_geometry_integration/retrieval_v2.py"
        tree = ast.parse(path.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0] if alias.name else "")
                    imported.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.add(node.module.split(".")[0])
        for forbidden in FORBIDDEN_IMPORTS:
            self.assertNotIn(forbidden, imported)
        self.assertTrue({"math", "typing"}.issubset(imported) or "math" in imported)

    def test_human_gold_file_unchanged_bytes(self) -> None:
        gold = REPO / "docs/validation/rd_geometry_integration/review_kit/gold_outcomes.jsonl"
        self.assertTrue(gold.exists(), gold)
        expected = hashlib.sha256(gold.read_bytes()).hexdigest()
        records = [json.loads(line) for line in gold.read_text().splitlines() if line.strip()]
        self.assertEqual(len(records), 75)
        associated = [r for r in records if r.get("decision") == "associated"]
        self.assertEqual(len(associated), 8)
        misses = [
            r
            for r in records
            if r.get("visible_member_on_drawing") and r.get("decision") == "no_valid_member"
        ]
        self.assertEqual(len(misses), 58)
        # retrieval_v2 must not be a writer of this path
        v2_src = (BACKEND / "scripts/rd_geometry_integration/retrieval_v2.py").read_text()
        run_src = (BACKEND / "scripts/rd_geometry_integration/run_retrieval_v2.py").read_text()
        self.assertNotIn("gold_outcomes.jsonl", v2_src)
        self.assertIn("Does not write gold_outcomes.jsonl", run_src)
        self.assertNotRegex(run_src, r"GOLD_PATH\.write")
        self.assertNotRegex(run_src, r"open\(GOLD_PATH,\s*[\"']w")
        self.assertEqual(hashlib.sha256(gold.read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
