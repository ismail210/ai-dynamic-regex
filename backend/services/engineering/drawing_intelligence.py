"""Drawing Intelligence Profile -- a structured, evidence-grounded machine
description of *what Estima3D understood about a structural drawing set*.

This is the MACHINE STRUCTURE half of the Drawing Summary (the HUMAN SUMMARY
prose is rendered from it -- deterministically here, or optionally polished by
a schema-constrained LLM in ``drawing_summary_llm``). Every field is derived
from data the extraction stage already produced (``pages``, ``blocks`` /
``lines``, ``engineering_tokens``, ``schedules``, ``title_blocks``, the legend
profile's ``context_pages`` / ``abbreviation_rules``). It reads no image, runs
no model, and -- like the legend profile it is attached to -- never mutates a
token, candidate, ranking, prediction or takeoff quantity. It never sees the
ground-truth Excel.

Contract, mirroring ``legend_profile``:

* every ``Insight`` carries ``source_pages`` + a verbatim ``source_text``
  snippet + ``method`` (``deterministic`` / ``llm_extracted``);
* claims are only made where the extracted evidence supports them -- an
  absent signal produces an explicit "none found" statement, never a guess;
* ``narrative`` is a rendered, deterministic fallback that is always usable
  even with no LLM and no provider.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.database_loader import catalog_form

DRAWING_INTELLIGENCE_VERSION = "drawing_intelligence_v1"

_METHOD_DETERMINISTIC = "deterministic"
_METHOD_LLM = "llm_extracted"

_SNIPPET_MAX = 240
_MAX_REPRESENTATIVE_PER_FAMILY = 4
_MAX_TYP_EXAMPLES = 5
_MAX_NOTES = 8


# --------------------------------------------------------------------------
# Insight container
# --------------------------------------------------------------------------
@dataclass
class Insight:
    """One grounded observation about the drawing set."""

    type: str
    value: str
    confidence: float
    source_pages: List[int] = field(default_factory=list)
    source_text: str = ""
    scope: str = "document"          # document | page | region
    method: str = _METHOD_DETERMINISTIC
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["source_text"] = (self.source_text or "")[:_SNIPPET_MAX]
        return data


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


# --------------------------------------------------------------------------
# Page text access (self-contained; never shares a helper with document_prior
# or legend_profile -- same rationale as legend_profile._page_text)
# --------------------------------------------------------------------------
def _page_texts(document: Dict[str, Any]) -> Dict[int, str]:
    by_page: Dict[int, List[str]] = defaultdict(list)
    blocks = document.get("blocks") or []
    if blocks:
        for block in blocks:
            page = int(block.get("page_number") or 0)
            if page:
                by_page[page].append(str(block.get("text") or ""))
    if not by_page:
        for line in document.get("lines") or []:
            page = int(line.get("page_number") or 0)
            if page:
                by_page[page].append(str(line.get("text") or ""))
    return {page: "\n".join(chunks) for page, chunks in by_page.items()}


def _full_text(document: Dict[str, Any], page_texts: Dict[int, str]) -> str:
    text = str(document.get("text") or "")
    if text.strip():
        return text
    return "\n".join(page_texts[p] for p in sorted(page_texts))


# --------------------------------------------------------------------------
# 1. Page groups -- classify EVERY page into a structural category
# --------------------------------------------------------------------------
_PAGE_CATEGORY_RULES: Tuple[Tuple[str, str, re.Pattern[str]], ...] = (
    ("drawing_index", "Drawing index / cover",
     re.compile(r"\bDRAWING\s+INDEX\b|\bSHEET\s+INDEX\b|\bDRAWING\s+SCHEDULE\b|\bLIST\s+OF\s+DRAWINGS\b", re.I)),
    ("roof_framing", "Roof framing plans",
     re.compile(r"\bROOF\s+FRAMING\s+PLAN\b|\b(?:LOW|HIGH|MAIN)\s+ROOF\s+PLAN\b|\bROOF\s+PLAN\b", re.I)),
    ("floor_framing", "Floor / level framing plans",
     re.compile(r"\b(?:\w+\s+)?FLOOR\s+FRAMING\s+PLAN\b|\bLEVEL\s+\d+\s+FRAMING\b|\bFRAMING\s+PLAN\b|\b(?:SECOND|THIRD|FOURTH|MEZZANINE|PENTHOUSE)\s+FLOOR\s+PLAN\b", re.I)),
    ("column_plan", "Column plans",
     re.compile(r"\bCOLUMN\s+PLAN\b|\bCOLUMN\s+LAYOUT\b|\bANCHOR\s+(?:BOLT|ROD)\s+PLAN\b", re.I)),
    ("foundation", "Foundation plans",
     re.compile(r"\bFOUNDATION\s+PLAN\b|\bFOOTING\s+PLAN\b|\bPILE\s+(?:CAP\s+)?PLAN\b|\bMAT\s+(?:SLAB|FOUNDATION)\b", re.I)),
    ("bracing", "Bracing / braced-frame sheets",
     re.compile(r"\bBRACED\s+FRAME\b|\bBRACE(?:D)?\s+ELEVATION\b|\bBRACING\s+(?:PLAN|ELEVATION)\b|\bVERTICAL\s+BRACING\b", re.I)),
    ("schedule", "Schedules",
     re.compile(r"\bCOLUMN\s+SCHEDULE\b|\bBEAM\s+SCHEDULE\b|\bBRAC(?:E|ING)\s+SCHEDULE\b|\bFRAMING\s+SCHEDULE\b|\bJOIST\s+SCHEDULE\b|\bLINTEL\s+SCHEDULE\b|\bBASE\s+PLATE\s+SCHEDULE\b|\bFOOTING\s+SCHEDULE\b", re.I)),
    ("elevation_section", "Elevations / sections",
     re.compile(r"\bBUILDING\s+SECTION\b|\bWALL\s+SECTION\b|\bSTRUCTURAL\s+SECTION\b|\bBUILDING\s+ELEVATION\b|\bFRAME\s+ELEVATION\b", re.I)),
    ("details", "Typical details",
     re.compile(r"\bTYPICAL\s+DETAILS?\b|\b(?:STEEL|FRAMING|CONNECTION|BRACE)\s+DETAILS?\b|\bDETAIL\s+SHEET\b|\bSTANDARD\s+DETAILS?\b", re.I)),
    ("notes_legend", "General notes / legend",
     re.compile(r"\bGENERAL\s+NOTES?\b|\bSTRUCTURAL\s+NOTES?\b|\bSTEEL\s+NOTES?\b|\bLEGEND\b|\bABBREVIATIONS?\b|\bDESIGN\s+CRITERIA\b|\bSYMBOLS\b", re.I)),
)

_PERSPECTIVE_RE = re.compile(r"\bPERSPECTIVE\b|\bAXONOMETRIC\b|\bISOMETRIC\s+VIEW\b|\b3D\s+VIEW\b", re.I)
_TITLE_HINT_LEN = 900  # look at the start of a page's text for its sheet title


def _classify_pages(
    document: Dict[str, Any],
    page_texts: Dict[int, str],
    context_pages: Dict[str, str],
) -> Tuple[List[Insight], Dict[int, str]]:
    """Assign every readable page a category. ``notes_legend`` defers to the
    legend profile's own ``context_pages`` verdict where it has one."""

    page_count = int(document.get("page_count") or 0)
    ctx = {int(k): v for k, v in (context_pages or {}).items()}
    page_meta = {int(p.get("page_number") or 0): p for p in (document.get("pages") or [])}

    category_of: Dict[int, str] = {}
    uncertain: List[int] = []
    for page in range(1, page_count + 1):
        text = page_texts.get(page, "")
        head = text[:_TITLE_HINT_LEN]
        meta = page_meta.get(page, {})
        if meta.get("unreadable") or not text.strip():
            category_of[page] = "unreadable"
            continue
        if page in ctx:
            category_of[page] = "notes_legend"
            continue
        matched = None
        for key, _label, pattern in _PAGE_CATEGORY_RULES:
            if pattern.search(head) or pattern.search(text):
                matched = key
                break
        if matched is None and _PERSPECTIVE_RE.search(head):
            matched = "perspective"
        if matched is None:
            # Fall back on structural signal: a page dense with real section
            # tokens and a low text ratio is almost always a framing plan.
            occ, _distinct = _catalog_section_counts(text)
            score = int(meta.get("engineering_relevance_score") or 0)
            if occ >= 8 or score >= 8:
                matched = "framing_plan_unlabeled"
            else:
                matched = "other"
                uncertain.append(page)
        category_of[page] = matched

    grouped: Dict[str, List[int]] = defaultdict(list)
    for page, cat in category_of.items():
        grouped[cat].append(page)

    labels = {key: label for key, label, _ in _PAGE_CATEGORY_RULES}
    labels.update({
        "framing_plan_unlabeled": "Framing plans (detected by content)",
        "perspective": "Perspective / 3D views",
        "unreadable": "Unreadable / image-only pages",
        "other": "Other / unclassified",
    })

    insights: List[Insight] = []
    for cat, pages in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        if cat in ("other", "unreadable") and len(pages) == 0:
            continue
        pages_sorted = sorted(pages)
        insights.append(Insight(
            type="page_group",
            value=f"{labels.get(cat, cat)}: {len(pages_sorted)} page(s)",
            confidence=0.85 if cat not in ("other", "framing_plan_unlabeled") else 0.55,
            source_pages=pages_sorted[:12],
            source_text=_clean(page_texts.get(pages_sorted[0], ""))[:_SNIPPET_MAX] if pages_sorted else "",
            scope="document",
            detail={"category": cat, "pages": pages_sorted, "label": labels.get(cat, cat)},
        ))
    if uncertain:
        insights.append(Insight(
            type="uncertainty",
            value=f"{len(uncertain)} page(s) could not be confidently categorised",
            confidence=0.5,
            source_pages=sorted(uncertain)[:12],
            scope="document",
            detail={"kind": "page_role", "pages": sorted(uncertain)},
        ))
    return insights, category_of


