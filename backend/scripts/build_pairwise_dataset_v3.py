"""Build v3's pairwise training data (Part 6/7): richer hard negatives than
v2's, mined from three sources instead of one.

Reuses the exact pointwise rows/splits from the frozen dataset version --
this NEVER regenerates the pointwise corruption dataset or touches which
strings are train/validation/test (Part 9 requires the frozen test split
stay untouched). Only TRAIN and VALIDATION pointwise rows are used here --
the test split needs no pairwise rows at all, because evaluation
(``evaluate_label_ranker.py``) re-generates each test query's candidates
fresh and re-ranks them; it never reads pairwise rows.

Each pointwise row's negatives come from:

1. **v2's actual mistakes** -- candidates the v2 XGBoost ranker scored
   ABOVE the true label, on this row (train/validation rows only, never
   test). These are the single most valuable negatives: proof the previous
   ranker found them confusable.
2. **Structural near-misses** (``structural_parser.nearest_by_fields``) --
   same family/grammar, nearest by field-numeric distance: nearby
   depth/weight for W-shapes, wrong-thickness/wrong-dimension for HSS,
   exactly the "W18X35 vs W16X35/W21X35/W18X30/W18X40" and "HSS8X8X1/4 vs
   HSS8X8X3/8" cases the spec calls out.
3. **v3's own candidate generator** (``generate_candidates_v3``) -- same
   principle as v2 had: whatever the deterministic system itself proposes
   is exactly what the ranker most needs to learn to de-prioritize when
   wrong.

Output: a plain JSONL (not versioned through ``dataset_registry`` --
pairwise training fuel, not the frozen evaluation artifact) at
``training/datasets/label_reconstruction/pairwise_v3_train_val.jsonl``,
plus a sidecar ``pairwise_v3_train_val.meta.json`` recording the source
dataset version, ranker version used for mistake-mining, seed, and negative
counts by source (Part 6's "do not hide candidate-generation failure /
do not fill mostly with easy negatives" transparency requirement).

Run from ``backend/``: ``python scripts/build_pairwise_dataset_v3.py``
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.label_reconstruction.candidates import (  # noqa: E402
    generate_candidates,
    generate_candidates_v3,
)
from services.label_reconstruction.ranker import load_ranker_version  # noqa: E402
from services.label_reconstruction.structural_parser import nearest_by_fields  # noqa: E402
from services.training_pipeline import dataset_registry  # noqa: E402

DATASET_VERSION = "label_reconstruction_20260807_125937"
V2_RANKER_VERSION_ID = "label_reconstruction_20260807_130015"
K_NEGATIVES = 6
CANDIDATE_LIMIT = 25


def _v2_mistake_negatives(row: dict, v2_ranker) -> List[str]:
    if v2_ranker is None:
        return []
    query = row["raw_corrupted"]
    target = row["target_label"]
    v2_set = generate_candidates(query, limit=CANDIDATE_LIMIT)
    if target not in v2_set.candidates or len(v2_set.candidates) < 2:
        return []
    scores = v2_ranker.score(v2_set.normalized, v2_set.candidates, generation_reasons=v2_set.generation_reasons)
    ranked = [c for c, _s in sorted(zip(v2_set.candidates, scores), key=lambda p: -p[1])]
    target_index = ranked.index(target)
    return ranked[:target_index]  # everything v2 wrongly ranked above the truth


def build_pairwise_rows_v3(pointwise_rows: List[dict], v2_ranker) -> List[dict]:
    pairwise: List[dict] = []
    source_counts = {"v2_mistake": 0, "structural_near_miss": 0, "v3_generator": 0}

    for row in pointwise_rows:
        query = row["raw_corrupted"]
        target = row["target_label"]
        split = row["split"]

        v3_set = generate_candidates_v3(query, limit=CANDIDATE_LIMIT)

        def _rank_and_reasons(label: str):
            if label in v3_set.candidates:
                return (
                    v3_set.candidates.index(label),
                    v3_set.generation_reasons.get(label),
                    v3_set.fuzzy_ranks.get(label),
                )
            return None, None, None

        target_rank, target_reasons, target_fuzzy_rank = _rank_and_reasons(target)
        pairwise.append(
            {
                "row_kind": "pairwise",
                "query": query,
                "candidate": target,
                "target": 1,
                "split": split,
                "family": row["family"],
                "deterministic_rank": target_rank,
                "generation_reasons": target_reasons,
                "fuzzy_rank": target_fuzzy_rank,
                "supervised": True,
            }
        )

        negatives_with_source: List[tuple] = []
        for neg in _v2_mistake_negatives(row, v2_ranker):
            if neg != target:
                negatives_with_source.append((neg, "v2_mistake"))
        for neg in nearest_by_fields(target, k=K_NEGATIVES):
            if neg != target:
                negatives_with_source.append((neg, "structural_near_miss"))
        for neg in v3_set.candidates:
            if neg != target:
                negatives_with_source.append((neg, "v3_generator"))

        seen: Set[str] = set()
        added = 0
        for neg, source in negatives_with_source:
            if neg in seen:
                continue
            seen.add(neg)
            neg_rank, neg_reasons, neg_fuzzy_rank = _rank_and_reasons(neg)
            pairwise.append(
                {
                    "row_kind": "pairwise",
                    "query": query,
                    "candidate": neg,
                    "target": 0,
                    "split": split,
                    "family": row["family"],
                    "deterministic_rank": neg_rank,
                    "generation_reasons": neg_reasons,
                    "fuzzy_rank": neg_fuzzy_rank,
                    "negative_source": source,
                    "supervised": True,
                }
            )
            source_counts[source] = source_counts.get(source, 0) + 1
            added += 1
            if added >= K_NEGATIVES:
                break

    return pairwise, source_counts


def main() -> int:
    started = time.time()
    samples = dataset_registry.load_dataset_samples("label_reconstruction", DATASET_VERSION)
    pointwise_rows = [
        r for r in samples if r.get("row_kind") == "pointwise" and r.get("split") in ("train", "validation")
    ]
    print(f"Loaded {len(pointwise_rows)} train/validation pointwise rows from {DATASET_VERSION}.")

    v2_ranker = load_ranker_version(V2_RANKER_VERSION_ID)
    if v2_ranker is None:
        print("WARNING: v2 ranker not found -- v2_mistake negatives will be skipped.")

    pairwise, source_counts = build_pairwise_rows_v3(pointwise_rows, v2_ranker)
    print(f"Built {len(pairwise)} pairwise rows. Negative sources: {source_counts}")

    out_path = (
        Path(__file__).resolve().parents[1]
        / "training"
        / "datasets"
        / "label_reconstruction"
        / "pairwise_v3_train_val.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in pairwise:
            handle.write(json.dumps(row, default=str) + "\n")

    meta = {
        "source_dataset_version": DATASET_VERSION,
        "v2_ranker_version_used_for_mistake_mining": V2_RANKER_VERSION_ID,
        "k_negatives": K_NEGATIVES,
        "n_pointwise_rows": len(pointwise_rows),
        "n_pairwise_rows": len(pairwise),
        "negative_source_counts": source_counts,
    }
    meta_path = out_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\nWrote {out_path}")
    print(f"Wrote {meta_path}")
    print(f"Runtime: {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
