"""Train the first learned candidate ranker for damaged AISC labels (Part L/M).

Simplest model that could materially improve on the deterministic/string-
similarity baselines: a gradient-boosted binary classifier (XGBoost) over
the hand-engineered (query, candidate) pair features in
``services.label_reconstruction.features``, trained on the pairwise rows
from the versioned dataset (1 positive + several hard negatives per
corrupted string). This is option (A) from Part L -- explicitly NOT a
character transformer or sequence generator, per "do not jump to a large
language model" / "prefer ranking over unconstrained generation".

Reproducibility (Part M): the dataset version, xgboost params, and a fixed
``random_state`` are all recorded in the model manifest via
``services.training_pipeline.model_registry``, alongside train/validation/
test metrics so later experiments are comparable.

Run from ``backend/``: ``python scripts/train_label_ranker.py``
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import xgboost as xgb  # noqa: E402

from services.label_reconstruction.features import FEATURE_NAMES, feature_vector  # noqa: E402
from services.training_pipeline import dataset_registry, model_registry  # noqa: E402

RANDOM_STATE = 20260807
XGB_PARAMS = {
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "max_depth": 5,
    "eta": 0.1,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "seed": RANDOM_STATE,
}
NUM_BOOST_ROUND = 200
EARLY_STOPPING_ROUNDS = 15


def _git_revision() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2])
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _build_matrix(rows: List[dict]) -> "xgb.DMatrix":
    features = [
        feature_vector(
            row["query"],
            row["candidate"],
            rank=row.get("deterministic_rank"),
            reasons=row.get("generation_reasons"),
        )
        for row in rows
    ]
    labels = [row["target"] for row in rows]
    return xgb.DMatrix(features, label=labels, feature_names=FEATURE_NAMES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-version", default=None, help="defaults to the active version")
    args = parser.parse_args()

    started = time.time()
    all_rows = dataset_registry.load_dataset_samples("label_reconstruction", args.dataset_version)
    if not all_rows:
        print("No dataset rows found -- run generate_label_corruption_dataset.py first.")
        return 1
    manifest = dataset_registry.load_dataset_manifest("label_reconstruction", args.dataset_version)
    dataset_version_id = manifest["version_id"]

    pairwise = [row for row in all_rows if row.get("row_kind") == "pairwise"]
    train_rows = [row for row in pairwise if row["split"] == "train"]
    val_rows = [row for row in pairwise if row["split"] == "validation"]
    test_rows = [row for row in pairwise if row["split"] == "test"]
    print(f"Dataset version: {dataset_version_id}")
    print(f"Pairwise rows -- train: {len(train_rows)}, val: {len(val_rows)}, test: {len(test_rows)}")

    dtrain = _build_matrix(train_rows)
    dval = _build_matrix(val_rows)
    dtest = _build_matrix(test_rows)

    evals_result: Dict[str, dict] = {}
    booster = xgb.train(
        XGB_PARAMS,
        dtrain,
        num_boost_round=NUM_BOOST_ROUND,
        evals=[(dtrain, "train"), (dval, "validation")],
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
        evals_result=evals_result,
        verbose_eval=False,
    )

    def _pairwise_accuracy(dmatrix: "xgb.DMatrix", rows: List[dict]) -> float:
        preds = booster.predict(dmatrix)
        correct = sum(1 for p, row in zip(preds, rows) if (p >= 0.5) == bool(row["target"]))
        return correct / len(rows) if rows else 0.0

    train_logloss = evals_result["train"]["logloss"][-1]
    val_logloss = evals_result["validation"]["logloss"][-1]
    metrics = {
        "train_logloss": round(train_logloss, 4),
        "validation_logloss": round(val_logloss, 4),
        "train_pairwise_accuracy": round(_pairwise_accuracy(dtrain, train_rows), 4),
        "validation_pairwise_accuracy": round(_pairwise_accuracy(dval, val_rows), 4),
        "test_pairwise_accuracy": round(_pairwise_accuracy(dtest, test_rows), 4),
        "best_iteration": booster.best_iteration,
        "n_train_pairs": len(train_rows),
        "n_validation_pairs": len(val_rows),
        "n_test_pairs": len(test_rows),
    }
    print(json.dumps(metrics, indent=2))

    artifact_dir = Path(__file__).resolve().parents[1] / "training" / "label_reconstruction_tmp"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    booster_path = artifact_dir / "label_ranker.xgb"
    booster.save_model(str(booster_path))

    manifest_out = model_registry.register_candidate_model(
        family="label_reconstruction",
        artifact_paths={"booster": booster_path},
        dataset_versions={"label_reconstruction": dataset_version_id},
        metrics=metrics,
        hyperparameters={**XGB_PARAMS, "num_boost_round": NUM_BOOST_ROUND, "early_stopping_rounds": EARLY_STOPPING_ROUNDS},
        feature_schema=FEATURE_NAMES,
        dependencies={"xgboost": xgb.__version__, "git_revision": _git_revision()},
        notes=(
            "First trained candidate ranker for damaged AISC label reconstruction "
            "(Part L option A: XGBoost pairwise/pointwise classifier over hand-"
            "engineered character-level features). Shadow-mode only -- see "
            "ML_LABEL_RANKER_ENABLED / ML_LABEL_RANKER_SHADOW in config.py. Not "
            "promoted automatically; promotion is a separate, explicit decision."
        ),
        promotion_status="candidate",
    )
    booster_path.unlink(missing_ok=True)

    print(f"\nRegistered model version: {manifest_out.version_id}")
    print(f"Runtime: {round(time.time() - started, 1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
