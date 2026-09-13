"""Validation-only tests for A2/A7 human-review workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "validation_reports" / "human_review"))

from hr_lib import (  # noqa: E402
    A2_GOLD,
    A2_REVIEW,
    A7_GOLD,
    A7_REVIEW,
    a2_is_reviewed,
    a7_is_reviewed,
    compute_a2_metrics,
    compute_a7_metrics,
    load_json,
    validate_a2_review_doc,
    validate_a7_review_doc,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class A2HumanReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = load_json(A2_GOLD)
        cls.review = load_json(A2_REVIEW)
        cls.gold_sha = _sha(A2_GOLD)

    def test_exactly_70_rows(self):
        self.assertEqual(len(self.review["rows"]), 70)
        self.assertEqual(self.review["count"], 70)

    def test_no_duplicate_review_ids(self):
        ids = [r["review_id"] for r in self.review["rows"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_original_87_gold_unchanged(self):
        self.assertEqual(self.gold["count"], 87)
        self.assertEqual(len(self.gold["rows"]), 87)
        self.assertEqual(self.review["source_gold_sha256"], self.gold_sha)
        unverified = [r for r in self.gold["rows"] if not r.get("human_verified")]
        self.assertEqual(len(unverified), 70)

    def test_unanswered_fields_remain_null(self):
        for row in self.review["rows"]:
            hr = row["human_review"]
            self.assertIsNone(hr["extraction_correct"])
            self.assertIsNone(hr["grouping_correct"])
            self.assertIsNone(hr["operation_correct"])
            self.assertIsNone(hr["expected_normalized_value"])
            self.assertIsNone(hr["should_abstain"])
            self.assertIsNone(hr["verdict"])
            self.assertIsNone(hr["reason_code"])
            self.assertIsNone(hr["reviewed_at"])

    def test_invalid_enum_rejected(self):
        bad = copy.deepcopy(self.review)
        bad["rows"][0]["human_review"]["verdict"] = "TOTALLY_WRONG"
        errors = validate_a2_review_doc(bad, gold=self.gold)
        self.assertTrue(any("invalid_verdict" in e for e in errors))

    def test_zero_reviewed_returns_na_not_fake_zero(self):
        metrics = compute_a2_metrics(self.review)
        self.assertEqual(metrics["reviewed"], 0)
        self.assertEqual(metrics["extraction"]["yes_rate"], "N/A — no reviewed samples")
        self.assertIn("not yet measured", metrics["note"])

    def test_partial_review_uses_reviewed_denominator(self):
        doc = copy.deepcopy(self.review)
        doc["rows"][0]["human_review"].update(
            {
                "extraction_correct": "YES",
                "grouping_correct": "NOT_APPLICABLE",
                "operation_correct": "YES",
                "should_abstain": "NO",
                "verdict": "ACCEPT",
                "reason_code": "correct",
            }
        )
        doc["rows"][1]["human_review"].update(
            {
                "extraction_correct": "NO",
                "grouping_correct": "NO",
                "operation_correct": "AMBIGUOUS",
                "should_abstain": "YES",
                "verdict": "ABSTAIN",
                "reason_code": "should_abstain",
            }
        )
        metrics = compute_a2_metrics(doc)
        self.assertEqual(metrics["reviewed"], 2)
        self.assertEqual(metrics["extraction"]["n"], 2)
        self.assertEqual(metrics["extraction"]["yes_rate"], 0.5)
        self.assertEqual(metrics["extraction"]["no_rate"], 0.5)

    def test_reload_roundtrip_70(self):
        again = load_json(A2_REVIEW)
        self.assertEqual(len(again["rows"]), 70)
        self.assertEqual(
            [r["review_id"] for r in again["rows"]],
            [r["review_id"] for r in self.review["rows"]],
        )


class A7HumanReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = load_json(A7_GOLD)
        cls.review = load_json(A7_REVIEW)
        cls.gold_sha = _sha(A7_GOLD)

    def test_exactly_100_links(self):
        self.assertEqual(len(self.review["links"]), 100)
        self.assertEqual(self.review["count"], 100)

    def test_no_duplicate_review_ids(self):
        ids = [r["review_id"] for r in self.review["links"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_original_a7_unchanged(self):
        self.assertEqual(self.gold["count"], 100)
        self.assertEqual(self.review["source_gold_sha256"], self.gold_sha)
        self.assertEqual(sum(1 for L in self.gold["links"] if L.get("human_verified")), 0)

    def test_verdicts_accepted(self):
        doc = copy.deepcopy(self.review)
        doc["links"][0]["human_review"]["verdict"] = "CORRECT"
        doc["links"][1]["human_review"]["verdict"] = "WRONG"
        doc["links"][2]["human_review"]["verdict"] = "AMBIGUOUS"
        self.assertEqual(validate_a7_review_doc(doc, gold=self.gold), [])

    def test_invalid_verdict_rejected(self):
        doc = copy.deepcopy(self.review)
        doc["links"][0]["human_review"]["verdict"] = "MAYBE"
        errors = validate_a7_review_doc(doc, gold=self.gold)
        self.assertTrue(any("invalid_verdict" in e for e in errors))

    def test_zero_reviewed_precision_na(self):
        metrics = compute_a7_metrics(self.review)
        self.assertEqual(metrics["reviewed"], 0)
        self.assertEqual(metrics["precision_excluding_ambiguous"], "N/A — no reviewed samples")
        self.assertIn("not yet measured", metrics["note"])

    def test_precision_excludes_ambiguous(self):
        doc = copy.deepcopy(self.review)
        doc["links"][0]["human_review"]["verdict"] = "CORRECT"
        doc["links"][1]["human_review"]["verdict"] = "WRONG"
        doc["links"][2]["human_review"]["verdict"] = "AMBIGUOUS"
        metrics = compute_a7_metrics(doc)
        self.assertEqual(metrics["reviewed"], 3)
        self.assertEqual(metrics["precision_excluding_ambiguous"], 0.5)
        self.assertEqual(metrics["ambiguous_rate"], round(1 / 3, 4))

    def test_method_breakdown_totals(self):
        doc = copy.deepcopy(self.review)
        # mark one of each method
        by_method = {}
        for link in doc["links"]:
            m = link["association_method"]
            if m not in by_method:
                by_method[m] = link
        for i, (m, link) in enumerate(by_method.items()):
            link["human_review"]["verdict"] = ["CORRECT", "WRONG", "AMBIGUOUS"][i % 3]
        metrics = compute_a7_metrics(doc)
        total_rev = sum(v["n_reviewed"] for v in metrics["by_method"].values())
        self.assertEqual(total_rev, metrics["reviewed"])
        self.assertEqual(total_rev, len(by_method))


if __name__ == "__main__":
    unittest.main()
