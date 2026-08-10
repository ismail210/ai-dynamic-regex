"""
Regression tests for the protected exact label path (accuracy sprint Phase 1A).

A clean, catalog-valid exact section read from text must never be silently
replaced by weaker fusion/graph/ranker evidence. This file reproduces the
specific bug found live during the accuracy audit:

    OCR "W16x26" (100% text match, normalizes to catalog entry W16X26)
    was overridden to "W14X22" (64% text evidence, 20% confidence) because
    graph evidence for a competing candidate outscored it.

and asserts the fixed behavior: the exact catalog match always wins, any
disagreement is surfaced for review, and non-catalog "shaped" text (e.g.
W12X999) is never accepted as a final prediction.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.exact_section_predictor import catalog_valid_exact_section
from services.multimodal.encoder_contracts import AttentionResult, FusedFeatures, UnifiedFusionResult
from services.prediction.orchestrator import _gated_exact_override, predict_token


def _fake_fusion_result(section: str, confidence: float = 0.20) -> UnifiedFusionResult:
    """A minimal, deliberately low-confidence/near-tied fusion result that
    disagrees with a clean exact text match — the exact shape of evidence
    that caused the live W16x26 -> W14X22 regression."""

    return UnifiedFusionResult(
        section=section,
        confidence=confidence,
        contributions={"text": 0.4, "geometry": 0.3, "graph": 0.3},
        attention=AttentionResult(weights={"text": 0.4, "geometry": 0.3, "graph": 0.3}, logits={}),
        fused_features=FusedFeatures(vector=[], modality_slices={}, availability={}, encoders={}),
        candidate_scores=[
            {"shape": section, "score": confidence},
        ],
        reasons=["Two or more candidates are near-tied; automatic selection is not reliable enough."],
    )


class CatalogValidExactSectionTests(unittest.TestCase):
    """Unit tests for the shared catalog-validity check."""

    def test_clean_uppercase_label_is_valid(self):
        self.assertEqual(catalog_valid_exact_section("W16X26"), "W16X26")

    def test_lowercase_normalizes_to_catalog_form(self):
        self.assertEqual(catalog_valid_exact_section("w16x26"), "W16X26")

    def test_spaced_separator_normalizes_to_catalog_form(self):
        self.assertEqual(catalog_valid_exact_section("W16 X 26"), "W16X26")
        self.assertEqual(catalog_valid_exact_section("w16 x 26"), "W16X26")

    def test_well_formatted_but_nonexistent_shape_is_rejected(self):
        # Regex-shaped like a section, but not a real AISC catalog row.
        self.assertIsNone(catalog_valid_exact_section("W12X999"))

    def test_garbage_text_is_rejected(self):
        self.assertIsNone(catalog_valid_exact_section("garbage"))
        self.assertIsNone(catalog_valid_exact_section(""))

    def test_family_examples(self):
        for raw, expected in [
            ("hss8x8x1/2", "HSS8X8X1/2"),
            ("c10x20", "C10X20"),
            ("mc12x35", "MC12X35"),
            ("l4x4x3/8", "L4X4X3/8"),
            ("wt7x15", "WT7X15"),
            ("st6x15.9", "ST6X15.9"),
            ("mt5x4.5", "MT5X4.5"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(catalog_valid_exact_section(raw), expected)


class GatedExactOverrideCatalogBypassTests(unittest.TestCase):
    """P0-1: the fallback path must require real catalog membership, not just
    regex-shaped text."""

    def test_non_catalog_but_regex_shaped_fusion_section_is_rejected(self):
        section, retrieval_gate_failed = _gated_exact_override("W12X999", [], "W12X999")
        self.assertEqual(section, "")
        self.assertTrue(retrieval_gate_failed)

    def test_catalog_valid_fusion_section_is_accepted(self):
        section, retrieval_gate_failed = _gated_exact_override("w16x26", [], "w16x26")
        self.assertEqual(section, "W16X26")
        self.assertFalse(retrieval_gate_failed)


class ProtectedExactLabelIntegrationTests(unittest.TestCase):
    """End-to-end: predict_token must keep a clean exact catalog label even
    when internal fusion strongly prefers a different candidate."""

    def test_w16x26_does_not_regress_to_w14x22(self):
        """Direct reproduction of the live audit finding."""

        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W14X22", confidence=0.20),
        ):
            result = predict_token("W16x26", queue_unknown=False, persist_learning=False)

        self.assertEqual(result["section"], "W16X26")
        self.assertNotEqual(result["section"], "W14X22")
        self.assertEqual(result["review_status"], "pending_review")

    def test_conflict_is_surfaced_not_hidden(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W14X22", confidence=0.20),
        ):
            result = predict_token("W16x26", queue_unknown=False, persist_learning=False)

        reasons = result.get("explanation", {}).get("ai_reasons") or result.get(
            "explanation", {}
        ).get("reasons", [])
        combined = " ".join(str(r) for r in reasons) if reasons else str(result.get("explanation"))
        self.assertIn("W16X26", combined)

    def test_no_conflict_when_fusion_agrees(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion_result("W16X26", confidence=0.95),
        ):
            result = predict_token("W16x26", queue_unknown=False, persist_learning=False)

        self.assertEqual(result["section"], "W16X26")

    def test_family_examples_survive_conflicting_fusion(self):
        """W, HSS, C, MC, L, WT/ST/MT: a clean exact match always wins over a
        conflicting fusion pick, regardless of family."""

        cases = [
            ("W18x35", "W18X35", "W14X22"),
            ("hss8x8x1/2", "HSS8X8X1/2", "HSS6X6X3/8"),
            ("c10x20", "C10X20", "MC12X35"),
            ("l4x4x3/8", "L4X4X3/8", "L6X6X1/2"),
            ("wt7x15", "WT7X15", "ST6X15.9"),
        ]
        for raw, expected, decoy in cases:
            with self.subTest(raw=raw):
                with patch(
                    "services.prediction.orchestrator.unified_multimodal_fusion.predict",
                    return_value=_fake_fusion_result(decoy, confidence=0.20),
                ):
                    result = predict_token(
                        raw, queue_unknown=False, persist_learning=False
                    )
                self.assertEqual(result["section"], expected)
                self.assertNotEqual(result["section"], decoy)


if __name__ == "__main__":
    unittest.main()
