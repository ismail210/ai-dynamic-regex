"""Paired statistical comparison between rankers on the frozen test set
(Part 9): is an observed accuracy difference real or noise?

For each pair of methods, reports:

* Paired counts: A-correct/B-wrong, B-correct/A-wrong, both-correct,
  both-wrong (a McNemar-style 2x2 table on top-1 correctness).
* McNemar's exact test p-value on the discordant pairs (the standard test
  for exactly this "two classifiers scored on the same items" situation --
  simpler and more appropriate here than a generic paired bootstrap, since
  top-1 correctness is a paired binary outcome, not a continuous metric).
* Paired bootstrap 95% CI on the top-1 accuracy difference (10,000
  resamples), as a second, distribution-free check that agrees or disagrees
  with McNemar's.

Run from ``backend/`` AFTER v3 is trained and registered:
``python scripts/paired_compare_rankers.py``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from scripts.benchmark_label_reconstruction_baselines import load_test_rows  # noqa: E402
from services.label_reconstruction.candidates import (  # noqa: E402
    generate_candidates,
    generate_candidates_v3,
)
from services.label_reconstruction.ranker import load_ranker_version  # noqa: E402

V2_RANKER_VERSION_ID = "label_reconstruction_20260807_130015"


def _rank_of(target: str, ranked: List[str]) -> int:
    try:
        return ranked.index(target) + 1
    except ValueError:
        return 0  # never correct at any k


def _top1_correct_vector(test_rows: Sequence[dict], rank_fn: Callable[[str], List[str]]) -> np.ndarray:
    out = []
    for row in test_rows:
        ranked = rank_fn(row["raw_corrupted"])
        out.append(1 if ranked and ranked[0] == row["target_label"] else 0)
    return np.array(out, dtype=np.int32)


def mcnemar_exact_p(b: int, c: int) -> float:
    """Exact two-sided McNemar test p-value from the binomial distribution
    on the discordant pair counts b, c (no continuity-correction chi-square
    approximation, which is unreliable when b+c is small)."""

    from math import comb

    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(comb(n, i) * (0.5**n) for i in range(0, k + 1))
    return min(1.0, 2 * p)


def paired_bootstrap_ci(a: np.ndarray, b: np.ndarray, *, n_boot: int = 10000, seed: int = 20260807):
    rng = np.random.default_rng(seed)
    n = len(a)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        diffs[i] = a[idx].mean() - b[idx].mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(diffs.mean()), float(lo), float(hi)


def compare(name_a: str, a: np.ndarray, name_b: str, b: np.ndarray) -> dict:
    both_correct = int(np.sum((a == 1) & (b == 1)))
    both_wrong = int(np.sum((a == 0) & (b == 0)))
    a_only = int(np.sum((a == 1) & (b == 0)))
    b_only = int(np.sum((a == 0) & (b == 1)))
    p = mcnemar_exact_p(a_only, b_only)
    mean_diff, lo, hi = paired_bootstrap_ci(a, b)
    result = {
        "a": name_a,
        "b": name_b,
        "a_acc": round(float(a.mean()), 4),
        "b_acc": round(float(b.mean()), 4),
        f"{name_a}_correct_{name_b}_wrong": a_only,
        f"{name_b}_correct_{name_a}_wrong": b_only,
        "both_correct": both_correct,
        "both_wrong": both_wrong,
        "mcnemar_exact_p": round(p, 4),
        "significant_at_0.05": p < 0.05,
        "bootstrap_mean_diff": round(mean_diff, 4),
        "bootstrap_95ci": [round(lo, 4), round(hi, 4)],
    }
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    test_rows = load_test_rows()
    print(f"Loaded {len(test_rows)} frozen test rows.")

    v2_ranker = load_ranker_version(V2_RANKER_VERSION_ID)
    v3_ranker = load_ranker_version(sys.argv[1]) if len(sys.argv) > 1 else None
    if v3_ranker is None:
        print("Pass the v3 model version_id as argv[1] (from train_label_ranker_v3.py's output).")
        return 1

    def det(query: str) -> List[str]:
        return generate_candidates(query, limit=25).candidates

    def det_v3(query: str) -> List[str]:
        return generate_candidates_v3(query, limit=25).candidates

    def learned_v2(query: str) -> List[str]:
        # Pass the RAW query, not cs.normalized -- both v2 and v3 were
        # trained with pairwise "query" = row["raw_corrupted"]
        # (generate_label_corruption_dataset.py / build_pairwise_dataset_v3.py),
        # i.e. pre-normalization text. Scoring with the normalized string
        # instead is a train/inference mismatch that silently changes
        # edit-distance/prefix/suffix features for any row where
        # normalization actually did something (whitespace, "×", "-X",
        # wrapping parens) -- exactly the failure mode Part D/9 asks this
        # analysis to catch, not commit.
        cs = generate_candidates(query, limit=25)
        if not cs.candidates:
            return []
        return v2_ranker.rank(query, cs.candidates, generation_reasons=cs.generation_reasons)

    def learned_v3(query: str) -> List[str]:
        cs = generate_candidates_v3(query, limit=25)
        if not cs.candidates:
            return []
        return v3_ranker.rank(
            query,
            cs.candidates,
            generation_reasons=cs.generation_reasons,
            fuzzy_ranks=cs.fuzzy_ranks,
        )

    vectors = {
        "deterministic": _top1_correct_vector(test_rows, det),
        "deterministic_v3_gen": _top1_correct_vector(test_rows, det_v3),
        "v2_learned": _top1_correct_vector(test_rows, learned_v2),
        "v3_learned": _top1_correct_vector(test_rows, learned_v3),
    }
    for name, vec in vectors.items():
        print(f"{name}: top1_acc={vec.mean():.4f}")

    print("\n=== v3_learned vs v2_learned ===")
    r1 = compare("v3_learned", vectors["v3_learned"], "v2_learned", vectors["v2_learned"])
    print("\n=== v3_learned vs deterministic ===")
    r2 = compare("v3_learned", vectors["v3_learned"], "deterministic", vectors["deterministic"])

    out_path = (
        Path(__file__).resolve().parents[1]
        / "training"
        / "datasets"
        / "label_reconstruction"
        / "paired_comparison_results.json"
    )
    out_path.write_text(
        json.dumps({"v3_vs_v2": r1, "v3_vs_deterministic": r2}, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
