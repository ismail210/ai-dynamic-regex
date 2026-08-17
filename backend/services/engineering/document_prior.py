"""Document-level priors from legend / abbreviations / general-notes pages.

Legend text is deliberately excluded from engineering takeoff tokens, but
the vocabulary it defines (L = angle, PL = plate, typical sections used on
the job) is valuable soft evidence during prediction. This module detects
those front-matter pages, extracts structured priors, and applies small
candidate boosts — never creating quantities or overriding local callouts.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set

from services.database_loader import catalog_form, lookup_shape
from services.section_parser import parse_section
from services.token_extractor import normalize_engineering_token

PRIOR_VERSION = "document_prior_v1"

_LEGEND_PAGE_RE = re.compile(
    r"\b(?:LEGEND|ABBREVIATIONS?|SYMBOLS?|GENERAL\s+NOTES?|"
    r"TYPICAL|UNLESS\s+NOTED|SHEET\s+INDEX|DESCRIPTION\s+OF\s+WORK|"
    r"STRUCTURAL\s+NOTES?|MATERIAL\s+NOTES?)\b",
    re.I,
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
_MARK_SECTION_RE = re.compile(
    r"\b(BM|BEAM|COL|COLUMN|BR|BRACE|GIRDER|JOIST|JST|MK|P)[-_ ]?(\d+[A-Z]?)"
    r"[^;\n]{0,48}?"
    r"((?:W|WT|HSS|L|2L|C|MC|PIPE|PL)\s*[\dXx/.\-]+)",
    re.I,
)
_GRADE_RE = re.compile(r"\bA(?:36|572|992|500|913)\b", re.I)
_PLATE_ABBREV_MEANINGS = {
    "PL",
    "PLATE",
    "BP",
    "BENTPLATE",
    "BENT PLATE",
    "BENT",
}
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
_MAX_LEGEND_PAGES = 6
_TYPICAL_SECTION_BOOST = 0.06
_ALLOWED_FAMILY_BOOST = 0.03
_DISALLOWED_FAMILY_PENALTY = 0.10
_MARK_MAP_BOOST = 0.12


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


def detect_legend_pages(document: Dict[str, Any]) -> List[int]:
    """Return page numbers whose text looks like legend / abbreviations / notes."""

    page_count = int(document.get("page_count") or 0)
    if page_count <= 0:
        return []
    legend_pages: List[int] = []
    for page_number in range(1, min(page_count, _MAX_LEGEND_PAGES) + 1):
        text = _page_text(document, page_number)
        if not text.strip():
            continue
        hits = len(_LEGEND_PAGE_RE.findall(text))
        if hits >= 1:
            legend_pages.append(page_number)
            continue
        # Early pages with many abbreviation pairs but no explicit LEGEND header.
        if page_number <= 3 and len(_ABBREV_PAIR_RE.findall(text)) >= 4:
            legend_pages.append(page_number)
    return legend_pages


def _normalize_abbrev_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())


def _normalize_abbrev_meaning(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip().upper())
    mapping = {
        "ANGLE": "angle",
        "ANGLES": "angle",
        "PLATE": "plate",
        "PLATES": "plate",
        "BENT PLATE": "bent_plate",
        "BENTPLATE": "bent_plate",
        "BENT": "bent_plate",
        "WIDE FLANGE": "wide_flange",
        "HSS": "hss",
        "TUBE": "hss",
        "PIPE": "pipe",
        "CHANNEL": "channel",
        "BEAM": "beam",
        "COLUMN": "column",
        "BRACE": "brace",
    }
    for key, mapped in mapping.items():
        if cleaned == key or cleaned.startswith(key + " "):
            return mapped
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


def build_document_prior(document: Dict[str, Any]) -> Dict[str, Any]:
    """Parse legend/front-matter pages into a reusable document prior."""

    legend_pages = detect_legend_pages(document)
    abbreviations: Dict[str, str] = {}
    typical_sections: Set[str] = set()
    allowed_families: Set[str] = set()
    mark_map: Dict[str, str] = {}
    material_grades: Set[str] = set()
    plate_terms: Set[str] = set()
    default_unless_noted: Dict[str, str] = {}

    texts: List[str] = []
    for page_number in legend_pages:
        texts.append(_page_text(document, page_number))
    if not texts and int(document.get("page_count") or 0) >= 1:
        # Fallback: first two pages often hold abbreviations even without a header.
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
        upper_key = key.upper()
        if upper_key in _PLATE_ABBREV_MEANINGS or meaning in {"plate", "bent_plate"}:
            plate_terms.add(upper_key)
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

    for section in _extract_sections(combined):
        typical_sections.add(section)
        family = _family_from_section(section)
        if family:
            allowed_families.add(family)

    for match in _MARK_SECTION_RE.finditer(combined):
        mark = f"{match.group(1).upper()}{match.group(2).upper()}".replace(" ", "")
        section = normalize_engineering_token(match.group(3))
        if lookup_shape(section):
            mark_map[mark] = catalog_form(section) or section

    for match in _GRADE_RE.finditer(combined):
        material_grades.add(match.group(0).upper())

    unless_block = _UNLESS_NOTED_RE.search(combined)
    if unless_block:
        for section in _extract_sections(unless_block.group(0)):
            family = _family_from_section(section)
            if family:
                default_unless_noted[family.lower()] = section

    confirms_plates = bool(
        plate_terms
        or abbreviations.get("PL") == "plate"
        or abbreviations.get("BP") == "bent_plate"
        or "PLATE" in combined.upper()
    )

    enabled = bool(
        legend_pages
        or abbreviations
        or typical_sections
        or mark_map
        or confirms_plates
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
        "confirms_plates": confirms_plates,
    }


def prior_context_blob(prior: Optional[Dict[str, Any]]) -> str:
    """Compact legend vocabulary for annotation context confirmation."""

    if not prior or not prior.get("enabled"):
        return ""
    parts: List[str] = []
    for key, meaning in sorted((prior.get("abbreviations") or {}).items()):
        parts.append(f"{key}={meaning}")
    if prior.get("confirms_plates"):
        parts.append("LEGEND_CONFIRMS_PLATES")
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
    """Apply small confidence boosts/penalties from the document prior."""

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
    mark_hit = mark_map.get(token_compact)

    adjusted: List[Any] = []
    for candidate in items:
        shape = normalize_engineering_token(_candidate_shape(candidate))
        if not shape:
            adjusted.append(candidate)
            continue
        confidence = _candidate_confidence(candidate)
        family = _family_from_section(shape)
        if shape in typical:
            confidence += _TYPICAL_SECTION_BOOST
        if allowed and family in allowed:
            confidence += _ALLOWED_FAMILY_BOOST
        if allowed and family and family not in allowed:
            confidence -= _DISALLOWED_FAMILY_PENALTY
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
    """Routing hints for plate / bent-plate interpretation only."""

    if not prior or not prior.get("enabled"):
        return {"supports_plate": False, "supports_bent_plate": False}
    upper = compact.upper()
    abbrev = {
        str(key).upper(): str(value)
        for key, value in (prior.get("abbreviations") or {}).items()
    }
    plate_terms = {str(term).upper() for term in (prior.get("plate_terms") or [])}
    supports_bent = bool(
        prior.get("confirms_plates")
        and (
            upper.startswith("BP")
            or upper.startswith("BENT")
            or abbrev.get("BP") == "bent_plate"
            or "BP" in plate_terms
        )
    )
    supports_plate = bool(
        prior.get("confirms_plates")
        and (
            upper.startswith("PL")
            or upper.startswith("PLATE")
            or abbrev.get("PL") == "plate"
            or "PL" in plate_terms
            or supports_bent
        )
    )
    return {
        "supports_plate": supports_plate,
        "supports_bent_plate": supports_bent,
    }
