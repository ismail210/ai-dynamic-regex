"""Optional, grounded LLM selection for the Drawing Summary.

The deterministic ``drawing_intelligence.build_drawing_intelligence`` is always
the source of truth: it reads the schedule definitions, interpretation rules
and unresolved items from extracted evidence. This module -- only when
``DRAWING_SUMMARY_LLM_ENABLED`` is set and a provider is reachable -- makes ONE
schema-constrained call in which the model SELECTS the takeoff-relevant facts
by id, explains each in one sentence, and writes a short overview.

Hard rules, enforced in code (not trusted from the model):

* the model sees ONLY ``drawing_intelligence.evidence_packet`` -- never raw
  pages, tokens or the Excel -- and can only cite fact ids from it;
* an item citing an unknown id, or whose text names a mark / section / plate
  size / sheet / page that is not in the cited fact, or that states a
  quantity, is dropped (recorded in ``dropped_claims``);
* a rejected overview falls back to the deterministic one;
* the call NEVER raises and NEVER changes anything outside the returned dict.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("takeoff.drawing_summary_llm")

# v2: the Ollama provider now receives THIS module's RESPONSE_SCHEMA as its
# structured-output ``format`` (previously it pinned the project-rule schema,
# so the model could never emit these section keys and every summary silently
# fell back to deterministic). Bumping invalidates v1 summary cache entries
# that recorded the all-sections-rejected fallback.
SUMMARY_PROMPT_VERSION = "drawing_summary_v3"

SYSTEM_PROMPT = """You are a senior structural-steel estimator. You receive an EVIDENCE PACKET extracted from one project's structural drawings. Every usable fact has an id in square brackets: [D#] schedule definitions, [R#] rules affecting interpretation, [U#] unresolved items.

Your job is to SELECT the facts an estimator needs before a steel takeoff and explain each in one short sentence. You cannot add facts.

RULES:
- Cite facts only by their ids. Never write a mark, section, plate size, rule, sheet or page that is not in the fact you cite.
- Keep marks distinct: L1 and L1A are different marks even when the section is the same. Keep each mark in its own schedule: C1 is a column mark, CL1 an ICF lintel mark, BP1 a bearing plate mark, L1 a lintel mark.
- A schedule definition explains how to read a mark on a plan. It is NOT a member count. Never state or estimate how many beams, columns, lintels, plates or studs there are.
- TYP, U.N.O. and SIM apply only to the condition they annotate.
- Do not describe drawing types or how often labels appear.
- "why" must say what the fact changes when reading the plans (which section or plate a callout means, when a default applies, what to check). Do not just restate the fact.

Return ONLY this JSON object:
{
  "overview": "1-2 sentences: what this set is and where its mark definitions are",
  "key_facts": [{"id": "D1", "why": "max 25 words: why this definition matters for takeoff"}],
  "cautions": [{"id": "U1", "why": "max 25 words: how this rule or open item changes interpretation"}]
}
key_facts: up to 8 ids of [D#] or [R#] facts. cautions: up to 5 ids of [R#] or [U#] facts."""

_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "why": {"type": "string"}},
        "required": ["id", "why"],
    },
}
RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "key_facts": _ITEM_SCHEMA,
        "cautions": _ITEM_SCHEMA,
    },
    "required": ["overview", "key_facts", "cautions"],
}

_LISTS = {"key_facts": (("D", "R"), 8), "cautions": (("R", "U"), 5)}
_MAX_WHY_CHARS = 220
_MAX_OVERVIEW_CHARS = 420
# Anything the model could state as a fact: a designation, a schedule mark, a
# printed plate/angle size, a sheet number or a page reference.
_ANCHOR_RES = (
    re.compile(r"\b(?:2L|WT|MT|ST|MC|HP|HSS|PIPE|W|S|M|C|L)\d+(?:\.\d+)?(?:\s*[xX×]\s*[\d./-]+)+", re.I),
    re.compile(r"\b(?:BP|CL|C|L)\d{1,2}[A-Z]?\b(?!\s*[xX×\d./])", re.I),
    re.compile(r"\d+(?:\.\d+)?\"?\s*[xX×]\s*\d+(?:\.\d+)?\"?(?:\s*[xX×]\s*[\d\s/.-]+\"?)?"),
    re.compile(r"\bS-?\d{3}[A-Z]?\b", re.I),
)
_PAGE_RE = re.compile(r"\b(?:PDF\s+)?(?:pages?|pp?\.)\s*(\d+)", re.I)
_QUANTITY_RE = re.compile(
    # a standalone count -- not the tail of a size such as HSS6X6X1/2
    r"(?<![\w/.\-\"])(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|several|many)\s+"
    r"(?:[a-z-]+\s+){0,2}(?:beams?|columns?|lintels?|members?|pieces?|plates?|studs?|angles?|girders?|joists?)\b"
    r"|\b(?:quantity|quantities|count of|total of|number of)\b",
    re.I,
)


