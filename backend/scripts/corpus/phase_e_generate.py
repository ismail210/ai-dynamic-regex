"""Phase E orchestration: generate the synthetic corruption dataset
independently per split (Section 33 -- generation happens AFTER project
split assignment, never before).

Usage:
    python -m scripts.corpus.phase_e_generate --output <corpus dir> --seed 42
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus import corruption_engine as ce  # noqa: E402
from scripts.corpus.common import read_jsonl, write_json, write_jsonl  # noqa: E402

# Per-clean-example generation budget -- modest pilot, not millions
# (Section 15). Each clean label yields at most this many repair examples
# across the three difficulty-0/1/2 categories combined.
MAX_REPAIR_PER_LABEL = 3
MAX_NORMALIZATION_PER_LABEL = 2


_REPAIR_CATEGORY_FUNCS = [
    ("confusion", lambda text, family, family_start, rng: ce.corrupt_character_confusion(text, family_start, rng)),
    ("deletion", lambda text, family, family_start, rng: ce.corrupt_character_deletion(text, family_start, rng)),
    ("insertion", lambda text, family, family_start, rng: ce.corrupt_character_insertion(text, family_start, rng)),
    ("multi", lambda text, family, family_start, rng: ce.corrupt_multi_step(text, family_start, rng, steps=2)),
    ("decimal", lambda text, family, family_start, rng: ce.corrupt_decimal(text, rng)),
    ("fracrepair", lambda text, family, family_start, rng: ce.corrupt_fraction_repair(text, rng)),
]
_NORMALIZATION_CATEGORY_FUNCS = [
    ("spacing", lambda text, family, rng: ce.corrupt_spacing(text, family, rng)),
    ("separator", lambda text, family, rng: ce.corrupt_separator(text, rng)),
    ("fractyp", lambda text, family, rng: ce.corrupt_fraction_typography(text, rng)),
]


def generate_for_example(seed_row: dict, base_seed: int) -> tuple[list[ce.CorruptionExample], list[ce.CorruptionExample]]:
    text = seed_row["canonical_text"]
    family = seed_row["family"]
    family_start = ce.family_prefix_length(family)

    # Try every category (each with its own deterministic sub-seed so
    # results are reproducible regardless of which categories happen to
    # apply to a given label), THEN sample diversely up to the per-label
    # cap -- a plain list-order truncation would (and, before this fix,
    # did) silently always keep the first few categories and never emit
    # multi-step/decimal/fraction examples at all.
    repair_candidates: list[ce.CorruptionExample] = []
    for name, fn in _REPAIR_CATEGORY_FUNCS:
        rng = ce._rng_for(base_seed, seed_row["seed_id"], name)
        result = fn(text, family, family_start, rng)
        if result:
            repair_candidates.append(result)

    normalization_candidates: list[ce.CorruptionExample] = []
    for name, fn in _NORMALIZATION_CATEGORY_FUNCS:
        rng = ce._rng_for(base_seed, seed_row["seed_id"], name)
        result = fn(text, family, rng)
        if result:
            normalization_candidates.append(result)

    sample_rng = ce._rng_for(base_seed, seed_row["seed_id"], "sample")
    repair_sample = (
        sample_rng.sample(repair_candidates, MAX_REPAIR_PER_LABEL)
        if len(repair_candidates) > MAX_REPAIR_PER_LABEL
        else repair_candidates
    )
    normalization_sample = (
        sample_rng.sample(normalization_candidates, MAX_NORMALIZATION_PER_LABEL)
        if len(normalization_candidates) > MAX_NORMALIZATION_PER_LABEL
        else normalization_candidates
    )
    return repair_sample, normalization_sample


def generate_completion_examples(seed_row: dict, base_seed: int) -> ce.CorruptionExample | None:
    rng = ce._rng_for(base_seed, seed_row["seed_id"], "completion")
    return ce.corrupt_missing_information(seed_row["canonical_text"], seed_row["family"], seed_row["fields"], rng)


def to_dataset_row(example_id: str, seed_row: dict, corruption: ce.CorruptionExample, split: str) -> dict:
    return {
        "example_id": example_id,
        "split": split,
        "source": {
            "project_id": seed_row["project_id"],
            "document_sha256": seed_row["document_sha256"],
            "page": seed_row["page"],
            "annotation_id": seed_row["annotation_id"],
            "bbox": seed_row["semantic_bbox"],
        },
        "clean": {
            "raw_text": seed_row["original_text"],
            "canonical_text": seed_row["canonical_text"],
            "family": seed_row["family"],
            "fields": seed_row["fields"],
        },
        "corrupted": {"text": corruption.corrupted_text},
        "target_operation": corruption.target_operation,
        "category": corruption.category,
        "corruptions": [{"type": s.type, **s.detail} for s in corruption.corruptions],
        "difficulty": corruption.difficulty,
        "seed": corruption.seed,
        "confusion_source": ce.CONFUSION_SOURCE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_dir: Path = args.output
    clean = list(read_jsonl(out_dir / "clean" / "annotations.jsonl"))

    splits_dir = out_dir / "splits"
    split_projects = {
        "train": set((splits_dir / "train_projects.txt").read_text(encoding="utf-8").splitlines()),
        "validation": set((splits_dir / "validation_projects.txt").read_text(encoding="utf-8").splitlines()),
        "test": set((splits_dir / "test_projects.txt").read_text(encoding="utf-8").splitlines()),
    }

    def split_for(project_id: str) -> str | None:
        for split_name, projects in split_projects.items():
            if project_id in projects:
                return split_name
        return None

    repair_rows: list[dict] = []
    normalization_rows: list[dict] = []
    completion_rows: list[dict] = []

    counter = 0
    for seed_row in clean:
        split = split_for(seed_row["project_id"])
        if split is None:
            continue
        repair_examples, normalization_examples = generate_for_example(seed_row, args.seed)
        for ex in repair_examples:
            counter += 1
            repair_rows.append(to_dataset_row(f"ex_{counter:07d}", seed_row, ex, split))
        for ex in normalization_examples:
            counter += 1
            normalization_rows.append(to_dataset_row(f"ex_{counter:07d}", seed_row, ex, split))
        completion_ex = generate_completion_examples(seed_row, args.seed)
        if completion_ex:
            counter += 1
            completion_rows.append(to_dataset_row(f"ex_{counter:07d}", seed_row, completion_ex, split))

    write_jsonl(out_dir / "synthetic" / "repair_pairs.jsonl", repair_rows)
    write_jsonl(out_dir / "synthetic" / "normalization_variants.jsonl", normalization_rows)
    write_jsonl(out_dir / "synthetic" / "completion_examples.jsonl", completion_rows)

    def counts_by(rows, key_fn):
        out: dict = {}
        for r in rows:
            k = key_fn(r)
            out[k] = out.get(k, 0) + 1
        return out

    summary = {
        "seed": args.seed,
        "clean_seed_total": len(clean),
        "repair_pairs_total": len(repair_rows),
        "repair_by_split": counts_by(repair_rows, lambda r: r["split"]),
        "repair_by_category": counts_by(repair_rows, lambda r: r["category"]),
        "repair_by_difficulty": counts_by(repair_rows, lambda r: r["difficulty"]),
        "normalization_variants_total": len(normalization_rows),
        "completion_examples_total": len(completion_rows),
        "confusion_source": ce.CONFUSION_SOURCE,
    }
    write_json(out_dir / "inventory" / "phase_e_summary.json", summary)
    import json
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
