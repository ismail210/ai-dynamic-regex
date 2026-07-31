"""
Phase 1 - Regex Learning Engine
================================

This module is the research core of the project. Instead of relying on a
hand-written dictionary of regular expressions, it *learns* a generalized
regex directly from a set of example tokens.

Pipeline
--------
1. Segmentation
   Every token is split into typed structural segments:
       - ALPHA  : a maximal run of letters            ("HSS", "X", "STD")
       - NUM    : an integer or decimal number         ("18", "12.5")
       - SEP    : a single non-alphanumeric separator  ("/", "-")

2. Generalization (per structural signature)
   Tokens that share the same *signature* (the ordered sequence of segment
   types, with separator characters kept literal) are generalized column by
   column into a list of regex fragments:
       ALPHA -> literal if constant, else ``[A-Z]+``
       NUM   -> ``\\d+`` or ``\\d+(?:\\.\\d+)?`` when decimals appear
       SEP   -> the escaped literal character

3. Merging via a fragment trie
   Each signature contributes exactly one fragment list. All fragment lists
   are inserted into a trie and emitted as a single regex, so:
       - shared prefixes collapse            (all "W" tokens -> ``W\\d+X\\d+``)
       - optional suffixes become optional   (``HSS\\d+X\\d+X\\d+(?:/\\d+)?``)
       - genuinely different shapes alternate (``(?:...|...)``)

The produced pattern is anchor-free (validation uses ``re.fullmatch``) and is
stored in upper-case; matching is performed case-insensitively.

The whole engine contains **no hand-written engineering regex** — every
pattern is derived from data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from services.regex_optimizer import optimize_variants, pick_primary_pattern, readability_score

# ---------------------------------------------------------------------------
# Segment types
# ---------------------------------------------------------------------------

ALPHA = "ALPHA"
NUM = "NUM"
SEP = "SEP"


@dataclass
class Segment:
    """A single typed structural unit of a token."""

    type: str
    value: str
    has_decimal: bool = False


def segment_token(token: str) -> List[Segment]:
    """Split a raw token into an ordered list of typed segments."""

    token = str(token).strip()
    segments: List[Segment] = []
    i = 0
    n = len(token)

    while i < n:
        c = token[i]

        # --- letters ----------------------------------------------------
        if c.isalpha():
            j = i
            while j < n and token[j].isalpha():
                j += 1
            segments.append(Segment(ALPHA, token[i:j].upper()))
            i = j

        # --- numbers (integer or decimal) -------------------------------
        elif c.isdigit():
            j = i
            while j < n and token[j].isdigit():
                j += 1
            has_decimal = False
            # Look ahead for a decimal part: digits '.' digits
            if j < n and token[j] == "." and (j + 1) < n and token[j + 1].isdigit():
                has_decimal = True
                j += 1  # consume '.'
                while j < n and token[j].isdigit():
                    j += 1
            segments.append(Segment(NUM, token[i:j], has_decimal=has_decimal))
            i = j

        # --- separators -------------------------------------------------
        else:
            segments.append(Segment(SEP, c))
            i += 1

    return segments


def token_signature(segments: List[Segment]) -> Tuple[str, ...]:
    """
    Build a structural signature used to group tokens that share the same
    layout. Separator characters are kept literal so that ``a/b`` and ``a-b``
    do not accidentally align.
    """

    sig: List[str] = []
    for seg in segments:
        if seg.type == ALPHA:
            sig.append("A")
        elif seg.type == NUM:
            sig.append("N")
        else:  # SEP
            sig.append(f"S:{seg.value}")
    return tuple(sig)


# ---------------------------------------------------------------------------
# Column-wise generalization inside a signature group
# ---------------------------------------------------------------------------

def _generalize_alpha(values: List[str]) -> str:
    """Generalize a column of alphabetic segments into a regex fragment."""

    unique = sorted(set(values))
    if len(unique) == 1:
        return re.escape(unique[0])
    # Distinct letter groups at the same position -> alternate them if the
    # set is small, otherwise fall back to a generic letter run.
    if len(unique) <= 4 and all(v.isalpha() for v in unique):
        return "(?:" + "|".join(re.escape(v) for v in unique) + ")"
    return "[A-Z]+"


def _generalize_num(segments: List[Segment]) -> str:
    """Generalize a column of numeric segments into a regex fragment."""

    any_decimal = any(s.has_decimal for s in segments)
    all_decimal = all(s.has_decimal for s in segments)

    if all_decimal:
        return r"\d+\.\d+"
    if any_decimal:
        return r"\d+(?:\.\d+)?"
    return r"\d+"


def _generalize_signature_group(tokens_segments: List[List[Segment]]) -> List[str]:
    """
    Given several tokens that share the exact same signature, generalize them
    column by column into a single list of regex fragments.
    """

    length = len(tokens_segments[0])
    fragments: List[str] = []

    for col in range(length):
        column = [segs[col] for segs in tokens_segments]
        kind = column[0].type

        if kind == ALPHA:
            fragments.append(_generalize_alpha([s.value for s in column]))
        elif kind == NUM:
            fragments.append(_generalize_num(column))
        else:  # SEP - constant within a signature by construction
            fragments.append(re.escape(column[0].value))

    return fragments


# ---------------------------------------------------------------------------
# Fragment trie -> regex
# ---------------------------------------------------------------------------

@dataclass
class _TrieNode:
    children: Dict[str, "_TrieNode"] = field(default_factory=dict)
    is_end: bool = False


def _insert(root: _TrieNode, fragments: List[str]) -> None:
    node = root
    for frag in fragments:
        node = node.children.setdefault(frag, _TrieNode())
    node.is_end = True


def _emit(node: _TrieNode) -> str:
    """Emit a regex string that matches any completion starting at ``node``."""

    branches: List[str] = []
    for frag, child in node.children.items():
        branches.append(frag + _emit(child))

    if not branches:
        return ""

    if len(branches) == 1:
        body = branches[0]
    else:
        body = "(?:" + "|".join(branches) + ")"

    # If this node also terminates a token, everything below it is optional.
    if node.is_end:
        return f"(?:{body})?"
    return body


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def learn_regex(tokens: List[str]) -> Optional[str]:
    """
    Learn a single generalized regex that describes ``tokens``.

    Returns ``None`` when no usable tokens are supplied. The returned pattern
    is anchor-free and intended to be validated with ``re.fullmatch`` using the
    ``re.IGNORECASE`` flag.
    """

    cleaned = [str(t).strip() for t in tokens if str(t).strip()]
    if not cleaned:
        return None

    # Group tokens by structural signature.
    groups: Dict[Tuple[str, ...], List[List[Segment]]] = {}
    for token in cleaned:
        segs = segment_token(token)
        if not segs:
            continue
        groups.setdefault(token_signature(segs), []).append(segs)

    if not groups:
        return None

    # Each signature -> one generalized fragment list.
    fragment_lists = [
        _generalize_signature_group(members) for members in groups.values()
    ]

    # Merge all fragment lists through a trie and emit a single regex.
    root = _TrieNode()
    for fragments in fragment_lists:
        _insert(root, fragments)

    return _emit(root)


def _variant_confidence(pattern: Optional[str], support: int, total: int) -> float:
    """Conservative confidence for one structural variant."""
    if not pattern or not total:
        return 0.0
    frequency = support / total
    support_score = min(1.0, support / 5)
    score = 0.45 * frequency + 0.35 * support_score + 0.20 * readability_score(pattern)
    return round(max(0.0, min(0.97, score)), 4)


def learn_regex_variants(tokens: List[str]) -> List[dict]:
    """Learn small, readable patterns per structural signature."""
    cleaned = [str(token).strip() for token in tokens if str(token).strip()]
    total = len(cleaned)
    grouped: Dict[Tuple[str, ...], List[str]] = {}
    for token in cleaned:
        grouped.setdefault(token_signature(segment_token(token)), []).append(token)

    variants = []
    for signature, members in grouped.items():
        pattern = learn_regex(members)
        support = len(members)
        variants.append({
            "pattern": pattern,
            "support": support,
            "frequency": round(support / total, 4) if total else 0.0,
            "confidence": _variant_confidence(pattern, support, total),
            "distinct_structure": list(signature),
            "examples": members[:5],
        })
    return optimize_variants(variants)


def learn_regex_with_report(tokens: List[str]) -> dict:
    """
    Learn a regex and return a rich report useful for research/inspection:
    the pattern, the number of distinct structural signatures discovered and
    a couple of representative example tokens.
    """

    cleaned = [str(t).strip() for t in tokens if str(t).strip()]
    variants = learn_regex_variants(cleaned)
    pattern = pick_primary_pattern(variants)

    signatures = {token_signature(segment_token(token)) for token in cleaned}

    return {
        "pattern": pattern,
        "variants": variants,
        "example_count": len(cleaned),
        "distinct_structures": len(signatures),
        "examples": cleaned[:5],
    }


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    demos = {
        "W": ["W18X40", "W16X26", "W36X170"],
        "HSS": ["HSS34X10X1", "HSS34X10X7/8", "HSS8X8"],
        "M": ["M12.5X12.4", "M12X11.8"],
        "PIPE": ["Pipe26STD", "Pipe24STD"],
        "2L": ["2L12X12X1-3/8", "2L12X12X1-3/8X3/4"],
    }
    for name, ex in demos.items():
        print(f"{name:6} {ex}  ->  {learn_regex(ex)}")
