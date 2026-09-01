"""Deterministic AISC candidate generation for damaged label text.

This is the validity gate: every candidate returned here is a real row from
``services.database_loader.catalog_entries()``. Nothing downstream (baseline
scorers or the learned ranker) is allowed to invent a label -- they only
reorder what this module produces.

Pipeline stage: normalization -> family/partial-pattern extraction ->
candidate generation. See ``services.label_reconstruction`` docstring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set

from services.annotation.plate_grammar import starts_with_plate_head
from services.family_codes import MODERN_FAMILY_CODES
from services.database_loader import catalog_entries, is_catalog_label
from services.label_reconstruction.corruption import OCR_CONFUSION, family_of
from services.structural_parser import (
    MISSING_FIELD,
    FieldParse,
    exact_catalog_labels_for_fields,
    generation_compatible_catalog_labels,
    generation_fields_compatible,
    is_missing_field,
    parse_fields,
)
from services.wildcard_matcher import WILDCARD_CHARS, has_wildcards, match_wildcard_mask

_CATALOG_ENTRIES = None  # lazy cache: List[(normalized_label, type)]
_CATALOG_LABELS: Set[str] = set()
_BY_LENGTH: Dict[int, List[str]] = {}
_BY_FAMILY: Dict[str, List[str]] = {}


def _ensure_loaded() -> None:
    if _CATALOG_ENTRIES is not None:
        return
    refresh_catalog_cache()


def refresh_catalog_cache() -> None:
    """Rebuild every module-level candidate-generation cache from the
    currently loaded catalog.

    Call after `services.database_loader.reload_from_pairs`/
    `reload_from_aisc_v16_catalog` in offline training/eval contexts -- these
    caches are otherwise built once (on first use) and never invalidated, so
    a catalog swap mid-process would silently keep generating candidates
    from the previous catalog.
    """

    global _CATALOG_ENTRIES
    entries = catalog_entries()
    _CATALOG_ENTRIES = entries
    _CATALOG_LABELS.clear()
    _BY_LENGTH.clear()
    _BY_FAMILY.clear()
    for label, _type in entries:
        _CATALOG_LABELS.add(label)
        _BY_LENGTH.setdefault(len(label), []).append(label)
        _BY_FAMILY.setdefault(family_of(label), []).append(label)


_REPEATED_HSS_GROUP = re.compile(
    r"^(HSS)\s*(\d+(?:\.\d+)?(?:X\d+(?:\.\d+)?(?:X[\d./]+)?))(?:\s+\2)+\s*$",
    re.I,
)
# OCR sometimes repeats a W/C/S depth-weight group: ``W 4X4 4X4``.
_REPEATED_DEPTH_WEIGHT_GROUP = re.compile(
    r"^(W|WT|M|S|HP|C|MC|MT|ST)\s*"
    r"(\d+(?:\.\d+)?X\d+(?:\.\d+)?)"
    r"(?:\s+\2)+\s*$",
    re.I,
)
_CLEAN_NUMERIC_FIELD = re.compile(r"^\d+(?:\.\d+)?(?:/\d+)?$")
_ANON_DIMENSION = re.compile(r"^[\d./\"]+\.?$")
_DIMENSION_ONLY_SYNTAX = re.compile(
    r'^[\d\s./"\-X×✕✖Ø⌀]+$',
    re.I,
)
# OCR often splits lintel notes into "1/2\"x5/16\"ANGLE" with no L-family prefix.
_FAMILYLESS_ANGLE_CALLOUT = re.compile(
    r'^[\d./"\-X×✕✖Ø⌀]+ANGLE$',
    re.I,
)
# Stray multiply-sign fragments such as ``x12"``.
_LEADING_X_FRAGMENT = re.compile(
    r'^X[\d./"\-Ø⌀]+$',
    re.I,
)
# Welded-wire reinforcement, not a W-section: ``6x6-W1.4xW1.4``.
_WWR_MESH = re.compile(
    r"^\d+X\d+-W\d+(?:\.\d+)?XW\d+(?:\.\d+)?$",
    re.I,
)
# Spacing / on-center / similar context after a section: ``W12x19@5'``.
_AT_CONTEXT_START = re.compile(r"^(?:\d|['\"″′]|O\.?C)", re.I)


def _collapse_repeated_hss_groups(text: str) -> str:
    """Keep the first HSS dimension group when OCR repeats it (``HSS 8X8 8X8``)."""

    match = _REPEATED_HSS_GROUP.match(text)
    if not match:
        return text
    return f"{match.group(1)} {match.group(2)}"


def _collapse_repeated_depth_weight_groups(text: str) -> str:
    """Keep the first depth-weight group when OCR repeats it (``W 4X4 4X4``)."""

    match = _REPEATED_DEPTH_WEIGHT_GROUP.match(text)
    if not match:
        return text
    return f"{match.group(1)} {match.group(2)}"


def _strip_at_context_suffix(text: str) -> str:
    """Drop ``@...`` spacing/on-center context from a rolled-section token.

    ``W12x19@5'`` is a W12X19 plus spacing metadata; the ``5`` must not
    become the section weight. Only strips when the left side is a known
    section family and the right side looks like spacing/context, not when
    ``@`` is interior OCR noise such as ``W12@X19``.
    """

    if "@" not in text:
        return text
    left, right = text.split("@", 1)
    if not left or not right:
        return text
    if family_of(left) not in MODERN_FAMILY_CODES:
        return text
    if not _AT_CONTEXT_START.match(right):
        return text
    return left


def conservative_normalize(raw: str) -> str:
    """Whitespace/case/multiply-sign normalization only -- never guesses
    digits. Mirrors the normalization already applied by the production
    extraction path so the benchmark reflects what inference will see."""

    text = str(raw or "").strip().upper()
    text = text.replace("×", "X").replace("-X", "X")
    text = _collapse_repeated_hss_groups(text)
    text = _collapse_repeated_depth_weight_groups(text)
    text = "".join(text.split())
    # Strip a single layer of parenthesis/noise wrapping, but keep interior
    # wildcard/unknown markers untouched.
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return _strip_at_context_suffix(text)


def _unwrap_eligibility_text(text: str) -> str:
    """Strip wrapping brackets and trailing list punctuation for eligibility.

    Does not rewrite interior structural characters. ``HSS12\"x4\"x1/2\"``
    and cut-length L labels are unchanged.
    """

    value = str(text or "").strip()
    for _ in range(4):
        if not value:
            break
        changed = False
        if value[0] in "([{" and value[-1] in ")]}":
            value = value[1:-1].strip()
            changed = True
        elif value[0] in "([{":
            value = value[1:].strip()
            changed = True
        elif value[-1] in ")]},;:":
            value = value[:-1].strip()
            changed = True
        if not changed:
            break
    return value


def _eligibility_surfaces(raw_text: str, normalized: str) -> List[str]:
    surfaces: List[str] = []
    for candidate in (
        normalized,
        str(raw_text or "").strip(),
        _unwrap_eligibility_text(raw_text),
        _unwrap_eligibility_text(normalized),
    ):
        if candidate and candidate not in surfaces:
            surfaces.append(candidate)
        unwrapped = _unwrap_eligibility_text(candidate)
        if unwrapped and unwrapped not in surfaces:
            surfaces.append(unwrapped)
        collapsed = conservative_normalize(unwrapped) if unwrapped else ""
        if collapsed and collapsed not in surfaces:
            surfaces.append(collapsed)
    return surfaces


def _quoted_l_leg_fields(normalized: str) -> bool:
    """True when an L/2L token puts inch marks on the designation legs.

    Cut-length suffixes such as ``L3X3X3/8X0'-6\"`` keep quotes off the
    first three fields and stay eligible. Opening callouts such as
    ``(L52\"x52\"x14\"T)`` do not.
    """

    fam = family_of(normalized)
    if fam not in {"L", "2L"}:
        return False
    remainder = normalized[len(fam) :]
    parts = remainder.split("X")
    designation = parts[:3]
    return any('"' in part or "”" in part for part in designation)


def _familyless_dimension_surface(surface: str) -> bool:
    fam = family_of(conservative_normalize(surface) if surface else "")
    if fam in MODERN_FAMILY_CODES:
        return False
    collapsed = conservative_normalize(surface)
    if _ANON_DIMENSION.match(surface) or _ANON_DIMENSION.match(collapsed):
        return True
    if _FAMILYLESS_ANGLE_CALLOUT.match(collapsed):
        return True
    if _LEADING_X_FRAGMENT.match(collapsed):
        return True
    if _DIMENSION_ONLY_SYNTAX.fullmatch(surface) or _DIMENSION_ONLY_SYNTAX.fullmatch(
        collapsed
    ):
        from services.annotation.parser import interpret_annotation
        from services.annotation.taxonomy import AnnotationType

        parsed = interpret_annotation(
            raw_text=surface,
            normalized_text=collapsed,
        )
        if (
            parsed.annotation_type == AnnotationType.DIMENSION.value
            and not parsed.structure_confirmed
        ):
            return True
        if _DIMENSION_ONLY_SYNTAX.fullmatch(collapsed) and fam not in MODERN_FAMILY_CODES:
            return True
    return False


def ineligible_for_section_reconstruction(raw_text: str, normalized: str = "") -> bool:
    """True when reconstruct must not emit rolled-section candidates.

    Familyless compound dimensions are semantically ambiguous: they may be
    plate dimensions, layout dimensions, or an incomplete section callout
    whose family can only be recovered from drawing context.  The production
    annotation layer already classifies these as unconfirmed ``DIMENSION``
    records and routes them through its context resolver instead of rolled
    section fusion.  Apply that same boundary here so direct deterministic and
    shadow callers cannot turn dimensions into catalog sections by fuzzy text
    similarity alone.

    Explicit supported section-family prefixes remain eligible, including
    damaged/wildcarded labels such as ``W??X?7`` and ``HSS8X8X?``.
    Mixed numbers (``1-1/2"``) and familyless ``…ANGLE`` fragments use the
    same boundary: they are not rolled-section reconstruction queries.
    """

    normalized = normalized or conservative_normalize(raw_text)
    if not normalized:
        return True
    if normalized.startswith("PIPE"):
        return False
    if starts_with_plate_head(normalized):
        return True
    if _WWR_MESH.match(normalized):
        return True
    if _quoted_l_leg_fields(normalized):
        return True
    fam = family_of(normalized)
    if fam in MODERN_FAMILY_CODES:
        return False
    for surface in _eligibility_surfaces(raw_text, normalized):
        if _familyless_dimension_surface(surface):
            return True
    return False


def _is_clean_numeric_field(field: str) -> bool:
    """True when a parsed field is empty, missing, all-wildcard, or clean numeric.

    Mixed wildcard/glue such as ``10?3/4`` or ``10*3/8`` is not a reliable
    numeric field: the wildcard destroyed an ``X`` boundary or digit slot,
    so positional field constraints must not be treated as trustworthy.
    """

    if not field or is_missing_field(field):
        return True
    if all(ch in WILDCARD_CHARS for ch in field):
        return True
    if any(ch in WILDCARD_CHARS for ch in field):
        return False
    return bool(_CLEAN_NUMERIC_FIELD.match(field))


def has_reliable_numeric_constraints(normalized: str) -> bool:
    """Known, undamaged numeric fields must not be relaxed by full-catalog fuzzy."""

    if is_missing_thickness_angle(normalized):
        return True
    parsed = parse_fields(normalized)
    if not parsed.ok or not parsed.fields:
        return False
    return _prefix_fields_are_reliable(parsed.fields)


_GRAMMAR_FIELD_ARITY = {
    "leg_leg_thickness": 3,
    "depth_weight": 2,
    "hss_rect": 3,
    "hss_round": 2,
    "pipe": 2,
}


def _is_printed_numeric_field(field: str) -> bool:
    """True for a fully printed numeric field (not missing, not wildcarded)."""

    return bool(field) and bool(_CLEAN_NUMERIC_FIELD.match(field))


def _prefix_fields_are_reliable(fields: List[str]) -> bool:
    constrained = [
        field
        for field in fields
        if field and not is_missing_field(field) and not all(ch in WILDCARD_CHARS for ch in field)
    ]
    if not constrained:
        return False
    return all(_is_clean_numeric_field(field) for field in fields)


def incomplete_angle_missing_thickness_parse(normalized: str) -> Optional[FieldParse]:
    """L/2L with two printed legs and no thickness: keep legs, do not invent wall.

    ``L6x3`` is not unconstrained fuzzy text. The printed 6x3 legs are
    reliable; thickness is unknown, same review class as ``HSS8X8``.
    """

    fam = family_of(normalized)
    if fam not in {"L", "2L"}:
        return None
    remainder = normalized[len(fam) :]
    parts = remainder.split("X")
    if len(parts) != 2:
        return None
    if not all(_is_printed_numeric_field(part) for part in parts):
        return None
    grammar = "leg_leg_thickness" if fam == "L" else "leg_leg_thickness_sep"
    return FieldParse(
        family=fam,
        grammar=grammar,
        fields=[parts[0], parts[1], MISSING_FIELD],
        ok=True,
    )


def is_missing_thickness_angle(normalized: str) -> bool:
    return incomplete_angle_missing_thickness_parse(normalized) is not None


def _grammar_arity(parsed: FieldParse) -> Optional[int]:
    if parsed.grammar == "leg_leg_thickness_sep":
        return 4 if len(parsed.fields) >= 4 else 3
    return _GRAMMAR_FIELD_ARITY.get(parsed.grammar)


def _structural_prefix_query(parsed: FieldParse) -> str:
    fields = list(parsed.fields)
    if fields and is_missing_field(fields[-1]):
        fields[-1] = "?"
    if parsed.family == "PIPE":
        return "PIPE" + "".join(fields)
    return parsed.family + "X".join(fields)


def reliable_acceptance_parse(normalized: str) -> Optional[FieldParse]:
    """Engineering fields the ranker must not override, or None if unconstrained.

    Clean parses reuse ``has_reliable_numeric_constraints``. Queries that fail
    ``parse_fields`` only because of a trailing extra field (cut length,
    quantity) still expose a reliable designation prefix -- e.g.
    ``L3X3X3/8X0'-6"`` keeps legs ``3``/``3`` and thickness ``3/8``.
    Incomplete L/2L callouts with two printed legs keep those legs; thickness
    stays missing so reconstruct can abstain instead of inventing a wall.
    Mixed wildcard/glue remains unconstrained so the ranker may reorder.
    """

    incomplete_angle = incomplete_angle_missing_thickness_parse(normalized)
    if incomplete_angle is not None:
        return incomplete_angle
    parsed = parse_fields(normalized)
    if parsed.ok and has_reliable_numeric_constraints(normalized):
        return parsed
    arity = _grammar_arity(parsed)
    if arity is None or not parsed.family or parsed.grammar == "unknown":
        return None
    if len(parsed.fields) <= arity:
        return None
    prefix = parsed.fields[:arity]
    if not all(prefix) or not _prefix_fields_are_reliable(prefix):
        return None
    return FieldParse(
        family=parsed.family,
        grammar=parsed.grammar,
        fields=prefix,
        ok=True,
    )


def reliable_exact_catalog_label(normalized: str) -> Optional[str]:
    """The single real catalog label ``normalized`` unambiguously names, even
    when a trailing non-designation field (cut length, quantity) keeps it
    from matching the catalog as a whole string -- e.g. ``L3X3X3/8X0'-6"``
    unambiguously names catalog label ``L3X3X3/8``.

    This is the canonical exact-label check for text with a reliable
    designation prefix. ``services.prediction.orchestrator``'s protected-
    exact-label fast path calls this (as a fallback after a direct
    ``catalog_valid_exact_section`` lookup on the untrimmed string) instead
    of maintaining its own, weaker copy of this logic -- see the cut-length
    bug this closes: printed text like ``L3X3X3/8X0'-6"`` was previously
    falling through to weighted fusion, which could let geometry/graph
    evidence silently override an explicit, unambiguous printed section.

    Returns ``None`` whenever the reliable prefix does not identify exactly
    one catalog row -- callers must never guess between multiple matches.
    """

    constraints = reliable_acceptance_parse(normalized)
    if constraints is None:
        return None
    matches = exact_catalog_labels_for_fields(
        constraints.family, constraints.grammar, constraints.fields
    )
    if len(matches) == 1:
        return matches[0]
    return None


def candidate_respects_reliable_query_fields(normalized: str, label: str) -> bool:
    """True when ``label`` does not contradict recoverable query fields.

    When no reliable constraints exist, every catalog-valid candidate is
    allowed (the ranker may reorder). Family, grammar, and
    ``generation_fields_compatible`` are the same checks generation already
    uses for mask/structural match.
    """

    constraints = reliable_acceptance_parse(normalized)
    if constraints is None:
        return True
    candidate = parse_fields(label)
    if not candidate.ok:
        return False
    if (
        candidate.family != constraints.family
        or candidate.grammar != constraints.grammar
    ):
        return False
    return generation_fields_compatible(constraints.fields, candidate.fields)


def is_missing_thickness_hss(normalized: str) -> bool:
    parsed = parse_fields(normalized)
    return (
        parsed.ok
        and parsed.grammar == "hss_rect"
        and len(parsed.fields) == 3
        and is_missing_field(parsed.fields[2])
    )


def _ocr_flex_candidates(normalized: str, *, limit: int) -> List[str]:
    """Same-length catalog labels reachable by only OCR-confusable swaps."""

    _ensure_loaded()
    pool = _BY_LENGTH.get(len(normalized), [])
    out: List[str] = []
    for label in pool:
        ok = True
        for a, b in zip(normalized, label):
            if a == b:
                continue
            if OCR_CONFUSION.get(a) == b:
                continue
            ok = False
            break
        if ok:
            out.append(label)
            if len(out) >= limit:
                break
    return out


def _fuzzy_candidates(normalized: str, *, limit: int, minimum_score: float = 0.55) -> List[str]:
    """Broad fallback net: character-similarity nearest neighbors across the
    FULL catalog. Catches deletions, added noise, separator corruption, and
    missing-prefix cases the positional strategies above don't cover.

    Previously scoped to only ``family_of(normalized)``'s catalog bucket,
    falling back to the full catalog solely when that bucket was empty.
    That silently misrouted results whenever ``family_of`` landed on ANY
    populated bucket key, right or wrong: a corruption that happens to
    start with a different real family code (e.g. a stray "B" or "W"
    prepended to a modern designation) searched that wrong family's small
    bucket instead of the true one; a handful of malformed catalog rows
    (e.g. "8X8", "8WF,CB82N" -- two designations concatenated by a comma)
    also seed spurious single-token "family" bucket keys that intercept
    unrelated queries whose alpha-only fallback heuristic happens to
    collide. Root-caused against the held-out test set: of 1,036
    candidate-generation misses, 828 (80%) were exactly this misrouting,
    not a case where the true label was genuinely unreachable by string
    similarity -- so this last-resort strategy now searches everything,
    as its own "broad fallback net" description already promised."""

    _ensure_loaded()
    pool = [label for label, _ in _CATALOG_ENTRIES]
    scored = []
    matcher = SequenceMatcher(None, normalized, "")
    for label in pool:
        matcher.set_seq2(label)
        if matcher.real_quick_ratio() < minimum_score:
            continue
        score = matcher.ratio()
        if score >= minimum_score:
            scored.append((score, label))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [label for _score, label in scored[:limit]]


def _family_only_candidates(normalized: str, *, limit: int) -> List[str]:
    """When the token is only a bare family prefix ('W', 'HSS') or a bare
    depth/weight fragment with no family, offer the most common members of
    the matching family (or all families if the family itself is unknown)."""

    _ensure_loaded()
    fam = family_of(normalized) if normalized.isalpha() else ""
    pool = _BY_FAMILY.get(fam, []) if fam else []
    return pool[:limit]


def _mask_label_structurally_compatible(normalized: str, label: str) -> bool:
    query_parse = parse_fields(normalized)
    candidate_parse = parse_fields(label)
    return (
        query_parse.ok
        and candidate_parse.ok
        and query_parse.family == candidate_parse.family
        and query_parse.grammar == candidate_parse.grammar
        and generation_fields_compatible(query_parse.fields, candidate_parse.fields)
    )


def _add_wildcard_mask_candidates(normalized, add, *, limit, ordered) -> None:
    """Add mask hits, but never let them bypass reliable numeric constraints."""

    remaining = limit - len(ordered)
    if remaining <= 0:
        return
    reliable = has_reliable_numeric_constraints(normalized)
    # Fetch past ``remaining`` so filtering incompatible mask hits cannot
    # starve the allowed set down to whatever happened to sort first.
    for candidate in match_wildcard_mask(normalized, limit=max(remaining, 25)):
        if len(ordered) >= limit:
            return
        if reliable and not _mask_label_structurally_compatible(
            normalized, candidate.label
        ):
            continue
        add(candidate.label, "wildcard_mask")


@dataclass
class CandidateSet:
    normalized: str
    family: str
    candidates: List[str]
    generation_reasons: Dict[str, List[str]]
    fuzzy_ranks: Dict[str, int] = field(default_factory=dict)


def generate_candidates(raw_text: str, *, limit: int = 25) -> CandidateSet:
    """Union of every deterministic strategy, deduplicated, catalog-valid."""

    _ensure_loaded()
    normalized = conservative_normalize(raw_text)
    fam = family_of(normalized)
    reasons: Dict[str, List[str]] = {}
    ordered: List[str] = []
    seen: Set[str] = set()

    def _add(label: str, reason: str) -> None:
        if label not in _CATALOG_LABELS or label in seen:
            return
        if fam in MODERN_FAMILY_CODES and family_of(label) != fam:
            return
        seen.add(label)
        ordered.append(label)
        reasons.setdefault(label, []).append(reason)

    if ineligible_for_section_reconstruction(raw_text, normalized):
        return CandidateSet(
            normalized=normalized,
            family=fam,
            candidates=[],
            generation_reasons={},
        )

    if is_catalog_label(normalized):
        _add(normalized, "exact_match")

    if normalized and len(ordered) < limit:
        for label in generation_compatible_catalog_labels(normalized)[
            : limit - len(ordered)
        ]:
            _add(label, "structural_field_match")

    prefix_parse = reliable_acceptance_parse(normalized)
    if prefix_parse is not None and prefix_parse.fields and len(ordered) < limit:
        prefix_query = _structural_prefix_query(prefix_parse)
        for label in generation_compatible_catalog_labels(prefix_query)[
            : limit - len(ordered)
        ]:
            _add(label, "structural_field_match")

    if has_wildcards(normalized) and len(ordered) < limit:
        _add_wildcard_mask_candidates(normalized, _add, limit=limit, ordered=ordered)

    if not has_wildcards(normalized) and normalized and len(ordered) < limit:
        for label in _ocr_flex_candidates(normalized, limit=limit):
            _add(label, "ocr_flex_positional")

    if (
        not is_missing_thickness_angle(normalized)
        and normalized
        and len(ordered) < limit
    ):
        for label in _family_only_candidates(normalized, limit=limit - len(ordered)):
            _add(label, "family_only")

    allow_fuzzy = not has_reliable_numeric_constraints(normalized)
    if allow_fuzzy and normalized and len(ordered) < limit:
        for label in _fuzzy_candidates(normalized, limit=limit - len(ordered)):
            _add(label, "fuzzy_nearest_neighbor")

    return CandidateSet(
        normalized=normalized,
        family=fam,
        candidates=ordered[:limit],
        generation_reasons={k: v for k, v in reasons.items() if k in ordered[:limit]},
    )


def generate_candidates_v3(raw_text: str, *, limit: int = 25) -> CandidateSet:
    """v3 generator (Part 3/4): adds a family/field-aware structural-match
    strategy ahead of whole-string fuzzy similarity. This is what fixes the
    ``HSS8X8X?`` -> ``HSS18X18X1`` bug -- ``structural_field_match`` requires
    depth AND width to match exactly (only a fully-wildcarded thickness
    field is treated as unconstrained, see
    ``structural_parser.field_generation_compatible``), so a completely
    different HSS size can never rank ahead of the real HSS8X8Xn family
    members. Priority order: exact_match -> structural_field_match ->
    wildcard_mask (positional fallback for grammars the parser doesn't
    cover) -> ocr_flex_positional -> family_only -> fuzzy_nearest_neighbor
    (now a last resort, not the tiebreaker it was in v2)."""

    _ensure_loaded()
    normalized = conservative_normalize(raw_text)
    fam = family_of(normalized)
    reasons: Dict[str, List[str]] = {}
    ordered: List[str] = []
    seen: Set[str] = set()
    fuzzy_ranks: Dict[str, int] = {}

    def _add(label: str, reason: str) -> None:
        if label not in _CATALOG_LABELS or label in seen:
            return
        if fam in MODERN_FAMILY_CODES and family_of(label) != fam:
            return
        seen.add(label)
        ordered.append(label)
        reasons.setdefault(label, []).append(reason)

    if ineligible_for_section_reconstruction(raw_text, normalized):
        return CandidateSet(
            normalized=normalized,
            family=fam,
            candidates=[],
            generation_reasons={},
            fuzzy_ranks={},
        )

    if is_catalog_label(normalized):
        _add(normalized, "exact_match")

    if normalized and len(ordered) < limit:
        for label in generation_compatible_catalog_labels(normalized)[: limit - len(ordered)]:
            _add(label, "structural_field_match")

    prefix_parse = reliable_acceptance_parse(normalized)
    if prefix_parse is not None and prefix_parse.fields and len(ordered) < limit:
        prefix_query = _structural_prefix_query(prefix_parse)
        for label in generation_compatible_catalog_labels(prefix_query)[
            : limit - len(ordered)
        ]:
            _add(label, "structural_field_match")

    if has_wildcards(normalized) and len(ordered) < limit:
        _add_wildcard_mask_candidates(normalized, _add, limit=limit, ordered=ordered)

    if not has_wildcards(normalized) and normalized and len(ordered) < limit:
        for label in _ocr_flex_candidates(normalized, limit=limit - len(ordered)):
            _add(label, "ocr_flex_positional")

    if (
        not is_missing_thickness_angle(normalized)
        and normalized
        and len(ordered) < limit
    ):
        for label in _family_only_candidates(normalized, limit=limit - len(ordered)):
            _add(label, "family_only")

    allow_fuzzy = not has_reliable_numeric_constraints(normalized)
    if allow_fuzzy and normalized and len(ordered) < limit:
        # Fetch generously past `limit` so fuzzy_ranks reflects each
        # candidate's TRUE position within the fuzzy-only ordering, not a
        # position truncated by how much room was left in the overall list.
        fuzzy_pool = _fuzzy_candidates(normalized, limit=max(limit, 25))
        for fuzzy_position, label in enumerate(fuzzy_pool):
            fuzzy_ranks[label] = fuzzy_position
        for label in fuzzy_pool:
            if len(ordered) >= limit:
                break
            _add(label, "fuzzy_nearest_neighbor")

    kept = set(ordered[:limit])
    return CandidateSet(
        normalized=normalized,
        family=fam,
        candidates=ordered[:limit],
        generation_reasons={k: v for k, v in reasons.items() if k in kept},
        fuzzy_ranks={k: v for k, v in fuzzy_ranks.items() if k in kept},
    )
