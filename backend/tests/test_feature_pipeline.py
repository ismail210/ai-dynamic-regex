from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

from services.dataset_builder import enrich_dataset
from services.feature_extractor import FEATURE_COLUMNS, extract_structural_features
from services.preprocessing_pipeline import build_preprocessing_pipeline
from services import training_service


class FeatureExtractorTests(unittest.TestCase):
    def test_structural_shape_features(self):
        hss = extract_structural_features("HSS8X8X1/2")
        self.assertEqual(hss["prefix"], "HSS")
        self.assertEqual(hss["shape_family"], "HSS")
        self.assertEqual(hss["x_count"], 2)
        self.assertEqual(hss["contains_fraction"], 1)
        self.assertEqual(hss["numeric_groups"], 4)

        company = extract_structural_features("Wide Flange W16X26 ASTM A992")
        self.assertEqual(company["shape_family"], "W")
        self.assertEqual(company["company_prefix"], "WIDE FLANGE")
        self.assertEqual(company["material_hint"], "A992")

    def test_rich_dataset_schema(self):
        source = pd.DataFrame(
            {
                "token": ["W16X26", "L6X6X3/4"],
                "class": ["W", "L"],
            }
        )
        enriched = enrich_dataset(source)
        self.assertEqual(
            enriched.columns.tolist(),
            ["token", "class", *FEATURE_COLUMNS[1:]],
        )
        self.assertEqual(enriched.loc[1, "contains_fraction"], 1)

    def test_preprocessor_accepts_raw_tokens(self):
        tokens = [
            "W16X26",
            "W18X35",
            "HSS8X8X1/2",
            "HSS6X6X3/8",
        ]
        pipeline = build_preprocessing_pipeline()
        transformed = pipeline.fit_transform(tokens)
        self.assertEqual(transformed.shape[0], len(tokens))
        self.assertGreater(transformed.shape[1], len(FEATURE_COLUMNS))


