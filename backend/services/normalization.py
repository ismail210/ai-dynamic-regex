"""
Conservative, formatting-only text normalization for steel-label comparison.

This is the single shared normalizer used to decide ``exact_match`` versus
``normalized_match`` in the canonical prediction contract. It performs only
formatting-safe transformations:

* Unicode normalization (NFKC)
* Uppercasing
* Unifying multiplication separators (``×``, ``✕``, ``x``) to ``X``
* Trimming and collapsing whitespace around dimensions

It intentionally never performs OCR character-substitution guesses
(``S``<->``5``, ``O``<->``0``, ``I``/``L``<->``1``, ``B``<->``8``), never
deletes unknown characters (``*``, ``?``), and never fills missing digits.
Those are correction/candidate hypotheses and belong to
``services.wildcard_matcher`` and ``services.exact_section_predictor``, not
normalization. Conflating the two is exactly what made ``W18X3S`` silently
look like a "normalized match" instead of a flagged correction in the past.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List


_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class NormalizationResult:
    """Raw input, its conservatively normalized form, and the steps applied."""

    raw: str
    normalized: str
    transformations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "transformations": list(self.transformations),
        }


def normalize_label_text(value: object) -> NormalizationResult:
    """Apply only formatting-safe normalization, logging each step taken."""

    raw = "" if value is None else str(value)
    text = raw
    transformations: List[str] = []

    unicode_text = unicodedata.normalize("NFKC", text)
    if unicode_text != text:
        transformations.append("unicode_nfkc")
    text = unicode_text

    stripped = text.strip()
    if stripped != text:
        transformations.append("trimmed_whitespace")
    text = stripped

    upper = text.upper()
    if upper != text:
        transformations.append("uppercased")
    text = upper

    unified = text.replace("×", "X").replace("✕", "X")
    if unified != text:
        transformations.append("multiplication_separator_unified")
    text = unified

    collapsed = _WHITESPACE_RE.sub("", text)
    if collapsed != text:
        transformations.append("whitespace_removed")
    text = collapsed

    return NormalizationResult(raw=raw, normalized=text, transformations=transformations)


def is_conservatively_equal(raw: object, canonical: object) -> bool:
    """True when ``raw`` normalizes to exactly the same text as ``canonical``."""

    left = normalize_label_text(raw).normalized
    right = normalize_label_text(canonical).normalized
    return bool(left) and left == right
