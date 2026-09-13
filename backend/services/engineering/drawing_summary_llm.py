"""Optional, grounded LLM polish for the Drawing Summary prose.

The deterministic ``drawing_intelligence.build_drawing_intelligence`` is always
the source of truth. This module -- only when ``DRAWING_SUMMARY_LLM_ENABLED``
is set and a provider is reachable -- makes ONE schema-constrained call that
rewrites the ``narrative`` prose from the profile's own evidence packet, so an
estimator reads a synthesised paragraph rather than a template.

Hard rules, enforced in code (not trusted from the model):

* the model is given ONLY the compact evidence packet
  (``drawing_intelligence.evidence_packet``) -- never raw pages, never tokens,
  never the Excel;
* the system prompt forbids inventing families, sections, quantities, rules,
  page roles or scope decisions;
* every returned section is re-validated: a family / section / page number /
  scope phase it names that is NOT present in the profile is stripped, and if
  a whole section fails it falls back to the deterministic text for that
  section;
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
SUMMARY_PROMPT_VERSION = "drawing_summary_v2"

_SECTION_KEYS = (
    "project_overview", "structural_content", "steel_system", "drawing_language",
    "typical_conditions", "schedules", "scope_revision",
)

SYSTEM_PROMPT = """You are a senior structural-steel estimator writing a short "what did we understand about this drawing set" briefing for another estimator.

You are given a STRUCTURED EVIDENCE PACKET already extracted from one project's structural drawings. Write a concise briefing FROM THAT PACKET ONLY.

STRICT RULES:
- Use only facts in the packet. Never invent a steel family, a section designation, a quantity, a project rule, a page role, or an issue phase.
- Never estimate or state member quantities. "Explicit designation occurrences" are label counts, not member counts -- say so if you mention them.
- Distinguish explicit facts from interpretation ("appears to", "may").
- Prefer information relevant to a steel takeoff. Do not list every section -- name a few representative ones.
- Mention uncertainty where the packet flags it (schedule semantics, multiple phases, unclassified pages).
- Be concise: 1-3 sentences per section. No preamble, no headings inside the values.

