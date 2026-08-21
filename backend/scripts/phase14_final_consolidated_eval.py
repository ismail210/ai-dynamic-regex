"""
Phase 14 / final consolidated legacy_external_test comparison. ONE
candidate-generation pass (with the fixed, full-catalog _fuzzy_candidates)
over the 6512 test rows, scoring with BOTH rankers so the expensive part
isn't repeated:

  - C1 + untuned BASE_PARAMS        (current best-known-good, unchanged)
  - candidate_ranker_cv_tuned        (Phase 4/5 CV-selected candidate, not yet promoted)

This is the single, final, post-hoc test-set touch -- neither ranker nor
the candidate-generation fix was chosen using test-set feedback; both
were selected via CV / training-set root-cause evidence beforehand.

Run from `backend/`: python scripts/phase14_final_consolidated_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import numpy as np
from xgboost import XGBRanker

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import database_loader  # noqa: E402
from services.label_reconstruction.candidates import generate_candidates_v3  # noqa: E402
from services.label_reconstruction.catalog_reload import refresh_all_dependent_caches  # noqa: E402
from services.label_reconstruction.features import (  # noqa: E402
    FEATURE_NAMES,
    features_from_candidate_set,
)

DATABASE_DIR = BACKEND_DIR / "database"
CATALOG_PATH = DATABASE_DIR / "aisc_v16_label_catalog.csv"
DATA_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_v16"
OLD_EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_optuna_20260816"
EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_groupcv_20260816"

CANDIDATE_LIMIT = 25
SEED = 20260813
BASE_PARAMS = dict(
    tree_method="hist", max_depth=5, learning_rate=0.1, n_estimators=200,
    subsample=0.9, colsample_bytree=0.9, random_state=SEED,
)
MASKED_FEATURES = ["deterministic_rank", "fuzzy_rank"]
MASKED_IDX = [FEATURE_NAMES.index(n) for n in MASKED_FEATURES]


def _load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _bucket():
    return {"n": 0, "top1": 0, "top3": 0, "mrr_sum": 0.0, "cand_present": 0}


def _update(b, rank, cand_present):
    b["n"] += 1
    b["cand_present"] += int(cand_present)
    if rank is not None:
        b["top1"] += int(rank == 0)
        b["top3"] += int(rank < 3)
        b["mrr_sum"] += 1.0 / (rank + 1)


def _finalize(b):
    n = b["n"] or 1
    return {"n": b["n"], "candidate_recall": b["cand_present"] / n,
            "top1": b["top1"] / n, "top3": b["top3"] / n, "mrr": b["mrr_sum"] / n}


def rank_with(model, feats, candidates, target):
    scores = model.predict(feats)
    ordered = [c for _s, c in sorted(zip(scores, candidates), key=lambda p: -p[0])]
    return ordered.index(target) if target in ordered else None


def main() -> int:
    # Untuned reference
    train = np.load(OLD_EXPERIMENT_DIR / "train_full.npz")
    X_train, y_train, groups_train = train["X"].copy(), train["y"], train["groups"]
    X_train[:, MASKED_IDX] = 0.0
    untuned = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
    untuned.fit(X_train, y_train, group=groups_train)
    print("trained C1 + untuned BASE_PARAMS")

    # CV-tuned candidate
    cv_tuned = XGBRanker()
    cv_tuned.load_model(str(EXPERIMENT_DIR / "candidate_ranker_cv_tuned.json"))
    print("loaded candidate_ranker_cv_tuned")

    pointwise_rows = _load_jsonl(DATA_DIR / "pointwise.jsonl")
    test_rows = [r for r in pointwise_rows if r["split"] == "test"]
    print(f"test rows: {len(test_rows)}")

    database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    try:
        buckets = {
            "untuned_overall": _bucket(), "untuned_modern": _bucket(), "untuned_historical": _bucket(),
            "untuned_holdout": _bucket(), "untuned_seen": _bucket(),
            "cv_tuned_overall": _bucket(), "cv_tuned_modern": _bucket(), "cv_tuned_historical": _bucket(),
            "cv_tuned_holdout": _bucket(), "cv_tuned_seen": _bucket(),
        }
        for row in test_rows:
            target = row["clean_designation"]
            corrupted = row["corrupted_text"]
            scope = row["catalog_scope"]
            holdout = "holdout" if row["designation_holdout"] else "seen"

            candidate_set = generate_candidates_v3(corrupted, limit=CANDIDATE_LIMIT)
            candidates = candidate_set.candidates
            cand_present = target in candidates

            if not candidates:
                rank_u = rank_c = None
            else:
                feats = np.array(
                    [[features_from_candidate_set(c, candidate_set)[name] for name in FEATURE_NAMES] for c in candidates]
                )
                feats_masked = feats.copy()
                feats_masked[:, MASKED_IDX] = 0.0
                rank_u = rank_with(untuned, feats_masked, candidates, target)
                rank_c = rank_with(cv_tuned, feats_masked, candidates, target)

            for prefix, rank in (("untuned", rank_u), ("cv_tuned", rank_c)):
                _update(buckets[f"{prefix}_overall"], rank, cand_present)
                _update(buckets[f"{prefix}_{scope}"], rank, cand_present)
                _update(buckets[f"{prefix}_{holdout}"], rank, cand_present)
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()

    results = {k: _finalize(v) for k, v in buckets.items()}
    for k, v in results.items():
        print(f"{k}: top1={v['top1']:.4f} top3={v['top3']:.4f} mrr={v['mrr']:.4f} recall={v['candidate_recall']:.4f} n={v['n']}")

    (EXPERIMENT_DIR / "phase14_final_consolidated_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nsaved to {EXPERIMENT_DIR / 'phase14_final_consolidated_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
