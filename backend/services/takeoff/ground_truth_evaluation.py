"""
Excel ground-truth evaluation -- never used as prediction input.

Delegates the parsing + matching + metric math to
``services.takeoff.canonical_takeoff_eval`` (the single shared
implementation) and maps the result onto the response shape existing
consumers and the Validation UI expect, PLUS the estimator-facing block:

    Section | Ground Truth | Correctly Caught | Success
      caught(s)       = min(predicted(s), ground_truth(s))
      success(s)      = caught / ground_truth
      overall_success = Σ caught / Σ ground_truth        (never > 100%)

Over-detection is always exposed alongside it -- total predictions, false
positives, precision -- so a high-recall/low-precision run can never look
perfect.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from services.takeoff.canonical_takeoff_eval import (
    PRIMARY_FRAMING,
    evaluate as _canonical_evaluate,
    parse_workbook_ground_truth,
)


def _f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0


def evaluate_against_excel(
    predictions: List[dict],
    *,
    excel_path: Optional[str | Path] = None,
    ground_truth: Optional[dict] = None,
    scope: str = PRIMARY_FRAMING,
) -> Dict[str, Any]:
    """Compare AI predictions to Excel ground truth and build an eval report."""

    if ground_truth is None:
        if excel_path is None:
            raise ValueError("excel_path or ground_truth is required")
        ground_truth = parse_workbook_ground_truth(excel_path)

    result = _canonical_evaluate(predictions, ground_truth, scope=scope)
    rows = result["rows"]

    recall = result["overall_success_pct"] / 100.0          # Σcaught / ΣGT
    precision = result["precision_pct"] / 100.0              # Σcaught / Σpred

    comparisons: List[dict] = []
    missing_elements: List[dict] = []
    extra_elements: List[dict] = []
    for r in rows:
        status = (
            "match" if r["status"] == "match"
            else "missing_member" if r["status"] == "missing"
            else "extra_member" if r["status"] == "extra"
            else "wrong_quantity"
        )
        entry = {
            "section": r["section"],
            "status": status,
            "predicted_quantity": r["predicted"],
            "expected_quantity": r["ground_truth"],
            "quantity_difference": r["delta"],
            "caught": r["caught"],
            "success_pct": r["success_pct"],
            "length_match": None,
            "weight_match": None,
            "member_match": None,
            "gt_rows": r["gt_rows"],
            "predicted_object_ids": r["predicted_object_ids"],
        }
        comparisons.append(entry)
        if status == "missing_member":
            missing_elements.append(entry)
        elif status == "extra_member":
            extra_elements.append(entry)

    metrics = {
        # honest redefinitions, computed on caught = min(pred, GT)
        "overall_success_pct": result["overall_success_pct"],
        "section_recall_pct": result["section_recall_pct"],
        "section_precision_pct": result["section_precision_pct"],
        "matching_quantity": result["matching_quantity"],
        "excess_quantity": result["excess_quantity"],
        "auto_resolved_total": result["auto_resolved_total"],
        "review_member_quantity": result["review_member_quantity"],
        "weak_geometry_quantity": result["weak_geometry_quantity"],
        "caught": result["caught"],
        "ground_truth_total": result["ground_truth_total"],
        "predicted_total": result["predicted_total"],
        "false_positives": result["false_positives"],
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": _f1(precision, recall),
        # kept for UI/back-compat; now derived from the same numbers
        "quantity_accuracy": round(recall, 4),
        "quantity_coverage": round(recall, 4),
        "match_rate": round(precision, 4),
        "length_accuracy": None,
        "weight_accuracy": None,
        "member_accuracy": None,
        "predicted_unique_sections": result["sections_predicted"],
        "expected_unique_sections": result["sections_ground_truth"],
        "predicted_total_quantity": result["predicted_total"],
        "expected_total_quantity": result["ground_truth_total"],
        "missing_count": result["sections_missing"],
        "extra_count": result["sections_extra"],
        "abstained_predictions": result["abstained_predictions"],
        "plate_or_dimension_predictions": result["plate_or_dimension_predictions"],
        "catalog_invalid_predictions": result["catalog_invalid_predictions"],
        "unsupported_gt_quantity": result["unsupported_gt_quantity"],
        "excluded_gt_quantity": result["excluded_gt_quantity"],
        "scope": scope,
        "scope_quantity": result["scope_quantity"],
    }

    return {
        "schema_version": "2.0",
        "role": "excel_ground_truth_evaluation",
        "excel_is_prediction": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": ground_truth.get("source_file"),
        "parser": ground_truth.get("parser") or "canonical_takeoff_eval",
        "sheets_used": ground_truth.get("sheets_used") or [],
        "scope": scope,
        # estimator-facing primary view
        "estimator_table": [
            {"section": r["section"], "ground_truth": r["ground_truth"],
             "correctly_caught": r["caught"], "success_pct": r["success_pct"],
             "predicted": r["predicted"], "status": r["status"]}
            for r in rows
        ],
        "overall_success_pct": result["overall_success_pct"],
        "metrics": metrics,
        "summary": {
            "overall_success_pct": result["overall_success_pct"],
            "caught": result["caught"],
            "ground_truth_total": result["ground_truth_total"],
            "match": sum(1 for r in rows if r["status"] == "match"),
            "wrong_quantity": sum(1 for r in rows if r["status"] in ("over", "under")),
            "missing_member": result["sections_missing"],
            "extra_member": result["sections_extra"],
            "false_positives": result["false_positives"],
            "match_rate": round(precision, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": _f1(precision, recall),
            "quantity_accuracy": round(recall, 4),
        },
        "comparisons": comparisons,
        "missing_elements": missing_elements,
        "extra_elements": extra_elements,
        "ground_truth": {
            "unique_labels": ground_truth.get("unique_labels"),
            "total_quantity": ground_truth.get("total_quantity"),
            "entity_distribution": ground_truth.get("entity_distribution"),
            "row_count": ground_truth.get("row_count"),
            "scope_quantity": ground_truth.get("scope_quantity"),
            "scope_sections": ground_truth.get("scope_sections"),
            "dropped": ground_truth.get("dropped"),
            "sheets": ground_truth.get("sheets"),
        },
    }


def persist_evaluation_report(
    report: dict,
    *,
    pdf_name: str = "",
    excel_name: str = "",
) -> Path:
    """Write an automatic evaluation report under takeoff_exports."""

    destination = settings.takeoff_exports_dir
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = Path(pdf_name or "takeoff").stem or "takeoff"
    path = destination / f"eval_{stem}_{stamp}.json"
    payload = {**report, "pdf_file": pdf_name, "excel_file": excel_name,
               "report_path": str(path)}
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    metrics = report.get("metrics") or {}
    table = report.get("estimator_table") or []
    table_lines = [
        f"| `{r['section']}` | {r['ground_truth']} | {r['correctly_caught']} | "
        f"{r['success_pct']}% |"
        for r in sorted(table, key=lambda r: -r["ground_truth"])[:60]
    ] or ["| _none_ | | | |"]
    md_path = path.with_suffix(".md")
    md_path.write_text(
        "\n".join(
            [
                "# Takeoff evaluation report",
                "",
                f"- PDF: `{pdf_name}`",
                f"- Excel (ground truth only): `{excel_name}`",
                f"- Generated: `{report.get('generated_at')}`",
                f"- Scope: `{report.get('scope')}`  (sheets: "
                f"{', '.join(report.get('sheets_used') or []) or '—'})",
                "",
                "## Overall",
                f"- **Overall success: {metrics.get('overall_success_pct')}%** "
                f"(caught {metrics.get('caught')} / GT {metrics.get('ground_truth_total')})",
                f"- Precision: **{round(100 * (metrics.get('precision') or 0), 1)}%** "
                f"(predicted {metrics.get('predicted_total')}, "
                f"false positives {metrics.get('false_positives')})",
                f"- Catalog-invalid predictions: {metrics.get('catalog_invalid_predictions')}  ·  "
                f"abstained: {metrics.get('abstained_predictions')}  ·  "
                f"plate/dimension: {metrics.get('plate_or_dimension_predictions')}",
                f"- Unsupported GT quantity (plates + connections): "
                f"{metrics.get('unsupported_gt_quantity')}  ·  "
                f"Excluded GT quantity (deck/misc/unparseable): "
                f"{metrics.get('excluded_gt_quantity')}",
                "",
                "## Section | Ground Truth | Correctly Caught | Success",
                "|---|---:|---:|---:|",
                *table_lines,
            ]
        ),
        encoding="utf-8",
    )
    report["report_path"] = str(path)
    report["markdown_report_path"] = str(md_path)
    return path
