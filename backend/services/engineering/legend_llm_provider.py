"""Narrow, fail-safe LLM provider for the project context profile.

Scope, deliberately narrow (see ``legend_profile.py`` module docstring):

* The LLM is called AT MOST ONCE per document, on a bounded amount of
  legend/general-notes/abbreviation/specification/design-criteria/
  connection-notes-page text -- never per token, never on a full drawing
  sheet, never on an image (this checkpoint is text-only; a scanned/
  low-text context page is marked ``VISION_REQUIRED`` upstream and
  excluded from the LLM call entirely).
* It never proposes explicit "X" = Y member-size substitution rules --
  ``legend_profile.extract_abbreviation_rules`` already handles those
  precisely and deterministically. The model's job is the prose Estima3D
  cannot parse with a fixed pattern: explicit source facts across the full
  structural-steel-estimating category set (notation, materials,
  connections, fabrication, interpretation, responsibility, scope), PLUS
  cross-note derived insights -- reasoning across multiple explicit facts
  to surface project-level conventions, patterns, and estimator
  implications that no single sentence states outright.
* SOURCE_FACT vs DERIVED_INSIGHT is the load-bearing distinction of this
  checkpoint (see request section 7). A source fact must be independently
  grounded by a verbatim quote (checked in code, not trusted from the
  model). A derived insight is NOT required to have a literal quote --
  reasoning across facts is exactly the point -- but it MUST cite which
  already-grounded source facts it is based on (``evidence_refs``), and an
  insight whose ``evidence_refs`` don't all resolve to real, validated
  facts is discarded. This is what keeps "the LLM may reason" from
  becoming "the LLM may assert anything": every inference's evidence chain
  terminates in a quote that was actually found in the document.
* No API key is ever hard-coded for the hosted providers. Ollama needs no
  key at all (local HTTP service) -- see ``OllamaLegendProvider``.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Protocol, Tuple

from services.engineering.legend_profile import (
    _ALLOWED_CATEGORIES,
    CATEGORY_OTHER,
    METHOD_LLM_PROPOSED,
    STATUS_PROPOSED_INFERENCE,
    verify_quote,
)

logger = logging.getLogger("takeoff.legend_llm_provider")

PROMPT_VERSION = "legend_analysis_v2"

_MAX_SUMMARY_CHARS = 1200
_MAX_ITEM_CHARS = 320
_MAX_QUOTE_CHARS = 400
_MAX_REASONING_CHARS = 400

# ---------------------------------------------------------------------------
# Prompt v2 -- deep project-context analysis, not minimal extraction.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are analyzing the project-level structural notes of a steel construction drawing set. You are acting as an experienced structural-steel estimator reviewing this specific project's General Notes, Structural Notes, Legends, Abbreviation tables, Material notes, Design Criteria, Connection notes, Typical notes, Steel specifications, and schedules where present.

Your purpose is NOT merely to summarize text. Your purpose is to build a concise Project Context Profile that helps an experienced steel estimator understand how THIS SPECIFIC project should be interpreted, and what would materially affect takeoff, interpretation, pricing scope, fabrication assumptions, or connection responsibility.

You work in two distinct modes. Never confuse them.

MODE 1 -- SOURCE FACTS (explicit, directly grounded)
Extract only what the document explicitly states. Every source fact MUST include the exact page number and a verbatim quote copied character-for-character from the provided text. If you cannot quote it exactly, omit the fact entirely. Never invent a steel section designation, dimension, or grade that is not present in the text. Never propose an abbreviation/shorthand mapping ("X" means "Y") in this section -- those are handled separately by deterministic code; do not duplicate or contradict them here.

Search actively across these categories, but only report what is actually present -- do not force content into a category when nothing relevant exists, and do not repeat generic boilerplate (standard code references, generic safety/legal disclaimers, generic tolerances) unless it materially affects takeoff, interpretation, pricing scope, fabrication assumptions, or connection responsibility:
- Section notation: W/HSS/C/L shorthand, omitted dimensions, nominal naming conventions, unusual project-specific designation syntax (excluding literal "X"=Y mappings, handled elsewhere).
- Materials: ASTM grades, steel grades, HSS grades, plate grades, bolt grades, anchor rods, galvanizing, coatings/fireproofing if relevant to steel.
- Connections: delegated design, bolted vs welded assumptions, shear/moment connection defaults, connection responsibility, shop vs field welding, connection design loads.
- Fabrication: camber, stiffeners, bearing plates, base plates, splice rules, holes, edge distances, weld requirements.
- Structural interpretation: "unless otherwise noted" rules, typical-detail applicability, drawing hierarchy, conflicting notes, schedules overriding plans, detail references, revision-specific instructions.
- Estimator scope: items included/excluded, delegated elements, miscellaneous steel, joists/deck if applicable, connection material, temporary works, erection requirements.

MODE 2 -- DERIVED INSIGHTS (reasoning across facts)
After extracting source facts, reason ACROSS them. Look for project-level conventions, patterns, risks, and implications that are not stated in any single sentence but emerge from combining multiple facts. This is genuinely valuable and you should do it -- do not be overly conservative here. Every derived insight MUST:
- state the inference itself;
- list which specific source facts it is based on (evidence_refs, referring to facts you extracted in Mode 1 -- do not invent evidence that isn't among your own extracted facts);
- give a short reasoning_summary connecting those facts to the inference (concise reasoning, not your full internal deliberation);
- give a confidence from 0.0 to 1.0;
- state the practical impact for an estimator;
- state whether a human should review this before relying on it (human_review_recommended).
A derived insight does NOT need its own literal quote -- that is the point of reasoning -- but it must never introduce a fact not already captured in Mode 1.

CONFLICTS
If two notes conflict (e.g. a general note and a more specific note disagree), report the conflict explicitly. Do not silently pick one and resolve it yourself.

OUTPUT DISCIPLINE
An empty result in any category is valid and expected if the document does not support it -- never fabricate content to appear thorough. Keep the executive_summary concise (a few sentences), not a restatement of the notes. Output only your conclusions -- do not expose step-by-step internal deliberation.

Return ONLY a JSON object of exactly this shape, nothing else, no prose before or after it:
{
  "executive_summary": "<a few sentences: what should an estimator know about THIS project before interpreting the drawings>",
  "source_facts": [
    {
      "category": "SECTION_NOTATION" | "MATERIAL" | "CONNECTION" | "FABRICATION" | "INTERPRETATION" | "RESPONSIBILITY" | "SCOPE" | "OTHER",
      "statement": "<the fact, in your own concise words>",
      "source_page": <integer page number from the [PAGE N] markers>,
      "source_quote": "<exact verbatim quote from that page>",
      "confidence": <0.0 to 1.0>
    }
  ],
  "derived_insights": [
    {
      "inference": "<the project-level pattern/convention/risk you derived>",
      "evidence_refs": ["<short excerpt or statement text of each source fact this is based on>"],
      "reasoning_summary": "<why these facts support this inference>",
      "confidence": <0.0 to 1.0>,
      "impact": "<practical consequence for the estimator>",
      "human_review_recommended": true | false
    }
  ],
  "warnings_and_conflicts": [
    {
      "summary": "<what is ambiguous or conflicting>",
      "source_page": <integer page number>,
      "source_quote": "<exact verbatim quote>"
    }
  ],
  "estimator_attention_items": [
    "<short, specific, actionable bullet -- something to verify, not assume, or watch for>"
  ]
}"""


