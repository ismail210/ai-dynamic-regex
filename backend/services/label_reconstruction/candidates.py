"""Deterministic AISC candidate generation for damaged label text.

This is the validity gate: every candidate returned here is a real row from
``services.database_loader.catalog_entries()``. Nothing downstream (baseline
scorers or the learned ranker) is allowed to invent a label -- they only
reorder what this module produces.

Pipeline stage: normalization -> family/partial-pattern extraction ->
candidate generation. See ``services.label_reconstruction`` docstring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set

from services.database_loader import catalog_entries, is_catalog_label
from services.label_reconstruction.corruption import OCR_CONFUSION, family_of
from services.label_reconstruction.structural_parser import generation_compatible_catalog_labels
from services.wildcard_matcher import has_wildcards, match_wildcard_mask

_CATALOG_ENTRIES = None  # lazy cache: List[(normalized_label, type)]
_CATALOG_LABELS: Set[str] = set()
_BY_LENGTH: Dict[int, List[str]] = {}
_BY_FAMILY: Dict[str, List[str]] = {}


def _ensure_loaded() -> None:
    global _CATALOG_ENTRIES
    if _CATALOG_ENTRIES is not None:
        return
    entries = catalog_entries()
    _CATALOG_ENTRIES = entries
    for label, _type in entries:
        _CATALOG_LABELS.add(label)
        _BY_LENGTH.setdefault(len(label), []).append(label)
        _BY_FAMILY.setdefault(family_of(label), []).append(label)


def conservative_normalize(raw: str) -> str:
    """Whitespace/case/multiply-sign normalization only -- never guesses
    digits. Mirrors the normalization already applied by the production
    extraction path so the benchmark reflects what inference will see."""

    text = str(raw or "").strip().upper()
    text = text.replace("×", "X").replace("-X", "X")
    text = "".join(text.split())
    # Strip a single layer of parenthesis/noise wrapping, but keep interior
    # wildcard/unknown markers untouched.
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return text


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
    """Broad fallback net: character-similarity nearest neighbors, family
    biased. Catches deletions, added noise, separator corruption, and
    missing-prefix cases the positional strategies above don't cover."""

    _ensure_loaded()
    fam = family_of(normalized)
    pool = _BY_FAMILY.get(fam) if fam else None
    pool = pool or [label for label, _ in _CATALOG_ENTRIES]
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
        seen.add(label)
        ordered.append(label)
        reasons.setdefault(label, []).append(reason)

    if is_catalog_label(normalized):
        _add(normalized, "exact_match")

    if has_wildcards(normalized):
        for candidate in match_wildcard_mask(normalized, limit=limit):
            _add(candidate.label, "wildcard_mask")

    if not has_wildcards(normalized) and normalized:
        for label in _ocr_flex_candidates(normalized, limit=limit):
            _add(label, "ocr_flex_positional")

    if normalized and len(ordered) < limit:
        for label in _family_only_candidates(normalized, limit=limit - len(ordered)):
            _add(label, "family_only")

    if normalized and len(ordered) < limit:
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
        seen.add(label)
        ordered.append(label)
        reasons.setdefault(label, []).append(reason)

    if is_catalog_label(normalized):
        _add(normalized, "exact_match")

    if normalized and len(ordered) < limit:
        for label in generation_compatible_catalog_labels(normalized)[: limit - len(ordered)]:
            _add(label, "structural_field_match")

    if has_wildcards(normalized) and len(ordered) < limit:
        for candidate in match_wildcard_mask(normalized, limit=limit - len(ordered)):
            _add(candidate.label, "wildcard_mask")

    if not has_wildcards(normalized) and normalized and len(ordered) < limit:
        for label in _ocr_flex_candidates(normalized, limit=limit - len(ordered)):
            _add(label, "ocr_flex_positional")

    if normalized and len(ordered) < limit:
        for label in _family_only_candidates(normalized, limit=limit - len(ordered)):
            _add(label, "family_only")

    if normalized and len(ordered) < limit:
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
