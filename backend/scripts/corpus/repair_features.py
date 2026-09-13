"""Section 21/22 -- shared feature engineering for Model A and Model B.

Kept as its own module (not inlined in the training script) so
``test_repair_policy_v2.py`` can import the exact same functions used at
train time -- avoiding train/serve feature drift.
"""
from __future__ import annotations

from typing import Optional

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from services.structural_parser import parse_fields, parse_section
from services.semantic_preprocessor.normalization import canonicalize

_CONFUSABLE_CHARS = set("IOSBLGZ")


def has_confusable_char(text: str) -> bool:
    """True if a letter commonly OCR-confused with a digit (I/O/S/B/L/G/Z)
    appears anywhere after the family prefix -- a WEAK signal, not proof of
    corruption (Section 10: presence alone must not imply "wrong")."""
    parsed = parse_section(text)
    fam = parsed.family if parsed else ""
    tail = text[len(fam):] if fam and text.startswith(fam) else text
    return any(ch in _CONFUSABLE_CHARS for ch in tail)


def char_bigram_jaccard(a: str, b: str) -> float:
    def bigrams(s: str) -> set:
        return {s[i:i + 2] for i in range(len(s) - 1)} or {s}

    ba, bb = bigrams(a), bigrams(b)
    inter = len(ba & bb)
    union = len(ba | bb)
    return inter / union if union else 0.0


def annotation_features(text: str, pool: list[str]) -> dict:
    """Model A features -- describe the ANNOTATION ITSELF, no specific
    candidate yet. ``pool`` is the family-scoped catalog list (empty if
    family unknown)."""
    parsed = parse_section(text)
    canon = canonicalize(text).correction
    fields = parse_fields(text)

    scored = sorted(
        ((c, fuzz.ratio(text, c)) for c in pool),
        key=lambda t: -t[1],
    )
    top_scores = [s for _, s in scored[:5]]
    top1 = top_scores[0] if top_scores else 0.0
    top2 = top_scores[1] if len(top_scores) > 1 else 0.0
    close_candidates = sum(1 for _, s in scored if s >= 90.0)

    return {
        "catalog_valid": bool(parsed and parsed.catalog_valid),
        "family_known": bool(parsed and parsed.family),
        "fields_ok": bool(fields.ok),
        "canonicalize_changed": bool(canon.canonical and canon.canonical != text),
        "canonicalize_is_none": not canon.canonical,
        "length": len(text),
        "has_confusable_char": has_confusable_char(text),
        "has_whitespace": " " in text.strip(),
        "top1_score": top1 / 100.0,
        "top1_top2_margin": (top1 - top2) / 100.0,
        "num_close_candidates": close_candidates,
        "pool_size": len(pool),
    }


FEATURE_ORDER_A = [
    "catalog_valid", "family_known", "fields_ok", "canonicalize_changed",
    "canonicalize_is_none", "length", "has_confusable_char", "has_whitespace",
    "top1_score", "top1_top2_margin", "num_close_candidates", "pool_size",
]


def featurize_a(feat: dict) -> list[float]:
    return [float(feat[k]) for k in FEATURE_ORDER_A]


def pair_features(query: str, candidate: str, *, doc_freq: int = 0) -> dict:
    """Model B features -- describe a (query, candidate) PAIR."""
    qf = parse_fields(query)
    cf = parse_fields(candidate)
    ratio = fuzz.ratio(query, candidate) / 100.0
    lev = Levenshtein.distance(query, candidate)
    norm_lev = 1.0 - lev / max(len(query), len(candidate), 1)
    prefix_len = 0
    for a, b in zip(query, candidate):
        if a != b:
            break
        prefix_len += 1
    suffix_len = 0
    for a, b in zip(reversed(query), reversed(candidate)):
        if a != b:
            break
        suffix_len += 1

    round_vs_rect_compatible = 1.0
    if cf.family == "HSS" and qf.family == "HSS":
        round_vs_rect_compatible = float(qf.grammar == cf.grammar) if qf.ok else 0.5

    return {
        "rapidfuzz_ratio": ratio,
        "levenshtein_distance": float(lev),
        "normalized_levenshtein": norm_lev,
        "char_bigram_jaccard": char_bigram_jaccard(query, candidate),
        "length_delta": float(abs(len(query) - len(candidate))),
        "prefix_match_len": float(prefix_len),
        "suffix_match_len": float(suffix_len),
        "family_match": float(qf.family == cf.family),
        "field_count_match": float(len(qf.fields) == len(cf.fields)),
        "candidate_field_ok": float(cf.ok),
        "round_vs_rect_compatible": round_vs_rect_compatible,
        "doc_frequency": float(doc_freq),
    }


FEATURE_ORDER_B = [
    "rapidfuzz_ratio", "levenshtein_distance", "normalized_levenshtein",
    "char_bigram_jaccard", "length_delta", "prefix_match_len", "suffix_match_len",
    "family_match", "field_count_match", "candidate_field_ok",
    "round_vs_rect_compatible", "doc_frequency",
]
FEATURE_ORDER_B_NO_CONTEXT = [f for f in FEATURE_ORDER_B if f != "doc_frequency"]


def featurize_b(feat: dict, *, with_context: bool = True) -> list[float]:
    order = FEATURE_ORDER_B if with_context else FEATURE_ORDER_B_NO_CONTEXT
    return [float(feat[k]) for k in order]


def deterministic_keep(text: str) -> bool:
    """Section 20 -- hard safety short-circuit. A catalog-exact clean label
    is KEPT unconditionally, before any ML runs. No ranker score, however
    confident, can override this."""
    parsed = parse_section(text)
    if not parsed or not parsed.catalog_valid:
        return False
    canon = canonicalize(text).correction
    return bool(canon.canonical == text or canon.canonical == parsed.normalized)
