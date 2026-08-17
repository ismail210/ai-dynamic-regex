"""
Phase 8: ONE-TIME final evaluation of the Optuna-tuned ranker on the
untouched test split. Trains the best trial's params on the full frozen-
feature TRAIN matrix (cached by phase1_feature_freeze.py), then scores the
test split via live generate_candidates_v3 calls (matching real serving),
with the same two rank features masked at inference that were masked at
training time -- consistency is the whole point of the earlier fix.

Also does Phase 10 error analysis: for every wrong prediction, splits into
"candidate generation failure" (true label never in the candidate set) vs
"ranker failure" (present but not ranked first), and buckets ranker
failures by corruption type / family.

Run from `backend/`: python scripts/phase8_final_test_eval.py
"""

from __future__ import annotations

import json
import sys
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
EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_optuna_20260816"
REPORTS_DIR = DATABASE_DIR / "reports"
OUT_REPORT = REPORTS_DIR / "aisc_v16_phase8_final_test_eval.md"

CANDIDATE_LIMIT = 25
SEED = 20260813


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
    study_params_path = EXPERIMENT_DIR / "all_trials.json"
    frozen = json.loads((EXPERIMENT_DIR / "frozen_feature_config.json").read_text(encoding="utf-8"))
    masked_features = frozen["masked_features"]
    masked_idx = [FEATURE_NAMES.index(name) for name in masked_features]

    trials = json.loads(study_params_path.read_text(encoding="utf-8"))
    best = max(trials, key=lambda t: t["value"])
    best_params = dict(best["params"])
    print(f"best trial #{best['number']}: val_top1={best['value']:.4f}")
    print(f"params: {best_params}")

    # Train on the FULL frozen-feature train matrix (cached, masked already
    # baked in from Phase 1 -- re-mask defensively in case this script is
    # ever pointed at an unmasked cache).
    train = np.load(EXPERIMENT_DIR / "train_full.npz")
    X_train, y_train, groups_train = train["X"].copy(), train["y"], train["groups"]
    X_train[:, masked_idx] = 0.0

    final_params = dict(
        tree_method="hist",
        random_state=SEED,
        **best_params,
    )
    model = XGBRanker(**final_params)
    model.fit(X_train, y_train, group=groups_train)

    pointwise_rows = _load_jsonl(DATA_DIR / "pointwise.jsonl")
    test_rows = [r for r in pointwise_rows if r["split"] == "test"]
    print(f"test rows: {len(test_rows)}")

    database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    try:
        overall = _bucket()
        by_scope = defaultdict(_bucket)
        by_holdout = defaultdict(_bucket)
        candidate_recall_bucket = _bucket()

        candidate_gen_failures = []  # true label never in candidate set
        ranker_failures = []  # present, but not ranked first
        ranker_failure_by_corruption = Counter()
        ranker_failure_by_family = Counter()

        for row in test_rows:
            target = row["clean_designation"]
            corrupted = row["corrupted_text"]
            scope = row["catalog_scope"]
            holdout = "holdout" if row["designation_holdout"] else "seen_designation"

            candidate_set = generate_candidates_v3(corrupted, limit=CANDIDATE_LIMIT)
            candidates = candidate_set.candidates
            candidate_rank = candidates.index(target) if target in candidates else None
            _update(candidate_recall_bucket, candidate_rank)

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
            _update(by_holdout[holdout], rank)

            if candidate_rank is None:
                candidate_gen_failures.append(row)
            elif rank != 0:
                ranker_failures.append(row)
                tags = row["corruption_type"] or ["none"]
                sev = row["corruption_severity"]
                key = tags[0] if sev == 1 else f"multi_corruption_severity_{sev}"
                ranker_failure_by_corruption[key] += 1
                ranker_failure_by_family[row["family"]] += 1

        m_overall = _finalize(overall)
        m_modern = _finalize(by_scope.get("modern", _bucket()))
        m_hist = _finalize(by_scope.get("historical", _bucket()))
        m_holdout = _finalize(by_holdout.get("holdout", _bucket()))
        m_seen = _finalize(by_holdout.get("seen_designation", _bucket()))

        n_candidate_gen_fail = len(candidate_gen_failures)
        n_ranker_fail = len(ranker_failures)
        recall_anywhere = 1.0 - (n_candidate_gen_fail / len(test_rows) if test_rows else 0.0)

        print(f"\nOverall: top1={m_overall['top1']:.4f} top3={m_overall['top3']:.4f} mrr={m_overall['mrr']:.4f} n={m_overall['n']}")
        print(f"Modern: top1={m_modern['top1']:.4f} top3={m_modern['top3']:.4f} mrr={m_modern['mrr']:.4f} n={m_modern['n']}")
        print(f"Historical: top1={m_hist['top1']:.4f} top3={m_hist['top3']:.4f} mrr={m_hist['mrr']:.4f} n={m_hist['n']}")
        print(f"Holdout: top1={m_holdout['top1']:.4f} top3={m_holdout['top3']:.4f} mrr={m_holdout['mrr']:.4f} n={m_holdout['n']}")
        print(f"Seen designation: top1={m_seen['top1']:.4f} top3={m_seen['top3']:.4f} mrr={m_seen['mrr']:.4f} n={m_seen['n']}")
        print(f"\nCandidate-set recall (anywhere in top-{CANDIDATE_LIMIT}): {recall_anywhere:.4f}")
        print(f"Candidate-generation failures (true label never in candidate set): {n_candidate_gen_fail} ({n_candidate_gen_fail/len(test_rows):.4f})")
        print(f"Ranker failures (present but not ranked first): {n_ranker_fail} ({n_ranker_fail/len(test_rows):.4f})")
        print("\nRanker failures by corruption type (top 10):")
        for k, v in ranker_failure_by_corruption.most_common(10):
            print(f"  {k}: {v}")
        print("\nRanker failures by family (top 10):")
        for k, v in ranker_failure_by_family.most_common(10):
            print(f"  {k}: {v}")

        results = {
            "best_trial": best["number"],
            "best_params": best_params,
            "overall": m_overall,
            "modern": m_modern,
            "historical": m_hist,
            "holdout": m_holdout,
            "seen_designation": m_seen,
            "candidate_gen_failures": n_candidate_gen_fail,
            "ranker_failures": n_ranker_fail,
            "recall_anywhere": recall_anywhere,
            "ranker_failure_by_corruption": dict(ranker_failure_by_corruption.most_common(15)),
            "ranker_failure_by_family": dict(ranker_failure_by_family.most_common(15)),
        }
        (EXPERIMENT_DIR / "phase8_test_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

        model.save_model(str(EXPERIMENT_DIR / "tuned_ranker.json"))
        print(f"\nsaved tuned model to {EXPERIMENT_DIR / 'tuned_ranker.json'}")
        print(f"saved results to {EXPERIMENT_DIR / 'phase8_test_results.json'}")
        return 0
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()


if __name__ == "__main__":
    raise SystemExit(main())
