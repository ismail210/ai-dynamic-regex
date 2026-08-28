"""Pair features for the learned candidate ranker.

Exactly one implementation of ``pair_features`` is used at BOTH training
time (``training/train_label_ranker.py``) and inference time
(``services.label_reconstruction.ranker``). This is deliberate: the single
most common way an offline ranker silently degrades in production is a
preprocessing/feature mismatch between training and serving. Sharing this
module removes that failure mode by construction rather than by discipline.

Every feature is a cheap, deterministic function of the (query, candidate)
string pair -- no external state, no catalog scan, no randomness -- so
scoring is fast enough for interactive use over the ~10-25 candidates the
deterministic generator (``services.label_reconstruction.candidates``)
already narrowed the field to. The ranker never sees the full catalog; it
only reorders what the deterministic, catalog-valid generator proposed.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from services.label_reconstruction.corruption import OCR_CONFUSION, family_of
from services.label_reconstruction.structural_parser import (
    fields_compatible,
    parse_fields,
)

# Must match the reason strings services.label_reconstruction.candidates
# actually emits (generate_candidates'/generate_candidates_v3's `_add(...,
# reason)` calls). Which deterministic strategy proposed a candidate is one
# of the single most informative signals available -- an exact_match
# candidate should almost always outrank a fuzzy_nearest_neighbor one -- so
# it is passed through as an explicit feature rather than left for the model
# to rediscover purely from string distance. "structural_field_match" is
# v3-only (see candidates.generate_candidates_v3); v2-sourced rows simply
# never set that flag, which is fine -- one-hots default to 0.
GENERATION_REASONS: List[str] = [
    "exact_match",
    "structural_field_match",
    "wildcard_mask",
    "ocr_flex_positional",
    "family_only",
    "fuzzy_nearest_neighbor",
]
_NO_RANK_SENTINEL = 25.0  # one past the largest candidate-list limit used anywhere
_NO_DIFF_SENTINEL = 999.0  # "fields not comparable" -- never a real numeric diff

FEATURE_NAMES: List[str] = [
    "query_len",
    "candidate_len",
    "len_diff_abs",
    "edit_distance",
    "edit_distance_norm",
    "ocr_aware_distance",
    "ocr_aware_distance_norm",
    "bigram_jaccard",
    "trigram_jaccard",
    "common_prefix_len",
    "common_suffix_len",
    "positional_match_count",
    "positional_match_ratio",
    "family_match",
    "query_family_known",
    "deterministic_rank",
    "fuzzy_rank",
    "is_structurally_compatible",
    "known_fields_matched",
    "known_fields_violated",
    "field0_diff_norm",
    "field1_diff_norm",
    "field2_diff_norm",
    "candidate_family_size_log1p",
    *[f"reason_{name}" for name in GENERATION_REASONS],
]


def _char_ngrams(text: str, n: int) -> set:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _edit_distance(a: str, b: str, *, ocr_aware: bool) -> float:
    if a == b:
        return 0.0
    prev = [float(j) for j in range(len(b) + 1)]
    for i, ca in enumerate(a, start=1):
        cur = [float(i)] + [0.0] * len(b)
        for j, cb in enumerate(b, start=1):
            if ca == cb:
                cost = 0.0
            elif ocr_aware and OCR_CONFUSION.get(ca) == cb:
                cost = 0.5
            else:
                cost = 1.0
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def _common_suffix_len(a: str, b: str) -> int:
    return _common_prefix_len(a[::-1], b[::-1])


def _parse_numeric(field: str) -> Optional[float]:
    """"18" -> 18.0, "48.5" -> 48.5, "3/8" -> 0.375, "1-1/2" -> 1.5. Returns
    None (never raises) for wildcarded or otherwise unparseable fields."""

    text = (field or "").strip()
    if not text or any(ch in "*?" for ch in text):
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


_FAMILY_SIZE_CACHE: Optional[Dict[str, int]] = None


def _family_size(family: str) -> int:
    global _FAMILY_SIZE_CACHE
    if _FAMILY_SIZE_CACHE is None:
        refresh_family_size_cache()
    return _FAMILY_SIZE_CACHE.get(family, 0)


def refresh_family_size_cache() -> Dict[str, int]:
    """Rebuild the family-size cache from the currently loaded catalog.

    Call after `services.database_loader.reload_from_pairs`/
    `reload_from_aisc_v16_catalog` in offline training/eval contexts -- this
    cache is otherwise built once (on first use) and never invalidated.
    """

    global _FAMILY_SIZE_CACHE
    from services.database_loader import catalog_entries

    counts: Dict[str, int] = {}
    for label, _type in catalog_entries():
        counts[family_of(label)] = counts.get(family_of(label), 0) + 1
    _FAMILY_SIZE_CACHE = counts
    return _FAMILY_SIZE_CACHE


def _structural_diff_features(query: str, candidate: str) -> Dict[str, float]:
    """Field-level structural comparison (Part 3/4/8): generic
    ``field{i}_diff_norm`` slots cover every grammar's numeric fields --
    for depth_weight families field0=depth, field1=weight; for HSS-rect
    field0=depth, field1=width, field2=thickness; for HSS-round
    field0=diameter, field1=thickness; for L/2L field0/1=legs,
    field2=thickness. This is what lets the model penalize e.g. a
    candidate whose depth is numerically far from the query's observed
    depth, distinct from (and stronger than) whole-string character
    similarity."""

    q_parse = parse_fields(query)
    c_parse = parse_fields(candidate)
    out = {
        "is_structurally_compatible": 0.0,
        "known_fields_matched": 0.0,
        "known_fields_violated": 0.0,
        "field0_diff_norm": _NO_DIFF_SENTINEL,
        "field1_diff_norm": _NO_DIFF_SENTINEL,
        "field2_diff_norm": _NO_DIFF_SENTINEL,
    }
    if not q_parse.ok or not c_parse.ok:
        return out
    if q_parse.grammar != c_parse.grammar or q_parse.family != c_parse.family:
        return out
    if len(q_parse.fields) != len(c_parse.fields):
        return out

    out["is_structurally_compatible"] = 1.0 if fields_compatible(q_parse.fields, c_parse.fields) else 0.0
    matched = 0
    violated = 0
    for index, (qf, cf) in enumerate(zip(q_parse.fields, c_parse.fields)):
        has_wildcard = any(ch in "*?" for ch in qf)
        if not has_wildcard:
            if qf == cf:
                matched += 1
            else:
                violated += 1
        if index < 3:
            q_num = _parse_numeric(qf)
            c_num = _parse_numeric(cf)
            if q_num is not None and c_num is not None:
                out[f"field{index}_diff_norm"] = abs(q_num - c_num) / (1.0 + abs(c_num))
    out["known_fields_matched"] = float(matched)
    out["known_fields_violated"] = float(violated)
    return out


def _log1p(x: float) -> float:
    import math

    return math.log1p(max(0.0, x))


def pair_features(
    query: str,
    candidate: str,
    *,
    rank: Optional[int] = None,
    reasons: Optional[Sequence[str]] = None,
    fuzzy_rank: Optional[int] = None,
) -> Dict[str, float]:
    """Deterministic (query, candidate) -> feature dict. Both strings are
    expected to already be conservatively normalized (upper-case, no
    whitespace) by the caller -- this function does not normalize.

    ``rank``, ``reasons`` and ``fuzzy_rank`` describe this candidate's
    position/provenance in the deterministic generator's output for this
    query (see ``services.label_reconstruction.candidates.generate_candidates_v3``).
    Callers that don't have this context (e.g. ad-hoc string-pair scoring)
    may omit them; they fall back to "unknown" sentinel values."""

    q, c = query, candidate
    max_len = max(len(q), len(c), 1)
    edit = _edit_distance(q, c, ocr_aware=False)
    ocr_edit = _edit_distance(q, c, ocr_aware=True)
    positional_matches = sum(1 for a, b in zip(q, c) if a == b)
    q_family = family_of(q)
    reason_set = set(reasons or [])

    row = {
        "query_len": float(len(q)),
        "candidate_len": float(len(c)),
        "len_diff_abs": float(abs(len(q) - len(c))),
        "edit_distance": edit,
        "edit_distance_norm": edit / max_len,
        "ocr_aware_distance": ocr_edit,
        "ocr_aware_distance_norm": ocr_edit / max_len,
        "bigram_jaccard": _jaccard(_char_ngrams(q, 2), _char_ngrams(c, 2)),
        "trigram_jaccard": _jaccard(_char_ngrams(q, 3), _char_ngrams(c, 3)),
        "common_prefix_len": float(_common_prefix_len(q, c)),
        "common_suffix_len": float(_common_suffix_len(q, c)),
        "positional_match_count": float(positional_matches),
        "positional_match_ratio": positional_matches / max_len,
        "family_match": 1.0 if q_family and c.startswith(q_family) else 0.0,
        "query_family_known": 1.0 if q_family else 0.0,
        "deterministic_rank": float(rank) if rank is not None else _NO_RANK_SENTINEL,
        "fuzzy_rank": float(fuzzy_rank) if fuzzy_rank is not None else _NO_RANK_SENTINEL,
        "candidate_family_size_log1p": _log1p(_family_size(family_of(c))),
    }
    row.update(_structural_diff_features(q, c))
    for name in GENERATION_REASONS:
        row[f"reason_{name}"] = 1.0 if name in reason_set else 0.0
    # FEATURE_NAMES is the canonical schema order for train, serve, and the
    # production-aligned validator. Insertion order of the dict above must
    # not drift from that list.
    return {name: row[name] for name in FEATURE_NAMES}


def features_from_candidate_set(candidate: str, candidate_set) -> Dict[str, float]:
    """Build one candidate's feature row from a ``CandidateSet`` (as returned
    by ``services.label_reconstruction.candidates.generate_candidates_v3``)
    -- the single source of truth for this candidate's ``rank`` (position in
    the generator's output), ``reasons`` (which deterministic strategy
    proposed it), and ``fuzzy_rank``.

    Training and evaluation/inference must both go through this function
    rather than calling ``pair_features`` directly with ad-hoc
    rank/reasons/fuzzy_rank -- that split is exactly how training and
    serving previously diverged: ``train_ranker`` fit on
    ``reasons=None, fuzzy_rank=None`` for every single row (so those columns
    were constant/sentinel throughout training and the trees never learned
    to use them), while evaluation passed the real, varying values from a
    live ``generate_candidates_v3`` call -- feature values the model had
    never seen vary. Routing both through one function makes that
    divergence impossible to reintroduce by omission."""

    candidates = candidate_set.candidates
    rank = candidates.index(candidate) if candidate in candidates else None
    return pair_features(
        candidate_set.normalized,
        candidate,
        rank=rank,
        reasons=candidate_set.generation_reasons.get(candidate),
        fuzzy_rank=candidate_set.fuzzy_ranks.get(candidate),
    )


def feature_vector(
    query: str,
    candidate: str,
    *,
    rank: Optional[int] = None,
    reasons: Optional[Sequence[str]] = None,
    fuzzy_rank: Optional[int] = None,
) -> List[float]:
    row = pair_features(query, candidate, rank=rank, reasons=reasons, fuzzy_rank=fuzzy_rank)
    return [row[name] for name in FEATURE_NAMES]
