"""Versioned model registry with atomic promotion and rollback."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from services.training_pipeline.contracts import MODEL_FAMILIES, ModelManifest
from services.training_pipeline.hashing import checksum_paths


def _family_dir(family: str) -> Path:
    if family not in MODEL_FAMILIES:
        raise ValueError(f"Unknown model family {family!r}")
    path = settings.models_registry_dir / family
    path.mkdir(parents=True, exist_ok=True)
    return path


def _registry_path(family: str) -> Path:
    return _family_dir(family) / "registry.json"


def _load_registry(family: str) -> Dict[str, Any]:
    path = _registry_path(family)
    if not path.exists():
        return {"active_version": None, "versions": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active_version": None, "versions": []}


def _save_registry(family: str, registry: Dict[str, Any]) -> None:
    _registry_path(family).write_text(
        json.dumps(registry, indent=2), encoding="utf-8"
    )


def new_model_version_id(family: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{family}_{stamp}"


def register_candidate_model(
    *,
    family: str,
    artifact_paths: Dict[str, Path],
    dataset_versions: Dict[str, str],
    metrics: Dict[str, Any],
    hyperparameters: Optional[dict] = None,
    feature_schema: Optional[List[str]] = None,
    dependencies: Optional[dict] = None,
    notes: str = "",
    parent_version: Optional[str] = None,
    promotion_status: str = "candidate",
    rejection_reasons: Optional[List[str]] = None,
) -> ModelManifest:
    """Archive model artifacts as an immutable candidate or promoted version."""

    version_id = new_model_version_id(family)
    destination = _family_dir(family) / version_id
    destination.mkdir(parents=True, exist_ok=True)
    saved: Dict[str, str] = {}
    for name, path in artifact_paths.items():
        if not path or not Path(path).exists():
            continue
        target = destination / Path(path).name
        shutil.copy2(path, target)
        saved[name] = str(target)

    manifest = ModelManifest(
        version_id=version_id,
        family=family,
        schema_version=settings.model_schema_version,
        created_at=datetime.now(timezone.utc).isoformat(),
        dataset_versions=dataset_versions,
        metrics=metrics or {},
        hyperparameters=hyperparameters or {},
        feature_schema=list(feature_schema or []),
        artifact_checksums=checksum_paths(Path(p) for p in saved.values()),
        promotion_status=promotion_status,
        rejection_reasons=list(rejection_reasons or []),
        parent_version=parent_version,
        dependencies=dependencies or {},
        notes=notes,
    )
    payload = manifest.to_dict()
    payload["artifacts"] = saved
    (destination / "manifest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    registry = _load_registry(family)
    registry.setdefault("versions", []).append(payload)
    if promotion_status == "promoted":
        registry["active_version"] = version_id
    _save_registry(family, registry)
    return manifest


def mark_promoted(family: str, version_id: str) -> Dict[str, Any]:
    registry = _load_registry(family)
    for entry in registry.get("versions") or []:
        if entry.get("version_id") == version_id:
            entry["promotion_status"] = "promoted"
            registry["active_version"] = version_id
            _save_registry(family, registry)
            return entry
    raise KeyError(f"Unknown model version {version_id!r}")


def mark_rejected(
    family: str, version_id: str, reasons: Optional[List[str]] = None
) -> Dict[str, Any]:
    registry = _load_registry(family)
    for entry in registry.get("versions") or []:
        if entry.get("version_id") == version_id:
            entry["promotion_status"] = "rejected"
            entry["rejection_reasons"] = list(reasons or [])
            _save_registry(family, registry)
            return entry
    raise KeyError(f"Unknown model version {version_id!r}")


def list_model_versions(family: str, limit: int = 20) -> Dict[str, Any]:
    registry = _load_registry(family)
    versions = list(reversed(registry.get("versions") or []))[: max(1, int(limit))]
    return {
        "family": family,
        "active_version": registry.get("active_version"),
        "count": len(registry.get("versions") or []),
        "versions": versions,
    }


def get_active_model(family: str) -> Optional[dict]:
    registry = _load_registry(family)
    active = registry.get("active_version")
    if not active:
        return None
    return next(
        (
            item
            for item in registry.get("versions") or []
            if item.get("version_id") == active
        ),
        None,
    )


def promote_to_live_paths(family: str, version_id: str) -> Dict[str, Any]:
    """Copy archived artifacts into current live deployment aliases."""

    registry = _load_registry(family)
    entry = next(
        (
            item
            for item in registry.get("versions") or []
            if item.get("version_id") == version_id
        ),
        None,
    )
    if not entry:
        raise KeyError(f"Unknown model version {version_id!r}")

    mapping = {
        "family_classifier": {
            "model": settings.model_path,
            "label_encoder": settings.label_encoder_path,
            "preprocessing_pipeline": settings.preprocessing_pipeline_path,
            "feature_names": settings.feature_names_path,
            "model_metadata": settings.model_metadata_path,
            "vectorizer": settings.vectorizer_path,
        },
        "exact_section": {
            "exact_section_model": settings.exact_section_model_path,
            "exact_section_metadata": settings.exact_section_metadata_path,
            "exact_section_dataset": settings.exact_section_dataset_path,
        },
        "geometry": {},
        "graph": {},
        "fusion": {},
    }.get(family, {})

    restored: Dict[str, str] = {}
    artifacts = entry.get("artifacts") or {}
    for key, live_path in mapping.items():
        source = artifacts.get(key)
        if not source:
            # Fall back to matching by filename.
            for path in artifacts.values():
                if Path(path).name == Path(live_path).name:
                    source = path
                    break
        if not source:
            continue
        source_path = Path(source)
        if source_path.exists():
            live_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, live_path)
            restored[key] = str(live_path)

    mark_promoted(family, version_id)
    return {"promoted_to": version_id, "restored": restored, "family": family}


def summarize_all_models() -> Dict[str, Any]:
    return {family: list_model_versions(family, limit=5) for family in MODEL_FAMILIES}


def should_promote(
    *,
    candidate_metrics: Dict[str, Any],
    active_metrics: Optional[Dict[str, Any]] = None,
) -> tuple[bool, List[str]]:
    """Quality gate: promote unless metrics regress beyond configured tolerance."""

    reasons: List[str] = []
    accuracy = float(candidate_metrics.get("accuracy") or 0.0)
    f1 = float(
        candidate_metrics.get("f1_weighted")
        or candidate_metrics.get("f1")
        or 0.0
    )
    if accuracy <= 0 and f1 <= 0:
        # Non-trainable modality placeholders may skip with readiness=false.
        if candidate_metrics.get("skipped"):
            return False, ["training skipped: insufficient modality coverage"]
        reasons.append("missing evaluation metrics")
        return False, reasons

    if not active_metrics:
        return True, []

    active_accuracy = float(active_metrics.get("accuracy") or 0.0)
    active_f1 = float(
        active_metrics.get("f1_weighted") or active_metrics.get("f1") or 0.0
    )
    if accuracy + settings.promotion_accuracy_tolerance < active_accuracy:
        reasons.append(
            f"accuracy regresses {active_accuracy:.4f} -> {accuracy:.4f}"
        )
    if f1 + settings.promotion_f1_tolerance < active_f1:
        reasons.append(f"f1 regresses {active_f1:.4f} -> {f1:.4f}")
    return (len(reasons) == 0), reasons
