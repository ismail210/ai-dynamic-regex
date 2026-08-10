"""
Learning / human-in-the-loop router
===================================
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import settings
from services.dataset_manager import dataset_manager
from services.entity_diagnostics import build_entity_diagnostics
from services.entity_taxonomy import list_categories
from services.engineering.correction_dataset import record_correction
from services.model_predictor import list_classes, reload_model
from services.multimodal.review_enrichment import (
    enrich_review_rows,
    evidence_for,
)
from services.regex_knowledge_base import knowledge_base
from services.retrain_service import (
    get_retrain_status,
    load_model_meta,
    retrain_model,
    start_retrain_job,
)

router = APIRouter()


class ReviewRequest(BaseModel):
    id: str = Field(..., description="Unknown-token row id")
    reviewed_class: Optional[str] = None
    reviewed_category: Optional[str] = None
    notes: str = ""


class BatchReviewRequest(BaseModel):
    ids: List[str]
    action: str = Field(..., pattern="^(approve|reject)$")
    reviewed_class: Optional[str] = None
    reviewed_category: Optional[str] = None
    notes: str = ""


@router.get("/unknown-tokens")
def get_unknown_tokens(status: str = "pending"):
    status_filter = None if status == "all" else status
    rows = enrich_review_rows(
        dataset_manager.list_unknown(status=status_filter)
    )
    return {
        "count": len(rows),
        "status": status,
        "tokens": rows,
        "counts": dataset_manager.unknown_counts(),
    }


@router.post("/approve-token")
def approve_token(payload: ReviewRequest):
    existing = next(
        (
            row
            for row in dataset_manager.list_unknown("pending")
            if row["id"] == payload.id
        ),
        None,
    )
    try:
        # Fall back to stored prediction when class not supplied.
        reviewed_class = payload.reviewed_class
        if not reviewed_class:
            reviewed_class = (existing or {}).get("prediction", "")
        result = dataset_manager.review_token(
            unknown_id=payload.id,
            action="approve",
            reviewed_class=reviewed_class or "",
            reviewed_category=payload.reviewed_category or "",
            notes=payload.notes,
            ranking_score=float((existing or {}).get("overall_confidence") or 0.0),
            predicted_section=str((existing or {}).get("prediction") or ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    evidence = evidence_for(
        (existing or {}).get("source_file", ""),
        (existing or {}).get("token", ""),
    )
    if evidence:
        record_correction(
            features=evidence.get("multimodal_features") or {},
            prediction=evidence,
            correct_label=result.get("reviewed_class"),
            correct_geometry=evidence.get("geometry_preview"),
            user_decision="approve",
            object_id=result.get("id"),
            notes=payload.notes,
        )
    from services.training_pipeline.continuous_learning import record_approval_event

    trigger = record_approval_event()
    return {
        "id": result["id"],
        "token": result["token"],
        "action": "approve",
        "class": result.get("reviewed_class"),
        "category": result.get("reviewed_category"),
        "status": result.get("status"),
        "continuous_learning": trigger,
    }


@router.post("/reject-token")
def reject_token(payload: ReviewRequest):
    existing = next(
        (
            row
            for row in dataset_manager.list_unknown("pending")
            if row["id"] == payload.id
        ),
        None,
    )
    try:
        result = dataset_manager.review_token(
            unknown_id=payload.id,
            action="reject",
            notes=payload.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    evidence = evidence_for(
        (existing or {}).get("source_file", ""),
        (existing or {}).get("token", ""),
    )
    if evidence:
        record_correction(
            features=evidence.get("multimodal_features") or {},
            prediction=evidence,
            correct_label=None,
            correct_geometry=evidence.get("geometry_preview"),
            user_decision="reject",
            object_id=result.get("id"),
            notes=payload.notes,
        )
    return {
        "id": result["id"],
        "token": result["token"],
        "action": "reject",
        "status": result.get("status"),
    }


@router.post("/review-batch")
def review_batch(payload: BatchReviewRequest):
    results = []
    errors = []
    approved = 0
    for uid in payload.ids:
        try:
            reviewed_class = payload.reviewed_class or ""
            existing = next(
                (r for r in dataset_manager.list_unknown("pending") if r["id"] == uid),
                None,
            )
            if payload.action == "approve" and not reviewed_class:
                reviewed_class = (existing or {}).get("prediction", "")
            result = dataset_manager.review_token(
                unknown_id=uid,
                action=payload.action,
                reviewed_class=reviewed_class,
                reviewed_category=payload.reviewed_category or "",
                notes=payload.notes,
            )
            results.append(result)
            evidence = evidence_for(
                (existing or {}).get("source_file", ""),
                (existing or {}).get("token", ""),
            )
            if evidence or payload.action == "approve":
                record_correction(
                    features=(evidence or {}).get("multimodal_features") or {},
                    prediction=evidence or {"token": result.get("token")},
                    correct_label=result.get("reviewed_class")
                    if payload.action == "approve"
                    else None,
                    correct_geometry=(evidence or {}).get("geometry_preview"),
                    user_decision=payload.action,
                    object_id=result.get("id"),
                    notes=payload.notes,
                )
            if payload.action == "approve":
                approved += 1
        except (KeyError, ValueError) as exc:
            errors.append({"id": uid, "error": str(exc)})
    trigger = None
    if approved:
        from services.training_pipeline.continuous_learning import record_approval_events

        trigger = record_approval_events(approved)
    return {
        "processed": len(results),
        "errors": errors,
        "results": results,
        "continuous_learning": trigger,
    }


@router.post("/retrain")
def retrain():
    try:
        meta = retrain_model(actor="user")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Retrain failed: {exc}") from exc
    return {"status": "ok", "model": meta}


@router.post("/retrain/start")
def start_retrain():
    """Start a non-blocking retrain for responsive progress-aware clients."""

    return start_retrain_job(actor="user")


@router.get("/retrain/status")
def retrain_status():
    return get_retrain_status()


@router.get("/continuous-learning/status")
def get_continuous_learning_status():
    from services.training_pipeline.continuous_learning import continuous_learning_status

    return continuous_learning_status()


@router.post("/continuous-learning/trigger")
def trigger_continuous_learning(force: bool = False):
    from services.training_pipeline.continuous_learning import (
        maybe_trigger_continuous_learning,
    )

    return maybe_trigger_continuous_learning(
        reason="manual_api",
        force=force,
        actor="user",
    )


@router.get("/datasets/versions")
def get_dataset_versions(modality: Optional[str] = None, limit: int = 10):
    from services.training_pipeline.contracts import MODALITIES
    from services.training_pipeline.dataset_registry import (
        list_dataset_versions,
        summarize_all_datasets,
    )

    if modality:
        if modality not in MODALITIES:
            raise HTTPException(status_code=400, detail=f"Unknown modality {modality}")
        return list_dataset_versions(modality, limit=limit)
    return summarize_all_datasets()


@router.get("/models/versions")
def get_model_family_versions(family: Optional[str] = None, limit: int = 10):
    from services.training_pipeline.contracts import MODEL_FAMILIES
    from services.training_pipeline.model_registry import (
        list_model_versions,
        summarize_all_models,
    )

    if family:
        if family not in MODEL_FAMILIES:
            raise HTTPException(status_code=400, detail=f"Unknown model family {family}")
        return list_model_versions(family, limit=limit)
    return summarize_all_models()


@router.get("/categories")
def get_categories():
    return {"categories": list_categories()}


@router.get("/dynamic-regex")
def get_dynamic_regex(category: Optional[str] = None):
    classes = knowledge_base.all()
    if category:
        classes = {
            k: v for k, v in classes.items() if v.get("category") == category
        }
    return {
        "classes": classes,
        "stats": knowledge_base.stats(),
        "categories": list_categories(),
    }


@router.get("/statistics")
def get_statistics():
    unknown = dataset_manager.unknown_counts()
    aisc = dataset_manager.load_aisc_dataset()
    approved_n = dataset_manager.approved_count()
    model_meta = load_model_meta() or {}
    kb_stats = knowledge_base.stats()
    history = dataset_manager.get_history(limit=40)
    uploads = dataset_manager._read_frame(
        settings.upload_log_path,
        [
            "id",
            "filename",
            "pages",
            "token_count",
            "known_count",
            "unknown_count",
            "uncertain_count",
            "created_at",
        ],
    )

    regex_variant_count = 0
    for record in knowledge_base.all().values():
        variants = record.get("variants") or []
        regex_variant_count += len(variants) if variants else (1 if record.get("pattern") else 0)

    # Augmentation stats from meta or on-disk file
    aug_meta = model_meta.get("augmentation") or {}
    augmented_n = aug_meta.get("augmented_samples")
    if augmented_n is None and settings.augmented_dataset_path.exists():
        try:
            import pandas as pd

            adf = pd.read_csv(settings.augmented_dataset_path, dtype=str)
            augmented_n = int((adf.get("source") == "augmented").sum()) if "source" in adf else len(adf)
        except Exception:
            augmented_n = 0

    comparison = model_meta.get("model_comparison") or []
    if "model_comparison" not in model_meta and settings.model_comparison_path.exists():
        try:
            import pandas as pd

            comparison = pd.read_csv(settings.model_comparison_path).to_dict(orient="records")
        except Exception:
            comparison = []

    metrics = model_meta.get("metrics") or {}
    flat_meta = {
        **model_meta,
        "accuracy": metrics.get("accuracy", model_meta.get("accuracy")),
        "precision": metrics.get("precision_weighted", model_meta.get("precision")),
        "recall": metrics.get("recall_weighted", model_meta.get("recall")),
        "f1": metrics.get("f1_weighted", model_meta.get("f1")),
        "training_time_sec": metrics.get("training_time_sec"),
        "samples_total": model_meta.get("rows", model_meta.get("samples_total")),
        "n_classes": model_meta.get("classes", model_meta.get("n_classes")),
        "confusion_matrix": {
            "labels": list_classes(),
            "matrix": metrics.get("confusion_matrix", []),
        }
        if metrics.get("confusion_matrix")
        else model_meta.get("confusion_matrix"),
    }

    latest_upload = None
    if not uploads.empty and "created_at" in uploads.columns:
        uploads_sorted = uploads.sort_values("created_at", ascending=False)
        latest_upload = uploads_sorted.iloc[0].to_dict()

    latest_retrain = next(
        (e for e in history if "retrain" in str(e.get("event", "")).lower()),
        None,
    )

    known = list_classes()
    diagnostics = build_entity_diagnostics(model_meta, class_labels=known)

    return {
        "total_pdfs": dataset_manager.upload_count(),
        "aisc_samples": int(len(aisc)),
        "approved_tokens": approved_n,
        "original_samples": int(len(aisc)),
        "synthetic_samples": int(augmented_n or 0),
        "augmentation": {
            "enabled": settings.augmentation_enabled,
            "original_samples": int(len(aisc)) + approved_n,
            "augmented_samples": int(augmented_n or 0),
            "training_samples_total": flat_meta.get("samples_total")
            or (int(len(aisc)) + approved_n + int(augmented_n or 0)),
            **aug_meta,
        },
        "unknown_tokens": unknown,
        "known_classes": known,
        "n_classes": len(known),
        "categories": list_categories(),
        "regex_class_count": kb_stats.get("total_classes", 0),
        "regex_variant_count": regex_variant_count,
        "current_model": flat_meta.get("model", "XGBoost"),
        "current_accuracy": flat_meta.get("accuracy"),
        "training_date": flat_meta.get("trained_at"),
        "model_meta": flat_meta,
        "model_comparison": comparison,
        "knowledge_base": kb_stats,
        "latest_upload": latest_upload,
        "latest_retrain": latest_retrain,
        "recent_activity": history[:12],
        "recent_unknowns": dataset_manager.list_unknown(status="pending")[:8],
        "auto_accept_threshold": settings.auto_accept_probability_threshold,
        "api_version": settings.api_version,
        **diagnostics,
    }


@router.get("/model-comparison")
def get_model_comparison():
    meta = load_model_meta() or {}
    rows = meta.get("model_comparison") or []
    if "model_comparison" not in meta and settings.model_comparison_path.exists():
        import pandas as pd

        rows = pd.read_csv(settings.model_comparison_path).to_dict(orient="records")
    return {"comparison": rows, "best_model": meta.get("model"), "metrics": meta.get("metrics")}


@router.get("/approved-tokens")
def get_approved_tokens():
    frame = dataset_manager.load_approved_dataset()
    rows = frame.to_dict(orient="records") if not frame.empty else []
    return {"count": len(rows), "tokens": rows}


@router.get("/history")
def get_history(limit: int = 100):
    return {"events": dataset_manager.get_history(limit=limit)}


@router.get("/data-quality")
def get_data_quality():
    """Pre-training data quality report (duplicates, imbalance, invalid labels)."""

    from services.data_quality import assess_training_data_quality

    return assess_training_data_quality()


@router.get("/model-versions")
def get_model_versions(limit: int = 20):
    from services.model_versioning import list_model_versions

    return list_model_versions(limit=limit)


class RollbackRequest(BaseModel):
    version_id: str


@router.post("/model-versions/rollback")
def post_model_rollback(payload: RollbackRequest):
    from services.model_predictor import reload_model
    from services.model_versioning import rollback_model_version

    try:
        result = rollback_model_version(payload.version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    reloaded = reload_model()
    return {**result, "model_reloaded": bool(reloaded)}


@router.post("/reload-model")
def reload():
    info = reload_model()
    return {"status": "ok", "model": info}
