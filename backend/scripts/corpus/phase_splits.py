"""Project-level train/validation/test splits (Section 16).

Splits by PROJECT, never by annotation or page -- a project's fonts,
title-block conventions, and abbreviation habits must never appear in both
train and test. Duplicate/near-identical project copies (detected by exact
PDF sha256 overlap in Phase A) are kept together in one split.

Usage:
    python -m scripts.corpus.phase_splits --output <corpus dir> --seed 42
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import read_jsonl, write_json  # noqa: E402

TRAIN_FRACTION = 0.6
VAL_FRACTION = 0.2
# remainder is test


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_dir: Path = args.output
    clean = list(read_jsonl(out_dir / "clean" / "annotations.jsonl"))
    projects = sorted({c["project_id"] for c in clean})

    # Cross-project duplicate PDF groups (Phase A) -- merge any projects that
    # share an exact-duplicate PDF into one union-find group so they always
    # land in the same split together.
    dup_groups_path = out_dir / "inventory" / "duplicate_pdfs_cross_project.json"
    parent = {p: p for p in projects}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    if dup_groups_path.exists():
        import json
        dup_groups = json.loads(dup_groups_path.read_text(encoding="utf-8"))
        for group in dup_groups.values():
            group_projects = [p for p in group["projects"] if p in parent]
            for p in group_projects[1:]:
                union(group_projects[0], p)

    clusters: dict[str, list[str]] = {}
    for p in projects:
        clusters.setdefault(find(p), []).append(p)
    cluster_ids = sorted(clusters.keys())

    rng = random.Random(args.seed)
    rng.shuffle(cluster_ids)

    n = len(cluster_ids)
    n_train = max(1, round(n * TRAIN_FRACTION))
    n_val = max(1, round(n * VAL_FRACTION)) if n > 2 else 0
    train_clusters = cluster_ids[:n_train]
    val_clusters = cluster_ids[n_train:n_train + n_val]
    test_clusters = cluster_ids[n_train + n_val:]

    def expand(cluster_list):
        out = []
        for c in cluster_list:
            out.extend(clusters[c])
        return sorted(out)

    train_projects = expand(train_clusters)
    val_projects = expand(val_clusters)
    test_projects = expand(test_clusters)

    splits_dir = out_dir / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    (splits_dir / "train_projects.txt").write_text("\n".join(train_projects), encoding="utf-8")
    (splits_dir / "validation_projects.txt").write_text("\n".join(val_projects), encoding="utf-8")
    (splits_dir / "test_projects.txt").write_text("\n".join(test_projects), encoding="utf-8")

    summary = {
        "seed": args.seed,
        "total_projects": len(projects),
        "duplicate_clusters_merged": sum(1 for c in clusters.values() if len(c) > 1),
        "train_projects": train_projects,
        "validation_projects": val_projects,
        "test_projects": test_projects,
        "train_annotation_count": sum(1 for c in clean if c["project_id"] in train_projects),
        "validation_annotation_count": sum(1 for c in clean if c["project_id"] in val_projects),
        "test_annotation_count": sum(1 for c in clean if c["project_id"] in test_projects),
    }
    write_json(splits_dir / "split_manifest.json", summary)
    import json
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
