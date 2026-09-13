"""Emit drawing_semantics.json from prediction payloads (Accuracy Track A8).

Read-model only: projects existing first-run / analyze predictions through
``services.semantic.projection.project_semantic_annotation`` into the one
canonical semantic model, then serializes it with
``services.semantic.serialization``. Does not change takeoff formulas,
enable ML, or invent completions.

Schema v2 (this module previously emitted its own ad hoc row-list under
``drawing_semantics_v1`` from the now-retired
``services.prediction.semantic_contract`` Pydantic model; see
``docs/architecture/unified_semantic_contract.md`` for the migration notes).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from services.semantic.models import SCHEMA_VERSION
from services.semantic.projection import project_semantic_annotation

DRAWING_SEMANTICS_SCHEMA = "drawing_semantics_v2"


def build_drawing_semantics(
    *,
    document_id: str,
    source_file: str,
    predictions: Iterable[Dict[str, Any]],
    context_definitions: Optional[Iterable[Dict[str, Any]]] = None,
    pipeline_version: Optional[str] = None,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for bucket, items in (
        ("predictions", list(predictions or [])),
        ("context_definitions", list(context_definitions or [])),
    ):
        for pred in items:
            ann = project_semantic_annotation(pred).to_dict()
            ann["source_bucket"] = bucket
            if pred.get("object_scope") is not None:
                ann["object_scope"] = pred.get("object_scope")
            if pred.get("completion_status") is not None:
                ann["completion_status"] = pred.get("completion_status")
            rows.append(ann)

    return {
        "schema": DRAWING_SEMANTICS_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "source_file": source_file,
        "pipeline_version": pipeline_version,
        "annotation_count": len(rows),
        "annotations": rows,
        "policy": {
            "excel_role": "not_used",
            "catalog_role": "verification_only",
            "incomplete_l_auto_complete": False,
            "grasshopper_required": False,
        },
    }


def write_drawing_semantics(path: Union[str, Path], payload: Dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    import json

    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def validate_drawing_semantics(payload: Dict[str, Any]) -> List[str]:
    """Return a list of schema problems (empty => OK)."""

    errors: List[str] = []
    if payload.get("schema") != DRAWING_SEMANTICS_SCHEMA:
        errors.append("missing_or_wrong_schema")
    if not payload.get("document_id"):
        errors.append("missing_document_id")
    anns = payload.get("annotations")
    if not isinstance(anns, list):
        errors.append("annotations_not_list")
        return errors
    for i, ann in enumerate(anns):
        if not isinstance(ann, dict):
            errors.append(f"annotation_{i}_not_object")
            continue
        if "original_text" not in ann:
            errors.append(f"annotation_{i}_missing_original_text")
        if ann.get("original_text_preserved") is False:
            errors.append(f"annotation_{i}_raw_not_preserved")
    return errors
