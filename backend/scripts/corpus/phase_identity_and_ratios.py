"""Section 2/4/8/9 -- build v2's clean identity layer and the clean:corrupt
ratio-balance datasets from v1's already-generated clean seed + repair pairs.

Identity examples (Layer 1, Section 2): one KEEP record per clean label.

Ratio datasets (Section 8): for each clean label, emit 1 KEEP example plus
up to N REPAIR examples (N = 1, 2, 4) drawn from that SAME label's own
already-generated corruptions in v1's repair_pairs.jsonl (never regenerated
independently, so ratio comparison isn't confounded by different corruption
draws). Normalization and completion examples are excluded from these files
per Section 9/40 -- they are separate actions, not repair-balance data.

Usage:
    python phase_identity_and_ratios.py --v1 <v1 dir> --output <v2 dir>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import read_jsonl, write_json, write_jsonl  # noqa: E402


def load_split_projects(v1_dir: Path) -> dict[str, str]:
    splits_dir = v1_dir / "splits"
    project_to_split: dict[str, str] = {}
    for split_name in ("train", "validation", "test"):
        for line in (splits_dir / f"{split_name}_projects.txt").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                project_to_split[line] = split_name
    return project_to_split


def build_identity_examples(v1_dir: Path, project_to_split: dict[str, str]) -> list[dict]:
    rows = []
    for seed_row in read_jsonl(v1_dir / "clean" / "annotations.jsonl"):
        split = project_to_split.get(seed_row["project_id"])
        if split is None:
            continue
        rows.append({
            "example_id": f"keep_{seed_row['seed_id']}",
            "split": split,
            "source": {
                "project_id": seed_row["project_id"],
                "document_sha256": seed_row["document_sha256"],
                "page": seed_row["page"],
                "annotation_id": seed_row["annotation_id"],
            },
            "input": seed_row["canonical_text"],
            "target": seed_row["canonical_text"],
            "action": "KEEP",
            "family": seed_row["family"],
            "key": (seed_row["document_sha256"], seed_row["annotation_id"]),
        })
    return rows


def build_ratio_dataset(identity_rows: list[dict], repair_by_key: dict, ratio: int) -> tuple[list[dict], dict]:
    out: list[dict] = []
    achieved_counts = []
    for identity in identity_rows:
        key = identity["key"]
        out.append({k: v for k, v in identity.items() if k != "key"})
        available = repair_by_key.get(key, [])
        take = available[:ratio]
        achieved_counts.append(len(take))
        for corrupt_row in take:
            out.append({
                "example_id": corrupt_row["example_id"],
                "split": corrupt_row["split"],
                "source": corrupt_row["source"],
                "input": corrupt_row["corrupted"]["text"],
                "target": corrupt_row["clean"]["canonical_text"],
                "action": "REPAIR",
                "family": corrupt_row["clean"]["family"],
            })
    n_labels = len(identity_rows)
    n_corrupt = sum(achieved_counts)
    stats = {
        "target_ratio_clean_to_corrupt": f"1:{ratio}",
        "clean_examples": n_labels,
        "corrupt_examples": n_corrupt,
        "achieved_ratio": round(n_labels / n_corrupt, 4) if n_corrupt else None,
        "labels_with_fewer_than_target_corruptions": sum(1 for c in achieved_counts if c < ratio),
    }
    return out, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    project_to_split = load_split_projects(args.v1)

    # Verify split integrity (Section 7) before anything else.
    train = {p for p, s in project_to_split.items() if s == "train"}
    val = {p for p, s in project_to_split.items() if s == "validation"}
    test = {p for p, s in project_to_split.items() if s == "test"}
    overlaps = (train & val) | (train & test) | (val & test)
    if overlaps:
        raise SystemExit(f"LEAKAGE: projects appear in multiple splits: {overlaps}")
    print(f"Split verification OK: {len(train)} train / {len(val)} val / {len(test)} test projects, 0 overlap.")

    identity_rows = build_identity_examples(args.v1, project_to_split)
    write_jsonl(args.output / "clean" / "identity_examples.jsonl", [
        {k: v for k, v in r.items() if k != "key"} for r in identity_rows
    ])
    print(f"Identity (KEEP) examples: {len(identity_rows)}")

    repair_by_key: dict = {}
    for row in read_jsonl(args.v1 / "synthetic" / "repair_pairs.jsonl"):
        key = (row["source"]["document_sha256"], row["source"]["annotation_id"])
        repair_by_key.setdefault(key, []).append(row)

    ratio_stats = {}
    for ratio in (1, 2, 4):
        rows, stats = build_ratio_dataset(identity_rows, repair_by_key, ratio)
        out_path = args.output / "synthetic" / f"repair_pairs_ratio_1_{ratio}.jsonl"
        write_jsonl(out_path, rows)
        ratio_stats[f"1:{ratio}"] = stats
        print(f"ratio 1:{ratio} -> {out_path.name}: {stats}")

    write_json(args.output / "inventory" / "ratio_balance_summary.json", ratio_stats)

    # Copy split files forward unchanged (Section 7 -- same project assignment).
    splits_out = args.output / "splits"
    splits_out.mkdir(parents=True, exist_ok=True)
    for split_name in ("train", "validation", "test"):
        src = args.v1 / "splits" / f"{split_name}_projects.txt"
        (splits_out / f"{split_name}_projects.txt").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print("Split files copied forward unchanged (byte-identical project assignment).")


if __name__ == "__main__":
    main()
