"""
Single source of truth for AISC family-prefix code sets and longest-prefix
matching, so "the 13 modern families" is defined exactly once instead of as
independently-maintained literals scattered across
`wildcard_matcher.py`/`corruption.py`/other modules (which drift out of sync
by construction: nothing enforces two hardcoded copies stay identical).

Zero dependencies on purpose (no pandas, no database_loader) — pure text
logic that offline dataset-generation code (`label_reconstruction/corruption.py`)
can use without pulling in a catalog load.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

# The 13 families the current candidate generator/parser grammar already
# understands. This is the floor every family-prefix set below is built on
# top of; it is not the ceiling — `wildcard_matcher.refresh_family_prefixes()`
# extends it with whatever the currently loaded catalog actually contains.
MODERN_FAMILY_CODES = frozenset(
    {"W", "WT", "HSS", "L", "2L", "C", "MC", "PIPE", "MT", "ST", "HP", "M", "S"}
)


def longest_prefix_first(codes: Iterable[str]) -> List[str]:
    """Sort family codes longest-first so a longer, more specific code (e.g.
    ``WT``/``HSS``/``2L``) is never swallowed by a shorter one (``W``/``H``/``L``)
    when scanning from the start of a label."""

    return sorted({str(code) for code in codes if str(code)}, key=len, reverse=True)


def split_family(text: str, codes: Iterable[str]) -> Tuple[str, str]:
    """Split ``text`` into ``(family_prefix, remainder)`` using the longest
    matching code in ``codes``. Returns ``("", text)`` when none match.
    ``codes`` should already be longest-first (see `longest_prefix_first`);
    if not, this still returns the longest match since every candidate is
    checked (not just the first hit)."""

    best = ""
    for code in codes:
        if text.startswith(code) and len(code) > len(best):
            best = code
    if not best:
        return "", text
    return best, text[len(best):]
