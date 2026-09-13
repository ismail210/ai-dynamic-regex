"""Phase: candidate-retrieval recall audit (Section 18).

Measures recall@{1,3,5,10,20,50} on the v1 TEST-split repair pairs, broken
out by corruption category, for RapidFuzz / Levenshtein / char-TF-IDF
individually and their union. This tells us whether the target designation
ever enters the candidate pool at all -- the precondition for any ranker
(current pipeline, LightGBM, or otherwise) to ever propose it.

Usage:
    python phase_retrieval_audit.py --v1 <v1 corpus dir> --output <v2 corpus dir>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus import candidate_retrieval as cr  # noqa: E402
from scripts.corpus.common import read_jsonl, write_json  # noqa: E402
from services.exact_section_predictor import predict_exact_sections  # noqa: E402

K_VALUES = (1, 3, 5, 10, 20, 50)


def build_catalog(v1_dir: Path) -> dict[str, list[str]]:
    by_family: dict[str, set[str]] = {}
    for row in read_jsonl(v1_dir / "clean" / "annotations.jsonl"):
        by_family.setdefault(row["family"], set()).add(row["canonical_text"])
    return {fam: sorted(vals) for fam, vals in by_family.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    catalog = build_catalog(args.v1)
    test_rows = [r for r in read_jsonl(args.v1 / "synthetic" / "repair_pairs.jsonl") if r["split"] == "test"]
    print(f"Test repair pairs: {len(test_rows)}")

    # per-example, per-method, per-k hit table
    per_category: dict[str, dict[str, dict[int, dict[str, int]]]] = {}
    overall: dict[str, dict[int, dict[str, int]]] = {}
    n_total = 0

    for row in test_rows:
        clean = row["clean"]["canonical_text"]
        corrupted = row["corrupted"]["text"]
        family = row["clean"]["family"]
        category = row["category"]
        pool = catalog.get(family, [])
        per_method = cr.union_retrieve(corrupted, pool, max(K_VALUES), predict_exact_sections)
        n_total += 1

        cat_bucket = per_category.setdefault(category, {})
        for k in K_VALUES:
            hits = cr.recall_at_k(clean, per_method, k)
            for method, hit in hits.items():
                overall.setdefault(method, {}).setdefault(k, {"hit": 0, "n": 0})
                overall[method][k]["hit"] += int(hit)
                overall[method][k]["n"] += 1
                cat_bucket.setdefault(method, {}).setdefault(k, {"hit": 0, "n": 0})
                cat_bucket[method][k]["hit"] += int(hit)
                cat_bucket[method][k]["n"] += 1

    def to_pct_table(bucket: dict[str, dict[int, dict[str, int]]]) -> dict:
        return {
            method: {str(k): round(v["hit"] / v["n"], 4) if v["n"] else None for k, v in ks.items()}
            for method, ks in bucket.items()
        }

    report = {
        "n_test_examples": n_total,
        "k_values": list(K_VALUES),
        "overall_recall": to_pct_table(overall),
        "recall_by_category": {cat: to_pct_table(bucket) for cat, bucket in per_category.items()},
    }
    write_json(args.output / "reports" / "candidate_retrieval_recall.json", report)

    print("\n=== Overall recall@K (union of RapidFuzz + Levenshtein + char-TF-IDF) ===")
    header = "category".ljust(22) + "".join(f"R@{k}".rjust(8) for k in K_VALUES)
    print(header)
    for cat, bucket in report["recall_by_category"].items():
        row = cat.ljust(22) + "".join(f"{bucket['union'][str(k)]*100:7.1f}%" for k in K_VALUES)
        print(row)
    all_row = "ALL".ljust(22) + "".join(f"{report['overall_recall']['union'][str(k)]*100:7.1f}%" for k in K_VALUES)
    print(all_row)


if __name__ == "__main__":
    main()
