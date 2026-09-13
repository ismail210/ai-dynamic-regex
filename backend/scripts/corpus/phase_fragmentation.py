"""Generate fragmentation/tokenization variants (Section 14, Case D) from the
v1 clean seed corpus. These are GROUPING examples, not repair examples --
kept in their own file and never mixed into repair_pairs.jsonl.

Usage:
    python phase_fragmentation.py --v1 <v1 dir> --output <v2 dir> --seed 42
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus import corruption_engine as ce  # noqa: E402
from scripts.corpus.common import read_jsonl, write_json, write_jsonl  # noqa: E402
from scripts.corpus.phase_identity_and_ratios import load_split_projects  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    project_to_split = load_split_projects(args.v1)
    rows = []
    n_applicable = 0
    n_total = 0
    for seed_row in read_jsonl(args.v1 / "clean" / "annotations.jsonl"):
        split = project_to_split.get(seed_row["project_id"])
        if split is None:
            continue
        n_total += 1
        rng = ce._rng_for(args.seed, seed_row["seed_id"], "fragmentation")
        result = ce.corrupt_fragmentation(seed_row["canonical_text"], seed_row["family"], rng)
        if result is None:
            continue
        n_applicable += 1
        rows.append({
            "example_id": f"frag_{seed_row['seed_id']}",
            "split": split,
            "source": {
                "project_id": seed_row["project_id"],
                "document_sha256": seed_row["document_sha256"],
                "annotation_id": seed_row["annotation_id"],
                "page": seed_row["page"],
            },
            "clean_text": result.clean_text,
            "fragments": result.fragments,
            "target_operation": result.target_operation,
            "category": result.category,
            "seed": result.seed,
        })

    write_jsonl(args.output / "synthetic" / "fragmented_variants.jsonl", rows)
    summary = {"clean_labels_considered": n_total, "fragmentation_applicable": n_applicable, "fragments_generated": len(rows)}
    write_json(args.output / "inventory" / "fragmentation_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
