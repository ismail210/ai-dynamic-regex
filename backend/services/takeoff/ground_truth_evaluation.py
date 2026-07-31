"""Excel ground-truth evaluation — never used as prediction input.

Compares AI predictions against Excel for:
  section, quantity, length, weight, member

Produces precision, recall, quantity accuracy, missing/extra elements,
and automatic evaluation reports.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from config import settings
from services.takeoff.ground_truth_excel import parse_ground_truth_excel


def _norm(value: Any) -> str:
    return str(value or "").upper().replace(" ", "").replace("-", "").replace("×", "X")


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(\.\d+)?", text)
    return float(match.group(0)) if match else None


def _length_close(predicted: Any, expected: Any, *, relative=0.08, absolute=0.5) -> bool:
    left = _to_float(predicted)
    right = _to_float(expected)
    if left is None or right is None:
        return False
    if right == 0:
        return abs(left) <= absolute
    return abs(left - right) <= max(absolute, abs(right) * relative)


def _weight_close(predicted: Any, expected: Any, *, relative=0.1, absolute=1.0) -> bool:
    return _length_close(predicted, expected, relative=relative, absolute=absolute)


def _prediction_fields(prediction: dict) -> dict:
    section = _norm(
        prediction.get("section")
        or prediction.get("predicted_shape")
        or prediction.get("prediction")
        or prediction.get("corrected_token")
        or prediction.get("original_token")
        or ""
    )
    geometry = prediction.get("geometry_preview") or {}
    features = prediction.get("features") or {}
    geometry_features = features.get("geometry") or {}
    obj = geometry_features.get("object") or {}
    length = (
        geometry.get("length")
        or obj.get("length")
        or prediction.get("length")
        or prediction.get("predicted_length")
    )
    weight = prediction.get("weight") or prediction.get("predicted_weight")
    if weight is None:
        db = (features.get("database") or {}).get("exact_match") or {}
        if isinstance(db, dict):
            weight = db.get("W") or db.get("weight")
    member = (
        prediction.get("component_id")
        or prediction.get("mark")
        or prediction.get("member")
        or prediction.get("material")
        or ""
    )
    member_type = (
        prediction.get("entity_type")
        or (prediction.get("entity") or {}).get("category")
        or ""
    )
    conf = prediction.get("confidence")
    confidence = float(
        conf.get("overall") if isinstance(conf, dict) else conf or 0.0
    )
    return {
        "section": section,
        "quantity": 1,
        "length": _to_float(length),
        "weight": _to_float(weight),
        "member": str(member or ""),
        "member_type": str(member_type or ""),
        "confidence": confidence,
        "original_token": prediction.get("original_token") or prediction.get("token"),
        "component_id": prediction.get("component_id") or prediction.get("object_id"),
        "family": prediction.get("family"),
    }


def _aggregate_predictions(predictions: Iterable[dict]) -> Dict[str, dict]:
    aggregates: Dict[str, dict] = {}
    for prediction in predictions:
        fields = _prediction_fields(prediction)
        section = fields["section"]
        if not section:
            continue
        bucket = aggregates.setdefault(
            section,
            {
                "section": section,
                "quantity": 0,
                "lengths": [],
                "weights": [],
                "members": [],
                "member_types": [],
                "confidence_sum": 0.0,
                "rows": [],
            },
        )
        bucket["quantity"] += 1
        if fields["length"] is not None:
            bucket["lengths"].append(fields["length"])
        if fields["weight"] is not None:
            bucket["weights"].append(fields["weight"])
        if fields["member"]:
            bucket["members"].append(fields["member"])
        if fields["member_type"]:
            bucket["member_types"].append(fields["member_type"])
        bucket["confidence_sum"] += fields["confidence"]
        bucket["rows"].append(fields)
    for bucket in aggregates.values():
        bucket["avg_length"] = (
            sum(bucket["lengths"]) / len(bucket["lengths"])
            if bucket["lengths"]
            else None
        )
        bucket["avg_weight"] = (
            sum(bucket["weights"]) / len(bucket["weights"])
            if bucket["weights"]
            else None
        )
        bucket["avg_confidence"] = bucket["confidence_sum"] / max(bucket["quantity"], 1)
    return aggregates


def _aggregate_ground_truth(ground_truth: dict) -> Dict[str, dict]:
    aggregates: Dict[str, dict] = {}
    for item in ground_truth.get("items") or []:
        section = _norm(item.get("canonical_label") or item.get("shape") or "")
        if not section:
            continue
        bucket = aggregates.setdefault(
            section,
            {
                "section": section,
                "quantity": 0,
                "lengths": [],
                "weights": [],
                "members": [],
                "member_types": [],
                "entity_class": item.get("entity_class"),
                "rows": [],
            },
        )
        qty = int(item.get("quantity") or 1)
        bucket["quantity"] += qty
        length = _to_float(item.get("length"))
        weight = _to_float(item.get("weight"))
        if length is not None:
            bucket["lengths"].extend([length] * qty)
        if weight is not None:
            bucket["weights"].extend([weight] * qty)
        if item.get("mark"):
            bucket["members"].append(str(item.get("mark")))
        if item.get("member_type"):
            bucket["member_types"].append(str(item.get("member_type")))
        bucket["rows"].append(item)
    # Prefer precomputed aggregates when items missing length detail.
    if not aggregates:
        for item in ground_truth.get("aggregates") or []:
            section = _norm(item.get("canonical_label") or item.get("shape") or "")
            if not section:
                continue
            aggregates[section] = {
                "section": section,
                "quantity": int(item.get("quantity") or 0),
                "lengths": [],
                "weights": [],
                "members": [],
                "member_types": [item.get("member_type")] if item.get("member_type") else [],
                "entity_class": item.get("entity_class"),
                "rows": item.get("occurrences") or [item],
            }
            for occurrence in item.get("occurrences") or []:
                length = _to_float(occurrence.get("length"))
                weight = _to_float(occurrence.get("weight"))
                if length is not None:
                    aggregates[section]["lengths"].append(length)
                if weight is not None:
                    aggregates[section]["weights"].append(weight)
                if occurrence.get("mark"):
                    aggregates[section]["members"].append(str(occurrence.get("mark")))
    for bucket in aggregates.values():
        bucket["avg_length"] = (
            sum(bucket["lengths"]) / len(bucket["lengths"])
            if bucket["lengths"]
            else None
        )
        bucket["avg_weight"] = (
            sum(bucket["weights"]) / len(bucket["weights"])
            if bucket["weights"]
            else None
        )
    return aggregates


def _binary_metrics(true_positive: int, false_positive: int, false_negative: int) -> dict:
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (
        2 * precision * recall / max(precision + recall, 1e-9)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def evaluate_against_excel(
    predictions: List[dict],
    *,
    excel_path: Optional[str | Path] = None,
    ground_truth: Optional[dict] = None,
) -> Dict[str, Any]:
    """Compare AI predictions to Excel ground truth and build an eval report."""

    if ground_truth is None:
        if excel_path is None:
            raise ValueError("excel_path or ground_truth is required")
        ground_truth = parse_ground_truth_excel(excel_path)

    predicted = _aggregate_predictions(predictions)
    expected = _aggregate_ground_truth(ground_truth)
    labels = sorted(set(predicted) | set(expected))

    comparisons: List[dict] = []
    missing_elements: List[dict] = []
    extra_elements: List[dict] = []
    section_tp = section_fp = section_fn = 0
    quantity_correct = 0
    quantity_compared = 0
    length_matches = length_compared = 0
    weight_matches = weight_compared = 0
    member_matches = member_compared = 0
    absolute_qty_error = 0

    for label in labels:
        pred = predicted.get(label)
        exp = expected.get(label)
        pred_qty = int((pred or {}).get("quantity") or 0)
        exp_qty = int((exp or {}).get("quantity") or 0)

        if pred_qty > 0 and exp_qty > 0:
            section_tp += 1
            status = "match" if pred_qty == exp_qty else "wrong_quantity"
            quantity_compared += 1
            if pred_qty == exp_qty:
                quantity_correct += 1
            absolute_qty_error += abs(pred_qty - exp_qty)

            pred_length = (pred or {}).get("avg_length")
            exp_length = (exp or {}).get("avg_length")
            length_ok = None
            if pred_length is not None and exp_length is not None:
                length_compared += 1
                length_ok = _length_close(pred_length, exp_length)
                if length_ok:
                    length_matches += 1

            pred_weight = (pred or {}).get("avg_weight")
            exp_weight = (exp or {}).get("avg_weight")
            weight_ok = None
            if pred_weight is not None and exp_weight is not None:
                weight_compared += 1
                weight_ok = _weight_close(pred_weight, exp_weight)
                if weight_ok:
                    weight_matches += 1

            # Member comparison: shared marks or member_type agreement.
            pred_members = set((pred or {}).get("members") or [])
            exp_members = set((exp or {}).get("members") or [])
            member_ok = None
            if pred_members or exp_members:
                member_compared += 1
                member_ok = bool(pred_members & exp_members) if exp_members else bool(pred_members)
                if not exp_members and (pred or {}).get("member_types") and (exp or {}).get("member_types"):
                    member_ok = bool(
                        set((pred or {}).get("member_types") or [])
                        & set((exp or {}).get("member_types") or [])
                    )
                if member_ok:
                    member_matches += 1
            elif (pred or {}).get("member_types") and (exp or {}).get("member_types"):
                member_compared += 1
                member_ok = bool(
                    set((pred or {}).get("member_types") or [])
                    & set((exp or {}).get("member_types") or [])
                )
                if member_ok:
                    member_matches += 1

            comparisons.append(
                {
                    "section": label,
                    "status": status,
                    "predicted_quantity": pred_qty,
                    "expected_quantity": exp_qty,
                    "quantity_difference": pred_qty - exp_qty,
                    "predicted_length": pred_length,
                    "expected_length": exp_length,
                    "length_match": length_ok,
                    "predicted_weight": pred_weight,
                    "expected_weight": exp_weight,
                    "weight_match": weight_ok,
                    "predicted_members": sorted(pred_members),
                    "expected_members": sorted(exp_members),
                    "member_match": member_ok,
                    "entity_class": (exp or {}).get("entity_class"),
                    "member_type": (
                        ((exp or {}).get("member_types") or [None])[0]
                    ),
                }
            )
        elif exp_qty > 0:
            section_fn += 1
            item = {
                "section": label,
                "status": "missing_member",
                "predicted_quantity": 0,
                "expected_quantity": exp_qty,
                "quantity_difference": -exp_qty,
                "expected_length": (exp or {}).get("avg_length"),
                "expected_weight": (exp or {}).get("avg_weight"),
                "expected_members": sorted(set((exp or {}).get("members") or [])),
                "entity_class": (exp or {}).get("entity_class"),
                "member_type": (((exp or {}).get("member_types") or [None])[0]),
            }
            comparisons.append(item)
            missing_elements.append(item)
        else:
            section_fp += 1
            item = {
                "section": label,
                "status": "extra_member",
                "predicted_quantity": pred_qty,
                "expected_quantity": 0,
                "quantity_difference": pred_qty,
                "predicted_length": (pred or {}).get("avg_length"),
                "predicted_weight": (pred or {}).get("avg_weight"),
                "predicted_members": sorted(set((pred or {}).get("members") or [])),
                "family": ((pred or {}).get("rows") or [{}])[0].get("family"),
            }
            comparisons.append(item)
            extra_elements.append(item)

    section_metrics = _binary_metrics(section_tp, section_fp, section_fn)
    quantity_accuracy = quantity_correct / max(quantity_compared, 1)
    total_expected_qty = sum(int(v.get("quantity") or 0) for v in expected.values())
    total_predicted_qty = sum(int(v.get("quantity") or 0) for v in predicted.values())
    quantity_coverage = 1.0 - (
        absolute_qty_error / max(total_expected_qty, 1)
    )
    quantity_coverage = max(0.0, min(1.0, quantity_coverage))

    report = {
        "schema_version": "1.0",
        "role": "excel_ground_truth_evaluation",
        "excel_is_prediction": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": ground_truth.get("source_file"),
        "parser": ground_truth.get("parser") or "ground_truth_excel",
        "sheets_used": ground_truth.get("sheets_used") or [],
        "metrics": {
            "section": section_metrics,
            "precision": section_metrics["precision"],
            "recall": section_metrics["recall"],
            "f1": section_metrics["f1"],
            "quantity_accuracy": round(quantity_accuracy, 4),
            "quantity_coverage": round(quantity_coverage, 4),
            "absolute_quantity_error": absolute_qty_error,
            "length_accuracy": round(
                length_matches / max(length_compared, 1), 4
            )
            if length_compared
            else None,
            "weight_accuracy": round(
                weight_matches / max(weight_compared, 1), 4
            )
            if weight_compared
            else None,
            "member_accuracy": round(
                member_matches / max(member_compared, 1), 4
            )
            if member_compared
            else None,
            "length_compared": length_compared,
            "weight_compared": weight_compared,
            "member_compared": member_compared,
            "predicted_unique_sections": len(predicted),
            "expected_unique_sections": len(expected),
            "predicted_total_quantity": total_predicted_qty,
            "expected_total_quantity": total_expected_qty,
            "missing_count": len(missing_elements),
            "extra_count": len(extra_elements),
        },
        "summary": {
            "match": sum(1 for row in comparisons if row["status"] == "match"),
            "wrong_quantity": sum(
                1 for row in comparisons if row["status"] == "wrong_quantity"
            ),
            "missing_member": len(missing_elements),
            "extra_member": len(extra_elements),
            "unknown_entity": len(extra_elements),
            "match_rate": section_metrics["precision"],
            "precision": section_metrics["precision"],
            "recall": section_metrics["recall"],
            "f1": section_metrics["f1"],
            "quantity_accuracy": round(quantity_accuracy, 4),
        },
        "comparisons": comparisons,
        "missing_elements": missing_elements,
        "extra_elements": extra_elements,
        "predicted_aggregates": list(predicted.values()),
        "expected_aggregates": list(expected.values()),
        "ground_truth": {
            "unique_labels": ground_truth.get("unique_labels"),
            "total_quantity": ground_truth.get("total_quantity"),
            "entity_distribution": ground_truth.get("entity_distribution"),
            "row_count": ground_truth.get("row_count"),
        },
    }
    return report


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
    payload = {
        **report,
        "pdf_file": pdf_name,
        "excel_file": excel_name,
        "report_path": str(path),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    # Also write a compact markdown summary for engineers.
    md_path = path.with_suffix(".md")
    metrics = report.get("metrics") or {}
    missing_lines = [
        f"- `{item.get('section')}` x{item.get('expected_quantity')}"
        for item in (report.get("missing_elements") or [])[:50]
    ] or ["- None"]
    extra_lines = [
        f"- `{item.get('section')}` x{item.get('predicted_quantity')}"
        for item in (report.get("extra_elements") or [])[:50]
    ] or ["- None"]
    md_path.write_text(
        "\n".join(
            [
                "# Takeoff evaluation report",
                "",
                f"- PDF: `{pdf_name}`",
                f"- Excel (ground truth only): `{excel_name}`",
                f"- Generated: `{report.get('generated_at')}`",
                "",
                "## Metrics",
                f"- Precision: **{metrics.get('precision')}**",
                f"- Recall: **{metrics.get('recall')}**",
                f"- F1: **{metrics.get('f1')}**",
                f"- Quantity accuracy: **{metrics.get('quantity_accuracy')}**",
                f"- Quantity coverage: **{metrics.get('quantity_coverage')}**",
                f"- Length accuracy: **{metrics.get('length_accuracy')}**",
                f"- Weight accuracy: **{metrics.get('weight_accuracy')}**",
                f"- Member accuracy: **{metrics.get('member_accuracy')}**",
                f"- Missing elements: **{metrics.get('missing_count')}**",
                f"- Extra elements: **{metrics.get('extra_count')}**",
                "",
                "## Missing elements",
                *missing_lines,
                "",
                "## Extra elements",
                *extra_lines,
            ]
        ),
        encoding="utf-8",
    )
    report["report_path"] = str(path)
    report["markdown_report_path"] = str(md_path)
    return path
