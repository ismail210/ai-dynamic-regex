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
# v4: typed column / plate, level, conflict, material and notation facts
# (X / K / C / M / G ids) join the packet, and grounding also checks
# dimensions, elevations, grid locations and forbidden certainty claims.
SUMMARY_PROMPT_VERSION = "drawing_summary_v5"

SYSTEM_PROMPT = """You are a senior structural-steel estimator. You receive an EVIDENCE PACKET extracted from one project's structural drawings. Every usable fact has an id in square brackets: [I#] complete coverage counts per schedule and table, [X#] disagreements between different sources, [K#] schedule levels linked to plan notes, [C#] representative column entries with their plate, [M#] materials a schedule note states, [G#] location notation, [D#] schedule definitions, [R#] rules affecting interpretation, [U#] unresolved items.

Your job is to SELECT the facts an estimator needs before a steel takeoff and explain each in one short sentence. You cannot add facts.

RULES:
- Cite facts only by their ids. Never write a mark, section, plate size, dimension, elevation, grid location, sheet or page that is not in the fact you cite.
- Keep marks distinct: L1 and L1A are different marks even when the section is the same. Keep each mark in its own schedule: C1 is a column mark, CL1 an ICF lintel mark, BP1 a bearing plate mark, L1 a lintel mark.
- A schedule entry or definition explains how to read the drawing. It is NOT a member count and NOT an installed member. Never state or estimate how many beams, columns, lintels, plates or studs there are.
- A conflict [X#] is between different sources (a plan note, a schedule, a section), never inside one schedule. Never say which value is correct, never average them and never call either a typo.
- An elevation difference between two levels is NOT a column or member length.
- A column the facts call precast or concrete is not steel.
- A grid offset is part of a location; it does not confirm where a member is placed.
- [C#] facts are selected examples, not the complete schedule; only [I#] facts give complete counts, and those count printed records, not members.
- TYP, U.N.O. and SIM apply only to the condition they annotate.
- "why" must say what the fact changes when reading the plans (which section or plate a callout means, which value to check, what to confirm). Do not just restate the fact.

Return ONLY this JSON object:
{
  "overview": "1-2 sentences: what this set is and where its column, plate and level information is",
  "key_facts": [{"id": "C1", "why": "max 25 words: why this matters for takeoff"}],
  "cautions": [{"id": "X1", "why": "max 25 words: what to check or confirm"}]
}
key_facts: up to 8 ids of [I#], [C#], [K#], [M#], [G#], [D#] or [R#] facts. cautions: up to 5 ids of [X#], [R#] or [U#] facts."""

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

_LISTS = {"key_facts": (("I", "C", "K", "M", "G", "D", "R"), 8), "cautions": (("X", "R", "U"), 5)}
_MAX_WHY_CHARS = 220
_MAX_OVERVIEW_CHARS = 420
# Anything the model could state as a fact: a designation, a schedule mark, a
# printed plate/angle size, a sheet number or a page reference.
_ANCHOR_RES = (
    re.compile(r"\b(?:2L|WT|MT|ST|MC|HP|HSS|PIPE|W|S|M|C|L)\d+(?:\.\d+)?(?:\s*[xX×]\s*[\d./-]+)+", re.I),
    # A mark (CBP-2, C1, W10): not the start of a size (W10X..) or a decimal; a full stop may follow.
    re.compile(r"\b[A-Z]{1,4}[-_]?\d{1,5}[A-Z]{0,2}(?:X\d{1,2})?\b(?!\s*[xX×]|[\d/]|\.\d)", re.I),
    re.compile(r"\d+(?:\.\d+)?\"?\s*[xX×]\s*\d+(?:\.\d+)?\"?(?:\s*[xX×]\s*[\d\s/.-]+\"?)?"),
    re.compile(r"\bS-?\d{3}[A-Z]?\b", re.I),
)
_PAGE_RE = re.compile(r"\b(?:PDF\s+)?(?:pages?|pp?\.)\s*(\d+)", re.I)
_QUANTITY_RE = re.compile(
    # a standalone count -- not the tail of a size such as HSS6X6X1/2
    # (a level / floor / grid number -- "LEVEL 2 in column schedule" -- is not a count)
    r"(?<![\w/.\-\"])(?<!LEVEL\s)(?<!FLOOR\s)(?<!GRID\s)"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|several|many)\s+"
    r"(?:[a-z-]+\s+){0,2}(?:beams?|columns?|lintels?|members?|pieces?|plates?|studs?|angles?|girders?|joists?)\b"
    r"|\b(?:quantity|quantities|(count of|total of|number of))\b",
    re.I,
)


class SummaryResult:
    __slots__ = ("summary", "method", "error", "latency_ms", "dropped_claims")

    def __init__(self, **kw: Any) -> None:
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


# Measured values: feet-inches (55'-10", 55' - 10", 8") and grid locations
# (C.8-8.9, C.1(-6")-7.3). Compared by value, so 55'-10" and 55' - 10" match
# and 55'-2" does not.
_LENGTH_SPAN_RE = re.compile(
    r"(?<![\w.'′/])[-+−]?\s*(?:\d+\s*['′]\s*-?\s*)?(?:\d+(?:\s+\d+/\d+|-\d+/\d+)?|\d+/\d+)\s*[\"″]"
)
_GRID_LOCATION_RE = re.compile(r"\b[A-Z]{1,3}\d{0,3}(?:\.\d{1,3})?['′]*(?:\([^)]*\))?-\d{1,3}(?:\.\d{1,3})?['′]*(?!\w|\.\d)")


def _measures(text: str) -> set:
    """Each printed length, by value (``column_schedule.parse_length``)."""

    from services.engineering.column_schedule import parse_length

    found = set()
    for m in _LENGTH_SPAN_RE.finditer(text.replace("″", '"').replace("′", "'")):
        value = parse_length(m.group(0).replace("−", "-"))
        if value:
            found.add(f"L{value['inches']:g}")
    return found


def _anchors(text: str) -> set:
    found = {
        re.sub(r"[\s\"]", "", m.group(0)).upper().replace("×", "X").rstrip(".-/")
        for pattern in _ANCHOR_RES for m in pattern.finditer(text)
    }
    found |= {"G" + re.sub(r"\s", "", m.group(0)).upper() for m in _GRID_LOCATION_RE.finditer(text)}
    return found | _measures(text) | {f"P{m.group(1)}" for m in _PAGE_RE.finditer(text)}


# Certainty the evidence never grants: choosing between conflicting values,
# a level difference read as a member length, schedule entries read as
# installed members, an offset read as a confirmed placement, and a column a
# fact calls precast / concrete called steel.
_CLAIM_RULES = (
    (re.compile(r"\b(?:correct(?:ed)?|average|actual|typo|mistake|resolved|governs)\b", re.I),
     re.compile(r"\b(?:not|never|un)(?:\s+\w+){0,4}\s*(?:correct|resolved|governs)\b|\bwhich\s+(?:\w+\s+)?governs\b",
                re.I)),
    (re.compile(r"\blength\b|[\"″]\s*long\b", re.I), re.compile(r"\bnot\s+(?:a\s+)?(?:\w+\s+){0,2}length\b", re.I)),
    (re.compile(r"\binstalled\b", re.I), re.compile(r"\bnot\s+(?:an?\s+)?installed\b", re.I)),
    (re.compile(r"\bconfirm(?:s|ed)?\s+(?:the\s+)?(?:placement|position|location)\b|\bis\s+placed\b", re.I), None),
)


_INSIDE_SCHEDULE_RE = re.compile(
    r"\bschedules?\b[^.]{0,30}\b(?:has|have|contains?|shows?|lists?|gives?)\b[^.]{0,25}\b(?:conflict\w*|inconsistent|"
    r"contradict\w*)|\b(?:conflict\w*|inconsisten\w*|contradict\w*)[^.]{0,40}\b(?:in|within|inside)\s+(?:the\s+)?"
    r"(?:column\s+)?schedules?\b", re.IGNORECASE)


