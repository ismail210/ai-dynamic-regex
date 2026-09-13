"""Promotion-gate evaluation for the schema-v5 broadened-fallback ranker
(scripts/train_label_ranker_v4_broadened.py's output).

Compares THREE candidate orderings on the broadened (deletion/insertion)
validation+test rows:
  A. SequenceMatcher.ratio() baseline (what repair_shadow.py used before)
  B. the currently-ACTIVE promoted ranker (schema v4, is_fallback_broadened
     unknown to it -- scores using only its own, older feature set)
  C. the new candidate ranker (schema v5)

...and regression-checks standard (non-broadened) corruption classes old vs
new on the frozen standard dataset's validation+test rows.

Run from ``backend/``: ``python scripts/evaluate_broadened_ranker.py``
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.label_reconstruction.candidates import (  # noqa: E402
    conservative_normalize,
    is_broadened_fallback_query,
)
from services.label_reconstruction.ranker import LabelRanker, load_ranker_version  # noqa: E402
from services.training_pipeline import model_registry  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
STANDARD_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_production_aligned"
BROADENED_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_broadened"


def _load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _group_by_query(rows: List[dict]) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["query"]].append(row)
    return grouped


def _rank_metrics(ordered_labels: List[str], target: str) -> Tuple[int, int, float]:
    """Returns (top1_hit, top3_hit, reciprocal_rank) -- 0 reciprocal rank if
    target absent from the ordering entirely."""
    if target not in ordered_labels:
        return 0, 0, 0.0
    rank = ordered_labels.index(target) + 1
    return int(rank == 1), int(rank <= 3), 1.0 / rank


def _baseline_order(query: str, candidates: List[str]) -> List[str]:
    normalized = conservative_normalize(query)
    scored = sorted(candidates, key=lambda c: -SequenceMatcher(None, normalized, c).ratio())
    return scored


def _ranker_order(ranker: LabelRanker, query: str, candidates: List[str], *, is_fallback_broadened: bool) -> List[str]:
    scores = ranker.score(query, candidates, is_fallback_broadened=is_fallback_broadened)
    return [label for label, _s in sorted(zip(candidates, scores), key=lambda p: -p[1])]


def _corruption_bucket(corruption_type: List[str]) -> str:
    tags = set(corruption_type or [])
    has_deletion = any(t.startswith("char_deletion") for t in tags)
    has_insertion = any(t.startswith("char_insertion") for t in tags)
    if has_deletion and has_insertion:
        return "multi_error"
    if has_deletion:
        return "deletion"
    if has_insertion:
        return "insertion"
    return "multi_error" if len(tags) > 1 else "other"


def evaluate_broadened(old_ranker: LabelRanker, new_ranker: LabelRanker) -> dict:
    rows = _load_jsonl(BROADENED_DIR / "pairwise.jsonl")
    eval_rows = [r for r in rows if r["split"] in ("validation", "test")]
    grouped = _group_by_query(eval_rows)

    buckets = defaultdict(lambda: defaultdict(lambda: {"n": 0, "top1": 0, "top3": 0, "mrr_sum": 0.0}))
    for query, group_rows in grouped.items():
        candidates = [r["candidate"] for r in group_rows]
        target_rows = [r for r in group_rows if r["target"] == 1]
        if not target_rows:
            continue
        target = target_rows[0]["candidate"]
        bucket = _corruption_bucket(group_rows[0].get("corruption_type"))

        for method, order in (
            ("sequence_matcher_baseline", _baseline_order(query, candidates)),
            ("old_promoted_ranker", _ranker_order(old_ranker, query, candidates, is_fallback_broadened=False)),
            ("new_broadened_ranker", _ranker_order(new_ranker, query, candidates, is_fallback_broadened=True)),
        ):
            top1, top3, rr = _rank_metrics(order, target)
            stat = buckets[bucket][method]
            stat["n"] += 1
            stat["top1"] += top1
            stat["top3"] += top3
            stat["mrr_sum"] += rr

    result = {}
    for bucket, methods in buckets.items():
        result[bucket] = {}
        for method, stat in methods.items():
            n = stat["n"] or 1
            result[bucket][method] = {
                "n": stat["n"],
                "top1": round(stat["top1"] / n, 4),
                "top3": round(stat["top3"] / n, 4),
                "mrr": round(stat["mrr_sum"] / n, 4),
            }
    return result


def evaluate_standard_regression(old_ranker: LabelRanker, new_ranker: LabelRanker) -> dict:
    """Old vs new on the FROZEN standard dataset's non-broadened rows,
    bucketed by single OCR-substitution corruption tag (1<->I, 0<->O, etc.)
    -- the classes the brief explicitly asks not to regress."""
    rows = _load_jsonl(STANDARD_DIR / "pairwise.jsonl")
    eval_rows = [r for r in rows if r["split"] in ("validation", "test")]
    grouped = _group_by_query(eval_rows)

    buckets = defaultdict(lambda: defaultdict(lambda: {"n": 0, "top1": 0, "mrr_sum": 0.0}))
    for query, group_rows in grouped.items():
        tags = group_rows[0].get("corruption_type") or []
        if len(tags) != 1 or not any(tag for tag in tags if "_to_" in tag):
            continue  # only single-tag OCR-substitution groups for this check
        bucket = tags[0]
        candidates = [r["candidate"] for r in group_rows]
        target_rows = [r for r in group_rows if r["target"] == 1]
        if not target_rows:
            continue
        target = target_rows[0]["candidate"]

        for method, order in (
            ("old_promoted_ranker", _ranker_order(old_ranker, query, candidates, is_fallback_broadened=False)),
            ("new_broadened_ranker", _ranker_order(new_ranker, query, candidates, is_fallback_broadened=False)),
        ):
            top1, _top3, rr = _rank_metrics(order, target)
            stat = buckets[bucket][method]
            stat["n"] += 1
            stat["top1"] += top1
            stat["mrr_sum"] += rr

    result = {}
    for bucket, methods in sorted(buckets.items()):
        if sum(m["n"] for m in methods.values()) < 10:
            continue  # too few examples for a meaningful per-tag comparison
        result[bucket] = {
            method: {"n": stat["n"], "top1": round(stat["top1"] / max(stat["n"], 1), 4), "mrr": round(stat["mrr_sum"] / max(stat["n"], 1), 4)}
            for method, stat in methods.items()
        }
    return result


def safety_checks() -> dict:
    checks = {
        "L4X4_not_broadened": not is_broadened_fallback_query("L4X4"),
        "2L4X4_not_broadened": not is_broadened_fallback_query("2L4X4"),
        "HSS8X8_not_broadened_missing_thickness": not is_broadened_fallback_query("HSS8X8"),
        "HSS5.563X0.258_not_broadened_round_hss_exact": not is_broadened_fallback_query("HSS5.563X0.258"),
        "W10X3_deletion_is_broadened": is_broadened_fallback_query("W10X3"),
        # A digit-duplication insertion (W12X26 -> W122X26) preserves the
        # depth_weight regex shape, so it IS a broadening trigger; an
        # X-duplication insertion (W18X40 -> W18XX40) breaks that regex
        # entirely and is already handled by the standard generator's own
        # built-in fuzzy inclusion -- confirmed empirically, not assumed.
        "W122X26_digit_insertion_is_broadened": is_broadened_fallback_query("W122X26"),
        "W18XX40_separator_insertion_handled_by_standard_path": not is_broadened_fallback_query("W18XX40"),
    }
    return checks


def feature_importance(new_version_id: str) -> dict:
    import xgboost as xgb

    entry = next(
        v for v in model_registry.list_model_versions("label_reconstruction", limit=100)["versions"]
        if v["version_id"] == new_version_id
    )
    booster = xgb.Booster()
    booster.load_model(entry["artifacts"]["booster"])
    gain = booster.get_score(importance_type="gain")
    return dict(sorted(gain.items(), key=lambda kv: -kv[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-version", required=True, help="version_id of the candidate model to evaluate")
    parser.add_argument("--old-version", default=None, help="version_id of the model to compare against (default: currently active)")
    args = parser.parse_args()

    if args.old_version:
        old_ranker = load_ranker_version(args.old_version)
    else:
        from services.label_reconstruction.ranker import get_active_ranker
        old_ranker = get_active_ranker()
    new_ranker = load_ranker_version(args.new_version)

    if old_ranker is None or new_ranker is None:
        print(f"Could not load rankers (old={old_ranker}, new={new_ranker})")
        return 1

    print(f"OLD ranker: {old_ranker.version_id} (schema features: {len(old_ranker.feature_names)}, supports_broadened={old_ranker.supports_broadened_fallback})")
    print(f"NEW ranker: {new_ranker.version_id} (schema features: {len(new_ranker.feature_names)}, supports_broadened={new_ranker.supports_broadened_fallback})")

    broadened_results = evaluate_broadened(old_ranker, new_ranker)
    print("\n=== BROADENED (deletion/insertion/multi_error) ===")
    print(json.dumps(broadened_results, indent=2))

    standard_results = evaluate_standard_regression(old_ranker, new_ranker)
    print("\n=== STANDARD REGRESSION (single OCR-substitution tags) ===")
    print(json.dumps(standard_results, indent=2))

    safety = safety_checks()
    print("\n=== SAFETY CHECKS ===")
    print(json.dumps(safety, indent=2))
    all_safe = all(safety.values())
    print(f"ALL SAFETY CHECKS PASS: {all_safe}")

    importance = feature_importance(args.new_version)
    print("\n=== FEATURE IMPORTANCE (gain), new model ===")
    print(json.dumps(importance, indent=2))

    out = {
        "old_version": old_ranker.version_id,
        "new_version": new_ranker.version_id,
        "broadened": broadened_results,
        "standard_regression": standard_results,
        "safety_checks": safety,
        "all_safety_checks_pass": all_safe,
        "feature_importance_gain": importance,
    }
    out_path = BACKEND_DIR / "training" / "label_reconstruction_tmp" / "broadened_ranker_eval.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
