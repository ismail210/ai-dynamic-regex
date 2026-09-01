"""Post-ranking gate: XGB must not override reliable engineering fields."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import settings
from services.label_reconstruction.candidates import (
    candidate_respects_reliable_query_fields,
    generate_candidates,
    ineligible_for_section_reconstruction,
)
from services.label_reconstruction.shadow import reconstruct
from services.prediction.label_ranker_hook import apply_label_ranker_for_analyze


def _ranker_preferring(preferred: str) -> MagicMock:
    ranker = MagicMock()
    ranker.version_id = "fake-field-gate"

    def score(query, candidates, **kwargs):
        return [2.0 if label == preferred else 0.1 for label in candidates]

    ranker.score.side_effect = score
    return ranker


class ReliableFieldAcceptanceTests(unittest.TestCase):
    def test_length_suffix_still_protects_angle_thickness(self) -> None:
        query = "L3X3X3/8X0'-6\""
        self.assertFalse(
            candidate_respects_reliable_query_fields(
                "L3X3X3/8X0'-6\"", "L3X3X3/16"
            )
        )
        self.assertTrue(
            candidate_respects_reliable_query_fields(
                "L3X3X3/8X0'-6\"", "L3X3X3/8"
            )
        )
        self.assertIn("L3X3X3/16", generate_candidates(query).candidates)
        self.assertIn("L3X3X3/8", generate_candidates(query).candidates)

    def test_length_suffix_still_protects_angle_legs(self) -> None:
        self.assertFalse(
            candidate_respects_reliable_query_fields(
                "L4X3X3/8X0'-6\"", "L3X3X3/8"
            )
        )
        self.assertTrue(
            candidate_respects_reliable_query_fields(
                "L4X3X3/8X0'-6\"", "L4X3X3/8"
            )
        )


class RankerCannotOverrideReliableFieldsTests(unittest.TestCase):
    def test_l3x3x3_8_cannot_become_3_16(self) -> None:
        result = reconstruct("L3X3X3/8")
        self.assertEqual(result.reason, "exact_match")
        self.assertEqual(result.selected_prediction, "L3X3X3/8")
        self.assertNotEqual(result.selected_prediction, "L3X3X3/16")

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker",
                return_value=_ranker_preferring("L3X3X3/16"),
            ):
                gated = reconstruct("L3X3X3/8X0'-6\"")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertEqual(gated.selected_prediction, "L3X3X3/8")
        self.assertNotEqual(gated.selected_prediction, "L3X3X3/16")

    def test_l4x3x3_8_cannot_become_l3x3x3_8(self) -> None:
        result = reconstruct("L4X3X3/8")
        self.assertEqual(result.reason, "exact_match")
        self.assertEqual(result.selected_prediction, "L4X3X3/8")
        self.assertNotEqual(result.selected_prediction, "L3X3X3/8")

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker",
                return_value=_ranker_preferring("L3X3X3/8"),
            ):
                gated = reconstruct("L4X3X3/8X0'-6\"")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertEqual(gated.selected_prediction, "L4X3X3/8")
        self.assertNotEqual(gated.selected_prediction, "L3X3X3/8")

    def test_l6x4x1_4_cannot_become_l4x4x1_4(self) -> None:
        query = 'L6x4x1/4x4"'
        self.assertFalse(
            candidate_respects_reliable_query_fields("L6X4X1/4X4\"", "L4X4X1/4")
        )
        self.assertTrue(
            candidate_respects_reliable_query_fields("L6X4X1/4X4\"", "L6X4X1/4")
        )
        for label in generate_candidates(query).candidates:
            if candidate_respects_reliable_query_fields("L6X4X1/4X4\"", label):
                self.assertTrue(label.startswith("L6X4X1/4"))

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker",
                return_value=_ranker_preferring("L4X4X1/4"),
            ):
                gated = reconstruct(query)
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertNotEqual(gated.selected_prediction, "L4X4X1/4")
        if gated.selected_prediction:
            self.assertTrue(gated.selected_prediction.startswith("L6X4X1/4"))
            self.assertTrue(
                candidate_respects_reliable_query_fields(
                    "L6X4X1/4X4\"", gated.selected_prediction
                )
            )

    def test_compatible_xgb_candidate_is_still_allowed(self) -> None:
        candidates = generate_candidates("HSS8X8X?").candidates
        self.assertGreater(len(candidates), 1)
        preferred = candidates[-1]
        self.assertTrue(preferred.startswith("HSS8X8X"))
        self.assertNotEqual(preferred, candidates[0])

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker",
                return_value=_ranker_preferring(preferred),
            ):
                result = reconstruct("HSS8X8X?")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertEqual(result.selected_prediction, preferred)
        self.assertEqual(result.reason, "learned_ranker_top_candidate")

    def test_xgb_may_reorder_when_no_reliable_conflicting_field(self) -> None:
        candidates = generate_candidates("W??X?7").candidates
        self.assertGreater(len(candidates), 1)
        self.assertTrue(all(not label.startswith("WT") for label in candidates))
        preferred = candidates[-1]
        self.assertNotEqual(preferred, candidates[0])

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker",
                return_value=_ranker_preferring(preferred),
            ):
                result = reconstruct("W??X?7")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

        self.assertEqual(result.selected_prediction, preferred)
        self.assertFalse(result.selected_prediction.startswith("WT"))


class ExistingSafetyInvariantsTests(unittest.TestCase):
    def test_hss_missing_thickness_still_abstains(self) -> None:
        for raw in ("HSS8X8", "HSS8x8", "HSS10X10"):
            with self.subTest(raw=raw):
                result = reconstruct(raw)
                self.assertIsNone(result.selected_prediction)
                self.assertEqual(result.reason, "no_candidates")

    def test_hss6x8x1_2_does_not_become_hss16(self) -> None:
        result = reconstruct("HSS6X8X1/2")
        self.assertIsNone(result.selected_prediction)
        self.assertNotEqual(result.selected_prediction, "HSS16X8X1/2")

    def test_hss8x8x_question_stays_in_family(self) -> None:
        for label in generate_candidates("HSS8X8X?").candidates:
            self.assertTrue(label.startswith("HSS8X8X"))

    def test_w_queries_do_not_emit_wt(self) -> None:
        for label in generate_candidates("W??X?7").candidates:
            self.assertFalse(label.startswith("WT"))

    def test_anonymous_dimensions_blocked_before_ranker(self) -> None:
        queries = (
            '2"x4"x1/4"',
            '2"x2"x1/4"',
            '1/2"x1/4"',
            '1/4"x2"',
            '1/2"⌀x6"',
            '1/8"x1"',
            "4x4",
            "3/4X4X6",
            '1/4"',
            '1-1/2"',
            '14-2".',
            '1/2"x5/16"ANGLE',
            '1-1/2",',
            '1-1/4"Ø',
            'x12"',
            '(14"x52")',
            '(20"x52")',
            '(24"x30")',
            '(L52"x52"x14"T)',
            "6x6-W1.4xW1.4",
            "[6 x 6",
        )
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker"
            ) as get_ranker:
                for query in queries:
                    with self.subTest(query=query):
                        self.assertTrue(ineligible_for_section_reconstruction(query))
                        result = reconstruct(query)
                        self.assertIsNone(result.selected_prediction)
                        self.assertEqual(result.reason, "no_candidates")
                        self.assertIsNone(result.shadow)
            get_ranker.assert_not_called()
        finally:
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)

    def test_exact_labels_are_not_changed_by_xgb(self) -> None:
        original_enabled = settings.ml_label_ranker_enabled
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker",
                return_value=_ranker_preferring("W18X35"),
            ):
                result = reconstruct("W16X26")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
        self.assertEqual(result.reason, "exact_match")
        self.assertEqual(result.selected_prediction, "W16X26")

    def test_shadow_mode_does_not_mutate_live_output(self) -> None:
        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        original_log = settings.ml_label_ranker_shadow_log_path
        live = "L3X3X3/8"
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", False)
            object.__setattr__(settings, "ml_label_ranker_shadow", True)
            with tempfile.TemporaryDirectory() as tmp_dir:
                object.__setattr__(
                    settings,
                    "ml_label_ranker_shadow_log_path",
                    Path(tmp_dir) / "shadow_log.jsonl",
                )
                with patch(
                    "services.label_reconstruction.ranker.get_active_ranker",
                    return_value=_ranker_preferring("L3X3X3/16"),
                ):
                    meta = apply_label_ranker_for_analyze(
                        raw_text="L3X3X3/8X0'-6\"",
                        live_section=live,
                    )
                    result = reconstruct("L3X3X3/8X0'-6\"")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)
            object.__setattr__(settings, "ml_label_ranker_shadow_log_path", original_log)

        self.assertFalse(meta["applied"])
        self.assertEqual(meta["live_section"], live)
        self.assertEqual(result.selected_prediction, "L3X3X3/8")
        self.assertNotEqual(result.reason, "learned_ranker_top_candidate")
        self.assertEqual(result.shadow["ml_prediction"], "L3X3X3/8")
        self.assertEqual(result.shadow["ranker_ungated_top"], "L3X3X3/16")
        self.assertTrue(result.shadow["field_gate_rejected"])

    def test_enabled_remains_false_in_persistent_settings(self) -> None:
        self.assertFalse(settings.ml_label_ranker_enabled)
        self.assertFalse(settings.ml_label_ranker_shadow)


class IncompleteAngleAndSpacingSafetyTests(unittest.TestCase):
    def test_l6x3_does_not_become_l6x6x1(self) -> None:
        self.assertFalse(
            candidate_respects_reliable_query_fields("L6X3", "L6X6X1")
        )
        for label in generate_candidates("L6x3").candidates:
            self.assertTrue(label.startswith("L6X3X"), label)
            self.assertFalse(label.startswith("L6X6"))
        result = reconstruct("L6x3")
        self.assertIsNone(result.selected_prediction)
        self.assertNotEqual(result.selected_prediction, "L6X6X1")
        self.assertEqual(result.reason, "no_candidates")

        original_enabled = settings.ml_label_ranker_enabled
        original_shadow = settings.ml_label_ranker_shadow
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            object.__setattr__(settings, "ml_label_ranker_shadow", False)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker",
                return_value=_ranker_preferring("L6X6X1"),
            ):
                gated = reconstruct("L6x3")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
            object.__setattr__(settings, "ml_label_ranker_shadow", original_shadow)
        self.assertIsNone(gated.selected_prediction)
        self.assertNotEqual(gated.selected_prediction, "L6X6X1")

    def test_l5x3_preserves_printed_legs(self) -> None:
        for label in generate_candidates("L5x3").candidates:
            self.assertTrue(label.startswith("L5X3X"), label)
        result = reconstruct("L5x3")
        self.assertIsNone(result.selected_prediction)
        if result.selected_prediction:
            self.assertNotIn("C15", result.selected_prediction)

    def test_l4x4_does_not_invent_thickness(self) -> None:
        for label in generate_candidates("L4x4").candidates:
            self.assertTrue(label.startswith("L4X4X"), label)
        result = reconstruct("L4x4")
        self.assertIsNone(result.selected_prediction)

    def test_2l4x4_preserves_double_angle_and_does_not_invent_thickness(self) -> None:
        candidates = generate_candidates("2L4x4").candidates
        self.assertTrue(candidates)
        self.assertTrue(all(label.startswith("2L4X4") for label in candidates))
        result = reconstruct("2L4x4")
        self.assertIsNone(result.selected_prediction)
        self.assertFalse(str(result.selected_prediction or "").startswith("L4X4"))

    def test_complete_angle_with_cut_length_still_reconstructs(self) -> None:
        result = reconstruct('L4x4x1/4x4\'-3"')
        self.assertEqual(result.selected_prediction, "L4X4X1/4")
        result = reconstruct('L5x3x3/8x6"')
        self.assertEqual(result.selected_prediction, "L5X3X3/8")
        result = reconstruct('L6x4x5/16x4"')
        self.assertEqual(result.selected_prediction, "L6X4X5/16")

    def test_w12x19_at_spacing_does_not_become_w12x152(self) -> None:
        from services.label_reconstruction.candidates import conservative_normalize

        for query in ("W12x19@5'", "W12x19 @ 5'", "W12X19@5'-0\"", "W16X26@8'"):
            with self.subTest(query=query):
                normalized = conservative_normalize(query)
                self.assertNotIn("@", normalized)
                self.assertNotEqual(reconstruct(query).selected_prediction, "W12X152")
        self.assertEqual(conservative_normalize("W12x19@5'"), "W12X19")
        self.assertEqual(reconstruct("W12x19@5'").selected_prediction, "W12X19")
        self.assertEqual(reconstruct("W12x19 @ 5'").selected_prediction, "W12X19")
        self.assertEqual(reconstruct("W12x19@5'").reason, "exact_match")

        original_enabled = settings.ml_label_ranker_enabled
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            with patch(
                "services.label_reconstruction.ranker.get_active_ranker",
                return_value=_ranker_preferring("W12X152"),
            ):
                gated = reconstruct("W12x19@5'")
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)
        self.assertEqual(gated.selected_prediction, "W12X19")
        self.assertNotEqual(gated.selected_prediction, "W12X152")


if __name__ == "__main__":
    unittest.main()
