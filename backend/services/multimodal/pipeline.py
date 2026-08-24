"""End-to-end AI-first multimodal structural prediction pipeline."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings
from services.artifact_store import prune_documents, write_artifact
from services.dataset_manager import dataset_manager
from services.engineering.geometry_adapters import (
    extract_geometry_document,
    geometry_capabilities,
)
from services.engineering.rule_engine import evaluate_document_rules
from services.engineering.structural_graph import build_structural_graph
from services.extraction_engine import extract_engineering_document
from services.multimodal.duplicate_detector import merge_duplicate_predictions
from services.multimodal.fusion_engine import fusion_engine
from services.multimodal.geometry_ai import enrich_geometry_embeddings
from services.multimodal.graph_ai import enrich_graph_embeddings
from services.multimodal.label_propagation import propagate_section_labels
from services.multimodal.review_enrichment import index_predictions
from services.multimodal.schedule_ingestion import build_schedule_tokens
from services.multimodal.spatial_association import build_spatial_association_tokens
from services.multimodal.validation_engine import (
    validate_multimodal_predictions,
)
from services.engineering.detail_regions import assign_detail_regions
from services.annotation.context_evidence import attach_context_evidence
from services.prediction.contract import confidence_overall
from services.takeoff.ground_truth_excel import parse_ground_truth_excel


# Bumped whenever prediction behaviour changes, so cached analyses are replaced.
PIPELINE_VERSION = "4.10-context-quality"


def _neural_model_status() -> Dict[str, Any]:
    """Report which learned modules are trained, and the active fallback."""

    geometry_trained = settings.geometry_embedding_index_path.exists()
    graph_trained = settings.graphsage_model_path.exists()
    fusion_trained = settings.fusion_model_path.exists()
    return {
        "geometry_model": (
            "mobilenet_v3_small_embedding_index"
            if geometry_trained
            else "vector_geometry_fallback"
        ),
        "graph_model": "graphsage" if graph_trained else "structural_rules_fallback",
        "fusion_model": (
            "candidate_fusion_mlp" if fusion_trained else "attention_fallback"
        ),
        "confidence_calibration": (
            "temperature_scaling" if fusion_trained else "attention_confidence"
        ),
    }


def _missing_label_tokens(
    geometry: Dict[str, Any],
    graph: Dict[str, Any],
) -> list[dict]:
    """Create inference records only when trained geometry and graph models agree."""

    graph_features = graph.get("source_features") or {}
    records = []
    for obj in geometry.get("objects") or []:
        geometry_id = str(obj.get("geometry_id") or "")
        learned_graph = graph_features.get(geometry_id) or {}
        candidates = obj.get("geometry_candidates") or []
        role_confidence = float(
            obj.get("geometry_role_confidence")
            or obj.get("geometry_confidence")
            or 0.0
        )
        if (
            not geometry_id
            or obj.get("nearby_text")
            or (not candidates and role_confidence < 0.55)
            or role_confidence < 0.55
            or float(learned_graph.get("missing_label_probability") or 0.0)
            < 0.50
        ):
            continue
        records.append(
            {
                "token_id": geometry_id,
                "text": "",
                "raw_text": "",
                "corrected_text": "",
                "normalized_text": "",
                "page": obj.get("page_number"),
                "bbox": obj.get("bbox"),
                "confidence": 0.0,
                "engineering_object_type": learned_graph.get("graph_prediction")
                or obj.get("geometry_role"),
                "missing_label": True,
                "extraction_method": "geometry_inference",
            }
        )
    return records


def _merge_audit(deduped: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge provenance only.

    ``merge_duplicate_predictions`` also returns the surviving predictions, so
    persisting its raw output stored every prediction a second time.
    """

    return {
        "duplicate_count": deduped.get("duplicate_count", 0),
        "merges": deduped.get("merges") or [],
    }


