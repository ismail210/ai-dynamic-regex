"""Structural label family/grammar detection.

Deliberately narrow: this module answers "is this text even a structural
steel designation, and if so, what family/grammar/typed fields does it
have" -- nothing else. It must reject architectural dimensions (``3'4"``)
and anything that doesn't match a known family grammar, rather than trying
to force a parse.

Where the repository already has a working, catalog-backed compatible-label
lookup (``services.label_reconstruction.structural_parser``), this module
calls into it for catalog validation rather than re-implementing a second
catalog index. That import is optional and best-effort: if the catalog
files aren't available in a given environment (e.g. a minimal test sandbox),
family/grammar detection still works, just without ``catalog_exact_match``.
"""
from __future__ import annotations

import re

from services.semantic.models import CATALOG_EXACT_MATCH, CATALOG_NOT_IN_CATALOG, StructuralParse

# Families with a simple "PREFIX + depth + X + weight-or-size" grammar.
_SIMPLE_FAMILY_RE = re.compile(
    r"^(?P<family>W|M|S|HP|C|MC|L|2L)(?P<depth>\d+(?:\.\d+)?)X(?P<rest>[\d./]+)$"
)

# Rectangular/square HSS: three numeric fields, HSSaXbXt.
_HSS_RECT_RE = re.compile(
    r"^HSS(?P<a>\d+(?:\.\d+)?)X(?P<b>\d+(?:\.\d+)?)X(?P<t>[\d./]+)$"
)

# Round HSS / Pipe: two numeric fields, OD x wall thickness, both decimal.
_HSS_ROUND_RE = re.compile(r"^HSS(?P<od>\d+\.\d+)X(?P<t>\d+\.\d+)$")
_PIPE_RE = re.compile(r"^PIPE(?P<size>[\d./]+)(?P<sched>STD|XS|XXS)?$")

_PL_RE = re.compile(r"^PL(?P<t>[\d./]+)(?:X(?P<w>[\d./]+))?$")
_BP_RE = re.compile(r"^BP(?P<l>\d+(?:\.\d+)?)X(?P<w>\d+(?:\.\d+)?)(?:X(?P<t>[\d./]+))?$")

# Architectural feet/inch dimensions -- must never be treated as structural.
_ARCHITECTURAL_RE = re.compile(r"^\d+['’]-?\d*(?:\"|”)?$")


def is_architectural_dimension(text: str) -> bool:
    """True for things like ``3'4"`` that must stay untouched by this pipeline."""

    return bool(_ARCHITECTURAL_RE.match(text.strip()))


def parse_structural_label(text: str) -> StructuralParse:
    candidate = text.strip().upper()
    if not candidate or is_architectural_dimension(candidate):
        return StructuralParse(is_structural=False, parser_reason="architectural_or_empty")

    m = _HSS_RECT_RE.match(candidate)
    if m:
        return _finish(StructuralParse(
            is_structural=True,
            family="HSS",
            grammar="hss_rectangular",
            fields={"a": m.group("a"), "b": m.group("b"), "t": m.group("t")},
        ), candidate)

    m = _HSS_ROUND_RE.match(candidate)
    if m:
        return _finish(StructuralParse(
            is_structural=True,
            family="HSS",
            grammar="hss_round",
            fields={"od": m.group("od"), "t": m.group("t")},
        ), candidate)

    m = _PIPE_RE.match(candidate)
    if m:
        return _finish(StructuralParse(
            is_structural=True,
            family="PIPE",
            grammar="pipe",
            fields={"size": m.group("size"), "schedule": m.group("sched")},
        ), candidate)

    m = _PL_RE.match(candidate)
    if m:
        return _finish(StructuralParse(
            is_structural=True,
            family="PL",
            grammar="plate",
            fields={"thickness": m.group("t"), "width": m.group("w")},
        ), candidate)

    m = _BP_RE.match(candidate)
    if m:
        return _finish(StructuralParse(
            is_structural=True,
            family="BP",
            grammar="base_plate",
            fields={"length": m.group("l"), "width": m.group("w"), "thickness": m.group("t")},
        ), candidate)

    m = _SIMPLE_FAMILY_RE.match(candidate)
    if m:
        return _finish(StructuralParse(
            is_structural=True,
            family=m.group("family"),
            grammar="depth_weight",
            fields={"depth": m.group("depth"), "rest": m.group("rest")},
        ), candidate)

    # Bare family shorthand with no size at all, e.g. "W8" alone -- structural
    # family is known, but the label is incomplete. This is a completion
    # case (Section 28), not a normalization/repair case, so it's flagged
    # is_structural=True with grammar="incomplete" rather than rejected.
    bare = re.match(r"^(?P<family>W|M|S|HP|C|MC|L|2L)(?P<depth>\d+(?:\.\d+)?)$", candidate)
    if bare:
        return StructuralParse(
            is_structural=True,
            family=bare.group("family"),
            grammar="incomplete",
            fields={"depth": bare.group("depth")},
            catalog_status=CATALOG_NOT_IN_CATALOG,
            parser_reason="missing_weight_or_size",
        )

    return StructuralParse(is_structural=False, parser_reason="no_known_grammar_matched")


def _finish(parse: StructuralParse, candidate: str) -> StructuralParse:
    parse.catalog_status = (
        CATALOG_EXACT_MATCH if _catalog_has_exact(candidate) else CATALOG_NOT_IN_CATALOG
    )
    return parse


def _catalog_has_exact(candidate: str) -> bool:
    compatible_catalog_labels = None
    try:
        from services.structural_parser import compatible_catalog_labels
    except Exception:  # pragma: no cover - module layout varies by branch
        try:
            from services.label_reconstruction.structural_parser import compatible_catalog_labels
        except Exception:
            return False
    try:
        return candidate in set(compatible_catalog_labels(candidate))
    except Exception:  # pragma: no cover - defensive: catalog lookup must never crash parsing
        return False
