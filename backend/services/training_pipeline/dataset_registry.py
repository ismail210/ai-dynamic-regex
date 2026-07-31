"""Immutable dataset version registry."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config import settings
from services.training_pipeline.contracts import DatasetManifest, MODALITIES
from services.training_pipeline.hashing import sha256_file, sha256_text


def _modality_dir(modality: str) -> Path:
    if modality not in MODALITIES:
        raise ValueError(f"Unknown modality {modality!r}")
    path = settings.datasets_registry_dir / modality
    path.mkdir(parents=True, exist_ok=True)
    return path


def _registry_path(modality: str) -> Path:
    return _modality_dir(modality) / "registry.json"


def _load_registry(modality: str) -> Dict[str, Any]:
    path = _registry_path(modality)
    if not path.exists():
        return {"active_version": None, "versions": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active_version": None, "versions": []}


def _save_registry(modality: str, registry: Dict[str, Any]) -> None:
    _registry_path(modality).write_text(
        json.dumps(registry, indent=2), encoding="utf-8"
    )


def new_version_id(modality: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{modality}_{stamp}"


def write_dataset_version(
    *,
    modality: str,
    samples: Iterable[dict],
    source_counts: Dict[str, int],
    class_distribution: Dict[str, int],
    split_counts: Dict[str, int],
    feature_schema: List[str],
    parent_versions: Optional[List[str]] = None,
    config: Optional[dict] = None,
    notes: str = "",
    activate: bool = True,
) -> DatasetManifest:
    """Persist an immutable dataset version and update the modality registry."""

    rows = list(samples)
    version_id = new_version_id(modality)
    destination = _modality_dir(modality) / version_id
    destination.mkdir(parents=True, exist_ok=True)
    data_path = destination / "samples.jsonl"
    with data_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    supervised = sum(1 for row in rows if row.get("supervised"))
    unlabeled = len(rows) - supervised
    checksum = sha256_file(data_path)
    manifest = DatasetManifest(
        version_id=version_id,
        modality=modality,
        schema_version=settings.dataset_schema_version,
        created_at=datetime.now(timezone.utc).isoformat(),
        sample_count=len(rows),
        supervised_count=supervised,
        unlabeled_count=unlabeled,
        class_distribution=dict(sorted(class_distribution.items())),
        source_counts=dict(sorted(source_counts.items())),
        split_counts=dict(sorted(split_counts.items())),
        checksum=checksum,
        parent_versions=list(parent_versions or []),
        feature_schema=list(feature_schema),
        config=config or {},
        notes=notes,
    )
    (destination / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
    )
    registry = _load_registry(modality)
    registry.setdefault("versions", []).append(manifest.to_dict())
    if activate:
        registry["active_version"] = version_id
    _save_registry(modality, registry)
    return manifest


def list_dataset_versions(modality: str, limit: int = 20) -> Dict[str, Any]:
    registry = _load_registry(modality)
    versions = list(reversed(registry.get("versions") or []))[: max(1, int(limit))]
    return {
        "modality": modality,
        "active_version": registry.get("active_version"),
        "count": len(registry.get("versions") or []),
        "versions": versions,
    }


def load_dataset_samples(modality: str, version_id: Optional[str] = None) -> List[dict]:
    registry = _load_registry(modality)
    version = version_id or registry.get("active_version")
    if not version:
        return []
    path = _modality_dir(modality) / version / "samples.jsonl"
    if not path.exists():
        return []
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_dataset_manifest(
    modality: str, version_id: Optional[str] = None
) -> Optional[dict]:
    registry = _load_registry(modality)
    version = version_id or registry.get("active_version")
    if not version:
        return None
    path = _modality_dir(modality) / version / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_all_datasets() -> Dict[str, Any]:
    return {modality: list_dataset_versions(modality, limit=5) for modality in MODALITIES}


def fingerprint_samples(samples: Iterable[dict]) -> str:
    return sha256_text(
        "\n".join(
            sorted(
                str(row.get("sample_id") or "") + ":" + str(row.get("content_hash") or "")
                for row in samples
            )
        )
    )
