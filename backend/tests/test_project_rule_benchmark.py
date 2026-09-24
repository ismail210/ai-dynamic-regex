"""Project-rule benchmark harness on the synthetic CI manifest.

Guards the Phase 1 safety gates and the honest baseline: every non-passing
item must be a declared ``expected_unsupported`` / ``expected_known_defect``,
never an unlabelled regression.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.helpers.script_loader import load_script_module

_MANIFEST = Path(__file__).resolve().parent / "fixtures" / "project_rules" / "synthetic_manifest.json"

bench = load_script_module("evaluate_project_rules.py", "evaluate_project_rules")


class ProjectRuleBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = bench.evaluate(bench.load_manifest(_MANIFEST))

    def _pipeline(self, name: str) -> dict:
        return self.report["pipelines"][name]

    def test_baseline_has_no_unlabelled_regressions(self) -> None:
        outcomes = self._pipeline("baseline")["outcomes"]
        self.assertNotIn("regression", outcomes["rows"])
        self.assertNotIn("regression", outcomes["regions"])

    def test_baseline_supported_schedule_cases(self) -> None:
        rows = {
            r["row_id"]: r
            for d in self._pipeline("baseline")["documents"]
            for r in d["rows"]
        }
        self.assertEqual(rows["A-L1"]["predicted_section"], "W8X21")
        self.assertTrue(rows["A-L1"]["roles_ok"])
        self.assertEqual(rows["A-C1"]["predicted_section"], "HSS6X6X1/2")
        self.assertIsNone(rows["A-L3"]["predicted_section"])
        self.assertIsNone(rows["C-RI1"]["predicted_section"])

    def test_baseline_limitations_are_declared(self) -> None:
        rows = {
            r["row_id"]: r
            for d in self._pipeline("baseline")["documents"]
            for r in d["rows"]
        }
        for row_id in ("B-LB1", "B-C1", "D-L1-p1"):
            self.assertEqual(rows[row_id]["outcome"], "expected_unsupported", row_id)
        # First-row-wins on a conflicting duplicate mark (pre-existing).
        self.assertEqual(rows["D-L1-p2"]["predicted_section"], "W8X21")

    def test_hard_safety_gates(self) -> None:
        for name, pipeline in self.report["pipelines"].items():
            safety = pipeline["safety"]
            with self.subTest(pipeline=name):
                self.assertEqual(safety["invalid_catalog_auto_accept"], 0)
                self.assertEqual(safety["schedule_rows_marked_countable"], 0)
                self.assertEqual(safety["fabricated_rows_on_vision_pages"], 0)
                self.assertEqual(safety["cross_project_leaks"], 0)

    def test_token_cases_semantic_lock(self) -> None:
        tokens = {t["case_id"]: t for t in self.report["token_cases"]}
        self.assertEqual(self.report["token_safety"]["semantic_lock_violations"], 0)
        for case in tokens.values():
            with self.subTest(case=case["case_id"]):
                self.assertIn(case["outcome"], {"pass", "expected_known_defect"})
        self.assertEqual(tokens["T01"]["section"], "W10X33")
        self.assertEqual(tokens["T04"]["section"], "W8X21")
        self.assertFalse(tokens["T13"]["auto_accepted"])

    def test_spaced_quantity_collapse_is_tracked(self) -> None:
        t12 = next(t for t in self.report["token_cases"] if t["case_id"] == "T12")
        # Known defect at 77f0ea0: "2 L4X4X1/2" auto-accepts as 2L4X4X1/2.
        # If this starts passing, flip the manifest's baseline marker.
        self.assertEqual(t12["outcome"], "expected_known_defect")
        self.assertTrue(t12["wrong_auto_accept"])

    def test_report_renders(self) -> None:
        text = bench.render_markdown(self.report)
        self.assertIn("Safety gates", text)


if __name__ == "__main__":
    unittest.main()
