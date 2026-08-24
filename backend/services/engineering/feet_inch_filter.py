"""Filter non-steel layout dimensions from the engineering token pipeline.

Architectural spacing (4", 6", 8"), feet-inch footings, and sub-gauge tick
fractions (3/64") are not steel takeoff annotations.
"""

from __future__ import annotations

import re

# One feet-inch segment: 7'-6", 1'-6", 12', 4'-0", etc.
FEET_INCH_SEGMENT_RE = re.compile(
    r"\d{1,4}\s*['′]\s*-?\s*\d{0,2}(?:\s+\d+/\d+)?\s*[\"″]?",
    re.IGNORECASE,
)

# Compound L x W x D footing / pad sizes: 7'-6"x7'-6"x1'-6"
FEET_INCH_COMPOUND_RE = re.compile(
    r"(?:"
    r"\d{1,4}\s*['′]\s*-?\s*\d{0,2}(?:\s+\d+/\d+)?\s*[\"″]?"
    r"\s*[x×]\s*"
    r")+"
    r"\d{1,4}\s*['′]\s*-?\s*\d{0,2}(?:\s+\d+/\d+)?\s*[\"″]?",
    re.IGNORECASE,
)

_EXISTING_FOOTING_PREFIX_RE = re.compile(r"\(\s*[EF]\s*\)", re.IGNORECASE)

_BARE_INCH_VALUE_RE = re.compile(
    r'^(?P<value>\d+(?:\.\d+)?|\d+/\d+)"?$', re.IGNORECASE
)

# Common plate / connection thickness denominators (keep these).
_STEEL_FRACTION_DENOMINATORS = frozenset({2, 4, 8, 16, 32})


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").upper().replace("×", "X"))


def feet_inch_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans for feet-inch segments inside ``text``."""

    value = str(text or "")
    return [(match.start(), match.end()) for match in FEET_INCH_SEGMENT_RE.finditer(value)]


def contains_feet_inch_notation(text: str) -> bool:
    """True when ``text`` includes at least one feet-inch segment."""

    return bool(FEET_INCH_SEGMENT_RE.search(str(text or "")))


def is_feet_inch_layout_dimension(text: str) -> bool:
    """True for footing/pad style feet-inch sizes (compound or marked existing)."""

    value = str(text or "")
    if not value:
        return False
    if FEET_INCH_COMPOUND_RE.search(value):
        return True
    if _EXISTING_FOOTING_PREFIX_RE.search(value) and contains_feet_inch_notation(value):
        return True
    return False


def match_overlaps_feet_inch(text: str, start: int, end: int) -> bool:
    """True when ``text[start:end]`` lies inside a feet-inch segment."""

    for seg_start, seg_end in feet_inch_spans(text):
        if start >= seg_start and end <= seg_end:
            return True
        if start < seg_end and end > seg_start:
            return True
    return False


def is_non_steel_layout_dimension(text: str) -> bool:
    """True for bare layout inch callouts such as 4", 6", 8", or 3/64"."""

    normalized = _compact(text)
    if not normalized:
        return False
    if is_feet_inch_layout_dimension(normalized):
        return True
    # Compound steel sizes (6x4x5/16) stay in takeoff.
    if "X" in normalized and not contains_feet_inch_notation(normalized):
        return False

    match = _BARE_INCH_VALUE_RE.fullmatch(normalized)
    if not match:
        return False

    value = match.group("value")
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        den = int(denominator)
        if den in _STEEL_FRACTION_DENOMINATORS:
            return False
        # 3/64", 1/128" etc. — dimension-line ticks, not plate gauges.
        return den > 32 or (den == 32 and int(numerator) <= 1)

    try:
        inches = float(value)
    except ValueError:
        return False
    # Whole-inch spacing on plans (4", 6", 8", 12") — not plate thickness.
    return inches >= 3.0


def is_non_steel_layout_token(token: dict) -> bool:
    """True when a token record should be dropped from steel takeoff."""

    parts = (
        token.get("raw_text"),
        token.get("text"),
        token.get("normalized_text"),
        (token.get("context") or {}).get("line_text"),
        (token.get("context") or {}).get("layout_dimension_text"),
    )
    combined = " | ".join(str(part or "") for part in parts if part)
    if is_feet_inch_layout_dimension(combined):
        return True
    if contains_feet_inch_notation(combined):
        normalized = _compact(token.get("normalized_text") or token.get("text") or "")
        if re.fullmatch(r'\d{1,2}"?', normalized) or re.fullmatch(
            r"\d{1,2}", normalized
        ):
            return True

    normalized = _compact(token.get("normalized_text") or token.get("text") or "")
    return is_non_steel_layout_dimension(normalized)


# Backward-compatible alias used by earlier filter wiring.
is_non_steel_feet_inch_token = is_non_steel_layout_token
