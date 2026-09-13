#!/usr/bin/env python3
"""False-correction audit for deterministic canonicalize (Accuracy Track A4)."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_BACKEND = _Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import argparse
import json
from pathlib import Path

from services.prediction.section_canonicalize import (
    canonicalize_section_text,
    is_format_only_change,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gold",
        default="training/eval_cache_backups/accuracy_gold/june_16page_extract_group_gold.json",
    )
    parser.add_argument(
        "--out",
        default="training/eval_cache_backups/accuracy_reports/a4_normalize_audit.json",
    )
    args = parser.parse_args()
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))

    false_corrections = []
    format_only = 0
    incomplete_preserved = 0
    for row in gold.get("rows") or []:
        raw = str(row.get("raw_text") or "")
        canon = canonicalize_section_text(raw)
        op = row.get("intended_operation")
        gold_label = str(row.get("canonical_label_or_abstain") or "")
        if op == "abstain_incomplete":
            if canon.upper().replace(" ", "").count("X") >= 2:
                false_corrections.append(
                    {
                        "gold_id": row.get("gold_id"),
                        "raw": raw,
                        "canon": canon,
                        "reason": "invented_thickness_on_incomplete",
                    }
                )
            else:
                incomplete_preserved += 1
            continue
        if is_format_only_change(raw, canon):
            format_only += 1
        # Field-count increase vs gold abstain/complete is a false correction.
        if gold_label == "ABSTAIN_MISSING_THICKNESS":
            continue
        if raw and canon and raw.upper().replace(" ", "").count("X") < canon.upper().replace(" ", "").count("X"):
            false_corrections.append(
                {
                    "gold_id": row.get("gold_id"),
                    "raw": raw,
                    "canon": canon,
                    "reason": "added_dimension_field",
                }
            )

    report = {
        "track": "A4",
        "rows": gold.get("count"),
        "format_only_changes": format_only,
        "incomplete_preserved": incomplete_preserved,
        "false_correction_count": len(false_corrections),
        "false_corrections": false_corrections,
        "gate_pass": len(false_corrections) == 0,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("false_correction_count", "incomplete_preserved", "gate_pass")}, indent=2))
    return 0 if report["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
