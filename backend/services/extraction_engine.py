"""PDF extraction preflight and stable extraction diagnostics contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from services.artifact_store import write_artifact
from services.document_intelligence import build_extraction_diagnostics
from services.annotation.fragment_grouper import group_annotation_fragments
from services.engineering.document_prior import attach_document_prior
from services.engineering_object_filter import filter_engineering_objects
from services.pdf_parser import extract_document_structure


# Bumped whenever extraction output changes, so cached documents are rebuilt
# instead of replaying stale artifacts.
EXTRACTION_VERSION = "3.7-extraction-quality"


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
    attach_document_prior(document)
    raw_tokens = document.get("engineering_tokens") or []
    document["raw_engineering_token_count"] = len(raw_tokens)
    # Rotation-aware merge of split shards (6 / x / 4 / x / 5/6) before filter.
    grouped = group_annotation_fragments(raw_tokens)
    _link_layout_dimensions(document, grouped)
    discard_counts: Dict[str, int] = {}
    document["engineering_tokens"] = filter_engineering_objects(
        grouped, document=document, discard_counts=discard_counts
    )
    document["extraction_discard_counts"] = discard_counts
    document["engineering_object_count"] = len(document["engineering_tokens"])
    document["source_file"] = path.name
    document["extraction_version"] = EXTRACTION_VERSION
    _rescope_diagnostics_to_engineering_objects(document)
    return document


def _bbox_overlap(a: list, b: list, *, min_ratio: float = 0.3) -> bool:
    if not a or not b or len(a) < 4 or len(b) < 4:
        return False
    x0 = max(float(a[0]), float(b[0]))
    y0 = max(float(a[1]), float(b[1]))
    x1 = min(float(a[2]), float(b[2]))
    y1 = min(float(a[3]), float(b[3]))
    if x1 <= x0 or y1 <= y0:
        return False
    inter = (x1 - x0) * (y1 - y0)
    area_a = max(1.0, (float(a[2]) - float(a[0])) * (float(a[3]) - float(a[1])))
    return inter / area_a >= min_ratio


def _link_layout_dimensions(document: Dict[str, Any], tokens: list) -> None:
    """Attach layout dimension ids to engineering tokens by bbox overlap."""

    layout_dims = document.get("dimensions") or []
    if not layout_dims:
        return
    for token in tokens:
        page = int(token.get("page") or 0)
        bbox = token.get("bbox")
        if not bbox:
            continue
        for dim in layout_dims:
            if int(dim.get("page_number") or 0) != page:
                continue
            dim_bbox = dim.get("bbox")
            if dim_bbox and _bbox_overlap(bbox, dim_bbox):
                token["layout_dimension_id"] = dim.get("dimension_id")
                token.setdefault("context", {})["layout_dimension_text"] = dim.get(
                    "text"
                )
                break


def _rescope_diagnostics_to_engineering_objects(document: Dict[str, Any]) -> None:
    """Report extraction quality for structural objects, not all page text.

    Raw pattern matches include material grades, sheet references, and note
    fragments. Scoring those made every drawing look mostly "suspicious".
    """

    previous = document.get("extraction_diagnostics") or {}
    diagnostics = build_extraction_diagnostics(
        document=document,
        tokens=document.get("engineering_tokens") or [],
        word_count_before_cleanup=int(
            previous.get("word_count_before_cleanup") or 0
        ),
        word_count_after_cleanup=int(
            previous.get("word_count_after_cleanup") or 0
        ),
        ocr_repairs=int(previous.get("ocr_repairs") or 0),
        tables=document.get("tables") or [],
        schedules=document.get("schedules") or [],
        callouts=document.get("callouts") or [],
        dimensions=document.get("dimensions") or [],
        title_blocks=document.get("title_blocks") or [],
    )
    diagnostics["scope"] = "engineering_objects"
    diagnostics["text_candidates_scanned"] = int(
        document.get("raw_engineering_token_count") or 0
    )
    document["extraction_diagnostics"] = diagnostics
    document["extraction_quality"] = {
        **diagnostics,
        "decorative_words_removed": (
            document.get("extraction_quality") or {}
        ).get("decorative_words_removed", diagnostics["noise_removed"]),
        "duplicate_tokens_removed": (
            document.get("extraction_quality") or {}
        ).get("duplicate_tokens_removed", 0),
    }


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
            "document_prior": document.get("document_prior") or {},
        },
        "object_counts": {
            **(document.get("object_counts") or {}),
            "engineering_objects": len(tokens),
            "discarded_text_candidates": max(
                0,
                int(document.get("raw_engineering_token_count") or 0) - len(tokens),
            ),
            "discard_breakdown": document.get("extraction_discard_counts") or {},
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
