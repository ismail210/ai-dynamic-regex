"""Shadow-mode bridge from the semantic pipeline to the stronger
``services.label_reconstruction`` candidate/ranking engine (repair-trace
sprint, Section 5/23).

Why this exists: ``services.semantic_preprocessor.normalization._try_repair``
is a deliberately minimal, single-character-confusion-only repair layer (see
its own docstring). It never attempts deletion, insertion, or multi-error
recovery, and it never checks whether a grammar-valid-looking label (e.g.
``W12X2`` after a deleted digit) is actually a REAL catalog member -- it only
runs at all when the text fails to parse as structural in the first place.
``services.label_reconstruction`` already has a full deterministic
candidate generator (``candidates.generate_candidates``) plus a promoted,
trained XGBRanker (``ranker.get_active_ranker``) that handles all of this.
This module wires that engine in for annotations the deterministic layer
left unresolved -- in SHADOW MODE: it only ever appends an UNACCEPTED
``OperationRecord`` (``accepted=False``), so ``effective_text`` (the value
every other consumer reads) never changes until a human explicitly accepts
one via ``services.semantic_document_service.apply_review_action``.

Never touches an annotation that is already an exact catalog match (the
0/962 clean-control false-change property from the PDF attack benchmark
depends on this staying true) or a bare-incomplete label (that is a
COMPLETION concern, not a repair one -- see ``drawing_language_profile.py``).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from os import cpu_count
from typing import Dict, List, Optional

from services.label_reconstruction.candidates import (
    conservative_normalize,
    ineligible_for_section_reconstruction,
)
from services.family_codes import MODERN_FAMILY_CODES
from services.label_reconstruction.corruption import family_of
from services.label_reconstruction.ranker import get_active_ranker
from services.label_reconstruction.shadow import reconstruct
from services.semantic.models import (
    CATALOG_EXACT_MATCH,
    EvidenceRecord,
    EvidenceStrength,
    EvidenceType,
    OperationKind,
    OperationRecord,
    RepairCandidate,
    ReviewStatus,
    SCORE_RAW_MODEL,
    SCORE_SIMILARITY,
    ScoreValue,
    SemanticAnnotation,
    SemanticDocument,
)

MAX_CANDIDATES_ATTACHED = 5
# Parallel reconstruct() calls — Burrville-scale docs evaluate ~2–3k labels;
# sequential shadow was ~225s wall time on one profiled run.
_SHADOW_WORKERS = max(4, min(8, (cpu_count() or 4)))

_GENERATION_REASON_LABELS: Dict[str, str] = {
    "exact_match": "Exact catalog match",
    "structural_field_match": "Structural fields (depth/weight/thickness) compatible",
    "ocr_flex_positional": "Reachable by a single OCR-confusable character swap",
    "wildcard_mask": "Matches the wildcard-masked query",
    "family_only": "Same family; no other constraint recoverable",
    "fuzzy_nearest_neighbor": "Nearest catalog entry by character similarity",
    "fuzzy_fallback_broadened": (
        "Broadened fallback: numeric fields looked complete, so the standard "
        "generator found no exact catalog match and abstained; this is a "
        "similarity-based suggestion, not a deterministic-strategy match"
    ),
}


def needs_repair_shadow(annotation: SemanticAnnotation) -> bool:
    """True when the deterministic layer left this annotation unresolved in
    a way the stronger engine might help with.

    Excludes: no structural parse at all yet, an already-exact catalog
    match (Section 24 -- never run the ranker over a clean label), a
    bare-incomplete label (``grammar == "incomplete"``, a COMPLETION
    concern), and anything ``label_reconstruction``'s OWN eligibility
    boundary (``ineligible_for_section_reconstruction``) already excludes --
    dates, general notes, plain dimensions, WWR mesh callouts, and other
    text that was never a structural-section callout in the first place.

    Found necessary empirically: on a real 4,900-annotation drawing, the
    semantic_preprocessor parser's ``is_structural=False`` fires for almost
    ANY unparseable text (a date like "1/22/2026" included), not just
    corrupted section labels -- without this boundary, the repair engine
    ran ~4,600 times per document and produced nonsense angle-iron
    candidates for a revision date.
    """
    parse = annotation.structural_parse
    if parse is None:
        return False
    if parse.catalog_status == CATALOG_EXACT_MATCH:
        return False
    if parse.grammar == "incomplete":
        return False
    text = annotation.primary_label or annotation.original_text or ""
    if not text:
        return False
    normalized = conservative_normalize(text)
    if ineligible_for_section_reconstruction(text, normalized):
        return False
    if family_of(normalized) not in MODERN_FAMILY_CODES and "X" not in normalized:
        return False
    return True


def _score_from_ranked_pairs(
    candidate_text: str,
    query: str,
    ranked_pairs: Optional[List[tuple]],
    model_version: Optional[str],
    is_fallback_broadened: bool,
) -> List[ScoreValue]:
    if ranked_pairs:
        for label, value in ranked_pairs:
            if label == candidate_text:
                return [ScoreValue(
                    value=float(value),
                    kind=SCORE_RAW_MODEL,
                    calibrated=False,
                    model_name="label_reconstruction_ranker",
                    model_version=model_version,
                )]
        return []
    if is_fallback_broadened:
        from difflib import SequenceMatcher

        ratio = SequenceMatcher(None, conservative_normalize(query), candidate_text).ratio()
        return [ScoreValue(value=round(ratio, 4), kind=SCORE_SIMILARITY, calibrated=False)]
    return []


def _evidence_notes(query: str, candidate_text: str, reasons: List[str]) -> List[str]:
    notes = [_GENERATION_REASON_LABELS[r] for r in reasons if r in _GENERATION_REASON_LABELS]
    if query == candidate_text:
        return notes
    if len(query) == len(candidate_text):
        diffs = [(i, a, b) for i, (a, b) in enumerate(zip(query, candidate_text)) if a != b]
        if len(diffs) == 1:
            i, a, b = diffs[0]
            notes.append(f"Single-character difference at position {i}: {a!r} -> {b!r}")
        elif diffs:
            notes.append(f"{len(diffs)} character positions differ")
    else:
        notes.append(f"Length differs: query has {len(query)} characters, candidate has {len(candidate_text)}")
    return notes


def _build_candidate(
    rank: int,
    candidate_text: str,
    query: str,
    family: Optional[str],
    reasons: List[str],
    ranked_pairs: Optional[List[tuple]],
    model_version: Optional[str],
    source: str,
    is_fallback_broadened: bool,
) -> RepairCandidate:
    scores = _score_from_ranked_pairs(candidate_text, query, ranked_pairs, model_version, is_fallback_broadened)
    notes = _evidence_notes(query, candidate_text, reasons)
    evidence = [
        EvidenceRecord(
            evidence_id=f"repair_candidate:{candidate_text}:{i}",
            evidence_type=EvidenceType.REPAIR_CANDIDATE,
            source=source,
            strength=EvidenceStrength.INFERRED,
            reference=candidate_text,
            notes=note,
        )
        for i, note in enumerate(notes)
    ]
    return RepairCandidate(
        candidate_text=candidate_text,
        rank=rank,
        family=family,
        catalog_valid=True,
        scores=scores,
        evidence=evidence,
        reason_codes=list(reasons),
        source=source,
        model_version=model_version,
    )


@dataclass
class RepairShadowSummary:
    evaluated: int = 0
    candidates_found: int = 0
    no_candidates: int = 0
    already_clean_skipped: int = 0


@dataclass
class _ShadowResult:
    annotation_id: str
    candidates: List[RepairCandidate]
    candidate_source: str
    query: str
    top: Optional[RepairCandidate]
    model_version: Optional[str]
    is_broadened: bool


def _evaluate_shadow_annotation(
    annotation: SemanticAnnotation,
    model_version: Optional[str],
) -> Optional[_ShadowResult]:
    """Pure per-annotation reconstruct work (safe to run on a worker thread)."""
    query = annotation.primary_label or annotation.original_text
    if not query:
        return None
    result = reconstruct(query, force_shadow_score=True)
    family = annotation.structural_parse.family if annotation.structural_parse else None
    is_broadened = result.is_fallback_broadened
    candidate_source = (
        "label_reconstruction_broadened_ranker" if (is_broadened and result.ranked_pairs) else
        "label_reconstruction_broadened_similarity" if is_broadened else
        "label_reconstruction_ranker" if result.ranked_pairs else
        "label_reconstruction_deterministic"
    )
    candidates: List[RepairCandidate] = [
        _build_candidate(
            rank=i + 1,
            candidate_text=label,
            query=query,
            family=family,
            reasons=result.generation_reasons.get(label, []),
            ranked_pairs=result.ranked_pairs,
            model_version=model_version,
            source=candidate_source,
            is_fallback_broadened=is_broadened,
        )
        for i, label in enumerate(result.candidate_labels[:MAX_CANDIDATES_ATTACHED])
    ]
    if result.ranked_pairs:
        order = {label: i for i, (label, _score) in enumerate(result.ranked_pairs)}
        candidates.sort(key=lambda c: order.get(c.candidate_text, len(order)))
        for i, c in enumerate(candidates):
            c.rank = i + 1
    elif is_broadened:
        candidates.sort(key=lambda c: -(c.scores[0].value if c.scores else 0.0))
        for i, c in enumerate(candidates):
            c.rank = i + 1
    return _ShadowResult(
        annotation_id=annotation.annotation_id,
        candidates=candidates,
        candidate_source=candidate_source,
        query=query,
        top=(candidates[0] if candidates else None),
        model_version=model_version,
        is_broadened=is_broadened,
    )


def attach_repair_shadow(document: SemanticDocument) -> RepairShadowSummary:
    """Mutates ``document.annotations`` in place: attaches
    ``repair_candidates`` and an unaccepted REPAIR proposal operation to
    every annotation ``needs_repair_shadow`` selects. Never changes
    ``effective_text`` by itself (Section 2: shadow/proposal mode only).
    """
    summary = RepairShadowSummary()
    ranker = get_active_ranker()
    model_version = ranker.version_id if ranker is not None else None

    targets: List[SemanticAnnotation] = []
    for annotation in document.annotations:
        if not needs_repair_shadow(annotation):
            summary.already_clean_skipped += 1
            continue
        targets.append(annotation)

    if not targets:
        return summary

    by_id = {a.annotation_id: a for a in targets}

    with ThreadPoolExecutor(max_workers=_SHADOW_WORKERS) as pool:
        results = list(pool.map(
            lambda ann: _evaluate_shadow_annotation(ann, model_version),
            targets,
        ))

    for shadow in results:
        if shadow is None:
            continue
        annotation = by_id.get(shadow.annotation_id)
        if annotation is None:
            continue
        summary.evaluated += 1
        annotation.repair_candidates = shadow.candidates
        if shadow.top is not None:
            summary.candidates_found += 1
            top = shadow.top
            annotation.operations.append(OperationRecord(
                operation=OperationKind.REPAIR,
                input_text=shadow.query,
                output_text=top.candidate_text,
                reason_codes=list(top.reason_codes) + ["label_reconstruction_shadow_proposal"],
                evidence=list(top.evidence),
                score=(top.scores[0] if top.scores else None),
                deterministic=(shadow.model_version is None and not shadow.is_broadened),
                semantic_information_added=False,
                provenance=top.source,
                accepted=False,
            ))
            annotation.review.status = ReviewStatus.NEEDS_REVIEW
            if not annotation.review.reason:
                annotation.review.reason = (
                    "ambiguous_low_confidence_candidates"
                    if shadow.candidate_source == "label_reconstruction_broadened_similarity"
                    else "repair_candidate_available"
                )
        else:
            summary.no_candidates += 1
            annotation.review.status = ReviewStatus.NEEDS_REVIEW
            if not annotation.review.reason:
                annotation.review.reason = "no_repair_candidates_found"

    return summary
