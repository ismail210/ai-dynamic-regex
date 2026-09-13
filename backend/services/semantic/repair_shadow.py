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

from dataclasses import dataclass
from typing import Dict, List, Optional

from services.label_reconstruction.candidates import (
    _fuzzy_candidates,
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

_GENERATION_REASON_LABELS: Dict[str, str] = {
    "exact_match": "Exact catalog match",
    "structural_field_match": "Structural fields (depth/weight/thickness) compatible",
    "ocr_flex_positional": "Reachable by a single OCR-confusable character swap",
    "wildcard_mask": "Matches the wildcard-masked query",
    "family_only": "Same family; no other constraint recoverable",
    "fuzzy_nearest_neighbor": "Nearest catalog entry by character similarity",
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
    # Second, narrower guard: real designations either start with a
    # recognized family prefix OR contain an "X" field separator (every
    # grammar this catalog covers -- WxD, HSSxAxBxT, LxAxBxT, PLxTxW,
    # BPxLxWxT -- uses one, PIPE aside, which is covered by the prefix
    # check). Load/unit callouts like "35K" (kips) have neither and pass
    # `ineligible_for_section_reconstruction` unfiltered (that function's
    # own eligibility boundary is about dimension ambiguity, not load
    # notation) -- confirmed empirically: without this, a revision-date
    # style plain token like a kip callout returned an unrelated angle-iron
    # fuzzy match.
    if family_of(normalized) not in MODERN_FAMILY_CODES and "X" not in normalized:
        return False
    return True


def _score_from_ranked_pairs(candidate_text: str, ranked_pairs: Optional[List[tuple]], model_version: Optional[str]) -> List[ScoreValue]:
    if not ranked_pairs:
        return []
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
) -> RepairCandidate:
    scores = _score_from_ranked_pairs(candidate_text, ranked_pairs, model_version)
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


def _fuzzy_fallback_candidates(query: str, family: Optional[str]) -> List[RepairCandidate]:
    """Last-resort candidates for a query the main engine's conservative
    "this field already looks reliable" gate abstained on entirely (e.g. a
    deletion that still parses as a syntactically-valid-but-wrong catalog
    shape -- ``W10X3``, brief Section 25). Real ``difflib.SequenceMatcher``
    similarity, never fabricated; explicitly labeled low-confidence and
    never eligible to become ``selected_prediction`` -- display/choose-
    alternate only.
    """
    normalized = conservative_normalize(query)
    if not normalized:
        return []
    from difflib import SequenceMatcher

    pool = _fuzzy_candidates(normalized, limit=MAX_CANDIDATES_ATTACHED)
    out = []
    for rank, label in enumerate(pool, start=1):
        ratio = SequenceMatcher(None, normalized, label).ratio()
        out.append(RepairCandidate(
            candidate_text=label,
            rank=rank,
            family=family,
            catalog_valid=True,
            scores=[ScoreValue(value=round(ratio, 4), kind=SCORE_SIMILARITY, calibrated=False)],
            evidence=[EvidenceRecord(
                evidence_id=f"repair_candidate:{label}:fallback",
                evidence_type=EvidenceType.REPAIR_CANDIDATE,
                source="label_reconstruction_fuzzy_fallback",
                strength=EvidenceStrength.INFERRED,
                reference=label,
                notes=(
                    "Broadened fuzzy fallback: the main candidate generator treats this "
                    "query's numeric fields as reliable/complete and found no exact catalog "
                    "match, so it abstained rather than guess. This is a lower-confidence, "
                    "similarity-only suggestion for human review, not an engine recommendation."
                ),
            )],
            reason_codes=["fuzzy_fallback_broadened"],
            source="label_reconstruction_fuzzy_fallback",
        ))
    return out


@dataclass
class RepairShadowSummary:
    evaluated: int = 0
    candidates_found: int = 0
    no_candidates: int = 0
    already_clean_skipped: int = 0


def attach_repair_shadow(document: SemanticDocument) -> RepairShadowSummary:
    """Mutates ``document.annotations`` in place: attaches
    ``repair_candidates`` and an unaccepted REPAIR proposal operation to
    every annotation ``needs_repair_shadow`` selects. Never changes
    ``effective_text`` by itself (Section 2: shadow/proposal mode only).
    """
    summary = RepairShadowSummary()
    ranker = get_active_ranker()  # None is a valid, handled outcome (no model promoted/loadable)
    model_version = ranker.version_id if ranker is not None else None

    for annotation in document.annotations:
        if not needs_repair_shadow(annotation):
            summary.already_clean_skipped += 1
            continue
        query = annotation.primary_label or annotation.original_text
        if not query:
            continue
        summary.evaluated += 1

        result = reconstruct(query, force_shadow_score=True)
        family = annotation.structural_parse.family if annotation.structural_parse else None

        candidates: List[RepairCandidate] = [
            _build_candidate(
                rank=i + 1,
                candidate_text=label,
                query=query,
                family=family,
                reasons=result.generation_reasons.get(label, []),
                ranked_pairs=result.ranked_pairs,
                model_version=model_version,
                source="label_reconstruction_ranker" if result.ranked_pairs else "label_reconstruction_deterministic",
            )
            for i, label in enumerate(result.candidate_labels[:MAX_CANDIDATES_ATTACHED])
        ]
        # Ranked pairs may reorder relative to the deterministic list (that
        # IS the point of the ranker) -- re-sort by score when available so
        # rank 1 is genuinely the ranker's top pick, not just generation order.
        if result.ranked_pairs:
            order = {label: i for i, (label, _score) in enumerate(result.ranked_pairs)}
            candidates.sort(key=lambda c: order.get(c.candidate_text, len(order)))
            for i, c in enumerate(candidates):
                c.rank = i + 1

        # Fuzzy fallback is restricted to text OUR OWN parser already
        # accepted as a real, grammar-valid structural shape (family +
        # grammar known, just not a catalog member -- the "W10X3" deletion
        # case). For text our parser never recognized as structural at all,
        # an empty candidate list is an honest abstention, not a gap to
        # paper over with unrelated fuzzy matches.
        parse = annotation.structural_parse
        grammar_valid_shape = bool(parse and parse.is_structural and parse.grammar not in (None, "incomplete"))
        if not candidates and grammar_valid_shape:
            candidates = _fuzzy_fallback_candidates(query, family)

        annotation.repair_candidates = candidates

        if candidates:
            summary.candidates_found += 1
            top = candidates[0]
            is_fallback = top.source == "label_reconstruction_fuzzy_fallback"
            annotation.operations.append(OperationRecord(
                operation=OperationKind.REPAIR,
                input_text=query,
                output_text=top.candidate_text,
                reason_codes=list(top.reason_codes) + ["label_reconstruction_shadow_proposal"],
                evidence=list(top.evidence),
                score=(top.scores[0] if top.scores else None),
                deterministic=(model_version is None and not is_fallback),
                semantic_information_added=False,
                provenance=top.source,
                accepted=False,  # SHADOW MODE: never changes effective_text by itself
            ))
            annotation.review.status = ReviewStatus.NEEDS_REVIEW
            if not annotation.review.reason:
                annotation.review.reason = (
                    "ambiguous_low_confidence_candidates" if is_fallback else "repair_candidate_available"
                )
        else:
            summary.no_candidates += 1
            annotation.review.status = ReviewStatus.NEEDS_REVIEW
            if not annotation.review.reason:
                annotation.review.reason = "no_repair_candidates_found"

    return summary
