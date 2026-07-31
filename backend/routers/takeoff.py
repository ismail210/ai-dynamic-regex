"""
Takeoff Platform API
====================

Paired PDF+Excel dataset building, takeoff validation, and Excel export.
Keeps existing upload / learning APIs intact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import settings
from services.artifact_store import read_artifact
from services.document_registry import document_source
from services.takeoff.paired_dataset_builder import (
    build_paired_training_dataset,
    list_training_pairs,
)
from services.takeoff.takeoff_exporter import generate_takeoff_excel
from services.takeoff.takeoff_validation import validate_pair
from services.upload_service import run_analysis

router = APIRouter()


class BuildDatasetRequest(BaseModel):
    pair_ids: Optional[List[str]] = Field(default=None)


class GenerateTakeoffRequest(BaseModel):
    document_id: str


@router.get("/takeoff/pairs")
def get_training_pairs():
    return {"pairs": list_training_pairs()}


@router.post("/takeoff/dataset/build")
def build_dataset(body: BuildDatasetRequest = BuildDatasetRequest()):
    try:
        return build_paired_training_dataset(persist=True, pair_ids=body.pair_ids)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/takeoff/dataset/summary")
def dataset_summary():
    meta = settings.training_dir / "paired_dataset_meta.json"
    pairs = list_training_pairs()
    payload = {
        "pairs": pairs,
        "paired_dataset_exists": settings.paired_dataset_path.exists(),
        "paired_dataset_path": str(settings.paired_dataset_path),
    }
    if meta.exists():
        import json

        payload["meta"] = json.loads(meta.read_text(encoding="utf-8"))
    return payload


@router.get("/takeoff/evaluations")
def list_evaluation_reports(limit: int = 20):
    """List automatic Excel ground-truth evaluation reports."""

    root = settings.takeoff_exports_dir
    root.mkdir(parents=True, exist_ok=True)
    files = sorted(
        root.glob("eval_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[: max(1, int(limit))]
    items = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        items.append(
            {
                "filename": path.name,
                "path": str(path),
                "pdf_file": payload.get("pdf_file"),
                "excel_file": payload.get("excel_file"),
                "generated_at": payload.get("generated_at"),
                "metrics": payload.get("metrics") or {},
                "markdown_report_path": payload.get("markdown_report_path"),
            }
        )
    return {"count": len(items), "reports": items}


@router.get("/takeoff/evaluations/{filename}")
def get_evaluation_report(filename: str):
    path = settings.takeoff_exports_dir / Path(filename).name
    if not path.exists() or not path.name.startswith("eval_"):
        raise HTTPException(status_code=404, detail="Evaluation report not found")
    if path.suffix.lower() == ".md":
        return FileResponse(path, media_type="text/markdown", filename=path.name)
    return FileResponse(path, media_type="application/json", filename=path.name)


@router.get("/takeoff/validate/{pair_id}")
def validate_training_pair(pair_id: str):
    try:
        return validate_pair(pair_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/takeoff/generate")
async def generate_takeoff(body: GenerateTakeoffRequest):
    prediction_artifact = read_artifact(
        body.document_id, "predictions.json"
    )
    if prediction_artifact is None:
        raise HTTPException(
            status_code=409,
            detail="Document analysis must complete before takeoff generation",
        )
    try:
        pdf_path = document_source(body.document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await run_analysis(
        "takeoff generation",
        generate_takeoff_excel,
        pdf_path,
        predictions=prediction_artifact.get("predictions") or [],
    )


@router.get("/takeoff/exports/{filename}")
def download_takeoff_export(filename: str):
    path = settings.takeoff_exports_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(
        path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
