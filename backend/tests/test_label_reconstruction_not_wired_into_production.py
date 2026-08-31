"""Structural guard: label_reconstruction must stay disconnected from the
live prediction pipeline *by direct import*, and both its feature flags must
default off.

Analyze reaches the package only through
``services.prediction.label_ranker_hook`` (indirection). Production modules
listed below must not contain the string ``label_reconstruction`` in source.

Mirrors test_ml_association_not_wired_into_production.py's pattern. The
shadow-mode design (Part P) requires that turning ML_LABEL_RANKER_SHADOW on
can only ever ADD a logged comparison, never change a returned prediction,
and that with both flags at their defaults, production behavior is
byte-for-byte unchanged by this package existing at all -- this test is what
would fail if a future change violated either property.
"""

from __future__ import annotations

import importlib
import inspect
import unittest

_PRODUCTION_MODULES = [
    "services.multimodal.pipeline",
    "services.prediction.orchestrator",
    "services.multimodal.fusion_engine",
    "services.multimodal.modular_fusion",
    "services.prediction.ranking",
    "services.prediction.canonical_contract",
    "services.staged_pipeline",
    "app",
    "routers.documents",
    "routers.analysis",
    "routers.engineering",
]


class ProductionPipelineDoesNotImportLabelReconstructionTests(unittest.TestCase):
    def test_no_production_module_references_label_reconstruction_in_source(self) -> None:
        offending = []
        for module_name in _PRODUCTION_MODULES:
            module = importlib.import_module(module_name)
            source = inspect.getsource(module)
            if "label_reconstruction" in source:
                offending.append(module_name)
        self.assertEqual(
            offending,
            [],
            f"label_reconstruction must not be referenced by production modules: {offending}",
        )

    def test_no_production_module_directly_references_label_reconstruction_attribute(self) -> None:
        for module_name in _PRODUCTION_MODULES:
            module = importlib.import_module(module_name)
            for attribute_name, value in vars(module).items():
                module_of_value = getattr(value, "__module__", "") or ""
                self.assertFalse(
                    module_of_value.startswith("services.label_reconstruction"),
                    f"{module_name}.{attribute_name} is bound to {module_of_value}",
                )


class FeatureFlagsDisabledByDefaultTests(unittest.TestCase):
    def test_settings_default_is_disabled(self) -> None:
        from config import settings

        self.assertFalse(settings.ml_label_ranker_enabled)
        self.assertFalse(settings.ml_label_ranker_shadow)

    def test_disabled_flags_never_touch_the_ranker_or_shadow_log(self) -> None:
        from config import settings
        from services.label_reconstruction import shadow

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        log_path = settings.ml_label_ranker_shadow_log_path
        existed_before = log_path.exists()
        size_before = log_path.stat().st_size if existed_before else None
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            result = shadow.reconstruct("W18X3?")
            self.assertIsNone(result.shadow)
            self.assertIsNone(result.model_version)
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)
        if existed_before:
            self.assertEqual(log_path.stat().st_size, size_before)
        else:
            self.assertFalse(log_path.exists())

    def test_selected_prediction_ignores_ranker_when_enabled_flag_is_off(self) -> None:
        # Shadow can run and log, but must never change selected_prediction
        # unless ML_LABEL_RANKER_ENABLED is explicitly true.
        from config import settings
        from services.label_reconstruction import shadow
        from services.label_reconstruction.candidates import generate_candidates

        original_enabled = settings.ml_label_ranker_enabled
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            result = shadow.reconstruct("W18X3?")
            deterministic = generate_candidates("W18X3?")
            expected = deterministic.candidates[0] if deterministic.candidates else None
            self.assertEqual(result.selected_prediction, expected)
            self.assertEqual(result.reason, "deterministic_top_candidate" if expected else "no_candidates")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)

    def test_shadow_true_enabled_false_does_not_mutate_selected_prediction(self) -> None:
        """ENABLED=false SHADOW=true: observe ranker pick without mutating selected."""
        import tempfile
        from pathlib import Path

        from config import settings
        from services.label_reconstruction import shadow
        from services.label_reconstruction.candidates import generate_candidates

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        original_log_path = settings.ml_label_ranker_shadow_log_path
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            with tempfile.TemporaryDirectory() as tmp_dir:
                object.__setattr__(
                    settings,
                    "ml_label_ranker_shadow_log_path",
                    Path(tmp_dir) / "shadow_log.jsonl",
                )
                result = shadow.reconstruct("W18X3?")
            deterministic = generate_candidates("W18X3?")
            expected = deterministic.candidates[0] if deterministic.candidates else None
            self.assertEqual(result.selected_prediction, expected)
            self.assertNotEqual(result.reason, "learned_ranker_top_candidate")
            self.assertEqual(
                result.reason,
                "deterministic_top_candidate" if expected else "no_candidates",
            )
            if result.shadow:
                self.assertIn("ml_prediction", result.shadow)
                # Observation may match or differ from the deterministic pick;
                # the invariant is that selected_prediction stays deterministic.
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)
            object.__setattr__(settings, "ml_label_ranker_shadow_log_path", original_log_path)


class ShadowScoresWithRawQueryTests(unittest.TestCase):
    """Regression test for a real bug found during v3 evaluation: shadow.py
    once scored the ranker with the NORMALIZED query, but every ranker is
    trained with pairwise "query" = raw_corrupted (pre-normalization) text
    -- scoring with the normalized string is an inference/training
    preprocessing mismatch that measurably changed accuracy (v2 top-1
    dropped from 0.7958 to 0.7680 in that mode on the frozen test set)."""

    def test_shadow_passes_raw_text_to_ranker_score_not_normalized(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from config import settings
        from services.label_reconstruction import shadow

        raw_with_case_and_space = "  w18 x3?  "  # normalizes to "W18X3?" -- not an exact catalog hit, so it reaches candidate generation + the ranker
        fake_ranker = MagicMock()
        fake_ranker.score.return_value = [1.0]
        fake_ranker.version_id = "fake"

        original_shadow = settings.ml_label_ranker_shadow
        original_log_path = settings.ml_label_ranker_shadow_log_path
        try:
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Never write to the real shadow log from a test -- redirect
                # to a throwaway path so running this test doesn't leave
                # fake "model_version": "fake" rows in a file a real shadow
                # deployment would otherwise treat as production log data.
                object.__setattr__(
                    settings, "ml_label_ranker_shadow_log_path", Path(tmp_dir) / "shadow_log.jsonl"
                )
                with patch(
                    "services.label_reconstruction.ranker.get_active_ranker",
                    return_value=fake_ranker,
                ):
                    shadow.reconstruct(raw_with_case_and_space)
        finally:
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)
            object.__setattr__(settings, "ml_label_ranker_shadow_log_path", original_log_path)

        self.assertTrue(fake_ranker.score.called)
        called_query = fake_ranker.score.call_args.args[0]
        self.assertEqual(called_query, raw_with_case_and_space)


if __name__ == "__main__":
    unittest.main()
