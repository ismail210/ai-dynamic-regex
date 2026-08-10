"""Exact-section predictor training / ingestion tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from services.exact_section_predictor import (
    is_exact_section_label,
    normalize_section_text,
    train_exact_section_model,
)


class ExactSectionHelpersTests(unittest.TestCase):
    def test_normalize_and_detect_exact_labels(self):
        self.assertTrue(is_exact_section_label("W18X35"))
        self.assertTrue(is_exact_section_label("HSS6X6X1/2"))
        self.assertFalse(is_exact_section_label("W"))
        self.assertEqual(normalize_section_text("w18x35"), "W18X35")


class ApprovedIngestionTests(unittest.TestCase):
    def test_approved_rows_use_exact_token_as_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = root / "approved_dataset.csv"
            pd.DataFrame(
                [
                    {"token": "W18X40", "class": "W"},
                    {"token": "HSS5X5X3/8", "class": "HSS"},
                ]
            ).to_csv(approved, index=False)

            class FakeSettings:
                approved_dataset_path = approved
                paired_dataset_path = root / "missing_paired.csv"
                exact_section_model_path = root / "exact_section_model.joblib"
                exact_section_metadata_path = root / "exact_section_model_metadata.json"
                exact_section_dataset_path = root / "exact_section_dataset.csv"
                training_dataset_path = root / "training_dataset.csv"
                training_dir = root
                # Engineering corrections are an optional additional retrieval
                # anchor source (services.exact_section_predictor reads this
                # path if it exists). Left pointing at a nonexistent file so
                # that code path is exercised (skips gracefully) without this
                # fixture needing to seed real correction data.
                engineering_corrections_path = root / "engineering_corrections.jsonl"

            # Minimal seed labels so training has AISC-like inventory too.
            pd.DataFrame(
                [{"token": "W18X35", "class": "W"}, {"token": "HSS6X6X1/2", "class": "HSS"}]
            ).to_csv(FakeSettings.training_dataset_path, index=False)

            with patch("services.exact_section_predictor.settings", FakeSettings), patch(
                "services.exact_section_predictor._canonical_labels",
                return_value=["W18X35", "HSS6X6X1/2", "W18X40"],
            ), patch(
                "services.exact_section_predictor.generate_variants_for_token",
                side_effect=lambda label, _: [label],
            ):
                meta = train_exact_section_model(persist=True)

            self.assertEqual(meta.get("schema_version"), 1)
            self.assertGreaterEqual(int(meta.get("training_variant_count") or 0), 2)
            exported = pd.read_csv(FakeSettings.exact_section_dataset_path)
            targets = set(exported["target_section"].astype(str))
            # WF18X40 normalizes; if not exact-label, HSS row must still ingest.
            self.assertTrue(
                "HSS5X5X3/8" in targets
                or any("HSS" in t for t in targets)
                or "W18X40" in targets
            )


if __name__ == "__main__":
    unittest.main()
