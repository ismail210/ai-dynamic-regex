"""
Phase 1 of the post-fix Optuna prep: decide the feature set to freeze before
tuning. VALIDATION SPLIT ONLY -- the test split is never touched here.

Builds the train/validation feature matrices exactly once (reusing
generate_candidates_v3 through the shared
services.label_reconstruction.features.features_from_candidate_set, the
same fix scripts/evaluate_v16_baselines.py and
scripts/ablate_v16_ranker_features.py already use), then compares:

  A  all_features
  B  without generation_provenance (deterministic_rank, fuzzy_rank, reason_*)
  C1 without generation_provenance ranks only (deterministic_rank, fuzzy_rank)
  C2 without generation_provenance reasons only (reason_* one-hots)

Also caches the built matrices to
training/experiments/v16_ranker_optuna_<date>/{train,val}_full.npz so the
Optuna phase does not have to repeat the ~15-20 min candidate-generation
pass -- hyperparameters don't change what generate_candidates_v3 returns.

Run from `backend/`: python scripts/phase1_feature_freeze.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Dict, List

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
REPORTS_DIR = DATABASE_DIR / "reports"
OUT_REPORT = REPORTS_DIR / "aisc_v16_phase1_feature_freeze.md"

CANDIDATE_LIMIT = 25
RANDOM_STATE = 20260813
BASE_PARAMS = dict(
    tree_method="hist",
    max_depth=5,
    learning_rate=0.1,
    n_estimators=200,
    subsample=0.9,
    colsample_bytree=0.9,
    random_state=RANDOM_STATE,
)

PROVENANCE_RANKS = ["deterministic_rank", "fuzzy_rank"]
PROVENANCE_REASONS = [name for name in FEATURE_NAMES if name.startswith("reason_")]
PROVENANCE_ALL = PROVENANCE_RANKS + PROVENANCE_REASONS


def _load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_matrix(rows: List[dict]):
    X, y, groups = [], [], []
    for _query, group in itertools.groupby(rows, key=lambda r: r["query"]):
        group = list(group)
        if len(group) < 2 or sum(r["target"] for r in group) == 0:
            continue
        candidate_set = generate_candidates_v3(group[0]["query"], limit=CANDIDATE_LIMIT)
        groups.append(len(group))
        for row in group:
            features = features_from_candidate_set(row["candidate"], candidate_set)
            X.append([features[name] for name in FEATURE_NAMES])
            y.append(row["target"])
    return np.array(X, dtype=float), np.array(y), np.array(groups)


def zero_out(X: np.ndarray, names: List[str]) -> np.ndarray:
    masked = X.copy()
    for name in names:
        masked[:, FEATURE_NAMES.index(name)] = 0.0
    return masked


def group_top1(model: XGBRanker, X_val, y_val, groups_val, modern_mask=None):
    scores = model.predict(X_val)
    correct = 0
    correct_modern = 0
    correct_hist = 0
    n_modern = 0
    n_hist = 0
    total = 0
    offset = 0
    for gi, size in enumerate(groups_val):
        s = scores[offset : offset + size]
        t = y_val[offset : offset + size]
        top = int(np.argmax(s))
        hit = int(t[top] == 1)
        correct += hit
        total += 1
        if modern_mask is not None:
            if modern_mask[gi]:
                n_modern += 1
                correct_modern += hit
            else:
                n_hist += 1
                correct_hist += hit
        offset += size
    result = {"top1": correct / total if total else 0.0, "n": total}
    if modern_mask is not None:
        result["top1_modern"] = correct_modern / n_modern if n_modern else 0.0
        result["n_modern"] = n_modern
        result["top1_historical"] = correct_hist / n_hist if n_hist else 0.0
        result["n_historical"] = n_hist
    return result


def group_scope_mask(rows: List[dict]) -> List[bool]:
    """One bool per query-group (True=modern), aligned with build_matrix's grouping."""
    mask = []
    for _query, group in itertools.groupby(rows, key=lambda r: r["query"]):
        group = list(group)
        if len(group) < 2 or sum(r["target"] for r in group) == 0:
            continue
        mask.append(group[0]["catalog_scope"] == "modern")
    return mask


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)

    pairwise_rows = _load_jsonl(DATA_DIR / "pairwise.jsonl")
    train_rows = [r for r in pairwise_rows if r["split"] == "train"]
    val_rows = [r for r in pairwise_rows if r["split"] == "validation"]

    database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    try:
        print("building train matrix (candidate generation, several minutes)...")
        X_train, y_train, groups_train = build_matrix(train_rows)
        print(f"train matrix: {X_train.shape}, groups: {len(groups_train)}")
        print("building validation matrix...")
        X_val, y_val, groups_val = build_matrix(val_rows)
        print(f"val matrix: {X_val.shape}, groups: {len(groups_val)}")
        val_modern_mask = group_scope_mask(val_rows)
        assert len(val_modern_mask) == len(groups_val)

        # Cache for the Optuna phase -- candidate generation is hyperparameter-
        # independent, so this ~15-20 min pass need not repeat per trial.
        np.savez_compressed(
            EXPERIMENT_DIR / "train_full.npz",
            X=X_train, y=y_train, groups=groups_train,
        )
        np.savez_compressed(
            EXPERIMENT_DIR / "val_full.npz",
            X=X_val, y=y_val, groups=groups_val,
            modern_mask=np.array(val_modern_mask),
        )
        (EXPERIMENT_DIR / "feature_names.json").write_text(
            json.dumps(FEATURE_NAMES, indent=2), encoding="utf-8"
        )
        print(f"cached matrices to {EXPERIMENT_DIR}")

        configs = {
            "A_all_features": [],
            "B_without_generation_provenance": PROVENANCE_ALL,
            "C1_without_provenance_ranks_only": PROVENANCE_RANKS,
            "C2_without_provenance_reasons_only": PROVENANCE_REASONS,
        }

        results: Dict[str, dict] = {}
        for name, masked_names in configs.items():
            Xt = zero_out(X_train, masked_names) if masked_names else X_train
            Xv = zero_out(X_val, masked_names) if masked_names else X_val
            model = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
            model.fit(Xt, y_train, group=groups_train)
            results[name] = group_top1(model, Xv, y_val, groups_val, val_modern_mask)
            print(f"{name}: {results[name]}")

        baseline = results["A_all_features"]["top1"]
        lines = ["# Phase 1: feature-set freeze decision (validation only)\n"]
        lines.append(
            f"Train groups: {len(groups_train)}, validation groups: {len(groups_val)}. "
            "Metric: group top-1 accuracy. Test split not used.\n"
        )
        lines.append("\n| Config | Val Top-1 | Delta vs A | Modern Top-1 | Historical Top-1 |\n|---|---|---|---|---|\n")
        for name, r in results.items():
            delta = r["top1"] - baseline
            lines.append(
                f"| {name} | {r['top1']:.4f} | {delta:+.4f} | {r['top1_modern']:.4f} "
                f"| {r['top1_historical']:.4f} |\n"
            )
        OUT_REPORT.write_text("".join(lines), encoding="utf-8")
        print(f"report: {OUT_REPORT}")
        return 0
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()


if __name__ == "__main__":
    raise SystemExit(main())
