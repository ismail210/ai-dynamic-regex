#!/usr/bin/env python3
"""Repair candidate shadow metrics only (Accuracy Track A5).

ML_LABEL_RANKER_* stay false. Measures catalog candidate coverage on
seeded corrupted / incomplete strings without enabling production remaps.
"""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_BACKEND = _Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import argparse
import json
import os
from pathlib import Path


SHADOW_CASES = [
    {"id": "w8xi0", "raw": "W8XI0", "family": "W", "expect_candidates": True},
    {"id": "w16x2b", "raw": "W16X2B", "family": "W", "expect_candidates": True},
    {"id": "hss_ocr", "raw": "HS56X6X3/8", "family": "HSS", "expect_candidates": True},
    {"id": "l4x4_incomplete", "raw": "L4X4", "family": "L", "expect_candidates": True, "must_not_auto_complete": True},
    {"id": "l5x3_incomplete", "raw": "L5X3", "family": "L", "expect_candidates": True, "must_not_auto_complete": True},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="training/eval_cache_backups/accuracy_reports/a5_repair_shadow.json",
    )
    args = parser.parse_args()

    # Hard assert production enable flags remain off for this measurement.
    for key in ("ML_LABEL_RANKER_ENABLED", "ML_LABEL_RANKER_SHADOW"):
        if os.environ.get(key, "").lower() in {"1", "true", "yes"}:
            raise SystemExit(f"refusing to run with {key} enabled")

    from services.label_reconstruction.candidates import generate_candidates

    rows = []
    coverage = 0
    for case in SHADOW_CASES:
        cand_set = generate_candidates(case["raw"])
        labels = list(cand_set.candidates or [])[:15]
        has = bool(labels)
        if has:
            coverage += 1
        rows.append(
            {
                **case,
                "candidate_count": len(cand_set.candidates or []),
                "top_candidates": labels,
                "auto_selected": None,  # shadow only — never select
                "flags": {
                    "ml_label_ranker_enabled": False,
                    "ml_label_ranker_shadow": False,
                },
            }
        )

    report = {
        "track": "A5",
        "mode": "shadow_metrics_only",
        "cases": len(SHADOW_CASES),
        "candidate_coverage": coverage / len(SHADOW_CASES),
        "enable_flags_remain_false": True,
        "rows": rows,
        "risk_notes": [
            "Incomplete L/2L may still generate catalog candidates; production must abstain.",
            "No remap applied; auto_selected is always null.",
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("cases", "candidate_coverage", "enable_flags_remain_false")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
