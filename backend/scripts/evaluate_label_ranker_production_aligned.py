"""Evaluate a registered candidate on production-aligned synthetic test rows.

This is an offline synthetic OCR-ranking evaluation. It never activates or
promotes the model.

Run from ``backend/``:
  python scripts/evaluate_label_ranker_production_aligned.py --version-id ID
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import database_loader  # noqa: E402
from services.label_reconstruction.candidates import generate_candidates  # noqa: E402
from services.label_reconstruction.catalog_reload import (  # noqa: E402
    refresh_all_dependent_caches,
)
from services.label_reconstruction.ranker import load_ranker_version  # noqa: E402

DATASET_DIR = (
    BACKEND_DIR
    / "training"
    / "datasets"
    / "label_reconstruction_production_aligned"
)
CANDIDATE_LIMIT = 25


def _load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _metric_bucket() -> dict:
    return {
        "n": 0,
        "candidate_present": 0,
        "top1": 0,
        "top3": 0,
        "mrr_sum": 0.0,
        "ndcg10_sum": 0.0,
    }


def _update(bucket: dict, rank: int | None, candidate_present: bool) -> None:
    bucket["n"] += 1
    bucket["candidate_present"] += int(candidate_present)
    if rank is None:
        return
    bucket["top1"] += int(rank == 0)
    bucket["top3"] += int(rank < 3)
    bucket["mrr_sum"] += 1.0 / (rank + 1)
    if rank < 10:
        bucket["ndcg10_sum"] += 1.0 / __import__("math").log2(rank + 2)


def _finalize(bucket: dict) -> dict:
    n = bucket["n"]
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "candidate_recall": bucket["candidate_present"] / n,
        "top1": bucket["top1"] / n,
        "top3": bucket["top3"] / n,
        "mrr": bucket["mrr_sum"] / n,
        "ndcg_at_10": bucket["ndcg10_sum"] / n,
    }


def _breakdown(
    scored: list[tuple[dict, int | None, bool]],
    key_fn: Callable[[dict], str],
) -> dict:
    buckets: dict[str, dict] = defaultdict(_metric_bucket)
    for row, rank, present in scored:
        _update(buckets[key_fn(row)], rank, present)
    return {
        key: _finalize(bucket)
        for key, bucket in sorted(buckets.items())
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-id", required=True)
    args = parser.parse_args()

    ranker = load_ranker_version(args.version_id)
    if ranker is None:
        print(f"Candidate model {args.version_id!r} not found.")
        return 1

    manifest = json.loads(
        (DATASET_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    expected_generator = (
        "services.label_reconstruction.candidates.generate_candidates"
    )
    if manifest.get("candidate_generator") != expected_generator:
        print("Refusing evaluation: dataset is not production-candidate aligned.")
        return 1

    database_loader.reset_to_default()
    refresh_all_dependent_caches()
    pointwise = _load_jsonl(DATASET_DIR / "pointwise.jsonl")
    test_rows = [row for row in pointwise if row["split"] == "test"]
    rank_rows = [
        row for row in test_rows if row["expected_decision"] == "rank"
    ]

    scored: list[tuple[dict, int | None, bool]] = []
    deterministic = _metric_bucket()
    for index, row in enumerate(rank_rows, start=1):
        candidate_set = generate_candidates(
            row["query"], limit=CANDIDATE_LIMIT
        )
        target = row["clean_designation"]
        present = target in candidate_set.candidates
        det_rank = (
            candidate_set.candidates.index(target) if present else None
        )
        _update(deterministic, det_rank, present)
        ranked = ranker.rank(
            row["query"],
            candidate_set.candidates,
            generation_reasons=candidate_set.generation_reasons,
            fuzzy_ranks=candidate_set.fuzzy_ranks,
        )
        rank = ranked.index(target) if target in ranked else None
        scored.append((row, rank, present))
        if index % 500 == 0 or index == len(rank_rows):
            print(f"evaluation: {index}/{len(rank_rows)}", flush=True)

    overall_bucket = _metric_bucket()
    for _row, rank, present in scored:
        _update(overall_bucket, rank, present)

    result = {
        "evaluation_kind": "synthetic_ocr_ranking_not_production_accuracy",
        "model_version": ranker.version_id,
        "dataset_version": manifest["dataset_version"],
        "candidate_generator": expected_generator,
        "candidate_limit": CANDIDATE_LIMIT,
        "test_decision_counts": {
            decision: sum(
                row["expected_decision"] == decision for row in test_rows
            )
            for decision in sorted(
                {row["expected_decision"] for row in test_rows}
            )
        },
        "rankable_test_rows": len(rank_rows),
        "deterministic_order": _finalize(deterministic),
        "candidate_ranker": _finalize(overall_bucket),
        "by_family": _breakdown(scored, lambda row: row["family"] or "unknown"),
        "by_corruption_type": _breakdown(
            scored,
            lambda row: (
                row["corruption_type"][0]
                if row["corruption_type"]
                else "none"
            ),
        ),
        "by_severity": _breakdown(
            scored, lambda row: f"severity_{row['corruption_severity']}"
        ),
        "designation_holdout": _breakdown(
            scored,
            lambda row: (
                "holdout"
                if row["designation_holdout"]
                else "seen_designation"
            ),
        ),
    }
    output_path = DATASET_DIR / f"evaluation_{ranker.version_id}.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    print(f"evaluation_path: {output_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
