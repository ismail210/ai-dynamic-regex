"""
Confidence helpers for the AI-primary prediction contract.

Runtime fusion confidence is produced by
``services.multimodal.modular_fusion``. This module only owns shared level
thresholds used after that score is calculated.
"""

from __future__ import annotations

from config import settings
from services.multimodal.modular_fusion import ATTENTION_PRIORS


# Display/documentation weights. Database is verification-only (0.0 for selection).
EVIDENCE_WEIGHTS = {
    **ATTENTION_PRIORS,
    "database": 0.0,
}


def level_from_score(score: float) -> str:
    if score >= settings.confidence_high_threshold:
        return "High"
    if score >= settings.confidence_medium_threshold:
        return "Medium"
    return "Low"
