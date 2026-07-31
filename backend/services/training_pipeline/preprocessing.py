"""Modality-agnostic preprocessing and split assignment."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Dict, Iterable, List


def _stable_bucket(sample_id: str) -> float:
    digest = hashlib.sha256(sample_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def assign_split(sample_id: str, *, train=0.8, validation=0.1) -> str:
    score = _stable_bucket(sample_id)
    if score < train:
        return "train"
    if score < train + validation:
        return "validation"
    return "test"


def preprocess_samples(samples: Iterable[dict]) -> List[dict]:
    """Cleanup types, normalize labels, and assign immutable splits."""

    cleaned: List[dict] = []
    for sample in samples:
        row = dict(sample)
        row["token"] = str(row.get("token") or "").strip()
        label = str(row.get("label") or row.get("section") or "").strip().upper()
        row["label"] = label or None
        row["section"] = label or None
        row["supervised"] = bool(row.get("supervised") and label)
        row["features"] = dict(row.get("features") or {})
        row["provenance"] = dict(row.get("provenance") or {})
        row["metadata"] = dict(row.get("metadata") or {})
        row["split"] = assign_split(str(row.get("sample_id") or row.get("content_hash")))
        if not row.get("quality_status"):
            row["quality_status"] = "unknown"
        cleaned.append(row)
    return cleaned


def summarize_splits(samples: Iterable[dict]) -> Dict[str, int]:
    return dict(Counter(str(sample.get("split") or "train") for sample in samples))


def summarize_classes(samples: Iterable[dict]) -> Dict[str, int]:
    counts: Counter = Counter()
    for sample in samples:
        if sample.get("supervised") and sample.get("label"):
            counts[str(sample["label"])] += 1
    return dict(counts)
