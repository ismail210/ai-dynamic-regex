"""
Catalog-constrained completion for HSS designations missing wall thickness.

``HSS10X10`` does not uniquely identify one AISC section: the production
catalog carries several valid thicknesses for essentially every rectangular
or square HSS outside-dimension pair (see the forensic audit this module
implements). When both outside dimensions are read cleanly but thickness is
absent, the two dimensions are KNOWN information and must constrain the
candidate pool to real catalog members sharing that pair — never a
fuzzy/global text-similarity search that could drift onto a different pair
(e.g. HSS8X8 -> HSS8X6X3/8).

This module answers two narrow questions against the same catalog authority
the live pipeline already uses (``services.database_loader``, backed by
``aisc-shapes-database-v160-2.xlsx`` — see ``config.Settings.database_file``):

1. Does this text look like "HSS A X B" with no thickness segment, and no
   corruption/wildcard marker in either dimension? (missing, not corrupted —
   those are different problems; see ``services.wildcard_matcher`` for the
   corrupted-character case.)
2. If so, which real catalog designations share that A x B pair?

Nothing here fabricates a designation: every returned label is a literal
catalog entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple

from services.database_loader import df
from services.exact_section_predictor import normalize_section_text
from services.wildcard_matcher import has_wildcards

# Exactly one clean numeric dimension: digits, an optional decimal point, or
# a simple slash fraction / mixed number (e.g. "10", "1.5", "1-1/2"). No
# wildcard/mask characters and no stray letters -- those are a corrupted or
# unsupported read, a different problem than "missing".
_CLEAN_DIMENSION_RE = re.compile(r"^\d+(?:-\d+/\d+)?(?:\.\d+)?$|^\d+/\d+$")

_HSS_THREE_PART_RE = re.compile(
    r"^HSS(\d+(?:-\d+/\d+)?(?:\.\d+)?)X(\d+(?:-\d+/\d+)?(?:\.\d+)?)X([\d./]+)$"
)


def _to_float(value: str) -> Optional[float]:
    text = value.strip()
    if not text:
        return None
    try:
        if "-" in text and "/" in text:
            whole, frac = text.split("-", 1)
            num, den = frac.split("/", 1)
            return float(whole) + float(num) / float(den)
        if "/" in text:
            num, den = text.split("/", 1)
            return float(num) / float(den)
        return float(text)
    except (ValueError, ZeroDivisionError):
        return None


@dataclass(frozen=True)
class HssDimensionCandidate:
    """One catalog-valid completion for a missing-thickness HSS read."""

    designation: str
    thickness: str
    thickness_value: Optional[float]

    def to_dict(self) -> dict:
        return {
            "designation": self.designation,
            "thickness": self.thickness,
        }


def detect_missing_thickness_hss(text: object) -> Optional[Tuple[str, str]]:
    """
    Return ``(dim1_raw, dim2_raw)`` when ``text`` reads as a clean
    "HSS A X B" with both outside dimensions present and no thickness
    segment — the two dimensions as written, in the order OCR gave them.

    Returns ``None`` for: complete designations (thickness already present),
    round HSS single-dimension reads, corrupted/wildcard-masked dimensions
    (a different problem — see ``services.wildcard_matcher``), or anything
    that isn't a clean two-part HSS read at all.
    """

    normalized = normalize_section_text(text)
    if not normalized.startswith("HSS"):
        return None
    remainder = normalized[3:]
    if not remainder:
        return None
    if has_wildcards(remainder) or "?" in remainder:
        return None
    parts = remainder.split("X")
    if len(parts) != 2:
        return None
    dim1_raw, dim2_raw = parts
    if not dim1_raw or not dim2_raw:
        return None
    if not _CLEAN_DIMENSION_RE.match(dim1_raw) or not _CLEAN_DIMENSION_RE.match(
        dim2_raw
    ):
        return None
    if _to_float(dim1_raw) is None or _to_float(dim2_raw) is None:
        return None
    return dim1_raw, dim2_raw


@lru_cache(maxsize=1)
def _rect_hss_catalog() -> Tuple[Tuple[float, float, str, str, Optional[float]], ...]:
    """
    Every rectangular/square HSS row in the live production catalog
    (``services.database_loader``, backed by ``config.Settings.database_file``
    — the same authority ``services.database_loader.lookup_shape`` uses),
    parsed once into ``(dim1, dim2, thickness_text, canonical_label,
    thickness_value)``. ``dim1`` is always the larger of the pair: AISC's own
    manual labels store rectangular HSS with the larger outside dimension
    first (verified against the current catalog — zero counter-examples),
    so lookups canonicalize OCR's dimension order to match.
    """

    rows: List[Tuple[float, float, str, str, Optional[float]]] = []
    labels = df["AISC_Manual_Label"].astype(str).str.upper().str.replace(" ", "")
    for label in labels:
        match = _HSS_THREE_PART_RE.match(label)
        if not match:
            continue
        a, b, thickness = match.groups()
        a_val, b_val = _to_float(a), _to_float(b)
        if a_val is None or b_val is None:
            continue
        dim1, dim2 = (a_val, b_val) if a_val >= b_val else (b_val, a_val)
        rows.append((dim1, dim2, thickness, label, _to_float(thickness)))
    return tuple(rows)


def hss_completion_candidates(dim1_raw: str, dim2_raw: str) -> List[HssDimensionCandidate]:
    """
    Every catalog-valid HSS designation sharing the two known outside
    dimensions, regardless of which order OCR read them in. Returns an empty
    list when the pair has no catalog match at all (e.g. a dimension typo,
    or a pair the manufacturer doesn't produce) — callers should treat that
    as "not a resolvable missing-thickness case" rather than forcing review
    with zero real options.

    Sorted by thickness ascending; every entry is the catalog's own literal
    label string, never a constructed one.
    """

    a_val, b_val = _to_float(dim1_raw), _to_float(dim2_raw)
    if a_val is None or b_val is None:
        return []
    dim1, dim2 = (a_val, b_val) if a_val >= b_val else (b_val, a_val)

    matches = [
        HssDimensionCandidate(
            designation=label,
            thickness=thickness,
            thickness_value=thickness_value,
        )
        for row_dim1, row_dim2, thickness, label, thickness_value in _rect_hss_catalog()
        if row_dim1 == dim1 and row_dim2 == dim2
    ]
    matches.sort(
        key=lambda item: (
            item.thickness_value if item.thickness_value is not None else 1e9,
            item.designation,
        )
    )
    return matches


def reload_hss_completion_cache() -> None:
    """Drop the cached catalog parse (e.g. after a catalog reload in tests)."""

    _rect_hss_catalog.cache_clear()
