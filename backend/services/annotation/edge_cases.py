"""Controlled edge-case ground-truth store (no auto-retrain)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings

EDGE_CASE_CATEGORIES = frozenset(
    {
        "plates",
        "bent_plates",
        "damaged_labels",
        "rotated_annotations",
        "compound_dimensions",
        "ranges",
        "mixed_units",
        "callouts",
        "schedule_references",
        "unreadable",
        "unsupported",
    }
)


def edge_case_path() -> Path:
    path = Path(getattr(settings, "annotation_edge_cases_path", None) or (
        settings.training_dir / "annotation_edge_cases.jsonl"
    ))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def record_edge_case(
    *,
    category: str,
    raw_text: str,
    normalized_text: str = "",
    annotation_type: str = "",
    parsed_structure: Optional[Dict[str, Any]] = None,
    page: Optional[int] = None,
    bbox: Optional[list] = None,
    text_rotation: Optional[float] = None,
    geometry_reference: Optional[Dict[str, Any]] = None,
    graph_reference: Optional[Dict[str, Any]] = None,
    ground_truth: str = "",
    correction: str = "",
    reviewer_decision: str = "",
    reason: str = "",
    provenance: Optional[Dict[str, Any]] = None,
    document_id: str = "",
    object_id: str = "",
) -> Dict[str, Any]:
    """Append one human-reviewed edge case. Does not trigger training."""

    bucket = category if category in EDGE_CASE_CATEGORIES else "unsupported"
    entry = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "category": bucket,
        "raw_text": raw_text,
        "normalized_text": normalized_text or raw_text,
        "annotation_type": annotation_type,
        "parsed_structure": parsed_structure or {},
        "page": page,
        "bbox": bbox,
        "text_rotation": text_rotation,
        "geometry_reference": geometry_reference or {},
        "graph_reference": graph_reference or {},
        "ground_truth": ground_truth,
        "correction": correction,
        "reviewer_decision": reviewer_decision,
        "reason": reason,
        "provenance": provenance or {},
        "document_id": document_id,
        "object_id": object_id,
        "training_eligible": reviewer_decision
        in {"approve", "correct", "edit", "mark_unreadable", "mark_unsupported"},
        "auto_retrain": False,
    }
    path = edge_case_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")
    return entry