# --------------------------------------------------------------------------
# 2. Steel families + representative sections
# --------------------------------------------------------------------------
_FAMILY_RE = re.compile(r"^(2L|WT|MT|ST|MC|HP|HSS|PIPE|W|S|M|C|L)\d")
_SECTION_TOKEN_RE = re.compile(
    r"\b(?:2L|WT|MT|ST|MC|HP|HSS|PIPE|W|S|M|C|L)\s?\d+(?:\.\d+)?"
    r"(?:\s?[Xx×]\s?\d+(?:\.\d+)?(?:\s?[Xx×]\s?(?:\d+/\d+|\d+(?:\.\d+)?))?)?\b"
)
_FAMILY_LABELS = {
    "W": "wide-flange (W)", "HSS": "hollow structural (HSS)", "PIPE": "pipe",
    "C": "channel (C)", "MC": "channel (MC)", "L": "angle (L)", "2L": "double angle (2L)",
    "WT": "tee (WT)", "MT": "tee (MT)", "ST": "tee (ST)", "S": "beam (S)",
    "M": "beam (M)", "HP": "bearing pile (HP)",
}


def _catalog_section_counts(text: str) -> Tuple[int, int]:
    occ = 0
    distinct: set[str] = set()
    for match in _SECTION_TOKEN_RE.finditer(text):
        token = match.group(0).replace("×", "X").replace(" ", "")
        if catalog_form(token):
            occ += 1
            distinct.add(catalog_form(token))
    return occ, len(distinct)


