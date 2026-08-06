"""Contracts for replaceable multimodal encoders and fusion stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ModalityEncoding:
    """Fixed contract returned by every encoder implementation."""

    modality: str
    encoder: str
    vector: List[float]
    confidence: float
    available: bool = True
    features: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self, *, include_vector: bool = True) -> Dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = round(float(self.confidence), 4)
        payload["dimension"] = len(self.vector)
        if include_vector:
            payload["vector"] = [round(float(value), 6) for value in self.vector]
        else:
            # The fused vector already carries every modality slice, so the
            # per-modality copies are omitted from API and artifact payloads.
            payload.pop("vector", None)
        return payload


class ModalityEncoder(ABC):
    """Pluggable encoder boundary for classical and future neural models."""

    modality: str = "unknown"
    name: str = "encoder"
    output_dimension: int = 8

    @abstractmethod
    def encode(self, context: Dict[str, Any]) -> ModalityEncoding:
        raise NotImplementedError


@dataclass
class FusedFeatures:
    vector: List[float]
    modality_slices: Dict[str, List[int]]
    availability: Dict[str, bool]
    encoders: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vector": [round(float(value), 6) for value in self.vector],
            "modality_slices": self.modality_slices,
            "availability": self.availability,
            "encoders": self.encoders,
        }


@dataclass
class AttentionResult:
    weights: Dict[str, float]
    logits: Dict[str, float]
    database_weight: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weights": {
                key: round(float(value), 4) for key, value in self.weights.items()
            },
            "percentages": {
                key: round(float(value) * 100.0, 1)
                for key, value in self.weights.items()
            },
            "logits": {
                key: round(float(value), 4) for key, value in self.logits.items()
            },
            "database": round(float(self.database_weight), 4),
        }


@dataclass
class UnifiedFusionResult:
    section: str
    confidence: float
    contributions: Dict[str, float]
    attention: AttentionResult
    fused_features: FusedFeatures
    candidate_scores: List[Dict[str, Any]]
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section": self.section,
            "confidence": round(float(self.confidence), 4),
            "contributions": {
                key: round(float(value), 4)
                for key, value in self.contributions.items()
            },
            "contribution_percentages": {
                key: round(float(value) * 100.0, 1)
                for key, value in self.contributions.items()
            },
            "attention": self.attention.to_dict(),
            "fused_features": self.fused_features.to_dict(),
            "candidate_scores": self.candidate_scores,
            "reasons": self.reasons,
            "database_decides_prediction": False,
        }
