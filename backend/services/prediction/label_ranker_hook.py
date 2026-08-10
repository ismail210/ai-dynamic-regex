"""Analyze-path hook for damaged-label ranker shadow / enable flags.

Production modules (orchestrator, pipeline, routers) must not import
``services.label_reconstruction`` directly — isolation tests scan their
source. This thin adapter is the only allowed bridge: it lazy-imports the
shadow entry point and applies flag semantics.

Semantics
---------
* Both flags off (default): no-op, zero cost beyond two bool checks.
* ``ML_LABEL_RANKER_SHADOW`` only: run reconstruct for logging; **never**
  change the live analyze section.
* ``ML_LABEL_RANKER_ENABLED``: may replace the live section with the
  ranker's ``selected_prediction`` (catalog-valid candidates only).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from config import settings

logger = logging.getLogger("takeoff.label_ranker_hook")


def apply_label_ranker_for_analyze(
    *,
    raw_text: str,
    live_section: str,
    reconstruct_fn: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Run ranker shadow/enable path for one analyze token.

    Returns a metadata dict always safe to stash on the prediction payload.
    ``applied`` is True only when ENABLED replaced ``live_section``.

    ``reconstruct_fn`` is for tests; production leaves it None and lazy-imports
    ``services.label_reconstruction.shadow.reconstruct``.

    Fail-safe contract: an exception inside the (experimental, R&D) ranker
    must never crash Analyze. SHADOW logs the error and leaves the live
    prediction untouched (as it always does); ENABLED falls back to whatever
    ``live_section`` already was — the deterministic/fusion baseline computed
    upstream — rather than propagating. The error is never hidden: it is
    logged via ``logger.exception`` and recorded in the returned metadata
    (``ranker_status``/``error_type``) so it is visible in the shadow log and
    explanation payload, not just swallowed.
    """
    meta: Dict[str, Any] = {
        "invoked": False,
        "applied": False,
        "shadow": None,
        "selected_prediction": None,
        "reason": None,
        "model_version": None,
        "live_section": live_section or "",
        "ranker_status": "disabled",
        "error_type": None,
        "ranking_scores": None,
    }
    if not (
        settings.ml_label_ranker_shadow or settings.ml_label_ranker_enabled
    ):
        return meta

    text = (raw_text or "").strip()
    if not text:
        return meta

    if reconstruct_fn is None:
        # Lazy import keeps cold path clean when flags are off, and keeps
        # production callers free of a direct package import.
        from services.label_reconstruction.shadow import reconstruct as reconstruct_fn

    meta["invoked"] = True
    try:
        result = reconstruct_fn(text, live_prediction=live_section or None)
    except Exception as exc:  # noqa: BLE001 - experimental path must not crash Analyze
        logger.exception(
            "label_ranker_hook: reconstruct failed for %r (shadow=%s enabled=%s)",
            text,
            settings.ml_label_ranker_shadow,
            settings.ml_label_ranker_enabled,
        )
        meta["ranker_status"] = "error"
        meta["error_type"] = type(exc).__name__
        # applied stays False — callers fall back to live_section unchanged.
        return meta

    meta["ranker_status"] = "ok"
    meta["selected_prediction"] = result.selected_prediction
    meta["reason"] = result.reason
    meta["model_version"] = result.model_version
    meta["shadow"] = result.shadow
    meta["ranking_scores"] = result.ranking_scores

    if (
        settings.ml_label_ranker_enabled
        and result.selected_prediction
        and result.reason == "learned_ranker_top_candidate"
        and result.selected_prediction != (live_section or "")
    ):
        meta["applied"] = True
    return meta
