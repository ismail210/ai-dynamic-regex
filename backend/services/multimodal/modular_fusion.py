"""Feature, attention, and confidence fusion for one unified prediction."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional

from services.multimodal.encoder_contracts import (
    AttentionResult,
    FusedFeatures,
    ModalityEncoding,
    UnifiedFusionResult,
)


# Decision priors. Database is intentionally absent from label selection.
ATTENTION_PRIORS = {
    "text": 0.32,
    "ocr": 0.08,
    "layout": 0.08,
    "geometry": 0.30,
    "graph": 0.17,
    "engineering_rules": 0.05,
}


class FeatureFusion:
    """Concatenate encoder vectors behind a stable modality-slice contract."""

    name = "concatenated_feature_fusion_v1"

    def fuse(self, encodings: Dict[str, ModalityEncoding]) -> FusedFeatures:
        vector: List[float] = []
        slices: Dict[str, List[int]] = {}
        availability: Dict[str, bool] = {}
        encoders: Dict[str, str] = {}
        for modality in ATTENTION_PRIORS:
            encoding = encodings[modality]
            start = len(vector)
            vector.extend(float(value) for value in encoding.vector)
            slices[modality] = [start, len(vector)]
            availability[modality] = bool(encoding.available)
            encoders[modality] = encoding.encoder
        return FusedFeatures(
            vector=vector,
            modality_slices=slices,
            availability=availability,
            encoders=encoders,
        )


class AttentionFusion:
    """Quality-conditioned attention over non-database modalities."""

    name = "quality_conditioned_attention_v1"

    def attend(
        self, encodings: Dict[str, ModalityEncoding]
    ) -> AttentionResult:
        logits: Dict[str, float] = {}
        for modality, prior in ATTENTION_PRIORS.items():
            encoding = encodings[modality]
            if not encoding.available:
                continue
            quality = max(0.05, min(1.0, float(encoding.confidence)))
            # Prior anchors expected behavior; quality supplies per-token attention.
            logits[modality] = math.log(prior) + 0.75 * math.log(quality)
        if not logits:
            return AttentionResult(
                weights={"text": 1.0},
                logits={"text": 0.0},
                database_weight=0.0,
            )
        peak = max(logits.values())
        exponentials = {
            modality: math.exp(logit - peak)
            for modality, logit in logits.items()
        }
        total = sum(exponentials.values()) or 1.0
        weights = {
            modality: value / total
            for modality, value in exponentials.items()
        }
        return AttentionResult(
            weights=weights,
            logits=logits,
            database_weight=0.0,
        )


class ConfidenceFusion:
    """Fuse encoder confidence, attention, and candidate separation."""

    name = "attention_confidence_fusion_v1"

    def fuse(
        self,
        encodings: Dict[str, ModalityEncoding],
        attention: AttentionResult,
        candidate_scores: List[Dict[str, Any]],
    ) -> float:
        modality_confidence = sum(
            attention.weights.get(modality, 0.0)
            * float(encoding.confidence)
            for modality, encoding in encodings.items()
        )
        if candidate_scores:
            top = float(candidate_scores[0]["score"])
            second = (
                float(candidate_scores[1]["score"])
                if len(candidate_scores) > 1
                else 0.0
            )
            margin = max(0.0, top - second)
            score = 0.72 * modality_confidence + 0.20 * top + 0.08 * margin
        else:
            score = modality_confidence
        return max(0.0, min(1.0, score))


def _family(shape: str) -> str:
    match = re.match(r"^[A-Z]+", str(shape or "").upper())
    return match.group(0) if match else ""


def _role_compatibility(shape: str, encoding: ModalityEncoding) -> float:
    role = str(encoding.features.get("member_role") or "").lower()
    family = _family(shape)
    if role == "beam":
        return 1.0 if family in {"W", "S", "M", "C", "MC"} else 0.45
    if role == "column":
        return 1.0 if family in {"W", "HSS", "PIPE", "HP"} else 0.5
    if role == "brace":
        return 1.0 if family in {"HSS", "PIPE", "L", "2L"} else 0.55
    return float(encoding.confidence)


class UnifiedMultimodalFusion:
    """Select one section using encoder attention; database cannot participate."""

    name = "unified_multimodal_attention_v1"

    def __init__(
        self,
        *,
        feature_fusion: Optional[FeatureFusion] = None,
        attention_fusion: Optional[AttentionFusion] = None,
        confidence_fusion: Optional[ConfidenceFusion] = None,
    ) -> None:
        self.feature_fusion = feature_fusion or FeatureFusion()
        self.attention_fusion = attention_fusion or AttentionFusion()
        self.confidence_fusion = confidence_fusion or ConfidenceFusion()

    def predict(
        self,
        *,
        encodings: Dict[str, ModalityEncoding],
        candidates: Iterable[Any],
        fallback_section: str,
    ) -> UnifiedFusionResult:
        fused = self.feature_fusion.fuse(encodings)
        attention = self.attention_fusion.attend(encodings)
        scored: List[Dict[str, Any]] = []
        for candidate in candidates:
            shape = str(
                getattr(candidate, "shape", None)
                or (candidate.get("shape") if isinstance(candidate, dict) else "")
            )
            if not shape:
                continue
            evidence = (
                getattr(candidate, "evidence", None)
                or (candidate.get("evidence") if isinstance(candidate, dict) else {})
                or {}
            )
            text_score = float(
                evidence.get("text")
                or getattr(candidate, "text_similarity", 0.0)
                or 0.0
            )
            modality_scores = {
                "text": text_score,
                "ocr": float(encodings["ocr"].confidence),
                "layout": _role_compatibility(
                    shape, encodings["layout"]
                ),
                "geometry": float(
                    evidence.get("geometry")
                    or encodings["geometry"].confidence
                ),
                "graph": float(
                    evidence.get("graph") or encodings["graph"].confidence
                ),
                "engineering_rules": _role_compatibility(
                    shape, encodings["engineering_rules"]
                ),
            }
            final = sum(
                attention.weights.get(modality, 0.0) * score
                for modality, score in modality_scores.items()
            )
            scored.append(
                {
                    "shape": shape,
                    "score": round(max(0.0, min(1.0, final)), 6),
                    "modality_scores": {
                        key: round(value, 4)
                        for key, value in modality_scores.items()
                    },
                }
            )
        scored.sort(key=lambda item: (-item["score"], item["shape"]))
        section = scored[0]["shape"] if scored else fallback_section
        confidence = self.confidence_fusion.fuse(
            encodings, attention, scored
        )

        contributions = {
            modality: float(attention.weights.get(modality, 0.0))
            for modality in ATTENTION_PRIORS
        }
        contributions["database"] = 0.0
        reasons = [
            (
                f"{modality.replace('_', ' ').title()} contributed "
                f"{weight * 100:.1f}% via {encodings[modality].encoder}"
            )
            for modality, weight in attention.weights.items()
        ]
        if scored:
            reasons.append(
                f"Attention fusion selected {section} with score "
                f"{scored[0]['score']:.3f}"
            )
        reasons.append(
            "Database contribution to prediction was 0%; lookup is post-prediction verification"
        )
        return UnifiedFusionResult(
            section=section,
            confidence=confidence,
            contributions=contributions,
            attention=attention,
            fused_features=fused,
            candidate_scores=scored[:8],
            reasons=reasons,
        )


unified_multimodal_fusion = UnifiedMultimodalFusion()
