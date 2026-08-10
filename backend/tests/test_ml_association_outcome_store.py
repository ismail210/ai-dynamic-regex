"""Categories 7, 8: append-only reviewed outcomes and supersession."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.ml_association import outcome_store
from services.ml_association.enums import AdjudicationStatus, CalloutScope, ReviewLabel
from services.ml_association.schemas import ReviewedOutcome


def _outcome(
    outcome_id: str,
    *,
    group_id: str = "group_1",
    reviewer_id: str = "alice",
    reviewed_at: str = "2026-01-01T00:00:00Z",
    targets=None,
    supersedes_outcome_id=None,
    adjudication_status: AdjudicationStatus = AdjudicationStatus.REVIEWED,
) -> ReviewedOutcome:
    return ReviewedOutcome(
        outcome_id=outcome_id,
        group_id=group_id,
        project_id="p1",
        document_id="d1",
        page_id="pg1",
        text_entity_id="t1",
        review_label=ReviewLabel.DIRECT_TARGET,
        reviewed_target_geometry_ids=targets or ["geo_1"],
        callout_scope=CalloutScope.SINGLE,
        adjudication_status=adjudication_status,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        supersedes_outcome_id=supersedes_outcome_id,
    )


class AppendOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "outcomes.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_append_and_read_back(self) -> None:
        outcome_store.append_outcome(_outcome("o1"), path=self.path)
        loaded = outcome_store.load_all_outcomes(self.path)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].outcome_id, "o1")

    def test_duplicate_outcome_id_is_rejected(self) -> None:
        outcome_store.append_outcome(_outcome("o1"), path=self.path)
        with self.assertRaises(outcome_store.DuplicateOutcomeError):
            outcome_store.append_outcome(_outcome("o1"), path=self.path)
        # The file must still contain exactly one line -- the rejected
        # write must never partially land.
        self.assertEqual(len(outcome_store.load_all_outcomes(self.path)), 1)

    def test_file_is_never_rewritten_in_place(self) -> None:
        outcome_store.append_outcome(_outcome("o1", targets=["geo_1"]), path=self.path)
        original_bytes = self.path.read_bytes()
        outcome_store.append_outcome(
            _outcome("o2", targets=["geo_2"], supersedes_outcome_id="o1"), path=self.path
        )
        new_bytes = self.path.read_bytes()
        self.assertTrue(new_bytes.startswith(original_bytes))

    def test_unknown_supersedes_target_is_rejected(self) -> None:
        with self.assertRaises(outcome_store.SupersedesTargetNotFoundError):
            outcome_store.append_outcome(
                _outcome("o1", supersedes_outcome_id="does_not_exist"), path=self.path
            )


class SupersessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "outcomes.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_correction_creates_a_new_outcome_not_a_mutation(self) -> None:
        outcome_store.append_outcome(_outcome("o1", targets=["geo_wrong"]), path=self.path)
        outcome_store.append_outcome(
            _outcome("o2", targets=["geo_right"], supersedes_outcome_id="o1"), path=self.path
        )
        history = outcome_store.history_for_group("group_1", self.path)
        self.assertEqual([o.outcome_id for o in history], ["o1", "o2"])
        # The original is untouched.
        self.assertEqual(history[0].reviewed_target_geometry_ids, ["geo_wrong"])

    def test_latest_outcomes_returns_the_supersession_head(self) -> None:
        outcome_store.append_outcome(_outcome("o1", targets=["geo_wrong"]), path=self.path)
        outcome_store.append_outcome(
            _outcome(
                "o2",
                targets=["geo_right"],
                reviewed_at="2026-01-02T00:00:00Z",
                supersedes_outcome_id="o1",
            ),
            path=self.path,
        )
        latest = outcome_store.latest_outcomes(self.path)
        self.assertEqual(latest["group_1"].outcome_id, "o2")
        self.assertEqual(latest["group_1"].reviewed_target_geometry_ids, ["geo_right"])

    def test_latest_outcomes_excludes_rejected_invalid(self) -> None:
        outcome_store.append_outcome(_outcome("o1"), path=self.path)
        outcome_store.append_outcome(
            _outcome(
                "o2",
                reviewed_at="2026-01-02T00:00:00Z",
                supersedes_outcome_id="o1",
                adjudication_status=AdjudicationStatus.REJECTED_INVALID,
            ),
            path=self.path,
        )
        latest = outcome_store.latest_outcomes(self.path)
        # o1 was superseded (excluded); o2 is rejected_invalid (also
        # excluded) -- no valid outcome remains for this group.
        self.assertNotIn("group_1", latest)

    def test_multiple_groups_are_independent(self) -> None:
        outcome_store.append_outcome(_outcome("o1", group_id="group_a"), path=self.path)
        outcome_store.append_outcome(_outcome("o2", group_id="group_b"), path=self.path)
        latest = outcome_store.latest_outcomes(self.path)
        self.assertEqual(set(latest.keys()), {"group_a", "group_b"})

    def test_supersession_chain_of_three_resolves_to_the_final_one(self) -> None:
        outcome_store.append_outcome(_outcome("o1", targets=["geo_a"]), path=self.path)
        outcome_store.append_outcome(
            _outcome(
                "o2", targets=["geo_b"], reviewed_at="2026-01-02T00:00:00Z", supersedes_outcome_id="o1"
            ),
            path=self.path,
        )
        outcome_store.append_outcome(
            _outcome(
                "o3", targets=["geo_c"], reviewed_at="2026-01-03T00:00:00Z", supersedes_outcome_id="o2"
            ),
            path=self.path,
        )
        latest = outcome_store.latest_outcomes(self.path)
        self.assertEqual(latest["group_1"].outcome_id, "o3")
        self.assertEqual(len(outcome_store.history_for_group("group_1", self.path)), 3)


if __name__ == "__main__":
    unittest.main()
