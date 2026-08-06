"""
Automatic Takeoff Excel generation.

Stable presentation-ready exporter:
  AI predictions (+ optional AISC metadata) → Excel workbook.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from config import settings
from services.database_loader import lookup_shape
from services.entity_taxonomy import classify_category
from services.prediction.contract import confidence_overall


def build_takeoff_rows(predictions: List[dict]) -> List[dict]:
    counts: Counter = Counter()
    meta: Dict[str, dict] = {}
    for result in predictions:
        label = str(
            result.get("section")
            or result.get("token")
            or ""
        ).upper().replace(" ", "")
        if not label:
            continue
        counts[label] += 1
        if label not in meta:
            aisc = lookup_shape(label)
            entity = classify_category(label)
            overall = confidence_overall(result.get("confidence"))
            meta[label] = {
                "Mark": label,
                "Family": result.get("family") or entity.class_name,
                "Section": label,
                "Shape": label,
                "Entity": entity.category_label,
                "AISC Type": (aisc or {}).get("type"),
                "Database Match": bool(result.get("database_match") or aisc),
                "AISC Confirmed": bool(result.get("database_match") or aisc),
                "Avg Confidence": overall,
                "Confidence Level": (
                    "High" if overall >= 0.80
                    else "Medium" if overall >= 0.55
                    else "Low"
                ),
            }
    rows = []
    for label, qty in counts.most_common():
        row = dict(meta[label])
        row["Quantity"] = qty
        rows.append(row)
    return rows


def generate_takeoff_excel(
    pdf_path: str | Path,
    *,
    destination: Optional[str | Path] = None,
    predictions: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """
    Generate a takeoff Excel from completed multimodal predictions.
    """

    pdf_path = Path(pdf_path)
    if predictions is None:
        raise ValueError(
            "Takeoff generation requires completed multimodal predictions"
        )

    rows = build_takeoff_rows(predictions)
    frame = pd.DataFrame(rows)
    out_dir = Path(destination).parent if destination else settings.takeoff_exports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(destination) if destination else out_dir / f"takeoff_{pdf_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    summary = pd.DataFrame(
        [
            {"Metric": "Source PDF", "Value": pdf_path.name},
            {"Metric": "Generated At", "Value": datetime.now(timezone.utc).isoformat()},
            {"Metric": "Unique Shapes", "Value": len(rows)},
            {"Metric": "Total Quantity", "Value": int(sum(r["Quantity"] for r in rows))},
            {"Metric": "Database Matches", "Value": int(sum(1 for r in rows if r.get("Database Match")))},
        ]
    )

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Takeoff", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)

    return {
        "export_path": str(out_path),
        "filename": out_path.name,
        "row_count": len(rows),
        "total_quantity": int(sum(r["Quantity"] for r in rows)),
        "rows": rows,
    }
