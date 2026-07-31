"""Stable contracts for interchangeable multimodal feature/model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class FeatureBundle:
    text: Dict[str, Any] = field(default_factory=dict)
    ocr: Dict[str, Any] = field(default_factory=dict)
    layout: Dict[str, Any] = field(default_factory=dict)
    geometry: Dict[str, Any] = field(default_factory=dict)
    graph: Dict[str, Any] = field(default_factory=dict)
    database: Dict[str, Any] = field(default_factory=dict)
    engineering_rules: Dict[str, Any] = field(default_factory=dict)
    fusion: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AlternativePrediction:
    shape: str
    confidence: float
    entity_type: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "shape": self.shape,
            "confidence": round(self.confidence, 4),
            "entity_type": self.entity_type,
        }


@dataclass
class Explainability:
    text_similarity: float
    geometry_similarity: float
    graph_consistency: float
    database_similarity: float
    ai_probability: float
    regex_contribution: float
    matched_features: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    contributions: Dict[str, float] = field(default_factory=dict)
    contribution_percentages: Dict[str, float] = field(default_factory=dict)
    attention: Dict[str, Any] = field(default_factory=dict)
    candidate_scores: List[Dict[str, Any]] = field(default_factory=list)
    encoders: Dict[str, str] = field(default_factory=dict)
    correction: Dict[str, Any] = field(default_factory=dict)
    prediction: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    why_selected: List[str] = field(default_factory=list)
    why_rejected: List[Dict[str, Any]] = field(default_factory=list)
    top_candidate_sections: List[Dict[str, Any]] = field(default_factory=list)
    modality_evidence: Dict[str, Any] = field(default_factory=dict)
    text_evidence: Dict[str, Any] = field(default_factory=dict)
    ocr_evidence: Dict[str, Any] = field(default_factory=dict)
    layout_evidence: Dict[str, Any] = field(default_factory=dict)
    geometry_evidence: Dict[str, Any] = field(default_factory=dict)
    graph_evidence: Dict[str, Any] = field(default_factory=dict)
    engineering_evidence: Dict[str, Any] = field(default_factory=dict)
    ocr_score: float = 0.0
    layout_score: float = 0.0
    fusion_score: float = 0.0
    matched_neighbors: List[str] = field(default_factory=list)
    correction_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = {
            key: round(value, 4) if isinstance(value, float) else value
            for key, value in asdict(self).items()
        }
        payload["schema_version"] = "2.0"
        return payload


@dataclass
class MultiModalPrediction:
    object_id: str
    original_token: str
    corrected_token: str
    entity_type: str
    predicted_shape: str
    confidence: float
    alternatives: List[AlternativePrediction]
    explainability: Explainability
    feature_bundle: FeatureBundle
    database_match: bool
    review_status: str
    geometry_preview: Optional[dict] = None
    graph_preview: Optional[dict] = None
    component_id: Optional[str] = None
    material: Optional[str] = None

    def to_dict(self) -> dict:
        fusion = self.feature_bundle.fusion or {}
        section = self.predicted_shape
        family = fusion.get("family")
        explanation = self.explainability.to_dict()
        if explanation.get("reasons") and "summary" not in explanation:
            explanation = {
                **explanation,
                "summary": (
                    f"AI predicted family={family or '—'} section={section}"
                ),
            }
        return {
            "schema_version": "2.0",
            "object_id": self.object_id,
            "component_id": self.component_id
            or fusion.get("component_id")
            or self.object_id,
            "original_token": self.original_token,
            "corrected_token": self.corrected_token,
            "entity_type": self.entity_type,
            "family": family,
            "section": section,
            "predicted_shape": section,
            "prediction": section,
            "material": self.material or fusion.get("material"),
            "confidence": {
                "overall": round(self.confidence, 4),
                "score": round(self.confidence, 4),
                "level": (
                    "High"
                    if self.confidence >= 0.80
                    else "Medium"
                    if self.confidence >= 0.55
                    else "Low"
                ),
                "model_probability": round(
                    float(explanation.get("ai_probability") or self.confidence), 4
                ),
                "weights": explanation.get("contributions") or {},
                "breakdown": explanation.get("contributions") or {},
                "database_role": "verification_only",
            },
            "alternatives": [item.to_dict() for item in self.alternatives],
            "explanation": explanation,
            "reasoning": explanation,
            "top_candidate_sections": explanation.get("top_candidate_sections") or [],
            "why_selected": explanation.get("why_selected") or [],
            "why_rejected": explanation.get("why_rejected") or [],
            "text_evidence": explanation.get("text_evidence") or {},
            "ocr_evidence": explanation.get("ocr_evidence") or {},
            "layout_evidence": explanation.get("layout_evidence") or {},
            "geometry_evidence": explanation.get("geometry_evidence") or {},
            "graph_evidence": explanation.get("graph_evidence") or {},
            "engineering_evidence": explanation.get("engineering_evidence") or {},
            "correction": explanation.get("correction") or None,
            "evidence": fusion.get("evidence_contributions") or {},
            "features": self.feature_bundle.to_dict(),
            "database_match": self.database_match,
            "database_role": "verification_only",
            "aisc_confirmed": self.database_match,
            "review_status": self.review_status,
            "geometry_preview": self.geometry_preview,
            "graph_preview": self.graph_preview,
            "ai_first": True,
            "database_decides_prediction": False,
        }


class FeatureProvider(Protocol):
    """Replaceable text, geometry, graph, or vision feature provider."""

    name: str

    def extract(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ...


class FusionModel(ABC):
    """Interchangeable fusion model for classical ML or future deep learning."""

    name: str = "fusion_model"

    @abstractmethod
    def predict(self, context: Dict[str, Any]) -> MultiModalPrediction:
        raise NotImplementedError
