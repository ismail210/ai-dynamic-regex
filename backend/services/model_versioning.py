"""Model versioning, metadata, and rollback support contracts.

Compatibility wrapper over the continuous-learning model registry.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from config import settings
from services.training_pipeline.model_registry import (
    list_model_versions as list_family_versions,
    promote_to_live_paths,
    register_candidate_model,
)


def register_model_version(
    *,
    metrics: Optional[dict] = None,
    notes: str = "",
    source: str = "retrain",
) -> Dict[str, Any]:
    """
    Snapshot current production artifacts into a versioned folder.

    Existing active model files remain the live deployment; this archives and
    marks the snapshot as promoted for the family classifier.
    """

    manifest = register_candidate_model(
        family="family_classifier",
        artifact_paths={
            "model": settings.model_path,
            "label_encoder": settings.label_encoder_path,
            "preprocessing_pipeline": settings.preprocessing_pipeline_path,
            "feature_names": settings.feature_names_path,
            "model_metadata": settings.model_metadata_path,
            "vectorizer": settings.vectorizer_path,
        },
        dataset_versions={"text": "live_snapshot"},
        metrics=metrics or {},
        notes=notes or f"snapshot from {source}",
        promotion_status="promoted",
    )
    return {
        "version_id": manifest.version_id,
        "created_at": manifest.created_at,
        "source": source,
        "notes": notes,
        "metrics": metrics or {},
        "rollback_supported": True,
    }


def list_model_versions(limit: int = 20) -> Dict[str, Any]:
    payload = list_family_versions("family_classifier", limit=limit)
    return {
        "active_version": payload.get("active_version"),
        "count": payload.get("count"),
        "versions": payload.get("versions") or [],
        "families": {
            "family_classifier": payload,
        },
    }


def rollback_model_version(version_id: str) -> Dict[str, Any]:
    """Restore a previously archived model version into the live paths."""

    return promote_to_live_paths("family_classifier", version_id)
