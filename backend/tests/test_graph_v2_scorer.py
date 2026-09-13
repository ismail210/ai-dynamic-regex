"""Offline unit tests for Graph v2 candidate-compatibility scorer."""

from __future__ import annotations

import unittest

from services.engineering.graph_v2_scorer import (
    apply_safety_gates,
    build_graph_context,
    family_of,
    is_explicit_complete_section,
    is_incomplete_angle,
    proxy_gold_section,
    score_candidate,
    score_candidates,
)


class GraphV2ScorerBasicsTests(unittest.TestCase):
    def test_family_of_longest_prefix(self) -> None:
        self.assertEqual(family_of("2L4X4X3/8"), "2L")
        self.assertEqual(family_of("L4X4X1/4"), "L")
        self.assertEqual(family_of("HSS8X8X1/2"), "HSS")
        self.assertEqual(family_of("W18X35"), "W")

    def test_incomplete_and_explicit(self) -> None:
        self.assertTrue(is_incomplete_angle("L4x4"))
        self.assertFalse(is_explicit_complete_section("L4x4"))
        self.assertIsNone(proxy_gold_section("L4x4"))

        self.assertTrue(is_explicit_complete_section('L4x3x1/4x6"'))
        self.assertEqual(proxy_gold_section('L4x3x1/4x6"'), "L4X3X1/4")
        self.assertFalse(is_incomplete_angle('L4x3x1/4x6"'))

    def test_score_is_deterministic(self) -> None:
        token = {"raw_text": "W18X35", "object_id": "t1"}
        ctx = {
            "min_distance": 12.0,
            "degree": 4.0,
            "structural_links": 2.0,
            "orientation_bin": "horizontal",
            "geometry_role": "beam",
            "leader_resolved": True,
            "leader_member_count": 1,
            "neighbor_families": ["W", "W", "HSS"],
        }
        a = score_candidate(token, "W18X35", ctx)
        b = score_candidate(token, "W18X35", ctx)
        self.assertEqual(a, b)
        self.assertIn("total_score", a)
        self.assertIn("feature_contributions", a)
        self.assertIn("evidence_used", a)
        self.assertIn("evidence_missing", a)
        self.assertIn("confidence", a)

    def test_does_not_generate_candidates(self) -> None:
        token = {"raw_text": "L4x4"}
        scored = score_candidates(token, ["L4X4X1/4", "L4X3X1/4"], {})
        self.assertEqual(set(scored), {"L4X4X1/4", "L4X3X1/4"})
        # No extra invented keys.
        self.assertEqual(len(scored), 2)

    def test_explicit_label_gate_protects_printed_core(self) -> None:
        ranked = ["L4X3X5/16", "L4X3X1/4", "2L4X3X1/4"]
        gated = apply_safety_gates(
            raw_text='L4x3x1/4x6"',
            ranked_candidates=ranked,
            graph_scores={
                "L4X3X5/16": {"total_score": 0.9, "confidence": 0.9},
                "L4X3X1/4": {"total_score": 0.1, "confidence": 0.1},
            },
        )
        self.assertEqual(gated["selected"], "L4X3X1/4")
        self.assertEqual(gated["reason"], "gate_explicit_protected")

    def test_incomplete_l_abstains(self) -> None:
        gated = apply_safety_gates(
            raw_text="L4x4",
            ranked_candidates=["L4X4X1/4", "L4X3X1/4"],
            graph_scores={
                "L4X4X1/4": {"total_score": 0.99, "confidence": 0.99},
            },
        )
        self.assertEqual(gated["selected"], "")
        self.assertTrue(gated["abstained"])
        self.assertEqual(gated["reason"], "gate_incomplete_abstain")

    def test_weak_evidence_keeps_baseline_order(self) -> None:
        ranked = ["W18X35", "W16X26"]
        gated = apply_safety_gates(
            raw_text="???",  # not explicit complete / not incomplete angle
            ranked_candidates=ranked,
            graph_scores={
                "W16X26": {"total_score": 0.011, "confidence": 0.05},
                "W18X35": {"total_score": 0.010, "confidence": 0.05},
            },
            min_confidence=0.25,
            min_margin=0.02,
        )
        self.assertEqual(gated["selected"], "W18X35")
        self.assertEqual(gated["reason"], "gate_weak_evidence_keep_baseline_order")

    def test_ignores_graphsage_role_in_context_builder(self) -> None:
        prediction = {
            "object_id": "token_1",
            "explanation": {
                "graph_evidence": {
                    "details": {
                        "degree": 3,
                        "structural_links": 1,
                        "min_distance": 10,
                        "node_kind": "brace",
                        "prediction": "beam",  # GraphSAGE — must be ignored
                        "role_prediction": "beam",
                    }
                },
                "geometry_evidence": {
                    "details": {
                        "object": {"kind": "leader", "geometry_role": "other"},
                        "features": {
                            "orientation_bin": "diagonal",
                            "role": "other",
                            "length": 40,
                        },
                    }
                },
            },
        }
        ctx = build_graph_context(prediction=prediction, token_id="token_1")
        self.assertEqual(ctx.get("graphsage_role_ignored"), "beam")
        # Scoring uses brace/other — diagonal + brace should favor L over W.
        token = {"raw_text": "L4X4X1/4", "object_id": "token_1"}
        l_score = score_candidate(token, "L4X4X1/4", ctx)
        w_score = score_candidate(token, "W18X35", ctx)
        self.assertGreaterEqual(l_score["total_score"], w_score["total_score"])

    def test_feature_contributions_sum_to_total(self) -> None:
        token = {"raw_text": "HSS8X8X1/2"}
        ctx = {
            "min_distance": 5.0,
            "degree": 6.0,
            "structural_links": 3.0,
            "orientation_bin": "vertical",
            "geometry_role": "column",
            "leader_hint": True,
            "leader_member_count": 1,
            "neighbor_families": ["HSS", "W"],
        }
        result = score_candidate(token, "HSS8X8X1/2", ctx)
        self.assertAlmostEqual(
            result["total_score"],
            sum(result["feature_contributions"].values()),
            places=5,
        )


class GraphV2NoMutationTests(unittest.TestCase):
    def test_score_candidate_does_not_mutate_token(self) -> None:
        token = {"raw_text": "L4X4X1/4", "section": "L4X4X1/4"}
        before = dict(token)
        score_candidate(token, "L4X4X3/8", {"degree": 2, "min_distance": 8})
        self.assertEqual(token, before)


if __name__ == "__main__":
    unittest.main()
