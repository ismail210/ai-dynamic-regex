"""Train the schema-v5 (``is_fallback_broadened``) Structural Reconstruction
candidate ranker.

Combines TWO dataset versions, each row keeping its own recorded split:

  - the FROZEN, already-promoted-model dataset
    (``label_reconstruction_production_aligned_20260828`` -- standard
    candidates only, ``is_fallback_broadened`` is implicitly False for
    every row)
  - the new, additive broadened-fallback slice
    (``label_reconstruction_broadened_20260914`` -- deletion/insertion
    queries the standard generator abstained on with zero candidates)

Neither dataset is regenerated or modified by this script (Section 6/13 of
the broadened-ranker brief: the original stays available for comparison).
Produces a NEW, separately versioned model artifact -- never overwrites the
currently-promoted one; promotion is a separate, explicit decision made
after the benchmark gates in evaluate_broadened_ranker.py pass.

Run from ``backend/``: ``python scripts/train_label_ranker_v4_broadened.py``
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

from services.label_reconstruction.features import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    pair_features,
)
from services.training_pipeline import model_registry  # noqa: E402

RANDOM_STATE = 20260914
BACKEND_DIR = Path(__file__).resolve().parents[1]
STANDARD_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_production_aligned"
BROADENED_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_broadened"
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
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BACKEND_DIR.parent).decode().strip()
    except Exception:
        return "unknown"


def _load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _grouped_matrix(rows: List[dict]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """One ranker group per distinct query. ``rows`` may mix standard and
    broadened-origin rows freely -- each row carries its own
    ``is_fallback_broadened`` flag, which is all `pair_features` needs to
    build the correct feature vector regardless of which dataset it came
    from."""

    features, labels, group_sizes, group_kinds = [], [], [], []
    grouped: Dict[str, List[dict]] = {}
    for row in rows:
        grouped.setdefault(row["query"], []).append(row)
    for query_rows in grouped.values():
        if len(query_rows) < 2 or sum(row["target"] for row in query_rows) != 1:
            continue
        group_sizes.append(len(query_rows))
        group_kinds.append("broadened" if query_rows[0].get("is_fallback_broadened") else "standard")
        for row in query_rows:
            row_features = pair_features(
                row["query"],
                row["candidate"],
                rank=row.get("deterministic_rank"),
                reasons=row.get("generation_reasons"),
                fuzzy_rank=row.get("fuzzy_rank"),
                is_fallback_broadened=bool(row.get("is_fallback_broadened", False)),
            )
            features.append([row_features[name] for name in FEATURE_NAMES])
            labels.append(row["target"])
    return (
        np.array(features, dtype=np.float64),
        np.array(labels, dtype=np.int32),
        np.array(group_sizes),
        group_kinds,
    )


def _ndcg_at_k(labels: np.ndarray, scores: np.ndarray, group_sizes: np.ndarray, k: int = 10) -> float:
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


def _ndcg_by_kind(labels, scores, group_sizes, group_kinds, kind: str, k: int = 10) -> float:
    offset = 0
    sub_labels, sub_scores, sub_sizes = [], [], []
    for size, this_kind in zip(group_sizes, group_kinds):
        if this_kind == kind:
            sub_labels.append(labels[offset : offset + size])
            sub_scores.append(scores[offset : offset + size])
            sub_sizes.append(size)
        offset += size
    if not sub_sizes:
        return float("nan")
    return _ndcg_at_k(np.concatenate(sub_labels), np.concatenate(sub_scores), np.array(sub_sizes), k=k)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    started = time.time()

    standard_manifest = json.loads((STANDARD_DIR / "manifest.json").read_text(encoding="utf-8"))
    broadened_manifest = json.loads((BROADENED_DIR / "manifest.json").read_text(encoding="utf-8"))

    standard_rows = _load_jsonl(STANDARD_DIR / "pairwise.jsonl")
    for row in standard_rows:
        row.setdefault("is_fallback_broadened", False)
    broadened_rows = _load_jsonl(BROADENED_DIR / "pairwise.jsonl")

    all_rows = standard_rows + broadened_rows
    train_rows = [r for r in all_rows if r["split"] == "train"]
    val_rows = [r for r in all_rows if r["split"] == "validation"]
    print(f"Pairwise rows -- train: {len(train_rows)} (standard {sum(1 for r in train_rows if not r['is_fallback_broadened'])}, "
          f"broadened {sum(1 for r in train_rows if r['is_fallback_broadened'])}), validation: {len(val_rows)}")

    X_train, y_train, group_train, _kinds_train = _grouped_matrix(train_rows)
    X_val, y_val, group_val, kinds_val = _grouped_matrix(val_rows)
    print(f"Train groups: {len(group_train)}, validation groups: {len(group_val)}")

    results = {}
    for objective in ("rank:pairwise", "rank:ndcg"):
        t0 = time.time()
        model = XGBRanker(objective=objective, eval_metric="ndcg@10", **BASE_PARAMS)
        model.fit(
            X_train, y_train, group=group_train,
            eval_set=[(X_val, y_val)], eval_group=[list(group_val)], verbose=False,
        )
        val_scores = model.predict(X_val)
        metrics = {
            "objective": objective,
            "val_ndcg_at_10": _ndcg_at_k(y_val, val_scores, group_val, k=10),
            "val_ndcg_at_5": _ndcg_at_k(y_val, val_scores, group_val, k=5),
            "val_ndcg_at_10_standard": _ndcg_by_kind(y_val, val_scores, group_val, kinds_val, "standard", k=10),
            "val_ndcg_at_10_broadened": _ndcg_by_kind(y_val, val_scores, group_val, kinds_val, "broadened", k=10),
            "train_seconds": round(time.time() - t0, 1),
        }
        results[objective] = (model, metrics)
        print(f"[{objective}] {metrics}")

    best_objective = max(results, key=lambda obj: results[obj][1]["val_ndcg_at_10"])
    best_model, best_metrics = results[best_objective]
    print(f"\nBest objective: {best_objective} ({best_metrics})")

    artifact_dir = BACKEND_DIR / "training" / "label_reconstruction_tmp"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    booster_path = artifact_dir / "label_ranker_v4_broadened.ubj"
    best_model.get_booster().save_model(str(booster_path))

    manifest = model_registry.register_candidate_model(
        family="label_reconstruction",
        artifact_paths={"booster": booster_path},
        dataset_versions={
            "label_reconstruction_standard": standard_manifest["dataset_version"],
            "label_reconstruction_broadened": broadened_manifest["dataset_version"],
            "candidate_generator": "services.label_reconstruction.candidates.generate_candidates",
            "broadened_candidate_generator": "services.label_reconstruction.candidates._fuzzy_candidates",
        },
        metrics={
            "rank_pairwise_val_ndcg_at_10": results["rank:pairwise"][1]["val_ndcg_at_10"],
            "rank_ndcg_val_ndcg_at_10": results["rank:ndcg"][1]["val_ndcg_at_10"],
            "best_objective": best_objective,
            **best_metrics,
        },
        hyperparameters={**BASE_PARAMS, "objective": best_objective},
        feature_schema=FEATURE_NAMES,
        dependencies={
            "xgboost": xgb.__version__,
            "git_revision": _git_revision(),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
        },
        notes=(
            "Schema-v5 Structural Reconstruction ranker: adds is_fallback_broadened "
            "(+ reason_fuzzy_fallback_broadened) so deletion/insertion queries the "
            "standard generator abstains on (zero candidates, e.g. W10X3, W18XX40) "
            "are ranked by this model instead of raw SequenceMatcher ordering. "
            "Trained on the frozen standard dataset PLUS the additive broadened "
            "slice; no PDF-attack-benchmark data anywhere in training. "
            "Candidate only; not active or promoted -- see "
            "reports/broadened_xgb_ranker_benchmark.md for the promotion decision."
        ),
        promotion_status="candidate",
    )
    booster_path.unlink(missing_ok=True)

    print(f"\nRegistered model version: {manifest.version_id}")
    print(f"Runtime: {round(time.time() - started, 1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