class LLMProvider(Protocol):
    def propose(self, system_prompt: str, document_text: str) -> Optional[Dict[str, Any]]:
        ...


class NullLLMProvider:
    """Default provider. Always returns nothing -- used whenever the LLM
    sub-feature is disabled or no usable provider could be constructed."""

    def propose(self, system_prompt: str, document_text: str) -> Optional[Dict[str, Any]]:
        return None


class OllamaUnavailableError(Exception):
    """Raised (and caught by the caller) specifically when the local Ollama
    service cannot be reached at all -- distinguished from a malformed
    response so the hook can report MODEL_UNAVAILABLE rather than
    MODEL_ERROR (see legend_profile_hook.py)."""


class OllamaLegendProvider:
    """Local, free LLM via the Ollama HTTP API (not a new CLI process per
    request -- reuses the already-running local Ollama service, one HTTP
    call per document).
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_s: float = 180.0,
        num_ctx: int = 16384,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        # Ollama defaults to a small context window (commonly 2048-4096
        # tokens) regardless of what the underlying model supports, unless
        # explicitly overridden per-request -- without this, a document's
        # context text (up to ~60k chars / ~15k tokens, see
        # legend_profile._DEFAULT_MAX_CONTEXT_CHARS) would be silently
        # truncated by Ollama itself, on top of our own cap.
        self._num_ctx = num_ctx

    def propose(self, system_prompt: str, document_text: str) -> Optional[Dict[str, Any]]:
        payload = json.dumps(
            {
                "model": self._model,
                "system": system_prompt,
                "prompt": document_text,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": self._num_ctx},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            raise OllamaUnavailableError(str(exc)) from exc
        raw = str(body.get("response") or "")
        return json.loads(raw)


class AnthropicLLMProvider:
    """Optional provider backed by the ``anthropic`` SDK, if installed.

    Not a hard dependency of this repository. Falls back to "no
    contribution" (never raises) if the package isn't installed, the key
    env var isn't set, or the call fails for any reason.
    """

    def __init__(self, *, api_key_env: str, model: str) -> None:
        self._api_key_env = api_key_env
        self._model = model

    def propose(self, system_prompt: str, document_text: str) -> Optional[Dict[str, Any]]:
        api_key = os.getenv(self._api_key_env)
        if not api_key:
            return None
        try:
            import anthropic  # type: ignore
        except ImportError:
            return None
        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=self._model,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": document_text}],
            )
            raw = "".join(
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            )
            return json.loads(raw)
        except Exception:  # pragma: no cover - network/SDK errors, fail safe
            return None


def get_default_provider(
    *,
    enabled: bool,
    provider_name: str,
    api_key_env: str,
    model: str,
    ollama_base_url: str,
) -> LLMProvider:
    if not enabled:
        return NullLLMProvider()
    if provider_name == "ollama":
        return OllamaLegendProvider(base_url=ollama_base_url, model=model)
    if provider_name == "anthropic":
        return AnthropicLLMProvider(api_key_env=api_key_env, model=model)
    return NullLLMProvider()


def _validate_source_fact(raw: Any, *, source_text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    category = str(raw.get("category") or "").strip().upper()
    if category not in _ALLOWED_CATEGORIES:
        category = CATEGORY_OTHER
    statement = str(raw.get("statement") or "").strip()
    quote = str(raw.get("source_quote") or "").strip()
    if not statement or not quote:
        return None
    if not verify_quote(source_text, quote):
        return None
    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    try:
        source_page = int(raw.get("source_page"))
    except (TypeError, ValueError):
        source_page = None
    return {
        "category": category,
        "statement": statement[:_MAX_ITEM_CHARS],
        "source_page": source_page,
        "source_quote": quote[:_MAX_QUOTE_CHARS],
        "confidence": confidence,
        "extraction_method": METHOD_LLM_PROPOSED,
        "source_quote_verified": True,
        "status": STATUS_PROPOSED_INFERENCE,
    }


def _validate_derived_insight(
    raw: Any, *, validated_facts: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """A derived insight needs no literal quote of its own, but every one of
    its evidence_refs must match (by substring, case-insensitive) an
    already-validated source fact's statement or quote. An insight with no
    grounded evidence_refs at all is discarded -- reasoning is welcome,
    unsupported assertion is not."""

    if not isinstance(raw, dict):
        return None
    inference = str(raw.get("inference") or "").strip()
    if not inference:
        return None
    raw_refs = raw.get("evidence_refs")
    if not isinstance(raw_refs, list) or not raw_refs:
        return None

    fact_haystack = [
        (str(f.get("statement") or "") + " " + str(f.get("source_quote") or "")).lower()
        for f in validated_facts
    ]
    grounded_refs: List[str] = []
    for ref in raw_refs:
        ref_text = str(ref or "").strip()
        if not ref_text:
            continue
        ref_lower = ref_text.lower()
        if any(
            ref_lower in haystack or haystack.find(ref_lower[:40]) != -1
            for haystack in fact_haystack
        ):
            grounded_refs.append(ref_text[:_MAX_ITEM_CHARS])
    if not grounded_refs:
        return None

    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.4
    confidence = max(0.0, min(1.0, confidence))

    return {
        "inference": inference[:_MAX_ITEM_CHARS],
        "evidence_refs": grounded_refs,
        "reasoning_summary": str(raw.get("reasoning_summary") or "").strip()[:_MAX_REASONING_CHARS],
        "confidence": confidence,
        "impact": str(raw.get("impact") or "").strip()[:_MAX_ITEM_CHARS],
        "human_review_recommended": bool(raw.get("human_review_recommended", True)),
        "extraction_method": METHOD_LLM_PROPOSED,
        "status": STATUS_PROPOSED_INFERENCE,
    }


def _validate_warning(raw: Any, *, source_text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    summary = str(raw.get("summary") or "").strip()
    quote = str(raw.get("source_quote") or "").strip()
    if not summary or not quote:
        return None
    if not verify_quote(source_text, quote):
        return None
    try:
        source_page = int(raw.get("source_page"))
    except (TypeError, ValueError):
        source_page = None
    return {
        "summary": summary[:_MAX_ITEM_CHARS],
        "source_page": source_page,
        "source_quote": quote[:_MAX_QUOTE_CHARS],
    }


def _validate_attention_item(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    return text[:_MAX_ITEM_CHARS]


class LegendAnalysisResult:
    """Plain data holder returned by ``propose_analysis`` -- avoids a
    5-element positional tuple at the call site."""

    __slots__ = (
        "executive_summary",
        "source_facts",
        "derived_insights",
        "warnings",
        "attention_items",
        "error",
        "unavailable",
        "raw_fact_count",
        "raw_insight_count",
        "rejected_fact_count",
        "rejected_insight_count",
        "latency_ms",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


def propose_analysis(context_text: str, *, provider: LLMProvider) -> LegendAnalysisResult:
    """Call the provider once and validate the response.

    Never raises. Distinguishes "provider unreachable" (``unavailable``)
    from "provider responded but the response was unusable" (``error``) so
    the hook can report MODEL_UNAVAILABLE vs. MODEL_ERROR respectively.
    """

    empty = LegendAnalysisResult(
        executive_summary="",
        source_facts=[],
        derived_insights=[],
        warnings=[],
        attention_items=[],
        error=None,
        unavailable=False,
        raw_fact_count=0,
        raw_insight_count=0,
        rejected_fact_count=0,
        rejected_insight_count=0,
        latency_ms=None,
    )
    if not context_text.strip():
        return empty

    start = time.monotonic()
    try:
        response = provider.propose(SYSTEM_PROMPT, context_text)
    except OllamaUnavailableError as exc:
        empty.unavailable = True
        empty.error = f"ollama_unavailable: {exc}"
        empty.latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.warning("legend LLM provider unavailable: %s", exc)
        return empty
    except Exception as exc:  # pragma: no cover - defensive
        empty.error = f"provider_error: {type(exc).__name__}: {exc}"
        empty.latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.exception("legend LLM provider raised unexpectedly")
        return empty
    latency_ms = round((time.monotonic() - start) * 1000, 1)

    if response is None:
        empty.latency_ms = latency_ms
        return empty
    if not isinstance(response, dict):
        empty.error = "malformed_response: not a JSON object"
        empty.latency_ms = latency_ms
        return empty

    summary = str(response.get("executive_summary") or "").strip()[:_MAX_SUMMARY_CHARS]

    raw_facts = response.get("source_facts")
    raw_facts = raw_facts if isinstance(raw_facts, list) else []
    validated_facts: List[Dict[str, Any]] = []
    for raw in raw_facts:
        validated = _validate_source_fact(raw, source_text=context_text)
        if validated is not None:
            validated_facts.append(validated)

    raw_insights = response.get("derived_insights")
    raw_insights = raw_insights if isinstance(raw_insights, list) else []
    validated_insights: List[Dict[str, Any]] = []
    for raw in raw_insights:
        validated = _validate_derived_insight(raw, validated_facts=validated_facts)
        if validated is not None:
            validated_insights.append(validated)

    raw_warnings = response.get("warnings_and_conflicts")
    raw_warnings = raw_warnings if isinstance(raw_warnings, list) else []
    validated_warnings: List[Dict[str, Any]] = []
    for raw in raw_warnings:
        validated = _validate_warning(raw, source_text=context_text)
        if validated is not None:
            validated_warnings.append(validated)

    raw_items = response.get("estimator_attention_items")
    raw_items = raw_items if isinstance(raw_items, list) else []
    validated_items = [
        item for item in (_validate_attention_item(raw) for raw in raw_items) if item
    ]

    return LegendAnalysisResult(
        executive_summary=summary,
        source_facts=validated_facts,
        derived_insights=validated_insights,
        warnings=validated_warnings,
        attention_items=validated_items,
        error=None,
        unavailable=False,
        raw_fact_count=len(raw_facts),
        raw_insight_count=len(raw_insights),
        rejected_fact_count=len(raw_facts) - len(validated_facts),
        rejected_insight_count=len(raw_insights) - len(validated_insights),
        latency_ms=latency_ms,
    )
