"""Train-split-only augmentation with explicit parent sample IDs."""

from __future__ import annotations

from typing import List

from config import settings
from services.data_augmentation import generate_variants_for_token
from services.training_pipeline.hashing import content_hash, sample_id


def augment_text_train_split(samples: List[dict]) -> List[dict]:
    """Augment only supervised text samples in the train split."""

    if not settings.augmentation_enabled:
        return list(samples)

    output = list(samples)
    for sample in samples:
        if sample.get("split") != "train":
            continue
        if not sample.get("supervised"):
            continue
        if sample.get("modality") != "text":
            continue
        token = str(sample.get("token") or "")
        label = str(sample.get("label") or "")
        if not token or not label:
            continue
        variants = generate_variants_for_token(token, label)[
            : settings.augmentation_max_variants_per_token
        ]
        for variant in variants:
            if str(variant).upper().replace(" ", "") == token.upper().replace(" ", ""):
                continue
            payload = {
                "token": str(variant),
                "label": label,
                "family": sample.get("family"),
                "features": {},
                "supervised": True,
            }
            digest = content_hash(modality="text", payload=payload)
            child = {
                **sample,
                "sample_id": sample_id(
                    modality="text",
                    source_type="augmentation",
                    source_id=f"{sample.get('sample_id')}:{variant}",
                    content=digest,
                ),
                "content_hash": digest,
                "token": str(variant),
                "parent_sample_id": sample.get("sample_id"),
                "augmented": True,
                "split": "train",
                "provenance": {
                    **dict(sample.get("provenance") or {}),
                    "source_type": "augmentation",
                    "source_id": f"{sample.get('sample_id')}:{variant}",
                    "parent_sample_id": sample.get("sample_id"),
                },
                "metadata": {
                    **dict(sample.get("metadata") or {}),
                    "augmentation_of": sample.get("token"),
                },
            }
            output.append(child)
    return output
