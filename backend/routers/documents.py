"""Staged document workflow API."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from config import settings
from services.artifact_store import artifact_path
from services.document_registry import (
    document_source,
    get_document,
    public_document,
    register_document,
)
from services.stage_runner import run_shared_stage
from services.staged_pipeline import (
    load_cached_analysis,
    load_cached_extraction,
    run_analysis_stage,
    run_extraction_stage,
)
from services.upload_service import (
    EXCEL_SUFFIXES,
    PDF_SUFFIXES,
    run_analysis,
    save_upload,
)


router = APIRouter()
_ARTIFACTS = {
    "document.json",
    "extraction.json",
    "geometry.json",
    "graph.json",
    "predictions.json",
    "predictions_view.json",
    "validation.json",
    "analysis.json",
    "expected_excel.json",
}


@router.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)):
    """Validate and store a PDF. No extraction or AI work occurs here."""

    original_name = Path(file.filename or "drawing.pdf").name
    source = await save_upload(
        file,
        settings.uploads_dir,
        allowed_suffixes=PDF_SUFFIXES,
        field="file",
    )
    try:
        return register_document(source, original_name=original_name)
    except ValueError as exc:
        source.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/documents/{document_id}")
def document_status(document_id: str):
    try:
        return public_document(get_document(document_id))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/documents/{document_id}/extract")
async def extract_document(
    document_id: str,
    force: bool = Query(False),
):
    try:
        document_source(document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await run_shared_stage(
        stage="document extraction",
        document_id=document_id,
        runner=lambda: run_analysis(
            "document extraction",
            run_extraction_stage,
            document_id,
            force=force,
        ),
    )


@router.get("/documents/{document_id}/extraction")
def document_extraction(document_id: str):
    result = load_cached_extraction(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return result


@router.post("/documents/{document_id}/analyze")
async def analyze_document(
    document_id: str,
    excel: Optional[UploadFile] = File(None),
    force: bool = Query(False),
):
    try:
        document_source(document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    excel_path = None
    if excel is not None and excel.filename:
        excel_path = await save_upload(
            excel,
            settings.uploads_dir,
            allowed_suffixes=EXCEL_SUFFIXES,
            field="excel",
        )
    return await run_shared_stage(
        stage="multimodal document analysis",
        document_id=document_id,
        runner=lambda: run_analysis(
            "multimodal document analysis",
            run_analysis_stage,
            document_id,
            expected_excel_path=excel_path,
            force=force,
        ),
    )


@router.get("/documents/{document_id}/analysis")
def document_analysis(document_id: str):
    result = load_cached_analysis(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@router.get("/documents/{document_id}/artifacts/{name}")
def document_artifact(document_id: str, name: str):
    if name not in _ARTIFACTS:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    try:
        path = artifact_path(document_id, name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path)