def _steel_families(document: Dict[str, Any]) -> Tuple[List[Insight], Dict[str, Any]]:
    fam_occ: Counter = Counter()
    fam_distinct: Dict[str, set] = defaultdict(set)
    designation_occ: Counter = Counter()
    designation_family: Dict[str, str] = {}

    for token in document.get("engineering_tokens") or []:
        if token.get("takeoff_eligible") is False:
            continue
        raw = _clean(token.get("normalized_text") or token.get("text") or "").replace(" ", "").upper()
        resolved = catalog_form(raw)
        if not resolved:
            continue
        match = _FAMILY_RE.match(resolved)
        if not match:
            continue
        fam = match.group(1)
        # One extracted label token == one explicit designation occurrence.
        # (``repeat_count`` is a merge/de-dup bookkeeping field, not a member
        # multiplier -- never treat it as a quantity.)
        fam_occ[fam] += 1
        fam_distinct[fam].add(resolved)
        designation_occ[resolved] += 1
        designation_family[resolved] = fam

    insights: List[Insight] = []
    families_payload: List[Dict[str, Any]] = []
    for fam, occ in fam_occ.most_common():
        representative = [
            d for d, _ in designation_occ.most_common()
            if designation_family.get(d) == fam
        ][:_MAX_REPRESENTATIVE_PER_FAMILY]
        families_payload.append({
            "family": fam,
            "label": _FAMILY_LABELS.get(fam, fam),
            "explicit_occurrences": occ,
            "distinct_designations": len(fam_distinct[fam]),
            "representative": representative,
        })
        insights.append(Insight(
            type="steel_family",
            value=(
                f"{_FAMILY_LABELS.get(fam, fam)}: {occ} explicit designation "
                f"occurrence(s), {len(fam_distinct[fam])} distinct"
            ),
            confidence=0.9,
            source_pages=[],
            scope="document",
            detail={
                "family": fam, "explicit_occurrences": occ,
                "distinct_designations": len(fam_distinct[fam]),
                "representative": representative,
            },
        ))
    payload = {
        "families": families_payload,
        "representative_sections": [d for d, _ in designation_occ.most_common(10)],
        "total_explicit_occurrences": int(sum(fam_occ.values())),
        "total_distinct_designations": len(designation_occ),
    }
    return insights, payload


# --------------------------------------------------------------------------
# 3. TYP / repeated-condition intelligence  (also feeds Phase C)
# --------------------------------------------------------------------------
_TYP_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("TYP", re.compile(r"\bTYP(?:ICAL)?\b\.?", re.I)),
    ("U.N.O.", re.compile(r"\bU\.?\s?N\.?\s?O\.?\b|\bUNLESS\s+NOTED\s+OTHERWISE\b|\bUNLESS\s+OTHERWISE\s+NOTED\b", re.I)),
    ("SIM", re.compile(r"\bSIM(?:ILAR)?\b\.?", re.I)),
    ("SAME", re.compile(r"\bSAME\s+AS\b|\bMATCH\s+(?:ADJACENT|EXISTING|SIMILAR)\b", re.I)),
    ("EQ SPACING", re.compile(r"\bEQ(?:UAL)?\s+SPA(?:CING|CES)?\b|\b@\s?EQ\b", re.I)),
)
_SECTION_NEAR_RE = re.compile(
    r"\b((?:2L|WT|MT|ST|MC|HP|HSS|PIPE|W|S|M|C|L)\d+(?:[Xx×]\d+(?:/\d+)?)*)\s*[,\-]?\s*"
    r"(?:TYP|TYPICAL|U\.?N\.?O\.?|SIM)\b",
    re.I,
)


def _typical_conditions(
    document: Dict[str, Any],
    page_texts: Dict[int, str],
    category_of: Dict[int, str],
) -> List[Insight]:
    framing_cats = {
        "roof_framing", "floor_framing", "column_plan", "bracing",
        "framing_plan_unlabeled", "details",
    }
    per_keyword: Dict[str, Dict[str, Any]] = {}
    for page, text in page_texts.items():
        if not text.strip():
            continue
        on_framing = category_of.get(page) in framing_cats
        for label, pattern in _TYP_PATTERNS:
            hits = pattern.findall(text)
            if not hits:
                continue
            bucket = per_keyword.setdefault(label, {
                "occurrences": 0, "pages": set(), "framing_pages": set(),
                "examples": [], "near_sections": Counter(),
            })
            bucket["occurrences"] += len(hits)
            bucket["pages"].add(page)
            if on_framing:
                bucket["framing_pages"].add(page)
            for m in _SECTION_NEAR_RE.finditer(text):
                sect = catalog_form(m.group(1).replace(" ", "").upper())
                if sect:
                    bucket["near_sections"][sect] += 1
                    if len(bucket["examples"]) < _MAX_TYP_EXAMPLES:
                        bucket["examples"].append(_clean(m.group(0))[:80])

    insights: List[Insight] = []
    total = sum(b["occurrences"] for b in per_keyword.values())
    if not per_keyword:
        insights.append(Insight(
            type="typical_condition",
            value="No TYP / U.N.O. / repeated-condition language detected in the set",
            confidence=0.8,
            scope="document",
            detail={"present": False},
        ))
        return insights

    for label, bucket in sorted(per_keyword.items(), key=lambda kv: -kv[1]["occurrences"]):
        pages = sorted(bucket["pages"])
        framing_pages = sorted(bucket["framing_pages"])
        near = [s for s, _ in bucket["near_sections"].most_common(6)]
        scope_note = (
            "on framing/detail pages" if framing_pages else "on notes/detail pages only"
        )
        insights.append(Insight(
            type="typical_condition",
            value=(
                f"'{label}' appears {bucket['occurrences']} time(s) across "
                f"{len(pages)} page(s) ({scope_note})"
            ),
            confidence=0.85,
            source_pages=pages[:12],
            source_text=" / ".join(bucket["examples"][:3]),
            scope="document",
            detail={
                "keyword": label,
                "occurrences": bucket["occurrences"],
                "pages": pages,
                "framing_pages": framing_pages,
                "near_sections": near,
                "examples": bucket["examples"],
                "present": True,
            },
        ))
    insights.append(Insight(
        type="typical_condition_summary",
        value=(
            f"{total} repeated-condition marker(s) total -- explicit section "
            f"labels on these pages may describe repeated framing rather than "
            f"one member each"
        ),
        confidence=0.75,
        scope="document",
        detail={"total": total, "keywords": sorted(per_keyword)},
    ))
    return insights


