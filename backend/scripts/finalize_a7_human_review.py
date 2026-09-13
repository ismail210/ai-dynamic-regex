#!/usr/bin/env python3
"""Finalize A7 human-review metrics (validation only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "validation_reports" / "human_review"))

from hr_lib import (  # noqa: E402
    A2_REVIEW,
    A7_GOLD,
    A7_REVIEW,
    REPORT_DIR,
    compute_a2_metrics,
    compute_a7_metrics,
    load_json,
    render_combined_report,
    save_json,
    sha256_file,
    validate_a7_review_doc,
)


def main() -> int:
    gold = load_json(A7_GOLD)
    review = load_json(A7_REVIEW)
    errors = validate_a7_review_doc(review, gold=gold)
    stored = review.get("source_gold_sha256")
    current = sha256_file(A7_GOLD)
    if stored and stored != current:
        errors.append("source_gold_sha256_mismatch_original_modified")
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1
    metrics = compute_a7_metrics(review)
    out = REPORT_DIR / "a7_finalize_metrics.json"
    save_json(out, {"ok": True, "metrics": metrics, "source": str(A7_REVIEW)})
    a2 = compute_a2_metrics(load_json(A2_REVIEW))
    (REPORT_DIR / "A2_A7_HUMAN_REVIEW_REPORT.md").write_text(
        render_combined_report(a2, metrics), encoding="utf-8"
    )
    print(json.dumps({"ok": True, "metrics": metrics, "wrote": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
