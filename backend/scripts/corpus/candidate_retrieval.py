"""Section 18 -- candidate retrieval audit.

The v1 repair benchmark found the current production repair path gets 0%
top-1 on deletion/insertion corruption. Before blaming the *ranker*, this
module answers a narrower question: does the correct target even enter the
candidate POOL for these corruption classes, from ANY retrieval method?

Retrieval must not implicitly assume the corrupted string is the same length
as its target -- RapidFuzz's ``fuzz.ratio``, plain Levenshtein distance, and
char-ngram TF-IDF cosine similarity all naturally compare strings of
different lengths, so none of the three methods below has a length
restriction baked in. This module unions their outputs so we can tell
"target never retrieved" (a real retrieval-recall gap) apart from "target
retrieved but ranked low" (a ranking problem for Model B to solve).
"""
from __future__ import annotations

from typing import Optional

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein


def retrieve_rapidfuzz(query: str, pool: list[str], limit: int) -> list[str]:
    if not pool:
        return []
    matches = process.extract(query, pool, scorer=fuzz.ratio, limit=limit)
    return [m[0] for m in matches]


def retrieve_levenshtein(query: str, pool: list[str], limit: int) -> list[str]:
    """Plain edit distance, ascending -- a different signal than RapidFuzz's
    normalized ratio, deliberately included as its own method per Section 18
    ("weighted edit distance") rather than treated as a duplicate of
    RapidFuzz's ratio scorer."""
    if not pool:
        return []
    scored = sorted(pool, key=lambda cand: Levenshtein.distance(query, cand))
    return scored[:limit]


def retrieve_tfidf(query: str, pool: list[str], limit: int, tfidf_fn) -> list[str]:
    """``tfidf_fn`` is the repo's existing char-ngram TF-IDF retriever
    (``predict_exact_sections``), which searches the FULL AISC catalog, not
    just this pilot's family pool -- filter its output down to the
    family-scoped pool so results are comparable to the other two methods."""
    pool_set = set(pool)
    candidates = tfidf_fn(query, limit=max(limit * 4, 50))
    ranked = [c.shape for c in candidates if c.shape in pool_set]
    return ranked[:limit]


def union_retrieve(query: str, pool: list[str], limit: int, tfidf_fn) -> dict[str, list[str]]:
    return {
        "rapidfuzz": retrieve_rapidfuzz(query, pool, limit),
        "levenshtein": retrieve_levenshtein(query, pool, limit),
        "tfidf": retrieve_tfidf(query, pool, limit, tfidf_fn),
    }


def recall_at_k(target: str, per_method: dict[str, list[str]], k: int) -> dict[str, bool]:
    out = {}
    union_topk: set[str] = set()
    for name, ranked in per_method.items():
        topk = ranked[:k]
        out[name] = target in topk
        union_topk.update(topk)
    out["union"] = target in union_topk
    return out
