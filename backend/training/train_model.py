"""Offline entry point for the production feature-engineered trainer."""

from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.data_augmentation import augment_dataset_stats
from services.dataset_builder import build_training_dataset
from services.dataset_manager import dataset_manager
from services.training_service import train_models


def main() -> dict:
    canonical = dataset_manager.build_merged_training_frame()
    training_frame, feature_frame = build_training_dataset(
        canonical,
        persist=True,
    )
    metadata = train_models(
        training_frame,
        actor="offline",
        canonical_rows=len(canonical),
        approved_examples=dataset_manager.approved_count(),
        augmentation=augment_dataset_stats(len(canonical), training_frame),
    )
    print(
        json.dumps(
            {
                "model": metadata["model"],
                "metrics": metadata["metrics"],
                "training_rows": len(training_frame),
                "feature_rows": len(feature_frame),
                "artifacts": metadata["artifacts"],
            },
            indent=2,
        )
    )
    return metadata


if __name__ == "__main__":
    main()
