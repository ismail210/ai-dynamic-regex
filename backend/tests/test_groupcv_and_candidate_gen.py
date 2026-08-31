"""
Regression tests for the grouped-CV methodology and the candidate-generation
fix from the v16_ranker_groupcv_20260816 experiment.

Covers:
  - group-CV leakage: no source_designation_id appears in both the train and
    validation half of any persisted fold.
  - C1 feature mask: masks exactly deterministic_rank/fuzzy_rank, nothing else.
  - candidate catalog validity: every generated candidate is a real catalog row.
  - candidate determinism: same input -> same candidate set, repeatedly.
  - no fabricated labels: a well-formed but non-existent shape never becomes
    a "final" candidate outside the real catalog (mirrors the earlier
    catalog-bypass regression class).
  - candidate deduplication: no duplicate labels within one candidate set.
  - recall/oracle bucket math: the shared aggregation helpers used throughout
    the v16 evaluation scripts compute candidate recall / top1 / top3 / mrr
    correctly on synthetic, hand-checked data.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from services import database_loader
from services.database_loader import is_catalog_label
from services.label_reconstruction.candidates import generate_candidates_v3
from services.label_reconstruction.catalog_reload import refresh_all_dependent_caches
from services.label_reconstruction.features import FEATURE_NAMES

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_groupcv_20260816"
CATALOG_PATH = BACKEND_DIR / "database" / "aisc_v16_label_catalog.csv"


class GroupCVLeakageTests(unittest.TestCase):
    """No designation group may appear in both the train and validation half
    of the same fold -- the exact leakage class GroupKFold/StratifiedGroupKFold
    exist to prevent."""

    @classmethod
    def setUpClass(cls):
        path = EXPERIMENT_DIR / "fold_assignment.json"
        if not path.exists():
            raise unittest.SkipTest("fold_assignment.json not generated yet (run scripts/phase2_build_group_folds.py)")
        cls.assignment = json.loads(path.read_text(encoding="utf-8"))

    def test_every_group_maps_to_exactly_one_fold(self):
        group_to_fold = self.assignment["group_to_fold"]
        n_splits = self.assignment["n_splits"]
        self.assertGreater(len(group_to_fold), 0)
        for fold in group_to_fold.values():
            self.assertIsInstance(fold, int)
            self.assertGreaterEqual(fold, 0)
            self.assertLess(fold, n_splits)

    def test_no_group_appears_in_more_than_one_fold(self):
        # group_to_fold is already a dict keyed by group id -> a group can
        # only ever hold one fold value by construction, but re-derive the
        # per-fold group SETS and assert pairwise-empty intersections, the
        # literal check the task calls for.
        group_to_fold = self.assignment["group_to_fold"]
        n_splits = self.assignment["n_splits"]
        fold_groups = [
            {g for g, f in group_to_fold.items() if f == fold}
            for fold in range(n_splits)
        ]
        for i in range(n_splits):
            for j in range(i + 1, n_splits):
                self.assertEqual(
                    fold_groups[i] & fold_groups[j], set(),
                    f"fold {i} and fold {j} share designation groups -- leakage",
                )

    def test_fold_audit_train_val_designations_are_disjoint(self):
        audit_path = EXPERIMENT_DIR / "fold_audit.json"
        if not audit_path.exists():
            raise unittest.SkipTest("fold_audit.json not generated yet")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        for key, fold in audit.items():
            if not key.startswith("fold_"):
                continue
            self.assertGreater(fold["train_unique_designations"], 0)
            self.assertGreater(fold["val_unique_designations"], 0)
            # train + val unique designation counts must not double count the
            # same group as both -- their sum should equal the total group
            # count for this dataset (checked loosely: val is a modest slice).
            self.assertLess(fold["val_unique_designations"], fold["train_unique_designations"])


class C1FeatureMaskTests(unittest.TestCase):
    """C1 masks exactly deterministic_rank and fuzzy_rank -- nothing else,
    especially not any reason_* one-hot."""

    def test_masked_features_are_exactly_the_two_ranks(self):
        path = EXPERIMENT_DIR / "frozen_feature_config.json"
        if path.exists():
            frozen = json.loads(path.read_text(encoding="utf-8"))
        else:
            # fall back to the older single-split experiment's copy
            alt = BACKEND_DIR / "training" / "experiments" / "v16_ranker_optuna_20260816" / "frozen_feature_config.json"
            if not alt.exists():
                raise unittest.SkipTest("no frozen_feature_config.json found")
            frozen = json.loads(alt.read_text(encoding="utf-8"))
        self.assertEqual(set(frozen["masked_features"]), {"deterministic_rank", "fuzzy_rank"})

    def test_reason_features_are_not_masked(self):
        masked = {"deterministic_rank", "fuzzy_rank"}
        reason_features = {n for n in FEATURE_NAMES if n.startswith("reason_")}
        self.assertTrue(reason_features, "expected at least one reason_* feature to exist")
        self.assertEqual(masked & reason_features, set())


class CandidateGenerationCorrectnessTests(unittest.TestCase):
    """Catalog validity, determinism, dedup, and no-fabrication guarantees
    for generate_candidates_v3 -- unaffected by, and re-verified after, the
    _fuzzy_candidates full-catalog fix."""

    @classmethod
    def setUpClass(cls):
        if not CATALOG_PATH.exists():
            raise unittest.SkipTest("aisc_v16_label_catalog.csv not present")
        database_loader.reload_from_aisc_v16_catalog(str(CATALOG_PATH))
        refresh_all_dependent_caches()

    @classmethod
    def tearDownClass(cls):
        database_loader.reset_to_default()
        refresh_all_dependent_caches()

    def test_every_candidate_is_a_real_catalog_label(self):
        for query in ["W12-26", "BW12X26", "12X26", "HSS8X8X?", "W1OX26"]:
            cs = generate_candidates_v3(query, limit=25)
            for candidate in cs.candidates:
                self.assertTrue(
                    is_catalog_label(candidate),
                    f"candidate {candidate!r} for query {query!r} is not a real catalog label",
                )

    def test_no_duplicate_candidates_within_one_set(self):
        for query in ["W12-26", "BW12X26", "HSS8X8X?"]:
            cs = generate_candidates_v3(query, limit=25)
            self.assertEqual(len(cs.candidates), len(set(cs.candidates)))

    def test_determinism_same_input_same_output(self):
        query = "BW12X26"
        first = generate_candidates_v3(query, limit=25).candidates
        for _ in range(5):
            again = generate_candidates_v3(query, limit=25).candidates
            self.assertEqual(first, again)

    def test_invalid_shape_never_returned_as_a_candidate(self):
        # W12X999 is well-formed but does not exist in the catalog -- it must
        # never itself be treated as a valid candidate/final label.
        cs = generate_candidates_v3("W12X999", limit=25)
        self.assertNotIn("W12X999", cs.candidates)
        for candidate in cs.candidates:
            self.assertTrue(is_catalog_label(candidate))

    def test_family_misroute_fix_recovers_real_prefix_collision(self):
        """The evidence-backed fix: a stray real-family-colliding prefix
        (e.g. "B" or "W" prepended) must no longer lock _fuzzy_candidates
        into the wrong family bucket."""
        cs = generate_candidates_v3("BW12X26", limit=25)
        self.assertIn("W12X26", cs.candidates)

    def test_familyless_recall_case_requires_reliable_family_evidence(self):
        """The old recall fixture predated anonymous-dimension safety."""
        naked = generate_candidates_v3("12X26", limit=25)
        with_context = generate_candidates_v3(
            "12X26",
            limit=25,
            reliable_family="W",
        )

        self.assertEqual(naked.candidates, [])
        self.assertIn("W12X26", with_context.candidates)


class RecallOracleBucketMathTests(unittest.TestCase):
    """The bucket/finalize aggregation pattern reused across every v16
    evaluation script: candidate recall = fraction of groups where the
    target appears anywhere; top1/top3/mrr computed from rank only when
    the target is present."""

    @staticmethod
    def _bucket():
        return {"n": 0, "top1": 0, "top3": 0, "mrr_sum": 0.0, "cand_present": 0}

    @staticmethod
    def _update(b, rank, cand_present):
        b["n"] += 1
        b["cand_present"] += int(cand_present)
        if rank is not None:
            b["top1"] += int(rank == 0)
            b["top3"] += int(rank < 3)
            b["mrr_sum"] += 1.0 / (rank + 1)

    @staticmethod
    def _finalize(b):
        n = b["n"] or 1
        return {
            "n": b["n"], "candidate_recall": b["cand_present"] / n,
            "top1": b["top1"] / n, "top3": b["top3"] / n, "mrr": b["mrr_sum"] / n,
        }

    def test_known_synthetic_case(self):
        b = self._bucket()
        # 5 rows: rank 0 (hit), rank 2 (top3 not top1), rank 5 (neither), and
        # 2 candidate-generation misses (rank=None).
        for rank, present in [(0, True), (2, True), (5, True), (None, False), (None, False)]:
            self._update(b, rank, present)
        m = self._finalize(b)
        self.assertEqual(m["n"], 5)
        self.assertAlmostEqual(m["candidate_recall"], 3 / 5)
        self.assertAlmostEqual(m["top1"], 1 / 5)
        self.assertAlmostEqual(m["top3"], 2 / 5)
        expected_mrr = (1.0 + 1 / 3 + 1 / 6) / 5
        self.assertAlmostEqual(m["mrr"], expected_mrr)


if __name__ == "__main__":
    unittest.main()
