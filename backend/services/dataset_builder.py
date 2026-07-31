"""Build canonical, augmented, and inspectable feature datasets.

Legacy compatibility adapter. Prefer
``services.training_pipeline.dataset_builder.build_all_modality_datasets`` for
versioned continuous-learning datasets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings
from services.data_augmentation import augment_frame
from services.dataset_manager import dataset_manager
from services.feature_extractor import FEATURE_COLUMNS, extract_feature_frame


DATASET_COLUMNS = ["token", "class", *FEATURE_COLUMNS[1:]]


def enrich_dataset(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Add engineered columns to a token/class frame.

    This materialized dataset is for auditability and analysis. Model training
    still starts with raw tokens and runs feature extraction inside its saved
    scikit-learn preprocessing pipeline.
    """

    if "token" not in frame.columns or "class" not in frame.columns:
        raise ValueError("Dataset must contain 'token' and 'class' columns")

    clean = frame.copy()
    clean["token"] = clean["token"].fillna("").astype(str)
    clean["class"] = clean["class"].fillna("").astype(str).str.strip().str.upper()
    clean = clean[(clean["token"].str.strip() != "") & (clean["class"] != "")]
    features = extract_feature_frame(clean["token"].tolist()).reset_index(drop=True)

    result = pd.concat(
        [
            clean[["token", "class"]].reset_index(drop=True),
            features.drop(columns=["token"]),
        ],
        axis=1,
    )
    for optional_column in ("category", "source"):
        if optional_column in clean.columns:
            result[optional_column] = clean[optional_column].reset_index(drop=True)
    return result


def build_training_dataset(
    canonical: Optional[pd.DataFrame] = None,
    *,
    include_augmentation: Optional[bool] = None,
    persist: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Merge reviewed data, regenerate augmentation, and materialize all features.

    Returns ``(training_frame, feature_frame)``. Augmentation is rebuilt on
    every call so newly approved examples cannot be omitted by a stale cache.
    """

    canonical = (
        dataset_manager.build_merged_training_frame()
        if canonical is None
        else canonical.copy()
    )
    if canonical.empty:
        return canonical, enrich_dataset(
            pd.DataFrame(columns=["token", "class"])
        )

    enabled = (
        settings.augmentation_enabled
        if include_augmentation is None
        else include_augmentation
    )
    if enabled:
        training_frame = augment_frame(
            canonical,
            max_variants_per_token=settings.augmentation_max_variants_per_token,
            include_original=True,
        )
    else:
        training_frame = canonical.copy()
        training_frame["source"] = training_frame.get("source", "original")

    feature_frame = enrich_dataset(training_frame)
    if persist:
        settings.training_dir.mkdir(parents=True, exist_ok=True)
        if enabled:
            training_frame.to_csv(settings.augmented_dataset_path, index=False)
        feature_frame.to_csv(settings.features_dataset_path, index=False)
    return training_frame, feature_frame


def write_enriched_dataset(
    frame: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> Path:
    """Write a rich feature dataset and return its resolved destination."""

    destination = output_path or settings.features_dataset_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    enrich_dataset(frame).to_csv(destination, index=False)
    return destination
