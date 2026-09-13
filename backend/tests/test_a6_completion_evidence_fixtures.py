"""Accuracy Track A6 — SOURCE_VERIFIED completion fixtures (policy only)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from services.prediction.label_ranker_hook import is_incomplete_angle_missing_thickness

FIX = (
    Path(__file__).resolve().parents[1]
    / "training/eval_cache_backups/accuracy_gold/a6_completion_evidence_fixtures.json"
)


class CompletionEvidenceFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(FIX.read_text(encoding="utf-8"))
        cls.by_id = {f["fixture_id"]: f for f in cls.doc["fixtures"]}

    def test_policy_flags(self):
        self.assertTrue(self.doc["policy"]["catalog_alone_never_completes"])
        self.assertFalse(self.doc["policy"]["incomplete_l_auto_complete_enabled"])

    def test_catalog_alone_abstains(self):
        fx = self.by_id["a6_catalog_alone_abstain"]
        self.assertTrue(is_incomplete_angle_missing_thickness(fx["raw_text"]))
        self.assertEqual(fx["expected_decision"], "abstain")

    def test_conflict_nearby_abstains(self):
        fx = self.by_id["a6_nearby_complete_conflict_abstain"]
        self.assertEqual(fx["expected_decision"], "abstain")
        self.assertGreaterEqual(len(fx["drawing_evidence"]), 2)

    def test_source_verified_not_auto_applied(self):
        fx = self.by_id["a6_legend_unique_source_verified"]
        self.assertEqual(fx["expected_decision"], "source_verified_candidate")
        self.assertFalse(fx.get("auto_apply"))
        self.assertEqual(fx["expected_completion_status"], "missing_thickness")

    def test_half_leg_complete(self):
        fx = self.by_id["a6_half_leg_already_complete"]
        self.assertFalse(is_incomplete_angle_missing_thickness(fx["raw_text"]))
        self.assertEqual(fx["expected_decision"], "no_completion_needed")


if __name__ == "__main__":
    unittest.main()
