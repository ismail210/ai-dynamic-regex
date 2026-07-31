"""Document-id driven extraction and multimodal analysis stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from services.artifact_store import read_artifact, write_artifact
from services.document_registry import (
    document_source,
    get_document,
    update_document,
)
from services.dataset_manager import dataset_manager
from services.extraction_engine import (
    extract_engineering_document,
    extraction_response,
)
from services.multimodal.pipeline import run_multimodal_pipeline


def _analysis_metadata(result: Dict[str, Any]) -> Dict[str, Any]:
    """Persist only fields not already stored in the stage artifacts."""

    return {
        key: value
        for key, value in result.items()
        if key
        not in {
            "extraction",
            "geometry",
            "graph",
            "predictions",
            "validation",
            "expected_excel",
        }
    }


def _cached_analysis(document_id: str) -> Optional[Dict[str, Any]]:
    document = read_artifact(document_id, "document.json")
    geometry = read_artifact(document_id, "geometry.json")
    graph = read_artifact(document_id, "graph.json")
    prediction_artifact = read_artifact(document_id, "predictions.json")
    validation = read_artifact(document_id, "validation.json")
    metadata = read_artifact(document_id, "analysis.json")
    if not all(
        item is not None
        for item in (
            document,
            geometry,
            graph,
            prediction_artifact,
            validation,
            metadata,
        )
    ):
        return None
    predictions = prediction_artifact.get("predictions") or []
    return {
        **metadata,
        "extraction": extraction_response(document),
        "geometry": geometry,
        "graph": graph,
        "predictions": predictions,
        "validation": validation,
        "cached": True,
    }


def run_extraction_stage(
    document_id: str,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Extract engineering objects exactly once for a registered document."""

    source = document_source(document_id)
    cached = None if force else read_artifact(document_id, "document.json")
    if cached is not None:
        update_document(
            document_id,
            stage="extracted",
            extraction_artifact="document.json",
        )
        return {**extraction_response(cached), "cached": True}

    update_document(document_id, stage="extracting")
    try:
        document = extract_engineering_document(
            source, document_id=document_id
        )
        artifact = write_artifact(document_id, "document.json", document)
        if artifact is None:
            raise OSError("Extraction artifact could not be stored")
        update_document(
            document_id,
            stage="extracted",
            extraction_artifact="document.json",
            engineering_object_count=len(
                document.get("engineering_tokens") or []
            ),
        )
        return {**extraction_response(document), "cached": False}
    except Exception as exc:
        update_document(document_id, stage="failed", error=str(exc))
        raise


def run_analysis_stage(
    document_id: str,
    *,
    expected_excel_path: Optional[str | Path] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Run geometry, graph, fusion, correction, and validation after extraction."""

    manifest = get_document(document_id)
    document = read_artifact(document_id, "document.json")
    if document is None or manifest.get("stage") not in {
        "extracted",
        "analyzing",
        "analyzed",
        "failed",
    }:
        raise RuntimeError("Extraction must complete before analysis starts")

    if not force and expected_excel_path is None:
        cached = _cached_analysis(document_id)
        if cached is not None:
            update_document(document_id, stage="analyzed")
            return cached

    source = document_source(document_id)
    geometry = None if force else read_artifact(document_id, "geometry.json")
    graph = None if force else read_artifact(document_id, "graph.json")
    update_document(document_id, stage="analyzing")
    try:
        result = run_multimodal_pipeline(
            source,
            expected_excel_path=expected_excel_path,
            persist=True,
            document_structure=document,
            geometry_document=geometry,
            graph_document=graph,
            document_id=document_id,
        )
        write_artifact(
            document_id, "analysis.json", _analysis_metadata(result)
        )
        predictions = result.get("predictions") or []
        known = sum(bool(item.get("database_match")) for item in predictions)
        uncertain = sum(
            item.get("review_status") in {"pending_review", "queued"}
            for item in predictions
        )
        dataset_manager.log_upload(
            str(manifest.get("source_file") or source.name),
            result.get("summary", {}).get("pages"),
            len(predictions),
            known,
            max(0, len(predictions) - known),
            uncertain,
        )
        update_document(
            document_id,
            stage="analyzed",
            analysis_artifact="analysis.json",
            prediction_count=len(result.get("predictions") or []),
        )
        return {**result, "cached": False}
    except Exception as exc:
        update_document(document_id, stage="failed", error=str(exc))
        raise