# --------------------------------------------------------------------------
# 4. Schedule semantic classification
# --------------------------------------------------------------------------
_SCHEDULE_KIND_RULES: Tuple[Tuple[str, str, re.Pattern[str]], ...] = (
    ("column_schedule", "Column schedule",
     re.compile(r"\bCOLUMN\s+SCHEDULE\b|\bCOLUMN\s+LOCATIONS?\b", re.I)),
    ("base_plate_schedule", "Base plate / anchor rod schedule",
     re.compile(r"\bBASE\s+PLATE\b.*\bSCHEDULE\b|\bBASE\s+PLATE\s+&?\s+ANCHOR\s+ROD\b|\bANCHOR\s+ROD\s+SCHEDULE\b", re.I)),
    ("beam_schedule", "Beam / framing schedule",
     re.compile(r"\bBEAM\s+SCHEDULE\b|\bFRAMING\s+SCHEDULE\b|\bGIRDER\s+SCHEDULE\b", re.I)),
    ("brace_schedule", "Bracing schedule",
     re.compile(r"\bBRAC(?:E|ING)\s+SCHEDULE\b", re.I)),
    ("joist_schedule", "Joist schedule",
     re.compile(r"\bJOIST\s+SCHEDULE\b|\bJOIST\s+GIRDER\s+SCHEDULE\b", re.I)),
    ("lintel_schedule", "Lintel / opening schedule",
     re.compile(r"\bLINTEL\s+SCHEDULE\b|\bOPENING\s+SCHEDULE\b|\bRELIEVING\s+ANGLE\s+SCHEDULE\b", re.I)),
    ("footing_schedule", "Footing / foundation schedule",
     re.compile(r"\bFOOTING\s+SCHEDULE\b|\bPILE\s+(?:CAP\s+)?SCHEDULE\b|\bPIER\s+SCHEDULE\b|\bFOUNDATION\s+SCHEDULE\b|\bSPREAD\s+FOOTING\b", re.I)),
    ("connection_schedule", "Connection schedule",
     re.compile(r"\bCONNECTION\s+SCHEDULE\b|\bSHEAR\s+CONNECTION\b.*\bSCHEDULE\b", re.I)),
    ("rebar_schedule", "Reinforcing / development schedule",
     re.compile(r"\b(?:LAP\s+SPLICE|DEVELOPMENT)\s+(?:LENGTH|SCHEDULE)\b|\bREINFORC(?:ING|EMENT)\s+SCHEDULE\b|\bBOND\s+BEAM\b", re.I)),
    ("drawing_index", "Drawing index",
     re.compile(r"\bDRAWING\s+(?:INDEX|SCHEDULE)\b|\bSHEET\s+(?:INDEX|LIST)\b", re.I)),
)
_MATRIX_RE = re.compile(
    r"\b(?:FIRST|SECOND|THIRD|FOURTH|GROUND|MAIN|LOW|HIGH)\s+(?:FLOOR|ROOF|LEVEL)\b"
    r"[\s\S]{0,40}\d+'\s*-\s*\d+", re.I,
)
_LEVEL_DATUM_RE = re.compile(
    r"\b(?:FLOOR|ROOF|LEVEL|PARAPET|GRADE|SLAB|T\.?O\.?[SW])\b[\s.:]*\d+'\s*-\s*\d+", re.I,
)


def _schedule_insights(document: Dict[str, Any]) -> List[Insight]:
    insights: List[Insight] = []
    schedules = document.get("schedules") or []
    if not schedules:
        return insights

    seen_kind_pages: set[Tuple[str, int]] = set()
    for sched in schedules:
        text = str(sched.get("text") or "")
        # A schedule title is at the top of the table; matching a heading
        # anywhere in a 2000-char blob catches cross-references in prose.
        head_zone = text[:400]
        page = int(sched.get("page_number") or 0)
        head = _clean(text)[:_SNIPPET_MAX]
        occ, _distinct = _catalog_section_counts(text)
        kind = None
        label = None
        for key, name, pattern in _SCHEDULE_KIND_RULES:
            if pattern.search(head_zone) or (
                pattern.search(text) and key in ("column_schedule", "base_plate_schedule")
            ):
                kind, label = key, name
                break
        if kind is None:
            # Structural steel schedule with no recognised heading.
            if occ >= 6:
                kind, label = "unclassified_steel_table", "Structural table (semantics unclear)"
            else:
                continue  # non-steel table -- not worth surfacing
        elif kind in ("beam_schedule", "brace_schedule", "joist_schedule") and occ < 3:
            continue  # heading matched but no steel content -- likely a title-block phrase

        if (kind, page) in seen_kind_pages:
            continue
        seen_kind_pages.add((kind, page))

        is_matrix = bool(
            len(_LEVEL_DATUM_RE.findall(text)) >= 3 or _MATRIX_RE.search(text)
        )
        structure = "mark_or_tier_matrix" if is_matrix else "row_list"
        if kind == "column_schedule" and is_matrix:
            note = ("defines column sizes by mark/elevation tier, not a simple "
                    "member count -- do not read row/cell repetition as quantities")
            confidence = 0.8
        elif kind in ("base_plate_schedule", "footing_schedule", "rebar_schedule",
                      "connection_schedule", "lintel_schedule", "drawing_index"):
            note = "a property/definition table, not a member-instance count"
            confidence = 0.8
        elif kind == "unclassified_steel_table":
            note = "row/cell semantics not yet confidently classified"
            confidence = 0.45
        else:
            note = "member/size table -- treat quantities with care"
            confidence = 0.6

        insights.append(Insight(
            type="schedule",
            value=f"{label} on page {page} ({structure.replace('_', ' ')})",
            confidence=confidence,
            source_pages=[page],
            source_text=head,
            scope="page",
            detail={
                "schedule_id": sched.get("schedule_id"),
                "page": page, "kind": kind, "label": label,
                "structure": structure, "note": note,
            },
        ))
    return insights


