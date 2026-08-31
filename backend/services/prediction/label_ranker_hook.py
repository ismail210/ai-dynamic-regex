"""Analyze-path hook into ``services.label_reconstruction``.

Production modules (orchestrator, pipeline, routers) must not import
``services.label_reconstruction`` directly — isolation tests scan their
source. This thin adapter is the only allowed bridge.

Two independent things live here, and they must not be confused:

* ``apply_label_ranker_for_analyze`` — the LEARNED ranker path, gated by
  ``ML_LABEL_RANKER_SHADOW`` / ``ML_LABEL_RANKER_ENABLED`` (both default
  off). See its docstring for flag semantics.
* ``resolve_reliable_exact_catalog_label`` — a purely DETERMINISTIC,
  always-on lookup with no model involved and no flag gate. It extends
  ``catalog_valid_exact_section``-style exact-label protection to text
  that carries a reliable designation plus a trailing non-designation
  field (cut length, quantity) that keeps it from matching the catalog as
  a whole string. It must remain safe to call unconditionally, with the
  ranker fully disabled.
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


def resolve_reliable_exact_catalog_label(
    normalized_text: str,
    *,
    resolver_fn: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[str]:
    """The single real catalog label ``normalized_text`` unambiguously names,
    even when a trailing cut-length/quantity field keeps it from matching
    the catalog as a whole string (e.g. ``L3X3X3/8X0'-6"`` -> ``L3X3X3/8``).

    Deterministic and unconditional — NOT gated by
    ``ML_LABEL_RANKER_ENABLED``/``ML_LABEL_RANKER_SHADOW``, which govern the
    learned ranker only. Callers use this to extend catalog-exact
    protection so the weighted fusion/correction path never gets a chance
    to override an explicit, unambiguous printed section just because a
    fabrication/cut-length suffix was attached to it.

    ``resolver_fn`` is for tests; production leaves it None and lazy-imports
    ``services.label_reconstruction.candidates.reliable_exact_catalog_label``.
    Fail-safe: any exception here is logged and treated as "no reliable
    exact label" (returns None) rather than raised — this must never break
    Analyze even if the (experimental-adjacent) label_reconstruction package
    changes underneath it.
    """

    text = (normalized_text or "").strip()
    if not text:
        return None
    if resolver_fn is None:
        from services.label_reconstruction.candidates import (
            reliable_exact_catalog_label as resolver_fn,
        )
    try:
        return resolver_fn(text)
    except Exception:  # noqa: BLE001 - must not crash Analyze
        logger.exception(
            "label_ranker_hook: reliable_exact_catalog_label failed for %r", text
        )
        return None
