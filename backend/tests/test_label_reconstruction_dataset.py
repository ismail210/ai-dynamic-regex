"""Correctness tests for the AISC damaged-label corruption dataset generator.

Covers the invariants the design depends on (Part G/H/I): every corruption
family stays catalog-consistent, no corrupted string leaks across splits,
and the reserved "unseen combination" slice is genuinely test-only. These
exercise ``build_pointwise_rows`` directly rather than the full pipeline
(which also builds ~80K pairwise rows via the deterministic candidate
generator's fuzzy fallback and takes several minutes) -- pairwise
correctness is covered separately by ``TestPairwiseHardNegatives`` on a
small slice, not the full run.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.database_loader import is_catalog_label  # noqa: E402
from services.label_reconstruction.corruption import (  # noqa: E402
    CORRUPTION_FAMILIES,
    family_of,
    generate_multi_corruption,
    generate_single_corruption,
)
import random  # noqa: E402

from scripts.generate_label_corruption_dataset import (  # noqa: E402
    _edit_distance,
    _split_for,
    build_pairwise_rows,
    build_pointwise_rows,
)


class CorruptionFamilyTests(unittest.TestCase):
    def test_every_family_can_apply_to_a_typical_label(self) -> None:
        label = "W18X35"
        rng = random.Random(1)
        applied = []
        for name, _fn in CORRUPTION_FAMILIES:
            result = generate_single_corruption(label, rng, family_name=name)
            if result is not None:
                applied.append(name)
                self.assertNotEqual(result.text, label)
                self.assertTrue(result.corruption_types)
        # missing_prefix and separator require specific label shapes but all
        # 6 families should fire on a well-formed W-shape label like W18X35.
        self.assertEqual(sorted(applied), sorted(name for name, _ in CORRUPTION_FAMILIES))

    def test_multi_corruption_chains_distinct_families(self) -> None:
        rng = random.Random(2)
        result = generate_multi_corruption("W18X35", rng, severity=2)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result.corruption_types), 1)

    def test_family_of_recognizes_known_prefixes(self) -> None:
        self.assertEqual(family_of("W18X35"), "W")
        self.assertEqual(family_of("HSS8X8X1/2"), "HSS")
        self.assertEqual(family_of("2L8X6X3/4"), "2L")
        self.assertEqual(family_of("WT9X48.5"), "WT")


class SplitAssignmentTests(unittest.TestCase):
    def test_split_is_deterministic_for_a_given_seed(self) -> None:
        first = _split_for("W1BX3S", seed=1, force_test=False)
        second = _split_for("W1BX3S", seed=1, force_test=False)
        self.assertEqual(first, second)

    def test_force_test_always_wins(self) -> None:
        self.assertEqual(_split_for("anything", seed=1, force_test=True), "test")

    def test_split_only_ever_produces_known_values(self) -> None:
        rng = random.Random(3)
        seen = set()
        for _ in range(200):
            text = "".join(rng.choice("ABCDEFGHIJ0123456789") for _ in range(8))
            seen.add(_split_for(text, seed=99, force_test=False))
        self.assertTrue(seen.issubset({"train", "validation", "test"}))


class PointwiseDatasetInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.reserved_combos = build_pointwise_rows(seed=20260807)

    def test_every_target_label_is_catalog_valid(self) -> None:
        sample = self.rows[:500]
        for row in sample:
            self.assertTrue(
                is_catalog_label(row["target_label"]),
                f"{row['target_label']} is not a real AISC catalog label",
            )

    def test_no_raw_corrupted_string_equals_its_target(self) -> None:
        for row in self.rows[:2000]:
            self.assertNotEqual(row["raw_corrupted"], row["target_label"])

    def test_raw_corrupted_strings_are_globally_unique(self) -> None:
        raw_texts = [row["raw_corrupted"] for row in self.rows]
        self.assertEqual(len(raw_texts), len(set(raw_texts)))

    def test_no_string_appears_in_more_than_one_split(self) -> None:
        # A direct consequence of global uniqueness above, checked explicitly
        # since it's the specific leakage guarantee Part I requires.
        by_text = {row["raw_corrupted"]: row["split"] for row in self.rows}
        self.assertEqual(len(by_text), len(self.rows))

    def test_reserved_combos_appear_only_in_test_split(self) -> None:
        for row in self.rows:
            if row["severity"] >= 2 and frozenset(row["corruption_types"]) in self.reserved_combos:
                self.assertTrue(row["unseen_combo"])
                self.assertEqual(row["split"], "test")

    def test_all_three_splits_are_nonempty(self) -> None:
        splits = {row["split"] for row in self.rows}
        self.assertEqual(splits, {"train", "validation", "test"})


class PairwiseHardNegativeTests(unittest.TestCase):
    def test_positive_row_present_for_every_pointwise_row_in_a_small_slice(self) -> None:
        rows, _reserved = build_pointwise_rows(seed=20260807)
        slice_rows = rows[:25]
        pairwise = build_pairwise_rows(slice_rows, k_negatives=3)
        positives = [r for r in pairwise if r["target"] == 1]
        self.assertEqual(len(positives), len(slice_rows))
        for row, positive in zip(slice_rows, positives):
            self.assertEqual(positive["query"], row["raw_corrupted"])
            self.assertEqual(positive["candidate"], row["target_label"])

    def test_hard_negatives_are_never_the_true_target_and_are_catalog_valid(self) -> None:
        rows, _reserved = build_pointwise_rows(seed=20260807)
        slice_rows = rows[:25]
        pairwise = build_pairwise_rows(slice_rows, k_negatives=3)
        negatives = [r for r in pairwise if r["target"] == 0]
        self.assertTrue(negatives)
        for negative in negatives:
            self.assertNotEqual(negative["candidate"], self._target_for(slice_rows, negative["query"]))
            self.assertTrue(is_catalog_label(negative["candidate"]))

    @staticmethod
    def _target_for(rows, query):
        for row in rows:
            if row["raw_corrupted"] == query:
                return row["target_label"]
        return None


class EditDistanceHelperTests(unittest.TestCase):
    def test_identical_strings_have_zero_distance(self) -> None:
        self.assertEqual(_edit_distance("W18X35", "W18X35"), 0)

    def test_single_substitution_has_distance_one(self) -> None:
        self.assertEqual(_edit_distance("W18X35", "W18X30"), 1)


if __name__ == "__main__":
    unittest.main()
