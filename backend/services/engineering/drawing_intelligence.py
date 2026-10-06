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
from services.engineering.column_schedule import _union_boxes, column_schedule_view
from services.engineering.framing_key import bracket_definition, read_framing_keys
from services.engineering.level_evidence import format_elevation, levels_view
from services.engineering.page_space import convert_boxes, display_boxes

DRAWING_INTELLIGENCE_VERSION = "drawing_intelligence_v3"

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
_POINTER_BEFORE_RE = re.compile(r"\b(?:SEE|REFER\s+TO|PER)\s+(?:THE\s+)?$", re.I)


def _heading_match(pattern: "re.Pattern[str]", text: str) -> bool:
    """``pattern`` names the thing itself, not a pointer ("SEE LINTEL SCHEDULE")."""

    return any(
        not _POINTER_BEFORE_RE.search(text[max(0, m.start() - 16):m.start()])
        for m in pattern.finditer(text)
    )


def _classify_pages(
    document: Dict[str, Any],
    page_texts: Dict[int, str],
    context_pages: Dict[str, str],
) -> Tuple[List[Insight], Dict[int, str]]:
    """Assign every readable page a category. A page hosting a live MARK|SIZE
    schedule grid is a schedule page even when it also carries notes;
    otherwise ``notes_legend`` defers to the legend profile's own
    ``context_pages`` verdict where it has one."""

    page_count = int(document.get("page_count") or 0)
    ctx = {int(k): v for k, v in (context_pages or {}).items()}
    page_meta = {int(p.get("page_number") or 0): p for p in (document.get("pages") or [])}
    grid_pages = {
        int(g.get("page") or 0) for g in document.get("schedule_grid") or [] if g.get("rows")
    }

    category_of: Dict[int, str] = {}
    uncertain: List[int] = []
    for page in range(1, page_count + 1):
        text = page_texts.get(page, "")
        head = text[:_TITLE_HINT_LEN]
        meta = page_meta.get(page, {})
        if meta.get("unreadable") or not text.strip():
            category_of[page] = "unreadable"
            continue
        if page in grid_pages:
            category_of[page] = "schedule"
            continue
        if page in ctx:
            category_of[page] = "notes_legend"
            continue
        matched = None
        for key, _label, pattern in _PAGE_CATEGORY_RULES:
            if _heading_match(pattern, text):
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
            if _heading_match(pattern, head_zone) or (
                _heading_match(pattern, text) and key in ("column_schedule", "base_plate_schedule")
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
# Framing named existing / new: "EXISTING BEAM", "EXIST. STEEL", "(E) W10X12";
# "NEW STEEL", "NEW BEAM", "(N) HSS6X6". Existing soils, slabs or surfaces are
# not framing.
_FRAMING_WORDS = r"(?:STEEL|BEAMS?|COLUMNS?|FRAMING|JOISTS?|GIRDERS?|MEMBERS?|(?:W|HSS|WT|MC)\d)"
_EXISTING_FRAMING_RE = re.compile(rf"\bEXIST(?:ING|\.)\s+{_FRAMING_WORDS}|\(E\)\s*{_FRAMING_WORDS}", re.I)
_NEW_FRAMING_RE = re.compile(rf"\bNEW\s+{_FRAMING_WORDS}|\(N\)\s*{_FRAMING_WORDS}", re.I)


def _existing_new(page_texts: Dict[int, str], full_text: str) -> Tuple[Optional[Insight], Dict[str, Any]]:
    existing = len(_EXISTING_RE.findall(full_text))
    new = len(_NEW_RE.findall(full_text))
    demo = len(_DEMO_RE.findall(full_text))
    en_members = len(_EN_MEMBER_RE.findall(full_text))
    existing_framing = len(_EXISTING_FRAMING_RE.findall(full_text))
    new_framing = len(_NEW_FRAMING_RE.findall(full_text))
    # "The set distinguishes existing and new framing" needs framing named
    # both ways (or tagged (E) / (N) members). General notes about existing
    # soils, slabs or surfaces and an abbreviation list's DEMO entry do not.
    both = existing_framing >= 2 and new_framing >= 2
    payload = {
        "existing_tags": existing, "new_tags": new, "demo_tags": demo,
        "en_member_callouts": en_members,
        "existing_framing_mentions": existing_framing, "new_framing_mentions": new_framing,
        "is_renovation": en_members >= 3 or both,
        "basis": ("tagged (E) / (N) member callouts" if en_members >= 3 else
                  "framing is named both existing and new" if both else
                  "existing construction is mentioned, but framing is not named both existing and new"
                  if existing else "no existing / new tags"),
        "pages": sorted(p for p, text in page_texts.items()
                        if _EXISTING_FRAMING_RE.search(text) or _NEW_FRAMING_RE.search(text) or _EN_MEMBER_RE.search(text)),
    }
    if not payload["is_renovation"]:
        return None, payload
    return (
        Insight(
            type="existing_new",
            value=(
                f"This set distinguishes existing and new structural framing ({payload['basis']}; "
                f"{existing_framing} existing / {new_framing} new framing mention(s)) "
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
# 7. Schedule definitions + rules affecting interpretation
#
# Definitions come from the LIVE ``schedule_grid`` -- the same MARK|SIZE rows
# production mark resolution already reads (SCHEDULE_GRID_ENABLED). Never the
# shadow structured-evidence artifact and never the schedule quarantine. A
# definition says how to READ a mark on plan; a schedule row is not a member
# instance and never a quantity.
# --------------------------------------------------------------------------
# schedule_grid kind -> (group label, schedule title, mark noun)
_COMPONENTS = {
    "lintel": ("Lintels", "Lintel schedule", "lintel"),
    "column": ("Columns", "Column schedule", "column"),
    "bearing_plate": ("Bearing plates", "Bearing plate schedule", "bearing plate"),
    "icf_lintel": ("ICF lintels", "ICF lintel schedule", "ICF lintel"),
    "schedule": ("Other schedule marks", "Schedule", "other schedule"),
}
_COMPONENT_ORDER = tuple(_COMPONENTS)
# ``S002`` / ``S-101`` / dotted ``S2.09``.
_SHEET_RE = re.compile(r"\bS-?(?:\d{3}|\d{1,2}\.\d{2})[A-Z]?\b")
_ANGLE_TYPE_RE = re.compile(r"\b(LOOSE|CONTINUOUS)\s+ANGLE", re.I)
# a printed "A x B" dimension in a resolved plate display
_DIMENSION_RE = re.compile(r"\d+(?:\s+\d+/\d+|/\d+|\.\d+)?\"?\s*[xX×]\s*\d")
# Words a clean MARK|SIZE|PLATE cell may legitimately contain; anything else
# means the grid captured text from an adjacent table on the same sheet.
_CELL_WORDS = frozenset(
    "WITH BOTTOM HUNG PLATE HSS STANDARD WALL AT HEAD LOOSE CONTINUOUS ANGLE "
    "WELDED TO REFER DETAIL STIRRUPS TOP OC NA PRECAST LINTEL IB".split()
)
# "SEE LINTEL SCHEDULE" is a pointer to a schedule, not the schedule itself.
_SCHEDULE_REFERENCE_RE = re.compile(
    r"\b(?:SEE|REFER\s+TO|PER)\s+(?:THE\s+)?((?:[A-Z]+\s+){0,2}?)SCHEDULE\b", re.I
)
_NOTES_HEAD_RE = re.compile(r"^\s*NOTES?\s*:\s*", re.I)
_NUMBERED_RE = re.compile(r"(?:^|\s)(\d{1,2})\.\s+")
_SYMBOL_LEGEND_RE = re.compile(r"\((\d{1,2}\*)\)\s*(.+?)(?=\s*\(\d{1,2}\*\)|$)")
_LEGEND_ENTRY_RE = re.compile(r"^[^.]{4,}?\.(?:\s+(?:REFER\s+TO|SEE)\b[^.]*\.)?", re.I)
# literal-anchored; the enclosing sentence is found with rfind/find, not by
# a leading [^.]* that backtracks quadratically on period-free drawing text
_SIMILAR_CONDITION_RE = re.compile(
    r"\bAPPLY\s+TO\s+(?:ALL\s+)?(?:AREAS|CONDITIONS)\s+SIMILAR\b", re.I
)
_BRACKET_TAG_RE = re.compile(r"\b(?:W|HSS|MC|WT|C|L)\d+(?:\.\d+)?[xX][\d./]+\s*\[\d+\]")
_UNO_RE = dict(_TYP_PATTERNS)["U.N.O."]  # same U.N.O. reading as TYP detection
_DETAIL_REF_RE = re.compile(r"\b(?:REFER\s+TO|SEE)\s+(?:SHEET|DETAIL|S/?\d)", re.I)
_MAX_RULES = 16
_MAX_SYMBOLS = 8
# Most interpretation-changing first; the cap then drops plain schedule notes.
_RULE_RANK = {
    "default unless otherwise noted": 0, "symbol denotes": 1,
    "scope of TYP / SIM conditions": 2, "scoped convention": 3,
    "schedule reference": 4, "schedule note": 5, "detail reference": 6,
}


def _sheet_ids(document: Dict[str, Any]) -> Dict[int, str]:
    """Sheet number per 1-based page from the bottom-right title strip only
    (``S002``). A page with no confident candidate is simply absent."""

    meta = {int(p.get("page_number") or 0): p for p in document.get("pages") or []}
    box = display_boxes(document)
    best: Dict[int, Tuple[float, str]] = {}
    for block in document.get("blocks") or []:
        page = int(block.get("page_number") or 0)
        # The title strip is bottom-right as the sheet is displayed.
        bbox = box(page, block.get("bbox")) or []
        width = float((meta.get(page) or {}).get("width") or 0)
        height = float((meta.get(page) or {}).get("height") or 0)
        if len(bbox) < 4 or not width or not height:
            continue
        if float(bbox[0]) < 0.62 * width or float(bbox[1]) < 0.72 * height:
            continue
        for match in _SHEET_RE.finditer(str(block.get("text") or "")):
            corner = float(bbox[2]) + float(bbox[3])
            if page not in best or corner > best[page][0]:
                best[page] = (corner, match.group(0).replace("-", ""))
    return {page: sheet for page, (_, sheet) in best.items()}


def _where(sheets: Dict[int, str], page: int) -> Dict[str, Any]:
    return {"page": page, "sheet": sheets.get(page)}


def _grid_kind(grid: Dict[str, Any]) -> str:
    return grid.get("kind") if grid.get("kind") in _COMPONENTS else "schedule"


def _mark_boxes(page_words: List[Dict[str, Any]], marks: List[str]) -> Dict[str, List[float]]:
    """Bbox of each mark's own MARK cell on the schedule page. Where a mark
    text also appears elsewhere on the sheet, the one aligned with the rest of
    the column (median x) wins."""

    from services.engineering.schedule_grid import _compact_mark

    wanted = {m.upper() for m in marks}
    found: Dict[str, List[List[float]]] = defaultdict(list)
    for word in page_words:
        text = _compact_mark(word.get("text"))
        if text in wanted and len(word.get("bbox") or []) >= 4:
            found[text].append([round(float(v), 1) for v in word["bbox"][:4]])
    firsts = sorted(boxes[0][0] for boxes in found.values())
    column_x = firsts[len(firsts) // 2] if firsts else 0.0
    return {
        mark: min(boxes, key=lambda box: abs(box[0] - column_x))
        for mark, boxes in found.items()
    }


def _mixed_cell(raw: str, value: str) -> bool:
    """True when a cell held words from outside the cell (adjacent table)."""

    rest = str(raw or "").upper().replace(str(value or "").upper(), " ")
    return any(word not in _CELL_WORDS for word in re.findall(r"[A-Z]{2,}", rest))


def _definition(
    grid: Dict[str, Any], row: Dict[str, Any], document: Dict[str, Any],
    sheets: Dict[int, str], boxes: Dict[str, List[float]],
) -> Optional[Dict[str, Any]]:
    from services.engineering.schedule_grid import (
        _EMPTY_PLATE_RE,
        NON_STEEL_SCHEDULE_KINDS,
        is_auxiliary_schedule_mark,
        resolve_auxiliary_schedule_mark,
    )

    mark = str(row.get("mark") or "").upper()
    if not mark or row.get("mark_role") == "grid_location":
        return None
    page = int(grid.get("page") or 0)
    kind = _grid_kind(grid)
    size_text = _clean(row.get("size_text"))
    plate_text = _clean(row.get("plate_text"))
    role = _COMPONENTS[kind][2]
    designation: Optional[str] = None   # only an exact catalog designation
    printed = ""                        # the schedule's own size / text
    configuration: List[str] = []       # how this mark's member is arranged
    parts: List[Dict[str, Any]] = []    # associated plates, with printed size
    status: Optional[str] = None
    mixed = False

    if is_auxiliary_schedule_mark(mark):
        aux = resolve_auxiliary_schedule_mark(mark, document) or {}
        raw = f"{size_text} {plate_text}"
        display = str(aux.get("display") or "")
        if aux.get("section"):
            relation, designation = "mark defines section", _catalog_designation(aux["section"])
            angle = _ANGLE_TYPE_RE.findall(raw)
            if angle:
                configuration.append(f"{angle[-1].lower()} angle")
        elif _DIMENSION_RE.search(display) and not aux.get("abstain"):
            # No plate designation exists in the catalog: keep the printed
            # size, in the schedule's own dimension order.
            relation, printed = "mark defines plate", display
        elif re.search(r"\bN/?A\b", raw, re.I) or aux.get("abstain"):
            relation, printed, status = "mark defines no steel item", "N/A", "no steel"
        else:
            relation = "unreadable"
        mixed = _mixed_cell(raw, display)
    elif row.get("catalog_valid") and row.get("section"):
        relation, designation = "mark defines section", _catalog_designation(row["section"])
        configuration.extend(r.replace("_", " ") for r in row.get("member_plate_roles") or [])
        if plate_text and not _EMPTY_PLATE_RE.fullmatch(plate_text):
            parts.append({
                "role": "base plate" if kind == "column" else "bearing plate",
                "printed": plate_text, "designation": None,
            })
        mixed = _mixed_cell(size_text, "")
    else:
        # A concrete row whose size sits in dimension columns (W23: WIDTH 23")
        # is still a printed definition; its cells carry it.
        printed_cells = grid.get("kind") in NON_STEEL_SCHEDULE_KINDS and any(c["text"] for c in row.get("cells") or [])
        if (not size_text or _EMPTY_PLATE_RE.fullmatch(size_text)) and not printed_cells:
            return None
        # Printed SIZE is not a catalog steel section (e.g. precast lintel).
        relation, printed = "mark defines non-steel item", size_text
        status = "precast" if "PRECAST" in size_text.upper() else "not steel"
    if relation == "mark defines section" and not designation:
        printed = size_text   # resolver section the catalog does not confirm
        mixed = True
    if mixed and status is None:
        status = "verify"
    return {
        "mark": mark,
        "component": kind,
        "component_label": _COMPONENTS[kind][0],
        "schedule": _COMPONENTS[kind][1],
        "relation": relation,
        "role": role,
        "designation": designation,
        "designation_source": "AISC v16 catalog" if designation else None,
        "printed": printed,
        "configuration": configuration,
        "parts": parts,
        "status": status,
        "is_definition_not_quantity": True,
        "cell_text_mixed": mixed,
        "source_text": _clean(f"{mark} | {size_text}" + (f" | {plate_text}" if plate_text else ""))[:_SNIPPET_MAX],
        "bbox": _display_row_box(row) if row.get("cells") else boxes.get(mark),
        "evidence": "schedule_grid",
        # The printed table's own title and its cells under their headings
        # (non-steel schedules), so equal values in two columns stay two values.
        "schedule_title": grid.get("title"),
        **({"cells": row["cells"]} if row.get("cells") else {}),
        **_where(sheets, page),
    }


def _catalog_designation(section: str) -> Optional[str]:
    """The catalog's own spelling when ``section`` is an exact catalog row."""

    from services.database_loader import lookup_shape

    form = catalog_form(str(section or ""))
    return form if form and lookup_shape(form) else None


def _schedule_notes(
    document: Dict[str, Any], grid_spans: List[Tuple[int, str, float, float]],
    sheets: Dict[int, str],
) -> List[Dict[str, Any]]:
    """Numbered NOTES printed directly under a steel schedule table."""

    rules: List[Dict[str, Any]] = []
    for block in document.get("blocks") or []:
        text = _clean(block.get("text"))
        bbox = block.get("bbox") or []
        if not _NOTES_HEAD_RE.match(text) or len(bbox) < 4:
            continue
        page = int(block.get("page_number") or 0)
        for span_page, kind, x0, y1 in grid_spans:
            if span_page != page or abs(float(bbox[0]) - x0) > 80:
                continue
            if not (y1 - 5 <= float(bbox[1]) <= y1 + 160):
                continue
            body = _NOTES_HEAD_RE.sub("", text)
            items = [item.strip() for item in _NUMBERED_RE.split(body)[2::2] if item.strip()]
            for item in items or [body]:
                if _UNO_RE.search(item):
                    relation = "default unless otherwise noted"
                elif _DETAIL_REF_RE.search(item):
                    relation = "detail reference"
                else:
                    relation = "schedule note"
                rules.append({
                    "relation": relation, "text": item[:_SNIPPET_MAX],
                    "scope": _COMPONENTS[kind][1], "source_text": item[:_SNIPPET_MAX],
                    "bbox": [round(float(v), 1) for v in bbox[:4]], **_where(sheets, page),
                })
            break
    return rules


def _symbol_legends(page_texts: Dict[int, str], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    """``LEGEND ... (1*) 6"x3 1/2"x3/8" CONTINUOUS ANGLE ...`` entries, verbatim.
    Only the stretch right after a LEGEND heading is read."""

    by_text: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for page in sorted(page_texts):
        text = _clean(page_texts[page])
        for heading in re.finditer(r"\bLEGEND\b", text, re.I):
            legend = text[heading.start():heading.start() + 900]
            if "(1*)" not in legend:
                continue
            legend = legend[legend.index("(1*)"):]
            for symbol, meaning in _SYMBOL_LEGEND_RE.findall(legend):
                # first sentence plus an optional "REFER TO / SEE ..." sentence;
                # anything after it is sheet furniture (grid labels, title block)
                sentence = _LEGEND_ENTRY_RE.match(meaning.strip())
                if not sentence:
                    continue
                meaning = sentence.group(0)[:_SNIPPET_MAX]
                entry = by_text.setdefault((symbol, meaning), {
                    "relation": "symbol denotes", "text": f"({symbol}) = {meaning}",
                    "scope": "plan symbol", "source_text": f"({symbol}) {meaning}",
                    "bbox": None, "pages": [], **_where(sheets, page),
                })
                if page not in entry["pages"]:
                    entry["pages"].append(page)
    return list(by_text.values())[:_MAX_SYMBOLS]


def _similar_condition_rules(page_texts: Dict[int, str], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    for page in sorted(page_texts):
        if "SIMILAR" not in page_texts[page].upper():
            continue
        text = _clean(page_texts[page])
        match = _SIMILAR_CONDITION_RE.search(text)
        if match:
            start = text.rfind(".", 0, match.start()) + 1
            end = text.find(".", match.end())
            sentence = text[start:(end + 1) if end >= 0 else len(text)]
            sentence = re.sub(r"^.*\bNOTES?\s*:?\s*\d+\.?\s*", "", sentence.strip())
            return [{
                "relation": "scope of TYP / SIM conditions", "text": sentence[:_SNIPPET_MAX],
                "scope": "sections and details", "source_text": sentence[:_SNIPPET_MAX],
                "bbox": None, **_where(sheets, page),
            }]
    return []


def _schedule_definitions(
    document: Dict[str, Any],
    page_texts: Dict[int, str],
    typ_insights: List[Insight],
    sheets: Dict[int, str],
    keys: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    keys = keys or []
    grids = [g for g in document.get("schedule_grid") or [] if g.get("rows")]
    grid_pages = {int(g.get("page") or 0) for g in grids}
    words_by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for word in document.get("words") or []:
        page = int(word.get("page_number") or word.get("page") or 0)
        if page in grid_pages:
            words_by_page[page].append(word)
    definitions: List[Dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    column_locations: List[Dict[str, Any]] = []
    spans: List[Tuple[int, str, float, float]] = []
    for grid in grids:
        page = int(grid.get("page") or 0)
        column_locations.extend(
            _column_location(grid, row, sheets)
            for row in grid["rows"]
            if row.get("mark_role") == "grid_location"
        )
        marks = [str(r.get("mark") or "") for r in grid["rows"]]
        page_words = words_by_page[page]
        grid_bbox = grid.get("bbox") or []
        if len(grid_bbox) >= 4:
            page_words = [
                word for word in page_words
                if len(word.get("bbox") or []) >= 4
                and grid_bbox[0] <= (word["bbox"][0] + word["bbox"][2]) / 2 <= grid_bbox[2]
                and grid_bbox[1] <= (word["bbox"][1] + word["bbox"][3]) / 2 <= grid_bbox[3]
            ]
        boxes = _mark_boxes(page_words, marks)
        found_here: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for row in grid["rows"]:
            found = _definition(grid, row, document, sheets, boxes)
            if found:
                reference = _reference(found.get("cells"))
                if reference:
                    found["reference"] = reference
                found_here.append(found)
            elif row.get("cells"):
                skipped.append({"printed_mark": row["mark"], "cells": row["cells"], "bbox": row.get("bbox"),
                                "reason": "no_size"})
        definitions.extend(found_here)
        if found_here and all(d.get("status") in NON_STEEL_STATUSES for d in found_here):
            supporting.append(_schedule_coverage(grid, found_here, skipped, sheets))
        grid_boxes = [boxes[m.upper()] for m in marks if m.upper() in boxes]
        if grid_boxes:
            spans.append((
                page, _grid_kind(grid), min(b[0] for b in grid_boxes), max(b[3] for b in grid_boxes),
            ))
    unreadable = [d for d in definitions if d["relation"] == "unreadable"]
    definitions = [d for d in definitions if d["relation"] != "unreadable"]
    definitions.sort(key=lambda d: (_COMPONENT_ORDER.index(d["component"]), d["page"]))

    rules = (
        _schedule_notes(document, spans, sheets)
        + _symbol_legends(page_texts, sheets)
        + _similar_condition_rules(page_texts, sheets)
        + _key_rules(keys)
    )
    typ_pages = sorted({
        p for i in typ_insights if i.type == "typical_condition" and i.detail.get("present")
        for p in i.source_pages
    })
    if typ_pages:
        rules.append({
            "relation": "scoped convention",
            "text": "TYP, U.N.O. and SIM apply only to the condition or detail they annotate; "
                    "they are not a blanket instruction to repeat members.",
            "scope": "annotated condition", "source_text": "", "bbox": None,
            "pages": typ_pages, "page": typ_pages[0], "sheet": sheets.get(typ_pages[0]),
        })

    # Pages that only POINT at a schedule ("SEE LINTEL SCHEDULE"). A graphical
    # column schedule has no mark rows but is a schedule page all the same.
    grid_kinds = {d["component"]: d for d in definitions}
    column_pages = sorted({
        p for s in (document.get("column_schedules") or {}).get("schedules") or [] for p in s["pages"]
    })
    if column_pages:
        grid_kinds.setdefault("column", {"page": column_pages[0], "sheet": sheets.get(column_pages[0])})
    referenced: Dict[str, List[int]] = defaultdict(list)
    for page, text in page_texts.items():
        if page in grid_pages or page in column_pages:
            continue
        for match in _SCHEDULE_REFERENCE_RE.finditer(text):
            kind = next(
                (k for k in _COMPONENTS if k != "schedule" and k.split("_")[0].upper()
                 in (match.group(1) or "").upper()), None,
            )
            if kind and page not in referenced[kind]:
                referenced[kind].append(page)
    for kind, pages in referenced.items():
        target = grid_kinds.get(kind)
        on = sorted(pages)
        where = ", ".join(f"{sheets.get(p) + ' · ' if sheets.get(p) else ''}PDF p. {p}" for p in on[:6])
        if target:
            text = (f"{where} refer to the {_COMPONENTS[kind][1].lower()}; those pages hold "
                    f"references only -- the definitions are on "
                    f"{(target['sheet'] + ' · ') if target['sheet'] else ''}PDF p. {target['page']}.")
        else:
            text = f"{where} refer to a {_COMPONENTS[kind][1].lower()} that was not found in this set."
        rules.append({
            "relation": "detail reference", "text": text, "scope": "schedule reference",
            "source_text": "SEE " + _COMPONENTS[kind][1].upper(), "bbox": None,
            "pages": on, "page": on[0], "sheet": sheets.get(on[0]),
        })
    rules.sort(key=lambda r: _RULE_RANK.get(
        "schedule reference" if r["scope"] == "schedule reference" else r["relation"], 9,
    ))
    rules = rules[:_MAX_RULES]

    unresolved: List[Dict[str, Any]] = []
    if unreadable:
        pages = sorted({d["page"] for d in unreadable})
        unresolved.append({
            "kind": "unreadable_schedule_rows",
            "text": "Could not read what " + ", ".join(d["mark"] for d in unreadable)
                    + " defines; check the schedule row on the sheet.",
            "pages": pages, "sheet": sheets.get(pages[0]),
        })
    mixed = [d for d in definitions if d["cell_text_mixed"]]
    if mixed:
        pages = sorted({d["page"] for d in mixed})
        unresolved.append({
            "kind": "mixed_schedule_cells",
            "text": (
                "Schedule cells for " + ", ".join(d["mark"] for d in mixed)
                + " also captured text from an adjacent table; the values shown were "
                "cleaned from the printed size -- spot-check them on the sheet."
            ),
            "pages": pages, "sheet": sheets.get(pages[0]),
        })
    for kind in referenced:
        if kind not in grid_kinds:
            unresolved.append({
                "kind": "missing_schedule",
                "text": f"{_COMPONENTS[kind][1]} is referenced but was not found; its marks cannot be read.",
                "pages": sorted(referenced[kind]), "sheet": sheets.get(min(referenced[kind])),
            })
    bracket: Dict[int, int] = Counter()
    for page, text in page_texts.items():
        hits = len(_BRACKET_TAG_RE.findall(text))
        if hits:
            bracket[page] = hits
    defined_in_text = any(
        re.search(r"\[[^\]]{0,6}\][^.]{0,40}\b(?:DENOTES?|INDICATES?)\b", text, re.I)
        for text in page_texts.values()
    )
    # A graphical framing key (leader from the bracket to a printed label)
    # defines the bracket as well as a sentence does; ``_key_rules`` shows it.
    by_key = bracket_definition(keys)
    if sum(bracket.values()) >= 10 and not defined_in_text and by_key["status"] != "defined":
        pages = sorted(bracket)
        example = _BRACKET_TAG_RE.search(page_texts[pages[0]]).group(0)
        if by_key["status"] == "conflicting":
            unresolved.append({
                "kind": "conflicting_bracket_definition",
                "text": (f"Numbers in brackets after beam sizes (e.g. {example}) are defined differently by the "
                         f"set's framing keys: {'; '.join(by_key['meanings'])}. Confirm which applies; "
                         "do not read them as member quantities."),
                "pages": sorted({s['page'] for s in by_key["sources"]} | set(pages)),
                "sheet": sheets.get(pages[0]),
            })
        else:
            unresolved.append({
                "kind": "undefined_bracket_tag",
                "text": (
                    f"Numbers in brackets after beam sizes (e.g. {example}) appear on plans, but no note and "
                    f"no framing key in the set defines them ({by_key['missing']}). Confirm their meaning on the "
                    "plan legend; do not read them as member quantities."
                ),
                "pages": pages, "sheet": sheets.get(pages[0]),
            })

    return {
        "definitions": [{**d, "id": f"D{i}"} for i, d in enumerate(definitions, 1)],
        "interpretation_rules": [{**r, "id": f"R{i}"} for i, r in enumerate(rules, 1)],
        "unresolved": [{**u, "id": f"U{i}"} for i, u in enumerate(unresolved, 1)],
        "column_locations": column_locations,
        "supporting_schedules": supporting,
    }


# A printed cell that sends the reader elsewhere for the row's content
# ("SEE SECTION FOR REINFORCEMENT", "DESIGNED BY CONTRACTOR'S ENGINEER").
_REFERENCE_RE = re.compile(r"\b(?:SEE|REFER\s+TO)\b|\bDESIGNED\s+BY\b|\bBY\s+OTHERS\b", re.IGNORECASE)


def _display_row_box(row: dict[str, Any]) -> list[float] | None:
    boxes = [box for box in [row.get("bbox"), *(c.get("bbox") for c in row.get("cells") or [])] if box]
    return _union_boxes(boxes) if boxes else None


def _reference(cells: list[dict[str, Any]] | None) -> str | None:
    return next((c["text"] for c in cells or [] if _REFERENCE_RE.search(c.get("text") or "")), None)


def _schedule_coverage(grid: dict[str, Any], found: list[dict[str, Any]], skipped: list[dict[str, Any]],
                       sheets: dict[int, str]) -> dict[str, Any]:
    """How much of a supporting (non-steel) schedule the summary shows. The
    printed total is known only for a ruled table, whose body rows were all
    read with their mark cells; rows not taken are listed as printed, each
    with any cell that refers to another source. Nothing is inferred for
    them (a precast beam's size stays the precast designer's)."""

    unread = [{**row, "reason": "mark_not_read"} for row in grid.get("unread_rows") or []] + skipped
    page = int(grid.get("page") or 0)
    return {
        "title": grid.get("title"),
        "kind": grid.get("kind"),   # wall / pier / footing / beam ... as titled
        "page": page,
        "bbox": _union_boxes([b for b in [grid.get("bbox"), *(_display_row_box(r) for r in grid["rows"]),
                                          *(_display_row_box(r) for r in unread)] if b]),
        "printed_rows": grid.get("printed_rows"),
        "extracted_rows": len(found),
        "unread_rows": [{**row, "bbox": _display_row_box(row), "reference": _reference(row["cells"])} for row in unread],
        **_where(sheets, page),
    }


def _key_rules(keys: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One interpretation rule per framing key: each callout part with the
    printed label its leader ends at. A part with no leader, or whose leader
    ends at two labels, is stated as such -- never given a meaning."""

    rules = []
    for key in keys:
        defined = [p for p in key["parts"] if p["status"] == "defined"]
        if not defined:
            continue
        parts = "; ".join(f"{p['token']} = {p['meaning']}" for p in defined)
        open_parts = [p["token"] for p in key["parts"] if p["status"] != "defined"]
        rules.append({
            "relation": "notation key", "kind": "framing_key",
            "text": (f"{key['title'].title()}: in a beam callout such as {key['example']}, {parts}."
                     + (f" Not defined (no leader to a visible label): {', '.join(open_parts)}." if open_parts else "")
                     + " The key's own numbers are an example, not a count."),
            "scope": "project legend", "source_text": key["example"],
            "bbox": key["region"], "page": key["page"], "pages": [key["page"]], "sheet": key["sheet"],
            "parts": [{k: p.get(k) for k in ("token", "form", "meaning", "field", "status", "bbox", "label_bbox", "hidden_text")}
                      for p in key["parts"]],
        })
    return rules


def _column_location(
    grid: Dict[str, Any], row: Dict[str, Any], sheets: Dict[int, str],
) -> Dict[str, Any]:
    """One Revit column-schedule cell (grid location x printed row) for display.

    Never a mark definition, member instance or quantity, and never evidence
    for the summary model: ``_mark_rows`` keeps these rows out of mark
    resolution, and ``evidence_facts`` does not read this list.
    """

    plate = _clean(row.get("plate_text"))
    record = {
        "location": str(row.get("mark") or ""),
        "level": _clean(row.get("level")) or None,
        "printed_size": _clean(row.get("size_text")) or None,
        "catalog_designation": _catalog_designation(row["section"]) if row.get("section") else None,
        "printed_base_plate": plate or None,
        "schedule": grid.get("title"),
        "bbox": grid.get("bbox"),
        "source": "schedule_grid",
        "is_definition_not_quantity": True,
        **_where(sheets, int(grid.get("page") or 0)),
    }
    # ``level`` is the printed band; ``level_band`` says which level each
    # printed part belongs to (never a level of its own unless paired).
    if isinstance(row.get("level_band"), dict):
        record["level_band"] = row["level_band"]
    parsed = row.get("parsed_location")
    if isinstance(parsed, dict):
        record["parsed_location"] = parsed
    plate_parsed = row.get("parsed_plate")
    if isinstance(plate_parsed, dict):
        record["parsed_plate"] = plate_parsed
    if row.get("plate_status"):
        record["plate_status"] = row.get("plate_status")
    if isinstance(row.get("resolved_plate"), dict):
        record["resolved_plate"] = row["resolved_plate"]
    return record


# Definition statuses of marks that are not steel (concrete walls, piers,
# footings; precast lintels; "N/A" rows).
NON_STEEL_STATUSES = frozenset({"not steel", "precast", "no steel"})


def _deterministic_overview(profile: Dict[str, Any]) -> str:
    """One or two short sentences: what the set is and where its steel is
    defined. Details (schedule lists, conflicts) have their own sections."""

    stamps = [s["detail"]["label"] for s in profile["scope_signals"] if s["detail"].get("present")]
    first = f"{profile['page_count']}-page structural set" + (f" ({', '.join(stamps).lower()})" if stamps else "")
    schedules = (profile.get("column_schedule") or {}).get("schedules") or []
    steel_sheets = sorted({s.get("sheet") or f"PDF p. {s['page']}" for s in schedules
                           if s.get("material_group") != "concrete"})
    steel_defs = [d for d in profile["definitions"] if d.get("status") not in NON_STEEL_STATUSES]
    kinds = [_COMPONENTS[k][2] for k in _COMPONENT_ORDER if any(d["component"] == k for d in steel_defs)]
    defined = []
    if steel_sheets:
        defined.append(("steel column schedules" if len(steel_sheets) > 1 else "a steel column schedule")
                       + f" on {', '.join(steel_sheets)}")
    if kinds:
        where = sorted({d["sheet"] or f"PDF p. {d['page']}" for d in steel_defs})
        defined.append(f"{' and '.join(kinds)} marks defined on {', '.join(where)}")
    if defined:
        first += " with " + " and ".join(defined)
    concrete = any(s.get("material_group") == "concrete" for s in schedules) or len(steel_defs) < len(profile["definitions"])
    if concrete:
        first += "; concrete schedules are kept with the supporting information"
    if not (defined or concrete):
        families = profile["steel_system"]["families"]
        first += (f". Most explicit section labels are {families[0]['label']}; no MARK/SIZE schedule definitions were read"
                  if families else ". No MARK/SIZE schedule definitions and no catalog-valid steel section labels were read")
        return first + "."
    return first + ". Schedule entries are definitions, not installed quantities."


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

    sheets = _sheet_ids(document)
    box = display_boxes(document)
    keys = read_framing_keys(document, sheets)
    page_group_insights, category_of = _classify_pages(document, page_texts, context_pages)
    family_insights, steel_payload = _steel_families(document)
    typ_insights = _typical_conditions(document, page_texts, category_of)
    schedule_insights = _schedule_insights(document)
    scope_insights = _scope_signals(document, page_texts)
    reno_insight, reno_payload = _existing_new(page_texts, full_text)
    note_insights = _structural_notes(page_texts, context_pages)

    uncertainties: List[Insight] = [
        i for i in page_group_insights + scope_insights if i.type == "uncertainty"
    ]
    # Text blobs on framing plans are plan callouts, not tables; the rest are
    # reported once, not one warning per page.
    framing = {"roof_framing", "floor_framing", "column_plan", "framing_plan_unlabeled", "bracing"}
    unclear_pages: List[int] = []
    kept: List[Insight] = []
    for sched in schedule_insights:
        if sched.detail.get("kind") == "unclassified_steel_table":
            if category_of.get(sched.detail["page"]) in framing:
                continue
            unclear_pages.append(sched.detail["page"])
        kept.append(sched)
    schedule_insights = kept
    if unclear_pages:
        uncertainties.append(Insight(
            type="uncertainty",
            value=f"Structural tables with unresolved row/cell semantics on page(s) {', '.join(map(str, unclear_pages))}",
            confidence=0.5,
            source_pages=unclear_pages,
            scope="document",
            detail={"kind": "schedule_semantics", "pages": unclear_pages},
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
        # Source boxes go to the viewer in display space (``page_space``).
        **convert_boxes(_schedule_definitions(document, page_texts, typ_insights, sheets, keys), box),
        # Display-only column entries (section, locations, plate, notes); not
        # evidence for the summary model and never a quantity.
        "column_schedule": convert_boxes(column_schedule_view(document, sheets), box),
        # Levels and elevations from schedules and plan notes, each sourced;
        # display-only like the column schedule.
        # A framing key's own example is a definition, not a plan observation.
        "levels": levels_view(document, sheets,
                              legend_regions={k["page"]: [box(k["page"], k["region"])] for k in keys}),
    }
    profile["facts"] = summary_facts(profile)
    profile["narrative"] = _render_narrative(profile)
    profile["narrative"]["project_overview"] = _deterministic_overview(profile) + (
        " The set distinguishes existing and new framing."
        if profile["existing_new"].get("is_renovation") else ""
    )
    profile["overview"] = profile["narrative"]["project_overview"]
    return profile


def where_label(item: Dict[str, Any]) -> str:
    """``S002 · PDF p. 2`` (sheet only when one was read confidently)."""

    pages = item.get("pages") or ([item["page"]] if item.get("page") else [])
    shown = ", ".join(str(p) for p in pages[:6]) + ("…" if len(pages) > 6 else "")
    label = f"PDF p{'p' if len(pages) > 1 else ''}. {shown}" if pages else ""
    return f"{item['sheet']} · {label}" if item.get("sheet") else label


def definition_line(item: Dict[str, Any]) -> str:
    """``L1 → W8X21 | bottom plate | bearing plate 6"x6"x1/2"``; a plate
    mark reads ``BP3 → bearing plate 6"x6"x5/8" (printed size)``."""

    if item.get("designation"):
        head = f"{item['mark']} → {item['designation']}"
    elif item["relation"] == "mark defines plate":
        head = f"{item['mark']} → {item['role']} {item['printed']} (printed size)"
    else:
        head = f"{item['mark']} → {item['printed']}"
    return " | ".join([
        head, *item.get("configuration", []),
        *(f"{p['role']} {p['printed']}" for p in item.get("parts", [])),
        *([item["status"]] if item.get("status") else []),
    ])


_MAX_COLUMN_FACTS = 6


def _difference(inches: float) -> str:
    """``8"`` under a foot, else feet-inches; the magnitude only."""

    text = format_elevation(abs(inches))
    return text.split("'-", 1)[1] if text.startswith("0'-") else text


def _plate_phrase(plate: Dict[str, Any]) -> str:
    if plate.get("status") == "resolved" and plate.get("dimensions"):
        dims = ", ".join(f"{d['label']} {d['raw']}" for d in plate["dimensions"])
        table = next((v for v in plate.get("via") or [] if v.get("kind") == "plate schedule"), None)
        return (f"base plate {plate.get('printed')} ({dims}"
                + (f"; from {str(table.get('title') or 'plate schedule').title()}, {where_label(table)}" if table else "")
                + ")")
    if plate.get("printed"):
        return f"base plate {plate['printed']} (dimensions not linked: {plate.get('status')})"
    return f"base plate {str(plate.get('status') or 'not shown').replace('_', ' ')}"


def summary_facts(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Typed, sourced facts for the overview model, with stable ids, built
    from the validated profile -- never from model output.

    * ``X`` level conflicts: both printed values, both sources, the
      difference; status ``conflicting`` (never resolved);
    * ``K`` schedule levels linked to a plan datum / note in scope;
    * ``C`` representative steel column entries: section, plate assignment
      and plate dimensions with their roles, and the level-to-level
      elevation difference when both ends sit on level lines (calculated
      from stated values; not a fabricated length). A selection, not the
      schedule: one entry per distinct section + plate;
    * ``M`` material a schedule note states for a label family (C_ precast);
    * ``G`` grid-location offsets read as locations, not elevations.

    Each fact keeps ``refs`` / ``sources`` to what it describes, so the
    summary renders canonical values and links from the data, never from
    the model's words."""

    facts: List[Dict[str, Any]] = []
    levels = (profile.get("levels") or {}).get("schedule_levels") or []
    for level in levels:
        schedule_source = {"page": level["page"], "sheet": level.get("sheet"), "bbox": level.get("bbox")}
        for match in level.get("plan_matches") or []:
            if match.get("association") != "supported":
                continue
            for value in (v for v in match["values"] if v.get("compared")):
                plan_value = value.get("raw") or value["display"]
                base = {
                    "level": level["name"], "schedule": level["schedule"], "schedule_value": level["printed"],
                    "plan_value": plan_value, "plan_sheet": match["sheet"], "surface": value["surface"],
                    "sources": [schedule_source, value["source"]],
                    "refs": {"schedule_id": level["schedule_id"], "level": level["name"], "plan_page": match["page"]},
                }
                if match["comparison"] == "differs" and level.get("elevation"):
                    diff = level["elevation"]["inches"] - value["inches"]
                    facts.append({
                        **base, "type": "level_conflict", "status": "conflicting", "difference": _difference(diff),
                        "difference_inches": round(diff, 4),
                        "text": (f"{level['schedule']}: {level['name']} is {level['printed']} in the column schedule "
                                 f"({where_label(schedule_source)}); the {match['sheet']} plan note gives "
                                 f"{value['surface']} {plan_value} ({where_label(value['source'])}). "
                                 f"Difference {_difference(diff)}. Both values stand; the drawing does not say "
                                 "which governs."),
                    })
                elif match["comparison"] == "agrees":
                    named = f" (the plan names it {value['name']})" if value.get("name") else ""
                    facts.append({
                        **base, "type": "level_link", "status": "read",
                        "text": (f"{level['schedule']}: {level['name']} {level['printed']} (column schedule, "
                                 f"{where_label(schedule_source)}) agrees with the {match['sheet']} plan note, "
                                 f"{value['surface']} {plan_value}{named}."),
                    })
    column = profile.get("column_schedule") or {}
    names = {s["id"]: s["name"] for s in column.get("schedules") or []}
    groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for entry in column.get("entries") or []:
        designation = next((s["designation"] for s in entry["sections"] if s.get("designation")), None)
        if designation:
            groups[(designation, (entry.get("plate") or {}).get("printed"))].append(entry)
    ranked = sorted(groups.items(),
                    key=lambda kv: (-((kv[1][0].get("plate") or {}).get("status") == "resolved"), -len(kv[1])))
    for (designation, _plate), group in ranked[:_MAX_COLUMN_FACTS]:
        entry = group[0]
        where = entry.get("location_text") or entry.get("mark")
        diff = entry.get("level_difference") or {}
        span = (f" Drawn from {diff['lower']['name']} ({diff['lower']['elevation']}) to {diff['upper']['name']} "
                f"({diff['upper']['elevation']}): elevation difference {diff['display']}, calculated from the "
                "schedule's elevations; not a fabricated member length."
                if diff.get("status") == "computed" else "")
        plate = entry.get("plate") or {}
        facts.append({
            "type": "column", "status": "read" if plate.get("status") == "resolved" else "partial",
            "schedule": names.get(entry["schedule_id"]), "location": where, "section": designation,
            "plate": plate.get("printed"),
            "sources": [{"page": entry["page"], "sheet": entry.get("sheet"), "bbox": entry.get("bbox")}]
            + list(plate.get("via") or []),
            "refs": {"column_entry": entry["id"]},
            "text": (f"{names.get(entry['schedule_id'])} ({where_label(entry)}): column at {where} -> {designation}; "
                     f"{_plate_phrase(plate)}.{span} Shown as an example of {len(group)} schedule "
                     "entries with this section and plate; a schedule entry is not an installed column."),
        })
    seen_materials = set()
    for entry in column.get("entries") or []:
        material = entry.get("material") or {}
        if material.get("status") != "read" or (entry["schedule_id"], material["mark"]) in seen_materials:
            continue
        seen_materials.add((entry["schedule_id"], material["mark"]))
        size = (material.get("size") or {}).get("raw")
        facts.append({
            "type": "material", "status": "read", "schedule": names.get(entry["schedule_id"]),
            "mark": material["mark"], "material": material["material"], "size": size,
            "sources": [material["source"]], "refs": {"schedule_id": entry["schedule_id"]},
            "text": (f"{names.get(entry['schedule_id'])}: {material['mark']} columns are {material['material']} "
                     f"per the schedule note \"{material['source']['text']}\" ({where_label(material['source'])})"
                     + (f"; printed size {size}" if size else "") + ". Not steel."),
        })
    offsets = (profile.get("levels") or {}).get("location_offsets") or []
    if offsets:
        examples = list(dict.fromkeys(o["location"] for o in offsets))[:3]
        facts.append({
            "type": "grid_offset", "status": "read", "examples": examples,
            "sources": [{"page": o["page"], "sheet": o.get("sheet"), "bbox": o.get("bbox")} for o in offsets[:3]],
            "text": (f"Bracketed values inside grid locations ({', '.join(examples)}) are offsets of a grid line "
                     "within the location, not elevations; the legend's bracket notation does not apply to them."),
        })
    prefix = {"level_conflict": "X", "level_link": "K", "column": "C", "material": "M", "grid_offset": "G"}
    counters: Dict[str, int] = defaultdict(int)
    for fact in facts:
        letter = prefix[fact["type"]]
        counters[letter] += 1
        fact["id"] = f"{letter}{counters[letter]}"
    return facts


def evidence_facts(profile: Dict[str, Any]) -> Dict[str, str]:
    """``{fact id: exact fact text}`` -- the only facts the summary model may cite."""

    facts: Dict[str, str] = {}
    for d in profile.get("definitions") or []:
        title = str(d.get("schedule_title") or d["schedule"]).title()
        facts[d["id"]] = f"{title} ({where_label(d)}): {definition_line(d)} [{d['relation']}]"
    for r in profile.get("interpretation_rules") or []:
        facts[r["id"]] = f"({r['relation']}; {r['scope']}; {where_label(r)}) {r['text']}"
    for u in profile.get("unresolved") or []:
        facts[u["id"]] = f"({where_label(u)}) {u['text']}"
    typed = profile.get("facts")
    for fact in typed if typed is not None else summary_facts(profile):
        facts[fact["id"]] = fact["text"]
    return facts


_PACKET_SECTIONS = (
    ("X", "CONFLICTS BETWEEN SOURCES -- both values stand; never choose, average or resolve them:"),
    ("K", "SCHEDULE LEVELS LINKED TO PLAN NOTES (same building / area):"),
    ("C", "SELECTED STEEL COLUMN ENTRIES -- examples chosen from the column schedule, one per distinct section "
          "and plate; NOT the complete schedule and NOT installed members:"),
    ("M", "MATERIAL STATED BY SCHEDULE NOTES:"),
    ("G", "LOCATION NOTATION:"),
    ("R", "RULES AFFECTING INTERPRETATION (verbatim notes and keys):"),
    ("U", "UNRESOLVED ITEMS:"),
    ("D", "OTHER SCHEDULE DEFINITIONS -- each says how to READ a mark on plan; a schedule row is NOT an "
          "installed member and NOT a quantity:"),
)


def evidence_packet(profile: Dict[str, Any], *, max_chars: int = 6000) -> str:
    """Plain-text evidence for the optional summary model, each fact under a
    citable id. Whole facts only: when the budget runs out, the remaining
    facts are left out *and the packet says so* -- a fact is never cut
    mid-record. Conflicts and linked levels come first, then the selected
    columns; non-steel schedule definitions last."""

    facts = evidence_facts(profile)
    stamps = [s["detail"]["label"] for s in profile["scope_signals"] if s["detail"].get("present")]
    families = [f["label"] for f in profile["steel_system"]["families"]]
    lines = [
        f"DRAWING SET: {profile['page_count']} pages"
        + (f"; issue stamps: {', '.join(stamps)}" if stamps else ""),
        "STEEL SYSTEM (families named on labels; not member quantities): "
        + (", ".join(families) if families else "none read"),
        "DETERMINISTIC OVERVIEW: " + str(profile.get("overview") or ""),
    ]
    non_steel = {d["id"] for d in profile.get("definitions") or [] if d.get("status") in NON_STEEL_STATUSES}
    definitions = sorted((k for k in facts if k.startswith("D")), key=lambda k: k in non_steel)
    used = sum(len(line) + 1 for line in lines)
    omitted = 0
    reserve = 120   # room for the omission line
    for prefix, title in _PACKET_SECTIONS:
        ids = definitions if prefix == "D" else [k for k in facts if k[0] == prefix and k[1:].isdigit()]
        rows = [f"  [{k}] {facts[k]}" for k in ids]
        if not rows:
            continue
        if used + len(title) + len(rows[0]) + 2 > max_chars - reserve:
            omitted += len(rows)
            continue
        lines.append(title)
        used += len(title) + 1
        for row in rows:
            if used + len(row) + 1 > max_chars - reserve:
                omitted += 1
                continue
            lines.append(row)
            used += len(row) + 1
    if omitted:
        lines.append(f"({omitted} further facts left out for length -- they are shown in the summary itself.)")
    return "\n".join(lines)
