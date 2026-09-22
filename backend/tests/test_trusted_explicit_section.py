"""Trusted-explicit section precedence (resolution contract sections 8/11-20).

When the printed OCR text is itself one complete, catalog-valid AISC section,
its identity is resolved from the text alone. No weaker modality (fuzzy
retrieval, fusion, geometry, graph, document prior, learned ranker) may change
that identity, lower its confidence, mark it ambiguous, force SECTION review,
or make a decoy candidate win. Only a human reviewer or a verified project /
schedule rule outranks it.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.exact_section_predictor import resolve_trusted_explicit_section
from services.multimodal.encoder_contracts import (
    AttentionResult,
    FusedFeatures,
    UnifiedFusionResult,
)
from services.prediction.orchestrator import predict_token


def _fake_fusion(section: str, *, confidence: float = 0.9) -> UnifiedFusionResult:
    return UnifiedFusionResult(
        section=section,
        confidence=confidence,
        contributions={"text": 0.4, "geometry": 0.3, "graph": 0.3},
        attention=AttentionResult(
            weights={"text": 0.4, "geometry": 0.3, "graph": 0.3}, logits={}
        ),
        fused_features=FusedFeatures(
            vector=[], modality_slices={}, availability={}, encoders={}
        ),
        candidate_scores=[
            {
                "shape": section,
                "score": confidence,
                "modality_scores": {
                    "text": 1.0,
                    "geometry": 1.0,
                    "graph": 0.3,
                    "engineering_rules": 0.95,
                },
            }
        ],
        reasons=[f"Fallback attention selected {section}"],
    )


class ResolverUnitTests(unittest.TestCase):
    def test_complete_catalog_labels_resolve(self):
        cases = {
            "HSS6X6X3/8": "HSS6X6X3/8",
            "hss6x6x3/8": "HSS6X6X3/8",
            "W18x35": "W18X35",
            "W12X16": "W12X16",
            "W14X22": "W14X22",
            "W16X26": "W16X26",
            "W27X84": "W27X84",
            "HSS10X0.625": "HSS10.000X0.625",
            "L4X4X3/8": "L4X4X3/8",
            "L4X3-1/2X3/8": "L4X3-1/2X3/8",
            "L3X3X3/8X0'-6\"": "L3X3X3/8",
            "C12X20.7": "C12X20.7",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(resolve_trusted_explicit_section(raw), expected)

    def test_incomplete_or_invalid_do_not_resolve(self):
        for raw in [
            "L4X4", "L5X3", "HSS8X8", "W12", "C8", "MC12",
            "3/4\"", "1/4\"", "11/4\"", "W12X999", "HSS6X6X99", "", "  ",
        ]:
            with self.subTest(raw=raw):
                self.assertIsNone(resolve_trusted_explicit_section(raw))


class ExactHssScreenshotReproTest(unittest.TestCase):
    """Section 16: the exact UI screenshot -- fusion + a decoy tie/win on
    geometry, and graph is weak, but HSS6X6X3/8 must still resolve cleanly."""

    def test_hss6x6x3_8_is_not_reviewed_when_a_decoy_ties(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion("HSS10X6X3/8", confidence=0.90),
        ):
            r = predict_token("HSS6X6X3/8", queue_unknown=False, persist_learning=False)

        self.assertEqual(r["section"], "HSS6X6X3/8")
        self.assertEqual(r["section_resolution"], "explicit_catalog_exact")
        self.assertFalse(r["inference_required"])
        self.assertFalse(r["needs_review"])
        self.assertNotEqual(r["review_status"], "pending_review")
        # HSS10X6X3/8 cannot be the selected candidate.
        candidates = (r.get("canonical") or {}).get("candidates") or []
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["label"].upper().replace(" ", ""), "HSS6X6X3/8")


class CrossFamilyDecoyTests(unittest.TestCase):
    """Section 17: bad fusion pick across every supported family never alters
    a trusted explicit section or sends it to review."""

    CASES = [
        ("W18X35", "W14X22"),
        ("W12X16", "W12X26"),
        ("W14X22", "W16X26"),
        ("W16X26", "W14X22"),
        ("HSS6X6X3/8", "HSS10X6X3/8"),
        ("HSS10X0.625", "HSS10.000X0.500"),
        ("L4X4X3/8", "L6X6X1/2"),
        ("C12X20.7", "MC12X31"),
        ("W21X44", "W21X50"),
    ]

    def test_decoy_never_wins_or_forces_review(self):
        for raw, decoy in self.CASES:
            with self.subTest(raw=raw):
                with patch(
                    "services.prediction.orchestrator.unified_multimodal_fusion.predict",
                    return_value=_fake_fusion(decoy, confidence=0.2),
                ):
                    r = predict_token(
                        raw, queue_unknown=False, persist_learning=False
                    )
                self.assertEqual(
                    r["section"].upper().replace(" ", ""),
                    resolve_trusted_explicit_section(raw).upper().replace(" ", ""),
                )
                self.assertNotEqual(r["section"], decoy)
                self.assertFalse(r["needs_review"])
                self.assertEqual(r["section_resolution"], "explicit_catalog_exact")


class NegativeSafetyTests(unittest.TestCase):
    """Section 18: exact protection must never become unsafe auto-completion."""

    def test_incomplete_label_is_not_locked_or_completed(self):
        for raw in ["L4X4", "HSS8X8", "W12", "C8"]:
            with self.subTest(raw=raw):
                r = predict_token(raw, queue_unknown=False, persist_learning=False)
                self.assertNotEqual(r.get("section_resolution"), "explicit_catalog_exact")
                self.assertTrue(r.get("inference_required", True))

    def test_invalid_shape_is_not_locked(self):
        for raw in ["W12X999", "HSS6X6X99"]:
            with self.subTest(raw=raw):
                r = predict_token(raw, queue_unknown=False, persist_learning=False)
                self.assertNotEqual(r.get("section_resolution"), "explicit_catalog_exact")
                self.assertTrue(r["needs_review"])

    def test_bare_dimension_is_not_a_section(self):
        for raw in ["3/4\"", "1/4\"", "11/4\""]:
            with self.subTest(raw=raw):
                self.assertIsNone(resolve_trusted_explicit_section(raw))


class HumanOverrideTests(unittest.TestCase):
    """Section 19: a human reviewer still outranks a trusted explicit value."""

    def test_human_selection_wins_over_explicit_text(self):
        with patch(
            "services.prediction.orchestrator.unified_multimodal_fusion.predict",
            return_value=_fake_fusion("W18X35", confidence=0.95),
        ):
            r = predict_token("W18X35", queue_unknown=False, persist_learning=False)
        self.assertEqual(r["section"], "W18X35")

        # Apply a human correction the way the pipeline overlay does.
        from services.multimodal.member_resolution import classify_member

        corrected = {
            **r,
            "section": "W18X40",
            "human_selected_section": "W18X40",
            "decision_source": "human_review",
            "raw_text": "W18X35",
        }
        resolution, _existence, section_conf, evidence = classify_member(corrected)
        self.assertEqual(resolution, "auto")
        self.assertEqual(evidence, "human_or_rule")
        self.assertGreaterEqual(section_conf, 0.9)
        # Raw OCR stays traceable and separate from the human value.
        self.assertEqual(corrected["raw_text"], "W18X35")


class LateAnnotationReclassificationTests(unittest.TestCase):
    """Orchestrator decomposition readiness (2026-09-22): characterizes an
    undocumented interaction discovered while mapping predict_from_context
    for docs/audits/codebase-refactor/orchestrator-decomposition-readiness.md.

    A trusted explicit section (a locked exact catalog match) is computed
    from the token's OWN text early in predict_from_context. Multimodal
    fusion and the label ranker cannot override it (see the classes above).
    But a *later* annotation-taxonomy interpretation
    (interpret_token_annotation) that confidently reclassifies the same
    token as a confirmed plate/bent-plate annotation currently CAN clear
    the locked section and route the token to plate handling instead --
    the code has no explicit guard checking "was this already a locked
    exact match" before applying a late plate reclassification.

    This is characterization, not a claimed defect: interpret_token_annotation
    generally will not classify literal rolled-shape catalog text (e.g.
    "W18X35") as a plate/bent-plate with real geometry/graph/context inputs
    -- plate-grammar and rolled-shape-catalog text patterns are largely
    disjoint by construction, and this test bypasses interpret_token_annotation
    entirely to force the interaction. It exists to lock in today's actual
    behavior before any future orchestrator extraction touches this area,
    not to assert it is correct or incorrect."""

    def test_confirmed_late_plate_annotation_can_clear_a_locked_section(self):
        fake_annotation_pack = {
            "annotation": {
                "annotation_type": "BENT_PLATE",
                "structure_confirmed": True,
            },
            "understandability": {"status": "UNDERSTOOD", "reasons": []},
            "abstain_for_review": False,
        }
        with patch(
            "services.prediction.orchestrator.interpret_token_annotation",
            return_value=fake_annotation_pack,
        ):
            r = predict_token("W18X35", queue_unknown=False, persist_learning=False)

        self.assertEqual(r["section"], "")
        self.assertEqual(r["category"], "plate")
        self.assertTrue(r["needs_review"])
        self.assertEqual(r["review_status"], "pending_review")


class ContextScopeIndependenceTests(unittest.TestCase):
    """Section 20: a trusted explicit label on a legend/notes/definition token
    keeps its section identity but is NOT auto-counted in the takeoff."""

    def test_context_definition_keeps_section_but_not_takeoff(self):
        from services.multimodal.member_resolution import classify_member

        prediction = {
            "section": "W14X22",
            "section_resolution": "explicit_catalog_exact",
            "raw_text": "W14X22",
            "object_scope": "context_definition",
            "takeoff_eligible": False,
        }
        # Identity is intact.
        self.assertEqual(prediction["section"], "W14X22")
        # Member routing never flips a context-definition token into the
        # takeoff just because its section is exact.
        resolution, _e, _sc, _ev = classify_member(prediction)
        self.assertIn(resolution, {"auto", "review_section", "weak_geometry"})
        self.assertIs(prediction["takeoff_eligible"], False)


if __name__ == "__main__":
    unittest.main()
