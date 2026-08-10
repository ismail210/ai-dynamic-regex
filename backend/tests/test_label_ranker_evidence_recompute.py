"""
Regression tests for stale confidence/evidence after a label-ranker override
(accuracy sprint Phase 2C).

When ``ML_LABEL_RANKER_ENABLED`` replaces the live section, everything
computed from ``unified_multimodal_fusion`` (confidence, per-modality
contributions, ``final_correction.reason``) previously kept describing the
PRE-swap candidate the fusion engine had actually scored — misattributing a
learned-ranker decision to "geometry and structural-graph evidence"
disagreement, and showing a confidence number that belonged to a different
shape entirely. This file asserts the fixed behavior directly.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.multimodal.encoder_contracts import AttentionResult, FusedFeatures, UnifiedFusionResult
from services.prediction.orchestrator import predict_token


def _stale_fusion_result() -> UnifiedFusionResult:
    """What unified_multimodal_fusion actually scored before the ranker
    replaced its pick — a different shape than the ranker will select."""

    return UnifiedFusionResult(
        section="W18X40",
        confidence=0.35,
        contributions={"text": 0.5, "geometry": 0.3, "graph": 0.2},
        attention=AttentionResult(weights={"text": 0.5, "geometry": 0.3, "graph": 0.2}, logits={}),
        fused_features=FusedFeatures(vector=[], modality_slices={}, availability={}, encoders={}),
        candidate_scores=[{"shape": "W18X40", "score": 0.35}],
        reasons=["fusion picked W18X40 from geometry/graph evidence"],
    )


def _ranker_applied_meta(selected: str, score: float) -> dict:
    return {
        "invoked": True,
        "applied": True,
        "shadow": None,
        "selected_prediction": selected,
        "reason": "learned_ranker_top_candidate",
        "model_version": "v3-test",
        "live_section": "W18X40",
        "ranker_status": "ok",
        "error_type": None,
        "ranking_scores": [score, score - 0.1],
    }


class LabelRankerEvidenceRecomputeTests(unittest.TestCase):
    def test_confidence_reflects_ranker_not_stale_fusion(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_stale_fusion_result(),
        ), patch(
            "services.prediction.orchestrator.apply_label_ranker_for_analyze",
            return_value=_ranker_applied_meta("W18X35", 0.88),
        ):
            result = predict_token("W18X3?", queue_unknown=False, persist_learning=False)

        self.assertEqual(result["section"], "W18X35")
        # The ranker's own score (0.88), not the stale fusion confidence (0.35)
        # that belonged to the candidate ("W18X40") the ranker replaced.
        self.assertAlmostEqual(result["confidence"]["overall"], 0.88, places=2)
        self.assertAlmostEqual(result["confidence"]["model_probability"], 0.88, places=2)

    def test_evidence_breakdown_attributed_to_ranker_not_geometry_graph(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_stale_fusion_result(),
        ), patch(
            "services.prediction.orchestrator.apply_label_ranker_for_analyze",
            return_value=_ranker_applied_meta("W18X35", 0.88),
        ):
            result = predict_token("W18X3?", queue_unknown=False, persist_learning=False)

        breakdown = result["confidence"]["breakdown"]
        weights = result["confidence"]["weights"]
        self.assertIn("label_ranker", breakdown)
        self.assertIn("label_ranker", weights)
        # The stale fusion's own per-modality shares (0.5 text / 0.3 geometry
        # / 0.2 graph) must not be presented as if they explain W18X35 — the
        # ranker never used them, fusion computed them for a different shape.
        self.assertNotIn("text", weights)
        self.assertNotIn("geometry", weights)
        self.assertNotIn("graph", weights)

    def test_correction_reason_attributes_ranker_not_geometry_graph(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_stale_fusion_result(),
        ), patch(
            "services.prediction.orchestrator.apply_label_ranker_for_analyze",
            return_value=_ranker_applied_meta("W18X35", 0.88),
        ):
            result = predict_token("W18X3?", queue_unknown=False, persist_learning=False)

        correction = result["explanation"].get("correction") or {}
        reason = str(correction.get("reason") or "")
        self.assertIn("ranker", reason.lower())
        self.assertNotIn("structural-graph evidence disagreed", reason)

    def test_ranker_score_missing_uses_conservative_non_fabricated_value(self):
        meta = _ranker_applied_meta("W18X35", 0.88)
        meta["ranking_scores"] = None
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_stale_fusion_result(),
        ), patch(
            "services.prediction.orchestrator.apply_label_ranker_for_analyze",
            return_value=meta,
        ):
            result = predict_token("W18X3?", queue_unknown=False, persist_learning=False)

        self.assertEqual(result["section"], "W18X35")
        # Not 0.35 (the stale, wrong-candidate fusion score) and not fabricated
        # certainty — a fixed, documented conservative fallback.
        self.assertAlmostEqual(result["confidence"]["overall"], 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
