"""Build and version text, geometry, graph, and fusion datasets."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from config import settings
from services.training_pipeline.augmentation import augment_text_train_split
from services.training_pipeline.dataset_registry import write_dataset_version
from services.training_pipeline.feature_engineering import (
    apply_feature_engineering,
    feature_schema_for,
)
from services.training_pipeline.preprocessing import (
    preprocess_samples,
    summarize_classes,
    summarize_splits,
)
from services.training_pipeline.source_ingestion import ingest_all_sources


def _source_counts(samples: List[dict]) -> Dict[str, int]:
    counts: Counter = Counter()
    for sample in samples:
        counts[str((sample.get("provenance") or {}).get("source_type") or "unknown")] += 1
    return dict(counts)


def build_modality_dataset(
    modality: str,
    samples: List[dict],
    *,
    parent_versions: Optional[List[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    prepared = preprocess_samples(samples)
    featured = apply_feature_engineering(prepared, modality)
    if modality == "text":
        featured = augment_text_train_split(featured)
        featured = apply_feature_engineering(featured, modality)

    manifest = write_dataset_version(
        modality=modality,
        samples=featured,
        source_counts=_source_counts(featured),
        class_distribution=summarize_classes(featured),
        split_counts=summarize_splits(featured),
        feature_schema=feature_schema_for(modality),
        parent_versions=parent_versions,
        config={
            "augmentation_enabled": settings.augmentation_enabled,
            "dataset_schema_version": settings.dataset_schema_version,
        },
        notes=notes,
        activate=True,
    )
    return {
        "manifest": manifest.to_dict(),
        "sample_count": len(featured),
        "supervised_count": sum(1 for row in featured if row.get("supervised")),
    }


def build_all_modality_datasets(
    *,
    notes: str = "continuous learning dataset build",
) -> Dict[str, Any]:
    ingested = ingest_all_sources()
    results = {}
    for modality, samples in ingested["by_modality"].items():
        results[modality] = build_modality_dataset(
            modality,
            samples,
            notes=notes,
        )
    return {
        "source_counts": ingested["source_counts"],
        "total_ingested": ingested["total"],
        "datasets": results,
    }