def run_multimodal_pipeline(
    source_path: str | Path,
    *,
    expected_excel_path: Optional[str | Path] = None,
    persist: bool = True,
    document_structure: Optional[Dict[str, Any]] = None,
    geometry_document: Optional[Dict[str, Any]] = None,
    graph_document: Optional[Dict[str, Any]] = None,
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse, fuse, predict, correct, explain, and validate one engineering file.

    Architecture:
      PDF → extraction → geometry → graph → rules → AI fusion →
      database verification → validation → review enrichment
    """

    path = Path(source_path)
    pipeline_started = time.perf_counter()
    timings: Dict[str, float] = {}
    if path.suffix.lower() != ".pdf":
        extract_geometry_document(path)
        raise ValueError("Text extraction currently requires a PDF source")

    stage_started = time.perf_counter()
    document = document_structure or extract_engineering_document(
        path, document_id=document_id
    )
    if document_id:
        document["document_id"] = document_id
    timings["extraction_ms"] = (
        0.0
        if document_structure is not None
        else round((time.perf_counter() - stage_started) * 1000, 2)
    )

    stage_started = time.perf_counter()
    geometry = geometry_document or extract_geometry_document(
        path, document_structure=document
    )
    geometry = enrich_geometry_embeddings(path, geometry)
    timings["geometry_ms"] = (
        0.0
        if geometry_document is not None
        else round((time.perf_counter() - stage_started) * 1000, 2)
    )

    stage_started = time.perf_counter()
    graph = graph_document or build_structural_graph(document, geometry)
    graph = enrich_graph_embeddings(graph)
    document_rules = evaluate_document_rules(graph)
    if settings.detail_regions_enabled:
        assign_detail_regions(document, geometry)
    attach_context_evidence(document, geometry, graph)
    timings["graph_rules_ms"] = round(
        (time.perf_counter() - stage_started) * 1000, 2
    )
    expected = (
        parse_ground_truth_excel(expected_excel_path)
        if expected_excel_path
        else None
    )

    stage_started = time.perf_counter()
    raw_predictions = []
    prediction_tokens = list(document.get("engineering_tokens") or [])
    if settings.schedule_ingestion_enabled:
        schedule_tokens = build_schedule_tokens(document, existing_tokens=prediction_tokens)
        prediction_tokens.extend(schedule_tokens)
        document["schedule_tokens_added"] = len(schedule_tokens)
    if settings.spatial_association_enabled:
        spatial_tokens = build_spatial_association_tokens(
            document,
            geometry,
            existing_tokens=prediction_tokens,
        )
        prediction_tokens.extend(spatial_tokens)
        document["spatial_association_tokens_added"] = len(spatial_tokens)
    prediction_tokens.extend(_missing_label_tokens(geometry, graph))
    for token in prediction_tokens:
        raw_predictions.append(
            fusion_engine.predict(
                {
                    "token": token,
                    "document": document,
                    "geometry": geometry,
                    "graph": graph,
                    "expected_excel": expected,
                    "source_file": path.name,
                }
            ).to_dict()
        )
    timings["prediction_ms"] = round(
        (time.perf_counter() - stage_started) * 1000, 2
    )

    deduped = merge_duplicate_predictions(raw_predictions)
    predictions = propagate_section_labels(deduped["predictions"], graph)

    # Human review is driven by multimodal confidence/conflicts, never by a
    # database miss alone.
    for prediction in predictions:
        if prediction.get("review_status") != "pending_review":
            continue
        if prediction.get("_skip_unknown_queue"):
            continue
        text_features = (prediction.get("features") or {}).get("text") or {}
        confidence_value = confidence_overall(prediction.get("confidence"))
        section = (
            prediction.get("section")
            or prediction.get("predicted_shape")
            or prediction.get("prediction")
            or ""
        )
        queued = dataset_manager.enqueue_unknown(
            token=prediction.get("original_token") or "",
            prediction=section,
            model_probability=text_features.get("model_probability") or 0.0,
            overall_confidence=confidence_value,
            confidence_level=(
                "High"
                if confidence_value >= 0.8
                else "Medium"
                if confidence_value >= 0.55
                else "Low"
            ),
            uncertain=True,
            source_file=path.name,
            regex_suggested="",
            category=prediction.get("entity_type") or "",
        )
        prediction["unknown_id"] = queued.get("id") if queued else None
        prediction["review_status"] = (
            "queued" if prediction["unknown_id"] else "pending_review"
        )

    validation = validate_multimodal_predictions(
        predictions,
        expected_excel=expected,
        extraction={
            "quality": document.get("extraction_quality"),
            "diagnostics": document.get("extraction_diagnostics"),
            "dimensions": document.get("dimensions") or [],
            "tables": document.get("tables") or [],
            "schedules": document.get("schedules") or [],
        },
    )
    excel_evaluation = None
    if expected:
        from services.takeoff.ground_truth_evaluation import (
            evaluate_against_excel,
            persist_evaluation_report,
        )

        excel_evaluation = evaluate_against_excel(
            predictions, ground_truth=expected
        )
        if persist:
            persist_evaluation_report(
                excel_evaluation,
                pdf_name=path.name,
                excel_name=str(
                    Path(expected_excel_path).name if expected_excel_path else ""
                ),
            )
        validation["excel_ground_truth"] = excel_evaluation
    validation["document_rules"] = document_rules
    validation["duplicates"] = {
        "merged": deduped["duplicate_count"],
        "merges": deduped["merges"],
    }
    timings["total_ms"] = round(
        (time.perf_counter() - pipeline_started) * 1000, 2
    )
    if persist:
        index_predictions(path.name, predictions)
    document_id = document["document_id"]
    artifacts: Dict[str, str] = {}
    if persist:
        prune_documents()
        written = {
            # A document supplied by the extraction stage is already stored;
            # rewriting it would re-serialize tens of megabytes per analysis.
            "document": (
                write_artifact(document_id, "document.json", document)
                if document_structure is None
                else None
            ),
            "geometry": write_artifact(document_id, "geometry.json", geometry),
            "graph": write_artifact(document_id, "graph.json", graph),
            "predictions": write_artifact(
                document_id,
                "predictions.json",
                {
                    "predictions": predictions,
                    "duplicates": _merge_audit(deduped),
                },
            ),
            "validation": write_artifact(
                document_id, "validation.json", validation
            ),
        }
        if expected:
            written["expected_excel"] = write_artifact(
                document_id, "expected_excel.json", expected
            )
        artifacts = {name: path for name, path in written.items() if path}

    validation_summary = validation["summary"]
    expected_counts = validation.get("expected_counts") or {}
    predicted_counts = validation.get("predicted_counts") or {}
    missing_components = sum(
        max(0, int(quantity) - int(predicted_counts.get(label, 0)))
        for label, quantity in expected_counts.items()
    )
    extra_components = sum(
        max(0, int(quantity) - int(expected_counts.get(label, 0)))
        for label, quantity in predicted_counts.items()
    ) if expected_counts else 0
    corrected_count = sum(
        str(item.get("original_token") or "").upper().replace(" ", "")
        != str(item.get("corrected_token") or "").upper().replace(" ", "")
        for item in predictions
    )
    review_needed = sum(
        item.get("review_status") in {"pending_review", "queued"}
        for item in predictions
    )
    validation_score = round(
        (
            validation_summary.get("pass", 0)
            + 0.5 * validation_summary.get("warning", 0)
        )
        / max(validation_summary.get("total", 0), 1),
        4,
    )

    return {
        "schema_version": "2.0",
        "pipeline": "text_geometry_graph_fusion",
        "architecture": "modular_multimodal_attention_ai_first",
        "document_id": document_id,
        "source_file": path.name,
        "summary": {
            "pages": document.get("page_count"),
            "text_length": document.get("text_length"),
            "tokens": len(predictions),
            "raw_tokens": len(raw_predictions),
            "duplicates_merged": deduped["duplicate_count"],
            "components_found": len(predictions),
            "ocr_corrections": corrected_count,
            "missing_components": missing_components,
            "extra_components": extra_components,
            "review_needed": review_needed,
            "validation_score": validation_score,
            "takeoff_accuracy": (
                validation_summary.get("pass_rate")
                if expected_counts
                else None
            ),
            "inference_time_ms": timings["total_ms"],
            "geometry_objects": geometry.get("geometry_count"),
            "graph_nodes": graph.get("stats", {}).get("node_count"),
            "graph_edges": graph.get("stats", {}).get("edge_count"),
            "tables": len(document.get("tables") or []),
            "title_blocks": len(document.get("title_blocks") or []),
            "excel_precision": (
                (excel_evaluation or {}).get("metrics", {}).get("precision")
                if excel_evaluation
                else None
            ),
            "excel_recall": (
                (excel_evaluation or {}).get("metrics", {}).get("recall")
                if excel_evaluation
                else None
            ),
            "excel_quantity_accuracy": (
                (excel_evaluation or {}).get("metrics", {}).get("quantity_accuracy")
                if excel_evaluation
                else None
            ),
            **validation["summary"],
        },
        "extraction": {
            "quality": document.get("extraction_quality"),
            "diagnostics": document.get("extraction_diagnostics"),
            "tokens": document.get("engineering_tokens") or [],
            "tables": document.get("tables") or [],
            "schedules": document.get("schedules") or [],
            "title_blocks": document.get("title_blocks") or [],
            "callouts": document.get("callouts") or [],
            "dimensions": document.get("dimensions") or [],
            "annotations": document.get("annotations") or [],
        },
        "geometry": geometry,
        "graph": graph,
        "document_rules": document_rules,
        "predictions": predictions,
        "validation": validation,
        "excel_evaluation": excel_evaluation,
        "performance": timings,
        "expected_excel": expected,
        "excel_role": "ground_truth_only" if expected else None,
        "excel_is_prediction": False,
        "policy": {
            "ai_predicts": True,
            "database_decides_prediction": False,
            "database_role": "verification_only",
            "pipeline_version": PIPELINE_VERSION,
            **_neural_model_status(),
        },
        "capabilities": {
            "geometry_adapters": geometry_capabilities(),
            "future_models": [
                "LayoutLMv3",
                "Donut",
                "ViT",
                "YOLO",
                "SAM",
                "PointNet",
                "Point Transformer",
                "GCN",
                "GraphSAGE",
            ],
        },
        "artifacts": artifacts,
    }
