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
    )
    context_text = lp.build_context_text(document, context_pages)
    profile["diagnostics"]["context_chars_available"] = sum(
        len(lp._page_text(document, p)) for p in lp._readable_context_pages(context_pages)
    )
    profile["diagnostics"]["context_chars_sent"] = len(context_text)

    result = llm.propose_analysis(context_text, provider=provider)

    profile["llm_provider"] = settings.legend_llm_provider
    profile["llm_model"] = settings.legend_llm_model
    profile["llm_latency_ms"] = result.latency_ms
    profile["llm_error"] = result.error

    profile["diagnostics"]["llm_provider"] = settings.legend_llm_provider
    profile["diagnostics"]["llm_model"] = settings.legend_llm_model
    profile["diagnostics"]["prompt_version"] = llm.PROMPT_VERSION
    profile["diagnostics"]["llm_latency_ms"] = result.latency_ms
    profile["diagnostics"]["raw_fact_count"] = result.raw_fact_count
    profile["diagnostics"]["raw_insight_count"] = result.raw_insight_count
    profile["diagnostics"]["rejected_fact_count"] = result.rejected_fact_count
    profile["diagnostics"]["rejected_insight_count"] = result.rejected_insight_count

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
    profile["source_facts"] = result.source_facts
    profile["derived_insights"] = result.derived_insights
    profile["warnings_and_conflicts"] = result.warnings
    profile["estimator_attention_items"] = result.attention_items

    has_content = bool(
        result.executive_summary
        or result.source_facts
        or result.derived_insights
        or result.warnings
        or result.attention_items
        or profile.get("abbreviation_rules")
    )
    profile["status"] = lp.ANALYSIS_SUCCESS if has_content else lp.ANALYSIS_NO_RELEVANT_INFORMATION

    logger.info(
        "legend_profile[%s]: LLM ok (provider=%s model=%s latency=%sms) -- "
        "%d/%d facts kept, %d/%d insights kept, %d warnings, %d attention items -> status=%s",
        document_id,
        settings.legend_llm_provider,
        settings.legend_llm_model,
        result.latency_ms,
        len(result.source_facts), result.raw_fact_count,
        len(result.derived_insights), result.raw_insight_count,
        len(result.warnings),
        len(result.attention_items),
        profile["status"],
    )


def get_legend_profile(document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Read-only accessor for anything that only wants to *read* an
    already-attached profile without triggering a build (e.g. API
    projection code) -- returns None if the profile was never attached."""

    profile = document.get("legend_profile")
    return profile if isinstance(profile, dict) else None