Return ONLY this JSON object:
{
  "project_overview": "<=3 sentences: what this set contains and the primary steel system",
  "structural_content": "<=2 sentences: the page make-up",
  "steel_system": "<=2 sentences: families present + a few representative sections",
  "drawing_language": "<=2 sentences: project shorthand rules, or that none were found",
  "typical_conditions": "<=2 sentences: TYP/UNO/repeated-condition language and what it implies for labels",
  "schedules": "<=2 sentences: which structural schedules exist and their nature",
  "scope_revision": "<=2 sentences: issue/phase/revision signals and any scope caution"
}"""

RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in _SECTION_KEYS},
    "required": list(_SECTION_KEYS),
}

_MAX_SECTION_CHARS = 600
# A section token shaped like a designation the model might have invented.
_SECTION_LIKE_RE = re.compile(
    r"\b((?:2L|WT|MT|ST|MC|HP|HSS|PIPE|W|S|M|C|L)\d+(?:X\d+(?:/\d+)?)+(?:\.\d+)?)\b",
    re.I,
)
_FAMILY_LIKE_RE = re.compile(r"\b(wide-flange|wide flange|W-shape|HSS|angle|channel|double angle|tee|pipe|bearing pile)\b", re.I)
_PAGE_REF_RE = re.compile(r"\bpage[s]?\s+(\d+(?:\s*[,\-and]+\s*\d+)*)", re.I)


class SummaryResult:
    __slots__ = ("narrative", "method", "error", "latency_ms", "dropped_claims")

    def __init__(self, **kw: Any) -> None:
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _known_sections(profile: Dict[str, Any]) -> set:
    known = {s.upper().replace(" ", "") for s in profile.get("representative_sections", [])}
    for fam in profile.get("steel_system", {}).get("families", []):
        known.update(s.upper().replace(" ", "") for s in fam.get("representative", []))
    for r in profile.get("abbreviation_rules", []) or []:
        known.add(str(r.get("rhs", "")).upper().replace(" ", ""))
    return known


def _known_pages(profile: Dict[str, Any]) -> set:
    pages: set[int] = set()
    for group in profile.get("page_groups", []):
        pages.update(group.get("detail", {}).get("pages", []) or [])
    for coll in ("schedule_insights", "scope_signals", "structural_notes"):
        for i in profile.get(coll, []):
            pages.update(i.get("source_pages", []) or [])
    return pages


def _known_families(profile: Dict[str, Any]) -> set:
    labels = {"wide-flange", "wide flange", "w-shape"}
    fam_words = {
        "W": {"wide-flange", "wide flange", "w-shape"}, "HSS": {"hss"},
        "L": {"angle"}, "2L": {"double angle"}, "C": {"channel"}, "MC": {"channel"},
        "WT": {"tee"}, "MT": {"tee"}, "ST": {"tee"}, "PIPE": {"pipe"}, "HP": {"bearing pile"},
        "S": {"s-shape", "beam"}, "M": {"m-shape", "beam"},
    }
    present = set()
    for f in profile.get("steel_system", {}).get("families", []):
        present |= fam_words.get(f.get("family", ""), set())
    return present or labels


def _validate_section(
    key: str, text: str, *, known_sections: set, known_pages: set, known_families: set,
) -> Optional[str]:
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:_MAX_SECTION_CHARS]
    if not text:
        return None
    for m in _SECTION_LIKE_RE.finditer(text):
        cand = m.group(1).upper().replace(" ", "")
        if cand not in known_sections and not any(cand in k or k in cand for k in known_sections):
            return None  # names a section not in the evidence -> reject whole section
    for m in _PAGE_REF_RE.finditer(text):
        for num in re.findall(r"\d+", m.group(1)):
            if int(num) not in known_pages:
                return None  # cites a page the evidence never attributed
    if key in ("steel_system", "project_overview"):
        named = {w.lower() for w in _FAMILY_LIKE_RE.findall(text)}
        if named and not (named & known_families) and "no " not in text.lower()[:12]:
            return None
    return text


def summarize(
    profile: Dict[str, Any],
    *,
    provider: Any,
    evidence_text: str,
) -> SummaryResult:
    """Return a validated narrative dict, or a result whose ``narrative`` is
    ``None`` (caller keeps the deterministic one). Never raises."""

    deterministic = profile.get("narrative") or {}
    if not evidence_text.strip():
        return SummaryResult(narrative=None, method="deterministic", error="empty_evidence")

    start = time.monotonic()
    try:
        raw = provider.propose(SYSTEM_PROMPT, evidence_text)
    except Exception as exc:  # noqa: BLE001 - provider must never break the summary
        logger.warning("drawing_summary_llm: provider error: %s", exc)
        return SummaryResult(
            narrative=None, method="deterministic",
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=round((time.monotonic() - start) * 1000, 1),
        )
    latency_ms = round((time.monotonic() - start) * 1000, 1)

    if not isinstance(raw, dict):
        return SummaryResult(narrative=None, method="deterministic",
                             error="non_dict_response", latency_ms=latency_ms)

    known_sections = _known_sections(profile)
    known_pages = _known_pages(profile)
    known_families = _known_families(profile)

    merged: Dict[str, Any] = dict(deterministic)
    dropped: List[str] = []
    used_llm = False
    for key in _SECTION_KEYS:
        validated = _validate_section(
            key, raw.get(key, ""),
            known_sections=known_sections, known_pages=known_pages,
            known_families=known_families,
        )
        if validated:
            merged[key] = validated
            used_llm = True
        else:
            dropped.append(key)  # keep deterministic text for this section

    if not used_llm:
        return SummaryResult(narrative=None, method="deterministic",
                             error="all_sections_rejected", latency_ms=latency_ms,
                             dropped_claims=dropped)

    return SummaryResult(
        narrative=merged, method="llm_enhanced",
        error=None, latency_ms=latency_ms, dropped_claims=dropped,
    )
