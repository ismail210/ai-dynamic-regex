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
import re
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Protocol

from services.engineering import project_rules as pr
from services.engineering.legend_profile import verify_quote

logger = logging.getLogger("takeoff.legend_llm_provider")

# Checkpoint 4, objective #3: the model now compiles the project's drawing
# language into a typed rule profile (see services.engineering.project_rules),
# not a notes summary. Bumping this invalidates every v3 cache entry.
PROMPT_VERSION = "project_rule_profile_v1"

_MAX_SUMMARY_CHARS = 1200
_MAX_ITEM_CHARS = 320

# ---------------------------------------------------------------------------
# Prompt project_rule_profile_v1 -- compile the project's DRAWING LANGUAGE
# into a typed, machine-readable rule profile (checkpoint 4, objective #3).
#
# The legend / general notes of a structural set are not a list of notes --
# they define a project-specific shorthand for encoding member information on
# the drawing pages. The model discovers that language and states it as
# small, precise, typed rules; services.engineering.project_rules is the
# deterministic layer that validates each rule and decides what Estima3D may
# do with it (application_policy). Only LABEL_SUBSTITUTION is ever
# auto-applicable, and only through the gated resolver.
#
# Kept from v3 (checkpoint-3 findings against the 8B model): structured
# output schema (not "json" mode), a hard 3-sentence executive_summary cap,
# an explicit LOW-VALUE exclusion list, output-count caps, and the
# verbatim-quote + statement/quote-coherence validation.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert structural-steel estimator and structural-drawing reviewer. You are given only the text of ONE project's non-drawing context pages (General/Structural Notes, Legends, Abbreviation tables, framing keys, relevant specification pages), each preceded by a [PAGE N] marker.

Structural drawings encode member information in a PROJECT-SPECIFIC SHORTHAND -- a small drawing language. Your job: read these context pages and compile that language into a concise, machine-readable RULE PROFILE that a structural-steel takeoff system can use. You are NOT doing takeoff, NOT identifying drawing objects, and you must NOT invent a steel family, section, dimension or grade the text does not state.

FOR EVERY EXPLICIT PROJECT STATEMENT, decide its type:
- LABEL_SUBSTITUTION -- an abbreviated member label expands to a complete section (give `trigger` = the label exactly as written, `result` = the full designation).
- NOTATION_GRAMMAR -- a bracketed / prefixed / parenthesised / suffixed annotation encodes a value: camber, shear studs, connection reaction, top-of-steel elevation, column posting load, a frame mark. Give `grammar` as a SEMANTIC pattern (e.g. "c=<dimension>", "[n]", "[n;n;n]", "(elev)") and `field` naming what it encodes ("camber", "shear_stud_count", "shear_stud_count_by_segment", "connection_reaction", "top_of_steel_elevation", "column_posting_load", "frame_mark"). Describe the syntax -- do NOT write a regular expression.
- INHERITANCE_RULE -- a member attribute is taken from a NEIGHBOURING member when omitted. Give `trigger` (the mark, e.g. "CANT"), `condition` (when it applies), `relation` (the neighbour the value comes from, e.g. "adjacent_backspan_beam"), `inherited_field` (e.g. "section_designation"). State the RELATIONSHIP NEEDED -- never name or guess a specific member; geometry code resolves that later.
- ATTRIBUTE_DEFAULT -- a project default for material grade, finish/coating, etc.
- ORIENTATION_RULE -- fixes member orientation (e.g. HSS long side vertical UNO).
- CONNECTION_DEFAULT -- a default for connection design (default reaction, connection type, delegated design).
- SCOPE_RULE -- allocates structural-steel fabricator scope (supplemental steel, opening framing, allowances).
- DOCUMENT_PRECEDENCE -- which document/detail/schedule governs, or that info must be taken from elsewhere.
- CONFLICT_WARNING -- two project statements conflict. State it; do not resolve it.