class TrainingArtifactTests(unittest.TestCase):
    def test_training_saves_complete_artifact_set(self):
        rows = []
        for index in range(12, 32):
            rows.extend(
                [
                    {"token": f"W{index}X{index + 10}", "class": "W"},
                    {"token": f"HSS{index}X{index}X1/2", "class": "HSS"},
                    {"token": f"L{index}X{index}X3/8", "class": "L"},
                ]
            )
        frame = pd.DataFrame(rows)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_settings = SimpleNamespace(
                training_dir=root,
                model_path=root / "best_model.pkl",
                preprocessing_pipeline_path=root / "preprocessing_pipeline.pkl",
                label_encoder_path=root / "label_encoder.pkl",
                feature_names_path=root / "feature_names.json",
                model_metadata_path=root / "model_metadata.json",
                legacy_model_meta_path=root / "model_meta.json",
                model_comparison_path=root / "model_comparison.csv",
            )
            candidates = {
                "SVM": LogisticRegression(max_iter=500, random_state=42)
            }
            with (
                patch.object(training_service, "settings", fake_settings),
                patch.object(
                    training_service,
                    "_candidate_estimators",
                    return_value=(candidates, {}),
                ),
            ):
                metadata = training_service.train_models(frame, actor="test")

            for name in (
                "best_model.pkl",
                "preprocessing_pipeline.pkl",
                "label_encoder.pkl",
                "feature_names.json",
                "model_metadata.json",
            ):
                self.assertTrue((root / name).exists(), name)

            preprocessing = joblib.load(root / "preprocessing_pipeline.pkl")
            model = joblib.load(root / "best_model.pkl")
            encoder = joblib.load(root / "label_encoder.pkl")
            prediction = model.predict(preprocessing.transform(["W20X30"]))
            self.assertIn(encoder.inverse_transform(prediction)[0], {"W", "HSS", "L"})
            self.assertEqual(metadata["schema_version"], 2)
            self.assertIn("classification_report", metadata["metrics"])

    def test_fast_retrain_uses_xgboost_only(self):
        rows = []
        for index in range(12, 32):
            rows.extend(
                [
                    {"token": f"W{index}X{index + 10}", "class": "W"},
                    {"token": f"HSS{index}X{index}X1/2", "class": "HSS"},
                    {"token": f"L{index}X{index}X3/8", "class": "L"},
                ]
            )
        progress = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_settings = SimpleNamespace(
                training_dir=root,
                model_path=root / "best_model.pkl",
                preprocessing_pipeline_path=root / "preprocessing_pipeline.pkl",
                label_encoder_path=root / "label_encoder.pkl",
                feature_names_path=root / "feature_names.json",
                model_metadata_path=root / "model_metadata.json",
                legacy_model_meta_path=root / "model_meta.json",
            )
            with patch.object(training_service, "settings", fake_settings):
                metadata = training_service.train_xgboost(
                    pd.DataFrame(rows),
                    actor="test",
                    progress_callback=lambda step, value: progress.append(
                        (step, value)
                    ),
                )

            self.assertEqual(metadata["model"], "XGBoost")
            self.assertEqual(metadata["training_mode"], "fast_retrain")
            self.assertEqual(metadata["model_comparison"], [])
            self.assertTrue((root / "preprocessing_pipeline.pkl").exists())
            self.assertGreaterEqual(progress[-1][1], 94)

    def test_training_subset_encoder_reports_only_classes_absent_from_fit(self):
        global_encoder = LabelEncoder().fit(["HSS", "L", "MC", "W", "WT"])
        selected_names = ["HSS", "L", "W", "WT", "W"]
        selected_ids = global_encoder.transform(selected_names)

        remapped, fit_encoder, excluded = (
            training_service._encoder_for_training_subset(
                selected_ids,
                global_encoder,
            )
        )

        self.assertEqual(list(fit_encoder.classes_), ["HSS", "L", "W", "WT"])
        self.assertEqual(excluded, ["MC"])
        self.assertEqual(set(remapped), set(range(len(fit_encoder.classes_))))

    def test_train_xgboost_cap_metadata_matches_actual_fitted_classes(self):
        """Capping metadata reflects selected rows, not assumed rare-class loss."""
        rows = []
        for index in range(20):
            rows.extend(
                [
                    {"token": f"W{index}X{index + 10}", "class": "W"},
                    {"token": f"HSS{index}X{index}X1/2", "class": "HSS"},
                    {"token": f"L{index}X{index}X3/8", "class": "L"},
                ]
            )
        # Rare class: whether it is excluded is determined by the actual cap,
        # not its frequency in the global dataset.
        rows.extend(
            {"token": f"MC{index}X{index + 1}", "class": "MC"}
            for index in range(2)
        )
        # New class that only appears in the bulk of the dataset.
        rows.extend(
            {"token": f"WT{index}X{index + 1}", "class": "WT"}
            for index in range(40)
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_settings = SimpleNamespace(
                training_dir=root,
                model_path=root / "best_model.pkl",
                preprocessing_pipeline_path=root / "preprocessing_pipeline.pkl",
                label_encoder_path=root / "label_encoder.pkl",
                feature_names_path=root / "feature_names.json",
                model_metadata_path=root / "model_metadata.json",
                legacy_model_meta_path=root / "model_meta.json",
            )
            with (
                patch.object(training_service, "settings", fake_settings),
                patch.object(training_service, "FINAL_TRAIN_CAP", 60),
            ):
                metadata = training_service.train_xgboost(
                    pd.DataFrame(rows),
                    actor="test",
                )

            fitted = set(metadata["class_labels"])
            excluded = set(metadata["excluded_training_classes"])
            global_classes = {"HSS", "L", "MC", "W", "WT"}

            self.assertEqual(fitted | excluded, global_classes)
            self.assertEqual(fitted & excluded, set())
            self.assertEqual(metadata["dataset_classes"], 5)
            self.assertEqual(metadata["classes"], len(fitted))
            saved_encoder = joblib.load(root / "label_encoder.pkl")
            self.assertEqual(
                list(saved_encoder.classes_),
                metadata["class_labels"],
            )
            self.assertTrue((root / "label_encoder.pkl").exists())


if __name__ == "__main__":
    unittest.main()
