"""G5 workflow safety: geometry sidecar must not rewrite semantic text/completion."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def attach_geometry_sidecar(
    annotation: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    *,
    status: str = "pending_review",
) -> Dict[str, Any]:
    """Return a copy with geometry evidence. Never mutates label fields."""
    out = dict(annotation)
    out["geometry_sidecar"] = {
        "status": status,
        "candidates": candidates,
        "note": "evidence_only",
    }
    return out


def semantic_fields(annotation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "original_text": annotation.get("original_text") or annotation.get("raw_text"),
        "primary_label": annotation.get("primary_label") or annotation.get("normalized_text"),
        "takeoff_eligible": annotation.get("takeoff_eligible"),
        "completion_status": annotation.get("completion_status")
        or ((annotation.get("structural_parse") or {}).get("complete")),
    }


def sidecar_preserves_semantics(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> bool:
    return semantic_fields(before) == semantic_fields(after)


def mike_corrected_pdf_checklist(document_id: str, corrected_exists: bool) -> Dict[str, Any]:
    return {
        "document_id": document_id,
        "corrected_pdf_present": corrected_exists,
        "owner": "Mike",
        "checks": [
            "Corrected PDF still extracts through existing multimodal pipeline",
            "document.json / geometry.json / graph.json IDs still join",
            "Semantic Review owns text; geometry is additive sidecar only",
            "Incomplete L/2L stay missing_thickness / takeoff_eligible false",
        ],
        "status": "ready_when_corrected_pdf_exists" if not corrected_exists else "run_live_compare",
    }
