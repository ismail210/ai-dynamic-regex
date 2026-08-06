"""
Engineering Validation & Takeoff API
====================================

Additive router. Does not replace /upload or existing learning endpoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import settings
from services.artifact_store import artifact_path
from services.dataset_manager import dataset_manager
from services.document_registry import register_document
from services.engineering.correction_dataset import (
    corrections_summary,
    list_corrections,
    record_correction,
)
from services.engineering.excel_loader import load_aisc_catalog, load_engineering_excel
from services.engineering.geometry_adapters import geometry_capabilities
from services.multimodal.encoder_registry import encoder_registry
from services.stage_runner import run_shared_stage
from services.staged_pipeline import run_analysis_stage, run_extraction_stage
from services.upload_service import (
    EXCEL_SUFFIXES,
    PDF_SUFFIXES,
    run_analysis,
    save_upload,
)

router = APIRouter()


class CorrectionRequest(BaseModel):
    document_id: Optional[str] = None
    object_id: Optional[str] = None
    features: dict = Field(default_factory=dict)
    prediction: Optional[dict] = None
    correct_label: Optional[str] = None
    correct_geometry: Optional[dict] = None
    user_decision: str = Field(..., description="approve | reject | edit | correct")
    notes: str = ""


@router.get("/multimodal/capabilities")
def multimodal_capabilities():
    """Report enabled and prepared geometry/model adapters."""

    return {
        "geometry_adapters": geometry_capabilities(),
        "active_fusion": "weighted_classical_multimodal_v2_ai_first",
        "active_attention_fusion": "unified_multimodal_attention_v1",
        "encoders": encoder_registry.capabilities(),
        "modalities": [
            "text",
            "ocr",
            "layout",
            "geometry",
            "graph",
            "engineering_rules",
            "database",
        ],
        "policy": {
            "ai_predicts": True,
            "database_decides_prediction": False,
            "database_role": "verification_only",
            "fusion_weights": {
                "text": 0.32,
                "ocr": 0.08,
                "layout": 0.08,
                "geometry": 0.30,
                "graph": 0.17,
                "engineering_rules": 0.05,
                "database": 0.0,
            },
            "attention_is_dynamic": True,
        },
        "prepared_model_families": [
            "XGBoost",
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
    }


@router.post("/multimodal/analyze")
async def analyze_multimodal_document(
    pdf: UploadFile = File(...),
    excel: Optional[UploadFile] = File(None),
):
    """
    Run text + geometry + graph fusion with optional ground-truth validation.

    Excel is used only as expected validation data, never as a prediction
    input.
    """

    destination = settings.engineering_uploads_dir
    pdf_path = await save_upload(
        pdf, destination, allowed_suffixes=PDF_SUFFIXES, field="pdf"
    )

    excel_path = None
    if excel and excel.filename:
        excel_path = await save_upload(
            excel, destination, allowed_suffixes=EXCEL_SUFFIXES, field="excel"
        )

    document = register_document(
        pdf_path, original_name=Path(pdf.filename or pdf_path.name).name
    )
    await run_shared_stage(
        stage="document extraction",
        document_id=document["document_id"],
        runner=lambda: run_analysis(
            "document extraction",
            run_extraction_stage,
            document["document_id"],
        ),
    )
    result = await run_shared_stage(
        stage="multimodal document analysis",
        document_id=document["document_id"],
        runner=lambda: run_analysis(
            "multimodal document analysis",
            run_analysis_stage,
            document["document_id"],
            expected_excel_path=excel_path,
        ),
    )

    # Excel uploads are ground-truth pairs — auto-register for dataset generation.
    if excel_path is not None:
        from services.takeoff.takeoff_validation import (
            _auto_build_dataset,
            _register_uploaded_pair,
        )

        pair_id = await run_analysis(
            "ground-truth pair registration",
            _register_uploaded_pair,
            pdf_path,
            excel_path,
        )
        result["registered_pair_id"] = pair_id
        result["dataset_build"] = await run_analysis(
            "paired dataset build", _auto_build_dataset, pair_id
        )
        result["excel_role"] = "ground_truth_only"
        result["excel_is_prediction"] = False
    return result


@router.post("/multimodal/extract")
async def extract_multimodal_document(
    pdf: UploadFile = File(...),
):
    """Run extraction + diagnostics only; prediction is explicitly not started."""

    pdf_path = await save_upload(
        pdf,
        settings.engineering_uploads_dir,
        allowed_suffixes=PDF_SUFFIXES,
        field="pdf",
    )
    document = register_document(
        pdf_path, original_name=Path(pdf.filename or pdf_path.name).name
    )
    return await run_shared_stage(
        stage="document extraction",
        document_id=document["document_id"],
        runner=lambda: run_analysis(
            "document extraction",
            run_extraction_stage,
            document["document_id"],
        ),
    )


@router.post("/engineering/excel/parse")
async def parse_engineering_excel(file: UploadFile = File(...)):
    dest = await save_upload(
        file,
        settings.engineering_uploads_dir,
        allowed_suffixes=EXCEL_SUFFIXES,
        field="file",
    )
    return await run_analysis("excel parse", load_engineering_excel, dest)


@router.get("/engineering/aisc-catalog")
def get_aisc_catalog(limit: int = 50):
    """Sample of AISC catalog as structured JSON (for UI previews)."""

    limit = max(1, min(int(limit), 500))
    return load_aisc_catalog(limit=limit)


@router.get("/engineering/artifacts/{document_id}/{name}")
def get_artifact(document_id: str, name: str):
    allowed = {
        "document.json",
        "geometry.json",
        "graph.json",
        "predictions.json",
        "validation.json",
        "analysis.json",
        "expected_excel.json",
    }
    if name not in allowed:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    path = artifact_path(document_id, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path)


@router.get("/engineering/pdf/{filename}")
def get_uploaded_engineering_pdf(filename: str):
    path = settings.engineering_uploads_dir / filename
    if not path.exists():
        # Fall back to general uploads (legacy upload page files)
        path = settings.uploads_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.post("/engineering/corrections")
def post_correction(body: CorrectionRequest):
    sample = record_correction(
        features=body.features,
        prediction=body.prediction,
        correct_label=body.correct_label,
        correct_geometry=body.correct_geometry,
        user_decision=body.user_decision,
        document_id=body.document_id,
        object_id=body.object_id,
        notes=body.notes,
    )
    approved = None
    if body.user_decision in {"approve", "edit", "correct"} and body.correct_label:
        original = str(
            (body.prediction or {}).get("original_token")
            or (body.features or {}).get("original_token")
            or body.correct_label
        )
        queued = dataset_manager.enqueue_unknown(
            token=original,
            prediction=str(body.correct_label),
            model_probability=(body.prediction or {}).get("confidence") or "",
            overall_confidence=(body.prediction or {}).get("confidence") or "",
            confidence_level="High",
            uncertain=False,
            source_file=body.document_id or "",
            category=str((body.prediction or {}).get("entity_type") or ""),
        )
        try:
            approved = dataset_manager.review_token(
                unknown_id=queued["id"],
                action="approve",
                reviewed_class=str(body.correct_label),
                reviewed_category=str(
                    (body.prediction or {}).get("entity_type") or ""
                ),
                notes=body.notes or f"Approved from validation issue {body.object_id or ''}",
                actor="validation_page",
            )
        except ValueError:
            approved = queued
        from services.training_pipeline.continuous_learning import record_approval_event

        trigger = record_approval_event()
    else:
        trigger = None
    return {
        "saved": True,
        "sample": sample,
        "approved": approved,
        "continuous_learning": trigger,
        "summary": corrections_summary(),
    }


@router.get("/engineering/corrections")
def get_corrections(limit: int = 100):
    return {
        "summary": corrections_summary(),
        "items": list_corrections(limit=limit),
    }


