"""
Automatic Takeoff Excel generation.

Stable presentation-ready exporter:
  AI predictions (+ optional AISC metadata) → Excel workbook.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config import settings
from services.database_loader import catalog_form, lookup_shape
from services.engineering.repeated_detail_linker import is_repeated_detail_member
from services.entity_taxonomy import classify_category
from services.prediction.contract import confidence_overall
from services.takeoff.quantity_engine import (
    LABELED_PREDICTION_SOURCES,
    QuantityReport,
    normalized_section,
    quantity_engine,
)

_TRUSTED_REPRESENTATIVE_MATCH = frozenset(
    {
        "exact_match",
        "normalized_match",
        "project_rule_resolved",
        "human_resolved",
    }
)


def _representative_rank(
    prediction: Dict[str, Any], label: str
) -> Tuple[int, int, int, int, float]:
    """Rank metadata candidates for one normalized section.

    Quantity is owned by QuantityEngine; this only chooses which prediction
    supplies display fields such as Family.
    """

    aisc = lookup_shape(label) or {}
    catalog_family = str(aisc.get("type") or "").strip().upper()
    predicted_family = str(prediction.get("family") or "").strip().upper()
    family_agrees = int(bool(catalog_family) and predicted_family == catalog_family)

    match_status = str(
        (prediction.get("comparison") or {}).get("match_status") or ""
    ).lower()
    trusted_match = int(match_status in _TRUSTED_REPRESENTATIVE_MATCH)

    source = str(
        prediction.get("original_token")
        or prediction.get("raw_text")
        or prediction.get("corrected_token")
        or ""
    )
    source_form = str(catalog_form(source) or "").strip().upper()
    source_agrees = int(bool(source_form) and source_form == label.upper())

    eligible = int(prediction.get("takeoff_eligible", True) is not False)
    confidence = confidence_overall(prediction.get("confidence"))
    return (eligible, family_agrees, trusted_match, source_agrees, confidence)


def _select_representative(
    current: Optional[Dict[str, Any]],
    challenger: Dict[str, Any],
    label: str,
) -> Dict[str, Any]:
    if current is None:
        return challenger
    if _representative_rank(challenger, label) > _representative_rank(current, label):
        return challenger
    return current


def build_takeoff_rows(
    predictions: List[dict],
    *,
    quantity_report: Optional[QuantityReport] = None,
) -> List[dict]:
    """Build export rows from conservative labeled-candidate quantities."""

    report = quantity_report or quantity_engine.count(predictions)
    candidates: Dict[str, dict] = {}
    for prediction in predictions:
        source = str(prediction.get("prediction_source") or "").upper()
        if source not in LABELED_PREDICTION_SOURCES:
            continue
        if is_repeated_detail_member(prediction):
            continue
        label = normalized_section(prediction)
        if not label:
            continue
        candidates[label] = _select_representative(
            candidates.get(label), prediction, label
        )

    rows = []
    positive_results = sorted(
        (
            result
            for result in report.results
            if result.section and result.physical_quantity > 0
        ),
        key=lambda result: (-result.physical_quantity, result.section),
    )
    for result in positive_results:
        label = result.section
        prediction = candidates.get(label) or {}
        aisc = lookup_shape(label)
        entity = classify_category(label)
        overall = result.confidence
        catalog_family = (aisc or {}).get("type")
        rows.append(
            {
                "Mark": label,
                "Family": prediction.get("family")
                or catalog_family
                or entity.class_name,
                "Section": label,
                "Shape": label,
                "Entity": entity.category_label,
                "AISC Type": catalog_family,
                "Database Match": bool(
                    prediction.get("database_match") or aisc
                ),
                "AISC Confirmed": bool(
                    prediction.get("database_match") or aisc
                ),
                "Avg Confidence": overall,
                "Confidence Level": (
                    "High"
                    if overall >= 0.80
                    else "Medium"
                    if overall >= 0.55
                    else "Low"
                ),
                "Quantity": result.physical_quantity,
                "Quantity Method": result.method,
            }
        )
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

    quantity_report = quantity_engine.count(predictions)
    rows = build_takeoff_rows(
        predictions, quantity_report=quantity_report
    )
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
        "quantity_engine": quantity_report.to_dict(),
    }
