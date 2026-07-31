"""Continuous-learning pipeline contracts, ingestion, versioning, and gates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.training_pipeline.augmentation import augment_text_train_split
from services.training_pipeline.continuous_learning import (
    load_state,
    record_approval_events,
    save_state,
)
from services.training_pipeline.dataset_builder import build_modality_dataset
from services.training_pipeline.dataset_registry import (
    load_dataset_samples,
    write_dataset_version,
)
from services.training_pipeline.hashing import content_hash, sample_id
from services.training_pipeline.model_registry import (
    get_active_model,
    promote_to_live_paths,
    register_candidate_model,
    should_promote as model_should_promote,
)
from services.training_pipeline.preprocessing import assign_split, preprocess_samples
from services.training_pipeline.source_ingestion import (
    dedupe_samples,
    ingest_corrections,
)


class HashingAndSplitTests(unittest.TestCase):
    def test_deterministic_ids_and_splits(self):
        first = sample_id(
            modality="text",
            source_type="approved_review",
            source_id="1",
            content="abc",
        )
        second = sample_id(
            modality="text",
            source_type="approved_review",
            source_id="1",
            content="abc",
        )
        self.assertEqual(first, second)
        self.assertEqual(assign_split(first), assign_split(second))
        self.assertEqual(
            content_hash(modality="text", payload={"token": "W18X35"}),
            content_hash(modality="text", payload={"token": "W18X35"}),
        )


class SourceIngestionTests(unittest.TestCase):
    def test_dedupe_by_provenance_and_hash(self):
        rows = [
            {
                "modality": "text",
                "content_hash": "h1",
                "provenance": {"source_type": "a", "source_id": "1"},
            },
            {
                "modality": "text",
                "content_hash": "h1",
                "provenance": {"source_type": "a", "source_id": "1"},
            },
            {
                "modality": "text",
                "content_hash": "h2",
                "provenance": {"source_type": "a", "source_id": "2"},
            },
        ]
        self.assertEqual(len(dedupe_samples(rows)), 2)

    def test_corrections_require_ready_for_training(self):
        with patch(
            "services.training_pipeline.source_ingestion.list_corrections",
            return_value=[
                {
                    "sample_id": "c1",
                    "ready_for_training": True,
                    "correct_label": "W18X35",
                    "prediction": {"original_token": "W18X3S"},
                    "input_features": {},
                    "timestamp": "2026-01-01T00:00:00Z",
                    "user_decision": "approve",
                },
                {
                    "sample_id": "c2",
                    "ready_for_training": False,
                    "correct_label": "HSS6X6X1/2",
                    "prediction": {"original_token": "HSS"},
                    "input_features": {},
                },
            ],
        ):
            rows = ingest_corrections()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "W18X35")
        self.assertTrue(rows[0]["supervised"])


class DatasetVersionTests(unittest.TestCase):
    def test_write_and_load_dataset_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "services.training_pipeline.dataset_registry.settings"
            ) as fake_settings:
                fake_settings.datasets_registry_dir = root
                fake_settings.dataset_schema_version = "1.0"
                samples = preprocess_samples(
                    [
                        {
                            "sample_id": "s1",
                            "modality": "text",
                            "content_hash": "h",
                            "token": "W18X35",
                            "label": "W18X35",
                            "family": "W",
                            "supervised": True,
                            "features": {},
                            "provenance": {"source_type": "approved_review", "source_id": "1"},
                            "metadata": {},
                        }
                    ]
                )
                manifest = write_dataset_version(
                    modality="text",
                    samples=samples,
                    source_counts={"approved_review": 1},
                    class_distribution={"W18X35": 1},
                    split_counts={"train": 1},
                    feature_schema=["token_len"],
                )
                loaded = load_dataset_samples("text", manifest.version_id)
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0]["token"], "W18X35")


class AugmentationIsolationTests(unittest.TestCase):
    def test_augmentation_only_on_train_split(self):
        samples = [
            {
                "sample_id": "train1",
                "modality": "text",
                "content_hash": "a",
                "token": "W18X35",
                "label": "W18X35",
                "family": "W",
                "supervised": True,
                "split": "train",
                "features": {},
                "provenance": {"source_type": "approved_review", "source_id": "t"},
                "metadata": {},
                "augmented": False,
            },
            {
                "sample_id": "val1",
                "modality": "text",
                "content_hash": "b",
                "token": "W21X44",
                "label": "W21X44",
                "family": "W",
                "supervised": True,
                "split": "validation",
                "features": {},
                "provenance": {"source_type": "approved_review", "source_id": "v"},
                "metadata": {},
                "augmented": False,
            },
        ]
        with patch(
            "services.training_pipeline.augmentation.settings"
        ) as fake_settings, patch(
            "services.training_pipeline.augmentation.generate_variants_for_token",
            return_value=["W18X35", "WF18X35", "W18×35"],
        ):
            fake_settings.augmentation_enabled = True
            fake_settings.augmentation_max_variants_per_token = 5
            output = augment_text_train_split(samples)
        val_children = [
            row for row in output if row.get("parent_sample_id") == "val1"
        ]
        train_children = [
            row for row in output if row.get("parent_sample_id") == "train1"
        ]
        self.assertEqual(val_children, [])
        self.assertGreater(len(train_children), 0)
        self.assertTrue(all(child["split"] == "train" for child in train_children))


class PromotionGateTests(unittest.TestCase):
    def test_regression_blocks_promotion(self):
        ok, reasons = model_should_promote(
            candidate_metrics={"accuracy": 0.70, "f1_weighted": 0.70},
            active_metrics={"accuracy": 0.90, "f1_weighted": 0.90},
        )
        self.assertFalse(ok)
        self.assertTrue(reasons)

    def test_first_model_promotes(self):
        ok, reasons = model_should_promote(
            candidate_metrics={"accuracy": 0.80, "f1_weighted": 0.80},
            active_metrics=None,
        )
        self.assertTrue(ok)
        self.assertEqual(reasons, [])


class ContinuousLearningStateTests(unittest.TestCase):
    def test_threshold_trigger_uses_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "continuous_learning_state.json"
            with patch(
                "services.training_pipeline.continuous_learning.settings"
            ) as fake_settings, patch(
                "services.training_pipeline.continuous_learning.maybe_trigger_continuous_learning",
                return_value={"triggered": False, "reason": "threshold_not_met"},
            ) as trigger:
                fake_settings.continuous_learning_state_path = state_path
                fake_settings.continuous_learning_threshold = 25
                fake_settings.continuous_learning_cooldown_seconds = 1
                save_state(
                    {
                        "pending_approved_count": 0,
                        "status": "idle",
                    }
                )
                record_approval_events(3)
                state = load_state()
                self.assertEqual(state["pending_approved_count"], 3)
                trigger.assert_called()


class ModelRegistryRollbackTests(unittest.TestCase):
    def test_register_and_promote_copies_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "best_model.pkl"
            artifact.write_text("model-bytes", encoding="utf-8")
            live = root / "live_best_model.pkl"
            with patch(
                "services.training_pipeline.model_registry.settings"
            ) as fake_settings:
                fake_settings.models_registry_dir = root / "models"
                fake_settings.model_schema_version = "1.0"
                fake_settings.model_path = live
                fake_settings.label_encoder_path = root / "label.pkl"
                fake_settings.preprocessing_pipeline_path = root / "prep.pkl"
                fake_settings.feature_names_path = root / "features.json"
                fake_settings.model_metadata_path = root / "meta.json"
                fake_settings.vectorizer_path = root / "vectorizer.pkl"
                manifest = register_candidate_model(
                    family="family_classifier",
                    artifact_paths={"model": artifact},
                    dataset_versions={"text": "text_v1"},
                    metrics={"accuracy": 0.9, "f1_weighted": 0.9},
                    promotion_status="candidate",
                )
                result = promote_to_live_paths(
                    "family_classifier", manifest.version_id
                )
                self.assertTrue(live.exists())
                self.assertEqual(result["promoted_to"], manifest.version_id)
                active = get_active_model("family_classifier")
                self.assertEqual(active["version_id"], manifest.version_id)


class ModalityDatasetBuildTests(unittest.TestCase):
    def test_build_text_modality_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "services.training_pipeline.dataset_registry.settings"
            ) as registry_settings, patch(
                "services.training_pipeline.dataset_builder.settings"
            ) as builder_settings, patch(
                "services.training_pipeline.augmentation.settings"
            ) as aug_settings, patch(
                "services.training_pipeline.augmentation.generate_variants_for_token",
                return_value=["W18X35"],
            ):
                registry_settings.datasets_registry_dir = root / "datasets"
                registry_settings.dataset_schema_version = "1.0"
                builder_settings.augmentation_enabled = False
                builder_settings.dataset_schema_version = "1.0"
                aug_settings.augmentation_enabled = False
                aug_settings.augmentation_max_variants_per_token = 2
                result = build_modality_dataset(
                    "text",
                    [
                        {
                            "sample_id": "s1",
                            "modality": "text",
                            "content_hash": "h",
                            "token": "W18X35",
                            "label": "W18X35",
                            "family": "W",
                            "supervised": True,
                            "features": {},
                            "provenance": {
                                "source_type": "approved_review",
                                "source_id": "1",
                            },
                            "metadata": {},
                        }
                    ],
                )
                self.assertGreaterEqual(result["sample_count"], 1)
                self.assertEqual(result["manifest"]["modality"], "text")


if __name__ == "__main__":
    unittest.main()
