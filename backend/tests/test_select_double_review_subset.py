"""Regression tests for the deterministic double-review subset selector.

Synthetic rows only, shaped like batch_audit_rows.json entries -- never
touches the real, git-ignored pilot data.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "select_double_review_subset.py"
_spec = importlib.util.spec_from_file_location("select_double_review_subset", _MODULE_PATH)
selector = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = selector
_spec.loader.exec_module(selector)  # type: ignore[union-attr]


def _row(group_id, project_id, page_number, label, page_type, candidate_count=10, leader=False):
    return {
        "pilot_id": f"pilot_{project_id}",
        "project_id": project_id,
        "page_number": page_number,
        "group_id": group_id,
        "label_raw_text": label,
        "candidate_count": candidate_count,
        "has_leader_evidence": leader,
        "page_type": page_type,
    }


def _synthetic_rows():
    rows = []
    for i in range(20):
        rows.append(
            _row(
                f"group_{i:03d}",
                project_id=f"project_{i % 4}",
                page_number=(i // 4) + 1,
                label=f"W12X{i:02d}",
                page_type="structural framing plan #1",
                leader=(i % 3 == 0),
            )
        )
    # A few repeated-label-combo rows (same project/page/label appearing twice).
    rows.append(_row("group_rep_a", "project_0", 1, "REPEATED_LABEL", "repeated steel labels"))
    rows.append(_row("group_rep_b", "project_0", 1, "REPEATED_LABEL", "repeated steel labels"))
    return rows


class DoubleReviewSubsetTests(unittest.TestCase):
    def test_selection_is_deterministic_across_runs(self) -> None:
        rows = _synthetic_rows()
        result_a = selector.select_subset(rows)
        result_b = selector.select_subset(rows)
        self.assertEqual(
            [g["group_id"] for g in result_a["groups"]],
            [g["group_id"] for g in result_b["groups"]],
        )

    def test_selection_is_stable_under_input_row_order(self) -> None:
        rows = _synthetic_rows()
        reversed_rows = list(reversed(rows))
        result_a = selector.select_subset(rows)
        result_b = selector.select_subset(reversed_rows)
        self.assertEqual(
            {g["group_id"] for g in result_a["groups"]},
            {g["group_id"] for g in result_b["groups"]},
        )

    def test_repeated_combo_rows_are_always_selected(self) -> None:
        rows = _synthetic_rows()
        result = selector.select_subset(rows)
        selected_ids = {g["group_id"] for g in result["groups"]}
        self.assertIn("group_rep_a", selected_ids)
        self.assertIn("group_rep_b", selected_ids)

    def test_every_project_meets_the_minimum_floor(self) -> None:
        rows = _synthetic_rows()
        result = selector.select_subset(rows)
        for project_id, count in result["summary"]["by_project"].items():
            self.assertGreaterEqual(count, min(selector.MIN_PER_PROJECT, 5))

    def test_selected_fraction_is_at_least_20_percent(self) -> None:
        rows = _synthetic_rows()
        result = selector.select_subset(rows)
        self.assertGreaterEqual(result["summary"]["selected_fraction_percent"], 20.0)


if __name__ == "__main__":
    unittest.main()
