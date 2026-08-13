"""
Regression tests for the Phase 2/3 resolution contract:

    Exact supported labels are deterministic.
    Missing, ambiguous, unsupported, or out-of-dataset labels must not be
    automatically guessed.
    ML may suggest candidates, but it must never bypass the catalog/review
    safety gate.

These tests target two real gaps found while auditing the merged
integration branch:

1. ``_gated_exact_override`` accepted ANY catalog-valid fusion/correction
   output as a resolved final answer, with no requirement that the
   extracted text itself actually supported it. A live repro: normalized
   text "W12X999" (not a real AISC shape) was silently rewritten to the
   real-but-unrelated catalog entry "W12X190" and returned as
   ``canonical.prediction.final_label`` -- ``needs_review`` happened to end
   up ``True`` via a downstream match_status check, but the canonical
   *final label* itself still carried a fabricated answer, violating "no
   fake certainty".
2. The damaged-label ranker (``ML_LABEL_RANKER_ENABLED``), when live, set
   ``retrieval_gate_failed = False`` unconditionally on the strength of its
   own score alone -- exactly the "ML confidence bypasses the catalog gate"
   failure mode the contract prohibits.

Fix: ``_gated_exact_override`` and the label-ranker branch now both gate
acceptance on whether the accepted label equals what ``ocr_text`` itself
resolves to under safe (non-fuzzy) normalization; and
``canonical_contract.build_canonical_prediction`` nulls ``final_label``
for every match_status that already forces review (reusing
``_REVIEW_REASONS`` as the single source of truth), so "auto-acceptable"
and "final_label is trustworthy" can never drift apart.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.exact_section_predictor import ExactSectionCandidate
from services.multimodal.encoder_contracts import (
    AttentionResult,
    FusedFeatures,
    UnifiedFusionResult,
)
from services.prediction.orchestrator import _gated_exact_override, predict_token


def _fake_fusion_result(section: str, confidence: float = 0.95) -> UnifiedFusionResult:
    return UnifiedFusionResult(
        section=section,
        confidence=confidence,
        contributions={"text": 0.4, "geometry": 0.3, "graph": 0.3},
        attention=AttentionResult(weights={"text": 0.4, "geometry": 0.3, "graph": 0.3}, logits={}),
        fused_features=FusedFeatures(vector=[], modality_slices={}, availability={}, encoders={}),
        candidate_scores=[{"shape": section, "score": confidence}],
        reasons=[],
    )


class GatedExactOverrideTextGroundingTests(unittest.TestCase):
    """Unit tests: catalog membership alone must not be enough to accept."""

    def test_catalog_valid_but_text_unsupported_candidate_is_gated(self):
        # "W12X999" does not exist; a fuzzy/correction engine proposing the
        # real-but-different "W12X190" must not be auto-accepted just
        # because W12X190 itself is a real catalog row.
        section, retrieval_gate_failed = _gated_exact_override(
            "W12X190", [], "W12X999"
        )
        self.assertEqual(section, "W12X190")
        self.assertTrue(retrieval_gate_failed)

    def test_high_confidence_fuzzy_candidate_still_gated_without_text_support(self):
        candidates = [
            ExactSectionCandidate(
                shape="W12X190", confidence=0.99, text_similarity=0.99, evidence={}
            ),
            ExactSectionCandidate(
                shape="W12X170", confidence=0.10, text_similarity=0.10, evidence={}
            ),
        ]
        section, retrieval_gate_failed = _gated_exact_override(
            "W", candidates, "W12X999"
        )
        # High confidence + wide margin previously auto-accepted this.
        self.assertEqual(section, "W12X190")
        self.assertTrue(retrieval_gate_failed)

    def test_text_grounded_exact_match_still_accepted(self):
        section, retrieval_gate_failed = _gated_exact_override(
            "w16x26", [], "w16x26"
        )
        self.assertEqual(section, "W16X26")
        self.assertFalse(retrieval_gate_failed)


class InvalidCatalogShapeTests(unittest.TestCase):
    """W12X999: not in catalog -> no fabricated final label, human review."""

    def test_no_fabricated_final_label(self):
        result = predict_token("W12X999", queue_unknown=False, persist_learning=False)

        self.assertIsNone(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label")
        )
        self.assertTrue(result["needs_review"])
        self.assertNotEqual(result["review_status"], "auto_accepted")

    def test_candidates_remain_available_for_reviewer(self):
        result = predict_token("W12X999", queue_unknown=False, persist_learning=False)

        candidates = result.get("canonical_candidates") or []
        self.assertGreater(len(candidates), 0)


class MissingCharactersTests(unittest.TestCase):
    """Wildcard/incomplete labels: candidates allowed, no automatic final
    section, human review -- even when a unique AISC possibility exists."""

    def test_wildcard_mask_does_not_auto_resolve(self):
        for text in ["W44X3**", "W18X?5", "W8*40"]:
            with self.subTest(text=text):
                result = predict_token(text, queue_unknown=False, persist_learning=False)
                self.assertIsNone(
                    (result.get("canonical") or {})
                    .get("prediction", {})
                    .get("final_label")
                )
                self.assertTrue(result["needs_review"])

    def test_wildcard_candidates_still_surfaced(self):
        result = predict_token("W44X3**", queue_unknown=False, persist_learning=False)
        candidates = {c.get("label") for c in (result.get("canonical_candidates") or [])}
        self.assertTrue(candidates & {"W44X335", "W44X368"})


class AmbiguousOcrSubstitutionTests(unittest.TestCase):
    """A valid designation reachable only via a semantic character swap
    (not safe formatting normalization) must not be silently accepted."""

    def test_mocked_semantic_correction_not_silently_accepted(self):
        # Simulate fusion "correcting" G->6-style: garbled text "W12G26"
        # (not a real shape) proposed as the real catalog entry "W12X26"
        # with high fusion confidence.
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W12X26", confidence=0.97),
        ):
            result = predict_token(
                "W12G26", queue_unknown=False, persist_learning=False
            )

        self.assertIsNone(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label")
        )
        self.assertTrue(result["needs_review"])


class UnsupportedAnnotationTests(unittest.TestCase):
    """Plate/non-standard annotations: no forced AISC section, review
    required, using the partner's new annotation-taxonomy classification."""

    def test_plate_annotation_gets_no_forced_section(self):
        result = predict_token("PL 1/2 X 8", queue_unknown=False, persist_learning=False)

        self.assertIsNone(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label")
        )
        self.assertTrue(result["needs_review"])
        self.assertNotEqual(result["review_status"], "auto_accepted")


