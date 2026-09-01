"""Narrow, fail-safe LLM provider for the legend/notes project-summary
profile.

Scope, deliberately narrow (see ``legend_profile.py`` module docstring):

* The LLM is called AT MOST ONCE per document, on a small, bounded amount
  of legend/general-notes/abbreviation/specification-page text -- never
  per token, never on a full drawing sheet, never on an image (this
  checkpoint is text-only; a scanned/low-text context page is marked
  ``VISION_REQUIRED`` upstream and excluded from the LLM call entirely,
  never silently skipped without a trace).
* It never proposes explicit "X" = Y member-size substitution rules --
  ``legend_profile.extract_abbreviation_rules`` already handles those
  precisely and deterministically; asking the model to also propose them
  would create two disagreeing sources for the one field closest to
  section identity. The model's job is strictly the prose Estima3D cannot
  parse with a fixed pattern: the narrative summary, and conventions/
  warnings that are not simple "X" = Y pairs (material defaults,
  connection responsibility, camber notes, "unless otherwise noted"
  rules, and similar).
* Every item the model returns is discarded unless its ``source_quote``
  is found verbatim (after only whitespace/case/Unicode normalization) in
  the exact text the model was given -- see ``_validate_proposed_item``.
  A schema-valid response is not itself proof of anything; grounding is
  checked independently of the model, in code.
* No API key is ever hard-coded. The provider reads its key from an
  environment variable name it is told to look for; if that variable is
  unset, the vendor SDK isn't installed, or the call fails/times out/
  returns malformed JSON, this module degrades to "no LLM contribution"
  rather than raising -- the deterministic profile (and the rest of the
  pipeline) is produced identically whether or not an LLM is configured.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Protocol, Tuple

from services.engineering.legend_profile import (
    _ALLOWED_CATEGORIES,
    CATEGORY_OTHER,
    METHOD_LLM_PROPOSED,
    STATUS_PROPOSED_INFERENCE,
    verify_quote,
)

PROMPT_VERSION = "legend_llm_prompt_v1"

_MAX_SUMMARY_CHARS = 600
_MAX_ITEM_SUMMARY_CHARS = 280
_MAX_QUOTE_CHARS = 400

# The entire prompt. Versioned (PROMPT_VERSION) so a later wording change
# is auditable/evaluable rather than a silent behavior change.
SYSTEM_PROMPT = """You are a structural drawing notes/legend analyst. You read \
ONLY the legend, general-notes, structural-notes, abbreviation, and \
specification pages of one structural-steel construction document, and \
extract project-specific information useful for interpreting the rest of \
the drawing set and for a steel estimator's understanding of project scope.

Rules you must follow exactly:

1. Read only the provided text. Do not assume anything about pages that \
were not given to you.
2. Extract only information that is useful for understanding this specific \
project -- not generic engineering boilerplate that would be true of any \
steel building unless it materially affects takeoff, interpretation, \
pricing scope, or estimator responsibility.
3. Prefer explicit statements over inference. If something is not stated, \
do not infer it.
4. Never invent a steel section designation, dimension, or grade that is \
not present in the text.
5. Never propose an abbreviation/shorthand mapping (e.g. "X" means "Y") \
unless the provided text actually states or clearly supports it. Do not \
guess member-size abbreviation tables -- those are handled separately.
6. For every conventions/warnings item you report, you MUST provide the \
page number and an exact, verbatim quote from the provided text that \
supports it. Never paraphrase the quote. If you cannot quote it exactly, \
omit the item entirely.
7. If a statement is ambiguous, say so in your summary rather than picking \
an interpretation.
8. If two notes conflict, report the conflict as a warning. Do not resolve \
it yourself.
9. Keep the overall project_summary short -- a few sentences at most, not \
a restatement of the notes page.
10. Do not repeat generic boilerplate (standard code references, generic \
safety notes, generic tolerances) unless it materially affects takeoff, \
interpretation, pricing scope, or estimator responsibility.
11. Treat the following as high-value when present: delegated connection \
design / responsibility language, project-specific shorthand or notation, \
unusual drafting conventions, material/grade defaults, camber conventions, \
and "unless otherwise noted" rules that change how a callout should be read.
12. An empty result is a valid, successful result. If nothing in the \
provided text is useful beyond what a generic project would already have, \
return empty lists and an empty project_summary. Do not fabricate content \
to appear useful.