For each rule, list which of these a takeoff system could gain (`system_benefit`, the letters that apply): A resolve an incomplete label - B parse a compound annotation - C join two text pieces into one member - D infer a missing attribute from a stated default - E a member-to-member relationship - F orientation - G interpret a reaction/camber/stud/elevation value - H connection-design assumptions - I fabricator scope - J info must come from another sheet - K a project-document conflict - L reduce unnecessary human review. Set `relevance` (CRITICAL/HIGH/MEDIUM/LOW): CRITICAL when the rule can resolve otherwise-incomplete member information or prevent review.

WRITE SMALL, PRECISE, EXECUTABLE STATEMENTS.
Bad: "the framing plans use special annotation conventions."
Good: "c=<dimension> denotes beam camber."
Bad: "cantilever rules apply."
Good: "When a steel member marked CANT has no section indicated, its section is the same as the adjacent backspan beam, UNO."
Bad: "connection reactions have project defaults."
Good: "When a beam reaction is not shown, the default factored connection reaction depends on the beam nominal depth per the project table."

`scope`: `page_roles` is where the rule applies -- ["FRAMING_PLAN"] if the note says "used on the framing plans", ["ALL"] otherwise; `uno_applies` true when the note says "UNO" / "unless noted".

EVERY rule except a derived insight needs an integer `source_page` and a `source_quote` copied character-for-character from that page. If you cannot quote it, drop the rule. A real quote paired with an unrelated statement is rejected.

DERIVED INSIGHTS: after the rules, at most 3 short cross-rule observations. Each MUST list `evidence_refs` naming the rule ids it rests on (RULE_001, RULE_002, ...). Example: "The project uses a systematic framing-plan shorthand and annotation grammar, so some apparently incomplete or isolated OCR fragments may be valid project notation rather than extraction errors." Proposed inferences only -- never executable.

LOW VALUE -- do NOT emit as rules: generic building-code citations; generic seismic / wind / snow / concrete / reinforcing / soils criteria; OSHA / safety / QA / special-inspection / submittal-procedure boilerplate; generic AISC / AWS / ASTM tolerance restatements; the contractor's duty to obtain / distribute / coordinate contract documents.

OUTPUT DISCIPLINE (a small, tight profile -- the model is a fast local one): at most 10 rules (the highest-value only), at most 2 derived_insights, at most 4 estimator_attention. Omit every field that does not apply to a rule -- do not emit empty strings. One short sentence per statement / quote / reasoning_summary / impact. executive_summary: 3 SENTENCES MAX, plain, lead with the steel material / notation / connection picture for THIS project. Output only the JSON object -- no text before or after.

