"""
Phase 1: comprehensive, ONE-PASS validation of C1 (deterministic_rank/
fuzzy_rank masked) + original untuned BASE_PARAMS on legacy_external_test.

Single live-candidate-generation pass over the 6512 test rows (the
expensive part), saving full per-row detail, then every requested
breakdown (holdout, corruption type, severity, family, edit-distance bins,
family-prefix damage) is computed from that in-memory table -- no repeat
candidate generation.

Reuses the train feature matrix cached by the prior Optuna phase
(training/experiments/v16_ranker_optuna_20260816/train_full.npz) since
candidate generation / features have not changed -- documented in
phase0_reproducibility.json rather than silently reused.

Run from `backend/`: python scripts/phase1_c1_untuned_validation.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
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
from services.label_reconstruction.corruption import family_of  # noqa: E402
from services.label_reconstruction.features import (  # noqa: E402
    FEATURE_NAMES,
    _edit_distance,
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
    return {
        "n": b["n"], "candidate_recall": b["cand_present"] / n,
        "top1": b["top1"] / n, "top3": b["top3"] / n, "mrr": b["mrr_sum"] / n,
    }


def family_prefix_damage(corrupted: str, true_family: str) -> str:
    inferred = family_of(corrupted)
    if inferred == true_family:
        return "intact"
    if inferred and corrupted.upper().startswith(true_family):
        return "intact"  # family_of picked a shorter/longer overlapping code but text still starts right
    if any(ch.isalpha() for ch in corrupted[: len(true_family) + 1]):
        return "partially_damaged"
    return "destroyed"


def main() -> int:
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)

    train = np.load(OLD_EXPERIMENT_DIR / "train_full.npz")
    X_train, y_train, groups_train = train["X"].copy(), train["y"], train["groups"]
    X_train[:, MASKED_IDX] = 0.0

    print(f"training C1 + untuned BASE_PARAMS: {BASE_PARAMS}")
    model = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
    model.fit(X_train, y_train, group=groups_train)

    pointwise_rows = _load_jsonl(DATA_DIR / "pointwise.jsonl")
    test_rows = [r for r in pointwise_rows if r["split"] == "test"]
    print(f"test rows: {len(test_rows)}")

    database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    detail_rows = []
    try:
        for row in test_rows:
            target = row["clean_designation"]
            corrupted = row["corrupted_text"]
            candidate_set = generate_candidates_v3(corrupted, limit=CANDIDATE_LIMIT)
            candidates = candidate_set.candidates
            cand_present = target in candidates
            if not candidates:
                rank = None
            else:
                feats = np.array(
                    [[features_from_candidate_set(c, candidate_set)[name] for name in FEATURE_NAMES] for c in candidates]
                )
                feats[:, MASKED_IDX] = 0.0
                scores = model.predict(feats)
                ordered = [c for _s, c in sorted(zip(scores, candidates), key=lambda p: -p[0])]
                rank = ordered.index(target) if target in ordered else None

            tags = row["corruption_type"] or ["none"]
            sev = row["corruption_severity"]
            corruption_key = tags[0] if sev == 1 else f"multi_corruption_severity_{sev}"
            edit_dist = _edit_distance(corrupted, target, ocr_aware=False)
            true_family = row["family"]
            prefix_status = family_prefix_damage(corrupted, true_family)

            detail_rows.append({
                "clean_designation": target,
                "corrupted_text": corrupted,
                "family": true_family,
                "catalog_scope": row["catalog_scope"],
                "designation_holdout": row["designation_holdout"],
                "corruption_key": corruption_key,
                "corruption_severity": sev,
                "edit_distance": edit_dist,
                "family_prefix_status": prefix_status,
                "candidate_present": cand_present,
                "rank": rank,
                "n_candidates": len(candidates),
            })
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()

    (EXPERIMENT_DIR / "phase1_detail_rows.json").write_text(json.dumps(detail_rows), encoding="utf-8")
    print(f"saved {len(detail_rows)} detail rows")

    # ---- Aggregations ----
    def agg_by(keyfn):
        buckets = defaultdict(_bucket)
        for r in detail_rows:
            _update(buckets[keyfn(r)], r["rank"], r["candidate_present"])
        return {k: _finalize(v) for k, v in buckets.items()}

    overall = _bucket()
    for r in detail_rows:
        _update(overall, r["rank"], r["candidate_present"])
    overall_m = _finalize(overall)
    print(f"\n=== Phase 0 reproduction check ===")
    print(f"overall: top1={overall_m['top1']:.4f} top3={overall_m['top3']:.4f} mrr={overall_m['mrr']:.4f} (expect ~0.7446/0.8150/0.7814)")

    by_holdout = agg_by(lambda r: "holdout" if r["designation_holdout"] else "seen_designation")
    by_corruption = agg_by(lambda r: r["corruption_key"])
    by_severity = agg_by(lambda r: r["corruption_severity"])
    by_family = agg_by(lambda r: r["family"])
    by_prefix = agg_by(lambda r: r["family_prefix_status"])

    def edit_bin(d):
        if d <= 1:
            return "0-1"
        if d <= 2:
            return "2"
        if d <= 4:
            return "3-4"
        if d <= 7:
            return "5-7"
        return "8+"
    by_edit_distance = agg_by(lambda r: edit_bin(r["edit_distance"]))

    results = {
        "overall": overall_m,
        "by_holdout": by_holdout,
        "by_corruption": by_corruption,
        "by_severity": by_severity,
        "by_family": by_family,
        "by_family_prefix_damage": by_prefix,
        "by_edit_distance_bin": by_edit_distance,
    }
    (EXPERIMENT_DIR / "phase1_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    for name, table in results.items():
        if name == "overall":
            continue
        print(f"\n=== {name} ===")
        for k, v in sorted(table.items(), key=lambda kv: -kv[1]["n"]):
            print(f"  {k}: n={v['n']} recall={v['candidate_recall']:.4f} top1={v['top1']:.4f} top3={v['top3']:.4f} mrr={v['mrr']:.4f}")

    print(f"\nsaved results to {EXPERIMENT_DIR / 'phase1_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
