"""
Offline builder for the Dynamic Regex Knowledge Base.

Reads the training dataset, and for every engineering class *learns* a regex
from its example tokens using the Regex Learning Engine, validates it, and
writes a rich knowledge-base record into ``training/dynamic_regex.json``.

Run from the ``backend`` directory:

    python -m training.build_dynamic_regex
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from config import settings
from services.regex_knowledge_base import knowledge_base
from services.entity_taxonomy import category_for_aisc_type
from services.regex_learning_engine import learn_regex_with_report
from services.regex_validator import validate_regex


def build() -> None:
    df = pd.read_csv(settings.training_dataset_path)
    now = datetime.now(timezone.utc).isoformat()

    data = {}
    print("\nLearning dynamic regex per class...\n")
    print(f"{'CLASS':6} {'CONF':>6} {'LEVEL':8} PATTERN")
    print("-" * 78)

    for shape_class in sorted(df["class"].astype(str).unique()):
        examples = (
            df[df["class"].astype(str) == shape_class]["token"].astype(str).tolist()
        )

        report = learn_regex_with_report(examples)
        pattern = report["pattern"]
        validation = validate_regex(pattern, examples)
        variants = report.get("variants", [])
        weighted_confidence = sum(
            float(variant.get("confidence", 0)) * float(variant.get("frequency", 0))
            for variant in variants
        )
        confidence = min(0.97, 0.70 * validation.confidence + 0.30 * weighted_confidence)

        data[shape_class] = {
            "pattern": pattern,
            "variants": variants,
            "category": category_for_aisc_type(shape_class),
            "examples": examples[: settings.max_examples_per_class],
            "example_count": len(examples),
            "coverage": round(validation.coverage, 4),
            "confidence": round(confidence, 4),
            "confidence_level": (
                "High" if confidence >= settings.confidence_high_threshold
                else "Medium" if confidence >= settings.confidence_medium_threshold
                else "Low"
            ),
            "distinct_structures": report["distinct_structures"],
            "usage_count": 0,
            "source": "training",
            "created_at": now,
            "updated_at": now,
        }

        print(f"{shape_class:6} {confidence:6.2f} "
              f"{data[shape_class]['confidence_level']:8} {pattern}")

    knowledge_base.reset(data, persist=True)

    print("\nKnowledge base written to:", settings.knowledge_base_path)
    print("Classes learned:", len(data))


if __name__ == "__main__":
    build()