# A value cut off mid-way: "(55' - 10" -- feet and inches without the inch
# mark, or a bracket that never closes.
_PARTIAL_MEASURE_RE = re.compile(r"\d+\s*['′]\s*-\s*\d+(?:\s+\d+/\d+)?(?!\s*(?:\d+/\d+\s*)?[\"″])(?!\d)")


def _claims_ok(text: str, fact: str, kind: Optional[str] = None) -> bool:
    """``kind``: the cited fact's id letter (``X`` conflict, ``M`` material,
    ...) or ``overview``; rules about one fact type apply to that type."""

    if _PARTIAL_MEASURE_RE.search(text) or any(text.count(a) != text.count(b) for a, b in ("()", "[]", "{}")):
        return False
    for claim, allowed in _CLAIM_RULES:
        if claim.search(text) and not (allowed and allowed.search(text)):
            return False
    # A conflict is between two sources; a claim of one must say what disagrees
    # ("schedule and plan", "the sources"), not place it inside one source.
    if (kind in ("X", "overview") and re.search(r"\b(?:conflict\w*|disagree\w*|differs|differing)\b", text, re.I)
            and not re.search(r"\b(?:plan|plans|sources?|between|versus|vs\.?|against)\b", text, re.I)):
        return False
    # ... and never inside the schedule ("the schedule has conflicting elevations").
    if kind in ("X", "overview") and _INSIDE_SCHEDULE_RE.search(text):
        return False
    # A fact that says precast / concrete: the text may not call those columns steel.
    if (kind in ("M", "D", "I", "C", "overview") and re.search(r"\b(?:precast|concrete)\b", fact, re.I)
            and re.search(r"\b(?:are|is|as)\s+(?:an?\s+)?(?:\w+\s+)?steel\b|\bsteel\s+columns?\b(?!\s+schedule)", text, re.I)
            and not re.search(r"\bnot\s+(?:\w+\s+)?steel\b", text, re.I)):
        return False
    return True


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


def _grounded(text: str, evidence: str, limit: int, kind: Optional[str] = None) -> Optional[str]:
    """``text`` if every anchor it names is in ``evidence`` and it states no
    quantity; otherwise ``None``."""

    text = re.sub(r"\s+", " ", str(text or "")).strip()
    # An [I#] fact is a count of printed records, so "count of" may name it; a member count never passes.
    quantity = any(
        m.group(1) is None or kind != "I"
        or not re.match(r"\s+printed\s+(?:location\s+)?(?:entries|records|rows)\b", text[m.end():], re.IGNORECASE)
        for m in _QUANTITY_RE.finditer(text)
    )
    if not text or len(text) > limit or quantity or not _claims_ok(text, evidence, kind):
        return None
    record_counts = re.findall(r"\b(\d+)\s+printed\s+(?:location\s+)?(?:entries|records|rows)\b", text, re.IGNORECASE)
    if any(not re.search(rf"\b{count}\s+printed\s+(?:location\s+)?(?:entries|records|rows)\b", evidence, re.IGNORECASE)
           for count in record_counts):
        return None
    # A mark named only to rule it out ("..., not L1") asserts nothing about it.
    asserted = re.sub(r"\bnot\s+(?:an?\s+)?[A-Z]{1,4}[-_]?\d{1,5}[A-Z]{0,2}\b", " ", text)
    return text if _anchors(asserted) <= _anchors(evidence) else None


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
            if re.fullmatch(r"\[[A-Z]\d+\]", fact_id):
                fact_id = fact_id[1:-1]  # the model may echo a known id as "[C1]"
            why = str(item.get("why") or "")
            grounded = None
            if (fact_id in facts and fact_id.startswith(prefixes)
                    and fact_id not in seen and len(seen) < limit
                    and not _restates(why, facts[fact_id])):
                grounded = _grounded(why, facts[fact_id], _MAX_WHY_CHARS, fact_id[0])
            if grounded:
                seen.add(fact_id)
                summary[key].append({"id": fact_id, "why": grounded})
            else:
                dropped.append(f"{key}:{fact_id or '?'}")

    raw_overview = raw.get("overview")
    overview = (
        _grounded(raw_overview, evidence_text, _MAX_OVERVIEW_CHARS, "overview")
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
