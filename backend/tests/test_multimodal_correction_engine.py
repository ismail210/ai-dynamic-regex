"""Regex-free multimodal correction behavior and contract tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.multimodal.correction_engine import (
    MultimodalCorrectionEngine,
)


class Candidate:
    def __init__(self, shape, confidence, text_similarity):
        self.shape = shape
        self.confidence = confidence
        self.text_similarity = text_similarity
        self.evidence = {
            "text": text_similarity,
            "geometry": 0.82,
            "graph": 0.76,
            "engineering_rules": 0.9,
        }


class MultimodalCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.engine = MultimodalCorrectionEngine()
        self.context = {
            "expected_family": "W",
            "geometry": {"available": True, "similarity": 0.82},
            "graph": {
                "degree": 3,
                "structural_links": 2,
                "graph_consistency": 0.76,
            },
            "engineering_context": {
                "score": 0.9,
                "member_role": "beam",
            },
        }

    def _candidates(self):
        return [
            Candidate("W18X35", 0.94, 0.94),
            Candidate("W18X40", 0.79, 0.79),
            Candidate("HSS8X8X1/2", 0.35, 0.3),
        ]

    def test_required_ocr_and_separator_examples(self):
        for token in ("W18X3S", "WF18X35", "W18 35", "W1835"):
            with self.subTest(token=token), patch(
                "services.multimodal.correction_engine._reviewed_examples",
                return_value=[],
            ):
                result = self.engine.correct(
                    token,
                    similarity_candidates=self._candidates(),
                    **self.context,
                )
                self.assertIsNotNone(result)
                self.assertEqual(result.corrected, "W18X35")
                self.assertGreater(result.confidence, 0.7)
                self.assertTrue(result.reason)
                self.assertIn("signals", result.evidence)
                self.assertIn("contributions", result.evidence)
                self.assertTrue(result.alternative_candidates)
                payload = result.to_dict()
                self.assertEqual(payload["original"], token)
                self.assertFalse(payload["regex_used"])
                self.assertFalse(payload["database_used"])

    def test_reviewed_example_contributes_to_correction(self):
        examples = [
            {
                "original": "HSS6X6Xl/2",
                "corrected": "HSS6X6X1/2",
                "source": "human_review",
            }
        ]
        with patch(
            "services.multimodal.correction_engine._reviewed_examples",
            return_value=examples,
        ), patch(
            "services.multimodal.correction_engine.predict_exact_sections",
            return_value=[],
        ):
            result = self.engine.correct(
                "HSS6X6Xl/2",
                expected_family="HSS",
                geometry={"available": False},
                graph={"degree": 0},
                engineering_context={"score": 0.85},
                candidate_sections=["HSS6X6X1/2", "HSS6X6X3/8"],
            )
        self.assertEqual(result.corrected, "HSS6X6X1/2")
        self.assertIsNotNone(result.evidence["reviewed_example"])
        self.assertGreater(result.evidence["signals"]["review_history"], 0.9)

    def test_missing_label_uses_contextual_candidates(self):
        with patch(
            "services.multimodal.correction_engine._reviewed_examples",
            return_value=[],
        ), patch(
            "services.multimodal.correction_engine.predict_exact_sections",
            return_value=[],
        ):
            result = self.engine.correct(
                "",
                expected_family="W",
                geometry={"available": True, "similarity": 0.8},
                graph={"degree": 2, "graph_consistency": 0.75},
                engineering_context={"score": 0.9, "member_role": "beam"},
                candidate_sections=["W18X35", "HSS8X8X1/2"],
            )
        self.assertEqual(result.corrected, "W18X35")
        self.assertIn("missing_label", result.issue_types)


if __name__ == "__main__":
    unittest.main()
