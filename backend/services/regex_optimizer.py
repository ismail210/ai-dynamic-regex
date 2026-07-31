"""
Regex Optimizer / Simplifier
============================

Post-processes learned regex into human-readable patterns.
Never emit giant nested alternation trees.
"""

from __future__ import annotations

import re
from typing import List, Optional

MAX_READABLE_LENGTH = 64


def simplify_regex(pattern: Optional[str]) -> Optional[str]:
    if not pattern:
        return pattern

    p = pattern

    changed = True
    while changed:
        changed = False

        def _unwrap(m: re.Match) -> str:
            inner = m.group(1)
            if "|" in inner or inner.startswith("?"):
                return m.group(0)
            return inner

        new_p = re.sub(r"\(\?:([A-Za-z0-9\\]+)\)(?![?*+{])", _unwrap, p)
        if new_p != p:
            p = new_p
            changed = True

    def _dedupe_alt(m: re.Match) -> str:
        parts = m.group(1).split("|")
        seen = []
        for part in parts:
            if part not in seen:
                seen.append(part)
        if len(seen) == 1:
            return seen[0]
        return "(?:" + "|".join(seen) + ")"

    p = re.sub(r"\(\?:((?:[^()|]+\|)+[^()|]+)\)", _dedupe_alt, p)
    p = p.replace("(?:)?", "")
    p = p.replace(r"\/", "/")
    return p


def readability_score(pattern: Optional[str]) -> float:
    if not pattern:
        return 0.0
    length = len(pattern)
    nests = pattern.count("(?:")
    alts = pattern.count("|")
    score = 1.0
    if length > 24:
        score -= min(0.55, (length - 24) / MAX_READABLE_LENGTH)
    score -= min(0.30, nests * 0.04)
    score -= min(0.20, alts * 0.03)
    return max(0.05, min(1.0, score))


def is_readable(pattern: Optional[str]) -> bool:
    if not pattern:
        return False
    return len(pattern) <= MAX_READABLE_LENGTH and pattern.count("(?:") <= 4


def optimize_variants(variants: List[dict]) -> List[dict]:
    best_by_pattern = {}
    for v in variants:
        pattern = simplify_regex(v.get("pattern"))
        if not pattern or not is_readable(pattern):
            if not pattern or len(pattern) > MAX_READABLE_LENGTH:
                continue
        entry = dict(v)
        entry["pattern"] = pattern
        entry["readability"] = round(readability_score(pattern), 4)
        prev = best_by_pattern.get(pattern)
        if prev is None or entry.get("support", 0) > prev.get("support", 0):
            best_by_pattern[pattern] = entry

    optimized = list(best_by_pattern.values())
    optimized.sort(
        key=lambda x: (x.get("support", 0), x.get("confidence", 0), x.get("readability", 0)),
        reverse=True,
    )
    return optimized


def pick_primary_pattern(variants: List[dict]) -> Optional[str]:
    if not variants:
        return None
    return variants[0].get("pattern")
