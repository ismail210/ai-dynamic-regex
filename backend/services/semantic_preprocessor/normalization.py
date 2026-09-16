"""Deterministic canonicalization (Section 23-24) and a minimal repair layer
(Section 27).

Normalization changes REPRESENTATION only and must never guess missing
information. The single highest-risk rule in this module is the
rectangular/square-HSS-only fraction<->decimal conversion: round HSS and
Pipe designations are legitimately decimal (``HSS5.563X0.258``) and must
never be touched, even though they share the ``HSS`` prefix with rectangular
HSS (``HSS8X8X3/8``). See ``structural_parser.py`` for how the two grammars
are told apart before this module ever sees a thickness field.

Repair (OCR-style character corruption, e.g. ``W8XI0``) is handled here only
in a minimal, conservative form: single-character confusion-set substitution
that must land on an exact, catalog-valid grammar match to be proposed at
all, and is NEVER auto-accepted (``auto_accept`` is always ``False`` for a
repair produced by this module -- confidence is uncalibrated). This is
intentionally not a replacement for the existing ranking-based repair engine
in ``services.exact_section_predictor`` / ``services.label_reconstruction``;
it exists so the semantic pipeline has a safe, explicit place to route
corrupted-but-recoverable text without inventing a second candidate-ranking
system (Section 57: do not train a new transformer / do not build a second
section-dimension database).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from services.normalization import normalize_label_text
from services.semantic.models import OperationKind, OperationRecord, ScoreValue
from services.semantic_preprocessor.structural_parser import (
    StructuralParse,
    parse_structural_label,
)

# Standard mill fraction increments (1/16" steps) used for HSS/PL/L wall and
# leg thickness fields. Anything that doesn't land within tolerance of one
# of these is left as-is rather than guessed at.
_STANDARD_SIXTEENTHS = {round(n / 16, 6): Fraction(n, 16) for n in range(1, 16)}
_FRACTION_TOLERANCE = 0.002  # inches

_OCR_CONFUSIONS = {
    "I": "1", "1": "I",
    "O": "0", "0": "O",
    "B": "8", "8": "B",
    "S": "5", "5": "S",
    "L": "1",
}


@dataclass
class CanonicalizationResult:
    parse: StructuralParse
    operation: OperationRecord


def _to_fraction_string(value: str) -> Optional[str]:
    """Convert a decimal thickness string to its standard fraction form.

    Returns None (leave untouched) when the value isn't within tolerance of
    a standard 1/16" increment -- a genuinely custom dimension should fail
    closed, not be silently reinterpreted (Section 4.1 / 24).
    """
    if "/" in value:
        return None  # already a fraction; nothing to convert
    try:
        decimal_value = float(value)
    except ValueError:
        return None
    for target, frac in _STANDARD_SIXTEENTHS.items():
        if abs(decimal_value - target) <= _FRACTION_TOLERANCE:
            return f"{frac.numerator}/{frac.denominator}"
    return None


def _reassemble(parse: StructuralParse) -> Optional[str]:
    family = parse.family
    fields = parse.fields
    if parse.grammar == "hss_rectangular":
        t = fields["t"]
        fraction = _to_fraction_string(t)
        canonical_t = fraction if fraction is not None else t
        return f"HSS{fields['a']}X{fields['b']}X{canonical_t}"
    if parse.grammar == "angle":
        # Same thickness fraction rule as rectangular HSS. Never invent a
        # missing thickness — incomplete LaXb stays outside this grammar.
        t = fields["t"]
        fraction = _to_fraction_string(t)
        canonical_t = fraction if fraction is not None else t
        return f"{family}{fields['a']}X{fields['b']}X{canonical_t}"
    if parse.grammar == "hss_round":
        # Round HSS/Pipe stays decimal, verbatim -- never fraction-converted.
        return f"HSS{fields['od']}X{fields['t']}"
    if parse.grammar == "depth_weight":
        return f"{family}{fields['depth']}X{fields['rest']}"
    if parse.grammar == "pipe":
        sched = fields.get("schedule") or ""
        return f"PIPE{fields['size']}{sched}"
    if parse.grammar == "plate":
        w = fields.get("width")
        return f"PL{fields['thickness']}" + (f"X{w}" if w else "")
    if parse.grammar == "base_plate":
        t = fields.get("thickness")
        base = f"BP{fields['length']}X{fields['width']}"
        return base + (f"X{t}" if t else "")
    return None


def format_designation_for_pdf(text: str) -> str:
    """Deterministic designation form for PDF write / Accept (fractions, etc.).

    Reuses ``canonicalize`` so Results and Semantic Review share one formatter.
    Never invents missing thickness or otherwise weakens safety gates.
    """
    if not text or not str(text).strip():
        return text
    result = canonicalize(str(text).strip())
    out = (result.operation.output_text or "").strip()
    return out or str(text).strip()


def canonicalize(raw_text: str) -> CanonicalizationResult:
    """Run the deterministic normalization pipeline for one label token.

    Never called on a full ``W8X10 [24]`` compound annotation -- callers
    pass only the already-grouped ``primary_label`` fragment (see
    ``grouping.py``); the bracket modifier is a separate concern.
    """
    lexed = normalize_label_text(raw_text).normalized
    parse = parse_structural_label(lexed)

    if not parse.is_structural:
        repaired = _try_repair(lexed)
        if repaired is not None:
            return CanonicalizationResult(parse=parse, operation=repaired)
        return CanonicalizationResult(
            parse=parse,
            operation=OperationRecord(operation=OperationKind.KEEP, input_text=raw_text, output_text=lexed),
        )

    if parse.grammar == "incomplete":
        # Missing information -- this is a completion case (Section 28),
        # not something this module may guess at.
        return CanonicalizationResult(
            parse=parse,
            operation=OperationRecord(operation=OperationKind.KEEP, input_text=raw_text, output_text=lexed),
        )

    canonical = _reassemble(parse) or lexed
    # Compare against the true original -- not the pre-lexed intermediate --
    # so a case/spacing/separator-only change (e.g. "W18x40" -> "W18X40")
    # is correctly reported as a normalization, not silently absorbed into
    # "lexing" and reported as unchanged.
    if canonical == raw_text:
        return CanonicalizationResult(
            parse=parse,
            operation=OperationRecord(operation=OperationKind.KEEP, input_text=raw_text, output_text=canonical),
        )
    return CanonicalizationResult(
        parse=parse,
        operation=OperationRecord(
            operation=OperationKind.NORMALIZATION,
            input_text=raw_text,
            output_text=canonical,
            score=ScoreValue(value=1.0, kind="deterministic", calibrated=False),
            deterministic=True,
            semantic_information_added=False,
            provenance="deterministic_normalizer",
            reason_codes=["deterministic_grammar_equivalence"],
        ),
    )


def _try_repair(lexed: str) -> Optional[OperationRecord]:
    """Single-character OCR-confusion repair, gated to an exact grammar+catalog hit.

    Deliberately does not rank multiple candidates or use edit-distance
    scoring -- that is the job of the existing repair/ranking services. This
    only proposes a repair when substituting exactly one confusable
    character produces a single, unambiguous, catalog-valid structural
    label; otherwise it abstains (returns None).
    """
    candidates = set()
    for i, ch in enumerate(lexed):
        replacement = _OCR_CONFUSIONS.get(ch)
        if replacement is None:
            continue
        candidate = lexed[:i] + replacement + lexed[i + 1 :]
        parse = parse_structural_label(candidate)
        if parse.is_structural and parse.grammar not in (None, "incomplete") and parse.catalog_exact_match:
            candidates.add(candidate)
    if len(candidates) != 1:
        return None  # zero or ambiguous -- abstain rather than guess
    (canonical,) = candidates
    return OperationRecord(
        operation=OperationKind.REPAIR,
        input_text=lexed,
        output_text=canonical,
        score=None,  # uncalibrated -- never fabricate a number
        deterministic=True,
        provenance="deterministic_normalizer",
        reason_codes=["single_char_ocr_confusion_candidate"],
    )
