"""
Honest baseline comparison against the AISC v16 all-editions catalog, using
the dataset built by generate_label_corruption_dataset_v16.py. NOT an
Optuna sweep -- one default-hyperparameter ranker (same architecture/params
as scripts/train_label_ranker_v3.py's BASE_PARAMS), evaluated alongside two
non-ML baselines, on the same held-out test rows.

Baselines:
  - deterministic: normalize the corrupted text, exact catalog lookup only.
  - string_similarity: generate_candidates_v3's candidate SET, re-ranked by
    plain SequenceMatcher ratio to the (normalized) query -- no ML.
  - ml_ranker_v3_default: generate_candidates_v3's candidate set, re-ranked
    by one XGBRanker (rank:pairwise, BASE_PARAMS, no tuning) trained fresh
    on this dataset's train split.

Metrics per baseline: candidate_recall (true label anywhere in the
generated candidate set -- a ceiling no re-ranking baseline can exceed),
top-1, top-3, MRR -- overall, by catalog_scope (modern vs historical),
by family, by corruption_type, and separately for the designation-holdout
slice (canonical designations never seen in training at all).

Run from `backend/`: python scripts/evaluate_v16_baselines.py
"""

from __future__ import annotations

import itertools
import json
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import xgboost as xgb
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
REPORTS_DIR = DATABASE_DIR / "reports"
OUT_REPORT = REPORTS_DIR / "aisc_v16_baseline_results.md"

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


def _load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def train_ranker(pairwise_rows: List[dict]) -> XGBRanker:
    train_rows = [r for r in pairwise_rows if r["split"] == "train"]
    X: List[List[float]] = []
    y: List[int] = []
    groups: List[int] = []
    for query, rows in itertools.groupby(train_rows, key=lambda r: r["query"]):
        rows = list(rows)
        if len(rows) < 2 or sum(r["target"] for r in rows) == 0:
            continue  # XGBRanker needs at least one positive per group
        # Same candidate-set call evaluation uses below, so `reason_*` /
        # `fuzzy_rank` carry real, varying values during training instead of
        # the previous constant/sentinel fill (train/serve skew fix).
        candidate_set = generate_candidates_v3(query, limit=CANDIDATE_LIMIT)
        groups.append(len(rows))
        for row in rows:
            features = features_from_candidate_set(row["candidate"], candidate_set)
            X.append([features[name] for name in FEATURE_NAMES])
            y.append(row["target"])

    model = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
    model.fit(np.array(X), np.array(y), group=np.array(groups))
    return model


def _rank_of(target: str, ordered_candidates: List[str]) -> Optional[int]:
    try:
        return ordered_candidates.index(target)
    except ValueError:
        return None


def _update_metric_bucket(bucket: dict, rank: Optional[int]) -> None:
    bucket["n"] += 1
    if rank is not None:
        bucket["top1"] += int(rank == 0)
        bucket["top3"] += int(rank < 3)
        bucket["mrr_sum"] += 1.0 / (rank + 1)


def _bucket() -> dict:
    return {"n": 0, "top1": 0, "top3": 0, "mrr_sum": 0.0}


