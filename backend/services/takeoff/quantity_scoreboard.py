"""Offline quantity scoreboard vs Excel, separate from section precision.

Section recognition (unique eligible designations) stays on the Excel
evaluator. This module only compares QuantityEngine labeled-callout counts
to frozen member schedule rows. It never changes QuantityEngine counts,
Fusion, or Excel parsing.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Union

from services.database_loader import catalog_form
from services.takeoff.ground_truth_evaluation import _aggregate_ground_truth
from services.takeoff.quantity_engine import QuantityReport, QuantityResult


def _section_key(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return str(catalog_form(raw) or raw.upper().replace(" ", "").replace("-", "").replace("×", "X"))


def _predicted_from_report(
    report: Union[QuantityReport, Dict[str, Any], None],
) -> Dict[str, Dict[str, Any]]:
    if report is None:
        return {}
    results: Iterable[Any]
    if isinstance(report, QuantityReport):
        results = report.results
    else:
        results = report.get("results") or []

    predicted: Dict[str, Dict[str, Any]] = {}
    for result in results:
        if isinstance(result, QuantityResult):
            section = _section_key(result.section)
            quantity = int(result.physical_quantity or 0)
            method = result.method
        else:
            section = _section_key(result.get("section"))
            quantity = int(result.get("physical_quantity") or 0)
            method = result.get("method")
        if not section:
            continue
        predicted[section] = {
            "section": section,
            "predicted_quantity": quantity,
            "method": method,
        }
    return predicted


def build_quantity_scoreboard(
    report: Union[QuantityReport, Dict[str, Any], None],
    ground_truth: Optional[dict],
) -> Optional[Dict[str, Any]]:
    """Compare QuantityEngine output to Excel member schedule rows.

    Returns ``None`` when there is no Excel ground truth. Missing and extra
    sections are included in MAE / bias so undercount is visible. This is
    not section precision and not true physical quantity.
    """

    if not ground_truth:
        return None

    predicted = _predicted_from_report(report)
    expected_buckets = _aggregate_ground_truth(ground_truth)
    expected = {
        _section_key(section): int(bucket.get("quantity") or 0)
        for section, bucket in expected_buckets.items()
        if _section_key(section)
    }

    labels = sorted(set(predicted) | set(expected))
    rows: List[dict] = []
    absolute_error = 0
    signed_error = 0
    undercount = 0
    overcount = 0
    exact_matches = 0

    for section in labels:
        pred_qty = int((predicted.get(section) or {}).get("predicted_quantity") or 0)
        exp_qty = int(expected.get(section) or 0)
        delta = pred_qty - exp_qty
        absolute_error += abs(delta)
        signed_error += delta
        if delta < 0:
            undercount += -delta
        elif delta > 0:
            overcount += delta
        else:
            exact_matches += 1

        if exp_qty > 0 and pred_qty > 0:
            bias = "match" if delta == 0 else ("undercount" if delta < 0 else "overcount")
        elif exp_qty > 0:
            bias = "missing"
        else:
            bias = "extra"

        rows.append(
            {
                "section": section,
                "predicted_quantity": pred_qty,
                "expected_quantity": exp_qty,
                "delta": delta,
                "bias": bias,
                "method": (predicted.get(section) or {}).get("method"),
            }
        )

    compared = len(labels)
    predicted_total = sum(
        int(item["predicted_quantity"] or 0) for item in predicted.values()
    )
    expected_total = sum(expected.values())
    return {
        "schema_version": "1.0",
        "scoreboard": "quantity",
        "quantity_definition": "eligible_labeled_candidate_count vs excel_member_schedule_rows",
        "is_true_physical_quantity": False,
        "does_not_affect_section_precision": True,
        "predicted_total": predicted_total,
        "expected_total": expected_total,
        "absolute_error": absolute_error,
        "mae": round(absolute_error / max(compared, 1), 4),
        "mean_signed_error": round(signed_error / max(compared, 1), 4),
        "undercount": undercount,
        "overcount": overcount,
        "sections_compared": compared,
        "exact_quantity_matches": exact_matches,
        "rows": rows,
    }


def build_scoreboards(
    *,
    section_recognition: Optional[dict],
    quantity_report: Union[QuantityReport, Dict[str, Any], None],
    ground_truth: Optional[dict],
) -> Dict[str, Any]:
    """Paired scoreboards: unique-section P/R stays separate from quantity MAE."""

    return {
        "schema_version": "1.0",
        "section_recognition": section_recognition,
        "quantity": build_quantity_scoreboard(quantity_report, ground_truth),
        "notes": {
            "section_recognition": (
                "Unique eligible designations vs Excel Framing/Column/Bracing. "
                "Do not use quantity MAE to judge this gate."
            ),
            "quantity": (
                "QuantityEngine labeled-callout counts vs Excel schedule rows. "
                "Not true physical quantity. Geometry does not create quantity."
            ),
        },
    }
