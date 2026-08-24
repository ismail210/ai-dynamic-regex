#!/usr/bin/env python3
"""Bulk-reject unknown tokens that match layout/footing noise patterns."""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from services.engineering.feet_inch_filter import (  # noqa: E402
    is_feet_inch_layout_dimension,
    is_non_steel_layout_dimension,
)

COLUMNS = [
    "id",
    "token",
    "category",
    "prediction",
    "model_probability",
    "overall_confidence",
    "confidence_level",
    "uncertain",
    "source_file",
    "regex_suggested",
    "status",
    "reviewed_category",
    "reviewed_class",
    "notes",
    "created_at",
    "updated_at",
]


def is_layout_noise(token: str) -> bool:
    value = str(token or "").strip()
    if not value:
        return False
    return is_feet_inch_layout_dimension(value) or is_non_steel_layout_dimension(
        value
    )


def main() -> int:
    path = settings.unknown_tokens_path
    if not path.exists():
        print(f"Missing file: {path}")
        return 1

    now = datetime.now(timezone.utc).isoformat()
    changed = 0
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("status") == "pending" and is_layout_noise(row.get("token")):
                row["status"] = "rejected"
                row["notes"] = (
                    (row.get("notes") or "").strip()
                    + " auto-reject layout/footing noise"
                ).strip()
                row["updated_at"] = now
                changed += 1
            rows.append(row)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"rejected_pending_layout_tokens={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
