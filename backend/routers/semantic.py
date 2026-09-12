"""Semantic preprocessor API -- upstream text semantics for a document.

Thin HTTP transport only; all logic lives in
``services.semantic_document_service`` / ``services.semantic_preprocessor``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.document_registry import document_source
from services.semantic_document_service import (
    apply_review_action,
    document_summary,
    get_cached_semantic_document,
    list_review_queue,
    run_semantic_pipeline,
)

router = APIRouter()


@router.post("/documents/{document_id}/semantic")
def process_semantic(document_id: str, force: bool = Query(False)):
    try:
        document_source(document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        document = run_semantic_pipeline(document_id, force=force)
    except Exception as exc:  # pragma: no cover - defensive: surface as 500, not a crash
        raise HTTPException(status_code=500, detail=f"Semantic processing failed: {exc}") from exc
    return {"document": document, "summary": document_summary(document)}


@router.get("/documents/{document_id}/semantic")
def get_semantic(document_id: str):
    document = get_cached_semantic_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No semantic result cached for this document yet")
    return {"document": document, "summary": document_summary(document)}


@router.get("/documents/{document_id}/semantic/review-queue")
def get_review_queue(document_id: str):
    return {"items": list_review_queue(document_id)}


class ReviewActionRequest(BaseModel):
    action: str  # "accept" | "reject" | "edit"
    edited_text: Optional[str] = None


@router.patch("/documents/{document_id}/semantic/annotations/{annotation_id}/review")
def review_annotation(document_id: str, annotation_id: str, body: ReviewActionRequest):
    try:
        annotation = apply_review_action(
            document_id, annotation_id, body.action, body.edited_text
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"annotation": annotation}
