"""Train v3: a true learning-to-rank model (Part 7/8), replacing v2's
pointwise binary-classification objective.

Trains TWO XGBRanker configurations -- ``rank:pairwise`` (RankNet-style
pairwise loss) and ``rank:ndcg`` (LambdaMART: NDCG-optimizing pairwise
gradients) -- each query's candidates as one ranking group, and keeps
whichever scores higher validation NDCG@10. This is deliberately NOT a
single fixed choice: Part 7 asks for both to be evaluated, and which one
wins is an empirical question, not a foregone conclusion.

Reproducible: fixed ``RANDOM_STATE`` seed, git revision and dataset/negative-
mining metadata recorded in the registered model manifest (Part M/9's
experiment-tracking requirement).

Run from ``backend/``: ``python scripts/train_label_ranker_v3.py``
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import xgboost as xgb  # noqa: E402
from xgboost import XGBRanker  # noqa: E402

from services.label_reconstruction.features import FEATURE_NAMES, pair_features  # noqa: E402
from services.training_pipeline import model_registry  # noqa: E402

RANDOM_STATE = 20260807
PAIRWISE_PATH = (
    Path(__file__).resolve().parents[1]
    / "training"
    / "datasets"
    / "label_reconstruction"
    / "pairwise_v3_train_val.jsonl"
)
BASE_PARAMS = dict(
    tree_method="hist",
    max_depth=5,
    learning_rate=0.1,
    n_estimators=200,
    subsample=0.9,
    colsample_bytree=0.9,
    random_state=RANDOM_STATE,
)


def _git_revision() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _load_rows() -> List[dict]:
    rows = []
    with PAIRWISE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _grouped_matrix(rows: List[dict]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rows must already be contiguous by query (build_pairwise_dataset_v3
    guarantees this: positive + its negatives are appended together, per
    pointwise row, in iteration order). Returns (X, y, group_sizes)."""

    features = []
    labels = []
    group_sizes = []
    current_query = None
    current_count = 0
    for row in rows:
        if row["query"] != current_query:
            if current_count:
                group_sizes.append(current_count)
            current_query = row["query"]
            current_count = 0
        current_count += 1
        row_features = pair_features(
            row["query"],
            row["candidate"],
            rank=row.get("deterministic_rank"),
            reasons=row.get("generation_reasons"),
            fuzzy_rank=row.get("fuzzy_rank"),
        )
        features.append([row_features[name] for name in FEATURE_NAMES])
        labels.append(row["target"])
    if current_count:
        group_sizes.append(current_count)
    return np.array(features, dtype=np.float64), np.array(labels, dtype=np.int32), np.array(group_sizes)


def _ndcg_at_k(labels: np.ndarray, scores: np.ndarray, group_sizes: np.ndarray, k: int = 10) -> float:
    """Mean NDCG@k across groups -- binary relevance (0/1), single relevant
    item per group in this dataset (exactly one positive per query)."""

    ndcgs = []
    offset = 0
    for size in group_sizes:
        group_labels = labels[offset : offset + size]
        group_scores = scores[offset : offset + size]
        offset += size
        order = np.argsort(-group_scores)
        ranked_labels = group_labels[order][:k]
        dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ranked_labels))
        ideal = sorted(group_labels, reverse=True)[:k]
        idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal))
        ndcgs.append(dcg / idcg if idcg > 0 else 0.0)
    return float(np.mean(ndcgs)) if ndcgs else 0.0


def _train_one(objective: str, X_train, y_train, group_train, X_val, y_val, group_val) -> Tuple[XGBRanker, Dict]:
    model = XGBRanker(objective=objective, eval_metric="ndcg@10", **BASE_PARAMS)
    model.fit(
        X_train,
        y_train,
        group=group_train,
        eval_set=[(X_val, y_val)],
        eval_group=[list(group_val)],
        verbose=False,
    )
    val_scores = model.predict(X_val)
    val_ndcg10 = _ndcg_at_k(y_val, val_scores, group_val, k=10)
    val_ndcg5 = _ndcg_at_k(y_val, val_scores, group_val, k=5)
    return model, {"objective": objective, "val_ndcg_at_10": val_ndcg10, "val_ndcg_at_5": val_ndcg5}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()

    started = time.time()
    if not PAIRWISE_PATH.exists():
        print(f"{PAIRWISE_PATH} not found -- run build_pairwise_dataset_v3.py first.")
        return 1

    rows = _load_rows()
    train_rows = [r for r in rows if r["split"] == "train"]
    val_rows = [r for r in rows if r["split"] == "validation"]
    print(f"Pairwise rows -- train: {len(train_rows)}, validation: {len(val_rows)}")

    X_train, y_train, group_train = _grouped_matrix(train_rows)
    X_val, y_val, group_val = _grouped_matrix(val_rows)
    print(f"Train groups: {len(group_train)}, validation groups: {len(group_val)}")

    results = {}
    for objective in ("rank:pairwise", "rank:ndcg"):
        t0 = time.time()
        model, metrics = _train_one(objective, X_train, y_train, group_train, X_val, y_val, group_val)
        metrics["train_seconds"] = round(time.time() - t0, 1)
        results[objective] = (model, metrics)
        print(f"[{objective}] {metrics}")

    best_objective = max(results, key=lambda obj: results[obj][1]["val_ndcg_at_10"])
    best_model, best_metrics = results[best_objective]
    print(f"\nBest objective: {best_objective} ({best_metrics})")

    artifact_dir = Path(__file__).resolve().parents[1] / "training" / "label_reconstruction_tmp"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    booster_path = artifact_dir / "label_ranker_v3.ubj"
    best_model.get_booster().save_model(str(booster_path))

    manifest = model_registry.register_candidate_model(
        family="label_reconstruction",
        artifact_paths={"booster": booster_path},
        dataset_versions={
            "label_reconstruction": "label_reconstruction_20260807_125937",
            "pairwise_v3": "pairwise_v3_train_val.jsonl",
        },
        metrics={
            "rank_pairwise_val_ndcg_at_10": results["rank:pairwise"][1]["val_ndcg_at_10"],
            "rank_ndcg_val_ndcg_at_10": results["rank:ndcg"][1]["val_ndcg_at_10"],
            "best_objective": best_objective,
            **best_metrics,
        },
        hyperparameters={**BASE_PARAMS, "objective": best_objective},
        feature_schema=FEATURE_NAMES,
        dependencies={"xgboost": xgb.__version__, "git_revision": _git_revision()},
        notes=(
            "v3 learning-to-rank model (Part 7/8): XGBRanker with query-"
            f"grouped {best_objective} objective (chosen over the alternative "
            "by validation NDCG@10), family-aware structural-compatibility "
            "features, and hard negatives mined from v2's actual train/"
            "validation mistakes + structural near-misses + v3's own "
            "generator. Shadow-mode candidate only -- see promotion "
            "decision in the v3 evaluation report."
        ),
        promotion_status="candidate",
    )
    booster_path.unlink(missing_ok=True)

    print(f"\nRegistered model version: {manifest.version_id}")
    print(f"Runtime: {round(time.time() - started, 1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
