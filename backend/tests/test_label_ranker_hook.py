"""Hook semantics: shadow-only never changes the live section."""

from __future__ import annotations

import unittest
from unittest import mock


def _fake_result(**kwargs):
    result = mock.Mock()
    result.selected_prediction = kwargs.get("selected_prediction", "W18X40")
    result.reason = kwargs.get("reason", "learned_ranker_top_candidate")
    result.model_version = kwargs.get("model_version", "test")
    result.shadow = kwargs.get("shadow")
    return result


class LabelRankerHookTests(unittest.TestCase):
    def test_noop_when_flags_off(self) -> None:
        from config import settings
        from services.prediction.label_ranker_hook import (
            apply_label_ranker_for_analyze,
        )

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            reconstruct = mock.Mock()
            meta = apply_label_ranker_for_analyze(
                raw_text="W18X3?",
                live_section="W18X35",
                reconstruct_fn=reconstruct,
            )
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertFalse(meta["invoked"])
        self.assertFalse(meta["applied"])
        reconstruct.assert_not_called()

    def test_shadow_only_does_not_apply(self) -> None:
        from config import settings
        from services.prediction.label_ranker_hook import (
            apply_label_ranker_for_analyze,
        )

        fake = _fake_result(
            shadow={"disagreement": True, "live_disagreement": True}
        )
        reconstruct = mock.Mock(return_value=fake)

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            meta = apply_label_ranker_for_analyze(
                raw_text="W18X3?",
                live_section="W18X35",
                reconstruct_fn=reconstruct,
            )
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertTrue(meta["invoked"])
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["selected_prediction"], "W18X40")
        reconstruct.assert_called_once()

    def test_shadow_exception_does_not_crash_and_leaves_section_untouched(self) -> None:
        """Phase 2B: an experimental-path exception must never propagate."""

        from config import settings
        from services.prediction.label_ranker_hook import (
            apply_label_ranker_for_analyze,
        )

        reconstruct = mock.Mock(side_effect=RuntimeError("xgboost blew up"))

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            meta = apply_label_ranker_for_analyze(
                raw_text="W18X3?",
                live_section="W18X35",
                reconstruct_fn=reconstruct,
            )
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertTrue(meta["invoked"])
        self.assertFalse(meta["applied"])
        self.assertEqual(meta["live_section"], "W18X35")
        self.assertEqual(meta["ranker_status"], "error")
        self.assertEqual(meta["error_type"], "RuntimeError")
        reconstruct.assert_called_once()

    def test_enabled_exception_falls_back_to_live_section(self) -> None:
        """Phase 2B: ENABLED must fall back to the deterministic/live
        baseline on ranker failure, not crash Analyze."""

        from config import settings
        from services.prediction.label_ranker_hook import (
            apply_label_ranker_for_analyze,
        )

        reconstruct = mock.Mock(side_effect=ValueError("bad candidate matrix"))

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            meta = apply_label_ranker_for_analyze(
                raw_text="W18X3?",
                live_section="W18X35",
                reconstruct_fn=reconstruct,
            )
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        # No exception propagated (pytest would have failed this test if it
        # had). applied stays False so the orchestrator keeps live_section.
        self.assertFalse(meta["applied"])
        self.assertIsNone(meta["selected_prediction"])
        self.assertEqual(meta["ranker_status"], "error")
        self.assertEqual(meta["error_type"], "ValueError")

    def test_ok_path_records_ranker_status(self) -> None:
        from config import settings
        from services.prediction.label_ranker_hook import (
            apply_label_ranker_for_analyze,
        )

        fake = _fake_result(shadow=None)
        reconstruct = mock.Mock(return_value=fake)

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            meta = apply_label_ranker_for_analyze(
                raw_text="W18X3?",
                live_section="W18X35",
                reconstruct_fn=reconstruct,
            )
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertEqual(meta["ranker_status"], "ok")
        self.assertIsNone(meta["error_type"])

    def test_enabled_applies_learned_pick(self) -> None:
        from config import settings
        from services.prediction.label_ranker_hook import (
            apply_label_ranker_for_analyze,
        )

        fake = _fake_result(shadow=None)
        reconstruct = mock.Mock(return_value=fake)

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            meta = apply_label_ranker_for_analyze(
                raw_text="W18X3?",
                live_section="W18X35",
                reconstruct_fn=reconstruct,
            )
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertTrue(meta["invoked"])
        self.assertTrue(meta["applied"])


if __name__ == "__main__":
    unittest.main()
