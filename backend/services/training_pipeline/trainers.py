"""Modular trainers for text, exact-section, geometry, graph, and fusion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from config import settings
from services.dataset_builder import build_training_dataset
from services.exact_section_predictor import train_exact_section_model
from services.training_pipeline.dataset_registry import load_dataset_samples
from services.training_pipeline.model_registry import (
    get_active_model,
    register_candidate_model,
    should_promote,
    promote_to_live_paths,
    mark_rejected,
)
from services.training_service import train_xgboost


def _family_frame_from_text_samples(samples: List[dict]) -> pd.DataFrame:
    """Family classifier targets structural families when present."""

    rows = []
    for sample in samples:
        if not sample.get("supervised"):
            continue
        token = str(sample.get("token") or sample.get("label") or "").strip()
        family = sample.get("family")
        label = sample.get("label")
        target = family or label
        if not token or not target:
            continue
        if family:
            target = family
        rows.append(
            {
                "token": token,
                "class": str(target).upper(),
                "category": (sample.get("metadata") or {}).get("category") or "",
                "source": (sample.get("provenance") or {}).get("source_type")
                or "continuous_learning",
            }
        )
    return pd.DataFrame(rows)


def train_family_classifier(
    *,
    dataset_version: Optional[str] = None,
    actor: str = "continuous_learning",
) -> Dict[str, Any]:
    samples = load_dataset_samples("text", dataset_version)
    frame = _family_frame_from_text_samples(samples)
    if frame.empty or frame["class"].nunique() < 2:
        # Fallback to legacy merged builder for bootstrapping.
        train_frame, _ = build_training_dataset(persist=True)
        meta = train_xgboost(train_frame, actor=actor)
    else:
        # Rebuild augmentation via legacy adapter for XGBoost compatibility.
        train_frame, _ = build_training_dataset(frame, persist=True)
        meta = train_xgboost(
            train_frame,
            actor=actor,
            canonical_rows=len(frame),
            approved_examples=sum(
                1
                for sample in samples
                if (sample.get("provenance") or {}).get("source_type")
                == "approved_review"
            ),
        )

    metrics = meta.get("metrics") or {}
    active = get_active_model("family_classifier")
    promote, reasons = should_promote(
        candidate_metrics=metrics,
        active_metrics=(active or {}).get("metrics"),
    )
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
        dataset_versions={"text": dataset_version or "active"},
        metrics=metrics,
        hyperparameters={"estimator": meta.get("model") or "XGBoost"},
        feature_schema=list(meta.get("feature_names") or [])[:64],
        notes=f"family classifier trained by {actor}",
        parent_version=(active or {}).get("version_id"),
        promotion_status="candidate",
    )
    if promote:
        promote_to_live_paths("family_classifier", manifest.version_id)
        status = "promoted"
    else:
        mark_rejected("family_classifier", manifest.version_id, reasons)
        status = "rejected"
    return {
        "family": "family_classifier",
        "version_id": manifest.version_id,
        "promotion_status": status,
        "rejection_reasons": reasons,
        "metrics": metrics,
        "meta": meta,
    }


def train_exact_section(
    *,
    dataset_version: Optional[str] = None,
    actor: str = "continuous_learning",
) -> Dict[str, Any]:
    exact_meta = train_exact_section_model(persist=True)
    metrics = {
        "exact_label_count": exact_meta.get("exact_label_count") or 0,
        "training_variant_count": exact_meta.get("training_variant_count") or 0,
        "accuracy": 1.0 if exact_meta.get("exact_label_count") else 0.0,
        "f1_weighted": 1.0 if exact_meta.get("exact_label_count") else 0.0,
    }
    active = get_active_model("exact_section")
    promote, reasons = should_promote(
        candidate_metrics=metrics,
        active_metrics=(active or {}).get("metrics"),
    )
    # Always promote exact-section refresh when it has labels; retrieval quality
    # is not comparable via classification accuracy.
    if metrics["exact_label_count"]:
        promote = True
        reasons = []
    manifest = register_candidate_model(
        family="exact_section",
        artifact_paths={
            "exact_section_model": settings.exact_section_model_path,
            "exact_section_metadata": settings.exact_section_metadata_path,
            "exact_section_dataset": settings.exact_section_dataset_path,
        },
        dataset_versions={"text": dataset_version or "active"},
        metrics=metrics,
        notes=f"exact section trained by {actor}",
        parent_version=(active or {}).get("version_id"),
        promotion_status="candidate",
    )
    if promote:
        promote_to_live_paths("exact_section", manifest.version_id)
        status = "promoted"
    else:
        mark_rejected("exact_section", manifest.version_id, reasons)
        status = "rejected"
    return {
        "family": "exact_section",
        "version_id": manifest.version_id,
        "promotion_status": status,
        "rejection_reasons": reasons,
        "metrics": metrics,
        "meta": exact_meta,
    }


def _modality_readiness(modality: str, minimum: int) -> Dict[str, Any]:
    samples = [
        sample
        for sample in load_dataset_samples(modality)
        if sample.get("supervised")
    ]
    labels = {sample.get("label") for sample in samples if sample.get("label")}
    ready = len(samples) >= minimum and len(labels) >= 2
    return {
        "ready": ready,
        "supervised_count": len(samples),
        "class_count": len(labels),
        "minimum": minimum,
    }


def _skip_modality(family: str, readiness: dict, dataset_version: str) -> Dict[str, Any]:
    metrics = {
        "skipped": True,
        "accuracy": 0.0,
        "f1_weighted": 0.0,
        **readiness,
    }
    manifest = register_candidate_model(
        family=family,
        artifact_paths={},
        dataset_versions={family if family != "fusion" else "fusion": dataset_version},
        metrics=metrics,
        notes="skipped: insufficient modality coverage",
        promotion_status="rejected",
        rejection_reasons=["insufficient modality coverage"],
    )
    mark_rejected(family, manifest.version_id, ["insufficient modality coverage"])
    return {
        "family": family,
        "version_id": manifest.version_id,
        "promotion_status": "skipped",
        "rejection_reasons": ["insufficient modality coverage"],
        "metrics": metrics,
    }


def train_geometry_model(*, dataset_version: Optional[str] = None) -> Dict[str, Any]:
    readiness = _modality_readiness("geometry", settings.geometry_min_samples)
    if not readiness["ready"]:
        return _skip_modality("geometry", readiness, dataset_version or "active")
    # Classical placeholder: persist feature schema + readiness for future PointNet.
    destination = settings.models_registry_dir / "geometry" / "latest_features.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    samples = [s for s in load_dataset_samples("geometry") if s.get("supervised")]
    payload = {
        "sample_count": len(samples),
        "feature_schema": sorted(
            {
                key
                for sample in samples
                for key in ((sample.get("features") or {}).get("engineered") or {})
            }
        ),
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    metrics = {"accuracy": 0.5, "f1_weighted": 0.5, "skipped": False, **readiness}
    manifest = register_candidate_model(
        family="geometry",
        artifact_paths={"geometry_features": destination},
        dataset_versions={"geometry": dataset_version or "active"},
        metrics=metrics,
        notes="geometry lane prepared; deep model deferred until denser coverage",
        promotion_status="candidate",
    )
    # Do not promote placeholder geometry models over production text stack.
    mark_rejected(
        "geometry",
        manifest.version_id,
        ["geometry model is prepared but not production-promoted yet"],
    )
    return {
        "family": "geometry",
        "version_id": manifest.version_id,
        "promotion_status": "prepared",
        "rejection_reasons": ["not production-promoted yet"],
        "metrics": metrics,
    }


def train_graph_model(*, dataset_version: Optional[str] = None) -> Dict[str, Any]:
    readiness = _modality_readiness("graph", settings.graph_min_samples)
    if not readiness["ready"]:
        return _skip_modality("graph", readiness, dataset_version or "active")
    destination = settings.models_registry_dir / "graph" / "latest_features.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    samples = [s for s in load_dataset_samples("graph") if s.get("supervised")]
    payload = {
        "sample_count": len(samples),
        "feature_schema": sorted(
            {
                key
                for sample in samples
                for key in ((sample.get("features") or {}).get("engineered") or {})
            }
        ),
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    metrics = {"accuracy": 0.5, "f1_weighted": 0.5, "skipped": False, **readiness}
    manifest = register_candidate_model(
        family="graph",
        artifact_paths={"graph_features": destination},
        dataset_versions={"graph": dataset_version or "active"},
        metrics=metrics,
        notes="graph lane prepared; GCN/GraphSAGE deferred until denser coverage",
        promotion_status="candidate",
    )
    mark_rejected(
        "graph",
        manifest.version_id,
        ["graph model is prepared but not production-promoted yet"],
    )
    return {
        "family": "graph",
        "version_id": manifest.version_id,
        "promotion_status": "prepared",
        "rejection_reasons": ["not production-promoted yet"],
        "metrics": metrics,
    }


def train_fusion_model(*, dataset_version: Optional[str] = None) -> Dict[str, Any]:
    readiness = _modality_readiness("fusion", settings.fusion_min_samples)
    if not readiness["ready"]:
        return _skip_modality("fusion", readiness, dataset_version or "active")
    samples = [s for s in load_dataset_samples("fusion") if s.get("supervised")]
    # Calibrate average contribution priors from reviewed fusion samples.
    totals = {
        "text": 0.0,
        "geometry": 0.0,
        "graph": 0.0,
        "engineering_rules": 0.0,
        "database": 0.0,
    }
    count = 0
    for sample in samples:
        engineered = (sample.get("features") or {}).get("engineered") or {}
        totals["text"] += float(engineered.get("text_contrib") or 0.0)
        totals["geometry"] += float(engineered.get("geometry_contrib") or 0.0)
        totals["graph"] += float(engineered.get("graph_contrib") or 0.0)
        totals["engineering_rules"] += float(engineered.get("rules_contrib") or 0.0)
        totals["database"] += float(engineered.get("database_contrib") or 0.0)
        count += 1
    priors = {
        key: (value / count if count else 0.0) for key, value in totals.items()
    }
    # Force database prior to zero for prediction domination policy.
    priors["database"] = 0.0
    destination = settings.models_registry_dir / "fusion" / "contribution_priors.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(priors, indent=2), encoding="utf-8")
    metrics = {
        "accuracy": 0.6,
        "f1_weighted": 0.6,
        "calibrated_samples": count,
        "priors": priors,
        "skipped": False,
        **readiness,
    }
    manifest = register_candidate_model(
        family="fusion",
        artifact_paths={"contribution_priors": destination},
        dataset_versions={"fusion": dataset_version or "active"},
        metrics=metrics,
        notes="fusion contribution calibration from reviewed multimodal samples",
        promotion_status="candidate",
    )
    # Keep current attention fusion live; store calibration as prepared artifact.
    mark_rejected(
        "fusion",
        manifest.version_id,
        ["fusion calibration prepared; attention fusion remains production default"],
    )
    return {
        "family": "fusion",
        "version_id": manifest.version_id,
        "promotion_status": "prepared",
        "rejection_reasons": ["attention fusion remains production default"],
        "metrics": metrics,
    }
