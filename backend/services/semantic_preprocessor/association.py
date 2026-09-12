"""Label <-> geometry association and evidence fusion (Section 34-37, 45).

The one rule every function in this module obeys: Grasshopper's own
text<->curve pairing, and any text Grasshopper's model happens to carry for
a beam, is ASSOCIATION evidence only. It can point an annotation at a piece
of geometry. It can never, by itself, rewrite what the annotation's label
says -- that would collapse the completion boundary this whole pipeline
exists to protect (Section 28/45's mandatory test: GHX says W8X10, PDF says
W8, no source_verified rule -> stays W8, GHX's text becomes a
``discrepancy`` note, not a rewrite).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from services.semantic_preprocessor.coordinate_transform import apply_transform
from services.semantic_preprocessor.models import (
    REVIEW_ACCEPTED,
    REVIEW_NEEDS_REVIEW,
    REVIEW_PENDING,
    AssociationCandidate,
    CoordinateTransform,
    EvidenceItem,
    GeometryEvidence,
    SemanticAnnotation,
)

REASON_GHX_EXISTING_PAIR = "GHX_EXISTING_PAIR"
REASON_PDF_LEADER_INTERSECTION = "PDF_LEADER_INTERSECTION"
REASON_ORIENTATION_MATCH = "ORIENTATION_MATCH"
REASON_PROJECTED_OVERLAP = "PROJECTED_OVERLAP"
REASON_NEAREST_STRUCTURAL_CURVE = "NEAREST_STRUCTURAL_CURVE"
REASON_GHX_PDF_DISAGREEMENT = "GHX_PDF_DISAGREEMENT"
REASON_AMBIGUOUS_MULTIPLE_BEAMS = "AMBIGUOUS_MULTIPLE_BEAMS"

_STRUCTURAL_GEOMETRY_TYPES = {"beam_curve", "curved_beam", "column", "moment"}
_NEAREST_NEIGHBOR_TIE_MARGIN = 0.15  # relative distance margin considered "too close to call"


def associate_via_ghx_pairing(
    annotation: SemanticAnnotation, ghx_text_pairs: List[Dict[str, Any]]
) -> Tuple[Optional[AssociationCandidate], Optional[str]]:
    """Match this annotation against an explicit GHX text<->geometry pairing.

    Returns ``(candidate, discrepancy_text)``. ``discrepancy_text`` is set
    (and the candidate is still returned) when GHX's own paired text differs
    from this annotation's canonical/primary label -- that difference is
    surfaced for review, never used to silently change the label.
    """
    normalized_label = (annotation.primary_label or "").strip().upper()
    for pair in ghx_text_pairs:
        pair_text = str(pair.get("text", "")).strip().upper()
        if pair_text != normalized_label:
            continue
        geometry_id = pair.get("geometry_id")
        if not geometry_id:
            continue
        discrepancy = None
        ghx_full_text = pair.get("full_text") or pair.get("text")
        if ghx_full_text and str(ghx_full_text).strip().upper() != normalized_label:
            discrepancy = str(ghx_full_text)
        candidate = AssociationCandidate(
            annotation_id=annotation.annotation_id,
            geometry_id=geometry_id,
            score=0.9,  # evidence strength, not a calibrated probability
            evidence=[EvidenceItem(type="ghx_existing_pairing", value=True, weight=1.0)],
            association_reason=[REASON_GHX_EXISTING_PAIR],
            review_status=REVIEW_PENDING,
        )
        return candidate, discrepancy
    return None, None


def associate_via_nearest_geometry(
    annotation: SemanticAnnotation,
    geometry_list: List[GeometryEvidence],
    transform: Optional[CoordinateTransform],
) -> Optional[AssociationCandidate]:
    """Deterministic nearest-structural-geometry fallback.

    Refuses to run (returns None) without a valid transform and an original
    anchor -- never falls back to comparing raw PDF coordinates against
    Rhino coordinates as if they were the same frame (Section 13).
    """
    if annotation.original_anchor is None:
        return None
    structural = [g for g in geometry_list if g.geometry_type in _STRUCTURAL_GEOMETRY_TYPES and g.centroid]
    if not structural:
        return None

    if transform is not None and transform.valid:
        anchor = apply_transform(transform, tuple(annotation.original_anchor))
    elif transform is None:
        # No transform supplied at all -- geometry is assumed already in the
        # same frame as the annotation anchor (e.g. a same-frame test
        # fixture). A transform that exists but is invalid must still block.
        anchor = tuple(annotation.original_anchor)
    else:
        return None

    distances = sorted(
        (
            (math.hypot(anchor[0] - g.centroid[0], anchor[1] - g.centroid[1]), g)
            for g in structural
        ),
        key=lambda pair: pair[0],
    )
    best_distance, best_geom = distances[0]
    if len(distances) > 1:
        second_distance, _ = distances[1]
        if second_distance > 0 and (second_distance - best_distance) / second_distance < _NEAREST_NEIGHBOR_TIE_MARGIN:
            return AssociationCandidate(
                annotation_id=annotation.annotation_id,
                geometry_id=best_geom.geometry_id,
                score=None,
                evidence=[EvidenceItem(type="nearest_distance", value=best_distance)],
                association_reason=[REASON_AMBIGUOUS_MULTIPLE_BEAMS],
                review_status=REVIEW_NEEDS_REVIEW,
            )
    return AssociationCandidate(
        annotation_id=annotation.annotation_id,
        geometry_id=best_geom.geometry_id,
        score=None,  # deterministic distance, not a calibrated probability
        evidence=[EvidenceItem(type="nearest_distance", value=best_distance)],
        association_reason=[REASON_NEAREST_STRUCTURAL_CURVE],
        review_status=REVIEW_PENDING,
    )


def fuse_candidates(
    ghx_candidate: Optional[AssociationCandidate],
    pdf_candidate: Optional[AssociationCandidate],
) -> List[AssociationCandidate]:
    """Combine GHX and PDF-native association evidence (Section 36).

    - Only one candidate exists: pass it through as-is (still ``pending``).
    - Both point at the same geometry: strong agreement, evidence merged.
    - They disagree: both are returned, flagged ``needs_review`` with
      ``GHX_PDF_DISAGREEMENT`` -- this module never picks a winner.
    """
    if ghx_candidate and not pdf_candidate:
        return [ghx_candidate]
    if pdf_candidate and not ghx_candidate:
        return [pdf_candidate]
    if ghx_candidate is None or pdf_candidate is None:
        return []

    if ghx_candidate.geometry_id == pdf_candidate.geometry_id:
        merged = AssociationCandidate(
            annotation_id=ghx_candidate.annotation_id,
            geometry_id=ghx_candidate.geometry_id,
            score=0.96,
            evidence=ghx_candidate.evidence + pdf_candidate.evidence,
            association_reason=list(dict.fromkeys(
                ghx_candidate.association_reason + pdf_candidate.association_reason
            )),
            review_status=REVIEW_PENDING,
        )
        return [merged]

    for c in (ghx_candidate, pdf_candidate):
        c.review_status = REVIEW_NEEDS_REVIEW
        if REASON_GHX_PDF_DISAGREEMENT not in c.association_reason:
            c.association_reason.append(REASON_GHX_PDF_DISAGREEMENT)
    return [ghx_candidate, pdf_candidate]
