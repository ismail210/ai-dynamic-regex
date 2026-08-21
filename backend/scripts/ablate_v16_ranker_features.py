"""
Feature-group ablation for the label ranker, against the AISC v16 dataset
(scripts/generate_label_corruption_dataset_v16.py output). Answers: which
feature groups actually help ranking, and do geometry/graph features help
(answer: they can't -- see note below).

Method: train the same default-hyperparameter XGBRanker as
evaluate_v16_baselines.py on the train split, once per condition -- "all
features" and "all features except group G" (that group's columns zeroed
out, so the model shape/training setup is identical and only the
information content changes) -- then compare validation-split group top-1
accuracy (does the highest-scored candidate in each (query, candidates)
group equal the true label) between conditions. A group whose removal
barely changes accuracy isn't pulling weight; a group whose removal hurts a
lot is.

Feature groups (from services.label_reconstruction.features.FEATURE_NAMES):
  length            query_len, candidate_len, len_diff_abs
  edit_distance     edit_distance(_norm), ocr_aware_distance(_norm)
  char_position     bigram/trigram_jaccard, common_prefix/suffix_len,
                     positional_match_count/ratio
  family            family_match, query_family_known,
                     candidate_family_size_log1p
  structural_dims   is_structurally_compatible, known_fields_matched/
                     violated, field{0,1,2}_diff_norm
  generation_prov   deterministic_rank, fuzzy_rank, reason_* one-hots

geometry_graph: NOT a group here -- confirmed via architecture audit that
zero geometry/graph/fusion features are wired into
services.label_reconstruction.features at all (services.multimodal's
geometry/graph/fusion machinery feeds a different, separate scoring path).
There is nothing to ablate; the honest answer to "are geometry/graph
features helping label ranking" is "they cannot be, because none exist in
this model" -- reported as a finding, not measured empirically.

Run from `backend/`: python scripts/ablate_v16_ranker_features.py
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

from services.label_reconstruction.candidates import generate_candidates_v3  # noqa: E402
from services.label_reconstruction.features import (  # noqa: E402
    FEATURE_NAMES,
    features_from_candidate_set,
)

DATA_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_v16"
REPORTS_DIR = BACKEND_DIR / "database" / "reports"
OUT_REPORT = REPORTS_DIR / "aisc_v16_feature_ablation.md"

CANDIDATE_LIMIT = 25  # matches scripts/evaluate_v16_baselines.py's generate_candidates_v3 limit
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

FEATURE_GROUPS: Dict[str, List[str]] = {
    "length": ["query_len", "candidate_len", "len_diff_abs"],
    "edit_distance": [
        "edit_distance", "edit_distance_norm", "ocr_aware_distance", "ocr_aware_distance_norm",
    ],
    "char_position": [
        "bigram_jaccard", "trigram_jaccard", "common_prefix_len", "common_suffix_len",
        "positional_match_count", "positional_match_ratio",
    ],
    "family": ["family_match", "query_family_known", "candidate_family_size_log1p"],
    "structural_dims": [
        "is_structurally_compatible", "known_fields_matched", "known_fields_violated",
        "field0_diff_norm", "field1_diff_norm", "field2_diff_norm",
    ],
    "generation_provenance": [
        "deterministic_rank", "fuzzy_rank",
        "reason_exact_match", "reason_structural_field_match", "reason_wildcard_mask",
        "reason_ocr_flex_positional", "reason_family_only", "reason_fuzzy_nearest_neighbor",
    ],
}


def _load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _grouped(rows: List[dict]):
    for _query, group in itertools.groupby(rows, key=lambda r: r["query"]):
        group = list(group)
        if len(group) >= 2 and sum(r["target"] for r in group) > 0:
            yield group


def build_matrix(rows: List[dict]):
    X, y, groups = [], [], []
    for group in _grouped(rows):
        # Same candidate-set call the real evaluation path uses, so
        # `reason_*`/`fuzzy_rank` vary meaningfully here instead of the
        # previous constant/sentinel fill (train/serve skew fix -- see
        # services.label_reconstruction.features.features_from_candidate_set).
        candidate_set = generate_candidates_v3(group[0]["query"], limit=CANDIDATE_LIMIT)
        groups.append(len(group))
        for row in group:
            features = features_from_candidate_set(row["candidate"], candidate_set)
            X.append([features[name] for name in FEATURE_NAMES])
            y.append(row["target"])
    return np.array(X, dtype=float), np.array(y), np.array(groups)


def zero_out(X: np.ndarray, feature_names: List[str], group: List[str]) -> np.ndarray:
    masked = X.copy()
    for name in group:
        idx = feature_names.index(name)
        masked[:, idx] = 0.0
    return masked


def group_top1_accuracy(model: XGBRanker, X_val: np.ndarray, y_val: np.ndarray, groups_val: np.ndarray) -> float:
    scores = model.predict(X_val)
    correct = 0
    total = 0
    offset = 0
    for size in groups_val:
        group_scores = scores[offset : offset + size]
        group_targets = y_val[offset : offset + size]
        offset += size
        top = int(np.argmax(group_scores))
        correct += int(group_targets[top] == 1)
        total += 1
    return correct / total if total else 0.0


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    pairwise_rows = _load_jsonl(DATA_DIR / "pairwise.jsonl")
    train_rows = [r for r in pairwise_rows if r["split"] == "train"]
    val_rows = [r for r in pairwise_rows if r["split"] == "validation"]

    X_train, y_train, groups_train = build_matrix(train_rows)
    X_val, y_val, groups_val = build_matrix(val_rows)

    results: Dict[str, float] = {}

    model_full = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
    model_full.fit(X_train, y_train, group=groups_train)
    results["all_features"] = group_top1_accuracy(model_full, X_val, y_val, groups_val)

    for group_name, group_features in FEATURE_GROUPS.items():
        X_train_masked = zero_out(X_train, FEATURE_NAMES, group_features)
        X_val_masked = zero_out(X_val, FEATURE_NAMES, group_features)
        model = XGBRanker(objective="rank:pairwise", **BASE_PARAMS)
        model.fit(X_train_masked, y_train, group=groups_train)
        results[f"without_{group_name}"] = group_top1_accuracy(model, X_val_masked, y_val, groups_val)

    lines = []
    lines.append("# AISC v16 ranker feature-group ablation\n")
    lines.append(
        f"Train groups: {len(groups_train)}, validation groups: {len(groups_val)}. "
        "Metric: group top-1 accuracy (highest-scored candidate in each "
        "(query, candidate-set) group is the true label). Each `without_X` "
        "row zeroes group X's columns in both train and validation matrices "
        "and retrains from scratch -- same architecture/hyperparameters as "
        "the `all_features` row, only the information changes.\n"
    )
    lines.append("\n| Condition | Group top-1 accuracy | Delta vs all_features |\n|---|---|---|\n")
    baseline = results["all_features"]
    lines.append(f"| all_features | {baseline:.4f} | -- |\n")
    for group_name in FEATURE_GROUPS:
        acc = results[f"without_{group_name}"]
        lines.append(f"| without_{group_name} | {acc:.4f} | {acc - baseline:+.4f} |\n")

    lines.append(
        "\n## Geometry/graph features\n"
        "Not included above: an architecture audit of "
        "`services/label_reconstruction/features.py` and `ranker.py` found "
        "**zero** geometry/graph/fusion features wired into the label "
        "ranker at all (`services.multimodal`'s geometry/graph/fusion "
        "machinery feeds a separate scoring path, not this one). There is "
        "nothing to ablate here -- the honest answer to \"are geometry/graph "
        "features helping label ranking\" is that they cannot be, because "
        "none currently exist in this model.\n"
    )

    OUT_REPORT.write_text("".join(lines), encoding="utf-8")
    print(f"all_features: {baseline:.4f}")
    for group_name in FEATURE_GROUPS:
        acc = results[f"without_{group_name}"]
        print(f"without_{group_name}: {acc:.4f} (delta {acc - baseline:+.4f})")
    print(f"report: {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
