"""Excel ground-truth evaluation — never used as prediction input.

Compares already-produced PDF-only predictions against Excel for four
separate concepts:

  A. section recognition (unique rolled-section set)
  B. quantity (Excel schedule-row count vs PDF token count)
  C. length (linear feet)
  D. tonnage (tons from Overall Weight / ProjectHome Total Weight)

Excel must not influence extraction, fusion, ranking, or takeoff.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config import settings
from services.engineering.repeated_detail_linker import is_repeated_detail_member
from services.takeoff.ground_truth_excel import parse_ground_truth_excel


def _norm(value: Any) -> str:
    return str(value or "").upper().replace(" ", "").replace("-", "").replace("×", "X")


_FEET_INCH_RE = re.compile(
    r"""
    ^\s*
    (?P<feet>-?\d+(?:\.\d+)?)
    \s*(?:'|ft|feet)
    \s*-?\s*
    (?P<inches>
        \d+(?:\.\d+)?
        (?:\s+\d+\s*/\s*\d+)?
        |
        \d+\s*/\s*\d+
    )?
    \s*(?:"|in|inch|inches)?
    \s*$
    """,
    re.I | re.X,
)
_INCH_ONLY_RE = re.compile(
    r"""
    ^\s*
    (?P<inches>
        \d+(?:\.\d+)?
        (?:\s+\d+\s*/\s*\d+)?
        |
        \d+\s*/\s*\d+
    )
    \s*(?:"|in|inch|inches)
    \s*$
    """,
    re.I | re.X,
)


def _parse_inch_token(text: str) -> Optional[float]:
    raw = str(text or "").strip().replace('"', "")
    if not raw:
        return 0.0
    mixed = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)$", raw)
    if mixed:
        return int(mixed.group(1)) + int(mixed.group(2)) / int(mixed.group(3))
    frac = re.match(r"^(\d+)\s*/\s*(\d+)$", raw)
    if frac:
        return int(frac.group(1)) / int(frac.group(2))
    try:
        return float(raw)
    except ValueError:
        return None


def length_to_feet(value: Any) -> Optional[float]:
    """Parse a schedule length into decimal feet.

    Evaluator-only. Does not change production PDF/geometry parsing.
    Bare numbers are treated as already-decimal feet.
    """

    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none"}:
        return None

    feet_inch = _FEET_INCH_RE.match(text)
    if feet_inch:
        feet = float(feet_inch.group("feet"))
        inch_token = feet_inch.group("inches")
        inches = _parse_inch_token(inch_token) if inch_token else 0.0
        if inches is None:
            return None
        return feet + inches / 12.0

    inch_only = _INCH_ONLY_RE.match(text)
    if inch_only:
        inches = _parse_inch_token(inch_only.group("inches"))
        if inches is None:
            return None
        return inches / 12.0

    unit_match = re.match(r"^(-?\d+(?:\.\d+)?)\s*(?:ft|feet)$", text, re.I)
    if unit_match:
        return float(unit_match.group(1))

    try:
        return float(text)
    except ValueError:
        return None


def _to_float(value: Any) -> Optional[float]:
    """Generic numeric parse — not used for imperial lengths."""

    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(\.\d+)?", text)
    return float(match.group(0)) if match else None


def _length_close(predicted: Any, expected: Any, *, relative=0.08, absolute=0.5) -> bool:
    left = length_to_feet(predicted)
    right = length_to_feet(expected)
    if left is None or right is None:
        return False
    if right == 0:
        return abs(left) <= absolute
    return abs(left - right) <= max(absolute, abs(right) * relative)


def _tons_close(predicted: Any, expected: Any, *, relative=0.1, absolute=0.05) -> bool:
    left = _to_float(predicted)
    right = _to_float(expected)
    if left is None or right is None:
        return False
    if right == 0:
        return abs(left) <= absolute
    return abs(left - right) <= max(absolute, abs(right) * relative)


def _is_member_prediction(prediction: dict) -> bool:
    if is_repeated_detail_member(prediction):
        return False
    if prediction.get("takeoff_eligible") is False:
        return False
    scope = str(prediction.get("object_scope") or "")
    if scope in {
        "non_member_dimension",
        "context_definition",
        "detail_reference",
        "repeated_detail_evidence",
    }:
        return False
    annotation = str(prediction.get("annotation_type") or "").upper()
    if annotation == "DIMENSION":
        return False
    return True


def _prediction_section(prediction: dict) -> str:
    # Do not fall back to the raw token: that promoted dimensions such as
    # 1/2" into section metrics when `section` was empty.
    return _norm(
        prediction.get("section")
        or prediction.get("predicted_shape")
        or prediction.get("prediction")
        or ""
    )


def _prediction_fields(prediction: dict) -> dict:
    section = _prediction_section(prediction)
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
    tons = (
        prediction.get("tons")
        or prediction.get("overall_weight")
        or prediction.get("overall_weight_tons")
        or prediction.get("predicted_tons")
    )
    weight_plf = prediction.get("weight_plf")
    if weight_plf is None:
        weight = prediction.get("weight") or prediction.get("predicted_weight")
        db = (features.get("database") or {}).get("exact_match") or {}
        if weight is None and isinstance(db, dict):
            weight = db.get("W") or db.get("weight")
        # Catalog W / Weight is lb/ft, never tons.
        weight_plf = weight
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
        "length_ft": length_to_feet(length),
        "tons": _to_float(tons),
        "weight_plf": _to_float(weight_plf),
        "member": str(member or ""),
        "member_type": str(member_type or ""),
        "confidence": confidence,
        "original_token": prediction.get("original_token") or prediction.get("token"),
        "component_id": prediction.get("component_id") or prediction.get("object_id"),
        "family": prediction.get("family"),
    }


def _is_member_gt_item(item: dict) -> bool:
    scope = item.get("metric_scope")
    if scope:
        return scope == "structural_member"
    if item.get("member_type") == "connection":
        return False
    if item.get("entity_class") in {"connection", "plate"}:
        return False
    return True


def _aggregate_predictions(predictions: Iterable[dict]) -> Dict[str, dict]:
    aggregates: Dict[str, dict] = {}
    for prediction in predictions:
        if not _is_member_prediction(prediction):
            continue
        fields = _prediction_fields(prediction)
        section = fields["section"]
        if not section:
            continue
        bucket = aggregates.setdefault(
            section,
            {
                "section": section,
                "quantity": 0,
                "lengths_ft": [],
                "tons_values": [],
                "weight_plf_values": [],
                "members": [],
                "member_types": [],
                "confidence_sum": 0.0,
                "rows": [],
            },
        )
        bucket["quantity"] += int(prediction.get("quantity") or 1)
        if fields["length_ft"] is not None:
            bucket["lengths_ft"].append(fields["length_ft"])
        if fields["tons"] is not None:
            bucket["tons_values"].append(fields["tons"])
        if fields["weight_plf"] is not None:
            bucket["weight_plf_values"].append(fields["weight_plf"])
        if fields["member"]:
            bucket["members"].append(fields["member"])
        if fields["member_type"]:
            bucket["member_types"].append(fields["member_type"])
        bucket["confidence_sum"] += fields["confidence"]
        bucket["rows"].append(fields)
    for bucket in aggregates.values():
        bucket["total_lf"] = (
            sum(bucket["lengths_ft"]) if bucket["lengths_ft"] else None
        )
        bucket["avg_length"] = (
            sum(bucket["lengths_ft"]) / len(bucket["lengths_ft"])
            if bucket["lengths_ft"]
            else None
        )
        bucket["tons"] = (
            sum(bucket["tons_values"]) if bucket["tons_values"] else None
        )
        bucket["avg_weight_plf"] = (
            sum(bucket["weight_plf_values"]) / len(bucket["weight_plf_values"])
            if bucket["weight_plf_values"]
            else None
        )
        bucket["avg_confidence"] = bucket["confidence_sum"] / max(bucket["quantity"], 1)
    return aggregates


def _lookup_rollup(rollups: dict, section: str) -> Optional[dict]:
    if not rollups:
        return None
    if section in rollups:
        return rollups[section]
    for key, payload in rollups.items():
        if _norm(key) == section:
            return payload
    return None


def _aggregate_ground_truth(ground_truth: dict) -> Dict[str, dict]:
    aggregates: Dict[str, dict] = {}
    source_items = ground_truth.get("items") or []
    for item in source_items:
        if not _is_member_gt_item(item):
            continue
        section = _norm(item.get("canonical_label") or item.get("shape") or "")
        if not section:
            continue
        bucket = aggregates.setdefault(
            section,
            {
                "section": section,
                "quantity": 0,
                "lengths_ft": [],
                "tons_values": [],
                "weight_plf_values": [],
                "members": [],
                "member_types": [],
                "entity_class": item.get("entity_class"),
                "rows": [],
                "tonnage_source": item.get("tonnage_source"),
            },
        )
        qty = int(item.get("quantity") or 1)
        bucket["quantity"] += qty
        length_ft = length_to_feet(item.get("length"))
        if length_ft is not None:
            bucket["lengths_ft"].extend([length_ft] * qty)
        piece_tons = _to_float(
            item.get("overall_weight_tons")
            if item.get("overall_weight_tons") is not None
            else item.get("tons")
        )
        if piece_tons is not None:
            bucket["tons_values"].append(piece_tons)
            bucket["tonnage_source"] = "overall_weight"
        plf = _to_float(
            item.get("weight_plf")
            if item.get("weight_plf") is not None
            else item.get("weight")
        )
        if plf is not None:
            bucket["weight_plf_values"].append(plf)
        if item.get("mark"):
            bucket["members"].append(str(item.get("mark")))
        if item.get("member_type"):
            bucket["member_types"].append(str(item.get("member_type")))
        bucket["rows"].append(item)
    if not aggregates:
        for item in ground_truth.get("aggregates") or []:
            if not _is_member_gt_item(item):
                continue
            section = _norm(item.get("canonical_label") or item.get("shape") or "")
            if not section:
                continue
            aggregates[section] = {
                "section": section,
                "quantity": int(item.get("quantity") or 0),
                "lengths_ft": [],
                "tons_values": [],
                "weight_plf_values": [],
                "members": [],
                "member_types": [item.get("member_type")] if item.get("member_type") else [],
                "entity_class": item.get("entity_class"),
                "rows": item.get("occurrences") or [item],
                "tonnage_source": item.get("tonnage_source"),
            }
            for occurrence in item.get("occurrences") or [item]:
                length_ft = length_to_feet(occurrence.get("length"))
                if length_ft is not None:
                    aggregates[section]["lengths_ft"].append(length_ft)
                piece_tons = _to_float(
                    occurrence.get("overall_weight_tons")
                    if occurrence.get("overall_weight_tons") is not None
                    else occurrence.get("tons")
                )
                if piece_tons is not None:
                    aggregates[section]["tons_values"].append(piece_tons)
                plf = _to_float(
                    occurrence.get("weight_plf")
                    if occurrence.get("weight_plf") is not None
                    else occurrence.get("weight")
                )
                if plf is not None:
                    aggregates[section]["weight_plf_values"].append(plf)
                if occurrence.get("mark"):
                    aggregates[section]["members"].append(str(occurrence.get("mark")))
    rollups = ground_truth.get("section_rollups") or {}
    for bucket in aggregates.values():
        bucket["total_lf"] = (
            sum(bucket["lengths_ft"]) if bucket["lengths_ft"] else None
        )
        bucket["avg_length"] = (
            sum(bucket["lengths_ft"]) / len(bucket["lengths_ft"])
            if bucket["lengths_ft"]
            else None
        )
        if bucket["tons_values"]:
            bucket["tons"] = sum(bucket["tons_values"])
            bucket["tonnage_source"] = bucket.get("tonnage_source") or "overall_weight"
        else:
            rollup = _lookup_rollup(rollups, bucket["section"])
            tons = _to_float((rollup or {}).get("total_weight_tons"))
            bucket["tons"] = tons
            if tons is not None:
                bucket["tonnage_source"] = "project_home_total_weight"
        bucket["avg_weight_plf"] = (
            sum(bucket["weight_plf_values"]) / len(bucket["weight_plf_values"])
            if bucket["weight_plf_values"]
            else None
        )
        bucket["weight"] = bucket["avg_weight_plf"]
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
    """Compare PDF-only predictions to Excel ground truth.

    Predictions must already be fully generated. This function only reads
    Excel as offline ground truth.
    """

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
    tonnage_matches = tonnage_compared = 0
    member_matches = member_compared = 0
    absolute_qty_error = 0
    gt_total_lf = 0.0
    pred_total_lf = 0.0
    gt_total_tons = 0.0
    pred_total_tons = 0.0
    gt_has_lf = False
    pred_has_lf = False
    gt_has_tons = False
    pred_has_tons = False

    for label in labels:
        pred = predicted.get(label)
        exp = expected.get(label)
        pred_qty = int((pred or {}).get("quantity") or 0)
        exp_qty = int((exp or {}).get("quantity") or 0)
        pred_lf = (pred or {}).get("total_lf")
        exp_lf = (exp or {}).get("total_lf")
        pred_tons = (pred or {}).get("tons")
        exp_tons = (exp or {}).get("tons")
        if exp_lf is not None:
            gt_total_lf += float(exp_lf)
            gt_has_lf = True
        if pred_lf is not None:
            pred_total_lf += float(pred_lf)
            pred_has_lf = True
        if exp_tons is not None:
            gt_total_tons += float(exp_tons)
            gt_has_tons = True
        if pred_tons is not None:
            pred_total_tons += float(pred_tons)
            pred_has_tons = True

        if pred_qty > 0 and exp_qty > 0:
            section_tp += 1
            status = "match" if pred_qty == exp_qty else "wrong_quantity"
            quantity_compared += 1
            if pred_qty == exp_qty:
                quantity_correct += 1
            absolute_qty_error += abs(pred_qty - exp_qty)

            length_ok = None
            if pred_lf is not None and exp_lf is not None:
                length_compared += 1
                length_ok = _length_close(pred_lf, exp_lf)
                if length_ok:
                    length_matches += 1

            tons_ok = None
            if pred_tons is not None and exp_tons is not None:
                tonnage_compared += 1
                tons_ok = _tons_close(pred_tons, exp_tons)
                if tons_ok:
                    tonnage_matches += 1

            pred_members = set((pred or {}).get("members") or [])
            exp_members = set((exp or {}).get("members") or [])
            member_ok = None
            if pred_members or exp_members:
                member_compared += 1
                member_ok = (
                    bool(pred_members & exp_members) if exp_members else bool(pred_members)
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
                    "quantity_comparison": "schedule_row_vs_token",
                    "predicted_length_lf": pred_lf,
                    "expected_length_lf": exp_lf,
                    "predicted_length": (pred or {}).get("avg_length"),
                    "expected_length": (exp or {}).get("avg_length"),
                    "length_match": length_ok,
                    "predicted_tons": pred_tons,
                    "expected_tons": exp_tons,
                    "tonnage_match": tons_ok,
                    "tonnage_source": (exp or {}).get("tonnage_source"),
                    "predicted_weight_plf": (pred or {}).get("avg_weight_plf"),
                    "expected_weight_plf": (exp or {}).get("avg_weight_plf"),
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
                "quantity_comparison": "schedule_row_vs_token",
                "expected_length_lf": exp_lf,
                "expected_length": (exp or {}).get("avg_length"),
                "expected_tons": exp_tons,
                "tonnage_source": (exp or {}).get("tonnage_source"),
                "expected_weight_plf": (exp or {}).get("avg_weight_plf"),
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
                "quantity_comparison": "schedule_row_vs_token",
                "predicted_length_lf": pred_lf,
                "predicted_length": (pred or {}).get("avg_length"),
                "predicted_tons": pred_tons,
                "predicted_weight_plf": (pred or {}).get("avg_weight_plf"),
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

    lf_error = None
    if gt_has_lf:
        lf_error = round(pred_total_lf - gt_total_lf, 4) if pred_has_lf else None
    tons_error = None
    if gt_has_tons:
        tons_error = (
            round(pred_total_tons - gt_total_tons, 4) if pred_has_tons else None
        )

    quantity_block = {
        "definition": "schedule_row_vs_token",
        "note": (
            "Excel quantity is framing/column/bracing schedule row count "
            "(or Count when present). Predicted quantity is PDF label/"
            "token occurrence count. This is not QuantityEngine physical "
            "member quantity."
        ),
        "accuracy": round(quantity_accuracy, 4),
        "coverage": round(quantity_coverage, 4),
        "absolute_error": absolute_qty_error,
        "expected_schedule_rows": total_expected_qty,
        "predicted_token_count": total_predicted_qty,
    }
    length_block = {
        "unit": "ft",
        "gt_total_lf": round(gt_total_lf, 4) if gt_has_lf else None,
        "predicted_total_lf": round(pred_total_lf, 4) if pred_has_lf else None,
        "error_lf": lf_error,
        "compared_sections": length_compared,
        "section_match_rate": round(length_matches / max(length_compared, 1), 4)
        if length_compared
        else None,
    }
    tonnage_block = {
        "unit": "tons",
        "gt_tons": round(gt_total_tons, 4) if gt_has_tons else None,
        "predicted_tons": round(pred_total_tons, 4) if pred_has_tons else None,
        "error_tons": tons_error,
        "compared_sections": tonnage_compared,
        "section_match_rate": round(tonnage_matches / max(tonnage_compared, 1), 4)
        if tonnage_compared
        else None,
        "note": (
            "GT tons come from Overall Weight (piece tons) or ProjectHome "
            "Total Weight / Total Weight (tons). Weight/IFS_W is lb/ft and "
            "is not used as tonnage."
        ),
    }

    report = {
        "schema_version": "1.1",
        "role": "excel_ground_truth_evaluation",
        "excel_is_prediction": False,
        "prediction_source": "pdf_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": ground_truth.get("source_file"),
        "parser": ground_truth.get("parser") or "ground_truth_excel",
        "sheets_used": ground_truth.get("member_sheets_used")
        or ground_truth.get("sheets_used")
        or [],
        "connection_rows_excluded_from_member_metrics": True,
        "metrics": {
            "section": section_metrics,
            "precision": section_metrics["precision"],
            "recall": section_metrics["recall"],
            "f1": section_metrics["f1"],
            "quantity": quantity_block,
            "quantity_accuracy": quantity_block["accuracy"],
            "quantity_coverage": quantity_block["coverage"],
            "absolute_quantity_error": absolute_qty_error,
            "length": length_block,
            "length_accuracy": length_block["section_match_rate"],
            "tonnage": tonnage_block,
            "weight_accuracy": tonnage_block["section_match_rate"],
            "member_accuracy": round(
                member_matches / max(member_compared, 1), 4
            )
            if member_compared
            else None,
            "length_compared": length_compared,
            "weight_compared": tonnage_compared,
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
            "quantity_accuracy": quantity_block["accuracy"],
            "quantity_definition": "schedule_row_vs_token",
            "gt_tons": tonnage_block["gt_tons"],
            "gt_total_lf": length_block["gt_total_lf"],
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
            "connection_row_count": len(ground_truth.get("connection_items") or []),
            "quantity_definition": ground_truth.get("quantity_definition")
            or "schedule_row_count",
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
    md_path = path.with_suffix(".md")
    metrics = report.get("metrics") or {}
    section = metrics.get("section") or {}
    quantity = metrics.get("quantity") or {}
    length = metrics.get("length") or {}
    tonnage = metrics.get("tonnage") or {}
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
                f"- Prediction source: `{report.get('prediction_source') or 'pdf_only'}`",
                "",
                "## A. Section recognition",
                f"- Precision: **{section.get('precision', metrics.get('precision'))}**",
                f"- Recall: **{section.get('recall', metrics.get('recall'))}**",
                f"- F1: **{section.get('f1', metrics.get('f1'))}**",
                f"- Missing sections: **{metrics.get('missing_count')}**",
                f"- Extra sections: **{metrics.get('extra_count')}**",
                "",
                "## B. Quantity (schedule-row vs PDF token count)",
                f"- Definition: `{quantity.get('definition', 'schedule_row_vs_token')}`",
                f"- Accuracy: **{quantity.get('accuracy', metrics.get('quantity_accuracy'))}**",
                f"- Coverage: **{quantity.get('coverage', metrics.get('quantity_coverage'))}**",
                f"- Excel schedule rows: **{quantity.get('expected_schedule_rows')}**",
                f"- PDF token count: **{quantity.get('predicted_token_count')}**",
                "",
                "## C. Length (linear feet)",
                f"- GT total LF: **{length.get('gt_total_lf')}**",
                f"- Predicted total LF: **{length.get('predicted_total_lf')}**",
                f"- Error LF: **{length.get('error_lf')}**",
                "",
                "## D. Tonnage (tons)",
                f"- GT tons: **{tonnage.get('gt_tons')}**",
                f"- Predicted tons: **{tonnage.get('predicted_tons')}**",
                f"- Error tons: **{tonnage.get('error_tons')}**",
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
