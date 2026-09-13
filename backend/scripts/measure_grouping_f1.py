#!/usr/bin/env python3
"""Measure grouping F1 on A2 gold multi-fragment rows (Accuracy Track A3).

Does not invent dimensions. Writes a report under accuracy_reports/.
"""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_BACKEND = _Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import argparse
import json
from pathlib import Path

from services.annotation.fragment_grouper import group_annotation_fragments


def _bbox_for_index(i: int, rotation: float = 0.0):
    if 70.0 <= abs(rotation) % 180.0 <= 110.0:
        return [0.0, float(i * 18), 10.0, float(i * 18 + 12)]
    return [float(i * 18), 0.0, float(i * 18 + 14), 10.0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gold",
        default="training/eval_cache_backups/accuracy_gold/june_16page_extract_group_gold.json",
    )
    parser.add_argument(
        "--out",
        default="training/eval_cache_backups/accuracy_reports/a3_grouping_f1.json",
    )
    args = parser.parse_args()
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    rows = [r for r in gold.get("rows") or [] if len(r.get("fragments_gold") or []) > 1]

    tp = fp = fn = 0
    details = []
    for row in rows:
        frags = row["fragments_gold"]
        expected = "".join(str(t) for t in frags).upper().replace(" ", "")
        # Multi-fragment W seeds use a consistent ~90° reading axis so the
        # rotation gap tolerance is exercised without breaking rot_delta.
        rot = 90.0 if len(frags) >= 4 else 0.0
        fragments = [
            {
                "text": t,
                "page": 1,
                "bbox": _bbox_for_index(i, rotation=rot),
                "rotation": rot,
                "font_size": 10.0,
            }
            for i, t in enumerate(frags)
        ]
        groups = group_annotation_fragments(fragments)
        got = (groups[0].get("text") or "").upper().replace(" ", "") if groups else ""
        merged = len(groups) == 1 and bool(groups[0].get("was_merged"))
        if merged and got == expected:
            tp += 1
            status = "tp"
        elif merged and got != expected:
            fp += 1
            status = "fp_wrong_text"
        else:
            fn += 1
            status = "fn_not_merged"
        details.append(
            {
                "gold_id": row.get("gold_id"),
                "expected": expected,
                "got": got,
                "status": status,
            }
        )

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        (2 * precision * recall / (precision + recall))
        if (precision + recall)
        else 0.0
    )
    report = {
        "track": "A3",
        "multi_fragment_rows": len(rows),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "details": details,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("multi_fragment_rows", "f1", "precision", "recall")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
