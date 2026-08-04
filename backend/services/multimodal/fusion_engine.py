"""
Classical multimodal fusion engine (AI-first).

Thin adapter over ``services.prediction.orchestrator``. Kept for backward
compatibility with ``FusionModel`` / multimodal pipeline contracts.
"""

from __future__ import annotations

from typing import Any, Dict

from services.multimodal.contracts import (
    AlternativePrediction,
    Explainability,
    FeatureBundle,
    FusionModel,
    MultiModalPrediction,
)


from services.multimodal.modular_fusion import ATTENTION_PRIORS

# Compatibility export. Runtime label selection uses ATTENTION_PRIORS.
# Database remains verification-only and never participates in selection.
FUSION_WEIGHTS = {
    **ATTENTION_PRIORS,
    "database": 0.0,
}


class WeightedFusionEngine(FusionModel):
    """Explainable multimodal fusion delegated to the AI-primary orchestrator."""

    name = "weighted_classical_multimodal_v2_ai_first"

    def predict(self, context: Dict[str, Any]) -> MultiModalPrediction:
        from services.prediction.orchestrator import predict_from_context

        result = predict_from_context(context)
        features = result.get("features") or {}
        explanation = result.get("explanation") or result.get("reasoning") or {}
        confidence = result.get("confidence") or {}
        overall = float(
            confidence.get("overall")
            if isinstance(confidence, dict)
            else confidence
            or 0.0
        )

        alternatives = [
            AlternativePrediction(
                shape=str(item.get("shape")),
                confidence=float(item.get("confidence") or 0.0),
                entity_type=item.get("entity_type"),
            )
            for item in (result.get("alternatives") or [])
            if item.get("shape")
        ]

        bundle = FeatureBundle(
            text=features.get("text") or {},
            ocr=features.get("ocr") or {},
            layout=features.get("layout") or {},
            geometry=features.get("geometry") or {},
            graph=features.get("graph") or {},
            database=features.get("database") or {},
            engineering_rules=features.get("engineering_rules") or {},
            fusion={
                **(features.get("fusion") or {}),
                "family": result.get("family"),
                "section": result.get("section"),
            },
        )
        return MultiModalPrediction(
            object_id=str(result.get("object_id") or result.get("component_id") or ""),
            original_token=str(result.get("original_token") or result.get("token") or ""),
            corrected_token=str(
                result.get("corrected_token") or result.get("section") or ""
            ),
            entity_type=str(result.get("entity_type") or result.get("category") or ""),
            predicted_shape=str(result.get("section") or result.get("prediction") or ""),
            confidence=overall,
            alternatives=alternatives,
            explainability=Explainability(
                text_similarity=float(explanation.get("text_similarity") or 0.0),
                geometry_similarity=float(
                    explanation.get("geometry_similarity") or 0.0
                ),
                graph_consistency=float(explanation.get("graph_consistency") or 0.0),
                database_similarity=float(
                    explanation.get("database_similarity") or 0.0
                ),
                ai_probability=float(explanation.get("ai_probability") or overall),
                regex_contribution=float(
                    explanation.get("regex_contribution") or 0.0
                ),
                matched_features=list(explanation.get("matched_features") or []),
                reasons=list(explanation.get("reasons") or []),
                contributions=dict(explanation.get("contributions") or {}),
                contribution_percentages=dict(
                    explanation.get("contribution_percentages") or {}
                ),
                attention=dict(explanation.get("attention") or {}),
                candidate_scores=list(
                    explanation.get("candidate_scores") or []
                ),
                encoders=dict(explanation.get("encoders") or {}),
                correction=dict(explanation.get("correction") or {}),
                prediction=dict(explanation.get("prediction") or {}),
                confidence=float(explanation.get("confidence") or overall),
                why_selected=list(explanation.get("why_selected") or []),
                why_rejected=list(explanation.get("why_rejected") or []),
                top_candidate_sections=list(
                    explanation.get("top_candidate_sections") or []
                ),
                modality_evidence=dict(
                    explanation.get("modality_evidence") or {}
                ),
                text_evidence=dict(explanation.get("text_evidence") or {}),
                ocr_evidence=dict(explanation.get("ocr_evidence") or {}),
                layout_evidence=dict(
                    explanation.get("layout_evidence") or {}
                ),
                ocr_score=float(explanation.get("ocr_score") or 0.0),
                layout_score=float(
                    explanation.get("layout_score") or 0.0
                ),
                fusion_score=float(
                    explanation.get("fusion_score") or overall
                ),
                matched_neighbors=list(
                    explanation.get("matched_neighbors") or []
                ),
                correction_history=list(
                    explanation.get("correction_history") or []
                ),
                geometry_evidence=dict(
                    explanation.get("geometry_evidence") or {}
                ),
                graph_evidence=dict(explanation.get("graph_evidence") or {}),
                engineering_evidence=dict(
                    explanation.get("engineering_evidence") or {}
                ),
            ),
            feature_bundle=bundle,
            database_match=bool(result.get("database_match")),
            review_status=str(result.get("review_status") or "pending_review"),
            geometry_preview=result.get("geometry_preview"),
            graph_preview=result.get("graph_preview"),
            component_id=result.get("component_id"),
            material=result.get("material"),
            document_id=result.get("document_id"),
            canonical=result.get("canonical"),
        )


fusion_engine = WeightedFusionEngine()
