"""
Phase 3 - Regex Validation Engine
=================================

Validates a (learned) regex against a set of example tokens using
``re.fullmatch`` and produces a coverage-based confidence score together with a
qualitative level: ``High`` / ``Medium`` / ``Low``.

The score also applies a light specificity penalty so that overly generic
patterns (e.g. ``.*`` or ``[A-Z]+\\d+``) do not receive a perfect score just
because they happen to match everything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from services.prediction.confidence_engine import level_from_score
from services.regex_optimizer import readability_score, simplify_regex


@dataclass
class ValidationResult:
    pattern: Optional[str]
    is_valid_regex: bool
    coverage: float                 # fraction of examples matched (0..1)
    matched: int
    total: int
    specificity: float              # 0..1, higher = more specific
    confidence: float               # 0..1 combined score
    level: str                      # High / Medium / Low
    unmatched_examples: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "is_valid_regex": self.is_valid_regex,
            "coverage": round(self.coverage, 4),
            "matched": self.matched,
            "total": self.total,
            "specificity": round(self.specificity, 4),
            "confidence": round(self.confidence, 4),
            "level": self.level,
            "unmatched_examples": self.unmatched_examples[:10],
        }


def compile_pattern(pattern: Optional[str]) -> Optional[re.Pattern]:
    """Safely compile a pattern (case-insensitive). Returns None on failure."""

    if not pattern:
        return None
    try:
        return re.compile(pattern, flags=re.IGNORECASE)
    except re.error:
        return None


def full_match(pattern: Optional[str], token: str) -> bool:
    """Return True if ``token`` is fully matched by ``pattern``."""

    compiled = compile_pattern(pattern)
    if compiled is None:
        return False
    return compiled.fullmatch(str(token).strip()) is not None


def _estimate_specificity(pattern: str) -> float:
    """
    Heuristic specificity estimate in [0, 1]. Literal characters and explicit
    digit classes are considered specific; unbounded wildcards reduce the
    score. This keeps confidence honest for very loose patterns.
    """

    if not pattern:
        return 0.0

    score = 0.6

    # Reward the presence of literal anchors (letters/digits/separators).
    literal_chars = len(re.findall(r"[A-Za-z0-9]", pattern))
    score += min(literal_chars, 8) * 0.05

    # Penalise very loose constructs.
    if ".*" in pattern or ".+" in pattern:
        score -= 0.4
    if "[A-Z]+" in pattern and literal_chars <= 1:
        score -= 0.15

    return max(0.0, min(1.0, score))


def validate_regex(pattern: Optional[str], examples: List[str]) -> ValidationResult:
    """
    Validate ``pattern`` against ``examples`` and compute a confidence score.

    Confidence = 0.75 * coverage + 0.25 * specificity, scaled slightly down
    when very few examples are available (low statistical support).
    """

    pattern = simplify_regex(pattern)
    examples = [str(e).strip() for e in examples if str(e).strip()]
    total = len(examples)

    compiled = compile_pattern(pattern)
    is_valid = compiled is not None

    if not is_valid or total == 0:
        return ValidationResult(
            pattern=pattern,
            is_valid_regex=is_valid,
            coverage=0.0,
            matched=0,
            total=total,
            specificity=_estimate_specificity(pattern or ""),
            confidence=0.0,
            level="Low",
            unmatched_examples=examples[:10],
        )

    matched = 0
    unmatched: List[str] = []
    for token in examples:
        if compiled.fullmatch(token):
            matched += 1
        else:
            unmatched.append(token)

    coverage = matched / total
    specificity = _estimate_specificity(pattern)

    # Coverage alone is not enough: a readable pattern with more independent
    # examples deserves confidence, while a generic/poorly supported one does not.
    support_score = min(1.0, total / 8)
    confidence = (
        0.50 * coverage
        + 0.20 * specificity
        + 0.20 * readability_score(pattern)
        + 0.10 * support_score
    )
    confidence = max(0.0, min(0.97, confidence))

    return ValidationResult(
        pattern=pattern,
        is_valid_regex=True,
        coverage=coverage,
        matched=matched,
        total=total,
        specificity=specificity,
        confidence=confidence,
        level=level_from_score(confidence),
        unmatched_examples=unmatched,
    )
