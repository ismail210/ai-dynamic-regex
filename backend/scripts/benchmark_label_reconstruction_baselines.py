"""Benchmark baselines for damaged-AISC-label reconstruction (Part J).

Loads the frozen test split of the versioned label-reconstruction dataset
(``scripts/generate_label_corruption_dataset.py``) and scores each baseline
candidate ranker against it: recall@{1,3,5,10} / top-{1,3,5} accuracy / MRR,
broken down by corruption family and severity. In this single-correct-answer
setting, "recall@k" and "top-k accuracy" are the same quantity (the true
label is either in the top-k or it isn't) -- both are reported because the
spec (Part J) names both, not because they differ here.

Every row's rank is computed EXACTLY ONCE per baseline (a single pass over
the frozen test set); all breakdowns (by severity/family/corruption-type/
slice) are aggregated from that one cached pass rather than re-running the
ranker per breakdown group -- the first version of this script recomputed
full-catalog scans up to 9x per row and was consequently far too slow.

Baselines, weakest-assumption to strongest:

1. ``edit_distance``   -- full catalog scan, ranked by Levenshtein distance
                          to the normalized query (length-window pruned: a
                          candidate whose length differs from the query by
                          more than 6 characters cannot plausibly be the
                          answer for any of these corruption types, and
                          skipping the O(n*m) DP for those pairs is the
                          single biggest speedup available without changing
                          what gets ranked in the top 10).
2. ``char_ngram``      -- full catalog scan, ranked by bigram+trigram
                          Jaccard similarity (catalog n-gram sets
                          precomputed once, not per query).
3. ``fuzzy_lookup``    -- the EXISTING shipped production fallback,
                          ``services.database_loader.search_similar_shapes``
                          (SequenceMatcher ratio + family-prefix bonus).
                          This is the closest thing this repo has today to
                          an "existing ML candidate ranker" for this task --
                          there is no trained LightGBM/XGBoost ranker for
                          label reconstruction prior to this work, only this
                          heuristic string-similarity function.
4. ``deterministic``   -- the current production candidate generator,
                          ``services.label_reconstruction.candidates.generate_candidates``
                          (exact match -> wildcard mask -> OCR-flex ->
                          family-only -> fuzzy nearest-neighbor, unioned and
                          deduplicated in that priority order).
5. ``wildcard_only``   -- ``services.wildcard_matcher.match_wildcard_mask``
                          alone, evaluated ONLY on the subset of test rows
                          whose corrupted text contains a wildcard token.

Run from ``backend/``: ``python scripts/benchmark_label_reconstruction_baselines.py``
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.database_loader import catalog_entries, search_similar_shapes  # noqa: E402
from services.label_reconstruction.candidates import generate_candidates  # noqa: E402
from services.label_reconstruction.corruption import CORRUPTION_FAMILIES  # noqa: E402
from services.training_pipeline import dataset_registry  # noqa: E402
from services.wildcard_matcher import has_wildcards, match_wildcard_mask  # noqa: E402

RECALL_KS = (1, 3, 5, 10)
_CATALOG_LABELS: List[str] = sorted({label for label, _type in catalog_entries()})
_LENGTH_WINDOW = 6


def _corruption_family_of_tag(tag: str) -> str:
    if "_to_" in tag and len(tag.split("_to_")) == 2:
        return "ocr_substitution"
    prefix_map = {
        "char_deletion_trailing": "char_deletion",
        "char_deletion_interior": "char_deletion",
        "unknown_char_single": "unknown_char",
        "unknown_char_multi": "unknown_char",
        "separator_space": "separator",
        "separator_multiply_sign": "separator",
        "separator_dash": "separator",
        "separator_space_after": "separator",
        "added_prefix_letter": "added_noise",
        "added_suffix_letter": "added_noise",
        "added_parens": "added_noise",
        "missing_family_prefix": "missing_prefix",
        "family_only_partial": "missing_prefix",
    }
    return prefix_map.get(tag, tag)


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def _char_ngrams(text: str, n: int) -> frozenset:
    if len(text) < n:
        return frozenset({text}) if text else frozenset()
    return frozenset(text[i : i + n] for i in range(len(text) - n + 1))


# Precomputed once -- avoids recomputing catalog-label n-grams on every query.
_CATALOG_BIGRAMS = {label: _char_ngrams(label, 2) for label in _CATALOG_LABELS}
_CATALOG_TRIGRAMS = {label: _char_ngrams(label, 3) for label in _CATALOG_LABELS}
_CATALOG_BY_LENGTH: Dict[int, List[str]] = {}
for _label in _CATALOG_LABELS:
    _CATALOG_BY_LENGTH.setdefault(len(_label), []).append(_label)


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def rank_edit_distance(query: str, *, limit: int = 10) -> List[str]:
    pool = [
        label
        for length, labels in _CATALOG_BY_LENGTH.items()
        if abs(length - len(query)) <= _LENGTH_WINDOW
        for label in labels
    ]
    scored = sorted(pool, key=lambda label: (_edit_distance(query, label), label))
    return scored[:limit]


def rank_char_ngram(query: str, *, limit: int = 10) -> List[str]:
    q2, q3 = _char_ngrams(query, 2), _char_ngrams(query, 3)

    def _score(label: str) -> float:
        s2 = _jaccard(q2, _CATALOG_BIGRAMS[label])
        s3 = _jaccard(q3, _CATALOG_TRIGRAMS[label])
        return (s2 + s3) / 2

    scored = sorted(_CATALOG_LABELS, key=lambda label: (-_score(label), label))
    return scored[:limit]


def rank_fuzzy_lookup(query: str, *, limit: int = 10) -> List[str]:
    results = search_similar_shapes(query, limit=limit, minimum_score=0.0)
    return [item["shape"].upper().replace(" ", "") for item in results]


def rank_deterministic(query: str, *, limit: int = 10) -> List[str]:
    return generate_candidates(query, limit=limit).candidates


def rank_wildcard_only(query: str, *, limit: int = 10) -> List[str]:
    return [c.label for c in match_wildcard_mask(query, limit=limit)]


BASELINES = {
    "edit_distance": rank_edit_distance,
    "char_ngram": rank_char_ngram,
    "fuzzy_lookup": rank_fuzzy_lookup,
    "deterministic": rank_deterministic,
}


def _rank_of(target: str, ranked: Sequence[str]) -> Optional[int]:
    try:
        return ranked.index(target) + 1
    except ValueError:
        return None


def _score_all_rows(rows: List[dict], rank_fn) -> List[dict]:
    """One pass: compute (rank, reciprocal_rank, hit@k) per row, once."""

    scored = []
    for row in rows:
        ranked = rank_fn(row["raw_corrupted"], limit=max(RECALL_KS))
        rank = _rank_of(row["target_label"], ranked) if ranked else None
        scored.append({**row, "_rank": rank, "_rr": (1.0 / rank if rank else 0.0)})
    return scored


def _ndcg_at_k(rank: Optional[int], k: int) -> float:
    """Binary relevance, exactly one relevant item per query (the true
    label) -- IDCG is always 1/log2(2)=1, so NDCG@k reduces to
    1/log2(rank+1) when the true label is ranked within k, else 0."""

    import math

    if rank is None or rank > k:
        return 0.0
    return 1.0 / math.log2(rank + 1)


def _aggregate(scored_rows: List[dict]) -> Dict[str, float]:
    n = len(scored_rows)
    if n == 0:
        return {"n": 0}
    metrics = {"n": n, "mrr": round(sum(r["_rr"] for r in scored_rows) / n, 4)}
    for k in RECALL_KS:
        hits = sum(1 for r in scored_rows if r["_rank"] is not None and r["_rank"] <= k)
        metrics[f"recall_at_{k}"] = round(hits / n, 4)
        metrics[f"top_{k}_accuracy"] = metrics[f"recall_at_{k}"]
    for k in (5, 10):
        metrics[f"ndcg_at_{k}"] = round(
            sum(_ndcg_at_k(r["_rank"], k) for r in scored_rows) / n, 4
        )
    return metrics


def _breakdown(scored_rows: List[dict], key_fn) -> Dict[str, Dict[str, float]]:
    groups: Dict[str, List[dict]] = {}
    for row in scored_rows:
        groups.setdefault(key_fn(row), []).append(row)
    return {key: _aggregate(group_rows) for key, group_rows in sorted(groups.items())}


def load_test_rows(version_id: Optional[str] = None) -> List[dict]:
    samples = dataset_registry.load_dataset_samples("label_reconstruction", version_id)
    return [
        row
        for row in samples
        if row.get("row_kind") == "pointwise" and row.get("split") == "test"
    ]


def main() -> int:
    started = time.time()
    test_rows = load_test_rows()
    if not test_rows:
        print("No test rows found -- run generate_label_corruption_dataset.py first.")
        return 1
    print(f"Loaded {len(test_rows)} frozen test rows.", flush=True)

    results: Dict[str, dict] = {}
    for name, rank_fn in BASELINES.items():
        t0 = time.time()
        scored = _score_all_rows(test_rows, rank_fn)
        overall = _aggregate(scored)
        results[name] = {
            "overall": overall,
            "by_severity": _breakdown(scored, lambda r: f"severity_{r['severity']}"),
            "by_family": _breakdown(scored, lambda r: r["family"]),
            "by_corruption_family": _breakdown(
                scored,
                lambda r: _corruption_family_of_tag(r["corruption_types"][0])
                if r["corruption_types"]
                else "none",
            ),
            "unseen_combo_slice": _aggregate([r for r in scored if r.get("unseen_combo")]),
            "wildcard_slice": _aggregate([r for r in scored if has_wildcards(r["raw_corrupted"])]),
            "suffix_truncated_slice": _aggregate(
                [r for r in scored if "char_deletion_trailing" in r["corruption_types"]]
            ),
            "ocr_confusion_slice": _aggregate(
                [
                    r
                    for r in scored
                    if any(_corruption_family_of_tag(t) == "ocr_substitution" for t in r["corruption_types"])
                ]
            ),
            "runtime_seconds": round(time.time() - t0, 1),
        }
        print(f"[{name}] overall={overall} ({round(time.time() - t0, 1)}s)", flush=True)

    wildcard_rows = [r for r in test_rows if has_wildcards(r["raw_corrupted"])]
    if wildcard_rows:
        scored_wc = _score_all_rows(wildcard_rows, rank_wildcard_only)
        results["wildcard_only"] = {
            "overall": _aggregate(scored_wc),
            "n_rows_with_wildcards": len(wildcard_rows),
            "note": "Evaluated only on the wildcard-containing subset of test rows.",
        }
        print(f"[wildcard_only] overall={results['wildcard_only']['overall']}", flush=True)

    out_path = (
        Path(__file__).resolve().parents[1]
        / "training"
        / "datasets"
        / "label_reconstruction"
        / "baseline_results.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote results to {out_path}")
    print(f"Total runtime: {round(time.time() - started, 1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
