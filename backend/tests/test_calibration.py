"""Confidence calibration tests (Phase 7)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from services.prediction import calibration


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        calibration.reset_cache()

    def tearDown(self):
        calibration.reset_cache()

    def test_no_dataset_returns_uncalibrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist.csv"

            class FakeSettings:
                approved_dataset_path = missing

            with patch("services.prediction.calibration.settings", FakeSettings):
                score, is_calibrated = calibration.calibrate_score(0.9)
        self.assertIsNone(score)
        self.assertFalse(is_calibrated)

    def test_dataset_without_required_columns_returns_uncalibrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "approved_dataset.csv"
            pd.DataFrame(
                [{"token": "W18X35", "class": "W", "category": "beam"}]
            ).to_csv(path, index=False)

            class FakeSettings:
                approved_dataset_path = path

            with patch("services.prediction.calibration.settings", FakeSettings):
                score, is_calibrated = calibration.calibrate_score(0.9)
        self.assertIsNone(score)
        self.assertFalse(is_calibrated)

    def test_insufficient_samples_returns_uncalibrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "approved_dataset.csv"
            pd.DataFrame(
                [
                    {"ranking_score": 0.9, "correct": 1},
                    {"ranking_score": 0.4, "correct": 0},
                ]
            ).to_csv(path, index=False)

            class FakeSettings:
                approved_dataset_path = path

            with patch("services.prediction.calibration.settings", FakeSettings):
                score, is_calibrated = calibration.calibrate_score(0.9)
        self.assertIsNone(score)
        self.assertFalse(is_calibrated)

    def test_enough_labeled_samples_fits_and_calibrates(self):
        rows = []
        for i in range(60):
            score = i / 59.0
            rows.append({"ranking_score": score, "correct": int(score > 0.5)})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "approved_dataset.csv"
            pd.DataFrame(rows).to_csv(path, index=False)

            class FakeSettings:
                approved_dataset_path = path

            with patch("services.prediction.calibration.settings", FakeSettings):
                score, is_calibrated = calibration.calibrate_score(0.95)
        self.assertTrue(is_calibrated)
        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
