"""Evaluate a trained candidate ranker on the SAME frozen test benchmark
used for the baselines (Part K/L/9: identical data and metrics, no separate
test set for any trained model -- v2 and v3 are both scored here against
the exact same frozen rows).

The ranker only ever REORDERS its candidate generator's catalog-valid
candidate list -- it cannot introduce a label the deterministic system
didn't already propose. So the fair comparison is: the generator's own
ordering vs. the same candidate set re-ordered by the learned ranker's
scores.

Run from ``backend/``:
``python scripts/evaluate_label_ranker.py --version-id <id> --generator v2 --result-key learned_ranker``
``python scripts/evaluate_label_ranker.py --version-id <id> --generator v3 --result-key learned_ranker_v3``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.benchmark_label_reconstruction_baselines import (  # noqa: E402
    _aggregate,
    _breakdown,
    _corruption_family_of_tag,
    _score_all_rows,
    load_test_rows,
)
from services.label_reconstruction.candidates import (  # noqa: E402
    generate_candidates,
    generate_candidates_v3,
)
from services.label_reconstruction.ranker import load_ranker_version  # noqa: E402
from services.wildcard_matcher import has_wildcards  # noqa: E402

GENERATORS = {"v2": generate_candidates, "v3": generate_candidates_v3}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-id", required=True, help="registered label_reconstruction model version")
    parser.add_argument("--generator", choices=list(GENERATORS), default="v3")
    parser.add_argument("--result-key", default="learned_ranker_v3")
    args = parser.parse_args()

    ranker = load_ranker_version(args.version_id)
    if ranker is None:
        print(f"Model version {args.version_id!r} not found -- train one first.")
        return 1
    generate = GENERATORS[args.generator]

    test_rows = load_test_rows()
    print(f"Loaded {len(test_rows)} frozen test rows. Ranker version: {ranker.version_id} ({args.generator})")

    def rank_learned(query: str, *, limit: int = 10):
        candidate_set = generate(query, limit=25)
        if not candidate_set.candidates:
            return []
        ranked = ranker.rank(
            query,
            candidate_set.candidates,
            generation_reasons=candidate_set.generation_reasons,
            fuzzy_ranks=getattr(candidate_set, "fuzzy_ranks", None),
        )
        return ranked[:limit]

    scored = _score_all_rows(test_rows, rank_learned)
    overall = _aggregate(scored)
    result = {
        "model_version": ranker.version_id,
        "generator": args.generator,
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
    }
    print(json.dumps(result["overall"], indent=2))

    baseline_path = (
        Path(__file__).resolve().parents[1]
        / "training"
        / "datasets"
        / "label_reconstruction"
        / "baseline_results.json"
    )
    baselines = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    baselines[args.result_key] = result
    baseline_path.write_text(json.dumps(baselines, indent=2), encoding="utf-8")
    print(f"\nMerged into {baseline_path} under key {args.result_key!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
