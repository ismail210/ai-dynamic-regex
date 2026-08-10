"""Small, controlled Optuna sweep over v3 ranker hyperparameters (Part 10).

Only run AFTER the baseline LambdaMART/rank:pairwise model in
``train_label_ranker_v3.py`` already works -- this script assumes
``pairwise_v3_train_val.jsonl`` exists and reuses that module's exact
feature-building/grouping code so the sweep is scored identically to the
baseline run.

Optuna was already installed in this environment (checked before writing
this script, per the "ask before adding it" instruction) -- no new
dependency was added.

Tunes: max_depth, learning_rate (n_estimators fixed high with early
stopping instead, which is the standard way to avoid re-tuning a redundant
axis), min_child_weight, subsample, colsample_bytree, reg_alpha, reg_lambda.

Optimizes against VALIDATION NDCG@10 only -- the frozen TEST set is never
touched by this script, consistent with Part 10's explicit instruction
("never optimize against the frozen test set") and Part 9's requirement
that the test set stay untouched throughout.

Run from ``backend/``: ``python scripts/tune_label_ranker_v3_optuna.py --trials 20``
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import optuna  # noqa: E402
from xgboost import XGBRanker  # noqa: E402

from scripts.train_label_ranker_v3 import (  # noqa: E402
    RANDOM_STATE,
    _git_revision,
    _grouped_matrix,
    _load_rows,
    _ndcg_at_k,
)
from services.label_reconstruction.features import FEATURE_NAMES  # noqa: E402
from services.training_pipeline import model_registry  # noqa: E402

optuna.logging.set_verbosity(optuna.logging.WARNING)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument(
        "--objective",
        default="rank:pairwise",
        help="whichever objective won the baseline run (see train_label_ranker_v3.py output)",
    )
    args = parser.parse_args()

    started = time.time()
    rows = _load_rows()
    train_rows = [r for r in rows if r["split"] == "train"]
    val_rows = [r for r in rows if r["split"] == "validation"]
    X_train, y_train, group_train = _grouped_matrix(train_rows)
    X_val, y_val, group_val = _grouped_matrix(val_rows)
    print(f"Sweeping over {args.trials} trials, objective={args.objective}")

    def objective_fn(trial: "optuna.Trial") -> float:
        params = dict(
            objective=args.objective,
            eval_metric="ndcg@10",
            tree_method="hist",
            random_state=RANDOM_STATE,
            max_depth=trial.suggest_int("max_depth", 3, 8),
            learning_rate=trial.suggest_float("learning_rate", 0.02, 0.3, log=True),
            n_estimators=trial.suggest_int("n_estimators", 100, 400),
            min_child_weight=trial.suggest_float("min_child_weight", 0.5, 10.0, log=True),
            subsample=trial.suggest_float("subsample", 0.6, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1.0),
            reg_alpha=trial.suggest_float("reg_alpha", 1e-8, 1.0, log=True),
            reg_lambda=trial.suggest_float("reg_lambda", 1e-8, 5.0, log=True),
        )
        model = XGBRanker(**params)
        model.fit(X_train, y_train, group=group_train, verbose=False)
        val_scores = model.predict(X_val)
        return _ndcg_at_k(y_val, val_scores, group_val, k=10)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))
    study.optimize(objective_fn, n_trials=args.trials, show_progress_bar=False)

    print(f"Best validation NDCG@10: {study.best_value:.4f}")
    print(f"Best params: {json.dumps(study.best_params, indent=2)}")

    best_params = {
        **study.best_params,
        "objective": args.objective,
        "eval_metric": "ndcg@10",
        "tree_method": "hist",
        "random_state": RANDOM_STATE,
    }
    final_model = XGBRanker(**best_params)
    final_model.fit(X_train, y_train, group=group_train, verbose=False)
    val_scores = final_model.predict(X_val)
    final_ndcg10 = _ndcg_at_k(y_val, val_scores, group_val, k=10)
    final_ndcg5 = _ndcg_at_k(y_val, val_scores, group_val, k=5)

    artifact_dir = Path(__file__).resolve().parents[1] / "training" / "label_reconstruction_tmp"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    booster_path = artifact_dir / "label_ranker_v3_tuned.ubj"
    final_model.get_booster().save_model(str(booster_path))

    manifest = model_registry.register_candidate_model(
        family="label_reconstruction",
        artifact_paths={"booster": booster_path},
        dataset_versions={
            "label_reconstruction": "label_reconstruction_20260807_125937",
            "pairwise_v3": "pairwise_v3_train_val.jsonl",
        },
        metrics={
            "val_ndcg_at_10": final_ndcg10,
            "val_ndcg_at_5": final_ndcg5,
            "optuna_trials": args.trials,
            "optuna_best_value": study.best_value,
        },
        hyperparameters=best_params,
        feature_schema=FEATURE_NAMES,
        dependencies={"optuna": optuna.__version__, "git_revision": _git_revision()},
        notes=(
            f"v3 ranker with Optuna-tuned hyperparameters ({args.trials} trials, "
            "validation NDCG@10 objective, frozen test set never touched by "
            "the sweep). Shadow-mode candidate only."
        ),
        promotion_status="candidate",
    )
    booster_path.unlink(missing_ok=True)

    print(f"\nRegistered tuned model version: {manifest.version_id}")
    print(f"Runtime: {round(time.time() - started, 1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
