"""
Takeoff Validation Service
==========================

Compare AI predictions from a drawing PDF against ground-truth Excel.

Excel is NEVER used as prediction input — only as ground truth.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from services.takeoff.ground_truth_evaluation import (
    evaluate_against_excel,
    persist_evaluation_report,
)
from services.takeoff.ground_truth_excel import parse_ground_truth_excel


def _norm(value: str) -> str:
    return str(value or "").upper().replace(" ", "").replace("-", "")


def _register_uploaded_pair(pdf_path: Path, excel_path: Path) -> Optional[str]:
    """Copy uploaded PDF+Excel into training dirs and refresh the pair manifest."""

    try:
        settings.training_pdf_dir.mkdir(parents=True, exist_ok=True)
        settings.training_excel_dir.mkdir(parents=True, exist_ok=True)
        stem = pdf_path.stem
        dest_pdf = settings.training_pdf_dir / f"{stem}{pdf_path.suffix.lower()}"
        dest_excel = settings.training_excel_dir / f"{stem}{excel_path.suffix.lower()}"
        if pdf_path.resolve() != dest_pdf.resolve():
            shutil.copy2(pdf_path, dest_pdf)
        if excel_path.resolve() != dest_excel.resolve():
            shutil.copy2(excel_path, dest_excel)

        manifest_path = settings.pair_manifest_path
        manifest = {"version": 1, "pairs": []}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = {"version": 1, "pairs": []}
        pairs = list(manifest.get("pairs") or [])
        existing = next((item for item in pairs if item.get("id") == stem), None)
        entry = {
            "id": stem,
            "label": stem,
            "pdf": dest_pdf.name,
            "excel": dest_excel.name,
            "pdf_canonical": dest_pdf.name,
            "excel_canonical": dest_excel.name,
            "role": "ground_truth_pair",
        }
        if existing:
            existing.update(entry)
        else:
            pairs.append(entry)
        manifest["pairs"] = pairs
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return stem
    except OSError:
        return None


def _auto_build_dataset(pair_id: Optional[str] = None) -> Optional[dict]:
    try:
        from services.takeoff.paired_dataset_builder import build_paired_training_dataset

        return build_paired_training_dataset(
            persist=True,
            pair_ids=[pair_id] if pair_id else None,
        )
    except Exception as exc:
        return {"error": str(exc), "built": False}


def validate_takeoff(
    *,
    pdf_path: str | Path,
    excel_path: str | Path,
    run_ai: bool = True,
    auto_register_pair: bool = True,
    auto_build_dataset: bool = True,
    persist_report: bool = True,
) -> Dict[str, Any]:
    """
    Run AI prediction on PDF and validate against Excel ground truth.
    """

    pdf_path = Path(pdf_path)
    excel_path = Path(excel_path)

    from services.multimodal.pipeline import run_multimodal_pipeline

    multimodal = (
        run_multimodal_pipeline(
            pdf_path,
            expected_excel_path=excel_path,
            persist=False,
        )
        if run_ai
        else {"predictions": [], "summary": {"pages": 0}}
    )
    predictions = multimodal.get("predictions") or []

    pred_rows: List[dict] = []
    for result in predictions:
        label = _norm(
            result.get("section")
            or result.get("predicted_shape")
            or result.get("prediction")
            or result.get("original_token")
            or ""
        )
        if not label:
            continue
        conf = result.get("confidence")
        confidence_value = float(
            conf.get("overall") if isinstance(conf, dict) else conf or 0.0
        )
        explanation = result.get("explanation") or {}
        geometry = result.get("geometry_preview") or {}
        features = result.get("features") or {}
        db = (features.get("database") or {}).get("exact_match") or {}
        weight = db.get("W") if isinstance(db, dict) else None
        if weight is None and isinstance(db, dict):
            weight = db.get("weight")
        pred_rows.append(
            {
                "component_id": result.get("component_id"),
                "token": result.get("original_token") or result.get("token"),
                "corrected_token": result.get("corrected_token"),
                "family": result.get("family"),
                "section": label,
                "prediction": label,
                "material": result.get("material"),
                "length": geometry.get("length"),
                "weight": weight,
                "entity_class": result.get("entity_type")
                or (result.get("entity") or {}).get("category"),
                "confidence": confidence_value,
                "confidence_level": (
                    conf.get("level")
                    if isinstance(conf, dict) and conf.get("level")
                    else "High"
                    if confidence_value >= 0.8
                    else "Medium"
                    if confidence_value >= 0.55
                    else "Low"
                ),
                "database_match": bool(result.get("database_match")),
                "aisc_confirmed": bool(result.get("database_match")),
                "model_probability": explanation.get("ai_probability"),
                "regex_confidence": explanation.get("regex_contribution"),
                "review_status": result.get("review_status"),
                "explanation": explanation,
                "evidence": result.get("evidence") or {},
                "geometry_preview": geometry,
                "graph_preview": result.get("graph_preview"),
                "features": features,
            }
        )

    gt = parse_ground_truth_excel(excel_path)
    evaluation = evaluate_against_excel(predictions, ground_truth=gt)
    if persist_report:
        persist_evaluation_report(
            evaluation,
            pdf_name=pdf_path.name,
            excel_name=excel_path.name,
        )

    # Legacy comparison shape for existing UI consumers.
    comparisons = []
    for row in evaluation.get("comparisons") or []:
        status = row.get("status")
        if status == "extra_member":
            status = "unknown_entity"
        comparisons.append(
            {
                "label": row.get("section"),
                "prediction": row.get("predicted_quantity"),
                "ground_truth": row.get("expected_quantity"),
                "difference": row.get("quantity_difference"),
                "status": status,
                "entity_class": row.get("entity_class"),
                "match": status == "match",
                "predicted_length": row.get("predicted_length"),
                "expected_length": row.get("expected_length"),
                "length_match": row.get("length_match"),
                "predicted_weight": row.get("predicted_weight"),
                "expected_weight": row.get("expected_weight"),
                "weight_match": row.get("weight_match"),
                "member_match": row.get("member_match"),
            }
        )

    summary = dict(evaluation.get("summary") or {})
    metrics = evaluation.get("metrics") or {}
    summary.update(
        {
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            "f1": metrics.get("f1"),
            "quantity_accuracy": metrics.get("quantity_accuracy"),
            "quantity_coverage": metrics.get("quantity_coverage"),
            "length_accuracy": metrics.get("length_accuracy"),
            "weight_accuracy": metrics.get("weight_accuracy"),
            "member_accuracy": metrics.get("member_accuracy"),
            "missing_member": metrics.get("missing_count"),
            "unknown_entity": metrics.get("extra_count"),
            "issue_count": int(metrics.get("missing_count") or 0)
            + int(metrics.get("extra_count") or 0)
            + int(summary.get("wrong_quantity") or 0),
        }
    )

    pair_id = None
    dataset_build = None
    if auto_register_pair:
        pair_id = _register_uploaded_pair(pdf_path, excel_path)
    if auto_build_dataset:
        dataset_build = _auto_build_dataset(pair_id)

    return {
        "pipeline": "excel_ground_truth_evaluation",
        "pdf_file": pdf_path.name,
        "excel_file": excel_path.name,
        "excel_role": "ground_truth_only",
        "excel_is_prediction": False,
        "pdf_pages": multimodal.get("summary", {}).get("pages", 0),
        "prediction_count": len(pred_rows),
        "ground_truth_unique": gt.get("unique_labels"),
        "summary": summary,
        "metrics": metrics,
        "evaluation": evaluation,
        "comparisons": comparisons,
        "missing_elements": evaluation.get("missing_elements") or [],
        "extra_elements": evaluation.get("extra_elements") or [],
        "classification_errors": [],
        "predictions": pred_rows,
        "ground_truth": gt.get("aggregates") or [],
        "ground_truth_detail": gt,
        "multimodal_validation": multimodal.get("validation"),
        "inference_time_ms": multimodal.get("summary", {}).get("inference_time_ms"),
        "extraction_summary": multimodal.get("summary") or {},
        "report_path": evaluation.get("report_path"),
        "markdown_report_path": evaluation.get("markdown_report_path"),
        "registered_pair_id": pair_id,
        "dataset_build": dataset_build,
        "document_id": multimodal.get("document_id"),
    }


def validate_pair(pair_id: str) -> Dict[str, Any]:
    from services.takeoff.paired_dataset_builder import list_training_pairs

    for pair in list_training_pairs():
        if pair["id"] == pair_id and pair.get("ready"):
            return validate_takeoff(
                pdf_path=pair["pdf_path"],
                excel_path=pair["excel_path"],
                auto_register_pair=False,
                auto_build_dataset=False,
            )
    raise FileNotFoundError(f"Training pair not ready: {pair_id}")
