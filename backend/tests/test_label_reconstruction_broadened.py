"""Tests for the schema-v5 broadened-fallback ranking feature: the
``is_fallback_broadened`` context flag, the shared eligibility gate
(``candidates.is_broadened_fallback_query``), and ``shadow.reconstruct``'s
internal broadening + fail-safe ranker scoring.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.label_reconstruction.candidates import is_broadened_fallback_query
from services.label_reconstruction.corruption import corrupt_char_insertion
from services.label_reconstruction.features import FEATURE_NAMES, pair_features
from services.label_reconstruction.ranker import LabelRanker
from services.label_reconstruction.shadow import reconstruct


class BroadenedEligibilityTests(unittest.TestCase):
    """Section 15/24/25 of the broadened-ranker brief: only a genuinely
    length-changed, field-reliable-looking query is broadened."""

    def test_deletion_is_broadened(self):
        self.assertTrue(is_broadened_fallback_query("W10X3"))  # W10X33, trailing digit deleted

    def test_digit_duplicating_insertion_is_broadened(self):
        self.assertTrue(is_broadened_fallback_query("W122X26"))  # W12X26, digit duplicated

    def test_separator_duplicating_insertion_is_not_broadened(self):
        # Breaks the depth_weight regex outright -- already reachable via
        # the standard generator's own built-in fuzzy inclusion.
        self.assertFalse(is_broadened_fallback_query("W18XX40"))

    def test_clean_exact_label_is_not_broadened(self):
        self.assertFalse(is_broadened_fallback_query("W24X68"))

    def test_incomplete_angle_is_not_broadened(self):
        """L4X4 / 2L4X4 (legs printed, thickness unknown) are a COMPLETION
        concern, never treated as a length-changed catalog member to hunt
        for (Section 9/25's non-negotiable safety boundary)."""
        self.assertFalse(is_broadened_fallback_query("L4X4"))
        self.assertFalse(is_broadened_fallback_query("2L4X4"))

    def test_missing_thickness_hss_is_not_broadened(self):
        self.assertFalse(is_broadened_fallback_query("HSS8X8"))

    def test_round_hss_exact_is_not_broadened(self):
        self.assertFalse(is_broadened_fallback_query("HSS5.563X0.258"))

    def test_non_structural_note_is_not_broadened(self):
        self.assertFalse(is_broadened_fallback_query("1/22/2026"))
        self.assertFalse(is_broadened_fallback_query("35K"))


class CorruptCharInsertionTests(unittest.TestCase):
    def test_duplicates_a_digit_or_separator(self):
        import random

        rng = random.Random(42)
        result = corrupt_char_insertion("W8X10", rng)
        self.assertIsNotNone(result)
        self.assertEqual(len(result.text), len("W8X10") + 1)
        self.assertTrue(result.corruption_types[0].startswith("char_insertion_duplicate_"))

    def test_returns_none_for_no_digits_or_separator(self):
        import random

        self.assertIsNone(corrupt_char_insertion("", random.Random(1)))


class FeatureSchemaTests(unittest.TestCase):
    def test_is_fallback_broadened_defaults_to_zero(self):
        row = pair_features("W12X26", "W12X26")
        self.assertEqual(row["is_fallback_broadened"], 0.0)

    def test_is_fallback_broadened_settable(self):
        row = pair_features("W10X3", "W10X33", is_fallback_broadened=True)
        self.assertEqual(row["is_fallback_broadened"], 1.0)

    def test_feature_names_stable_and_includes_new_columns(self):
        self.assertIn("is_fallback_broadened", FEATURE_NAMES)
        self.assertIn("reason_fuzzy_fallback_broadened", FEATURE_NAMES)
        # Every pair_features() call must return exactly this key set, in
        # this order, regardless of which arguments were passed -- this is
        # what lets an OLDER model's shorter feature_names list safely index
        # into a row built by the CURRENT pair_features() (ranker.py's
        # backward-compatibility guarantee).
        row = pair_features("W10X3", "W10X33")
        self.assertEqual(list(row.keys()), FEATURE_NAMES)


class OlderModelBackwardCompatibilityTests(unittest.TestCase):
    """An older, already-promoted model's own `feature_names` (schema v4,
    no is_fallback_broadened) must keep scoring correctly against the
    CURRENT pair_features() -- the extra v5 columns are simply never
    referenced (Section 12: no silent mismatch, but also no unnecessary
    breakage of a model that predates the new columns)."""

    def test_old_schema_ranker_ignores_new_columns_without_error(self):
        old_schema = [n for n in FEATURE_NAMES if n not in ("is_fallback_broadened", "reason_fuzzy_fallback_broadened")]

        class _FakeBooster:
            def predict(self, matrix):
                import numpy as np

                return np.zeros(matrix.num_row())

        ranker = LabelRanker(_FakeBooster(), version_id="fake_old", feature_names=old_schema)
        self.assertFalse(ranker.supports_broadened_fallback)
        scores = ranker.score("W10X3", ["W10X30", "W10X33"], is_fallback_broadened=True)
        self.assertEqual(len(scores), 2)


class ReconstructFailSafeTests(unittest.TestCase):
    """Section 12/26: a ranker scoring error must degrade gracefully, never
    crash the semantic pipeline."""

    def test_ranker_exception_degrades_to_no_ranker_score(self):
        class _ExplodingRanker:
            version_id = "exploding"

            def score(self, *args, **kwargs):
                raise RuntimeError("simulated feature-schema mismatch")

        with patch("services.label_reconstruction.ranker.get_active_ranker", return_value=_ExplodingRanker()):
            result = reconstruct("W18X4O", force_shadow_score=True)
        self.assertIsNotNone(result.candidate_labels)
        self.assertGreater(len(result.candidate_labels), 0, "deterministic candidates must survive a ranker failure")
        self.assertIsNone(result.ranked_pairs, "a failed scoring attempt must not report ranked_pairs")

    def test_no_active_ranker_still_returns_deterministic_candidates(self):
        with patch("services.label_reconstruction.ranker.get_active_ranker", return_value=None):
            result = reconstruct("W18X4O", force_shadow_score=True)
        self.assertGreater(len(result.candidate_labels), 0)
        self.assertIsNone(result.ranked_pairs)


class NoOracleLeakageTests(unittest.TestCase):
    def test_broadened_ranking_modules_never_reference_the_attack_benchmark(self):
        import services.label_reconstruction.candidates as candidates_module
        import services.label_reconstruction.shadow as shadow_module

        for module in (candidates_module, shadow_module):
            with open(module.__file__, encoding="utf-8") as fh:
                contents = fh.read()
            self.assertNotIn("pdf_attack", contents)
            self.assertNotIn("estima3d_pdf_attack_benchmark", contents)
            self.assertNotIn("mutation_id", contents)


if __name__ == "__main__":
    unittest.main()
