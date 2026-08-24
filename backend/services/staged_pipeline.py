"""Document-id driven extraction and multimodal analysis stages."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings
from services.artifact_store import read_artifact, write_artifact
from services.document_registry import (
    document_source,
    get_document,
    update_document,
)
from services.dataset_manager import dataset_manager
from services.engineering.structural_graph import graph_matches_document
from services.extraction_engine import (
    EXTRACTION_VERSION,
    extract_engineering_document,
    extraction_response,
)
from services.human_selections import (
    apply_human_selection_overlay,
    get_human_selection_entries,
)
from services.multimodal.pipeline import PIPELINE_VERSION, run_multimodal_pipeline
from services.prediction.hss_review_enrichment import (
    enrich_missing_thickness_hss_predictions,
)

logger = logging.getLogger("takeoff.stages")


def _analysis_fingerprint() -> str:
    """Identify the code and model state that produced an analysis.

    Cached artifacts are only replayed when extraction, pipeline, and neural
    model versions all match, so retrained models or code changes take effect
    on the next run instead of returning a stale result.
    """

    parts = [EXTRACTION_VERSION, PIPELINE_VERSION]
    for path in (
        settings.geometry_embedding_index_path,
        settings.graphsage_model_path,
        settings.fusion_model_path,
    ):
        stamp = int(path.stat().st_mtime) if path.exists() else 0
        parts.append(f"{path.name}:{stamp}")
    return "|".join(parts)


def _analysis_metadata(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist only fields not already stored in the stage artifacts.

    Geometry and graph are reduced to their digests here so replaying a cached
    analysis never has to parse the multi-megabyte geometry and graph
    documents just to answer the API contract.
    """

    metadata = {
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
    metadata["geometry"] = _geometry_digest(result.get("geometry") or {})
    metadata["graph"] = _graph_digest(result.get("graph") or {})
    metadata["pipeline_fingerprint"] = _analysis_fingerprint()
    return metadata


def _geometry_digest(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize the geometry document instead of shipping every object."""

    return {
        "source_file": geometry.get("source_file"),
        "source_format": geometry.get("source_format"),
        "units": geometry.get("units"),
        "geometry_count": geometry.get("geometry_count")
        or len(geometry.get("objects") or []),
        "counts_by_kind": geometry.get("counts_by_kind") or {},
        "page_summaries": (geometry.get("metadata") or {}).get("page_summaries")
        or [],
        "geometry_ai": geometry.get("geometry_ai") or {},
        "artifact": "geometry.json",
    }


def _graph_digest(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize the structural graph; the full graph stays an artifact."""

    return {
        "stats": graph.get("stats") or {},
        "schema": graph.get("schema") or {},
        "graph_ai": graph.get("graph_ai") or {},
        "artifact": "graph.json",
    }


def analysis_response(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project one analysis onto the API contract.

    Geometry and graph documents plus per-prediction training feature bundles
    are tens of megabytes and no page consumes them, so they stay in the
    artifacts (downloadable through ``/artifacts/{name}``) and are summarized
    here. Sending them made a finished analysis look like a hung request.
    """

    predictions = [
        {key: value for key, value in prediction.items() if key != "features"}
        for prediction in enrich_missing_thickness_hss_predictions(
            result.get("predictions") or []
        )
    ]
    return {
        **result,
        "geometry": _geometry_digest(result.get("geometry") or {}),
        "graph": _graph_digest(result.get("graph") or {}),
        "predictions": predictions,
    }


def _current_document(document_id: str) -> Optional[Dict[str, Any]]:
    """Read the cached document only when it matches the extraction contract."""

    document = read_artifact(document_id, "document.json")
    if document is None:
        return None
    if str(document.get("extraction_version") or "") != EXTRACTION_VERSION:
        return None
    return document


def _write_extraction_view(document: Dict[str, Any]) -> Optional[str]:
    """
    Store the extraction API projection next to the raw document.

    ``document.json`` holds every word, line, and block of the drawing and is
    tens of megabytes; parsing it on each request to rebuild a ~1 MB response
    dominated the response time of every page that reloads a document.

    Returns the written path, or ``None`` when the cache write was skipped.
    """

    view = {
        **extraction_response(document),
        "extraction_version": EXTRACTION_VERSION,
    }
    return write_artifact(
        str(document.get("document_id") or ""), "extraction.json", view
    )


def load_cached_extraction(document_id: str) -> Optional[Dict[str, Any]]:
    """Return the persisted extraction without starting extraction."""

    view = read_artifact(document_id, "extraction.json")
    if view is not None and str(view.get("extraction_version") or "") == EXTRACTION_VERSION:
        return view
    document = _current_document(document_id)
    if document is None:
        return None
    _write_extraction_view(document)
    return {
        **extraction_response(document),
        "extraction_version": EXTRACTION_VERSION,
    }


def _apply_human_selections(
    document_id: str, predictions: list[Dict[str, Any]]
) -> list[Dict[str, Any]]:
    """
    Overlay reviewer-selected sections (services.human_selections) onto
    served predictions, so a resolved missing-thickness (or similar
    catalog-candidate) ambiguity stays resolved across a refresh instead of
    the served prediction reverting to its pre-review "select a candidate"
    state. The underlying analysis.json/predictions_view.json artifacts are
    NOT rewritten -- this applies on every read, keeping the raw model
    output and the human decision in separate, honest places.
    """

    selections = get_human_selection_entries(document_id)
    if not selections:
        return predictions

    updated = []
    for prediction in predictions:
        object_id = str(prediction.get("object_id") or "")
        entry = selections.get(object_id)
        if not entry:
            updated.append(prediction)
            continue
        section = str(entry.get("section") or "")
        semantic_type = str(entry.get("semantic_type") or "")
        updated.append(
            apply_human_selection_overlay(
                prediction, section, semantic_type=semantic_type
            )
        )
    return updated


def load_cached_analysis(document_id: str) -> Optional[Dict[str, Any]]:
    """
    Return the persisted analysis without running inference.

    Only projected artifacts are read: the fingerprint is verified first, and
    geometry, graph, and per-prediction training features stay on disk because
    no page consumes them.
    """

    metadata = read_artifact(document_id, "analysis.json")
    if metadata is None:
        return None
    if str(metadata.get("pipeline_fingerprint") or "") != _analysis_fingerprint():
        return None
    extraction = load_cached_extraction(document_id)
    prediction_view = read_artifact(document_id, "predictions_view.json")
    validation = read_artifact(document_id, "validation.json")
    if extraction is None or prediction_view is None or validation is None:
        return None
    return {
        **metadata,
        "extraction": extraction,
        "predictions": _apply_human_selections(
            document_id,
            enrich_missing_thickness_hss_predictions(
                prediction_view.get("predictions") or []
            ),
        ),
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
    cached = None if force else _current_document(document_id)
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
        view_path = _write_extraction_view(document)
        if artifact is None and view_path is None:
            # Extraction itself succeeded; only the disk cache failed. Return
            # the live response so the UI is not blocked by a full volume.
            logger.warning(
                "extraction for %s succeeded in memory but could not be cached",
                document_id,
            )
        update_document(
            document_id,
            stage="extracted",
            extraction_artifact=(
                "document.json"
                if artifact
                else ("extraction.json" if view_path else None)
            ),
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

    document = _current_document(document_id)
    stale_extraction = document is None
    if stale_extraction:
        # Cached extraction predates the current contract. Rebuild it so
        # analysis never runs on an outdated document, geometry, or graph.
        run_extraction_stage(document_id, force=True)
        document = _current_document(document_id)
    manifest = get_document(document_id)
    if document is None or manifest.get("stage") not in {
        "extracted",
        "analyzing",
        "analyzed",
        "failed",
    }:
        raise RuntimeError("Extraction must complete before analysis starts")

    if not force and expected_excel_path is None:
        cached = load_cached_analysis(document_id)
        if cached is not None:
            update_document(document_id, stage="analyzed")
            return cached

    source = document_source(document_id)
    reuse_stage_artifacts = not force and not stale_extraction
    geometry = (
        read_artifact(document_id, "geometry.json")
        if reuse_stage_artifacts
        else None
    )
    graph = (
        read_artifact(document_id, "graph.json") if reuse_stage_artifacts else None
    )
    if graph is not None and not graph_matches_document(graph, document):
        # Token ids are positional, so a graph cached before the current
        # extraction covers a different id space; reusing it would leave those
        # tokens with no structural neighborhood.
        logger.info(
            "Rebuilding graph for %s: cached graph predates current token ids",
            document_id,
        )
        graph = None
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
        response = analysis_response({**result, "cached": False})
        # The projected predictions are what every page reads, so they are
        # cached separately from the training feature bundles.
        write_artifact(
            document_id,
            "predictions_view.json",
            {"predictions": response.get("predictions") or []},
        )
        return response
    except Exception as exc:
        update_document(document_id, stage="failed", error=str(exc))
        raise