class SummaryResult:
    __slots__ = ("summary", "method", "error", "latency_ms", "dropped_claims")

    def __init__(self, **kw: Any) -> None:
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _anchors(text: str) -> set:
    found = {
        re.sub(r"[\s\"]", "", m.group(0)).upper().replace("×", "X")
        for pattern in _ANCHOR_RES for m in pattern.finditer(text)
    }
    return found | {f"P{m.group(1)}" for m in _PAGE_RE.finditer(text)}


# Words a note may add without adding information ("Defines the section for
# lintel mark L1" only restates the row it cites).
_FILLER_WORDS = frozenset(
    "the a an for of this that is are to on in with and or by as at it its mark marks "
    "defines define defined definition section sections plate plates size schedule "
    "lintel lintels column columns bearing unless noted otherwise default".split()
)


def _restates(why: str, fact: str) -> bool:
    fact_words = set(re.findall(r"[a-z]+", fact.lower()))
    return not (set(re.findall(r"[a-z]+", why.lower())) - fact_words - _FILLER_WORDS)


def _grounded(text: str, evidence: str, limit: int) -> Optional[str]:
    """``text`` if every anchor it names is in ``evidence`` and it states no
    quantity; otherwise ``None``."""

    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text or len(text) > limit or _QUANTITY_RE.search(text):
        return None
    return text if _anchors(text) <= _anchors(evidence) else None


def summarize(
    profile: Dict[str, Any],
    *,
    provider: Any,
    evidence_text: str,
) -> SummaryResult:
    """Validated ``{"overview", "overview_source", "key_facts", "cautions"}``,
    or ``summary=None`` (the deterministic summary stands). Never raises."""

    from services.engineering.drawing_intelligence import evidence_facts

    if not evidence_text.strip():
        return SummaryResult(summary=None, method="deterministic", error="empty_evidence")

    start = time.monotonic()
    try:
        raw = provider.propose(SYSTEM_PROMPT, evidence_text)
    except Exception as exc:  # noqa: BLE001 - provider must never break the summary
        logger.warning("drawing_summary_llm: provider error: %s", exc)
        return SummaryResult(
            summary=None, method="deterministic",
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=round((time.monotonic() - start) * 1000, 1),
        )
    latency_ms = round((time.monotonic() - start) * 1000, 1)

    if not isinstance(raw, dict):
        return SummaryResult(summary=None, method="deterministic",
                             error="non_dict_response", latency_ms=latency_ms)

    facts = evidence_facts(profile)
    dropped: List[str] = []
    summary: Dict[str, Any] = {"key_facts": [], "cautions": []}
    for key, (prefixes, limit) in _LISTS.items():
        items = raw.get(key) if isinstance(raw.get(key), list) else []
        seen: set = set()
        for item in items:
            item = item if isinstance(item, dict) else {}
            fact_id = str(item.get("id") or "").strip().upper()
            why = str(item.get("why") or "")
            grounded = None
            if (fact_id in facts and fact_id.startswith(prefixes)
                    and fact_id not in seen and len(seen) < limit
                    and not _restates(why, facts[fact_id])):
                grounded = _grounded(why, facts[fact_id], _MAX_WHY_CHARS)
            if grounded:
                seen.add(fact_id)
                summary[key].append({"id": fact_id, "why": grounded})
            else:
                dropped.append(f"{key}:{fact_id or '?'}")

    raw_overview = raw.get("overview")
    overview = (
        _grounded(raw_overview, evidence_text, _MAX_OVERVIEW_CHARS)
        if isinstance(raw_overview, str) else None
    )
    if overview is None:
        dropped.append("overview")
    summary["overview"] = overview or str(profile.get("overview") or "")
    summary["overview_source"] = "llm" if overview else "deterministic"

    if not overview and not summary["key_facts"] and not summary["cautions"]:
        return SummaryResult(summary=None, method="deterministic",
                             error="all_claims_rejected", latency_ms=latency_ms,
                             dropped_claims=dropped)
    return SummaryResult(summary=summary, method="llm_enhanced", error=None,
                         latency_ms=latency_ms, dropped_claims=dropped)
