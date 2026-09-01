"""Sole production bridge into the legend/notes project-summary feature.

``extraction_engine.py`` must only ever call ``attach_legend_profile`` from
this module -- never import ``legend_profile``/``legend_llm_provider``
directly. That keeps the LLM client, prompt, and provider selection fully
swappable behind one typed entry point: production code consumes a plain
dict profile and does not know or care which model (if any) produced its
LLM-derived fields.

Fail-safe contract: this function NEVER raises, and NEVER changes any key
on ``document`` other than ``document["legend_profile"]``. Any internal
failure (disabled flag, cache miss and extraction error, LLM error, bad
document shape) results in ``legend_profile.empty_profile(...)`` being
attached instead -- the rest of extraction always proceeds identically.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from config import settings


def attach_legend_profile(document: Dict[str, Any]) -> Dict[str, Any]:
    """Attach ``document["legend_profile"]`` and return it.

    Always sets the key (never leaves it absent) so callers/serializers
    never need to distinguish "feature disabled" from "nothing found" --
    both produce the same empty-but-well-formed shape.
    """

    from services.engineering import legend_profile as lp

    if not settings.legend_profile_enabled:
        profile = lp.empty_profile(document, llm_requested=False)
        document["legend_profile"] = profile
        return profile

    try:
        profile = _build(document)
    except Exception as exc:  # noqa: BLE001 - must never break extraction
        profile = lp.empty_profile(
            document, llm_requested=settings.legend_profile_llm_enabled
        )
        profile["llm_error"] = f"hook_error: {type(exc).__name__}: {exc}"
        document["legend_profile"] = profile
        return profile

    document["legend_profile"] = profile
    return profile


def _build(document: Dict[str, Any]) -> Dict[str, Any]:
    from services.engineering import legend_profile as lp

    llm_requested = bool(settings.legend_profile_llm_enabled)
    document_hash = lp.compute_document_hash(document)
    cache_dir = settings.legend_profile_cache_dir
    cached = lp.load_cached_profile(cache_dir, document_hash, llm_requested=llm_requested)
    if cached is not None:
        return cached

    context_pages = lp.detect_context_pages(document)
    abbreviation_rules = lp.extract_abbreviation_rules(document, context_pages)

    profile = lp.empty_profile(document, llm_requested=llm_requested)
    profile["context_pages"] = {str(k): v for k, v in context_pages.items()}
    profile["abbreviation_rules"] = abbreviation_rules

    if llm_requested:
        _apply_llm(document, context_pages, profile)

    lp.save_profile(cache_dir, profile)
    return profile


def _apply_llm(document: Dict[str, Any], context_pages: Dict[str, Any], profile: Dict[str, Any]) -> None:
    from services.engineering import legend_llm_provider as llm
    from services.engineering import legend_profile as lp

    provider = llm.get_default_provider(
        enabled=True,
        provider_name=settings.legend_profile_llm_provider,
        api_key_env=settings.legend_profile_llm_api_key_env,
        model=settings.legend_profile_llm_model,
    )
    context_text = lp.build_context_text(document, context_pages)
    summary, conventions, warnings, error = llm.propose_summary(
        context_text, provider=provider
    )
    profile["llm_model"] = settings.legend_profile_llm_model
    profile["prompt_version"] = llm.PROMPT_VERSION if error is None else None
    profile["llm_error"] = error
    profile["llm_used"] = error is None and bool(context_text.strip())
    profile["project_summary"] = summary
    profile["important_conventions"] = conventions
    profile["warnings_or_conflicts"] = warnings


def get_legend_profile(document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Read-only accessor for anything that only wants to *read* an
    already-attached profile without triggering a build (e.g. API
    projection code) -- returns None if the profile was never attached."""

    profile = document.get("legend_profile")
    return profile if isinstance(profile, dict) else None
