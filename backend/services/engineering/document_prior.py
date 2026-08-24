"""Document-level priors from legend / abbreviations / general-notes pages.

Legend text is deliberately excluded from engineering takeoff tokens, but
the vocabulary it defines (L = angle, PL = plate, typical sections used on
the job) is valuable soft evidence during prediction. This module detects
those front-matter pages, extracts structured priors, and applies small
candidate boosts — never creating quantities or overriding local callouts.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from services.database_loader import catalog_form, lookup_shape
from services.section_parser import parse_section
from services.token_extractor import normalize_engineering_token

PRIOR_VERSION = "document_prior_v2"

# --- Legend page scoring ---------------------------------------------------

_STRONG_LEGEND_SIGNALS = (
    (re.compile(r"\bLEGEND\b", re.I), 5.0),
    (re.compile(r"\bABBREVIATIONS?\b", re.I), 5.0),
    (re.compile(r"\bSYMBOLS?\b", re.I), 4.0),
    (re.compile(r"\bSTRUCTURAL\s+LEGEND\b", re.I), 6.0),
    (re.compile(r"\bSTEEL\s+BEAM\s+LEGEND\b", re.I), 6.0),
    (re.compile(r"\bSTEEL\s+COLUMN\s+LEGEND\b", re.I), 6.0),
    (re.compile(r"\bGENERAL\s+NOTES?\b", re.I), 5.0),
    (re.compile(r"\bSTRUCTURAL\s+NOTES?\b", re.I), 5.0),
    (re.compile(r"\bMATERIAL\s+NOTES?\b", re.I), 4.0),
    (re.compile(r"\bTYPICAL\s+DETAILS?\b", re.I), 4.0),
    (re.compile(r"\bDRAWING\s+SYMBOLS?\b", re.I), 4.0),
    (re.compile(r"\bSHEET\s+INDEX\b", re.I), 3.0),
    (re.compile(r"\bDESCRIPTION\s+OF\s+WORK\b", re.I), 3.0),
    (re.compile(r"\bUNLESS\s+NOTED\b", re.I), 2.0),
)

_PLAN_PAGE_SIGNALS = (
    re.compile(r"\bFRAMING\s+PLAN\b", re.I),
    re.compile(r"\bFLOOR\s+PLAN\b", re.I),
    re.compile(r"\bFOUNDATION\s+PLAN\b", re.I),
    re.compile(r"\bROOF\s+PLAN\b", re.I),
    re.compile(r"\bELEVATION\b", re.I),
    re.compile(r"\bSECTION\s+[A-Z0-9-]+\b", re.I),
    re.compile(r"\bDETAIL\s+\d", re.I),
)

_ABBREV_PAIR_RE = re.compile(
    r"^([A-Z]{1,5})\s*[=:\-–—]\s*([A-Z][A-Z0-9/ \-]{1,48})\s*$",
    re.I | re.M,
)
_UNLESS_NOTED_RE = re.compile(
    r"UNLESS\s+(?:NOTED|OTHERWISE)[^.;\n]{0,160}",
    re.I,
)
_SHAPE_LINE_RE = re.compile(
    r"\b(?:W|WT|S|M|HP|C|MC|HSS|PIPE|L|2L)\s*"
    r"\d+(?:\.\d+)?(?:\s*[X×]\s*\d+(?:\.\d+)?"
    r"(?:\s*[X×]\s*(?:\d+/\d+|\d+(?:\.\d+)?))?)?\b",
    re.I,
)
# Explicit mark -> section: BM3 W27X84, BM3 = W27X84, COL1 HSS6X6X3/8
_MARK_SECTION_RE = re.compile(
    r"\b(BM|BEAM|COL|COLUMN|BR|BRACE|GIRDER|JOIST|JST|G|J|B|C|P)"
    r"[-_ ]?(\d+[A-Z]?)\s*(?:[=:\-–—]\s*)?"
    r"((?:W|WT|HSS|L|2L|C|MC|PIPE)\s*[\dXx/.\-]+)\b",
    re.I,
)
_GRADE_RE = re.compile(r"\bA(?:36|572|992|500|913)\b", re.I)
_PLATE_VOCABULARY_RE = re.compile(r"\bPLATE\b", re.I)
_BENT_PLATE_VOCABULARY_RE = re.compile(r"\bBENT\s+PL(?:ATE)?\b", re.I)

_FAMILY_PREFIXES = (
    "2L",
    "HSS",
    "PIPE",
    "WT",
    "MC",
    "HP",
    "W",
    "S",
    "M",
    "C",
    "L",
)

_MAX_LEGEND_PAGES = 8
_MIN_LEGEND_PAGE_SCORE = 4.0
_EARLY_PAGE_BONUS = 1.0

_TYPICAL_SECTION_BOOST = 0.06
_ALLOWED_FAMILY_BOOST = 0.03
_MARK_MAP_BOOST = 0.12

# Canonical semantic meanings for explicit abbreviation pairs only.
_ABBREV_MEANING_MAP = {
    "ANGLE": "angle",
    "ANGLES": "angle",
    "PLATE": "plate",
    "PLATES": "plate",
    "BENT PLATE": "bent_plate",
    "BENTPLATE": "bent_plate",
    "BENT PL": "bent_plate",
    "WIDE FLANGE": "wide_flange",
    "WIDE FLANGE BEAM": "wide_flange",
    "WF": "wide_flange",
    "HSS": "hss",
    "TUBE": "hss",
    "PIPE": "pipe",
    "CHANNEL": "channel",
    "CH": "channel",
    "BEAM": "beam",
    "BM": "beam",
    "COLUMN": "column",
    "COL": "column",
    "BRACE": "brace",
    "BR": "brace",
    "GIRDER": "girder",
    "JOIST": "joist",
    "STIFFENER": "stiffener",
    "CONNECTION": "connection",
    "CONN": "connection",
    "THICKNESS": "thickness",
    "THK": "thickness",
    "TYPICAL": "typical",
    "TYP": "typical",
    "UNLESS NOTED": "unless_noted",
    "UNLESS NOTED OTHERWISE": "unless_noted",
}


def _page_text(document: Dict[str, Any], page_number: int) -> str:
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


def score_legend_page(text: str, *, page_number: int = 1) -> float:
    """Score how likely a page is legend/front-matter (higher = more likely)."""

    if not text.strip():
        return 0.0

    score = 0.0
    for pattern, weight in _STRONG_LEGEND_SIGNALS:
        if pattern.search(text):
            score += weight

    abbrev_count = len(_ABBREV_PAIR_RE.findall(text))
    if abbrev_count >= 4:
        score += 3.0
    elif abbrev_count >= 2:
        score += 1.5

    section_count = len(_extract_sections(text))
    if section_count >= 3:
        score += 1.5
    elif section_count >= 1:
        score += 0.5

    if len(re.findall(r"\bTYP(?:ICAL)?\.?\b", text, re.I)) >= 2:
        score += 1.0
    if re.search(r"\bSEE\s+(?:PLAN|DETAIL)\b", text, re.I):
        score += 0.5

    for pattern in _PLAN_PAGE_SIGNALS:
        if pattern.search(text):
            score -= 3.0

    # Isolated member words on plan sheets are weak legend evidence.
    if score < 3.0 and re.search(r"\b(?:BEAM|COLUMN|PLATE|ANGLE)\b", text, re.I):
        if not abbrev_count and not any(p.search(text) for p, _ in _STRONG_LEGEND_SIGNALS[:6]):
            score -= 1.0

    if page_number <= 3:
        score += _EARLY_PAGE_BONUS

    return max(0.0, score)


def detect_legend_pages(document: Dict[str, Any]) -> List[int]:
    """Return page numbers whose text looks like legend / abbreviations / notes."""

    page_count = int(document.get("page_count") or 0)
    if page_count <= 0:
        return []

    scored: List[Tuple[float, int]] = []
    for page_number in range(1, page_count + 1):
        text = _page_text(document, page_number)
        page_score = score_legend_page(text, page_number=page_number)
        if page_score >= _MIN_LEGEND_PAGE_SCORE:
            scored.append((page_score, page_number))

    scored.sort(key=lambda item: (-item[0], item[1]))
    legend_pages = [page for _, page in scored[:_MAX_LEGEND_PAGES]]

    # Fallback: first pages often hold abbreviations even without a header.
    if not legend_pages and page_count >= 1:
        for page_number in (1, 2):
            text = _page_text(document, page_number)
            if text.strip() and len(_ABBREV_PAIR_RE.findall(text)) >= 4:
                legend_pages.append(page_number)

    return sorted(set(legend_pages))


def _normalize_abbrev_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())


def _normalize_abbrev_meaning(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip().upper())
    if cleaned in _ABBREV_MEANING_MAP:
        return _ABBREV_MEANING_MAP[cleaned]
    for key, mapped in _ABBREV_MEANING_MAP.items():
        if cleaned == key or cleaned.startswith(key + " "):
            return mapped
    # Do not invent semantics for arbitrary uppercase phrases.
    if re.fullmatch(r"[A-Z0-9/ \-]{1,48}", cleaned):
        return cleaned.lower()
    return cleaned.lower()


def _extract_sections(text: str) -> Set[str]:
    sections: Set[str] = set()
    for match in _SHAPE_LINE_RE.finditer(text):
        normalized = normalize_engineering_token(match.group(0))
        if parse_section(normalized) and lookup_shape(normalized):
            sections.add(catalog_form(normalized) or normalized)
    return sections


def _family_from_section(section: str) -> str:
    parsed = parse_section(section)
    if parsed and parsed.family:
        return str(parsed.family).upper()
    compact = normalize_engineering_token(section)
    for prefix in _FAMILY_PREFIXES:
        if compact.startswith(prefix):
            return prefix
    return ""


def _abbreviation_plate_flags(
    abbreviations: Dict[str, str],
) -> Tuple[bool, bool, Set[str]]:
    """Return explicit plate/bent-plate abbreviation confirmation + plate terms."""

    plate_terms: Set[str] = set()
    confirms_plate = False
    confirms_bent = False

    for key, meaning in abbreviations.items():
        upper_key = _normalize_abbrev_key(key)
        if meaning == "plate" and upper_key in {"PL", "PLATE"}:
            confirms_plate = True
            plate_terms.add(upper_key)
        elif meaning == "bent_plate" and upper_key in {"BP", "BENTPL", "BENTPLATE"}:
            confirms_bent = True
            plate_terms.add(upper_key)
        elif meaning == "bent_plate" and upper_key == "BENT":
            confirms_bent = True
            plate_terms.add(upper_key)

    return confirms_plate, confirms_bent, plate_terms


def _local_plate_signals(normalized: str, compact: str) -> Dict[str, bool]:
    """Detect plate/bent-plate evidence in a local callout string only."""

    norm = str(normalized or "")
    comp = re.sub(r"\s+", "", str(compact or norm).upper())

    is_bent_local = bool(
        re.search(r"\bBENT\s*PL(?:ATE)?\b", norm, re.I)
        or comp.startswith("BENT")
        or "BENTPL" in comp
        or re.match(r"^BP[\d./\"X×\-']", comp)
        or re.match(r"^BP\b", norm, re.I)
    )
    is_pl_local = bool(
        re.search(r"\bPL\s+[\d./\"X×\-']", norm, re.I)
        or re.search(r"\bPLATE\s+[\d./\"X×\-']", norm, re.I)
        or re.match(r"^PL[\d./\"X×\-']", comp)
        or re.match(r"^PLATE[\d./\"X×\-']", comp)
    )
    # Thickness-first bent callouts: 1/4"BENTPL
    if re.match(r'^[\d./]+"?BENTPL', comp):
        is_bent_local = True

    # Dimension-only tokens must not inherit plate semantics from legend alone.
    dimension_only = bool(
        re.fullmatch(r'[\d./]+"?', norm.strip())
        or re.fullmatch(r"[\d./Xx×\-']+", comp)
    )
    if dimension_only:
        return {
            "is_pl_local": False,
            "is_bent_local": False,
            "is_dimension_only": True,
        }

    return {
        "is_pl_local": is_pl_local or is_bent_local,
        "is_bent_local": is_bent_local,
        "is_dimension_only": False,
    }


def _explicit_local_sections(token_text: str) -> Set[str]:
    """Catalog-valid sections explicitly present in a local callout."""

    return _extract_sections(token_text or "")


def build_document_prior(document: Dict[str, Any]) -> Dict[str, Any]:
    """Parse legend/front-matter pages into a reusable document prior."""

    legend_pages = detect_legend_pages(document)
    abbreviations: Dict[str, str] = {}
    typical_sections: Set[str] = set()
    allowed_families: Set[str] = set()
    mark_map: Dict[str, str] = {}
    material_grades: Set[str] = set()
    default_unless_noted: Dict[str, str] = {}

    texts: List[str] = []
    for page_number in legend_pages:
        texts.append(_page_text(document, page_number))
    if not texts and int(document.get("page_count") or 0) >= 1:
        for page_number in (1, 2):
            snippet = _page_text(document, page_number)
            if snippet.strip():
                texts.append(snippet)

    combined = "\n".join(texts)

    for match in _ABBREV_PAIR_RE.finditer(combined):
        key = _normalize_abbrev_key(match.group(1))
        meaning = _normalize_abbrev_meaning(match.group(2))
        if not key or len(key) > 5:
            continue
        abbreviations[key] = meaning
        if meaning == "angle":
            allowed_families.add("L")
            allowed_families.add("2L")
        elif meaning == "hss":
            allowed_families.add("HSS")
        elif meaning in {"wide_flange", "beam"}:
            allowed_families.add("W")
        elif meaning == "channel":
            allowed_families.add("C")
            allowed_families.add("MC")
        elif meaning == "pipe":
            allowed_families.add("PIPE")

    confirms_plate_abbreviation, confirms_bent_plate_abbreviation, plate_terms = (
        _abbreviation_plate_flags(abbreviations)
    )

    mentions_plate_vocabulary = bool(
        _PLATE_VOCABULARY_RE.search(combined) or _BENT_PLATE_VOCABULARY_RE.search(combined)
    )

    for section in _extract_sections(combined):
        typical_sections.add(section)
        family = _family_from_section(section)
        if family:
            allowed_families.add(family)

    for match in _MARK_SECTION_RE.finditer(combined):
        mark_prefix = match.group(1).upper()
        mark_suffix = match.group(2).upper()
        section = normalize_engineering_token(match.group(3))
        if not lookup_shape(section):
            continue
        canonical = catalog_form(section) or section
        # Canonical member marks: BM3, B1, C1, COL1, etc.
        if mark_prefix in {"BEAM", "BM"}:
            mark = f"BM{mark_suffix}"
        elif mark_prefix in {"COLUMN", "COL", "C"}:
            mark = f"COL{mark_suffix}" if mark_prefix.startswith("COL") else f"C{mark_suffix}"
        elif mark_prefix in {"BRACE", "BR"}:
            mark = f"BR{mark_suffix}"
        elif mark_prefix in {"GIRDER", "G"}:
            mark = f"G{mark_suffix}"
        elif mark_prefix in {"JOIST", "JST", "J"}:
            mark = f"J{mark_suffix}"
        elif mark_prefix == "B":
            mark = f"B{mark_suffix}"
        else:
            mark = f"{mark_prefix}{mark_suffix}".replace(" ", "")
        if len(mark) >= 2:
            mark_map[mark] = canonical

    for match in _GRADE_RE.finditer(combined):
        material_grades.add(match.group(0).upper())

    unless_block = _UNLESS_NOTED_RE.search(combined)
    if unless_block:
        for section in _extract_sections(unless_block.group(0)):
            family = _family_from_section(section)
            if family:
                default_unless_noted[family.lower()] = section

    # Backward-compatible alias: explicit abbreviation evidence only.
    confirms_plates = bool(
        confirms_plate_abbreviation or confirms_bent_plate_abbreviation
    )

    enabled = bool(
        legend_pages
        or abbreviations
        or typical_sections
        or mark_map
        or confirms_plates
        or mentions_plate_vocabulary
    )

    return {
        "version": PRIOR_VERSION,
        "enabled": enabled,
        "legend_pages": legend_pages,
        "abbreviations": abbreviations,
        "typical_sections": sorted(typical_sections),
        "allowed_families": sorted(allowed_families),
        "mark_map": mark_map,
        "material_grades": sorted(material_grades),
        "default_unless_noted": default_unless_noted,
        "plate_terms": sorted(plate_terms),
        "confirms_plate_abbreviation": confirms_plate_abbreviation,
        "confirms_bent_plate_abbreviation": confirms_bent_plate_abbreviation,
        "mentions_plate_vocabulary": mentions_plate_vocabulary,
        "confirms_plates": confirms_plates,
    }


def prior_context_blob(prior: Optional[Dict[str, Any]]) -> str:
    """Compact legend vocabulary for annotation context confirmation."""

    if not prior or not prior.get("enabled"):
        return ""
    parts: List[str] = []
    for key, meaning in sorted((prior.get("abbreviations") or {}).items()):
        parts.append(f"{key}={meaning}")
    if prior.get("confirms_plate_abbreviation") or prior.get("confirms_bent_plate_abbreviation"):
        parts.append("LEGEND_CONFIRMS_PLATES")
    if prior.get("confirms_plate_abbreviation"):
        parts.append("LEGEND_CONFIRMS_PLATE_ABBREV")
    if prior.get("confirms_bent_plate_abbreviation"):
        parts.append("LEGEND_CONFIRMS_BENT_PLATE_ABBREV")
    plate_terms = prior.get("plate_terms") or []
    if plate_terms:
        parts.append("PLATE_TERMS=" + ",".join(plate_terms))
    return " | ".join(parts)


def _candidate_shape(candidate: Any) -> str:
    if hasattr(candidate, "shape"):
        return str(getattr(candidate, "shape") or "")
    if isinstance(candidate, dict):
        return str(candidate.get("shape") or "")
    return ""


def _candidate_confidence(candidate: Any) -> float:
    if hasattr(candidate, "confidence"):
        return float(getattr(candidate, "confidence") or 0.0)
    if isinstance(candidate, dict):
        return float(candidate.get("confidence") or 0.0)
    return 0.0


def _set_candidate_confidence(candidate: Any, value: float) -> Any:
    clamped = max(0.0, min(0.99, value))
    if hasattr(candidate, "confidence"):
        candidate.confidence = clamped
        return candidate
    if isinstance(candidate, dict):
        candidate["confidence"] = clamped
        if isinstance(candidate.get("evidence"), dict):
            candidate["evidence"]["document_prior"] = round(clamped, 4)
        return candidate
    return candidate


def apply_prior_to_candidates(
    candidates: Iterable[Any],
    prior: Optional[Dict[str, Any]],
    *,
    token_text: str = "",
) -> List[Any]:
    """Apply small confidence boosts from the document prior (never penalties)."""

    items = list(candidates)
    if not prior or not prior.get("enabled") or not items:
        return items

    typical = {
        normalize_engineering_token(section)
        for section in (prior.get("typical_sections") or [])
    }
    allowed = {
        str(family).upper()
        for family in (prior.get("allowed_families") or [])
    }
    mark_map = {
        str(key).upper(): normalize_engineering_token(value)
        for key, value in (prior.get("mark_map") or {}).items()
    }
    token_compact = normalize_engineering_token(token_text)
    local_sections = _explicit_local_sections(token_text)
    explicit_local: Optional[str] = None
    if len(local_sections) == 1:
        explicit_local = normalize_engineering_token(next(iter(local_sections)))

    mark_hit: Optional[str] = None
    if not explicit_local:
        for mark, section in mark_map.items():
            if mark == token_compact or token_compact.startswith(mark):
                mark_hit = section
                break
        if mark_hit and local_sections and mark_hit not in local_sections:
            mark_hit = None

    adjusted: List[Any] = []
    for candidate in items:
        shape = normalize_engineering_token(_candidate_shape(candidate))
        if not shape:
            adjusted.append(candidate)
            continue
        confidence = _candidate_confidence(candidate)

        # A single catalog-valid section read locally is authoritative — priors
        # must not reorder or inflate competing candidates for this token.
        if explicit_local:
            if shape == explicit_local and shape in typical:
                confidence += _TYPICAL_SECTION_BOOST
            adjusted.append(_set_candidate_confidence(candidate, confidence))
            continue

        family = _family_from_section(shape)
        if shape in typical:
            confidence += _TYPICAL_SECTION_BOOST
        if allowed and family in allowed:
            confidence += _ALLOWED_FAMILY_BOOST
        if mark_hit and shape == mark_hit:
            confidence += _MARK_MAP_BOOST
        adjusted.append(_set_candidate_confidence(candidate, confidence))

    adjusted.sort(
        key=lambda item: (
            -_candidate_confidence(item),
            _candidate_shape(item),
        )
    )
    return adjusted


def attach_document_prior(document: Dict[str, Any]) -> Dict[str, Any]:
    """Detect legend pages and store ``document_prior`` on the document."""

    prior = build_document_prior(document)
    document["document_prior"] = prior
    return prior


def plate_context_from_prior(
    prior: Optional[Dict[str, Any]],
    *,
    normalized: str,
    compact: str,
) -> Dict[str, bool]:
    """Routing hints for plate / bent-plate interpretation from local callouts."""

    if not prior or not prior.get("enabled"):
        return {"supports_plate": False, "supports_bent_plate": False}

    signals = _local_plate_signals(normalized, compact)
    if signals.get("is_dimension_only"):
        return {"supports_plate": False, "supports_bent_plate": False}

    is_bent_local = bool(signals.get("is_bent_local"))
    is_pl_local = bool(signals.get("is_pl_local"))

    # Local callout determines semantic type; legend vocabulary never manufactures it.
    return {
        "supports_plate": is_pl_local,
        "supports_bent_plate": is_bent_local,
    }
