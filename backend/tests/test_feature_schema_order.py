"""Regression tests for pair_features vs FEATURE_NAMES schema order."""

from __future__ import annotations

import unittest

from services.label_reconstruction.features import FEATURE_NAMES, pair_features


class FeatureSchemaOrderTests(unittest.TestCase):
    def test_pair_features_matches_feature_names_set_and_order(self) -> None:
        row = pair_features("W16X2?", "W16X26", rank=0, reasons=["wildcard_mask"])
        self.assertEqual(set(row), set(FEATURE_NAMES))
        self.assertEqual(list(row), FEATURE_NAMES)
        self.assertEqual(len(row), len(FEATURE_NAMES))

    def test_pair_features_is_deterministic(self) -> None:
        first = pair_features(
            "HSS8X8X?",
            "HSS8X8X1/2",
            rank=1,
            reasons=["structural_field_match"],
            fuzzy_rank=None,
        )
        second = pair_features(
            "HSS8X8X?",
            "HSS8X8X1/2",
            rank=1,
            reasons=["structural_field_match"],
            fuzzy_rank=None,
        )
        self.assertEqual(list(first), FEATURE_NAMES)
        self.assertEqual(first, second)
        self.assertEqual(list(first.values()), list(second.values()))


if __name__ == "__main__":
    unittest.main()
