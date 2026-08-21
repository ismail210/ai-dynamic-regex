"""
Phase 3: build the FULL development-pool (train+validation) feature matrix
ONCE, with each query-group tagged by its Phase-2 fold assignment, then
evaluate C1 (deterministic_rank/fuzzy_rank masked) + original untuned
BASE_PARAMS with real 5-fold grouped cross-validation.

This is also the shared cache Phase 4's Optuna CV study reuses -- candidate
generation is independent of hyperparameters, so it must not be repeated
per trial or per fold-evaluation.

Caches to:
  devpool_full.npz        -- X, y, row_group_sizes (per query-group), row_fold (per query-group)
Run from `backend/`: python scripts/phase3_build_devpool_and_cv_baseline.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

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
EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_groupcv_20260816"

CANDIDATE_LIMIT = 25
SEED = 20260813
BASE_PARAMS = dict(
    tree_method="hist", max_depth=5, learning_rate=0.1, n_estimators=200,
    subsample=0.9, colsample_bytree=0.9, random_state=SEED,
)
MASKED_FEATURES = ["deterministic_rank", "fuzzy_rank"]
MASKED_IDX = [FEATURE_NAMES.index(n) for n in MASKED_FEATURES]
N_SPLITS = 5


def _load_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_devpool_matrix():
    pointwise_rows = _load_jsonl(DATA_DIR / "pointwise.jsonl")
    corrupted_to_group = {r["corrupted_text"]: r["source_designation_id"] for r in pointwise_rows}

    fold_assignment = json.loads((EXPERIMENT_DIR / "fold_assignment.json").read_text(encoding="utf-8"))
    group_to_fold = fold_assignment["group_to_fold"]

    pairwise_rows = _load_jsonl(DATA_DIR / "pairwise.jsonl")
    dev_rows = [r for r in pairwise_rows if r["split"] in ("train", "validation")]

    X, y, group_sizes, group_fold = [], [], [], []
    for query, group in itertools.groupby(dev_rows, key=lambda r: r["query"]):
        group = list(group)
        if len(group) < 2 or sum(r["target"] for r in group) == 0:
            continue
        candidate_set = generate_candidates_v3(query, limit=CANDIDATE_LIMIT)
        group_sizes.append(len(group))
        fold = group_to_fold[corrupted_to_group[query]]
        group_fold.append(fold)
        for row in group:
            feats = features_from_candidate_set(row["candidate"], candidate_set)
            X.append([feats[name] for name in FEATURE_NAMES])
            y.append(row["target"])

    return (np.array(X, dtype=float), np.array(y), np.array(group_sizes), np.array(group_fold))


def group_metrics(model, X, y, group_sizes):
    scores = model.predict(X)
    top1 = top3 = 0
    mrr_sum = 0.0
    cand_present = 0
    total = 0
    offset = 0
    for size in group_sizes:
        s = scores[offset : offset + size]
        t = y[offset : offset + size]
        offset += size
        total += 1
        if not t.any():
            continue
        cand_present += 1
        order = np.argsort(-s)
        rank = int(np.argmax(t[order]))
        top1 += int(rank == 0)
        top3 += int(rank < 3)
        mrr_sum += 1.0 / (rank + 1)
    return {
        "n": total, "candidate_recall": cand_present / total if total else 0.0,
        "top1": top1 / total if total else 0.0, "top3": top3 / total if total else 0.0,
        "mrr": mrr_sum / total if total else 0.0,
    }


def main() -> int:
    cache_path = EXPERIMENT_DIR / "devpool_full.npz"
    if cache_path.exists():
        print(f"reusing cached {cache_path}")
        data = np.load(cache_path)
        X, y, group_sizes, group_fold = data["X"], data["y"], data["group_sizes"], data["group_fold"]
    else:
        database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
        refresh_all_dependent_caches()
        try:
            print("building development-pool matrix (candidate generation, ~15-20 min)...")
            X, y, group_sizes, group_fold = build_devpool_matrix()
        finally:
            database_loader.reset_to_default()
            refresh_all_dependent_caches()
        np.savez_compressed(cache_path, X=X, y=y, group_sizes=group_sizes, group_fold=group_fold)
        print(f"cached to {cache_path}")

    print(f"X: {X.shape}, query-groups: {len(group_sizes)}, folds present: {sorted(set(group_fold.tolist()))}")

    # row-level offsets per query-group, and per-row fold (expand group_fold to row level)
    offsets = np.concatenate([[0], np.cumsum(group_sizes)])

    Xc = X.copy()
    Xc[:, MASKED_IDX] = 0.0

    fold_results = []
    for fold in range(N_SPLITS):
        train_group_mask = group_fold != fold
        val_group_mask = group_fold == fold

        train_row_mask = np.zeros(len(y), dtype=bool)
        val_row_mask = np.zeros(len(y), dtype=bool)
        for gi in range(len(group_sizes)):
            s, e = offsets[gi], offsets[gi + 1]
            if train_group_mask[gi]:
                train_row_mask[s:e] = True
            else:
                val_row_mask[s:e] = True

        model = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
        model.fit(Xc[train_row_mask], y[train_row_mask], group=group_sizes[train_group_mask])
        m = group_metrics(model, Xc[val_row_mask], y[val_row_mask], group_sizes[val_group_mask])
        m["fold"] = fold
        fold_results.append(m)
        print(f"fold {fold}: top1={m['top1']:.4f} top3={m['top3']:.4f} mrr={m['mrr']:.4f} "
              f"candidate_recall={m['candidate_recall']:.4f} n={m['n']}")

    top1s = [r["top1"] for r in fold_results]
    top3s = [r["top3"] for r in fold_results]
    mrrs = [r["mrr"] for r in fold_results]
    summary = {
        "fold_results": fold_results,
        "top1_mean": float(np.mean(top1s)), "top1_std": float(np.std(top1s)),
        "top1_min": float(np.min(top1s)), "top1_max": float(np.max(top1s)),
        "top3_mean": float(np.mean(top3s)), "mrr_mean": float(np.mean(mrrs)),
    }
    print(f"\nCV baseline (C1 + untuned BASE_PARAMS): top1 mean={summary['top1_mean']:.4f} "
          f"std={summary['top1_std']:.4f} min={summary['top1_min']:.4f} max={summary['top1_max']:.4f}")
    (EXPERIMENT_DIR / "phase3_cv_baseline.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"saved to {EXPERIMENT_DIR / 'phase3_cv_baseline.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
