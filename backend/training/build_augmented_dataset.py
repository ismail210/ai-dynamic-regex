"""Offline builder for augmented_dataset.csv (classifier training only)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from services.data_augmentation import augment_dataset_stats
from services.dataset_builder import build_training_dataset
from services.dataset_manager import dataset_manager


def main() -> None:
    frame = dataset_manager.build_merged_training_frame()
    augmented, features = build_training_dataset(frame, persist=True)
    out = settings.augmented_dataset_path
    stats = augment_dataset_stats(len(frame), augmented)
    print("Augmented dataset written:", out)
    print("Engineered feature dataset written:", settings.features_dataset_path)
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
