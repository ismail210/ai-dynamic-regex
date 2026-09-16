"""Semantic preprocessor API -- upstream text semantics for a document.

Thin HTTP transport only; all logic lives in
``services.semantic_document_service`` / ``services.semantic_preprocessor``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.document_registry import document_source
from services.semantic_document_service import (
    accept_all_eligible_corrections,
    apply_review_action,
    document_summary,
    export_corrected_pdf,
    get_annotation_oracle,
    get_benchmark_context,
    get_cached_semantic_document,
    list_review_queue,
    run_semantic_pipeline,
)
from services.semantic.corrected_pdf import list_accepted_text_corrections, sync_corrected_pdf

router = APIRouter()


def _sync_corrected_pdf_safe(document_id: str, document: dict) -> None:
    """Background rebuild — never raise into the ASGI worker."""
    try:
        sync_corrected_pdf(document_id, document)
    except Exception:
        pass


@router.post("/documents/{document_id}/semantic")
def process_semantic(
    document_id: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(False),
):
    try:
        document_source(document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        document = run_semantic_pipeline(document_id, force=force)
    except Exception as exc:  # pragma: no cover - defensive: surface as 500, not a crash
        raise HTTPException(status_code=500, detail=f"Semantic processing failed: {exc}") from exc
    # Do not block Process on a full corrected-PDF rebuild (multi-page sets
    # with many auto-normalizations can take minutes). Overlays show accepted
    # text immediately; warm the derived PDF in the background when needed.
    summary = document_summary(document, document_id=document_id)
    if list_accepted_text_corrections(document):
        background_tasks.add_task(_sync_corrected_pdf_safe, document_id, document)
    return {"document": document, "summary": summary}


@router.get("/documents/{document_id}/semantic")
def get_semantic(document_id: str):
    """Return the cached semantic result, or a quiet not-ready payload.

    Unprocessed-but-registered documents must NOT 404: the Semantic Review
    page always GETs on mount, and a 404 floods the browser console even
    though "not processed yet" is the normal empty state. Unknown document
    ids still 404 via ``document_source``.
    """
    try:
        document_source(document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    document = get_cached_semantic_document(document_id)
    if document is None:
        return {"document": None, "summary": None, "status": "not_ready"}
    return {
        "document": document,
        "summary": document_summary(document, document_id=document_id),
        "status": "ready",
    }


@router.get("/documents/{document_id}/semantic/review-queue")
def get_review_queue(document_id: str):
    return {"items": list_review_queue(document_id)}


@router.get("/documents/{document_id}/semantic/benchmark")
def get_benchmark(document_id: str):
    """Dev/demo only (Section 20/34/35): None for any ordinary document --
    only non-None when this document is a registered copy of a PDF-attack-
    benchmark attacked file. Never consulted by the repair path itself."""
    return {"benchmark": get_benchmark_context(document_id)}


@router.get("/documents/{document_id}/semantic/annotations/{annotation_id}/oracle")
def get_oracle(document_id: str, annotation_id: str):
    """Dev/demo only: reveals the known-clean answer key for one annotation
    AFTER a review decision, for benchmark cases only (Section 20 -- no
    target leakage into the repair path; this is a separate, dedicated
    endpoint the repair engine never calls)."""
    return {"oracle": get_annotation_oracle(document_id, annotation_id)}


class ReviewActionRequest(BaseModel):
    action: str  # "accept" | "reject" | "edit"
    edited_text: Optional[str] = None
    candidate_text: Optional[str] = None  # which repair_candidates entry "accept" applies to


@router.patch("/documents/{document_id}/semantic/annotations/{annotation_id}/review")
def review_annotation(document_id: str, annotation_id: str, body: ReviewActionRequest):
    try:
        annotation = apply_review_action(
            document_id, annotation_id, body.action, body.edited_text, body.candidate_text
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    document = get_cached_semantic_document(document_id)
    corrected = sync_corrected_pdf(document_id, document) if document else {
        "available": False,
        "revision": "none",
        "correction_count": 0,
        "url": None,
    }
    summary = document_summary(document, document_id=document_id) if document else None
    if summary is not None:
        summary["corrected_pdf"] = corrected
    return {
        "annotation": annotation,
        "summary": summary,
        "corrected_pdf": corrected,
    }


@router.post("/documents/{document_id}/semantic/corrections/accept-all")
def accept_all_corrections(document_id: str):
    """Accept every eligible repair proposal, persist once, rebuild corrected PDF once."""
    try:
        document_source(document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        result = accept_all_eligible_corrections(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/documents/{document_id}/semantic/corrected-pdf")
def download_corrected_pdf(
    document_id: str,
    v: Optional[str] = Query(None, description="Cache-bust revision from summary.corrected_pdf"),
    download: bool = Query(False, description="If true, Content-Disposition: attachment"),
):
    """Serve the derived PDF = original + all accepted semantic corrections.

    Always rebuilds from the persisted semantic state so the bytes match
    the latest Accept decisions. Never overwrites the uploaded original.
    ``v`` is ignored for lookup but required by the viewer for cache busting.
    """
    del v  # used only as a cache-busting query param by the frontend
    try:
        document_source(document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        path, filename, _count = export_corrected_pdf(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Corrected PDF generation failed: {exc}") from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )
