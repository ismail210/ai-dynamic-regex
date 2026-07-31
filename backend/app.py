"""
AI Structural Steel Takeoff Platform - FastAPI entrypoint.

Upload, extraction, analysis, validation, review, learning, and takeoff are
separate API stages.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from routers.analysis import router as analysis_router
from routers.documents import router as documents_router
from routers.engineering import router as engineering_router
from routers.learning import router as learning_router
from routers.takeoff import router as takeoff_router
from routers.upload import router as upload_router

# Application loggers are attached to uvicorn's stream so upload progress and
# tracebacks appear in the same console as request logs.
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(levelname)s:     %(name)s %(message)s",
)

app = FastAPI(title=settings.api_title, version=settings.api_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials="*" not in settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/upload", tags=["Upload"])
app.include_router(documents_router, prefix="/api", tags=["Documents"])
app.include_router(analysis_router, prefix="/api", tags=["Analysis"])
app.include_router(learning_router, prefix="/api", tags=["Learning"])
app.include_router(engineering_router, prefix="/api", tags=["Engineering"])
app.include_router(takeoff_router, prefix="/api", tags=["Takeoff"])


@app.get("/", tags=["Health"])
def root():
    return {
        "message": "AI Structural Steel Takeoff Platform is running.",
        "version": settings.api_version,
        "docs": "/docs",
        "capabilities": [
            "pdf_upload",
            "entity_classification",
            "aisc_verification_only",
            "confidence_scoring",
            "human_review",
            "retraining",
            "paired_pdf_excel_dataset",
            "takeoff_validation",
            "takeoff_excel_export",
            "dynamic_regex_internal",
            "multimodal_text_geometry_graph",
            "geometry_adapters_pdf_rhino_dwg_dxf",
            "explainable_fusion_predictions",
            "ai_correction_engine",
            "engineering_rule_engine",
            "component_tracking",
            "data_quality_report",
            "model_versioning",
        ],
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/live", tags=["Health"])
def liveness():
    """Process liveness probe; does not touch external artifacts."""

    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
def readiness():
    """Deployment readiness probe for required runtime artifacts."""

    checks = {
        "database": settings.database_file.exists(),
        "model": settings.model_path.exists(),
        "training_directory": settings.training_dir.exists(),
        "uploads_directory": settings.uploads_dir.exists(),
    }
    ready = all(checks.values())
    payload = {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "checks": checks,
    }
    return JSONResponse(payload, status_code=200 if ready else 503)
