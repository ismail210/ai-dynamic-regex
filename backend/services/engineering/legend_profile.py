"""Project Context Profile -- deep analysis of a document's legend/notes
pages (formerly "legend profile"; kept this module name/internal function
names for compatibility rather than renaming dozens of call sites for no
architectural benefit -- see module docstring in legend_profile_hook.py for
the external-facing rationale).

Reads ONLY the text-dense, non-drawing pages of a document (legend,
general/structural/steel notes, abbreviations, specifications, design
criteria, connection notes, special/typical notes) and produces a
document-scoped, cached analysis of project-specific conventions, material/
connection/fabrication notes, and cross-note deductions -- for display to
the estimator.

Checkpoint 2 changes (see docs accompanying this commit for the full
diagnosis): a real customer PDF (ST__0bfc2d61245d.pdf) produced an empty
panel. Root-caused to two independent problems, both fixed here:

1. Page-role classification relied on ``document_prior.detect_legend_pages``
   as an unconditional fallback whenever no heading matched. That scorer
   was built for a *soft* reranking-confidence consumer (tolerant of being
   occasionally wrong) and was never precise enough to gate "should the LLM
   read this entire page" -- on the real PDF it flagged three genuine
   framing/foundation PLAN pages (dense with real "(E) W14x22"-style member
   schedules) as legend-like, purely because they contained many distinct
   AISC-shape strings (the scorer's "many sections = legend-like" signal,
   which backfires on an actual framing plan). ``_looks_like_drawing_page``
   below is a new, independent negative filter for exactly this failure
   mode: a page dense with Existing/New-tagged member callouts is a plan
   page regardless of what the soft scorer says.
2. Heading matching was restricted to the first 200 characters of a page
   (a precision fix for a *different*, earlier false positive -- see git
   history) but the real PDF's actual "GENERAL NOTES" heading sits ~650
   characters into the page, after a full title-block/sheet-index preamble
   on the same page. Fixed by searching the WHOLE page text and taking
   whichever heading pattern matches EARLIEST in the text, rather than
   only searching a fixed prefix -- this satisfies both documents at once
   (GCDC's false "ABBREVIATIONS" mid-sentence match no longer wins because
   its own real "GENERAL NOTES" heading is earlier in the text; the real
   PDF's late-but-real heading is still found because there's no window).

This module is still informational only. It:

* never mutates ``engineering_tokens``, candidate generation, ranking, or
  any prediction;
* never inserts a family into a token that did not already carry one in
  its own extracted text (the exact behavior the ``reliable_family``
  mechanism, added in 9731651 and removed in 8b3d065, was ruled out for);
* keeps every extracted item's ``status`` as ``PROPOSED_INFERENCE`` --
  nothing here is authoritative, and nothing here is applied to a
  prediction, regardless of whether it's a directly-quoted source fact or
  a cross-note derived insight.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.database_loader import catalog_form
from services.engineering.document_prior import detect_legend_pages
from services.structural_parser import parse_section
from services.token_extractor import normalize_engineering_token

PROFILE_VERSION = "legend_profile_v2"
EXTRACTOR_VERSION = "legend_extractor_v2"
SCHEMA_VERSION = "legend_schema_v2"

STATUS_PROPOSED_INFERENCE = "PROPOSED_INFERENCE"

METHOD_DETERMINISTIC = "deterministic"
METHOD_LLM_PROPOSED = "llm_proposed"

# Overall per-document analysis outcome -- always set, so the UI/API never
# has to guess *why* a panel is empty (see legend_profile_hook.py).
ANALYSIS_SUCCESS = "SUCCESS"
ANALYSIS_NO_CONTEXT_PAGES = "NO_CONTEXT_PAGES"
ANALYSIS_NO_RELEVANT_INFORMATION = "NO_RELEVANT_INFORMATION"
ANALYSIS_MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
ANALYSIS_MODEL_ERROR = "MODEL_ERROR"
ANALYSIS_VISION_REQUIRED = "VISION_REQUIRED"
ANALYSIS_DISABLED = "DISABLED"

# Structural-steel-estimating categories a source fact may belong to (see
# section 9 of the request this implements: notation, materials,
# connections, fabrication, structural interpretation, estimator scope).
CATEGORY_SECTION_NOTATION = "SECTION_NOTATION"
CATEGORY_MATERIAL = "MATERIAL"
CATEGORY_CONNECTION = "CONNECTION"
CATEGORY_FABRICATION = "FABRICATION"
CATEGORY_INTERPRETATION = "INTERPRETATION"
CATEGORY_RESPONSIBILITY = "RESPONSIBILITY"
CATEGORY_SCOPE = "SCOPE"
CATEGORY_OTHER = "OTHER"

_ALLOWED_CATEGORIES = {
    CATEGORY_SECTION_NOTATION,
    CATEGORY_MATERIAL,
    CATEGORY_CONNECTION,
    CATEGORY_FABRICATION,
    CATEGORY_INTERPRETATION,
    CATEGORY_RESPONSIBILITY,
    CATEGORY_SCOPE,
    CATEGORY_OTHER,
}

PAGE_ROLE_LEGEND = "LEGEND"
PAGE_ROLE_GENERAL_NOTES = "GENERAL_NOTES"
PAGE_ROLE_STRUCTURAL_NOTES = "STRUCTURAL_NOTES"
PAGE_ROLE_ABBREVIATIONS = "ABBREVIATIONS"
PAGE_ROLE_SPECIFICATIONS = "SPECIFICATIONS"
PAGE_ROLE_VISION_REQUIRED = "VISION_REQUIRED"
PAGE_ROLE_EXCLUDED_DRAWING_PAGE = "EXCLUDED_DRAWING_PAGE"

_CONTEXT_PAGE_ROLES = {
    PAGE_ROLE_LEGEND,
    PAGE_ROLE_GENERAL_NOTES,
    PAGE_ROLE_STRUCTURAL_NOTES,
    PAGE_ROLE_ABBREVIATIONS,
    PAGE_ROLE_SPECIFICATIONS,
}

# Minimum extracted-text length for a page that scored as a legend/notes
# page to be treated as usable text (rather than a scan Estima3D cannot
# read yet). No OCR/VLM call is made here; a page below this threshold is
# only ever flagged, never silently treated as "no useful notes found".
_VISION_REQUIRED_MIN_CHARS = 40

_DIM_TEXT_RE = r"\d+(?:-\d+/\d+|/\d+|\.\d+)?"
_ABBREV_TRIGGER_RE = re.compile(
    r'"([A-Za-z0-9./\-]{1,14})"\s*[=:]\s*'
    r"([A-Za-z]{1,4}\s?"
    + _DIM_TEXT_RE
    + r"(?:\s*[Xx×]\s*"
    + _DIM_TEXT_RE
    + r")*)"
    r"(?![A-Za-z0-9/])"
)

# (role, pattern) in priority order used ONLY as a tie-break when two
# patterns match at the exact same position (never happens in practice,
# kept for determinism). The real decision below is "earliest match wins",
# not list order -- see _classify_page_role.
_HEADING_PATTERNS = (
    (PAGE_ROLE_LEGEND, re.compile(r"\bLEGEND\b|\bSYMBOLS\s+AND\s+NOTATIONS?\b|\bSTRUCTURAL\s+SYMBOLS\b", re.I)),
    (PAGE_ROLE_ABBREVIATIONS, re.compile(r"\bABBREVIATIONS?\b", re.I)),
    (PAGE_ROLE_SPECIFICATIONS, re.compile(r"\bSPECIFICATIONS?\b", re.I)),
    (
        PAGE_ROLE_STRUCTURAL_NOTES,
        re.compile(
            r"\bSTRUCTURAL\s+NOTES?\b|\bSTEEL\s+NOTES?\b|\bDESIGN\s+CRITERIA\b"
            r"|\bCONNECTION\s+NOTES?\b|\bSPECIAL\s+NOTES?\b|\bTYPICAL\s+NOTES?\b",
            re.I,
        ),
    ),
    (PAGE_ROLE_GENERAL_NOTES, re.compile(r"\bGENERAL\s+NOTES?\b", re.I)),
)

# A page dense with Existing/New-tagged real member callouts (the
# unmistakable signature of an actual framing/foundation plan sheet) is
# excluded even if document_prior's soft scorer flagged it as legend-like.
# See module docstring, failure mode 1.
_MEMBER_CALLOUT_RE = re.compile(
    r"\((?:E|N)\)\s*(?:W|WT|HSS|L|2L|C|MC|PIPE|M|S|HP)\d", re.I
)
_DRAWING_PAGE_MIN_CALLOUTS = 2


def _page_text(document: Dict[str, Any], page_number: int) -> str:
    """Duplicated from document_prior._page_text intentionally -- this
    module must never be able to change document_prior's already-tested
    behavior by sharing a private helper with it."""

    chunks: List[str] = []
    for block in document.get("blocks") or []:
        if int(block.get("page_number") or 0) != page_number:
            continue
        chunks.append(str(block.get("text") or ""))
    if not chunks:
        for line in document.get("lines") or []:
            if int(line.get("page_number") or 0) == page_number:
                chunks.append(str(line.get("text") or ""))
    return "\n".join(chunks)


def compute_document_hash(document: Dict[str, Any]) -> str:
    """Content hash used as (part of) the profile cache key -- never a
    filename-only key, so a changed/re-uploaded PDF never serves a stale
    cached profile."""

    text = str(document.get("text") or "")
    if text.strip():
        basis = text
    else:
        chunks: List[str] = []
        for key in ("blocks", "lines"):
            for item in document.get(key) or []:
                chunks.append(
                    "{}:{}:{}".format(
                        item.get("page_number") or "",
                        item.get("bbox") or "",
                        item.get("text") or "",
                    )
                )
        basis = "\n".join(chunks)
        if not basis.strip():
            basis = "{}::{}".format(
                document.get("source_file") or "", document.get("page_count") or 0
            )
    return hashlib.sha256(basis.encode("utf-8", errors="ignore")).hexdigest()[:32]


def _looks_like_drawing_page(text: str) -> bool:
    """True when a page is dense with real, tagged member-schedule
    callouts -- i.e. an actual framing/foundation plan, not a notes page.
    See module docstring, failure mode 1, for the real document that
    exposed this."""

    return len(_MEMBER_CALLOUT_RE.findall(text)) >= _DRAWING_PAGE_MIN_CALLOUTS


def _classify_page_role(text: str, *, is_legend_page: bool) -> Optional[str]:
    """Whichever heading pattern matches EARLIEST in the page text wins --
    not a fixed priority order, and not limited to a text prefix. This is
    what lets a real "GENERAL NOTES" heading win over a later, incidental
    mention of the word "abbreviations" in body prose (GCDC), while still
    finding a real heading that sits after a long title-block/sheet-index
    preamble on the same page (the ST.pdf failure this checkpoint fixes)."""

    # Checked FIRST, unconditionally -- a real framing/foundation plan page
    # can still carry a small on-sheet note ("SEE GENERAL NOTES...") that
    # would otherwise win the heading-match race below even though the
    # page as a whole is dense with real member-schedule callouts, not
    # project-level notes. See module docstring, failure mode 1.
    if _looks_like_drawing_page(text):
        return None

    best_role: Optional[str] = None
    best_index: Optional[int] = None
    for role, pattern in _HEADING_PATTERNS:
        match = pattern.search(text)
        if match and (best_index is None or match.start() < best_index):
            best_index = match.start()
            best_role = role
    if best_role is not None:
        return best_role
    if is_legend_page:
        return PAGE_ROLE_LEGEND
    return None


def detect_context_pages(document: Dict[str, Any]) -> Dict[int, str]:
    """Deterministic page-role classification, context pages only.

    Reuses ``document_prior.detect_legend_pages`` as one candidate signal
    (never the sole gate -- see ``_looks_like_drawing_page``) so this
    module still benefits from that already-tested scoring without
    inheriting its false-positive rate on real framing/foundation plans.

    Ordinary drawing/framing/detail pages are never included here, even
    if they contain some text -- this function is the sole gate for which
    pages this feature is allowed to read at all.
    """

    page_count = int(document.get("page_count") or 0)
    if page_count <= 0:
        return {}
    legend_pages = set(detect_legend_pages(document))
    roles: Dict[int, str] = {}
    for page_number in range(1, page_count + 1):
        text = _page_text(document, page_number)
        if not text.strip():
            continue
        role = _classify_page_role(text, is_legend_page=page_number in legend_pages)
        if role is None:
            continue
        if len(text.strip()) < _VISION_REQUIRED_MIN_CHARS:
            roles[page_number] = PAGE_ROLE_VISION_REQUIRED
        else:
            roles[page_number] = role
    return roles


def _readable_context_pages(context_pages: Dict[int, str]) -> List[int]:
    return sorted(
        page for page, role in context_pages.items() if role in _CONTEXT_PAGE_ROLES
    )


def _quote_around(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return text[line_start : line_end if line_end != -1 else len(text)].strip()


def extract_abbreviation_rules(
    document: Dict[str, Any], context_pages: Dict[int, str]
) -> List[Dict[str, Any]]:
    """Deterministic-only extraction of explicit ``"X" = Y`` member-size
    substitution rules (e.g. ``"W8" = W8x10``).

    Deliberately regex-only, never LLM-proposed: an explicit table/legend
    pair is exactly the case a fixed pattern already handles precisely, and
    keeping it deterministic means every field is reparsed directly from
    the source text rather than trusted from a model response.

    Every candidate rule must pass, in order:

    1. the trigger (LHS) is NOT itself already a complete, catalog-valid
       designation on its own -- otherwise it isn't a substitution, it's a
       restatement;
    2. the target (RHS) DOES parse as a real, catalog-valid designation --
       an unresolved/guessed target is never stored;
    3. LHS and RHS parse to the SAME family.

    Gate 3 is the direct, load-bearing answer to "does this reintroduce
    reliable_family under a different name?" It does not. reliable_family
    was removed because nothing may attach a family to a token from
    *context* when the token's own text has none. This extractor never
    looks at token text at all -- it only accepts a rule when the source
    document's own LHS and RHS already agree on family with each other.
    """

    rules: List[Dict[str, Any]] = []
    for page_number in _readable_context_pages(context_pages):
        text = _page_text(document, page_number)
        for match in _ABBREV_TRIGGER_RE.finditer(text):
            lhs_raw = match.group(1).strip()
            rhs_raw = match.group(2).strip()
            lhs_norm = normalize_engineering_token(lhs_raw)
            rhs_norm = normalize_engineering_token(rhs_raw)
            if not lhs_norm or not rhs_norm or lhs_norm == rhs_norm:
                continue
            lhs_parsed = parse_section(lhs_norm)
            if lhs_parsed and lhs_parsed.catalog_valid:
                continue
            rhs_parsed = parse_section(rhs_norm)
            if not (rhs_parsed and rhs_parsed.catalog_valid):
                continue
            if (
                lhs_parsed
                and rhs_parsed
                and lhs_parsed.family
                and rhs_parsed.family
                and lhs_parsed.family != rhs_parsed.family
            ):
                continue
            canonical_rhs = catalog_form(rhs_norm) or rhs_norm
            quote = _quote_around(text, match.start(), match.end())
            rules.append(
                {
                    "lhs": lhs_norm,
                    "rhs": canonical_rhs,
                    "lhs_family": lhs_parsed.family if lhs_parsed else None,
                    "rhs_family": rhs_parsed.family if rhs_parsed else None,
                    "rhs_catalog_valid": True,
                    "source_page": page_number,
                    "source_quote": quote[:400],
                    "confidence": 0.95,
                    "extraction_method": METHOD_DETERMINISTIC,
                    "source_quote_verified": True,
                    "non_context_occurrence_count": _count_non_context_occurrences(
                        document, lhs_norm, context_pages
                    ),
                    "status": STATUS_PROPOSED_INFERENCE,
                }
            )
    return rules


def _count_non_context_occurrences(
    document: Dict[str, Any], lhs: str, context_pages: Dict[int, str]
) -> int:
    """Informational only (never gates whether a rule is extracted/shown):
    how many times does the shorthand appear outside context pages?"""

    full_text = str(document.get("text") or "")
    if not full_text or not lhs:
        return 0
    pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(lhs) + r"(?![A-Za-z0-9])")
    total_hits = len(pattern.findall(full_text))
    context_hits = 0
    for page_number in context_pages:
        context_hits += len(pattern.findall(_page_text(document, page_number)))
    return max(0, total_hits - context_hits)


def _normalize_for_quote_match(text: str) -> str:
    normalized = text.replace("×", "x").replace("÷", "/")
    normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
    return " ".join(normalized.split()).lower()


def verify_quote(source_text: str, quote: str) -> bool:
    """Deterministic quote-grounding check: the exact evidence text must be
    findable in the real extracted page text, allowing only non-semantic
    normalization (whitespace collapse, case, common Unicode look-alikes).
    Never a second LLM call, never a semantic/paraphrase match."""

    if not quote or not source_text:
        return False
    return _normalize_for_quote_match(quote) in _normalize_for_quote_match(source_text)


#: ~60k chars (~15k tokens) comfortably covers most real note/spec page
#: sets seen so far (GCDC: ~9 context pages; a real customer set: ~10
#: pages, ~92k chars uncapped) while staying within a sensible local-model
#: context window (see OllamaLegendProvider's num_ctx). Documents whose
#: context pages exceed this ARE truncated in this checkpoint -- chunking
#: is explicitly out of scope per the request ("chunk ONLY when
#: necessary... do not turn this into an agentic loop yet"); this is a
#: disclosed limitation (see diagnostics.context_chars_available vs.
#: diagnostics.context_chars_sent in legend_profile_hook.py), not a silent
#: one, and it is applied FAIRLY per page (see module docstring below), not
#: as a first-come-first-served cut of the concatenated blob.
_DEFAULT_MAX_CONTEXT_CHARS = 60000


def build_context_text(
    document: Dict[str, Any],
    context_pages: Dict[int, str],
    *,
    max_chars: int = _DEFAULT_MAX_CONTEXT_CHARS,
) -> str:
    """Bounded, page-tagged text blob for the single LLM call -- only
    readable context pages (never VISION_REQUIRED, never drawing pages).

    Truncates PER PAGE with a fair, equal character budget, rather than
    concatenating every page in page-number order and hard-cutting the
    result at ``max_chars``. Confirmed real-document bug this fixes: on
    GCDC Building 4 - ST1.pdf, pages 1+3+4 alone total ~61k characters --
    a naive concatenate-then-cut approach silently dropped page 5 (the
    page with the actual "W8"=W8x10-style abbreviation table) ENTIRELY,
    because it happened to sort after three large pages. A fair per-page
    budget instead guarantees every selected context page contributes at
    least something to the model's input, regardless of page order or
    other pages' sizes.
    """

    pages = _readable_context_pages(context_pages)
    if not pages:
        return ""
    per_page_budget = max(max_chars // len(pages), 500)
    combined = "\n\n".join(
        f"[PAGE {page}]\n{_page_text(document, page)[:per_page_budget]}" for page in pages
    )
    return combined[:max_chars]


def _cache_path(cache_dir: Path, cache_key: str) -> Path:
    return cache_dir / f"{cache_key}.json"


def compute_cache_key(
    document_hash: str,
    *,
    llm_requested: bool,
    provider_name: str = "",
    model: str = "",
) -> str:
    """Cache key versioned on everything that changes the analysis: content,
    extractor/schema code version, and -- when the LLM ran -- which
    provider/model produced the prose fields. Changing the prompt (which
    bumps EXTRACTOR_VERSION/SCHEMA_VERSION), switching provider, or
    switching model all invalidate old cache entries automatically instead
    of silently replaying a stale (possibly empty) analysis."""

    parts = [document_hash, PROFILE_VERSION, EXTRACTOR_VERSION, SCHEMA_VERSION]
    if llm_requested:
        parts.extend([provider_name or "", model or ""])
    else:
        parts.append("no_llm")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def load_cached_profile(cache_dir: Path, cache_key: str) -> Optional[Dict[str, Any]]:
    path = _cache_path(cache_dir, cache_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("cache_key") != cache_key:
        return None
    return data


def save_profile(cache_dir: Path, cache_key: str, profile: Dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    profile["cache_key"] = cache_key
    path = _cache_path(cache_dir, cache_key)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def empty_profile(
    document: Dict[str, Any],
    *,
    status: str,
    llm_requested: bool,
    catalog_version: Optional[str] = None,
) -> Dict[str, Any]:
    """The all-fields-present shape. ``status`` must always be one of the
    ANALYSIS_* constants -- callers must never need to guess *why* a panel
    would be empty (see legend_profile_hook.py, which is the only place
    that decides which status applies)."""

    return {
        "profile_version": PROFILE_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_document_hash": compute_document_hash(document),
        "catalog_version": catalog_version,
        "built_at": time.time(),
        "status": status,
        "llm_requested": llm_requested,
        "llm_used": False,
        "llm_error": None,
        "llm_provider": None,
        "llm_model": None,
        "prompt_version": None,
        "llm_latency_ms": None,
        "context_pages": {},
        "executive_summary": "",
        "source_facts": [],
        "abbreviation_rules": [],
        "derived_insights": [],
        "warnings_and_conflicts": [],
        "estimator_attention_items": [],
        "diagnostics": {},
    }
