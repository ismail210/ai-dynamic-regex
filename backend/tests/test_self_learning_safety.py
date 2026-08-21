"""
Regression tests for the self-learning persistence gate.

Pre-training audit finding: ``predict_token()`` called
``process_token(section, token, persist=persist_learning)`` using the raw,
pre-gate ``section`` guess -- BEFORE ``needs_review``/``match_status`` were
even computed -- so a fuzzy correction, wildcard completion, ranker
prediction, or any other review-required guess could be merged into the
self-learning regex knowledge base (``training/dynamic_regex.json``) as
though it were confirmed ground truth. The canonical live repro is
"W12X999" (not a real AISC shape) resolving toward the real-but-unrelated
catalog entry "W12X190" (see ``tests/test_resolution_contract.py``).

Fix: ``predict_token`` now computes the final ``match_status``/
``needs_review`` decision first, and only calls
``process_token(..., learn=True)`` when the result is EXACT_MATCH or
NORMALIZED_MATCH *and* does not need review -- the same two trusted paths
``canonical_contract`` allows through to ``prediction.final_label`` without
nulling it. Everything else is passed ``learn=False``, which
``self_learning_engine.process_token`` honors by skipping the
knowledge-base-mutating branch entirely (Case 2 / ``learn_and_upsert``);
only a read-only check against an already-existing pattern (Case 1) still
runs, so a suggestion can still be shown without ever being learned.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.multimodal.encoder_contracts import (
    AttentionResult,
    FusedFeatures,
    UnifiedFusionResult,
)
from services.prediction.orchestrator import predict_token
from services.regex_knowledge_base import RegexKnowledgeBase
from services.self_learning_engine import (
    STATUS_REUSED,
    STATUS_UNRESOLVED,
    process_token,
)


def _fake_fusion_result(section: str, confidence: float = 0.95) -> UnifiedFusionResult:
    """A clean, high-confidence, non-conflicting fusion result -- same shape
    used by tests/test_protected_exact_label.py and
    tests/test_resolution_contract.py -- so these tests assert the
    persistence-gate decision itself, not incidental behavior of whatever
    real fusion/knowledge-base state happens to exist when the full suite
    runs in some other order."""

    return UnifiedFusionResult(
        section=section,
        confidence=confidence,
        contributions={"text": 0.4, "geometry": 0.3, "graph": 0.3},
        attention=AttentionResult(weights={"text": 0.4, "geometry": 0.3, "graph": 0.3}, logits={}),
        fused_features=FusedFeatures(vector=[], modality_slices={}, availability={}, encoders={}),
        candidate_scores=[{"shape": section, "score": confidence}],
        reasons=[],
    )


class ProcessTokenLearnGateTests(unittest.TestCase):
    """Unit tests directly against process_token()'s learn gate, isolated
    from the real knowledge base file."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.kb = RegexKnowledgeBase(path=Path(self.tmp.name) / "kb.json")
        self._patcher = patch("services.self_learning_engine.knowledge_base", self.kb)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_learn_false_does_not_create_a_new_class(self):
        outcome = process_token("W99X999", "W99X999", persist=False, learn=False)

        self.assertEqual(outcome.status, STATUS_UNRESOLVED)
        self.assertFalse(outcome.learned)
        self.assertEqual(
            outcome.detail.get("reason"), "learning_suppressed_untrusted_prediction"
        )
        self.assertIsNone(self.kb.get("W99X999"))

    def test_learn_true_creates_a_new_class(self):
        outcome = process_token("W99X999", "W99X999", persist=False, learn=True)

        self.assertTrue(outcome.learned)
        self.assertIsNotNone(self.kb.get("W99X999"))

    def test_learn_false_still_reuses_an_existing_pattern(self):
        # Seed the class the way a previously-trusted persist would have.
        process_token("W18X35", "W18X35", persist=False, learn=True)
        self.assertIsNotNone(self.kb.get("W18X35"))

        outcome = process_token("W18X35", "W18X35", persist=False, learn=False)

        self.assertEqual(outcome.status, STATUS_REUSED)
        self.assertTrue(outcome.matched)


class PredictTokenSelfLearningGateTests(unittest.TestCase):
    """End-to-end: predict_token must only pass learn=True for a trusted
    resolution, using the FINAL needs_review/match_status decision, not the
    pre-gate internal guess."""

    def test_review_required_prediction_is_not_learned(self):
        """W12X999 -> (unrelated) W12X190: the documented live bug repro.
        final_label stays null and needs_review is True; process_token must
        be called with learn=False, so nothing is merged into the KB."""

        with patch(
            "services.self_learning_engine.process_token"
        ) as mock_process_token:
            mock_process_token.return_value = _fake_learning_outcome()
            result = predict_token(
                "W12X999", queue_unknown=False, persist_learning=True
            )

        self.assertIsNone(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label")
        )
        self.assertTrue(result["needs_review"])
        mock_process_token.assert_called_once()
        _, kwargs = mock_process_token.call_args
        self.assertFalse(kwargs.get("learn"))

    def test_exact_catalog_match_is_learned(self):
        """A clean, catalog-valid exact text match must still be eligible
        for self-learning (learn=True)."""

        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W16X26", confidence=0.95),
        ), patch(
            "services.self_learning_engine.process_token"
        ) as mock_process_token:
            mock_process_token.return_value = _fake_learning_outcome()
            result = predict_token(
                "W16X26", queue_unknown=False, persist_learning=True
            )

        self.assertEqual(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label"),
            "W16X26",
        )
        mock_process_token.assert_called_once()
        _, kwargs = mock_process_token.call_args
        self.assertTrue(kwargs.get("learn"))

    def test_safe_normalization_match_is_learned(self):
        """A formatting-only normalization ("w16 x 26" -> "W16X26") is the
        other trusted path and must also be eligible for self-learning."""

        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W16X26", confidence=0.95),
        ), patch(
            "services.self_learning_engine.process_token"
        ) as mock_process_token:
            mock_process_token.return_value = _fake_learning_outcome()
            result = predict_token(
                "w16 x 26", queue_unknown=False, persist_learning=True
            )

        self.assertEqual(result["section"], "W16X26")
        mock_process_token.assert_called_once()
        _, kwargs = mock_process_token.call_args
        self.assertTrue(kwargs.get("learn"))


def _fake_learning_outcome():
    from services.self_learning_engine import LearningOutcome

    return LearningOutcome(
        status=STATUS_REUSED,
        learned=False,
        pattern=r"W\d+X\d+",
        previous_pattern=r"W\d+X\d+",
        matched=True,
        regex_confidence=0.9,
        regex_level="High",
        detail={},
    )


if __name__ == "__main__":
    unittest.main()