class GeometryConflictTests(unittest.TestCase):
    """Exact AISC text + conflicting evidence: retain the text reading,
    flag the conflict, never substitute a different section."""

    def test_exact_text_survives_conflicting_fusion_pick(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W14X22", confidence=0.85),
        ):
            result = predict_token("W16x26", queue_unknown=False, persist_learning=False)

        self.assertEqual(result["section"], "W16X26")
        self.assertEqual(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label"),
            "W16X26",
        )
        self.assertIn(
            "protected_label_conflict",
            (result.get("features") or {}).get("fusion", {}).get("detected_issues", []),
        )
        self.assertTrue(result["needs_review"])


class ArtificiallyHighModelScoreOodTests(unittest.TestCase):
    """A mocked near-certain model score on out-of-catalog input must not
    defeat the safety gate."""

    def test_high_score_ood_still_requires_review(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W12X190", confidence=0.999),
        ):
            result = predict_token("W12X999", queue_unknown=False, persist_learning=False)

        self.assertIsNone(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label")
        )
        self.assertTrue(result["needs_review"])
        self.assertNotEqual(result["review_status"], "auto_accepted")


class LabelRankerCannotBypassGateTests(unittest.TestCase):
    """Even if ML_LABEL_RANKER_ENABLED were live, its own confidence must
    not satisfy the safety gate for a reconstruction the raw text does not
    itself support."""

    def test_enabled_ranker_high_confidence_pick_still_gated(self):
        from config import settings

        fake_result = type(
            "FakeResult",
            (),
            {
                "selected_prediction": "W12X190",
                "reason": "learned_ranker_top_candidate",
                "model_version": "test",
                "shadow": None,
                "ranking_scores": [0.99],
            },
        )()

        original_enabled = settings.ml_label_ranker_enabled
        try:
            object.__setattr__(settings, "ml_label_ranker_enabled", True)
            with patch(
                "services.label_reconstruction.shadow.reconstruct",
                return_value=fake_result,
            ):
                result = predict_token(
                    "W12X999", queue_unknown=False, persist_learning=False
                )
        finally:
            object.__setattr__(settings, "ml_label_ranker_enabled", original_enabled)

        self.assertIsNone(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label")
        )
        self.assertTrue(result["needs_review"])


class ExactAndFormattingMatchesRemainDeterministicTests(unittest.TestCase):
    """Confirm the fixes above did not disturb the Case A path.

    ``match_status``/``final_label`` for a protected exact label are
    computed purely from catalog membership + string comparison and never
    depend on the trained retrieval model, so they are asserted
    unconditionally. ``review_status``/``needs_review`` additionally depend
    on whether fusion's own (separately trained, fuzzy) pick agrees with
    the protected label -- correctly forcing review via
    ``protected_label_conflict`` when it does not, per the geometry-conflict
    tests above. Fusion is mocked to agree here so this test isolates "Case
    A resolution", not "does the ambient exact_section_model currently
    happen to agree with the catalog", which depends on unrelated tests'
    shared on-disk training data and is not this test's concern.
    """

    def test_exact_match(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W16X26", confidence=0.95),
        ):
            result = predict_token("W16X26", queue_unknown=False, persist_learning=False)

        self.assertEqual(result["section"], "W16X26")
        self.assertEqual(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label"),
            "W16X26",
        )
        self.assertEqual(result["review_status"], "auto_accepted")
        self.assertFalse(result["needs_review"])
        self.assertEqual(
            (result.get("comparison") or {}).get("match_status"), "exact_match"
        )

    def test_formatting_only_normalization(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W16X26", confidence=0.95),
        ):
            result = predict_token("w16 x 26", queue_unknown=False, persist_learning=False)

        self.assertEqual(result["section"], "W16X26")
        self.assertEqual(
            (result.get("canonical") or {}).get("prediction", {}).get("final_label"),
            "W16X26",
        )
        self.assertEqual(result["review_status"], "auto_accepted")
        self.assertEqual(
            (result.get("comparison") or {}).get("match_status"), "normalized_match"
        )


if __name__ == "__main__":
    unittest.main()