# --------------------------------------------------------------------------
# 5. Scope / revision signals  (never uses the Excel)
#
# Deliberately conservative: an issuance PHASE is only claimed when it reads
# like a title-block stamp -- "ISSUED FOR <x>", "<x> SET", "FOR <x> ONLY", or
# the bare phrase standing alone on a short title-block line -- never a prose
# mention ("...during design development...", "...per the contract
# documents..."). A false phase claim would wrongly tell an estimator to
# split the takeoff scope.
# --------------------------------------------------------------------------
_STAMP_PREFIX = r"(?:ISSUED\s+FOR\s+|FOR\s+|)"
_SCOPE_SIGNALS: Tuple[Tuple[str, str, re.Pattern[str]], ...] = (
    ("NOT_FOR_CONSTRUCTION", "Not For Construction",
     re.compile(r"\bNOT\s+FOR\s+CONSTRUCTION\b|\bPRELIMINARY[\s-]+NOT\s+FOR\b", re.I)),
    ("EARLY_RELEASE", "Early / partial steel release",
     re.compile(r"\bEARLY\s+(?:STEEL\s+)?RELEASE(?:\s+PACKAGE)?\b|\bPARTIAL\s+(?:STEEL\s+)?RELEASE\b|\bEARLY\s+STEEL\s+PACKAGE\b", re.I)),
    ("IFC", "Issued For Construction",
     re.compile(r"\bISSUED\s+FOR\s+CONSTRUCTION\b|\bIFC\s+SET\b", re.I)),
    ("PERMIT", "Permit set",
     re.compile(_STAMP_PREFIX + r"PERMIT(?:\s+SET|\s+ONLY|\s+REVIEW)?\b", re.I)),
    ("BID", "Bid set",
     re.compile(r"\bISSUED\s+FOR\s+BID\b|\bFOR\s+BID\s+(?:SET|ONLY|PURPOSES)\b|\bBID\s+SET\b", re.I)),
    ("ADDENDUM", "Addendum",
     re.compile(r"\bADDENDUM\s+(?:NO\.?\s*)?\d+\b|\bASI\s*#?\s*\d+\b", re.I)),
    ("REVISION", "Numbered revision",
     re.compile(r"\bREV(?:ISION)?\.?\s*(?:NO\.?\s*)?[0-9]{1,2}\b(?!\d)|\bREVISED\s+PER\s+(?:ADDENDUM|ASI|RFI)\b", re.I)),
)
# A title-block line short enough to be a stamp, not prose.
_STAMP_LINE_MAX = 60


def _scope_signals(
    document: Dict[str, Any],
    page_texts: Dict[int, str],
) -> List[Insight]:
    title_lines: List[Tuple[int, str]] = []
    for block in document.get("title_blocks") or []:
        page = int(block.get("page_number") or 0)
        for raw_line in str(block.get("text") or "").splitlines():
            line = _clean(raw_line)
            if line:
                title_lines.append((page, line))

    found: Dict[str, Dict[str, Any]] = {}
    for key, label, pattern in _SCOPE_SIGNALS:
        pages: set[int] = set()
        example = ""
        for page, line in title_lines:
            if len(line) > _STAMP_LINE_MAX:
                continue
            m = pattern.search(line)
            if m:
                pages.add(page)
                if not example:
                    example = line[:_SNIPPET_MAX]
        # A revision/addendum marking may also legitimately appear in a
        # revision-block row within page text -- accept it there too.
        if key in ("REVISION", "ADDENDUM") and not pages:
            for page, text in page_texts.items():
                hit = pattern.search(text)
                if hit is not None:
                    pages.add(page)
                    if not example:
                        example = _clean(
                            text[max(0, hit.start() - 30): hit.end() + 30]
                        )[:_SNIPPET_MAX]
        if pages:
            found[key] = {"label": label, "pages": sorted(pages), "example": example}

    insights: List[Insight] = []
    if not found:
        insights.append(Insight(
            type="scope_signal",
            value="No explicit issue / revision / phase stamp detected in the title blocks",
            confidence=0.6,
            scope="document",
            detail={"present": False},
        ))
        return insights

    phase_keys = {"EARLY_RELEASE", "IFC", "PERMIT", "BID", "NOT_FOR_CONSTRUCTION"}
    phases_present = [k for k in found if k in phase_keys]
    for key, data in found.items():
        insights.append(Insight(
            type="scope_signal",
            value=f"{data['label']} stamp on page(s) {', '.join(map(str, data['pages'][:8]))}",
            confidence=0.7,
            source_pages=data["pages"][:12],
            source_text=data["example"],
            scope="document",
            detail={"signal": key, "label": data["label"], "pages": data["pages"], "present": True},
        ))
    if len(phases_present) >= 2:
        insights.append(Insight(
            type="uncertainty",
            value=(
                "More than one issue phase is stamped ("
                + ", ".join(found[k]["label"] for k in phases_present)
                + ") -- confirm which sheets belong to the takeoff scope before combining them"
            ),
            confidence=0.6,
            scope="document",
            detail={"kind": "scope", "phases": phases_present},
        ))
    return insights