def _finalize(bucket: dict) -> dict:
    n = bucket["n"] or 1
    return {
        "n": bucket["n"],
        "top1": bucket["top1"] / n,
        "top3": bucket["top3"] / n,
        "mrr": bucket["mrr_sum"] / n,
    }


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    pointwise_rows = _load_jsonl(DATA_DIR / "pointwise.jsonl")
    pairwise_rows = _load_jsonl(DATA_DIR / "pairwise.jsonl")
    test_rows = [r for r in pointwise_rows if r["split"] == "test"]

    catalog = database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    try:
        model = train_ranker(pairwise_rows)

        methods = ["deterministic", "string_similarity", "ml_ranker_v3_default"]
        overall = {m: _bucket() for m in methods}
        candidate_recall_bucket = _bucket()
        by_scope = {m: defaultdict(_bucket) for m in methods}
        by_family = {m: defaultdict(_bucket) for m in methods}
        by_corruption = {m: defaultdict(_bucket) for m in methods}
        by_holdout = {m: defaultdict(_bucket) for m in methods}
        recall_anywhere_present = 0

        for row in test_rows:
            target = row["clean_designation"]
            corrupted = row["corrupted_text"]
            family = row["family"]
            scope = row["catalog_scope"]
            holdout = "holdout" if row["designation_holdout"] else "seen_designation"
            corruption_tags = row["corruption_type"] or ["none"]

            candidate_set = generate_candidates_v3(corrupted, limit=CANDIDATE_LIMIT)
            candidates = candidate_set.candidates
            candidate_rank = _rank_of(target, candidates)
            _update_metric_bucket(candidate_recall_bucket, candidate_rank)
            if candidate_rank is not None:
                recall_anywhere_present += 1

            # --- deterministic: normalize + exact lookup only ---
            normalized = candidate_set.normalized
            det_rank = 0 if normalized == target else None

            # --- string_similarity: re-rank the SAME candidate set ---
            scored = sorted(
                candidates,
                key=lambda c: -SequenceMatcher(None, normalized, c).ratio(),
            )
            str_rank = _rank_of(target, scored)

            # --- ml_ranker_v3_default: re-rank the SAME candidate set ---
            if candidates:
                feat_matrix = np.array(
                    [
                        [
                            features_from_candidate_set(c, candidate_set)[name]
                            for name in FEATURE_NAMES
                        ]
                        for c in candidates
                    ]
                )
                scores = model.predict(feat_matrix)
                ml_ordered = [c for _s, c in sorted(zip(scores, candidates), key=lambda p: -p[0])]
            else:
                ml_ordered = []
            ml_rank = _rank_of(target, ml_ordered)

            ranks = {
                "deterministic": det_rank,
                "string_similarity": str_rank,
                "ml_ranker_v3_default": ml_rank,
            }
            severity = row["corruption_severity"]
            corruption_key = corruption_tags[0] if severity == 1 else f"multi_corruption_severity_{severity}"
            for method, rank in ranks.items():
                _update_metric_bucket(overall[method], rank)
                _update_metric_bucket(by_scope[method][scope], rank)
                _update_metric_bucket(by_family[method][family], rank)
                _update_metric_bucket(by_corruption[method][corruption_key], rank)
                _update_metric_bucket(by_holdout[method][holdout], rank)

        lines = []
        lines.append("# AISC v16 baseline results (honest, no Optuna)\n")
        lines.append(
            f"Test rows: {len(test_rows)}. Candidate generator: `generate_candidates_v3` "
            f"(limit={CANDIDATE_LIMIT}). ML baseline: one default-hyperparameter XGBRanker "
            f"(`rank:pairwise`, same params as `train_label_ranker_v3.py`'s `BASE_PARAMS`), "
            "trained fresh on this dataset's train split -- no Optuna, no promotion.\n"
        )
        candidate_recall = _finalize(candidate_recall_bucket)
        recall_anywhere = recall_anywhere_present / len(test_rows) if test_rows else 0.0
        lines.append(
            "\n**Candidate generator's own naive top-pick accuracy on this test "
            f"set: {candidate_recall['top1']:.4f}** (fraction of rows where the "
            "FIRST candidate `generate_candidates_v3` returns is already the "
            "true label -- NOT a ceiling on re-ranking: a re-ranker may still "
            "correctly promote a true label the generator listed lower down. "
            "Previously mislabeled here as a 'recall ceiling'; corrected after "
            "the fixed ranker's top-1 (see Overall below) measured higher than "
            "this figure, which is only possible if it was never really a "
            "ceiling.)\n"
        )
        lines.append(
            "\n**Actual candidate-set recall ceiling (true label present "
            f"ANYWHERE in the up-to-{CANDIDATE_LIMIT} candidate set) on this "
            f"test set: {recall_anywhere:.4f}** ({recall_anywhere_present}/"
            f"{len(test_rows)}) -- this is the real bound no re-ranking "
            "baseline below can exceed.\n"
        )

        lines.append("\n## Overall\n")
        lines.append("| Method | Top-1 | Top-3 | MRR | n |\n|---|---|---|---|---|\n")
        for method in methods:
            m = _finalize(overall[method])
            lines.append(f"| {method} | {m['top1']:.4f} | {m['top3']:.4f} | {m['mrr']:.4f} | {m['n']} |\n")

        lines.append("\n## By catalog scope (modern is the primary benchmark)\n")
        for scope in ("modern", "historical"):
            lines.append(f"\n### {scope}\n")
            lines.append("| Method | Top-1 | Top-3 | MRR | n |\n|---|---|---|---|---|\n")
            for method in methods:
                m = _finalize(by_scope[method].get(scope, _bucket()))
                lines.append(f"| {method} | {m['top1']:.4f} | {m['top3']:.4f} | {m['mrr']:.4f} | {m['n']} |\n")

        lines.append("\n## By designation holdout (unseen-designation generalization)\n")
        for slice_name in ("seen_designation", "holdout"):
            lines.append(f"\n### {slice_name}\n")
            lines.append("| Method | Top-1 | Top-3 | MRR | n |\n|---|---|---|---|---|\n")
            for method in methods:
                m = _finalize(by_holdout[method].get(slice_name, _bucket()))
                lines.append(f"| {method} | {m['top1']:.4f} | {m['top3']:.4f} | {m['mrr']:.4f} | {m['n']} |\n")

        lines.append("\n## By corruption type (ml_ranker_v3_default)\n")
        lines.append("| Corruption | Top-1 | Top-3 | MRR | n |\n|---|---|---|---|---|\n")
        for name, bucket in sorted(by_corruption["ml_ranker_v3_default"].items()):
            m = _finalize(bucket)
            lines.append(f"| {name} | {m['top1']:.4f} | {m['top3']:.4f} | {m['mrr']:.4f} | {m['n']} |\n")

        lines.append("\n## By family (ml_ranker_v3_default, modern families only)\n")
        modern_families = {
            e.family for e in catalog.entries() if e.catalog_scope == "modern"
        }
        lines.append("| Family | Top-1 | Top-3 | MRR | n |\n|---|---|---|---|---|\n")
        for family, bucket in sorted(
            by_family["ml_ranker_v3_default"].items(), key=lambda kv: -kv[1]["n"]
        ):
            if family not in modern_families:
                continue
            m = _finalize(bucket)
            lines.append(f"| {family} | {m['top1']:.4f} | {m['top3']:.4f} | {m['mrr']:.4f} | {m['n']} |\n")

        OUT_REPORT.write_text("".join(lines), encoding="utf-8")

        print(f"generator naive top-pick rate: {candidate_recall['top1']:.4f}")
        print(f"candidate-set recall (anywhere in top-{CANDIDATE_LIMIT}): {recall_anywhere:.4f}")
        for method in methods:
            m = _finalize(overall[method])
            print(f"{method}: top1={m['top1']:.4f} top3={m['top3']:.4f} mrr={m['mrr']:.4f} n={m['n']}")
        print(f"report: {OUT_REPORT}")
        return 0
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()


if __name__ == "__main__":
    raise SystemExit(main())
