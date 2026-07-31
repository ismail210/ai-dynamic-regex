"""
One-shot seed CLI: build immutable ``training/training_dataset.csv`` from the AISC workbook.

Runtime retrains never overwrite that CSV — they merge it with approved HITL rows via
``dataset_manager.build_merged_training_frame``. Run manually only when reseeding:

    python -m training.build_dataset
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import settings
from services.database_loader import df


def build_training_dataset(output_path: Path | None = None) -> pd.DataFrame:
    """Export AISC Manual Labels + Types into the immutable training CSV."""

    dataset = [
        {
            "token": str(row["AISC_Manual_Label"]).strip(),
            "class": str(row["Type"]).strip(),
        }
        for _, row in df.iterrows()
    ]
    training_df = pd.DataFrame(dataset)
    path = output_path or settings.training_dataset_path
    path.parent.mkdir(parents=True, exist_ok=True)
    training_df.to_csv(path, index=False)

    print("\nTraining Dataset Created Successfully!\n")
    print(training_df.head(20))
    print("\nTotal Samples:", len(training_df))
    print("Wrote:", path)
    return training_df


if __name__ == "__main__":
    build_training_dataset()
