"""Regression: incomplete L/2L must abstain — never invent thickness or 2L."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.database_loader import lookup_shape
from services.multimodal.encoder_contracts import (
    AttentionResult,
    FusedFeatures,
    UnifiedFusionResult,
)
from services.prediction.label_ranker_hook import (
    incomplete_angle_preserved_core,
    is_complete_angle_outside_catalog,
    is_incomplete_angle_missing_thickness,
    non_catalog_angle_preserved_core,
)
from services.prediction.orchestrator import predict_token
from services.exact_section_predictor import catalog_valid_exact_section


def _fake_fusion_result(section: str, confidence: float = 0.55) -> UnifiedFusionResult:
    return UnifiedFusionResult(
        section=section,
        confidence=confidence,
        contributions={"text": 0.5, "geometry": 0.25, "graph": 0.25},
        attention=AttentionResult(
            weights={"text": 0.5, "geometry": 0.25, "graph": 0.25},
            logits={},
        ),
        fused_features=FusedFeatures(
            vector=[], modality_slices={}, availability={}, encoders={}
        ),
        candidate_scores=[{"shape": section, "score": confidence}],
        reasons=["fake fusion decoy for incomplete-angle abstention tests"],
    )


class IncompleteAngleDetectorTests(unittest.TestCase):
    def test_incomplete_examples_detected(self) -> None:
        for raw in (
            "L4x4",
            "L4X4",
            "L5x3",
            "L4X3",
            "2L4X4",
            "2L5x3",
            "2l4x4",
            "L4X4,",
            "L4X4;",
            'L4X4"',
            "2L4X4,",
            "2L4X4;",
            '2L4X4"',
            "L4X4@6",
            "L4X4@length",
        ):
            with self.subTest(raw=raw):
                self.assertTrue(is_incomplete_angle_missing_thickness(raw))

    def test_complete_and_shop_cut_not_detected(self) -> None:
        for raw in (
            "L4X4X1/4",
            "L5X3X3/8",
            'L4x3x1/4x6"',
            "L3X3X3/8X0'-6\"",
            "L3X3X5/16,",
            # Same-designation thickness present (must not become incomplete L5X3)
            "L5X3-1/2X5/16",
            "L4X3-1/2X5/16",
            "W16X26",
            "HSS8X8X1/2",
        ):
            with self.subTest(raw=raw):
                self.assertFalse(is_incomplete_angle_missing_thickness(raw))

    def test_preserved_core(self) -> None:
        self.assertEqual(incomplete_angle_preserved_core("L4x4"), "L4X4")
        self.assertEqual(incomplete_angle_preserved_core("2L5x3"), "2L5X3")
        self.assertEqual(incomplete_angle_preserved_core("L4X4,"), "L4X4")
        self.assertEqual(incomplete_angle_preserved_core('L4X4"'), "L4X4")
        self.assertEqual(incomplete_angle_preserved_core("2L4X4;"), "2L4X4")
        self.assertEqual(incomplete_angle_preserved_core("L4X4@length"), "L4X4")
        self.assertIsNone(incomplete_angle_preserved_core("L4X4X1/4"))

    def test_non_catalog_complete_angle_detected(self) -> None:
        self.assertTrue(is_complete_angle_outside_catalog("L2x2x10"))
        self.assertTrue(is_complete_angle_outside_catalog("L2X2X10"))
        self.assertEqual(non_catalog_angle_preserved_core("L2x2x10"), "L2X2X10")
        self.assertFalse(is_complete_angle_outside_catalog("L4X4X1/4"))
        self.assertFalse(is_complete_angle_outside_catalog("L4X4"))
        self.assertFalse(is_complete_angle_outside_catalog("L5X3-1/2X5/16"))


class IncompleteAngleAbstentionIntegrationTests(unittest.TestCase):
    """End-to-end: predict_token must not invent thickness for incomplete L/2L."""

    def _predict_against_decoy(self, raw: str, decoy: str) -> dict:
        with patch(
            "services.prediction.orchestrator.predict_exact_sections",
            return_value=[],
        ), patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result(decoy, confidence=0.90),
        ), patch(
            "services.prediction.orchestrator.suggest_token_corrections",
            return_value=[],
        ):
            return predict_token(raw, queue_unknown=False, persist_learning=False)

    def test_l4x4_abstains_and_preserves_core(self) -> None:
        result = self._predict_against_decoy("L4x4", "L4X4X1/4")
        self.assertEqual(result["section"], "L4X4")
        self.assertNotEqual(result["section"], "L4X4X1/4")
        self.assertIsNone(lookup_shape(result["section"]))
        self.assertEqual(result.get("completion_status"), "missing_thickness")
        self.assertTrue(result.get("needs_review") or result.get("abstain"))
        self.assertFalse(result.get("takeoff_eligible"))

    def test_l5x3_abstains(self) -> None:
        result = self._predict_against_decoy("L5x3", "L5X3X3/8")
        self.assertEqual(result["section"], "L5X3")
        self.assertNotEqual(result["section"], "L5X3X3/8")
        self.assertFalse(result.get("takeoff_eligible"))

    def test_l4x3_abstains(self) -> None:
        result = self._predict_against_decoy("L4X3", "L4X3X1/4")
        self.assertEqual(result["section"], "L4X3")
        self.assertNotEqual(result["section"], "L4X3X1/4")

    def test_2l4x4_preserves_incomplete_2l_not_thickness(self) -> None:
        result = self._predict_against_decoy("2L4X4", "2L4X4X1/4")
        self.assertEqual(result["section"], "2L4X4")
        self.assertNotEqual(result["section"], "2L4X4X1/4")
        self.assertTrue(str(result["section"]).startswith("2L"))
        self.assertFalse(result.get("takeoff_eligible"))

    def test_incomplete_l_does_not_become_2l(self) -> None:
        result = self._predict_against_decoy("L4x4", "2L4X4X1/4")
        self.assertEqual(result["section"], "L4X4")
        self.assertFalse(str(result["section"]).startswith("2L"))

    def test_incomplete_l_ignores_tfidf_candidates(self) -> None:
        """Even if TF-IDF would return complete neighbors, gate skips them."""

        class _Cand:
            def __init__(self, shape: str) -> None:
                self.shape = shape
                self.confidence = 0.95

            def to_dict(self) -> dict:
                return {"shape": self.shape, "confidence": self.confidence}

        with patch(
            "services.prediction.orchestrator.predict_exact_sections",
            return_value=[_Cand("L4X4X1/4"), _Cand("L4X3X1/4")],
        ) as mocked_exact, patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("L4X4X1/4", confidence=0.99),
        ), patch(
            "services.prediction.orchestrator.suggest_token_corrections",
            return_value=[],
        ):
            result = predict_token("L4x4", queue_unknown=False, persist_learning=False)

        mocked_exact.assert_not_called()
        self.assertEqual(result["section"], "L4X4")
        self.assertNotEqual(result["section"], "L4X4X1/4")

    def test_trailing_punct_incomplete_l_abstains(self) -> None:
        for raw in ("L4X4,", "L4X4;", 'L4X4"'):
            with self.subTest(raw=raw):
                result = self._predict_against_decoy(raw, "L4X4X1/4")
                self.assertEqual(result["section"], "L4X4")
                self.assertEqual(result.get("completion_status"), "missing_thickness")
                self.assertFalse(result.get("takeoff_eligible"))
                self.assertFalse(str(result["section"]).startswith("2L"))

    def test_trailing_punct_incomplete_2l_abstains(self) -> None:
        result = self._predict_against_decoy("2L4X4,", "2L4X4X1/4")
        self.assertEqual(result["section"], "2L4X4")
        self.assertEqual(result.get("completion_status"), "missing_thickness")
        self.assertFalse(result.get("takeoff_eligible"))

    def test_at_length_noise_incomplete_l_abstains(self) -> None:
        result = self._predict_against_decoy("L4X4@length", "L4X4X1/4")
        self.assertEqual(result["section"], "L4X4")
        self.assertEqual(result.get("completion_status"), "missing_thickness")
        self.assertFalse(result.get("takeoff_eligible"))

    def test_non_catalog_complete_angle_not_invented(self) -> None:
        result = self._predict_against_decoy("L2x2x10", "L2X2X1/8")
        self.assertEqual(result["section"], "L2X2X10")
        self.assertNotEqual(result["section"], "L2X2X1/8")
        self.assertFalse(result.get("takeoff_eligible"))
        self.assertTrue(result.get("needs_review") or result.get("abstain"))

    def test_half_leg_complete_angle_unchanged(self) -> None:
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("L5X3X5/16", confidence=0.20),
        ):
            result = predict_token(
                "L5X3-1/2X5/16", queue_unknown=False, persist_learning=False
            )
        self.assertEqual(result["section"], "L5X3-1/2X5/16")
        self.assertEqual(result.get("completion_status"), "complete")
        self.assertFalse(is_incomplete_angle_missing_thickness("L5X3-1/2X5/16"))

    def test_complete_l_with_trailing_comma_stays_l_not_2l(self) -> None:
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("2L3X3X5/16", confidence=0.95),
        ), patch(
            "services.prediction.orchestrator.suggest_token_corrections",
            return_value=[],
        ):
            result = predict_token(
                "L3X3X5/16,", queue_unknown=False, persist_learning=False
            )
        self.assertEqual(result["section"], "L3X3X5/16")
        self.assertFalse(str(result["section"]).startswith("2L"))
        self.assertEqual(result.get("completion_status"), "complete")

    def test_complete_l_unchanged(self) -> None:
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("L4X4X3/8", confidence=0.20),
        ):
            result = predict_token(
                "L4X4X1/4", queue_unknown=False, persist_learning=False
            )
        self.assertEqual(result["section"], "L4X4X1/4")
        self.assertEqual(catalog_valid_exact_section("L4X4X1/4"), "L4X4X1/4")

    def test_complete_l5x3x38_unchanged(self) -> None:
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("L5X3X1/4", confidence=0.20),
        ):
            result = predict_token(
                "L5X3X3/8", queue_unknown=False, persist_learning=False
            )
        self.assertEqual(result["section"], "L5X3X3/8")

    def test_shop_cut_l_core_preserved(self) -> None:
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("L4X3X5/16", confidence=0.20),
        ):
            result = predict_token(
                'L4x3x1/4x6"', queue_unknown=False, persist_learning=False
            )
        self.assertEqual(result["section"], "L4X3X1/4")
        self.assertNotEqual(result["section"], "L4X3X5/16")
        self.assertFalse(is_incomplete_angle_missing_thickness('L4x3x1/4x6"'))

    def test_shop_cut_feet_inches_core_preserved(self) -> None:
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("L3X3X5/16", confidence=0.20),
        ):
            result = predict_token(
                "L3X3X3/8X0'-6\"", queue_unknown=False, persist_learning=False
            )
        self.assertEqual(result["section"], "L3X3X3/8")
        self.assertNotEqual(result["section"], "L3X3X5/16")

    def test_document_prior_cannot_complete_incomplete_l(self) -> None:
        prior = {
            "enabled": True,
            "local_sections": {"L4X4X1/4": 12, "L4X3X1/4": 8},
        }
        with patch(
            "services.prediction.orchestrator.predict_exact_sections",
            return_value=[],
        ), patch(
            "services.prediction.orchestrator.apply_prior_to_candidates",
            side_effect=AssertionError("document prior must not run for incomplete L"),
        ), patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("L4X4X1/4", confidence=0.90),
        ), patch(
            "services.prediction.orchestrator.suggest_token_corrections",
            return_value=[],
        ):
            from services.prediction.orchestrator import predict_from_context

            result = predict_from_context(
                {
                    "token": {
                        "text": "L4x4",
                        "raw_text": "L4x4",
                        "normalized_text": "L4X4",
                        "confidence": 0.9,
                    },
                    "document": {"document_prior": prior, "source_file": "test.pdf"},
                }
            )
        self.assertEqual(result["section"], "L4X4")
        self.assertNotEqual(result["section"], "L4X4X1/4")


if __name__ == "__main__":
    unittest.main()
