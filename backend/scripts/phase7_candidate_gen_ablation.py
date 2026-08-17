"""
Phase 7/8: measure the effect of the ONE targeted candidate-generation fix
(_fuzzy_candidates now searches the full catalog instead of a
family_of()-scoped bucket that could misroute to a wrong or spurious
pseudo-family bucket -- see services/label_reconstruction/candidates.py's
updated docstring for the root-cause evidence).

Reports, on the SAME legacy_external_test 6512 rows used throughout:
  - candidate recall (anywhere in top-25) -- retrieval quality
  - candidate count distribution (avg/median/p90/p95/max)
  - runtime (total + per-row)
  - recall by family / corruption type / severity
  - end-to-end Top-1/Top-3/MRR with C1 + untuned BASE_PARAMS re-ranking the
    NEW candidates (ranking efficiency = Top-1 / new candidate recall)

Run from `backend/`: python scripts/phase7_candidate_gen_ablation.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
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
    return {"n": b["n"], "candidate_recall": b["cand_present"] / n,
            "top1": b["top1"] / n, "top3": b["top3"] / n, "mrr": b["mrr_sum"] / n}


def main() -> int:
    train = np.load(OLD_EXPERIMENT_DIR / "train_full.npz")
    X_train, y_train, groups_train = train["X"].copy(), train["y"], train["groups"]
    X_train[:, MASKED_IDX] = 0.0

    print(f"training reference ranker: C1 + untuned BASE_PARAMS")
    model = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
    model.fit(X_train, y_train, group=groups_train)

    pointwise_rows = _load_jsonl(DATA_DIR / "pointwise.jsonl")
    test_rows = [r for r in pointwise_rows if r["split"] == "test"]
    print(f"test rows: {len(test_rows)}")

    database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    try:
        overall = _bucket()
        by_family = defaultdict(_bucket)
        by_corruption = defaultdict(_bucket)
        by_severity = defaultdict(_bucket)
        candidate_counts = []

        t0 = time.time()
        for row in test_rows:
            target = row["clean_designation"]
            corrupted = row["corrupted_text"]
            candidate_set = generate_candidates_v3(corrupted, limit=CANDIDATE_LIMIT)
            candidates = candidate_set.candidates
            candidate_counts.append(len(candidates))
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

            _update(overall, rank, cand_present)
            _update(by_family[row["family"]], rank, cand_present)
            tags = row["corruption_type"] or ["none"]
            sev = row["corruption_severity"]
            key = tags[0] if sev == 1 else f"multi_corruption_severity_{sev}"
            _update(by_corruption[key], rank, cand_present)
            _update(by_severity[sev], rank, cand_present)
        elapsed = time.time() - t0
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()

    m = _finalize(overall)
    counts = np.array(candidate_counts)
    print(f"\nruntime: {elapsed:.1f}s total, {elapsed/len(test_rows)*1000:.2f}ms/row")
    print(f"candidate count: avg={counts.mean():.2f} median={np.median(counts):.1f} "
          f"p90={np.percentile(counts,90):.1f} p95={np.percentile(counts,95):.1f} max={counts.max()}")
    print(f"\nNEW candidate recall: {m['candidate_recall']:.4f} (was 0.8409, 1036/6512 misses)")
    print(f"NEW end-to-end (C1+untuned reranking new candidates): top1={m['top1']:.4f} top3={m['top3']:.4f} mrr={m['mrr']:.4f}")
    print(f"NEW ranking efficiency = top1/candidate_recall = {m['top1']/m['candidate_recall']:.4f}")
    print(f"(reference: OLD candidate recall 0.8409, OLD end-to-end top1=0.7446, OLD ranking efficiency=0.8855)")

    results = {
        "runtime_s": elapsed, "ms_per_row": elapsed / len(test_rows) * 1000,
        "candidate_count": {"avg": float(counts.mean()), "median": float(np.median(counts)),
                             "p90": float(np.percentile(counts, 90)), "p95": float(np.percentile(counts, 95)),
                             "max": int(counts.max())},
        "overall": m,
        "by_family": {k: _finalize(v) for k, v in by_family.items()},
        "by_corruption": {k: _finalize(v) for k, v in by_corruption.items()},
        "by_severity": {str(k): _finalize(v) for k, v in by_severity.items()},
        "reference_old": {"candidate_recall": 0.8409, "top1": 0.7446, "top3": 0.8150, "mrr": 0.7814,
                           "ranking_efficiency": 0.8855, "misses": 1036},
    }
    (EXPERIMENT_DIR / "phase7_candidate_gen_ablation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nsaved to {EXPERIMENT_DIR / 'phase7_candidate_gen_ablation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
