"""Continuous-learning state, threshold triggers, and orchestration."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from config import settings
from services.dataset_manager import dataset_manager
from services.model_predictor import reload_model
from services.training_pipeline.dataset_builder import build_all_modality_datasets
from services.training_pipeline.dataset_registry import summarize_all_datasets
from services.training_pipeline.model_registry import summarize_all_models
from services.training_pipeline.source_ingestion import source_inventory
from services.training_pipeline.trainers import (
    train_exact_section,
    train_family_classifier,
    train_fusion_model,
    train_geometry_model,
    train_graph_model,
)


_LOCK = threading.Lock()


def _state_path() -> Path:
    path = settings.continuous_learning_state_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_state() -> Dict[str, Any]:
    path = _state_path()
    default = {
        "pending_approved_count": 0,
        "last_trigger_at": None,
        "last_completed_at": None,
        "last_dataset_versions": {},
        "last_model_versions": {},
        "last_consumed_source_counts": {},
        "last_trigger_reason": None,
        "last_result": None,
        "last_error": None,
        "status": "idle",
    }
    if not path.exists():
        return dict(default)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {**default, **payload}
    except (OSError, json.JSONDecodeError):
        return dict(default)


def save_state(state: Dict[str, Any]) -> Dict[str, Any]:
    path = _state_path()
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    return state


def record_approval_events(count: int = 1) -> Dict[str, Any]:
    """Increment pending approvals by ``count`` and maybe start a run."""

    with _LOCK:
        state = load_state()
        state["pending_approved_count"] = int(state.get("pending_approved_count") or 0) + max(
            0, int(count)
        )
        save_state(state)
    return maybe_trigger_continuous_learning(reason="approval_threshold")


def record_approval_event() -> Dict[str, Any]:
    return record_approval_events(1)


def _cooldown_ok(state: dict) -> bool:
    last = state.get("last_trigger_at")
    if not last:
        return True
    try:
        previous = datetime.fromisoformat(last)
    except ValueError:
        return True
    elapsed = (datetime.now(timezone.utc) - previous).total_seconds()
    return elapsed >= settings.continuous_learning_cooldown_seconds


def maybe_trigger_continuous_learning(
    *,
    reason: str = "manual",
    force: bool = False,
    actor: str = "system",
) -> Dict[str, Any]:
    """Start a background candidate run when threshold/cooldown allow."""

    state = load_state()
    pending = int(state.get("pending_approved_count") or 0)
    ready = force or pending >= settings.continuous_learning_threshold
    if not ready:
        return {
            "triggered": False,
            "reason": "threshold_not_met",
            "pending_approved_count": pending,
            "threshold": settings.continuous_learning_threshold,
            "state": state,
        }
    if not force and not _cooldown_ok(state):
        return {
            "triggered": False,
            "reason": "cooldown_active",
            "pending_approved_count": pending,
            "threshold": settings.continuous_learning_threshold,
            "state": state,
        }
    if state.get("status") == "running":
        return {
            "triggered": False,
            "reason": "already_running",
            "state": state,
        }

    # Reuse retrain job machinery for UI progress while running the new pipeline.
    from services.retrain_service import start_retrain_job

    status = start_retrain_job(actor=actor)
    state = load_state()
    state.update(
        {
            "status": "running",
            "last_trigger_at": datetime.now(timezone.utc).isoformat(),
            "last_trigger_reason": reason,
            "pending_approved_count": 0 if ready else pending,
        }
    )
    save_state(state)
    return {
        "triggered": True,
        "reason": reason,
        "retrain_status": status,
        "state": state,
    }


def run_continuous_learning_pipeline(
    *,
    actor: str = "user",
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Dict[str, Any]:
    """
    Full continuous-learning run:

    ingest → version datasets → train available modalities → evaluate/promote → reload
    """

    def progress(step: str, percent: int) -> None:
        if progress_callback:
            progress_callback(step, percent)

    state = load_state()
    state["status"] = "running"
    state["last_error"] = None
    save_state(state)

    try:
        progress("Ingesting learning sources", 5)
        inventory = source_inventory()

        progress("Building versioned modality datasets", 18)
        datasets = build_all_modality_datasets(
            notes=f"continuous learning build by {actor}"
        )
        text_version = (
            datasets["datasets"]["text"]["manifest"]["version_id"]
            if datasets["datasets"].get("text")
            else None
        )

        progress("Training family classifier", 35)
        family_result = train_family_classifier(
            dataset_version=text_version, actor=actor
        )

        progress("Training exact-section model", 55)
        exact_result = train_exact_section(
            dataset_version=text_version, actor=actor
        )

        progress("Preparing geometry lane", 68)
        geometry_result = train_geometry_model(
            dataset_version=datasets["datasets"]["geometry"]["manifest"]["version_id"]
        )

        progress("Preparing graph lane", 76)
        graph_result = train_graph_model(
            dataset_version=datasets["datasets"]["graph"]["manifest"]["version_id"]
        )

        progress("Calibrating fusion lane", 84)
        fusion_result = train_fusion_model(
            dataset_version=datasets["datasets"]["fusion"]["manifest"]["version_id"]
        )

        progress("Rebuilding compatibility regex KB", 90)
        # Keep regex KB rebuild as compatibility-only side effect.
        from services.retrain_service import _rebuild_regex_kb

        canonical = dataset_manager.build_merged_training_frame()
        now = datetime.now(timezone.utc).isoformat()
        _rebuild_regex_kb(canonical, now)

        progress("Reloading production models", 96)
        reload_model()

        result = {
            "inventory": inventory,
            "datasets": datasets,
            "models": {
                "family_classifier": family_result,
                "exact_section": exact_result,
                "geometry": geometry_result,
                "graph": graph_result,
                "fusion": fusion_result,
            },
            "dataset_registry": summarize_all_datasets(),
            "model_registry": summarize_all_models(),
            "actor": actor,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        # Shape a legacy-compatible metadata payload for existing UI.
        legacy_meta = family_result.get("meta") or {}
        legacy_meta["exact_section_model"] = exact_result.get("meta") or {}
        legacy_meta["continuous_learning"] = {
            "dataset_versions": {
                modality: payload["manifest"]["version_id"]
                for modality, payload in datasets["datasets"].items()
            },
            "model_versions": {
                key: value.get("version_id")
                for key, value in result["models"].items()
            },
            "promotion": {
                key: value.get("promotion_status")
                for key, value in result["models"].items()
            },
        }

        state.update(
            {
                "status": "succeeded",
                "pending_approved_count": 0,
                "last_completed_at": result["completed_at"],
                "last_dataset_versions": legacy_meta["continuous_learning"][
                    "dataset_versions"
                ],
                "last_model_versions": legacy_meta["continuous_learning"][
                    "model_versions"
                ],
                "last_consumed_source_counts": inventory.get("sources") or {},
                "last_result": {
                    "promotion": legacy_meta["continuous_learning"]["promotion"],
                    "family_metrics": family_result.get("metrics"),
                },
                "last_error": None,
            }
        )
        save_state(state)
        progress("Continuous learning complete", 100)
        dataset_manager.log_event(
            "continuous_learning_completed",
            "",
            json.dumps(
                {
                    "family_version": family_result.get("version_id"),
                    "exact_version": exact_result.get("version_id"),
                    "promotion": legacy_meta["continuous_learning"]["promotion"],
                }
            ),
            actor,
        )
        return legacy_meta
    except Exception as exc:
        state = load_state()
        state["status"] = "failed"
        state["last_error"] = str(exc)
        state["last_completed_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        raise


def continuous_learning_status() -> Dict[str, Any]:
    state = load_state()
    return {
        "state": state,
        "threshold": settings.continuous_learning_threshold,
        "cooldown_seconds": settings.continuous_learning_cooldown_seconds,
        "pending_approved_count": state.get("pending_approved_count") or 0,
        "ready_for_trigger": int(state.get("pending_approved_count") or 0)
        >= settings.continuous_learning_threshold
        and _cooldown_ok(state),
        "datasets": summarize_all_datasets(),
        "models": summarize_all_models(),
        "sources": source_inventory(),
        "modality_thresholds": {
            "geometry_min_samples": settings.geometry_min_samples,
            "graph_min_samples": settings.graph_min_samples,
            "fusion_min_samples": settings.fusion_min_samples,
        },
    }
