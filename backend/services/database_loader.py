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
from typing import List, Optional, Tuple

import pandas as pd

from config import settings

# Mutable module state, populated by `_build_indices()` below. The only way
# any of this changes is a full, atomic rebuild via `_build_indices` — never
# a partial mutation, so no caller can ever observe a half-swapped catalog.
df: pd.DataFrame
_NORMALIZED_LABELS: List[str] = []
_SHAPES: List[str] = []
_TYPES: List[str] = []
_LABEL_PREFIXES: List[str] = []
_MATCHERS: List[SequenceMatcher] = []
_LABEL_INDEX: dict[str, dict] = {}
_ACTIVE_SOURCE: str = ""


def _build_indices(pairs: List[Tuple[str, str]], *, source: str) -> None:
    """(Re)build every module-level lookup structure from ``(label, type)``
    pairs."""

    global df, _NORMALIZED_LABELS, _SHAPES, _TYPES, _LABEL_PREFIXES
    global _MATCHERS, _LABEL_INDEX, _ACTIVE_SOURCE

    shapes = [str(label) for label, _type in pairs]
    types = [str(_type) for _label, _type in pairs]
    df = pd.DataFrame({"AISC_Manual_Label": shapes, "Type": types})

    normalized_labels = [label.upper().replace(" ", "") for label in shapes]

    _SHAPES = shapes
    _TYPES = types
    _NORMALIZED_LABELS = normalized_labels
    _LABEL_PREFIXES = [
        "".join(char for char in label if char.isalpha())[:3]
        for label in normalized_labels
    ]
    # One matcher per database label, each holding the label as the second
    # sequence. `SequenceMatcher` only builds its expensive b-chain when the
    # second sequence changes, so reusing these keeps that work to once per
    # process instead of once per token comparison.
    _MATCHERS = [SequenceMatcher(None, "", label) for label in normalized_labels]

    # Exact lookup is a dictionary hit rather than a boolean mask over the
    # whole frame, which cost milliseconds on every token of every drawing.
    # The first matching row wins, matching the previous `result.iloc[0]`
    # behaviour.
    label_index: dict[str, dict] = {}
    for index, label in enumerate(normalized_labels):
        label_index.setdefault(label, {"shape": shapes[index], "type": types[index]})
    _LABEL_INDEX = label_index
    _ACTIVE_SOURCE = source

    _scan_similar_shapes.cache_clear()


def _default_pairs() -> Tuple[List[Tuple[str, str]], str]:
    source_df = pd.read_excel(settings.database_file, sheet_name=settings.database_sheet)
    pairs = list(
        zip(
            source_df["AISC_Manual_Label"].astype(str).tolist(),
            source_df["Type"].astype(str).tolist(),
        )
    )
    return pairs, f"{settings.database_file.name}#{settings.database_sheet}"


def reload_from_pairs(pairs: List[Tuple[str, str]], *, source: str) -> None:
    """Swap the active catalog to arbitrary ``(label, type)`` pairs.

    For offline training/evaluation use only (e.g. pointing candidate
    generation at the larger AISC v16 all-editions catalog while it is being
    prepared). The live prediction path never calls this — production always
    loads ``settings.database_file``/``settings.database_sheet`` at import,
    via `reset_to_default()`/the module-level load below.
    """

    if not pairs:
        raise ValueError("reload_from_pairs requires at least one (label, type) pair")
    _build_indices(pairs, source=source)


def reset_to_default() -> None:
    """Restore the production catalog (settings.database_file/sheet)."""

    pairs, source = _default_pairs()
    _build_indices(pairs, source=source)


def lookup_shape(token: str) -> Optional[dict]:
    """Search for a shape inside the AISC database by its manual label."""

    entry = _LABEL_INDEX.get(str(token).upper().replace(" ", ""))
    return dict(entry) if entry else None


def catalog_version() -> str:
    """Identify the currently active catalog source for response provenance."""

    return _ACTIVE_SOURCE


def reload_from_aisc_v16_catalog(path=None, *, scope: Optional[str] = None) -> "object":
    """Swap the active catalog to the derived AISC v16 all-editions catalog.

    Offline/training use only (see `reload_from_pairs`). ``scope`` optionally
    restricts to ``"modern"`` or ``"historical"`` entries
    (`services.aisc_v16_catalog.CatalogEntry.catalog_scope`); ``None`` loads
    every entry. Returns the loaded `AiscV16Catalog` so callers can inspect
    provenance without re-reading the CSV.
    """

    from services.aisc_v16_catalog import load_catalog

    catalog = load_catalog(path)
    entries = catalog.entries() if scope is None else catalog.entries_by_scope(scope)
    if not entries:
        raise ValueError(f"no catalog entries found for scope={scope!r}")
    pairs = [(entry.designation, entry.family) for entry in entries]
    label = "aisc_v16_label_catalog.csv" if scope is None else f"aisc_v16_label_catalog.csv[{scope}]"
    reload_from_pairs(pairs, source=label)
    return catalog


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


# Load the production database once, at import time. This is the only
# catalog the live prediction path ever uses.
reset_to_default()
