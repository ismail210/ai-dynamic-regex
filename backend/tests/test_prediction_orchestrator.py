"""AI-primary prediction orchestrator contract tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.prediction.contract import to_token_prediction
from services.prediction.orchestrator import predict_token
from services.engineering.suggestion_engine import suggest_for_text_node


class ContractSerializerTests(unittest.TestCase):
    def test_aliases_and_policy_flags(self):
        payload = to_token_prediction(
            token="W18X35",
            family="W",
            section="W18X35",
            confidence={"overall": 0.91, "level": "High"},
            explanation={"summary": "ok", "reasons": ["AI"]},
            evidence={"text": 0.4, "database": 0.05},
            database_match=True,
        )
        self.assertEqual(payload["family"], "W")
        self.assertEqual(payload["section"], "W18X35")
        self.assertEqual(payload["prediction"], "W18X35")
        self.assertEqual(payload["predicted_shape"], "W18X35")
        self.assertEqual(payload["confidence"]["score"], 0.91)
        self.assertEqual(payload["explanation"]["summary"], "ok")
        self.assertNotIn("reasoning", payload)
        self.assertTrue(payload["ai_first"])
        self.assertFalse(payload["database_decides_prediction"])
        self.assertEqual(payload["database_role"], "verification_only")


class OrchestratorPolicyTests(unittest.TestCase):
    def test_database_hit_does_not_override_ai_section(self):
        class FakeFamily:
            label = "W"
            probability = 0.8
            distribution = {"W": 0.8}

            def to_dict(self):
                return {
                    "label": self.label,
                    "probability": self.probability,
                    "top_classes": [],
                }

        class FakeExact:
            shape = "W18X35"
            confidence = 0.93

            def to_dict(self):
                return {"shape": self.shape, "confidence": self.confidence}

        with patch(
            "services.prediction.orchestrator.predict_with_confidence",
            return_value=FakeFamily(),
        ), patch(
            "services.prediction.orchestrator.predict_exact_sections",
            return_value=[FakeExact()],
        ), patch(
            "services.prediction.orchestrator.lookup_shape",
            return_value={"shape": "W21X44", "type": "W"},
        ), patch(
            "services.prediction.orchestrator.suggest_token_corrections",
            return_value=[],
        ), patch(
            "services.self_learning_engine.process_token",
        ) as process_token:
            class Learning:
                pattern = r"W\d+X\d+"
                matched = True
                regex_confidence = 0.9
                regex_level = "High"
                detail = {}

                def to_dict(self):
                    return {"status": "reused", "learned": False, "pattern": self.pattern}

            process_token.return_value = Learning()
            result = predict_token(
                "W18X35", queue_unknown=False, persist_learning=False
            )

        self.assertEqual(result["section"], "W18X35")
        self.assertEqual(result["prediction"], "W18X35")
        self.assertNotEqual(result["section"], "W21X44")
        self.assertTrue(result["database_match"])
        self.assertEqual(result["family"], "W")
        self.assertIn("explanation", result)
        self.assertIn("evidence", result)
        self.assertEqual(result["schema_version"], "2.0")
        explanation = result["explanation"]
        self.assertTrue(explanation["top_candidate_sections"])
        self.assertTrue(explanation["why_selected"])
        self.assertIn("why_rejected", explanation)
        self.assertIn("text_evidence", explanation)
        self.assertIn("geometry_evidence", explanation)
        self.assertIn("graph_evidence", explanation)
        self.assertIn("engineering_evidence", explanation)
        self.assertEqual(
            result["explanation"]["prediction"]["section"], "W18X35"
        )
        self.assertFalse(result["database_decides_prediction"])


class SuggestionEnginePolicyTests(unittest.TestCase):
    def test_suggestion_uses_ai_not_database_shape(self):
        with patch(
            "services.prediction.orchestrator.predict_token",
            return_value={
                "section": "W18X35",
                "family": "W",
                "prediction": "W18X35",
                "confidence": {"overall": 0.88, "level": "High"},
                "database_match": True,
            },
        ):
            suggestion = suggest_for_text_node(
                {"text": "W18X35", "node_id": "n1", "source_id": "s1"},
                graph={"edges": []},
            )
        self.assertEqual(suggestion.expected_label, "W18X35")
        self.assertIn("AI prediction", suggestion.reason)
        self.assertNotIn("Exact AISC database match", suggestion.reason)


if __name__ == "__main__":
    unittest.main()