# --------------------------------------------------------------------------
# 6. Existing / new work
# --------------------------------------------------------------------------
_EXISTING_RE = re.compile(r"\(E\)|\bEXIST(?:ING|\.)?\b|\bE\.?T\.?R\.?\b")
_NEW_RE = re.compile(r"\(N\)|\bNEW\s+(?:STEEL|BEAM|COLUMN|FRAMING|MEMBER|CONSTRUCTION)\b")
_DEMO_RE = re.compile(r"\bDEMO(?:LISH|LITION)?\b|\bREMOVE\s+(?:EXISTING|\(E\))\b|\bREPLACE\s+(?:EXISTING|\(E\))\b")
_EN_MEMBER_RE = re.compile(r"\((?:E|N)\)\s*(?:W|WT|HSS|L|2L|C|MC|PIPE|M|S|HP)\d", re.I)


def _existing_new(document: Dict[str, Any], full_text: str) -> Tuple[Optional[Insight], Dict[str, Any]]:
    existing = len(_EXISTING_RE.findall(full_text))
    new = len(_NEW_RE.findall(full_text))
    demo = len(_DEMO_RE.findall(full_text))
    en_members = len(_EN_MEMBER_RE.findall(full_text))
    payload = {
        "existing_tags": existing, "new_tags": new, "demo_tags": demo,
        "en_member_callouts": en_members,
        "is_renovation": en_members >= 3 or (existing >= 8 and demo >= 1),
    }
    if not payload["is_renovation"]:
        return None, payload
    return (
        Insight(
            type="existing_new",
            value=(
                f"This set distinguishes existing and new structural framing "
                f"({en_members} tagged member callout(s), {demo} demo/remove note(s)) "
                f"-- takeoff scope should preserve those designations"
            ),
            confidence=0.75,
            scope="document",
            detail=payload,
        ),
        payload,
    )


# --------------------------------------------------------------------------
# 7. Structural notes worth surfacing
# --------------------------------------------------------------------------
_NOTE_TOPICS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("grade", re.compile(r"\b(?:A992|A572|A500|A53|A36|A1085|GRADE\s+\d+|F[yY]\s*=\s*\d+)\b")),
    ("camber", re.compile(r"\bCAMBER\b")),
    ("typical_applies", re.compile(r"\bTYPICAL\s+DETAILS?\b.*\bAPPLY\b|\bU\.?N\.?O\.?\b.*\bAPPL", re.I)),
    ("connection", re.compile(r"\b(?:SHEAR|MOMENT|SIMPLE)\s+CONNECTION\b|\bCONNECTION\s+(?:DESIGN|REACTION)\b|\bDELEGATED\s+DESIGN\b", re.I)),
    ("existing", re.compile(r"\bFIELD\s+VERIFY\b|\bEXISTING\s+(?:CONDITIONS?|STEEL|FRAMING)\b", re.I)),
    ("scope", re.compile(r"\bSUPPLEMENTAL\s+STEEL\b|\bMISCELLANEOUS\s+(?:METAL|STEEL)\b|\bOPENING\s+FRAMING\b|\bBY\s+(?:OTHERS|FABRICATOR)\b", re.I)),
)


# A line worth surfacing as a NOTE states a rule -- it has a directive verb
# or a defined value -- rather than being a detail/section title.
_DIRECTIVE_RE = re.compile(
    r"\bSHALL\b|\bMUST\b|\bPROVIDE\b|\bREFER\s+TO\b|\bSEE\s+(?:SHEET|DETAIL|SCHEDULE|NOTE)\b"
    r"|\bASSUME\b|\bUNLESS\s+NOTED\b|\bMINIMUM\b|=\s*\d",
    re.I,
)
# A detail/section/plan title (ALL-CAPS noun phrase, no directive) -- excluded.
_TITLE_LINE_RE = re.compile(
    r"^[A-Z0-9 ,/&()\"'.\-]+\b(?:DETAIL|DETAILS|SCHEDULE|PLAN|SECTION|ELEVATION|NOTES?)\s*$"
)
_GRADE_TOKEN_RE = re.compile(
    r"\bA\s?(36|53|500|529|572|588|992|1085|1064)\b(?:\s*,?\s*GR(?:ADE)?\.?\s*[\"']?([A-D]|50|55|60|65|80)\b[\"']?)?",
    re.I,
)


def _structural_notes(page_texts: Dict[int, str], context_pages: Dict[str, str]) -> List[Insight]:
    note_pages = {
        int(p) for p, role in (context_pages or {}).items()
        if role in ("GENERAL_NOTES", "STRUCTURAL_NOTES", "LEGEND")
    }
    if not note_pages:
        return []
    seen: set[str] = set()
    out: List[Insight] = []
    grades: set[str] = set()
    for page in sorted(note_pages):
        text = page_texts.get(page, "")
        for m in _GRADE_TOKEN_RE.finditer(text):
            astm = "A" + m.group(1)
            grades.add(astm + (f" Gr.{m.group(2).upper()}" if m.group(2) else ""))
        for line in re.split(r"(?<=[.;])\s+|\n", text):
            line = _clean(line)
            if len(line) < 30 or len(line) > 240 or _TITLE_LINE_RE.match(line):
                continue
            if not line[-1:] in ".;)\"'" and not re.search(r"=\s*\d", line):
                continue  # not a complete statement -- likely an OCR fragment
            if not _DIRECTIVE_RE.search(line):
                continue
            if line.lower()[:38] in seen:
                continue
            for topic, pattern in _NOTE_TOPICS:
                if topic == "grade":
                    continue  # handled by the consolidated grade insight
                if pattern.search(line):
                    seen.add(line.lower()[:38])
                    out.append(Insight(
                        type="structural_note",
                        value=line,
                        confidence=0.7,
                        source_pages=[page],
                        source_text=line,
                        scope="page",
                        detail={"topic": topic, "page": page},
                    ))
                    break
            if len(out) >= _MAX_NOTES:
                break
    if grades:
        out.insert(0, Insight(
            type="structural_note",
            value="Steel grades referenced: " + ", ".join(sorted(grades)),
            confidence=0.8,
            source_pages=sorted(note_pages)[:4],
            source_text="",
            scope="document",
            detail={"topic": "grade", "grades": sorted(grades)},
        ))
    return out[: _MAX_NOTES + 1]


