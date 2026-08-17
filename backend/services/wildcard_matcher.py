"""
Deterministic, family-aware wildcard/mask candidate matching.

Handles incomplete steel-section labels such as ``W44X3**`` where ``*``/``?``
mark visibly-missing characters (e.g. a smudged or unreadable digit on the
drawing). Each wildcard character stands for exactly one unknown character —
this is a positional mask match, not a brute-force "generate every possible
string" search and not fuzzy string similarity.

The known family is parsed and held fixed (a ``W`` label can never resolve to
an ``HSS`` candidate), the remaining known characters must match literally,
and every returned candidate is checked against the loaded AISC catalog
(``services.database_loader``) so only real, existing AISC designations are
ever produced. This intentionally runs *before* fuzzy text-similarity
retrieval in ``services.exact_section_predictor`` — fuzzy retrieval is the
fallback for tokens that have no wildcard characters, or corruption a
positional mask cannot express (e.g. a wrong digit rather than a missing one).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from services.database_loader import catalog_entries
from services.family_codes import MODERN_FAMILY_CODES, longest_prefix_first, split_family

WILDCARD_CHARS = "*?"


def _compute_family_prefixes() -> List[str]:
    """Family codes recognized for splitting/matching, longest-first.

    Derived from whatever catalog is currently loaded
    (`services.database_loader.catalog_entries()`) rather than a hardcoded
    literal list, unioned with the 13-family floor so recognition never
    regresses below today's behavior even against an unusual catalog swap.
    """

    families = {shape_type for _label, shape_type in catalog_entries()}
    return longest_prefix_first(families | set(MODERN_FAMILY_CODES))


_FAMILY_PREFIXES: List[str] = _compute_family_prefixes()


def refresh_family_prefixes() -> List[str]:
    """Recompute `_FAMILY_PREFIXES` from the currently loaded catalog.

    Call this after `services.database_loader.reload_from_pairs`/
    `reload_from_aisc_v16_catalog` in offline training/eval contexts. The
    live prediction path never reloads the catalog mid-process (it is
    loaded once at import), so it never needs to call this.
    """

    global _FAMILY_PREFIXES
    _FAMILY_PREFIXES = _compute_family_prefixes()
    return _FAMILY_PREFIXES


# Depth/weight may be decimal (e.g. round HSS/PIPE store diameter and wall
# thickness as "10.750"/"0.188") — matching digits only silently truncated
# these to "10"/"0", which was wrong for every decimal-dimension label.
_DEPTH_RE = re.compile(r"^(\d+(?:\.\d+)?)")
_WEIGHT_RE = re.compile(r"X(\d+(?:\.\d+)?)")
_NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}


@dataclass
class WildcardCandidate:
    """One catalog label that satisfies a wildcard/mask query, with reasons."""

    label: str
    catalog_type: Optional[str]
    catalog_valid: bool
    mask_match: bool
    match_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "catalog_type": self.catalog_type,
            "catalog_valid": self.catalog_valid,
            "mask_match": self.mask_match,
            "text_similarity": 0.0,
            "geometry_score": 0.0,
            "graph_score": 0.0,
            "engineering_score": 0.0,
            "combined_score": 0.0,
            "match_reasons": list(self.match_reasons),
        }


def has_wildcards(text: object) -> bool:
    return any(char in WILDCARD_CHARS for char in str(text or ""))


def _split_family(text: str) -> Tuple[str, str]:
    """Split ``text`` into ``(family_prefix, remainder)`` using the longest
    known family prefix. Returns ``("", text)`` when no family is recognized
    (wildcards inside the family prefix itself are not currently supported)."""

    return split_family(text, _FAMILY_PREFIXES)


def _mask_pattern(remainder: str) -> "re.Pattern[str]":
    """Regex requiring an exact-length match; one wildcard = one character."""

    parts = ["." if char in WILDCARD_CHARS else re.escape(char) for char in remainder]
    return re.compile("^" + "".join(parts) + "$")


def _describe_match(family: str, remainder: str) -> List[str]:
    reasons: List[str] = [f"Family {family} matches"] if family else []

    depth_match = _DEPTH_RE.match(remainder)
    if depth_match and not has_wildcards(depth_match.group(1)):
        reasons.append(f"Known depth {depth_match.group(1)} matches")

    weight_match = _WEIGHT_RE.search(remainder)
    if weight_match:
        known_prefix = re.match(r"[^*?]*", weight_match.group(1)).group(0)
        if known_prefix:
            reasons.append(f"Known weight prefix {known_prefix} matches")

    wildcard_count = sum(char in WILDCARD_CHARS for char in remainder)
    if wildcard_count:
        label = _NUMBER_WORDS.get(wildcard_count, str(wildcard_count))
        noun = "position" if wildcard_count == 1 else "positions"
        reasons.append(f"{label} wildcard {noun} matched")
    return reasons


def match_wildcard_mask(text: object, *, limit: int = 8) -> List[WildcardCandidate]:
    """
    Resolve a wildcarded label (e.g. ``W44X3**``) against the loaded AISC
    catalog using a deterministic positional mask.

    Returns an empty list when ``text`` has no wildcard characters, when the
    family cannot be recognized, or when no catalog label satisfies the mask.
    Every returned candidate exists in the AISC catalog by construction.
    """

    cleaned = str(text or "").strip().upper().replace(" ", "")
    if not cleaned or not has_wildcards(cleaned):
        return []

    family, remainder = _split_family(cleaned)
    if not family or not remainder:
        return []

    pattern = _mask_pattern(remainder)
    reasons = _describe_match(family, remainder)

    matches: List[WildcardCandidate] = []
    for label, shape_type in catalog_entries():
        if not label.startswith(family):
            continue
        candidate_remainder = label[len(family):]
        if len(candidate_remainder) != len(remainder):
            continue
        if pattern.match(candidate_remainder):
            matches.append(
                WildcardCandidate(
                    label=label,
                    catalog_type=shape_type,
                    catalog_valid=True,
                    mask_match=True,
                    match_reasons=list(reasons),
                )
            )

    matches.sort(key=lambda item: item.label)
    return matches[: max(1, limit)]
