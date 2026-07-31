"""PDF extraction preflight and stable extraction diagnostics contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from services.artifact_store import write_artifact
from services.engineering_object_filter import filter_engineering_objects
from services.pdf_parser import extract_document_structure


def extract_engineering_document(
    source_path: str | Path,
    *,
    document_id: str | None = None,
) -> Dict[str, Any]:
    """Build the canonical extraction document used by later stages."""

    path = Path(source_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("Extraction requires a PDF")
    document = extract_document_structure(str(path))
    if document_id:
        document["document_id"] = document_id
    raw_tokens = document.get("engineering_tokens") or []
    document["raw_engineering_token_count"] = len(raw_tokens)
    document["engineering_tokens"] = filter_engineering_objects(raw_tokens)
    document["engineering_object_count"] = len(document["engineering_tokens"])
    document["source_file"] = path.name
    return document


def extraction_response(document: Dict[str, Any]) -> Dict[str, Any]:
    """Create the public extraction-stage contract from a full document."""

    tokens = document.get("engineering_tokens") or []
    diagnostics = document.get("extraction_diagnostics") or {}
    return {
        "schema_version": "2.0",
        "stage": "extracted",
        "prediction_started": False,
        "document_id": document.get("document_id"),
        "source_file": document.get("source_file"),
        "pages": document.get("page_count"),
        "quality": diagnostics,
        "diagnostics": diagnostics,
        "tokens": tokens,
        "layout": {
            "tables": document.get("tables") or [],
            "schedules": document.get("schedules") or [],
            "callouts": document.get("callouts") or [],
            "dimensions": document.get("dimensions") or [],
            "title_blocks": document.get("title_blocks") or [],
        },
        "object_counts": {
            **(document.get("object_counts") or {}),
            "engineering_objects": len(tokens),
            "discarded_text_candidates": max(
                0,
                int(document.get("raw_engineering_token_count") or 0) - len(tokens),
            ),
        },
    }


def run_extraction_preflight(
    source_path: str | Path,
    *,
    document_id: str | None = None,
    persist: bool = False,
) -> Dict[str, Any]:
    """Extract and diagnose a PDF without starting prediction."""

    document = extract_engineering_document(
        source_path, document_id=document_id
    )
    if persist:
        write_artifact(str(document["document_id"]), "document.json", document)
    return extraction_response(document)
