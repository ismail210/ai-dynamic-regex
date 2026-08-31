"""Model retraining from immutable AISC, reviewed examples, and augmentation."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from config import settings
from services.dataset_manager import dataset_manager
from services.entity_taxonomy import category_for_aisc_type
from services.prediction.confidence_engine import level_from_score
from services.regex_learning_engine import learn_regex_with_report
from services.regex_knowledge_base import knowledge_base
from services.regex_validator import validate_regex
from services.training_service import load_model_metadata


_RETRAIN_LOCK = threading.Lock()
_STATUS_LOCK = threading.Lock()
_retrain_status = {
    "job_id": None,
    "status": "idle",
    "step": "Ready",
    "progress": 0,
    "approved_samples": 0,
    "total_samples": 0,
    "estimated_remaining_seconds": None,
    "started_at": None,
    "completed_at": None,
    "error": None,
    "result": None,
}


def load_model_meta() -> dict:
    return load_model_metadata()


def get_retrain_status() -> dict:
    """Return a thread-safe snapshot for UI progress polling."""

    with _STATUS_LOCK:
        return dict(_retrain_status)


def _set_retrain_status(**changes) -> dict:
    with _STATUS_LOCK:
        _retrain_status.update(changes)
        return dict(_retrain_status)


def _rebuild_regex_kb(canonical: pd.DataFrame, now: str) -> dict:
    """Learn readable ranked variants from canonical tokens only (no synthetic phrases)."""
    kb = {}
    max_variants = getattr(settings, "max_regex_variants_per_class", 8)
    for cls, group in canonical.groupby(canonical["class"].str.upper()):
        # Prefer compact designations for regex learning
        examples = [
            str(t)
            for t in group["token"].tolist()
            if " " not in str(t) or str(t).count(" ") <= 1
        ]
        if not examples:
            examples = [str(t) for t in group["token"].tolist()]
        # Cap examples fed into the learner for performance; keep true count in metadata.
        learn_examples = examples[: max(settings.max_examples_per_class * 2, 120)]
        report = learn_regex_with_report(learn_examples)
        validation = validate_regex(report["pattern"], learn_examples)
        variants = list(report.get("variants") or [])[:max_variants]
        weighted = sum(float(v.get("confidence", 0)) * float(v.get("frequency", 0)) for v in variants)
        confidence = min(0.97, 0.70 * validation.confidence + 0.30 * weighted)
        category = next(
            (value for value in group["category"] if value),
            category_for_aisc_type(cls),
        )
        kb[cls] = {
            "pattern": report["pattern"],
            "variants": variants,
            "examples": examples[: settings.max_examples_per_class],
            "example_count": len(examples),
            "coverage": round(validation.coverage, 4),
            "confidence": round(confidence, 4),
            "confidence_level": level_from_score(confidence),
            "category": category,
            "distinct_structures": report.get("distinct_structures", len(variants)),
            "usage_count": 0,
            "source": "training+approved",
            "created_at": now,
            "updated_at": now,
        }
    knowledge_base.reset(kb, persist=True)
    return kb


def retrain_model(
    actor: str = "user",
    progress_callback: Callable[[str, int], None] | None = None,
) -> dict:
    """
    Production retrain via the continuous-learning orchestrator.

    Builds versioned text/geometry/graph/fusion datasets, trains available
    modalities with quality gates, and reloads promoted production models.
    """
    if not _RETRAIN_LOCK.acquire(blocking=False):
        raise RuntimeError("A model retrain is already running")

    def progress(step: str, percent: int) -> None:
        if progress_callback:
            progress_callback(step, percent)

    try:
        from services.training_pipeline.continuous_learning import (
            run_continuous_learning_pipeline,
        )

        return run_continuous_learning_pipeline(
            actor=actor,
            progress_callback=progress,
        )
    finally:
        _RETRAIN_LOCK.release()


def start_retrain_job(actor: str = "user") -> dict:
    """Start one background retrain and return immediately."""

    with _STATUS_LOCK:
        if _retrain_status["status"] == "running" or _RETRAIN_LOCK.locked():
            return dict(_retrain_status)

        approved = dataset_manager.approved_count()
        canonical = dataset_manager.build_merged_training_frame()
        job_id = uuid.uuid4().hex[:12]
        started_at = datetime.now(timezone.utc).isoformat()
        _retrain_status.update(
            {
                "job_id": job_id,
                "status": "running",
                "step": "Preparing retrain",
                "progress": 1,
                "approved_samples": approved,
                "total_samples": int(len(canonical)),
                "estimated_remaining_seconds": None,
                "started_at": started_at,
                "completed_at": None,
                "error": None,
                "result": None,
            }
        )

    started_clock = time.monotonic()

    def update(step: str, percent: int) -> None:
        elapsed = time.monotonic() - started_clock
        remaining = (
            round((elapsed / percent) * (100 - percent))
            if percent > 2 and percent < 100
            else None
        )
        _set_retrain_status(
            step=step,
            progress=max(1, min(100, int(percent))),
            estimated_remaining_seconds=remaining,
        )

    def run() -> None:
        try:
            result = retrain_model(actor=actor, progress_callback=update)
            _set_retrain_status(
                status="succeeded",
                step="Retrain complete",
                progress=100,
                estimated_remaining_seconds=0,
                completed_at=datetime.now(timezone.utc).isoformat(),
                result=result,
            )
        except Exception as exc:  # status endpoint surfaces the failure
            _set_retrain_status(
                status="failed",
                step="Retrain failed",
                estimated_remaining_seconds=None,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )

    threading.Thread(
        target=run,
        name=f"model-retrain-{job_id}",
        daemon=True,
    ).start()
    return get_retrain_status()
