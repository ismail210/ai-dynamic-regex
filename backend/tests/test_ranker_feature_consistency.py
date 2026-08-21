"""
Regression tests for the ranker train/serve feature-skew fix.

Pre-training audit finding: ``scripts/evaluate_v16_baselines.py``'s
``train_ranker()`` (and ``scripts/ablate_v16_ranker_features.py``'s
``build_matrix()``) built training features via
``pair_features(query, candidate, rank=row["deterministic_rank"])`` --
never passing ``reasons``/``fuzzy_rank``. Every training row therefore had
``fuzzy_rank`` fixed at its sentinel value and every ``reason_*`` one-hot
fixed at 0.0, so those columns had zero variance during fitting and the
model could not learn to use them -- while evaluation/inference *did* pass
real, varying values from a live ``generate_candidates_v3`` call, feeding
the fitted model combinations it had never seen vary.

Fix: both scripts now build every training AND evaluation feature row
through the single shared
``services.label_reconstruction.features.features_from_candidate_set``,
which derives ``rank``/``reasons``/``fuzzy_rank`` from one
``generate_candidates_v3`` call -- the same source both paths already used
for the candidate SET itself, just not (for training) for these columns.
"""

from __future__ import annotations

import unittest

from services.label_reconstruction.candidates import generate_candidates_v3
from services.label_reconstruction.features import (
    FEATURE_NAMES,
    features_from_candidate_set,
    pair_features,
)


class FeaturesFromCandidateSetTests(unittest.TestCase):
    def test_matches_manual_pair_features_call(self):
        """The shared helper must produce exactly what a caller who looked
        up rank/reasons/fuzzy_rank by hand would have gotten -- it is a
        convenience wrapper, not a different feature computation."""

        candidate_set = generate_candidates_v3("W12-26", limit=25)
        self.assertIn("W12X26", candidate_set.candidates)

        got = features_from_candidate_set("W12X26", candidate_set)
        rank = candidate_set.candidates.index("W12X26")
        expected = pair_features(
            candidate_set.normalized,
            "W12X26",
            rank=rank,
            reasons=candidate_set.generation_reasons.get("W12X26"),
            fuzzy_rank=candidate_set.fuzzy_ranks.get("W12X26"),
        )
        self.assertEqual(got, expected)

    def test_reason_and_fuzzy_rank_are_not_constant_across_candidates(self):
        """The whole point of the fix: reason_*/fuzzy_rank must actually
        vary within a single query's candidate group, not sit at one
        sentinel value for every row -- reproducing this against a live
        generate_candidates_v3() call is exactly what training now does."""

        # "W1OX26" (letter O for digit 0): the top candidate is resolved via
        # the OCR-flex path (reason_ocr_flex_positional), the rest via the
        # generic fuzzy-nearest-neighbor fallback -- a mix of reasons within
        # one query's group, exactly what training must be able to see vary.
        candidate_set = generate_candidates_v3("W1OX26", limit=25)
        rows = [
            features_from_candidate_set(c, candidate_set)
            for c in candidate_set.candidates
        ]
        self.assertGreater(len(rows), 1)

        fuzzy_ranks = {row["fuzzy_rank"] for row in rows}
        self.assertGreater(
            len(fuzzy_ranks), 1, "fuzzy_rank must vary across candidates, not be constant"
        )

        reason_columns = [name for name in FEATURE_NAMES if name.startswith("reason_")]
        # At least one reason_* column must be 1.0 for at least one row and
        # 0.0 for at least one other row -- i.e. not every reason column is
        # a constant 0.0 (or constant 1.0) across the whole group.
        varies = any(
            len({row[name] for row in rows}) > 1 for name in reason_columns
        )
        self.assertTrue(varies, "reason_* one-hots must vary across candidates")

    def test_candidate_not_in_generated_set_falls_back_to_sentinel(self):
        """A pairwise-dataset negative that isn't a member of today's fresh
        candidate set (e.g. a deliberately harder random negative) must
        degrade gracefully to the documented sentinel, not raise."""

        candidate_set = generate_candidates_v3("W12X26", limit=25)
        row = features_from_candidate_set("ZZZZ_NOT_A_REAL_CANDIDATE", candidate_set)
        self.assertEqual(row["deterministic_rank"], 25.0)
        self.assertEqual(row["fuzzy_rank"], 25.0)
        for name in FEATURE_NAMES:
            if name.startswith("reason_"):
                self.assertEqual(row[name], 0.0)


class TrainingScriptsUseSharedHelperTests(unittest.TestCase):
    """Static check that the two offline training scripts route through the
    shared helper rather than calling pair_features directly with an
    incomplete rank-only argument list -- guards against silently
    reintroducing the train/serve skew in either script."""

    def test_evaluate_v16_baselines_uses_shared_helper(self):
        import scripts.evaluate_v16_baselines as mod

        source = open(mod.__file__, encoding="utf-8").read()
        self.assertIn("features_from_candidate_set", source)
        self.assertNotIn("rank=row.get(\"deterministic_rank\")", source)

    def test_ablate_v16_ranker_features_uses_shared_helper(self):
        import scripts.ablate_v16_ranker_features as mod

        source = open(mod.__file__, encoding="utf-8").read()
        self.assertIn("features_from_candidate_set", source)
        self.assertNotIn("rank=row.get(\"deterministic_rank\")", source)


if __name__ == "__main__":
    unittest.main()
