"""Simple production influence states for multimodal models."""

from __future__ import annotations

import os
from typing import Dict

from services.annotation.taxonomy import ModelState


def _state(env_name: str, default: str = "APPROVED") -> str:
    value = os.getenv(env_name, default).strip().upper()
    if value not in {item.value for item in ModelState}:
        return default
    return value


def model_governance_status() -> Dict[str, str]:
    """EXPERIMENTAL | APPROVED | DISABLED for each evidence model."""

    return {
        "geometry_mobilenet": _state("MODEL_STATE_GEOMETRY", "APPROVED"),
        "graph_graphsage": _state("MODEL_STATE_GRAPH", "APPROVED"),
        "learned_fusion": _state("MODEL_STATE_FUSION", "APPROVED"),
        "label_ranker": _state("MODEL_STATE_LABEL_RANKER", "EXPERIMENTAL"),
    }


def model_may_influence(name: str) -> bool:
    status = model_governance_status().get(name, ModelState.DISABLED.value)
    return status == ModelState.APPROVED.value
