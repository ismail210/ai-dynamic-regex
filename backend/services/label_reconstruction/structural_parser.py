"""Family-aware structural field parsing against the actual AISC v16 catalog.

Part 3/4 of the v3 architecture: fuzzy string similarity alone let
``HSS8X8X?`` rank ``HSS18X18X1`` above every real HSS8X8Xn entry, because
character-similarity has no notion of "depth" or "width" as distinct,
independently-meaningful fields. This module fixes that by parsing labels
into their real AISC fields (family, depth, weight; or family, depth,
width, thickness for HSS; etc.) and only ever treating two labels as
"structurally compatible" when every KNOWN (non-wildcard) field matches
exactly, field by field -- never by whole-string character similarity.

Grammar is derived empirically from ``services.database_loader.catalog_entries()``,
not assumed:

* W / M / S / HP / C / MC / WT / MT / ST -- always exactly 2 numeric
  fields split on the first/only "X": depth, weight. Both may contain a
  decimal point (e.g. ``WT10.5X22``, ``M12.5X11.6``).
* HSS -- either 3 fields (rectangular/square: depth, width, thickness) or
  2 fields (round: outside diameter, wall thickness). Both forms coexist
  in the real catalog (``HSS8X8X1/2`` vs. ``HSS28.000X1.000``).
* L -- always exactly 3 fields: leg, leg, thickness.
* 2L -- either 3 fields (leg, leg, thickness) or 4 fields (leg, leg,
  thickness, back-to-back separation) -- both are real, distinct AISC
  designations, confirmed by scanning the full 2L catalog slice.
* PIPE -- no "X" delimiter at all; grammar is
  ``PIPE<nominal size><STD|XS|XXS>`` via regex, confirmed against every
  PIPE catalog row.

A field parse can legitimately FAIL (e.g. a corruption destroyed the "X"
delimiter, as ``separator_space`` does after ``conservative_normalize``
strips whitespace). That is reported as ``ok=False`` -- Part 2 uses this
to classify a query as ``NO_EXACT_STRUCTURAL_MATCH`` rather than pretend a
parse succeeded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from services.database_loader import catalog_entries
from services.label_reconstruction.corruption import family_of
from services.wildcard_matcher import WILDCARD_CHARS

_DEPTH_WEIGHT_FAMILIES = {"W", "M", "S", "HP", "C", "MC", "WT", "MT", "ST"}
_PIPE_RE = re.compile(r"^PIPE([\d\-/.]*[?*]?[\d\-/.]*)(STD|XXS|XS|[?*]+)?$")


@dataclass
class FieldParse:
    family: str
    grammar: str
    fields: List[str]
    ok: bool


def _split_fields(remainder: str) -> List[str]:
    return remainder.split("X")


def parse_fields(text: str) -> FieldParse:
    """Parse ``text`` (a clean catalog label OR a corrupted/wildcarded
    query, already conservatively-normalized) into its structural fields.
    Never raises; ``ok=False`` means "could not confidently parse", not
    an error."""

    cleaned = str(text or "").strip().upper()
    fam = family_of(cleaned)
    if not fam or not cleaned.startswith(fam):
        return FieldParse(family=fam, grammar="unknown", fields=[], ok=False)
    remainder = cleaned[len(fam):]
    if not remainder:
        return FieldParse(family=fam, grammar="unknown", fields=[], ok=False)

    if fam == "PIPE":
        match = _PIPE_RE.match(cleaned)
        if not match:
            return FieldParse(family=fam, grammar="pipe", fields=[], ok=False)
        size, cls = match.group(1) or "", match.group(2) or ""
        return FieldParse(family=fam, grammar="pipe", fields=[size, cls], ok=bool(size and cls))

    if fam in _DEPTH_WEIGHT_FAMILIES:
        parts = _split_fields(remainder)
        if len(parts) != 2 or not all(parts):
            return FieldParse(family=fam, grammar="depth_weight", fields=parts, ok=False)
        return FieldParse(family=fam, grammar="depth_weight", fields=parts, ok=True)

    if fam == "L":
        parts = _split_fields(remainder)
        if len(parts) != 3 or not all(parts):
            return FieldParse(family=fam, grammar="leg_leg_thickness", fields=parts, ok=False)
        return FieldParse(family=fam, grammar="leg_leg_thickness", fields=parts, ok=True)

    if fam == "2L":
        parts = _split_fields(remainder)
        if len(parts) not in (3, 4) or not all(parts):
            return FieldParse(family=fam, grammar="leg_leg_thickness_sep", fields=parts, ok=False)
        return FieldParse(family=fam, grammar="leg_leg_thickness_sep", fields=parts, ok=True)

    if fam == "HSS":
        parts = _split_fields(remainder)
        if len(parts) == 3 and all(parts):
            return FieldParse(family=fam, grammar="hss_rect", fields=parts, ok=True)
        if len(parts) == 2 and all(parts):
            return FieldParse(family=fam, grammar="hss_round", fields=parts, ok=True)
        return FieldParse(family=fam, grammar="hss_rect", fields=parts, ok=False)

    # Family recognized by corruption.family_of but not in this module's
    # known grammar table -- treat as unparseable rather than guess.
    return FieldParse(family=fam, grammar="unknown", fields=[], ok=False)


def field_compatible(known_field: str, catalog_field: str) -> bool:
    """True when every non-wildcard character in ``known_field`` matches
    the corresponding character in ``catalog_field`` -- same length
    required. Purely positional; OCR-confusable-but-different characters
    are NOT considered compatible here (that leniency belongs to candidate
    generation's separate OCR-flex pass, not the compatibility count used
    for ambiguity classification)."""

    if len(known_field) != len(catalog_field):
        return False
    for a, b in zip(known_field, catalog_field):
        if a in WILDCARD_CHARS:
            continue
        if a != b:
            return False
    return True


def fields_compatible(query_fields: List[str], catalog_fields: List[str]) -> bool:
    if len(query_fields) != len(catalog_fields):
        return False
    return all(field_compatible(q, c) for q, c in zip(query_fields, catalog_fields))


# (family, grammar) -> [(fields, label), ...], built once and reused across
# every compatible_catalog_labels() call -- this function runs once per
# frozen-test row (2772+ calls per evaluation), so re-parsing the full
# 2299-row catalog from scratch on every call would dominate runtime.
_CATALOG_INDEX: Optional[Dict[Tuple[str, str], List[Tuple[List[str], str]]]] = None


def _ensure_catalog_index() -> Dict[Tuple[str, str], List[Tuple[List[str], str]]]:
    global _CATALOG_INDEX
    if _CATALOG_INDEX is not None:
        return _CATALOG_INDEX
    index: Dict[Tuple[str, str], List[Tuple[List[str], str]]] = {}
    for label, _type in catalog_entries():
        parse = parse_fields(label)
        if not parse.ok:
            continue
        index.setdefault((parse.family, parse.grammar), []).append((parse.fields, label))
    _CATALOG_INDEX = index
    return index


def compatible_catalog_labels(text: str) -> List[str]:
    """Every catalog label structurally compatible with ``text``'s known
    (non-wildcard) fields, same grammar and field count required. Empty
    list means either the parse failed (``NO_EXACT_STRUCTURAL_MATCH``) or
    genuinely zero catalog entries match every known field."""

    query_parse = parse_fields(text)
    if not query_parse.ok:
        return []
    index = _ensure_catalog_index()
    bucket = index.get((query_parse.family, query_parse.grammar), [])
    return [label for fields, label in bucket if fields_compatible(query_parse.fields, fields)]


def _parse_numeric_field(text: str) -> Optional[float]:
    text = (text or "").strip()
    if not text or any(ch in WILDCARD_CHARS for ch in text):
        return None
    try:
        if "-" in text and "/" in text:
            whole, frac = text.split("-", 1)
            num, den = frac.split("/")
            return float(whole) + float(num) / float(den)
        if "/" in text:
            num, den = text.split("/")
            return float(num) / float(den)
        return float(text)
    except (ValueError, ZeroDivisionError):
        return None


def nearest_by_fields(label: str, *, k: int = 6) -> List[str]:
    """Same-family, same-grammar catalog labels ranked by total numeric
    field distance (Part 6 hard-negative mining: "same family, nearby
    depth", "HSS same first dimensions but wrong thickness", etc.) --
    NOT edit distance or character similarity. E.g. for ``W18X35`` this
    surfaces ``W16X35``/``W21X35`` (depth off by one nominal size) and
    ``W18X30``/``W18X40`` (weight off by one nominal size) ahead of
    structurally-unrelated labels that merely look similar as strings."""

    label_parse = parse_fields(label)
    if not label_parse.ok:
        return []
    index = _ensure_catalog_index()
    bucket = index.get((label_parse.family, label_parse.grammar), [])
    label_nums = [_parse_numeric_field(f) for f in label_parse.fields]

    scored = []
    for fields, candidate in bucket:
        if candidate == label:
            continue
        total = 0.0
        comparable = 0
        for q_num, cand_field in zip(label_nums, fields):
            c_num = _parse_numeric_field(cand_field)
            if q_num is None or c_num is None:
                continue
            total += abs(q_num - c_num) / (1.0 + abs(q_num))
            comparable += 1
        if comparable == 0:
            continue
        scored.append((total, candidate))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [candidate for _dist, candidate in scored[:k]]


def _is_all_wildcards(field: str) -> bool:
    return bool(field) and all(ch in WILDCARD_CHARS for ch in field)


def field_generation_compatible(query_field: str, catalog_field: str) -> bool:
    """Looser sibling of ``field_compatible``, used only by v3 candidate
    GENERATION (never by the ambiguity metric). A field made entirely of
    wildcard characters (``?``, ``**``) is treated as "this whole field is
    illegible" rather than literally "exactly N unknown characters" --
    without this, ``HSS8X8X?`` cannot generate any HSS8X8Xn candidate at
    all, because no real thickness field ("1/2", "3/8", ...) is exactly
    one character long, and the fix for the HSS18X18X1 bug is precisely
    to keep depth/width exact while letting a fully-wildcarded thickness
    match any thickness. Partially-known fields (e.g. "3?") still require
    exact length -- only an ALL-wildcard field gets this relaxation."""

    if _is_all_wildcards(query_field):
        return True
    return field_compatible(query_field, catalog_field)


def generation_fields_compatible(query_fields: List[str], catalog_fields: List[str]) -> bool:
    if len(query_fields) != len(catalog_fields):
        return False
    return all(
        field_generation_compatible(q, c) for q, c in zip(query_fields, catalog_fields)
    )


def generation_compatible_catalog_labels(text: str) -> List[str]:
    """Family/field-aware candidate pool for v3 generation: same grammar
    and field count as ``compatible_catalog_labels``, but fully-wildcarded
    fields are treated as "any value" (see ``field_generation_compatible``).
    Still never matches across families or across a wrong depth/width --
    that structural constraint is exactly what fixes the
    HSS8X8X? -> HSS18X18X1 bug (depth field "8" only matches depth "8")."""

    query_parse = parse_fields(text)
    if not query_parse.ok:
        return []
    index = _ensure_catalog_index()
    bucket = index.get((query_parse.family, query_parse.grammar), [])
    return [
        label
        for fields, label in bucket
        if generation_fields_compatible(query_parse.fields, fields)
    ]


AMBIGUITY_UNIQUE = "UNIQUE"
AMBIGUITY_SMALL = "SMALL_AMBIGUOUS_SET"
AMBIGUITY_LARGE = "LARGE_AMBIGUOUS_SET"
AMBIGUITY_NO_MATCH = "NO_EXACT_STRUCTURAL_MATCH"


def ambiguity_category(compatible_count: int) -> str:
    if compatible_count == 0:
        return AMBIGUITY_NO_MATCH
    if compatible_count == 1:
        return AMBIGUITY_UNIQUE
    if compatible_count <= 5:
        return AMBIGUITY_SMALL
    return AMBIGUITY_LARGE
