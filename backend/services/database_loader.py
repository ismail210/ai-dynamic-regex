"""
AISC Shapes Database loader and lookup.

Loads the official AISC shapes database once and exposes a normalized lookup.
Paths come from the central config so the module works regardless of the
current working directory.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import List, Optional

import pandas as pd

from config import settings

# Load database once.
df = pd.read_excel(settings.database_file, sheet_name=settings.database_sheet)

# Normalize labels once (upper-case, no spaces) for fast exact matching.
labels = (
    df["AISC_Manual_Label"]
    .astype(str)
    .str.upper()
    .str.replace(" ", "", regex=False)
)

# Row-by-row `df.iloc[...]` costs ~1ms per access, which made a per-token scan
# of the whole database dominate every upload. The same columns are materialized
# once as plain lists so the scan below is pure Python indexing.
_NORMALIZED_LABELS: List[str] = labels.tolist()
_SHAPES: List[str] = df["AISC_Manual_Label"].astype(str).tolist()
_TYPES: List[str] = df["Type"].astype(str).tolist()
_LABEL_PREFIXES: List[str] = [
    "".join(char for char in label if char.isalpha())[:3]
    for label in _NORMALIZED_LABELS
]

# One matcher per database label, each holding the label as the second sequence.
# `SequenceMatcher` only builds its expensive b-chain when the second sequence
# changes, so reusing these keeps that work to once per process instead of once
# per token comparison.
_MATCHERS: List[SequenceMatcher] = [
    SequenceMatcher(None, "", label) for label in _NORMALIZED_LABELS
]


# Exact lookup is a dictionary hit rather than a boolean mask over the whole
# frame, which cost milliseconds on every token of every drawing. The first
# matching row wins, matching the previous `result.iloc[0]` behaviour.
_LABEL_INDEX: dict[str, dict] = {}
for _index, _label in enumerate(_NORMALIZED_LABELS):
    _LABEL_INDEX.setdefault(
        _label, {"shape": _SHAPES[_index], "type": _TYPES[_index]}
    )


def lookup_shape(token: str) -> Optional[dict]:
    """Search for a shape inside the AISC database by its manual label."""

    entry = _LABEL_INDEX.get(str(token).upper().replace(" ", ""))
    return dict(entry) if entry else None


def catalog_version() -> str:
    """Identify the loaded AISC catalog file/sheet for response provenance."""

    return f"{settings.database_file.name}#{settings.database_sheet}"


def catalog_entries() -> List[tuple[str, str]]:
    """Yield ``(normalized_label, type)`` for every row of the loaded catalog."""

    return list(zip(_NORMALIZED_LABELS, _TYPES))


def is_catalog_label(token: str) -> bool:
    """True when ``token`` (normalized) is an authoritative AISC manual label."""

    return str(token).upper().replace(" ", "") in _LABEL_INDEX


# Drawings write round HSS/pipe as ``HSS10X0.625`` while the catalog stores
# ``HSS10.000X0.625``. That is a spelling difference, not a different member.
_ROUND_SHORTHAND = re.compile(r"^(HSS|PIPE)(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")


def catalog_form(token: str) -> str:
    """Return the catalog spelling of ``token``, or ``""`` when it is not one.

    Only spelling variants of the same designation are resolved here; no
    similar-but-different shape is ever substituted.
    """

    normalized = str(token or "").upper().replace(" ", "")
    if not normalized:
        return ""
    if normalized in _LABEL_INDEX:
        return normalized
    match = _ROUND_SHORTHAND.match(normalized)
    if match:
        family, diameter, wall = match.groups()
        padded = f"{family}{float(diameter):.3f}X{float(wall):.3f}"
        if padded in _LABEL_INDEX:
            return padded
    return ""


def examples_for_type(shape_type: str, limit: Optional[int] = None) -> List[str]:
    """Return example manual labels belonging to a given shape ``Type``."""

    mask = df["Type"].astype(str).str.strip() == str(shape_type).strip()
    tokens = df.loc[mask, "AISC_Manual_Label"].astype(str).str.strip().tolist()
    return tokens[:limit] if limit else tokens


def search_similar_shapes(
    token: str,
    *,
    limit: int = 5,
    minimum_score: float = 0.45,
) -> List[dict]:
    """
    Return the closest AISC labels for OCR repair and multimodal fusion.

    This is additive to the authoritative exact ``lookup_shape`` API. Scores
    are normalized string similarities in the range [0, 1].
    """

    normalized = str(token or "").upper().replace(" ", "")
    if not normalized:
        return []

    return [
        dict(candidate)
        for candidate in _scan_similar_shapes(
            normalized, max(1, int(limit)), float(minimum_score)
        )
    ]


@lru_cache(maxsize=20_000)
def _scan_similar_shapes(
    normalized: str,
    limit: int,
    minimum_score: float,
) -> tuple:
    """Scan the database once per distinct token; drawings repeat labels heavily."""

    prefix = "".join(char for char in normalized if char.isalpha())[:3]
    candidates: List[dict] = []
    for index, matcher in enumerate(_MATCHERS):
        prefix_bonus = (
            0.08 if prefix and prefix == _LABEL_PREFIXES[index] else 0.0
        )
        matcher.set_seq1(normalized)
        # `ratio()` never exceeds `real_quick_ratio()` or `quick_ratio()`, so an
        # upper bound below the threshold rules the candidate out before paying
        # for the full O(n*m) comparison.
        if matcher.real_quick_ratio() + prefix_bonus < minimum_score:
            continue
        if matcher.quick_ratio() + prefix_bonus < minimum_score:
            continue
        score = min(1.0, matcher.ratio() + prefix_bonus)
        if score < minimum_score:
            continue
        candidates.append(
            {
                "shape": _SHAPES[index],
                "type": _TYPES[index],
                "similarity": round(score, 4),
            }
        )

    candidates.sort(key=lambda item: (-item["similarity"], item["shape"]))
    return tuple(candidates[:limit])
