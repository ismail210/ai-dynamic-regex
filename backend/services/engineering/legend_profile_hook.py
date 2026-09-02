"""Sole production bridge into the project context profile feature.

``extraction_engine.py`` must only ever call ``attach_legend_profile`` from
this module -- never import ``legend_profile``/``legend_llm_provider``
directly. That keeps the LLM client (Ollama/Anthropic/none), prompt, and
provider selection fully swappable behind one typed entry point:
production code consumes a plain dict profile and does not know or care
which model (if any) produced its LLM-derived fields.

This module is also the ONLY place that decides the overall
``status`` on a profile (see legend_profile.ANALYSIS_*) and the only place
that logs the observability trail requested for this checkpoint --
candidate/selected pages, character counts, provider/model, latency,
counts of facts/insights/rejections, and cache hit/miss. The previous
checkpoint's silent "blank panel, no idea why" failure mode is exactly
what this logging and status field exist to prevent.

Fail-safe contract: this function NEVER raises, and NEVER changes any key
on ``document`` other than ``document["legend_profile"]``. Any internal
failure results in ``legend_profile.empty_profile(...)`` being attached
instead, tagged with the most specific status available -- the rest of
extraction always proceeds identically either way.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger("takeoff.legend_profile_hook")


def attach_legend_profile(document: Dict[str, Any]) -> Dict[str, Any]:
    """Attach ``document["legend_profile"]`` and return it.

    Always sets the key (never leaves it absent) so callers/serializers
    never need to distinguish "feature disabled" from "nothing found" --
    both produce the same well-formed shape, distinguished only by
    ``status``.
    """

    from services.engineering import legend_profile as lp

    if not settings.legend_profile_enabled:
        profile = lp.empty_profile(document, status=lp.ANALYSIS_DISABLED, llm_requested=False)
        document["legend_profile"] = profile
        return profile

    try:
        profile = _build(document)
    except Exception as exc:  # noqa: BLE001 - must never break extraction
        logger.exception("legend_profile_hook: unexpected failure, degrading to empty profile")
        profile = lp.empty_profile(
            document,
            status=lp.ANALYSIS_MODEL_ERROR,
            llm_requested=settings.legend_profile_llm_enabled,
        )
        profile["llm_error"] = f"hook_error: {type(exc).__name__}: {exc}"
        document["legend_profile"] = profile
        return profile

    document["legend_profile"] = profile
    return profile


def _build(document: Dict[str, Any]) -> Dict[str, Any]:
    from services.engineering import legend_profile as lp

    document_id = document.get("document_id") or document.get("source_file") or "?"
    llm_requested = bool(settings.legend_profile_llm_enabled)
    document_hash = lp.compute_document_hash(document)
    cache_key = lp.compute_cache_key(
        document_hash,
        llm_requested=llm_requested,
        provider_name=settings.legend_llm_provider,
        model=settings.legend_llm_model,
    )
    cache_dir = settings.legend_profile_cache_dir
    cached = lp.load_cached_profile(cache_dir, cache_key)
    if cached is not None:
        logger.info(
            "legend_profile[%s]: cache HIT (key=%s, status=%s)",
            document_id,
            cache_key[:12],
            cached.get("status"),
        )
        if isinstance(cached.get("diagnostics"), dict):
            cached["diagnostics"]["cache_state"] = "CACHE_HIT"
        return cached

    context_pages = lp.detect_context_pages(document)
    readable_pages = lp._readable_context_pages(context_pages)
    vision_pages = sorted(
        p for p, role in context_pages.items() if role == lp.PAGE_ROLE_VISION_REQUIRED
    )
    abbreviation_rules = lp.extract_abbreviation_rules(document, context_pages)

    logger.info(
        "legend_profile[%s]: %d candidate context page(s) %s, %d readable, "
        "%d vision-required, %d abbreviation rule(s) extracted",
        document_id,
        len(context_pages),
        context_pages,
        len(readable_pages),
        len(vision_pages),
        len(abbreviation_rules),
    )

    if not context_pages:
        status = lp.ANALYSIS_NO_CONTEXT_PAGES
    elif not readable_pages:
        status = lp.ANALYSIS_VISION_REQUIRED
    elif abbreviation_rules:
        status = lp.ANALYSIS_SUCCESS
    else:
        status = lp.ANALYSIS_NO_RELEVANT_INFORMATION

    profile = lp.empty_profile(document, status=status, llm_requested=llm_requested)
    profile["context_pages"] = {str(k): v for k, v in context_pages.items()}
    profile["abbreviation_rules"] = abbreviation_rules
    profile["diagnostics"] = {
        "candidate_context_pages": {str(k): v for k, v in context_pages.items()},
        "readable_pages": readable_pages,
        "vision_required_pages": vision_pages,
        "abbreviation_rules_found": len(abbreviation_rules),
        "cache_key": cache_key[:12],
        "cache_state": "FRESH_LLM_RUN" if llm_requested else "FRESH_DETERMINISTIC_RUN",
    }

    if llm_requested and readable_pages:
        _apply_llm(document, context_pages, profile, document_id=document_id)
    elif llm_requested and not readable_pages:
        logger.info("legend_profile[%s]: LLM requested but no readable pages to send", document_id)

    lp.save_profile(cache_dir, cache_key, profile)
    return profile


def _apply_llm(
    document: Dict[str, Any],
    context_pages: Dict[int, str],
    profile: Dict[str, Any],
    *,
    document_id: str,
) -> None:
    from services.engineering import legend_llm_provider as llm
    from services.engineering import legend_profile as lp

    provider = llm.get_default_provider(
        enabled=True,
        provider_name=settings.legend_llm_provider,
        api_key_env=settings.legend_profile_llm_api_key_env,
        model=settings.legend_llm_model,
        ollama_base_url=settings.ollama_base_url,
        ollama_num_ctx=settings.legend_llm_num_ctx,
        ollama_num_predict=settings.legend_llm_num_predict,
        ollama_timeout_s=settings.legend_llm_timeout_s,
    )
    context_text = lp.build_context_text(document, context_pages)
    chars_available = sum(
        len(lp._page_text(document, p)) for p in lp._readable_context_pages(context_pages)
    )
    profile["diagnostics"]["context_chars_available"] = chars_available
    profile["diagnostics"]["context_chars_sent"] = len(context_text)
    profile["diagnostics"]["context_truncated"] = len(context_text) < chars_available
    profile["diagnostics"]["num_ctx"] = settings.legend_llm_num_ctx
    profile["diagnostics"]["num_predict"] = settings.legend_llm_num_predict

    result = llm.propose_analysis(
        context_text,
        provider=provider,
        abbreviation_rules=profile.get("abbreviation_rules") or [],
    )

    profile["llm_provider"] = settings.legend_llm_provider
    profile["llm_model"] = settings.legend_llm_model
    profile["llm_latency_ms"] = result.latency_ms
    profile["llm_error"] = result.error

    profile["diagnostics"]["llm_provider"] = settings.legend_llm_provider
    profile["diagnostics"]["llm_model"] = settings.legend_llm_model
    profile["diagnostics"]["prompt_version"] = llm.PROMPT_VERSION
    profile["diagnostics"]["llm_latency_ms"] = result.latency_ms
    profile["diagnostics"]["raw_rule_count"] = result.raw_rule_count
    profile["diagnostics"]["rejected_rule_count"] = result.rejected_rule_count
    profile["diagnostics"]["raw_insight_count"] = result.raw_insight_count
    profile["diagnostics"]["rejected_insight_count"] = result.rejected_insight_count
    profile["diagnostics"]["rules_by_type"] = result.rules_by_type()
    # Ollama's own timing/token counters for the single model call, so the
    # analysis-latency breakdown can attribute time to model load vs prompt
    # eval vs generation rather than one opaque wall-clock number.
    run_stats = getattr(provider, "last_run_stats", None)
    if run_stats:
        profile["diagnostics"]["ollama_stats"] = {
            "load_ms": round((run_stats.get("load_duration") or 0) / 1e6, 1),
            "prompt_eval_count": run_stats.get("prompt_eval_count"),
            "prompt_eval_ms": round((run_stats.get("prompt_eval_duration") or 0) / 1e6, 1),
            "eval_count": run_stats.get("eval_count"),
            "eval_ms": round((run_stats.get("eval_duration") or 0) / 1e6, 1),
            "total_ms": round((run_stats.get("total_duration") or 0) / 1e6, 1),
            "done_reason": run_stats.get("done_reason"),
        }

    if result.unavailable:
        profile["status"] = lp.ANALYSIS_MODEL_UNAVAILABLE
        profile["llm_used"] = False
        logger.warning(
            "legend_profile[%s]: MODEL_UNAVAILABLE (provider=%s model=%s): %s",
            document_id, settings.legend_llm_provider, settings.legend_llm_model, result.error,
        )
        return

    if result.error:
        profile["status"] = lp.ANALYSIS_MODEL_ERROR
        profile["llm_used"] = False
        logger.warning(
            "legend_profile[%s]: MODEL_ERROR (provider=%s model=%s): %s",
            document_id, settings.legend_llm_provider, settings.legend_llm_model, result.error,
        )
        return

    profile["llm_used"] = True
    profile["prompt_version"] = llm.PROMPT_VERSION
    profile["executive_summary"] = result.executive_summary
    profile["project_rules"] = result.rules
    profile["drawing_language"] = result.drawing_language
    profile["derived_insights"] = result.derived_insights
    profile["warnings_and_conflicts"] = result.warnings
    profile["estimator_attention_items"] = result.attention_items

    has_content = bool(
        result.executive_summary
        or result.rules
        or result.derived_insights
        or result.warnings
        or result.attention_items
        or profile.get("abbreviation_rules")
    )
    profile["status"] = lp.ANALYSIS_SUCCESS if has_content else lp.ANALYSIS_NO_RELEVANT_INFORMATION

    logger.info(
        "legend_profile[%s]: LLM ok (provider=%s model=%s latency=%sms) -- "
        "%d/%d rules kept %s, %d/%d insights kept, %d attention items -> status=%s",
        document_id,
        settings.legend_llm_provider,
        settings.legend_llm_model,
        result.latency_ms,
        len(result.rules), result.raw_rule_count, result.rules_by_type(),
        len(result.derived_insights), result.raw_insight_count,
        len(result.attention_items),
        profile["status"],
    )


def get_legend_profile(document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Read-only accessor for anything that only wants to *read* an
    already-attached profile without triggering a build (e.g. API
    projection code) -- returns None if the profile was never attached."""

    profile = document.get("legend_profile")
    return profile if isinstance(profile, dict) else None
