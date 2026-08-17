"""
Optuna hyperparameter search for the v16 label ranker, on the FROZEN feature
set from Phase 1, using cached train/validation matrices (candidate
generation already baked in -- hyperparameters never change what
generate_candidates_v3 returns, so it is built exactly once by
scripts/phase1_feature_freeze.py, not per trial).

TRAIN+VALIDATION ONLY. The test split is never read here.

Primary objective: validation group top-1 accuracy (overall). Modern-family
top-1, historical-family top-1, top-3, and MRR are recorded per trial as
user attributes for the post-hoc modern-vs-historical sanity check (Phase 3):
a trial must not be preferred purely because gains came from historical
labels while modern regressed.

Persisted via sqlite so the study can resume after interruption:
  training/experiments/v16_ranker_optuna_20260816/optuna_study.db

Run from `backend/`:
  python scripts/optuna_v16_ranker_search.py --n-trials 3   # profiling pass
  python scripts/optuna_v16_ranker_search.py --n-trials 60  # full sweep (resumes)
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
EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_optuna_20260816"
STUDY_DB = EXPERIMENT_DIR / "optuna_study.db"
STUDY_NAME = "v16_ranker_search"
SEED = 20260813

FROZEN_CONFIG_PATH = EXPERIMENT_DIR / "frozen_feature_config.json"


def load_matrices():
    train = np.load(EXPERIMENT_DIR / "train_full.npz")
    val = np.load(EXPERIMENT_DIR / "val_full.npz")
    feature_names = json.loads((EXPERIMENT_DIR / "feature_names.json").read_text(encoding="utf-8"))
    X_train, y_train, groups_train = train["X"], train["y"], train["groups"]
    X_val, y_val, groups_val = val["X"], val["y"], val["groups"]
    modern_mask = val["modern_mask"]

    frozen = json.loads(FROZEN_CONFIG_PATH.read_text(encoding="utf-8"))
    masked = frozen["masked_features"]
    if masked:
        idx = [feature_names.index(name) for name in masked]
        X_train = X_train.copy()
        X_val = X_val.copy()
        X_train[:, idx] = 0.0
        X_val[:, idx] = 0.0
    return X_train, y_train, groups_train, X_val, y_val, groups_val, modern_mask, frozen


def group_metrics(model: XGBRanker, X, y, groups, modern_mask=None) -> dict:
    scores = model.predict(X)
    top1 = top3 = 0
    mrr_sum = 0.0
    top1_modern = top1_hist = 0
    n_modern = n_hist = 0
    total = 0
    offset = 0
    for gi, size in enumerate(groups):
        s = scores[offset : offset + size]
        t = y[offset : offset + size]
        order = np.argsort(-s)
        ranked_targets = t[order]
        rank = int(np.argmax(ranked_targets)) if ranked_targets.any() else None
        offset += size
        total += 1
        if rank is None:
            continue
        top1 += int(rank == 0)
        top3 += int(rank < 3)
        mrr_sum += 1.0 / (rank + 1)
        if modern_mask is not None:
            if modern_mask[gi]:
                n_modern += 1
                top1_modern += int(rank == 0)
            else:
                n_hist += 1
                top1_hist += int(rank == 0)
    result = {
        "top1": top1 / total if total else 0.0,
        "top3": top3 / total if total else 0.0,
        "mrr": mrr_sum / total if total else 0.0,
        "n": total,
    }
    if modern_mask is not None:
        result["top1_modern"] = top1_modern / n_modern if n_modern else 0.0
        result["n_modern"] = n_modern
        result["top1_historical"] = top1_hist / n_hist if n_hist else 0.0
        result["n_historical"] = n_hist
    return result


def make_objective(X_train, y_train, groups_train, X_val, y_val, groups_val, modern_mask):
    def objective(trial: optuna.Trial) -> float:
        params = dict(
            tree_method="hist",
            random_state=SEED,
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
        model = XGBRanker(**params)
        model.fit(X_train, y_train, group=groups_train)

        val_metrics = group_metrics(model, X_val, y_val, groups_val, modern_mask)
        train_metrics = group_metrics(model, X_train, y_train, groups_train)

        trial.set_user_attr("val_top3", val_metrics["top3"])
        trial.set_user_attr("val_mrr", val_metrics["mrr"])
        trial.set_user_attr("val_top1_modern", val_metrics["top1_modern"])
        trial.set_user_attr("val_top1_historical", val_metrics["top1_historical"])
        trial.set_user_attr("train_top1", train_metrics["top1"])
        trial.set_user_attr("train_val_gap", train_metrics["top1"] - val_metrics["top1"])

        return val_metrics["top1"]

    return objective


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-trials", type=int, default=3)
    args = parser.parse_args()

    X_train, y_train, groups_train, X_val, y_val, groups_val, modern_mask, frozen = load_matrices()
    print(f"frozen feature config: {frozen['config_name']} (masked: {frozen['masked_features']})")
    print(f"train matrix: {X_train.shape}, val matrix: {X_val.shape}")

    study = optuna.create_study(
        study_name=STUDY_NAME,
        storage=f"sqlite:///{STUDY_DB}",
        direction="maximize",
        sampler=TPESampler(seed=SEED),
        load_if_exists=True,
    )

    objective = make_objective(X_train, y_train, groups_train, X_val, y_val, groups_val, modern_mask)

    start = time.time()
    study.optimize(objective, n_trials=args.n_trials)
    elapsed = time.time() - start

    print(f"\nran {args.n_trials} trials in {elapsed:.1f}s ({elapsed/args.n_trials:.2f}s/trial avg)")
    print(f"total trials in study so far: {len(study.trials)}")
    print(f"best value so far: {study.best_value:.4f}")
    print(f"best params so far: {study.best_params}")
    print(f"best trial user_attrs: {study.best_trial.user_attrs}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