# --------------------------------------------------------------------------
# Narrative rendering (deterministic; always usable)
# --------------------------------------------------------------------------
def _render_narrative(profile: Dict[str, Any]) -> Dict[str, Any]:
    groups = {g["detail"]["category"]: g["detail"] for g in profile["page_groups"]}
    fam_payload = profile["steel_system"]
    families = fam_payload["families"]
    typ = [i for i in profile["typical_conditions"] if i["detail"].get("present")]
    scheds = profile["schedule_insights"]
    scopes = [i for i in profile["scope_signals"] if i["detail"].get("present")]
    notes = profile["structural_notes"]
    uncertainties = profile["uncertainties"]

    framing_pages = sum(
        len(groups[c]["pages"]) for c in
        ("roof_framing", "floor_framing", "column_plan", "framing_plan_unlabeled", "bracing")
        if c in groups
    )
    detail_pages = sum(
        len(groups[c]["pages"]) for c in ("details", "schedule", "elevation_section")
        if c in groups
    )

    # A. project overview -- only claims the evidence supports
    if families:
        primary = families[0]
        # a "secondary" family needs a non-trivial presence, not one stray tag
        secondary = [
            f["family"] for f in families[1:5]
            if f["explicit_occurrences"] >= 5 or f["distinct_designations"] >= 3
        ]
        sys_phrase = f"{primary['label']} framing dominates the explicit designations"
        if secondary:
            sys_phrase += f"; {', '.join(secondary)} members also appear"
        if "bracing" in groups and groups["bracing"]["pages"]:
            sys_phrase += f"; dedicated bracing sheets are present ({len(groups['bracing']['pages'])})"
    else:
        sys_phrase = "no catalog-valid steel section designations were read"
    overview = (
        f"This {profile['page_count']}-page structural set has "
        f"{framing_pages} framing/plan page(s) and {detail_pages} detail/schedule/"
        f"section page(s). {sys_phrase[0].upper() + sys_phrase[1:]}."
    )
    if profile["existing_new"].get("is_renovation"):
        overview += " The set distinguishes existing and new framing."

    # C. steel system
    if families:
        parts = [
            f"{f['label']}: {f['explicit_occurrences']} occurrences / "
            f"{f['distinct_designations']} distinct"
            + (f" (e.g. {', '.join(f['representative'][:3])})" if f["representative"] else "")
            for f in families[:4]
        ]
        steel_system = "; ".join(parts) + "."
    else:
        steel_system = "No catalog-valid steel designations were extracted."

    # D. drawing language
    abbr = profile.get("abbreviation_rules") or []
    if abbr:
        shown = "; ".join(f"{r['lhs']} = {r['rhs']}" for r in abbr[:5])
        more = f" (+{len(abbr) - 5} more)" if len(abbr) > 5 else ""
        drawing_language = (
            f"{len(abbr)} explicit project shorthand rule(s): {shown}{more}"
        )
    else:
        drawing_language = "No project-specific shorthand substitutions were found."

    # E. typical conditions
    if typ:
        total = next(
            (i["detail"]["total"] for i in profile["typical_conditions"]
             if i["type"] == "typical_condition_summary"), 0,
        )
        kws = ", ".join(sorted({i["detail"]["keyword"] for i in typ}))
        typical = (
            f"{total} repeated-condition marker(s) ({kws}). Explicit section "
            f"labels on these pages may describe repeated framing conditions "
            f"rather than one member each."
        )
    else:
        typical = "No TYP / U.N.O. / repeated-condition language detected."

    # F. schedules
    if scheds:
        schedule_text = "; ".join(
            f"{s['detail']['label']} (p{s['detail']['page']}) — {s['detail']['note']}"
            for s in scheds[:5]
        )
    else:
        schedule_text = "No structural schedules identified."

    # G. scope / revision
    if scopes:
        scope_text = "; ".join(s["detail"]["label"] for s in scopes)
        multi = [u for u in uncertainties if u["detail"].get("kind") == "scope"]
        if multi:
            scope_text += ". Multiple phases present — confirm takeoff scope before combining sheets."
    else:
        scope_text = "No explicit issue/revision/phase markings detected."

    important = [n["value"] for n in notes[:_MAX_NOTES]]
    uncertainty_lines = [u["value"] for u in uncertainties]
    if not uncertainty_lines:
        uncertainty_lines = ["No unresolved conflicts or ambiguous page roles detected."]

    return {
        "project_overview": overview,
        "structural_content": _page_group_sentence(groups),
        "steel_system": steel_system,
        "drawing_language": drawing_language,
        "typical_conditions": typical,
        "schedules": schedule_text,
        "scope_revision": scope_text,
        "important_notes": important,
        "uncertainties": uncertainty_lines,
    }


