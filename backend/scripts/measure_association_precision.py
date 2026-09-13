#!/usr/bin/env python3
"""Measure association precision against A7 gold links (Accuracy Track A7)."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_BACKEND = _Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gold",
        default="training/eval_cache_backups/accuracy_gold/june_association_gold.json",
    )
    parser.add_argument(
        "--out",
        default="training/eval_cache_backups/accuracy_reports/a7_association_precision.json",
    )
    args = parser.parse_args()
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    links = gold.get("links") or []

    reviewed = [L for L in links if L.get("human_verified")]
    # Until humans label CORRECT/WRONG, report system presence metrics only.
    with_system = [
        L
        for L in links
        if L.get("system_geometry_id") or L.get("system_association_method")
    ]
    provisional_correct = [
        L for L in reviewed if str(L.get("human_label") or "").upper() == "CORRECT"
    ]
    provisional_wrong = [
        L for L in reviewed if str(L.get("human_label") or "").upper() == "WRONG"
    ]
    precision = (
        len(provisional_correct) / (len(provisional_correct) + len(provisional_wrong))
        if (provisional_correct or provisional_wrong)
        else None
    )

    report = {
        "track": "A7",
        "link_count": len(links),
        "human_verified_count": len(reviewed),
        "system_associated_count": len(with_system),
        "system_association_rate": (len(with_system) / len(links)) if links else 0.0,
        "precision_on_reviewed": precision,
        "gate_note": (
            "Precision is null until human_label CORRECT/WRONG reviews land; "
            "do not raise dense-page geometry cap as the primary fix."
        ),
        "methods": sorted(
            {
                str(L.get("system_association_method") or "unknown")
                for L in with_system
            }
        ),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
