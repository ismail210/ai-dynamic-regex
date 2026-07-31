"""Tests for replaceable encoders and database-free attention decisions."""

from __future__ import annotations

import unittest

from services.multimodal.encoder_contracts import (
    ModalityEncoder,
    ModalityEncoding,
)
from services.multimodal.encoder_registry import EncoderRegistry
from services.multimodal.modular_fusion import UnifiedMultimodalFusion


class FixedEncoder(ModalityEncoder):
    def __init__(self, modality: str, confidence: float, name: str) -> None:
        self.modality = modality
        self.confidence = confidence
        self.name = name

    def encode(self, context):
        return ModalityEncoding(
            modality=self.modality,
            encoder=self.name,
            vector=[self.confidence] * 8,
            confidence=self.confidence,
            available=bool(context.get("available", True)),
            features={"member_role": context.get("member_role")},
            reasons=[f"{self.name} encoded {self.modality}"],
        )


class EncoderRegistryTests(unittest.TestCase):
    def test_encoder_can_be_replaced_without_changing_fusion_contract(self):
        registry = EncoderRegistry(
            [
                FixedEncoder("text", 0.9, "layoutlm_adapter"),
                FixedEncoder("geometry", 0.8, "pointnet_adapter"),
                FixedEncoder("graph", 0.7, "graphsage_adapter"),
                FixedEncoder("engineering_rules", 0.95, "rule_adapter"),
            ]
        )
        registry.register(FixedEncoder("graph", 0.88, "gcn_adapter"))
        encodings = registry.encode_all(
            {
                "text": {},
                "geometry": {},
                "graph": {},
                "engineering_rules": {"member_role": "beam"},
            }
        )
        self.assertEqual(encodings["text"].encoder, "layoutlm_adapter")
        self.assertEqual(encodings["geometry"].encoder, "pointnet_adapter")
        self.assertEqual(encodings["graph"].encoder, "gcn_adapter")
        self.assertEqual(len(encodings["graph"].vector), 8)


class AttentionFusionTests(unittest.TestCase):
    def setUp(self):
        self.encodings = {
            "text": FixedEncoder("text", 0.92, "text").encode({}),
            "geometry": FixedEncoder("geometry", 0.82, "geometry").encode({}),
            "graph": FixedEncoder("graph", 0.78, "graph").encode({}),
            "engineering_rules": FixedEncoder(
                "engineering_rules", 0.9, "rules"
            ).encode({"member_role": "beam"}),
        }

    def test_contributions_sum_to_one_and_database_is_zero(self):
        result = UnifiedMultimodalFusion().predict(
            encodings=self.encodings,
            candidates=[
                {
                    "shape": "W18X35",
                    "evidence": {
                        "text": 0.94,
                        "geometry": 0.85,
                        "graph": 0.8,
                        "engineering_rules": 0.9,
                    },
                },
                {
                    "shape": "HSS8X8X1/2",
                    "evidence": {
                        "text": 0.86,
                        "geometry": 0.6,
                        "graph": 0.55,
                        "engineering_rules": 0.5,
                    },
                },
            ],
            fallback_section="W18X35",
        )
        self.assertEqual(result.section, "W18X35")
        self.assertAlmostEqual(sum(result.contributions.values()), 1.0)
        self.assertEqual(result.contributions["database"], 0.0)
        self.assertEqual(result.attention.database_weight, 0.0)
        self.assertIn("Text contributed", " ".join(result.reasons))
        self.assertTrue(result.candidate_scores)

    def test_database_cannot_be_supplied_as_candidate_modality(self):
        result = UnifiedMultimodalFusion().predict(
            encodings=self.encodings,
            candidates=[
                {
                    "shape": "W18X35",
                    "evidence": {
                        "text": 0.9,
                        "geometry": 0.8,
                        "graph": 0.7,
                        "engineering_rules": 0.9,
                        "database": 0.0,
                    },
                }
            ],
            fallback_section="W18X35",
        )
        self.assertNotIn(
            "database",
            result.candidate_scores[0]["modality_scores"],
        )


if __name__ == "__main__":
    unittest.main()
