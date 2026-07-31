"""Backward-compatible upload-only endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from config import settings
from services.document_registry import register_document
from services.upload_service import PDF_SUFFIXES, save_upload


router = APIRouter()


# Both paths avoid FastAPI's trailing-slash redirect through the dev proxy.
@router.post("", include_in_schema=False, status_code=201)
@router.post("/", status_code=201)
async def upload_pdf(file: UploadFile = File(...)):
    """
    Validate and store a drawing.

    Extraction, geometry, graph construction, prediction, and validation are
    deliberately excluded. Clients continue with
    ``POST /api/documents/{document_id}/extract``.
    """

    original_name = Path(file.filename or "drawing.pdf").name
    source = await save_upload(
        file,
        settings.uploads_dir,
        allowed_suffixes=PDF_SUFFIXES,
        field="file",
    )
    try:
        document = register_document(source, original_name=original_name)
    except ValueError as exc:
        source.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        **document,
        # Stable compatibility fields for older upload clients. They make the
        # absence of analysis explicit instead of fabricating empty results.
        "filename": document["source_file"],
        "pages": document["page_count"],
        "token_count": None,
        "results": None,
        "summary": {
            "stage": "uploaded",
            "analysis_started": False,
            "next_action": "extract",
        },
    }
