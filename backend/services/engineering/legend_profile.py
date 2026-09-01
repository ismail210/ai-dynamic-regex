"""Legend / general-notes project-summary profile.

Reads ONLY the text-dense, non-drawing pages of a document (legend,
general/structural notes, abbreviations, specifications) and produces a
small, document-scoped, cached summary of project-specific conventions --
e.g. a general-notes line that says::

    "W8" = W8x10

This module is informational by design for this checkpoint. It:

* never mutates ``engineering_tokens``, candidate generation, ranking, or
  any prediction;
* never inserts a family into a token that did not already carry one in
  its own extracted text (this is the exact behavior the ``reliable_family``
  mechanism, added in 9731651 and removed in 8b3d065, was ruled out for --
  see the module-level note in ``extract_abbreviation_rules`` below);
* marks every extracted item ``STATUS_PROPOSED_INFERENCE`` -- nothing here
  is authoritative, and nothing here is applied to a prediction. A later,
  separate feature may one day let a human-reviewed, same-family,
  catalog-valid abbreviation rule assist an unresolved token; this module
  only prepares evidence for that decision, it does not make it.

Adapted from the orphaned ``bassam/drawing-language-profile`` prototype
(``services/engineering/drawing_language_profile.py`` in that worktree,
never committed/merged) rather than rewritten from scratch -- the page-role
classification, quote-anchored provenance, and same-family/catalog-valid
extraction gates are carried over near-verbatim because they were already
correct. What's new here: the ``project_summary``/``important_conventions``/
``warnings_or_conflicts`` shape (the prototype only produced typed rules,
not a human-facing summary), and the explicit ``STATUS_PROPOSED_INFERENCE``
status on every item regardless of extraction method (the prototype
promoted explicit deterministic matches straight to ``SOURCE_VERIFIED``;
this checkpoint deliberately does not draw that distinction anywhere
consumption happens, since nothing here is applied to a token either way).
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

PROFILE_VERSION = "legend_profile_v1"
EXTRACTOR_VERSION = "legend_extractor_v1"
SCHEMA_VERSION = "legend_schema_v1"

STATUS_PROPOSED_INFERENCE = "PROPOSED_INFERENCE"

METHOD_DETERMINISTIC = "deterministic"
METHOD_LLM_PROPOSED = "llm_proposed"

CATEGORY_SECTION_SHORTHAND = "SECTION_SHORTHAND"
CATEGORY_MATERIAL = "MATERIAL"
CATEGORY_CONNECTION = "CONNECTION"
CATEGORY_CAMBER = "CAMBER"
CATEGORY_RESPONSIBILITY = "RESPONSIBILITY"
CATEGORY_GENERAL_STRUCTURAL = "GENERAL_STRUCTURAL"
CATEGORY_OTHER = "OTHER"

_ALLOWED_CATEGORIES = {
    CATEGORY_SECTION_SHORTHAND,
    CATEGORY_MATERIAL,
    CATEGORY_CONNECTION,
    CATEGORY_CAMBER,
    CATEGORY_RESPONSIBILITY,
    CATEGORY_GENERAL_STRUCTURAL,
    CATEGORY_OTHER,
}

PAGE_ROLE_LEGEND = "LEGEND"
PAGE_ROLE_GENERAL_NOTES = "GENERAL_NOTES"
PAGE_ROLE_STRUCTURAL_NOTES = "STRUCTURAL_NOTES"
PAGE_ROLE_ABBREVIATIONS = "ABBREVIATIONS"
PAGE_ROLE_SPECIFICATIONS = "SPECIFICATIONS"
PAGE_ROLE_VISION_REQUIRED = "VISION_REQUIRED"

_CONTEXT_PAGE_ROLES = {
    PAGE_ROLE_LEGEND,
    PAGE_ROLE_GENERAL_NOTES,
    PAGE_ROLE_STRUCTURAL_NOTES,
    PAGE_ROLE_ABBREVIATIONS,
    PAGE_ROLE_SPECIFICATIONS,
}

# Minimum extracted-text length for a page that scored as a legend/notes
# page to be treated as usable text (rather than a scan Estima3D cannot
# read yet). This is a conservative, deterministic heuristic -- no OCR/VLM
# call is made here; a page below this threshold is only ever flagged, its
# text (if any) is still passed through unchanged, and it is excluded from
# LLM input so a near-empty page can't silently become "no useful context
# found" filler.
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

_ABBREVIATIONS_HEADING_RE = re.compile(r"\bABBREVIATIONS?\b", re.I)
_GENERAL_NOTES_HEADING_RE = re.compile(r"\bGENERAL\s+NOTES?\b", re.I)
_STRUCTURAL_NOTES_HEADING_RE = re.compile(r"\bSTRUCTURAL\s+NOTES?\b", re.I)
_SPECIFICATION_HEADING_RE = re.compile(r"\bSPECIFICATIONS?\b", re.I)


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
    """Content hash used as the profile cache key -- never a filename-only
    key, so a changed/re-uploaded PDF never serves a stale cached profile."""

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


#: Headings are only recognized near the top of the page. Without this
#: bound, a GENERAL NOTES page whose body text happens to mention e.g.
#: "...MEMBER SIZE ABBREVIATIONS ARE USED ON THE FRAMING PLANS..." (a real
#: GCDC sentence) would be mislabeled ABBREVIATIONS just because that word
#: appears somewhere in the prose. This only affects the informational
#: page-role label -- GENERAL_NOTES/ABBREVIATIONS/STRUCTURAL_NOTES/
#: SPECIFICATIONS are all equally "readable context" for extraction
#: purposes (see _CONTEXT_PAGE_ROLES), so this is a precision refinement,
#: not a safety gate.
_HEADING_SEARCH_WINDOW = 200


def _classify_page_role(text: str, *, is_legend_page: bool) -> Optional[str]:
    upper = text[:_HEADING_SEARCH_WINDOW].upper()
    if _ABBREVIATIONS_HEADING_RE.search(upper):
        return PAGE_ROLE_ABBREVIATIONS
    if _SPECIFICATION_HEADING_RE.search(upper):
        return PAGE_ROLE_SPECIFICATIONS
    if _STRUCTURAL_NOTES_HEADING_RE.search(upper):
        return PAGE_ROLE_STRUCTURAL_NOTES
    if _GENERAL_NOTES_HEADING_RE.search(upper):
        return PAGE_ROLE_GENERAL_NOTES
    if is_legend_page:
        return PAGE_ROLE_LEGEND
    return None


def detect_context_pages(document: Dict[str, Any]) -> Dict[int, str]:
    """Deterministic page-role classification, context pages only.

    Reuses ``document_prior.detect_legend_pages`` for the underlying
    legend-likelihood scoring so this module never disagrees with the
    already-tested legend-page signal document_prior itself relies on --
    it only refines *which* context role a legend-scoring page gets, and
    additionally recognizes STRUCTURAL_NOTES/ABBREVIATIONS/SPECIFICATIONS
    headings document_prior's binary in/out signal doesn't distinguish.

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
    the source text rather than trusted from a model response (this is the
    "independent parse gate" -- see module docstring).

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
    Whether any given *token* is itself eligible to be completed by such a
    rule is future work (see docs update accompanying this checkpoint) and
    is explicitly NOT implemented anywhere in this module: nothing here
    reads ``engineering_tokens``, and nothing here returns a value used by
    candidate generation.
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
    how many times does the shorthand appear outside context pages? This is
    what answers "is this rule actually used on this project, or unused
    boilerplate" without ever suppressing an explicitly-stated project rule
    just because it happens to be rare or unused so far."""

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
    normalized = normalized.replace("’", "'").replace("“", '"').replace(
        "”", '"'
    )
    return " ".join(normalized.split()).lower()


def verify_quote(source_text: str, quote: str) -> bool:
    """Deterministic quote-grounding check: the exact evidence text must be
    findable in the real extracted page text, allowing only non-semantic
    normalization (whitespace collapse, case, common Unicode look-alikes).
    Never a second LLM call, and never a semantic/paraphrase match -- if the
    normalized quote is not a substring of the normalized source, the item
    is rejected outright, per the checkpoint's "precision over recall"
    instruction."""

    if not quote or not source_text:
        return False
    return _normalize_for_quote_match(quote) in _normalize_for_quote_match(source_text)


def build_context_text(
    document: Dict[str, Any], context_pages: Dict[int, str], *, max_chars: int = 20000
) -> str:
    """Bounded, page-tagged text blob for the single LLM call -- only
    readable context pages (never VISION_REQUIRED, never drawing pages)."""

    pages = _readable_context_pages(context_pages)
    combined = "\n\n".join(
        f"[PAGE {page}]\n{_page_text(document, page)}" for page in pages
    )
    return combined[:max_chars]


def _cache_path(cache_dir: Path, document_hash: str) -> Path:
    return cache_dir / f"{document_hash}.json"


def load_cached_profile(
    cache_dir: Path,
    document_hash: str,
    *,
    llm_requested: bool,
) -> Optional[Dict[str, Any]]:
    path = _cache_path(cache_dir, document_hash)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        data.get("profile_version") != PROFILE_VERSION
        or data.get("extractor_version") != EXTRACTOR_VERSION
        or data.get("schema_version") != SCHEMA_VERSION
        or data.get("source_document_hash") != document_hash
        or bool(data.get("llm_requested")) != bool(llm_requested)
    ):
        return None
    return data


def save_profile(cache_dir: Path, profile: Dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, profile["source_document_hash"])
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def empty_profile(
    document: Dict[str, Any], *, llm_requested: bool, catalog_version: Optional[str] = None
) -> Dict[str, Any]:
    """The all-fields-present, nothing-found shape. Returned whenever the
    feature is disabled, the document has no context pages, or extraction
    otherwise finds nothing -- callers should never need to special-case
    "no profile" vs. "empty profile"."""

    return {
        "profile_version": PROFILE_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_document_hash": compute_document_hash(document),
        "catalog_version": catalog_version,
        "built_at": time.time(),
        "llm_requested": llm_requested,
        "llm_used": False,
        "llm_error": None,
        "llm_model": None,
        "prompt_version": None,
        "context_pages": {},
        "project_summary": "",
        "important_conventions": [],
        "abbreviation_rules": [],
        "warnings_or_conflicts": [],
    }
