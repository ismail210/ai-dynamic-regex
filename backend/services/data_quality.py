"""Data quality checks run before training / retraining."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from config import settings


def _frame_from_path(path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def assess_training_data_quality(
    *,
    approved: Optional[pd.DataFrame] = None,
    base: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Detect duplicate samples, invalid labels, imbalance, and outliers.

    This report is advisory and never mutates training files.
    """

    approved = (
        approved
        if approved is not None
        else _frame_from_path(settings.approved_dataset_path)
    )
    base = base if base is not None else _frame_from_path(settings.training_dataset_path)

    frames: List[pd.DataFrame] = []
    if not base.empty:
        frames.append(base.rename(columns={"class": "label"}) if "class" in base else base)
    if not approved.empty:
        renamed = approved.rename(columns={"class": "label"}) if "class" in approved else approved
        frames.append(renamed)

    if not frames:
        return {
            "status": "empty",
            "sample_count": 0,
            "issues": [{"severity": "error", "message": "No training samples available"}],
        }

    df = pd.concat(frames, ignore_index=True, sort=False)
    token_col = "token" if "token" in df.columns else df.columns[0]
    label_col = "label" if "label" in df.columns else ("class" if "class" in df.columns else None)
    issues: List[dict] = []

    duplicate_mask = df.duplicated(subset=[token_col], keep=False)
    duplicate_count = int(duplicate_mask.sum())
    if duplicate_count:
        issues.append(
            {
                "severity": "warning",
                "message": f"{duplicate_count} duplicate token rows detected",
                "code": "duplicate_samples",
            }
        )

    invalid_labels = 0
    if label_col:
        blank = df[label_col].astype(str).str.strip() == ""
        invalid_labels = int(blank.sum())
        if invalid_labels:
            issues.append(
                {
                    "severity": "error",
                    "message": f"{invalid_labels} rows have blank labels",
                    "code": "invalid_labels",
                }
            )

    class_counts: Dict[str, int] = {}
    imbalance_ratio = 0.0
    if label_col:
        class_counts = Counter(df[label_col].astype(str).str.upper().tolist())
        if class_counts:
            max_c = max(class_counts.values())
            min_c = min(class_counts.values())
            imbalance_ratio = round(max_c / max(min_c, 1), 3)
            if imbalance_ratio >= 25:
                issues.append(
                    {
                        "severity": "warning",
                        "message": f"Severe class imbalance (max/min={imbalance_ratio})",
                        "code": "class_imbalance",
                    }
                )

    short_tokens = int((df[token_col].astype(str).str.len() < 2).sum())
    if short_tokens:
        issues.append(
            {
                "severity": "warning",
                "message": f"{short_tokens} unusually short tokens",
                "code": "outliers",
            }
        )

    status = "pass"
    if any(item["severity"] == "error" for item in issues):
        status = "fail"
    elif issues:
        status = "warning"

    return {
        "status": status,
        "sample_count": int(len(df)),
        "approved_count": int(len(approved)),
        "base_count": int(len(base)),
        "duplicate_count": duplicate_count,
        "invalid_label_count": invalid_labels,
        "class_count": len(class_counts),
        "imbalance_ratio": imbalance_ratio,
        "top_classes": dict(Counter(class_counts).most_common(12)),
        "issues": issues,
    }