Return ONLY a JSON object of exactly this shape, nothing else, no prose \
before or after it:
{
  "project_summary": "<short summary, or empty string if nothing useful>",
  "important_conventions": [
    {
      "category": "MATERIAL" | "CONNECTION" | "CAMBER" | "RESPONSIBILITY" | "GENERAL_STRUCTURAL" | "OTHER",
      "summary": "<one or two sentences>",
      "source_page": <integer page number from the [PAGE N] markers>,
      "source_quote": "<exact verbatim quote from that page>",
      "confidence": <0.0 to 1.0>
    }
  ],
  "warnings_or_conflicts": [
    {
      "summary": "<what is ambiguous or conflicting>",
      "source_page": <integer page number>,
      "source_quote": "<exact verbatim quote>"
    }
  ]
}

Do not include a "SECTION_SHORTHAND" category and do not include an \
"abbreviation_rules" field -- explicit "X" = Y member-size substitutions \
are extracted separately and you must not duplicate or contradict them."""


class LLMProvider(Protocol):
    def propose(self, system_prompt: str, document_text: str) -> Optional[Dict[str, Any]]:
        ...


class NullLLMProvider:
    """Default provider. Always returns nothing -- used whenever the LLM
    sub-feature is disabled or no usable provider could be constructed."""

    def propose(self, system_prompt: str, document_text: str) -> Optional[Dict[str, Any]]:
        return None


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
                max_tokens=1500,
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
    *, enabled: bool, provider_name: str, api_key_env: str, model: str
) -> LLMProvider:
    if not enabled:
        return NullLLMProvider()
    if provider_name == "anthropic":
        return AnthropicLLMProvider(api_key_env=api_key_env, model=model)
    return NullLLMProvider()


def _validate_convention(raw: Any, *, source_text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    category = str(raw.get("category") or "").strip().upper()
    if category not in _ALLOWED_CATEGORIES or category == "SECTION_SHORTHAND":
        category = CATEGORY_OTHER if category else None
    if category is None:
        return None
    summary = str(raw.get("summary") or "").strip()
    quote = str(raw.get("source_quote") or "").strip()
    if not summary or not quote:
        return None
    if not verify_quote(source_text, quote):
        return None
    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.4
    confidence = max(0.0, min(1.0, confidence))
    try:
        source_page = int(raw.get("source_page"))
    except (TypeError, ValueError):
        source_page = None
    return {
        "category": category,
        "summary": summary[:_MAX_ITEM_SUMMARY_CHARS],
        "source_page": source_page,
        "source_quote": quote[:_MAX_QUOTE_CHARS],
        "confidence": confidence,
        "extraction_method": METHOD_LLM_PROPOSED,
        "source_quote_verified": True,
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
        "summary": summary[:_MAX_ITEM_SUMMARY_CHARS],
        "source_page": source_page,
        "source_quote": quote[:_MAX_QUOTE_CHARS],
    }


def propose_summary(
    context_text: str, *, provider: LLMProvider
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    """Call the provider once and turn a validated response into
    (project_summary, important_conventions, warnings_or_conflicts, error).

    ``error`` is a short human-readable string (never a raw traceback) on
    any failure; in that case the three data values are always empty/blank
    -- a failed or malformed LLM call never partially applies. Never
    raises.
    """

    if not context_text.strip():
        return "", [], [], None

    try:
        response = provider.propose(SYSTEM_PROMPT, context_text)
    except Exception as exc:  # pragma: no cover - defensive
        return "", [], [], f"provider_error: {type(exc).__name__}"

    if response is None:
        return "", [], [], None
    if not isinstance(response, dict):
        return "", [], [], "malformed_response: not a JSON object"

    summary = str(response.get("project_summary") or "").strip()[:_MAX_SUMMARY_CHARS]

    raw_conventions = response.get("important_conventions")
    conventions: List[Dict[str, Any]] = []
    if isinstance(raw_conventions, list):
        for raw in raw_conventions:
            validated = _validate_convention(raw, source_text=context_text)
            if validated is not None:
                conventions.append(validated)

    raw_warnings = response.get("warnings_or_conflicts")
    warnings: List[Dict[str, Any]] = []
    if isinstance(raw_warnings, list):
        for raw in raw_warnings:
            validated = _validate_warning(raw, source_text=context_text)
            if validated is not None:
                warnings.append(validated)

    return summary, conventions, warnings, None