def _page_group_sentence(groups: Dict[str, Any]) -> str:
    order = [
        ("drawing_index", "index"), ("notes_legend", "notes/legend"),
        ("foundation", "foundation"), ("column_plan", "column"),
        ("floor_framing", "floor framing"), ("roof_framing", "roof framing"),
        ("framing_plan_unlabeled", "framing (by content)"), ("bracing", "bracing"),
        ("elevation_section", "elevation/section"), ("schedule", "schedule"),
        ("details", "typical detail"), ("perspective", "perspective"),
        ("other", "unclassified"), ("unreadable", "unreadable"),
    ]
    parts = [
        f"{len(groups[key]['pages'])} {name}"
        for key, name in order
        if key in groups and groups[key]["pages"]
    ]
    return ("Page make-up: " + ", ".join(parts) + ".") if parts else "No pages classified."


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def build_drawing_intelligence(
    document: Dict[str, Any],
    *,
    context_pages: Optional[Dict[str, str]] = None,
    abbreviation_rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the deterministic Drawing Intelligence Profile from an already
    extracted ``document``. Never raises for a well-formed document; a caller
    that passes junk gets a profile with empty sections, not an exception."""

    context_pages = context_pages or {}
    abbreviation_rules = abbreviation_rules or []
    page_texts = _page_texts(document)
    full_text = _full_text(document, page_texts)
    page_count = int(document.get("page_count") or (max(page_texts) if page_texts else 0))

    page_group_insights, category_of = _classify_pages(document, page_texts, context_pages)
    family_insights, steel_payload = _steel_families(document)
    typ_insights = _typical_conditions(document, page_texts, category_of)
    schedule_insights = _schedule_insights(document)
    scope_insights = _scope_signals(document, page_texts)
    reno_insight, reno_payload = _existing_new(document, full_text)
    note_insights = _structural_notes(page_texts, context_pages)

    uncertainties: List[Insight] = [
        i for i in page_group_insights + scope_insights if i.type == "uncertainty"
    ]
    for sched in schedule_insights:
        if sched.detail.get("kind") == "unclassified_steel_table":
            uncertainties.append(Insight(
                type="uncertainty",
                value=f"Structural table on page {sched.detail['page']} has unresolved row/cell semantics",
                confidence=0.5,
                source_pages=sched.source_pages,
                scope="page",
                detail={"kind": "schedule_semantics", "page": sched.detail["page"]},
            ))
    # conflicting abbreviation rules (same LHS, different RHS)
    by_lhs: Dict[str, set] = defaultdict(set)
    for rule in abbreviation_rules:
        by_lhs[str(rule.get("lhs"))].add(str(rule.get("rhs")))
    conflicts: List[Insight] = []
    for lhs, rhss in by_lhs.items():
        if len(rhss) > 1:
            conflicts.append(Insight(
                type="conflict",
                value=f"Shorthand '{lhs}' expands to more than one section ({', '.join(sorted(rhss))})",
                confidence=0.7,
                scope="document",
                detail={"kind": "conflicting_rule", "lhs": lhs, "candidates": sorted(rhss)},
            ))
    uncertainties.extend(conflicts)

    page_groups = [i for i in page_group_insights if i.type == "page_group"]
    typical_conditions = [i for i in typ_insights]
    all_insights = (
        page_group_insights + family_insights + typ_insights + schedule_insights
        + scope_insights + note_insights + ([reno_insight] if reno_insight else [])
        + uncertainties + conflicts
    )

    profile: Dict[str, Any] = {
        "version": DRAWING_INTELLIGENCE_VERSION,
        "method": _METHOD_DETERMINISTIC,
        "page_count": page_count,
        "abbreviation_rules": abbreviation_rules,
        "page_groups": [i.as_dict() for i in page_groups],
        "page_categories": {str(p): c for p, c in sorted(category_of.items())},
        "steel_system": steel_payload,
        "steel_family_insights": [i.as_dict() for i in family_insights],
        "representative_sections": steel_payload["representative_sections"],
        "typical_conditions": [i.as_dict() for i in typical_conditions],
        "schedule_insights": [i.as_dict() for i in schedule_insights],
        "scope_signals": [i.as_dict() for i in scope_insights],
        "structural_notes": [i.as_dict() for i in note_insights],
        "existing_new": reno_payload,
        "uncertainties": [i.as_dict() for i in uncertainties],
        "conflicts": [i.as_dict() for i in conflicts],
        "sources": [i.as_dict() for i in all_insights if i.source_pages or i.source_text],
    }
    profile["narrative"] = _render_narrative(profile)
    profile["overview"] = profile["narrative"]["project_overview"]
    return profile


def evidence_packet(profile: Dict[str, Any], *, max_chars: int = 6000) -> str:
    """Compact, ranked, plain-text evidence packet for the optional LLM
    summariser. HIGH-value context first (page make-up, steel system,
    drawing language, TYP, schedules, scope, notes); no raw token dumps."""

    lines: List[str] = []
    lines.append(f"DRAWING SET: {profile['page_count']} pages")
    lines.append("PAGE MAKE-UP:")
    for g in profile["page_groups"]:
        d = g["detail"]
        lines.append(f"  - {d['label']}: pages {d['pages'][:15]}")
    lines.append("STEEL SYSTEM (explicit designation occurrences, not member quantities):")
    for f in profile["steel_system"]["families"]:
        rep = ", ".join(f["representative"])
        lines.append(
            f"  - {f['label']}: {f['explicit_occurrences']} occ / "
            f"{f['distinct_designations']} distinct; representative: {rep}"
        )
    if profile.get("abbreviation_rules"):
        lines.append("PROJECT SHORTHAND RULES (explicit, verified):")
        for r in profile["abbreviation_rules"]:
            lines.append(f"  - {r['lhs']} = {r['rhs']} (page {r.get('source_page')})")
    lines.append("REPEATED-CONDITION LANGUAGE:")
    for i in profile["typical_conditions"]:
        lines.append(f"  - {i['value']}")
        if i["detail"].get("near_sections"):
            lines.append(f"    near sections: {i['detail']['near_sections']}")
    lines.append("SCHEDULES:")
    for i in profile["schedule_insights"]:
        lines.append(f"  - {i['value']} -- {i['detail'].get('note')}")
    if not profile["schedule_insights"]:
        lines.append("  - none identified")
    lines.append("SCOPE / REVISION SIGNALS:")
    for i in profile["scope_signals"]:
        lines.append(f"  - {i['value']}")
    lines.append("STRUCTURAL NOTES (verbatim):")
    for i in profile["structural_notes"]:
        lines.append(f"  - (p{i['source_pages'][0] if i['source_pages'] else '?'}) {i['value']}")
    if not profile["structural_notes"]:
        lines.append("  - none surfaced")
    lines.append("UNCERTAINTIES:")
    for i in profile["uncertainties"]:
        lines.append(f"  - {i['value']}")
    if not profile["uncertainties"]:
        lines.append("  - none")
    packet = "\n".join(lines)
    return packet[:max_chars]
