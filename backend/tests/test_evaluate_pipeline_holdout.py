"""
Regression tests for the P0-2 holdout-evaluation bug (accuracy sprint Phase 1B).

``evaluate_pipeline.py::section_prediction_performance`` used to build a
leakage-free shadow exact-section model (excluding holdout/test tokens), then
immediately call ``reload_exact_section_artifact()`` — which discarded that
in-memory shadow model *before* any prediction was scored, silently falling
back to the full, on-disk production artifact for every holdout prediction.

These tests assert the fixed ordering directly: the shadow model must be
built and used for every scored prediction, and the production artifact may
only be restored (via ``reload_exact_section_artifact``) after scoring is
complete — i.e. ``model_used_for_evaluation == model_fitted_on_allowed_training_partition``.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = BACKEND_DIR / "scripts" / "evaluate_pipeline.py"


def _load_evaluate_pipeline_module():
    spec = importlib.util.spec_from_file_location(
        "test_evaluate_pipeline_module", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evaluate_pipeline = _load_evaluate_pipeline_module()


def _fake_approved_frame() -> pd.DataFrame:
    # A handful of rows; assign_split is a deterministic hash, so which rows
    # land in "test" is stable for the same unknown_id/token — we don't need
    # to control it precisely, only observe call ordering and which tokens
    # actually get predicted.
    return pd.DataFrame(
        [
            {"token": "W16X26", "class": "W16X26", "category": "", "source": "x", "approved_at": "", "unknown_id": "u1"},
            {"token": "W18X35", "class": "W18X35", "category": "", "source": "x", "approved_at": "", "unknown_id": "u2"},
            {"token": "HSS8X8X1/2", "class": "HSS8X8X1/2", "category": "", "source": "x", "approved_at": "", "unknown_id": "u3"},
            {"token": "C10X20", "class": "C10X20", "category": "", "source": "x", "approved_at": "", "unknown_id": "u4"},
            {"token": "L4X4X3/8", "class": "L4X4X3/8", "category": "", "source": "x", "approved_at": "", "unknown_id": "u5"},
            {"token": "MC12X35", "class": "MC12X35", "category": "", "source": "x", "approved_at": "", "unknown_id": "u6"},
            {"token": "WT7X15", "class": "WT7X15", "category": "", "source": "x", "approved_at": "", "unknown_id": "u7"},
            {"token": "ST6X15.9", "class": "ST6X15.9", "category": "", "source": "x", "approved_at": "", "unknown_id": "u8"},
        ]
    )


class HoldoutOrderingTests(unittest.TestCase):
    """Directly reproduces the discard-before-score bug via call ordering."""

    def test_shadow_model_is_built_and_used_before_reload(self):
        call_order: list[str] = []

        def fake_train_exact_section_model(*, persist, exclude_tokens, exclude_split):
            call_order.append("train_shadow")
            return {
                "trained_at": "2026-08-11T00:00:00Z",
                "schema_version": 1,
                "model": "character_tfidf_cosine_retrieval",
                "exact_label_count": 2299,
                "training_variant_count": 100,
            }

        def fake_reload_exact_section_artifact():
            call_order.append("reload_production")

        def fake_predict_token(token, *, queue_unknown, persist_learning):
            call_order.append(f"predict:{token}")
            return {
                "section": token,
                "family": "W",
                "review_status": "auto_accepted",
                "canonical_candidates": [],
            }

        with patch.object(
            evaluate_pipeline.dataset_manager,
            "load_approved_dataset",
            return_value=_fake_approved_frame(),
        ), patch(
            "services.exact_section_predictor.train_exact_section_model",
            side_effect=fake_train_exact_section_model,
        ), patch(
            "services.exact_section_predictor.reload_exact_section_artifact",
            side_effect=fake_reload_exact_section_artifact,
        ), patch.object(
            evaluate_pipeline, "predict_token", side_effect=fake_predict_token
        ):
            result = evaluate_pipeline.section_prediction_performance()

        self.assertIsInstance(result, tuple)
        performance, evaluated = result
        self.assertEqual(performance["status"], "ok")

        # The bug: reload_production happened before any predict_token call,
        # meaning every prediction scored against the production (leaked)
        # artifact instead of the shadow one. The fix requires the opposite
        # order: train_shadow, then every predict:* call, then (only at the
        # very end) reload_production.
        self.assertIn("train_shadow", call_order)
        self.assertIn("reload_production", call_order)
        predict_calls = [c for c in call_order if c.startswith("predict:")]
        self.assertTrue(predict_calls, "expected at least one holdout prediction")

        train_index = call_order.index("train_shadow")
        reload_index = call_order.index("reload_production")
        last_predict_index = max(call_order.index(c) for c in predict_calls)

        self.assertLess(
            train_index,
            last_predict_index,
            "shadow model must be built before any holdout prediction is scored",
        )
        self.assertGreater(
            reload_index,
            last_predict_index,
            "production artifact must only be restored AFTER scoring — "
            "restoring it earlier (the original bug) means every holdout "
            "prediction used the full, leaked production model instead of "
            "the leakage-free shadow model",
        )

    def test_reproducibility_manifest_is_recorded(self):
        def fake_train_exact_section_model(*, persist, exclude_tokens, exclude_split):
            return {
                "trained_at": "2026-08-11T00:00:00Z",
                "schema_version": 1,
                "model": "character_tfidf_cosine_retrieval",
                "exact_label_count": 2299,
                "training_variant_count": 100,
            }

        def fake_predict_token(token, *, queue_unknown, persist_learning):
            return {
                "section": token,
                "family": "W",
                "review_status": "auto_accepted",
                "canonical_candidates": [],
            }

        with patch.object(
            evaluate_pipeline.dataset_manager,
            "load_approved_dataset",
            return_value=_fake_approved_frame(),
        ), patch(
            "services.exact_section_predictor.train_exact_section_model",
            side_effect=fake_train_exact_section_model,
        ), patch(
            "services.exact_section_predictor.reload_exact_section_artifact",
        ), patch.object(
            evaluate_pipeline, "predict_token", side_effect=fake_predict_token
        ):
            performance, _ = evaluate_pipeline.section_prediction_performance()

        manifest = performance.get("reproducibility")
        self.assertIsNotNone(manifest)
        self.assertIn("dataset_version", manifest)
        self.assertIn("split_manifest", manifest)
        self.assertIn("model_artifact", manifest)
        self.assertFalse(manifest["project_level_split"])
        self.assertIn("no project/document identifier", manifest["project_level_split_note"])
        self.assertEqual(
            manifest["model_artifact"]["used_for_scoring"], "in-memory shadow (persist=False)"
        )


if __name__ == "__main__":
    unittest.main()
