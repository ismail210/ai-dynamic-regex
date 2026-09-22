"""AI-primary prediction orchestrator contract tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.multimodal.encoder_registry import encoder_registry
from services.prediction.contract import to_token_prediction
from services.prediction.orchestrator import predict_token


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


class EncoderInputContractTests(unittest.TestCase):
    """Locks the exact encoder_registry.encode_all() input contract before
    extracting its construction into orchestrator._build_encoder_input --
    see docs/audits/codebase-refactor/orchestrator-decomposition-readiness.md.
    Spies on the real encode_all (via ``wraps``) so behavior is unaffected;
    only the argument it was called with is captured."""

    def _capture_encoder_input(self, token: str) -> dict:
        captured: list = []
        real_encode_all = encoder_registry.encode_all

        def spy(contexts):
            captured.append(contexts)
            return real_encode_all(contexts)

        with patch.object(encoder_registry, "encode_all", side_effect=spy):
            predict_token(token, queue_unknown=False, persist_learning=False)

        self.assertEqual(len(captured), 1, "encode_all must be called exactly once")
        return captured[0]

    def test_exact_match_branch_contract(self):
        contexts = self._capture_encoder_input("W18X35")

        self.assertEqual(
            list(contexts.keys()),
            ["text", "ocr", "layout", "geometry", "graph", "engineering_rules"],
        )
        text = contexts["text"]
        self.assertEqual(
            list(text.keys()),
            ["token", "model_probability", "extraction_confidence",
             "regex_confidence", "candidates"],
        )
        self.assertEqual(text["token"], "W18X35")
        self.assertEqual(text["extraction_confidence"], 0.5)
        self.assertEqual(text["regex_confidence"], 0.0)
        self.assertTrue(text["candidates"])
        self.assertEqual(text["candidates"][0].shape, "W18X35")
        # model_probability is the top exact candidate's own confidence.
        self.assertEqual(
            text["model_probability"], float(text["candidates"][0].confidence)
        )

        self.assertEqual(
            contexts["ocr"],
            {
                "original": "W18X35",
                "corrected": "W18X35",
                "confidence": 0.5,
                "repairs": [],
            },
        )
        self.assertEqual(
            list(contexts["layout"].keys()),
            ["bbox", "page", "reading_order", "font_size", "rotation",
             "member_role", "neighbors"],
        )
        self.assertIsNone(contexts["layout"]["bbox"])
        self.assertEqual(contexts["layout"]["neighbors"], [])
        self.assertEqual(list(contexts["geometry"].keys()), ["geometry"])
        self.assertEqual(list(contexts["graph"].keys()), ["graph"])
        self.assertEqual(list(contexts["engineering_rules"].keys()), ["rules"])

    def test_plate_annotation_branch_contract(self):
        contexts = self._capture_encoder_input("PL 1/2 X 8")

        self.assertEqual(
            list(contexts.keys()),
            ["text", "ocr", "layout", "geometry", "graph", "engineering_rules"],
        )
        self.assertEqual(
            contexts["text"],
            {
                "token": "PL1/2X8",
                "model_probability": 0.0,
                "extraction_confidence": 0.5,
                "regex_confidence": 0.0,
                "candidates": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
