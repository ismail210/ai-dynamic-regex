"""Materialize the rich feature dataset without fitting a model."""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.dataset_builder import build_training_dataset


if __name__ == "__main__":
    _, feature_frame = build_training_dataset(persist=True)
    print(feature_frame.head(20).to_string(index=False))
    print(f"\nTotal samples: {len(feature_frame)}")
