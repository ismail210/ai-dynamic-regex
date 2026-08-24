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
    encoders: Dict[str, str] = field(default_factory=dict)
    correction: Dict[str, Any] = field(default_factory=dict)
    prediction: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    why_selected: List[str] = field(default_factory=list)
    why_rejected: List[Dict[str, Any]] = field(default_factory=list)
    top_candidate_sections: List[Dict[str, Any]] = field(default_factory=list)
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
    engineer_explanation: Dict[str, Any] = field(default_factory=dict)
    ai_engineer_explanation: Dict[str, Any] = field(default_factory=dict)
    annotation_interpretation: Dict[str, Any] = field(default_factory=dict)

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
    document_id: Optional[str] = None
    canonical: Optional[dict] = None
    raw_text: str = ""
    normalized_text: str = ""
    page_number: Optional[int] = None
    bounding_box: Optional[List[float]] = None
    evidence_source: List[str] = field(default_factory=list)
    prediction_source: str = "Fusion"
    missing_label_prediction: Optional[dict] = None
    # Missing-thickness HSS completion (services.hss_completion): "complete"
    # for an ordinary prediction, "missing_thickness" when known dimensions
    # were read but thickness wasn't -- see canonical_contract.MatchStatus
    # .MISSING_DIMENSION_FIELD, which is what actually nulls `final_label`
    # for this case. These three are additive/informational for the UI.
    completion_status: str = "complete"
    known_dimensions: Optional[List[str]] = None
    candidate_sections: Optional[List[dict]] = None
    plate_annotation_type: Optional[str] = None
    section_prediction_not_applicable: bool = False

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
        payload = {
            "schema_version": "3.0",
            "object_id": self.object_id,
            "document_id": self.document_id,
            "component_id": self.component_id
            or fusion.get("component_id")
            or self.object_id,
            "original_token": self.original_token,
            "corrected_token": self.corrected_token,
            "raw_text": self.raw_text or self.original_token,
            "corrected_text": self.corrected_token,
            "normalized_text": self.normalized_text,
            "page_number": self.page_number,
            "bounding_box": self.bounding_box,
            "evidence_source": self.evidence_source,
            "prediction_source": self.prediction_source,
            "missing_label_prediction": self.missing_label_prediction,
            "plate_annotation_type": self.plate_annotation_type,
            "section_prediction_not_applicable": self.section_prediction_not_applicable,
            "entity_type": self.entity_type,
            "family": family,
            "section": section,
            "material": self.material or fusion.get("material"),
            "confidence": round(self.confidence, 4),
            "alternatives": [item.to_dict() for item in self.alternatives],
            # Candidates, reasons, and per-modality evidence live inside
            # `explanation`. They used to be repeated at the top level, which
            # doubled the size of every prediction on the wire and on disk.
            "explanation": explanation,
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
            "completion_status": self.completion_status,
            "known_dimensions": self.known_dimensions,
            "candidate_sections": self.candidate_sections,
        }
        # Canonical contract (see services.prediction.canonical_contract).
        # New consumers should read from here; the fields above remain only
        # for the migration period (see contract.py::apply_legacy_aliases).
        if self.canonical:
            payload["canonical"] = self.canonical
            payload["source_text"] = self.canonical["source_text"]
            payload["comparison"] = self.canonical["comparison"]
            payload["decision"] = self.canonical["decision"]
            payload["ranking_score"] = self.canonical["prediction"]["ranking_score"]
            payload["final_confidence"] = self.canonical["prediction"][
                "final_confidence"
            ]
            payload["confidence_is_calibrated"] = self.canonical["prediction"][
                "confidence_is_calibrated"
            ]
            payload["canonical_candidates"] = self.canonical["candidates"]
            payload["catalog_version"] = self.canonical["catalog_version"]
            payload["needs_review"] = self.canonical["needs_review"]
            payload["review_reason"] = self.canonical["review_reason"]
            canonical_prediction = self.canonical.get("prediction") or {}
            payload["annotation_type"] = canonical_prediction.get("annotation_type")
            payload["annotation_label"] = canonical_prediction.get("annotation_label")
            payload["section_applicable"] = canonical_prediction.get("section_applicable")
            payload["confidence_basis"] = canonical_prediction.get("confidence_basis")
        return payload


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
