"""
Diagnostic: isolate whether the test-set regression (tuned model 0.7291
test top1, below the untuned-all-features fixed ranker's 0.7394) comes from
(a) the frozen feature config (masking deterministic_rank/fuzzy_rank) or
(b) the Optuna-searched hyperparameters, by evaluating the FROZEN FEATURE
CONFIG with the ORIGINAL (untuned) BASE_PARAMS on the test set -- the one
cell of the 2x2 (features x params) grid not yet measured.

Run from `backend/`: python scripts/diagnose_val_test_gap.py
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
EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_optuna_20260816"

CANDIDATE_LIMIT = 25
SEED = 20260813
BASE_PARAMS = dict(
    tree_method="hist",
    max_depth=5,
    learning_rate=0.1,
    n_estimators=200,
    subsample=0.9,
    colsample_bytree=0.9,
    random_state=SEED,
)


def _load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _bucket():
    return {"n": 0, "top1": 0, "top3": 0, "mrr_sum": 0.0}


def _update(bucket, rank):
    bucket["n"] += 1
    if rank is not None:
        bucket["top1"] += int(rank == 0)
        bucket["top3"] += int(rank < 3)
        bucket["mrr_sum"] += 1.0 / (rank + 1)


def _finalize(bucket):
    n = bucket["n"] or 1
    return {"n": bucket["n"], "top1": bucket["top1"] / n, "top3": bucket["top3"] / n, "mrr": bucket["mrr_sum"] / n}


def main() -> int:
    frozen = json.loads((EXPERIMENT_DIR / "frozen_feature_config.json").read_text(encoding="utf-8"))
    masked_features = frozen["masked_features"]
    masked_idx = [FEATURE_NAMES.index(name) for name in masked_features]

    train = np.load(EXPERIMENT_DIR / "train_full.npz")
    X_train, y_train, groups_train = train["X"].copy(), train["y"], train["groups"]
    X_train[:, masked_idx] = 0.0

    print(f"training config-C1 (ranks masked) + BASE_PARAMS (untuned): {BASE_PARAMS}")
    model = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
    model.fit(X_train, y_train, group=groups_train)

    pointwise_rows = _load_jsonl(DATA_DIR / "pointwise.jsonl")
    test_rows = [r for r in pointwise_rows if r["split"] == "test"]

    database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    try:
        overall = _bucket()
        by_scope = {"modern": _bucket(), "historical": _bucket()}
        for row in test_rows:
            target = row["clean_designation"]
            corrupted = row["corrupted_text"]
            scope = row["catalog_scope"]
            candidate_set = generate_candidates_v3(corrupted, limit=CANDIDATE_LIMIT)
            candidates = candidate_set.candidates
            if not candidates:
                rank = None
            else:
                feats = np.array(
                    [[features_from_candidate_set(c, candidate_set)[name] for name in FEATURE_NAMES] for c in candidates]
                )
                feats[:, masked_idx] = 0.0
                scores = model.predict(feats)
                ordered = [c for _s, c in sorted(zip(scores, candidates), key=lambda p: -p[0])]
                rank = ordered.index(target) if target in ordered else None
            _update(overall, rank)
            _update(by_scope[scope], rank)

        m = _finalize(overall)
        print(f"\nConfig C1 (ranks masked) + BASE_PARAMS on TEST: top1={m['top1']:.4f} top3={m['top3']:.4f} mrr={m['mrr']:.4f} n={m['n']}")
        for scope in ("modern", "historical"):
            ms = _finalize(by_scope[scope])
            print(f"  {scope}: top1={ms['top1']:.4f} top3={ms['top3']:.4f} mrr={ms['mrr']:.4f} n={ms['n']}")
        return 0
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()


if __name__ == "__main__":
    raise SystemExit(main())
