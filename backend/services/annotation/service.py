"""Assemble annotation interpretation for one prediction token."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.annotation.ambiguity import assess_ambiguity
from services.annotation.model_governance import model_governance_status
from services.annotation.normalize import (
    as_float,
    as_int,
    compact_normalize,
    orientation_bin_name,
    safe_bbox,
    soft_normalize,
)
from services.annotation.parser import AnnotationParse, interpret_annotation
from services.annotation.taxonomy import (
    AnnotationType,
    Understandability,
    annotation_type_value,
    understandability_value,
)
from services.annotation.understandability import classify_understandability

logger = logging.getLogger("takeoff.annotation")

_EVIDENCE_POLICY = {
    "geometry_is_evidence_only": True,
    "graph_is_evidence_only": True,
    "aisc_is_plausibility_only": True,
    "text_rotation_independent_of_geometry_orientation": True,
}


def interpret_token_annotation(
    token: Dict[str, Any],
    *,
    geometry: Optional[Dict[str, Any]] = None,
    graph: Optional[Dict[str, Any]] = None,
    candidate_scores: Optional[List[Dict[str, Any]]] = None,
    selected_section: str = "",
) -> Dict[str, Any]:
    """Interpret one annotation. Never raises; unusable input is unresolved."""

    token = token if isinstance(token, dict) else {}
    try:
        return _interpret(
            token,
            geometry=geometry,
            graph=graph,
            candidate_scores=candidate_scores,
            selected_section=selected_section,
        )
    except Exception as exc:  # one annotation must not fail the document
        logger.warning(
            "annotation interpretation unresolved for %r: %s",
            token.get("raw_text") or token.get("text"),
            exc,
        )
        return unresolved_annotation(token, geometry=geometry, error=exc)


def unresolved_annotation(
    token: Dict[str, Any],
    *,
    geometry: Optional[Dict[str, Any]] = None,
    error: Optional[BaseException] = None,
) -> Dict[str, Any]:
    """Structured UNSUPPORTED result with preserved evidence and provenance."""

    raw = str(token.get("raw_text") or token.get("text") or "")
    geometry_orientation = ((geometry or {}).get("object") or {}).get("orientation")
    orientation_source = (
        geometry_orientation
        if geometry_orientation is not None
        else (geometry or {}).get("geometry_orientation")
    )
    parsed = AnnotationParse(
        raw_text=raw,
        normalized_text=soft_normalize(
            str(token.get("normalized_text") or token.get("text") or raw)
        ),
        annotation_type=AnnotationType.UNSUPPORTED.value,
        page=as_int(token.get("page")),
        bbox=safe_bbox(token.get("bbox")),
        text_rotation=as_float(token.get("rotation")),
        geometry_orientation=as_float(orientation_source),
        geometry_orientation_bin=orientation_bin_name(orientation_source),
        source=str(token.get("extraction_method") or "pdf_text"),
        provenance={
            "unresolved": True,
            "error_type": type(error).__name__ if error else "unresolved",
            "error": str(error) if error else "Annotation could not be interpreted.",
        },
    )
    reason = (
        "Annotation could not be interpreted by the current taxonomy; "
        "captured for human review instead of guessing."
    )
    return {
        "annotation": parsed.to_dict(),
        "understandability": {
            "status": Understandability.UNSUPPORTED.value,
            "reasons": [reason],
            "continue_prediction": False,
            "route_to_review": True,
        },
        "ambiguity": {
            "ambiguous": True,
            "resolution": "human_review",
            "top_k": [],
            "margin": None,
            "selected": None,
            "reason": reason,
        },
        "abstain_for_review": True,
        "model_governance": model_governance_status(),
        "evidence_policy": dict(_EVIDENCE_POLICY),
    }


def _interpret(
    token: Dict[str, Any],
    *,
    geometry: Optional[Dict[str, Any]] = None,
    graph: Optional[Dict[str, Any]] = None,
    candidate_scores: Optional[List[Dict[str, Any]]] = None,
    selected_section: str = "",
) -> Dict[str, Any]:
    context = token.get("context") or {}
    nearby = list(context.get("neighbor_text") or [])
    if token.get("surrounding_text"):
        nearby.append(str(token.get("surrounding_text")))
    parsed = interpret_annotation(
        raw_text=str(token.get("raw_text") or token.get("text") or ""),
        normalized_text=str(
            token.get("normalized_text") or token.get("text") or ""
        ),
        page=token.get("page"),
        bbox=token.get("bbox"),
        text_rotation=token.get("rotation"),
        geometry_orientation=(
            # Numeric degrees first; ``geometry_orientation`` may be a coarse bin.
            ((geometry or {}).get("object") or {}).get("orientation")
            if ((geometry or {}).get("object") or {}).get("orientation") is not None
            else (geometry or {}).get("geometry_orientation")
        ),
        nearby_text=nearby,
        nearby_geometry=geometry,
        leader={"present": bool(context.get("leader"))} if context.get("leader") else None,
        page_context=str(context.get("line_text") or ""),
        graph_context=graph,
        fragments=list(token.get("fragments") or []),
        source=str(token.get("extraction_method") or "pdf_text"),
    )
    understand = dict(
        classify_understandability(
            parsed,
            extraction_confidence=as_float(token.get("confidence")),
            candidate_labels=[
                str(item.get("shape") or "")
                for item in (candidate_scores or [])
                if isinstance(item, dict)
            ],
        )
    )
    status = understandability_value(understand.get("status"))
    understand["status"] = status
    # Undamaged catalog text that equals the selected label is self-resolving,
    # so close fusion margins must not push it into the review queue.
    text_designation = parsed.catalog_designation or compact_normalize(
        parsed.normalized_text or parsed.raw_text
    )
    text_resolves_selected = bool(
        selected_section
        and status == Understandability.UNDERSTOOD.value
        and not parsed.wildcard
        and compact_normalize(selected_section) == text_designation
    )
    ambiguity = assess_ambiguity(
        candidate_scores or [],
        selected=selected_section or None,
        text_supports_selected=text_resolves_selected,
    )
    # Candidate-margin ambiguity only decides section-like annotations; a plate
    # or member mark is not resolved by AISC candidate ranking at all.
    annotation_type = annotation_type_value(parsed.annotation_type)
    section_like = annotation_type in {
        AnnotationType.STANDARD_SECTION.value,
        AnnotationType.UNKNOWN.value,
    }
    needs_structure_confirmation = (
        annotation_type
        in {
            AnnotationType.PLATE.value,
            AnnotationType.BENT_PLATE.value,
            AnnotationType.DIMENSION.value,
        }
        and not parsed.structure_confirmed
    )
    abstain = (
        status
        in {
            Understandability.UNREADABLE.value,
            Understandability.UNSUPPORTED.value,
        }
        or (
            section_like
            and ambiguity.get("resolution") == "human_review"
            and not text_resolves_selected
        )
        or needs_structure_confirmation
    )

    annotation = parsed.to_dict()
    annotation["annotation_type"] = annotation_type
    return {
        "annotation": annotation,
        "understandability": understand,
        "ambiguity": ambiguity,
        "abstain_for_review": bool(abstain),
        "model_governance": model_governance_status(),
        "evidence_policy": dict(_EVIDENCE_POLICY),
    }
