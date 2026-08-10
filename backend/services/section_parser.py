"""
Structural steel-section parser.

Decomposes designations such as ``W12X26`` or ``HSS6X6X1/2`` into family,
depth, weight, and optional thickness so retrieval/fusion can gate on
structural plausibility instead of character n-gram similarity alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from services.database_loader import is_catalog_label, lookup_shape
from services.exact_section_predictor import normalize_section_text
from services.wildcard_matcher import _DEPTH_RE, _FAMILY_PREFIXES, _WEIGHT_RE

# Near-free OCR confusions; digit↔digit swaps inside dimensions are expensive.
_OCR_NEAR_FREE = {
    ("0", "O"),
    ("O", "0"),
    ("1", "I"),
    ("I", "1"),
    ("1", "L"),
    ("L", "1"),
    ("5", "S"),
    ("S", "5"),
    ("8", "B"),
    ("B", "8"),
    ("X", "×"),
    ("×", "X"),
    ("X", "✕"),
    ("✕", "X"),
}

_HSS_THICKNESS_RE = re.compile(
    r"^(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?|\d+/\d+)$",
    re.IGNORECASE,
)
_ANGLE_THICKNESS_RE = re.compile(
    r"^(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?|\d+/\d+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedSection:
    """Structured view of a steel designation."""

    family: str
    depth: Optional[float]
    weight: Optional[float]
    thickness: Optional[str]
    normalized: str
    catalog_valid: bool
    raw_remainder: str = ""

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "depth": self.depth,
            "weight": self.weight,
            "thickness": self.thickness,
            "normalized": self.normalized,
            "catalog_valid": self.catalog_valid,
            "raw_remainder": self.raw_remainder,
        }


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "/" in text:
        try:
            numerator, denominator = text.split("/", 1)
            return float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_section(text: object) -> Optional[ParsedSection]:
    """Parse a steel designation into family / depth / weight / thickness."""

    normalized = normalize_section_text(text)
    if not normalized:
        return None

    family = ""
    remainder = normalized
    for prefix in _FAMILY_PREFIXES:
        if normalized.startswith(prefix):
            family = prefix
            remainder = normalized[len(prefix) :]
            break
    if not family:
        return None

    depth: Optional[float] = None
    weight: Optional[float] = None
    thickness: Optional[str] = None

    if family in {"HSS", "L", "2L"}:
        thick_match = (
            _HSS_THICKNESS_RE.match(remainder)
            if family == "HSS"
            else _ANGLE_THICKNESS_RE.match(remainder)
        )
        if thick_match:
            depth = _to_float(thick_match.group(1))
            weight = _to_float(thick_match.group(2))
            thickness = thick_match.group(3)
        else:
            depth_match = _DEPTH_RE.match(remainder)
            if depth_match:
                depth = _to_float(depth_match.group(1))
            weight_match = _WEIGHT_RE.search(remainder)
            if weight_match:
                weight = _to_float(weight_match.group(1))
    elif family == "PIPE":
        depth_match = _DEPTH_RE.match(remainder)
        if depth_match:
            depth = _to_float(depth_match.group(1))
    else:
        depth_match = _DEPTH_RE.match(remainder)
        if depth_match:
            depth = _to_float(depth_match.group(1))
        weight_match = _WEIGHT_RE.search(remainder)
        if weight_match:
            weight = _to_float(weight_match.group(1))

    catalog_valid = is_catalog_label(normalized) or lookup_shape(normalized) is not None
    return ParsedSection(
        family=family,
        depth=depth,
        weight=weight,
        thickness=thickness,
        normalized=normalized,
        catalog_valid=catalog_valid,
        raw_remainder=remainder,
    )


def ocr_edit_cost(a: object, b: object) -> float:
    """
    OCR-aware edit distance.

    Near-free substitutions for common OCR confusions; digit↔digit swaps
    inside the string cost more than letter confusions.
    """

    left = normalize_section_text(a)
    right = normalize_section_text(b)
    if left == right:
        return 0.0

    rows = len(left) + 1
    cols = len(right) + 1
    dp = [[0.0] * cols for _ in range(rows)]
    for i in range(1, rows):
        dp[i][0] = float(i)
    for j in range(1, cols):
        dp[0][j] = float(j)

    for i in range(1, rows):
        for j in range(1, cols):
            ca = left[i - 1]
            cb = right[j - 1]
            if ca == cb:
                sub_cost = 0.0
            elif (ca, cb) in _OCR_NEAR_FREE:
                sub_cost = 0.15
            elif ca.isdigit() and cb.isdigit():
                sub_cost = 1.5
            else:
                sub_cost = 1.0
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,
                dp[i][j - 1] + 1.0,
                dp[i - 1][j - 1] + sub_cost,
            )
    return float(dp[-1][-1])


def plausible_against_ocr(candidate: object, ocr_text: object) -> bool:
    """
    True when ``candidate`` is structurally consistent with OCR text.

    Requires the same family. When OCR depth is readable, candidate depth must
    match. Empty OCR / unparseable OCR is treated as unconstrained (True) so
    geometry-only rows are not blocked.
    """

    ocr = parse_section(ocr_text)
    cand = parse_section(candidate)
    if cand is None:
        return False
    if ocr is None or not str(ocr_text or "").strip():
        return True
    if ocr.family != cand.family:
        return False
    if ocr.depth is not None and cand.depth is not None and ocr.depth != cand.depth:
        return False
    return True
