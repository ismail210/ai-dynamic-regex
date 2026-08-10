"""Single source-of-truth per-row analysis over the FROZEN test split.

Computes everything Parts 1/2/5 need in one pass (candidate generation and
ranker scoring are the expensive parts, so this avoids recomputing them
once per downstream report). Reuses the EXACT SAME dataset version already
used for the v2 baselines/ranker (``label_reconstruction_20260807_125937``)
-- per Part 9's explicit instruction, this script never regenerates the
dataset or changes which corrupted strings are in the test split.

Output: ``training/datasets/label_reconstruction/frozen_test_analysis.jsonl``,
one row per frozen pointwise test example.

Run from ``backend/``: ``python scripts/analyze_frozen_test_rows.py``
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.label_reconstruction.candidates import (  # noqa: E402
    generate_candidates,
    generate_candidates_v3,
)
from services.label_reconstruction.structural_parser import (  # noqa: E402
    ambiguity_category,
    compatible_catalog_labels,
)
from services.training_pipeline import dataset_registry  # noqa: E402

DATASET_VERSION = "label_reconstruction_20260807_125937"
# The v2 XGBoost ranker specifically (pointwise binary-classification
# objective, 21-feature schema) -- this script's job is to analyze what V2
# actually did, so it pins to that exact registered version rather than
# "whichever model is newest," which would silently become v3 once trained.
V2_RANKER_VERSION_ID = "label_reconstruction_20260807_130015"
CANDIDATE_LIMIT = 25


def _v2_ranker():
    from services.label_reconstruction.ranker import load_ranker_version

    return load_ranker_version(V2_RANKER_VERSION_ID)


def _rank_of(target: str, ranked: List[str]) -> Optional[int]:
    try:
        return ranked.index(target) + 1
    except ValueError:
        return None


def main() -> int:
    started = time.time()
    samples = dataset_registry.load_dataset_samples("label_reconstruction", DATASET_VERSION)
    test_rows = [r for r in samples if r.get("row_kind") == "pointwise" and r.get("split") == "test"]
    print(f"Loaded {len(test_rows)} frozen test rows from {DATASET_VERSION}.")

    ranker = _v2_ranker()
    if ranker is None:
        print("WARNING: no trained ranker found -- v2_learned fields will be null.")

    out_rows = []
    for i, row in enumerate(test_rows):
        query = row["raw_corrupted"]
        target = row["target_label"]

        compat = compatible_catalog_labels(query)
        ambiguity = ambiguity_category(len(compat))

        v2_set = generate_candidates(query, limit=CANDIDATE_LIMIT)
        v2_candidates = v2_set.candidates
        v2_det_rank = _rank_of(target, v2_candidates)
        v2_true_in_candidates = target in v2_candidates

        v2_learned_top10 = None
        v2_learned_rank = None
        if ranker is not None and v2_candidates:
            # RAW query, not v2_set.normalized -- the ranker was trained
            # with pairwise "query" = raw_corrupted text (see
            # generate_label_corruption_dataset.py's build_pairwise_rows).
            scores = ranker.score(
                query, v2_candidates, generation_reasons=v2_set.generation_reasons
            )
            ranked = [label for label, _s in sorted(zip(v2_candidates, scores), key=lambda p: -p[1])]
            v2_learned_top10 = ranked[:10]
            v2_learned_rank = _rank_of(target, ranked)

        v3_set = generate_candidates_v3(query, limit=CANDIDATE_LIMIT)
        v3_candidates = v3_set.candidates
        v3_det_rank = _rank_of(target, v3_candidates)
        v3_true_in_candidates = target in v3_candidates

        if not v2_true_in_candidates:
            failure_kind = "candidate_generation"
        elif v2_learned_rank != 1:
            failure_kind = "ranking"
        else:
            failure_kind = "none"

        out_rows.append(
            {
                "raw_corrupted": query,
                "normalized": v2_set.normalized,
                "target_label": target,
                "family": row["family"],
                "corruption_types": row["corruption_types"],
                "severity": row["severity"],
                "unseen_combo": row.get("unseen_combo", False),
                "compatible_catalog_count": len(compat),
                "ambiguity_category": ambiguity,
                "v2_det_top10": v2_candidates[:10],
                "v2_det_rank": v2_det_rank,
                "v2_candidate_set_size": len(v2_candidates),
                "v2_true_in_candidates": v2_true_in_candidates,
                "v2_learned_top10": v2_learned_top10,
                "v2_learned_rank": v2_learned_rank,
                "v3_det_top10": v3_candidates[:10],
                "v3_det_rank": v3_det_rank,
                "v3_candidate_set_size": len(v3_candidates),
                "v3_true_in_candidates": v3_true_in_candidates,
                "failure_kind": failure_kind,
            }
        )
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(test_rows)} ({time.time() - started:.0f}s elapsed)", flush=True)

    out_path = (
        Path(__file__).resolve().parents[1]
        / "training"
        / "datasets"
        / "label_reconstruction"
        / "frozen_test_analysis.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in out_rows:
            handle.write(json.dumps(row) + "\n")

    print(f"\nWrote {len(out_rows)} rows to {out_path}")
    print(f"Total runtime: {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
