"""
Phase 4: grouped-CV Optuna search. Objective = mean 5-fold Top-1 (group
accuracy) on the FROZEN C1 feature config, using the fixed folds from
Phase 2 and the cached dev-pool matrix from Phase 3 -- candidate generation
is never repeated per trial.

This replaces the invalid single-split Optuna study
(training/experiments/v16_ranker_optuna_20260816/) as the selection
authority. That study is kept on disk, unmodified, for the record.

Every trial also records per-fold Top-1, std, worst-fold, mean Top-3/MRR,
and train Top-1 (for the fold-averaged train/val gap) -- so trial ranking
never happens on a single number in isolation.

Run from `backend/`:
  python scripts/phase4_cv_optuna_search.py --n-trials 3   # profiling
  python scripts/phase4_cv_optuna_search.py --n-trials 97  # full sweep (resumes)
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import optuna
from optuna.samplers import TPESampler
from xgboost import XGBRanker

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_groupcv_20260816"
STUDY_DB = EXPERIMENT_DIR / "optuna_cv_study.db"
STUDY_NAME = "v16_ranker_groupcv_search"
SEED = 20260813
N_SPLITS = 5

MASKED_FEATURES = ["deterministic_rank", "fuzzy_rank"]
FEATURE_NAMES_PATH = BACKEND_DIR / "training" / "experiments" / "v16_ranker_optuna_20260816" / "feature_names.json"


def load_devpool():
    data = np.load(EXPERIMENT_DIR / "devpool_full.npz")
    X, y, group_sizes, group_fold = data["X"], data["y"], data["group_sizes"], data["group_fold"]
    feature_names = json.loads(FEATURE_NAMES_PATH.read_text(encoding="utf-8"))
    masked_idx = [feature_names.index(n) for n in MASKED_FEATURES]
    Xc = X.copy()
    Xc[:, masked_idx] = 0.0

    offsets = np.concatenate([[0], np.cumsum(group_sizes)])
    row_fold = np.zeros(len(y), dtype=int)
    for gi in range(len(group_sizes)):
        row_fold[offsets[gi] : offsets[gi + 1]] = group_fold[gi]

    return Xc, y, group_sizes, group_fold, row_fold, offsets


def group_top1(model, X, y, group_sizes):
    scores = model.predict(X)
    top1 = top3 = 0
    mrr_sum = 0.0
    total = 0
    offset = 0
    for size in group_sizes:
        s = scores[offset : offset + size]
        t = y[offset : offset + size]
        offset += size
        if not t.any():
            continue
        total += 1
        order = np.argsort(-s)
        rank = int(np.argmax(t[order]))
        top1 += int(rank == 0)
        top3 += int(rank < 3)
        mrr_sum += 1.0 / (rank + 1)
    return {"top1": top1 / total if total else 0.0, "top3": top3 / total if total else 0.0,
            "mrr": mrr_sum / total if total else 0.0, "n": total}


def make_objective(Xc, y, group_sizes, group_fold, row_fold, offsets):
    def objective(trial: optuna.Trial) -> float:
        params = dict(
            tree_method="hist", random_state=SEED,
            objective=trial.suggest_categorical("objective", ["rank:pairwise", "rank:ndcg"]),
            n_estimators=trial.suggest_int("n_estimators", 50, 500),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            max_depth=trial.suggest_int("max_depth", 3, 9),
            min_child_weight=trial.suggest_float("min_child_weight", 1.0, 10.0, log=True),
            subsample=trial.suggest_float("subsample", 0.6, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1.0),
            gamma=trial.suggest_float("gamma", 1e-8, 5.0, log=True),
            reg_alpha=trial.suggest_float("reg_alpha", 1e-8, 5.0, log=True),
            reg_lambda=trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
        )

        fold_top1, fold_top3, fold_mrr, fold_train_top1 = [], [], [], []
        for fold in range(N_SPLITS):
            train_group_mask = group_fold != fold
            val_group_mask = group_fold == fold
            train_row_mask = row_fold != fold
            val_row_mask = row_fold == fold

            model = XGBRanker(**params)
            model.fit(Xc[train_row_mask], y[train_row_mask], group=group_sizes[train_group_mask])
            val_m = group_top1(model, Xc[val_row_mask], y[val_row_mask], group_sizes[val_group_mask])
            train_m = group_top1(model, Xc[train_row_mask], y[train_row_mask], group_sizes[train_group_mask])
            fold_top1.append(val_m["top1"])
            fold_top3.append(val_m["top3"])
            fold_mrr.append(val_m["mrr"])
            fold_train_top1.append(train_m["top1"])

        mean_top1 = float(np.mean(fold_top1))
        trial.set_user_attr("fold_top1", fold_top1)
        trial.set_user_attr("std_top1", float(np.std(fold_top1)))
        trial.set_user_attr("worst_fold_top1", float(np.min(fold_top1)))
        trial.set_user_attr("mean_top3", float(np.mean(fold_top3)))
        trial.set_user_attr("mean_mrr", float(np.mean(fold_mrr)))
        trial.set_user_attr("mean_train_top1", float(np.mean(fold_train_top1)))
        trial.set_user_attr("train_val_gap", float(np.mean(fold_train_top1)) - mean_top1)
        return mean_top1

    return objective


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-trials", type=int, default=3)
    args = parser.parse_args()

    Xc, y, group_sizes, group_fold, row_fold, offsets = load_devpool()
    print(f"dev pool: X={Xc.shape}, query-groups={len(group_sizes)}, folds={sorted(set(group_fold.tolist()))}")

    study = optuna.create_study(
        study_name=STUDY_NAME, storage=f"sqlite:///{STUDY_DB}",
        direction="maximize", sampler=TPESampler(seed=SEED), load_if_exists=True,
    )
    objective = make_objective(Xc, y, group_sizes, group_fold, row_fold, offsets)

    start = time.time()
    study.optimize(objective, n_trials=args.n_trials)
    elapsed = time.time() - start
    print(f"\nran {args.n_trials} trials in {elapsed:.1f}s ({elapsed/args.n_trials:.2f}s/trial)")
    print(f"total trials so far: {len(study.trials)}")
    print(f"best mean_top1 so far: {study.best_value:.4f}")
    print(f"best params: {study.best_params}")
    print(f"best user_attrs: {study.best_trial.user_attrs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