Return ONLY a JSON object of this shape:
{
  "executive_summary": "<3 sentences max>",
  "rules": [
    {
      "type": "LABEL_SUBSTITUTION | NOTATION_GRAMMAR | INHERITANCE_RULE | ATTRIBUTE_DEFAULT | ORIENTATION_RULE | CONNECTION_DEFAULT | SCOPE_RULE | DOCUMENT_PRECEDENCE | CONFLICT_WARNING",
      "statement": "<one concise sentence>",
      "trigger": "<label or mark, if applicable>",
      "result": "<complete designation, for LABEL_SUBSTITUTION>",
      "grammar": "<semantic pattern, for NOTATION_GRAMMAR>",
      "field": "<what it encodes, for NOTATION_GRAMMAR>",
      "relation": "<neighbour, for INHERITANCE_RULE>",
      "inherited_field": "<field, for INHERITANCE_RULE>",
      "condition": "<when it applies, if applicable>",
      "scope": {"page_roles": ["FRAMING_PLAN"], "uno_applies": true},
      "relevance": "CRITICAL | HIGH | MEDIUM | LOW",
      "system_benefit": ["A", "L"],
      "source_page": <integer>,
      "source_quote": "<exact verbatim quote>"
    }
  ],
  "derived_insights": [
    {
      "statement": "<cross-rule observation>",
      "evidence_refs": ["RULE_001", "RULE_002"],
      "reasoning_summary": "<one line>",
      "impact": "<practical consequence>",
      "confidence": <0.0 to 1.0>
    }
  ],
  "estimator_attention": ["<short actionable bullet>"]
}"""


#: Ollama structured-output schema (passed as the request ``format``).
#: Only `type` + `statement` + `source_page` + `source_quote` are required
#: per rule -- checkpoint-3 finding: requiring every optional field makes the
#: 8B model pad. The Python validators in ``project_rules`` do the real work.
RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": sorted(pr.RULE_TYPES - {pr.DERIVED_INSIGHT})},
                    "statement": {"type": "string"},
                    "trigger": {"type": "string"},
                    "result": {"type": "string"},
                    "grammar": {"type": "string"},
                    "field": {"type": "string"},
                    "relation": {"type": "string"},
                    "inherited_field": {"type": "string"},
                    "condition": {"type": "string"},
                    "scope": {
                        "type": "object",
                        "properties": {
                            "page_roles": {"type": "array", "items": {"type": "string"}},
                            "uno_applies": {"type": "boolean"},
                        },
                    },
                    "relevance": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                    "system_benefit": {"type": "array", "items": {"type": "string"}},
                    "source_page": {"type": "integer"},
                    "source_quote": {"type": "string"},
                },
                "required": ["type", "statement", "source_page", "source_quote"],
            },
        },
        "derived_insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "reasoning_summary": {"type": "string"},
                    "impact": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["statement", "evidence_refs"],
            },
        },
        "estimator_attention": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["executive_summary", "rules", "derived_insights", "estimator_attention"],
}


def _close_truncated_json(text: str) -> str:
    """Best-effort completion of a JSON object cut off mid-generation
    (llama3.1:8b hitting num_predict on a content-rich document). Walks the
    text tracking string/bracket state and appends the closers needed to
    make it parseable, so the facts the model DID finish are recovered
    instead of the whole analysis becoming MODEL_ERROR."""

    stack: List[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    out = text
    if in_string:
        out += '"'
    out = out.rstrip().rstrip(",")
    out += "".join("}" if opener == "{" else "]" for opener in reversed(stack))
    return out


def _loads_lenient(raw: str) -> Dict[str, Any]:
    """Parse a model response that should be a JSON object.

    Structured-output mode makes a clean object the common case; this
    additionally tolerates (a) a markdown code fence or a stray leading/
    trailing sentence -- take the span from the first ``{`` to the last
    ``}`` -- and (b) a response truncated at num_predict -- close the open
    strings/brackets. Raises ``json.JSONDecodeError`` (surfaced by the
    caller as MODEL_ERROR, never MODEL_UNAVAILABLE) only if nothing parses.
    """

    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        return json.loads(text)  # re-raise the original error
    body = text[start:]
    end = body.rfind("}")
    if end != -1:
        try:
            return json.loads(body[: end + 1])
        except json.JSONDecodeError:
            pass
    return json.loads(_close_truncated_json(body))


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
        timeout_s: float = 420.0,
        num_ctx: int = 16384,
        num_predict: int = 3000,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        # Ollama defaults to a small context window (commonly 2048-4096
        # tokens) regardless of what the underlying model supports, unless
        # explicitly overridden per-request -- without this, a document's
        # context text (see legend_profile._DEFAULT_MAX_CONTEXT_CHARS,
        # ~30k chars / ~7k tokens) plus the system prompt would be silently
        # truncated by Ollama itself. num_ctx must comfortably exceed
        # input + num_predict.
        self._num_ctx = num_ctx
        # Cap generation. Checkpoint-3 real testing: with no cap, on a dense
        # document llama3.1:8b spent 2500+ tokens on one runaway
        # executive_summary paragraph and returned truncated (invalid) JSON;
        # ~3k tokens is enough for a full populated analysis of a bounded
        # context blob and bounds worst-case latency.
        self._num_predict = num_predict
        # Ollama's own timing/token fields from the most recent call
        # (nanosecond *_duration fields + *_eval_count). Read by the hook
        # for the analysis diagnostics -- see legend_profile_hook.
        self.last_run_stats: Dict[str, Any] = {}

    def propose(self, system_prompt: str, document_text: str) -> Optional[Dict[str, Any]]:
        payload = json.dumps(
            {
                "model": self._model,
                "system": system_prompt,
                "prompt": document_text,
                # Structured output: constrain generation to the response
                # schema. Checkpoint-3: plain "json" mode let the 8B model
                # bail with {} / {"error": "Error in input"} on dense
                # multi-page input; the schema makes it emit the real shape.
                "format": RESPONSE_SCHEMA,
                "stream": False,
                "options": {
                    # Factual extraction, not creativity -- deterministic.
                    "temperature": 0.0,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_ctx": self._num_ctx,
                    "num_predict": self._num_predict,
                },
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
        self.last_run_stats = {
            key: body[key]
            for key in (
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
                "done_reason",
            )
            if key in body
        }
        return _loads_lenient(str(body.get("response") or ""))


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
    ollama_num_ctx: Optional[int] = None,
    ollama_num_predict: Optional[int] = None,
    ollama_timeout_s: Optional[float] = None,
) -> LLMProvider:
    if not enabled:
        return NullLLMProvider()
    if provider_name == "ollama":
        kwargs: Dict[str, Any] = {"base_url": ollama_base_url, "model": model}
        if ollama_num_ctx:
            kwargs["num_ctx"] = ollama_num_ctx
        if ollama_num_predict:
            kwargs["num_predict"] = ollama_num_predict
        if ollama_timeout_s:
            kwargs["timeout_s"] = ollama_timeout_s
        return OllamaLegendProvider(**kwargs)
    if provider_name == "anthropic":
        return AnthropicLLMProvider(api_key_env=api_key_env, model=model)
    return NullLLMProvider()


# Words too generic to count as shared meaning between a paraphrased
# statement and its supposed source quote (or between an evidence_ref and a
# fact). Without this, "structural steel framing" alone links almost any
# two strings in a structural-notes document.
_GENERIC_WORDS = frozenset(
    {
        "shall", "steel", "project", "structural", "framing", "design",
        "connection", "connections", "contractor", "engineer", "member",
        "members", "construction", "requirements", "provide", "including",
        "attachment", "installation", "responsibility", "drawings", "detail",
        "details", "note", "notes", "system", "uses", "used", "based",
    }
)


def _content_words(text: str) -> set:
    return {
        w
        for w in re.findall(r"[a-z0-9]{4,}", text.lower())
        if w not in _GENERIC_WORDS
    }


def _statement_supported_by_quote(statement: str, quote: str) -> bool:
    """A paraphrased statement must share at least one distinctive content
    word with the verbatim quote it claims to rest on. Checkpoint 3:
    llama3.1:8b sometimes pairs a real quote from the page with a statement
    about something else entirely on that page (e.g. statement 'the project
    uses plate' with a quote listing precast-facade connection types)."""

    return bool(_content_words(statement) & _content_words(quote))


def _phrase_overlap_factory(validated_rules: List[Dict[str, Any]]):
    """A closure that decides whether a free-text evidence_ref matches a
    validated rule's statement -- by fuzzy ratio or >=3 shared distinctive
    content words (checkpoint-3 anti-pattern: a bare index or a citation
    sharing only 'construction')."""

    index = [
        (r["statement"].lower(), _content_words(r["statement"] + " " + (r.get("source_quote") or "")))
        for r in validated_rules
    ]

    def _overlap(ref_text: str) -> bool:
        if len(ref_text) < 12:
            return False
        ref_lower = ref_text.lower()
        ref_words = _content_words(ref_text)
        for statement_lower, rule_words in index:
            if SequenceMatcher(None, ref_lower, statement_lower).ratio() >= 0.5:
                return True
            if len(ref_words & rule_words) >= 3:
                return True
        return False

    return _overlap


def _validate_attention_item(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    return text[:_MAX_ITEM_CHARS] or None


class LegendAnalysisResult:
    """Plain data holder returned by ``propose_analysis`` (a rule profile
    since checkpoint 4 -- see services.engineering.project_rules)."""

    __slots__ = (
        "executive_summary",
        "rules",
        "derived_insights",
        "drawing_language",
        "warnings",
        "attention_items",
        "error",
        "unavailable",
        "raw_rule_count",
        "rejected_rule_count",
        "raw_insight_count",
        "rejected_insight_count",
        "latency_ms",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))

    def rules_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for rule in self.rules or []:
            counts[rule["type"]] = counts.get(rule["type"], 0) + 1
        return counts


def _empty_result() -> "LegendAnalysisResult":
    return LegendAnalysisResult(
        executive_summary="",
        rules=[],
        derived_insights=[],
        drawing_language=[],
        warnings=[],
        attention_items=[],
        error=None,
        unavailable=False,
        raw_rule_count=0,
        rejected_rule_count=0,
        raw_insight_count=0,
        rejected_insight_count=0,
        latency_ms=None,
    )


def propose_analysis(
    context_text: str,
    *,
    provider: LLMProvider,
    abbreviation_rules: Optional[List[Dict[str, Any]]] = None,
) -> LegendAnalysisResult:
    """Call the provider once and validate the rule profile.

    Never raises. Distinguishes "provider unreachable" (``unavailable``)
    from "provider responded but the response was unusable" (``error``) so
    the hook can report MODEL_UNAVAILABLE vs. MODEL_ERROR respectively.

    ``abbreviation_rules`` are the deterministic ``"X" = Y`` rules from
    ``legend_profile`` -- passed in only so the human-readable
    ``drawing_language`` bullets can mention them; they are the LABEL_
    SUBSTITUTION source of truth and are NOT re-derived from the model.
    """

    empty = _empty_result()
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

    raw_rules = response.get("rules")
    raw_rules = raw_rules if isinstance(raw_rules, list) else []
    validated_rules: List[Dict[str, Any]] = []
    next_id = 1
    for raw in raw_rules:
        rule = pr.validate_rule(
            raw,
            source_text=context_text,
            verify_quote=verify_quote,
            statement_supported_by_quote=_statement_supported_by_quote,
            next_id=next_id,
        )
        if rule is not None:
            validated_rules.append(rule)
            next_id += 1

    valid_ids = {r["id"] for r in validated_rules}
    overlap = _phrase_overlap_factory(validated_rules)
    raw_insights = response.get("derived_insights")
    raw_insights = raw_insights if isinstance(raw_insights, list) else []
    validated_insights: List[Dict[str, Any]] = []
    for raw in raw_insights:
        insight = pr.validate_insight(
            raw, validated_rule_ids=valid_ids, phrase_overlap=overlap
        )
        if insight is not None:
            validated_insights.append(insight)

    warnings = [
        {
            "summary": r["statement"],
            "source_page": r.get("source_page"),
            "source_quote": r.get("source_quote"),
        }
        for r in validated_rules
        if r["type"] == pr.CONFLICT_WARNING
    ]

    raw_items = response.get("estimator_attention") or response.get("estimator_attention_items")
    raw_items = raw_items if isinstance(raw_items, list) else []
    validated_items = [i for i in (_validate_attention_item(x) for x in raw_items) if i]

    drawing_language = pr.build_drawing_language(
        rules=validated_rules, abbreviation_rules=abbreviation_rules or []
    )

    return LegendAnalysisResult(
        executive_summary=summary,
        rules=validated_rules,
        derived_insights=validated_insights,
        drawing_language=drawing_language,
        warnings=warnings,
        attention_items=validated_items,
        error=None,
        unavailable=False,
        raw_rule_count=len(raw_rules),
        rejected_rule_count=len(raw_rules) - len(validated_rules),
        raw_insight_count=len(raw_insights),
        rejected_insight_count=len(raw_insights) - len(validated_insights),
        latency_ms=latency_ms,
    )
