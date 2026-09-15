"""Build a corrected PDF from the immutable original + accepted semantic edits.

Does not modify the uploaded/original PDF. Applies white-cover + Helvetica
replacement at each annotation's ``semantic_bbox`` (same technique as the
damage-corpus generator). Only annotations whose effective text differs from
``original_text`` and whose review status is accepted contribute.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import fitz

from config import settings
from services.artifact_store import write_artifact
from services.document_registry import document_source
from services.semantic.models import ReviewStatus

_CORRECTED_NAME = "semantic_corrected.pdf"
_REVISION_NAME = "semantic_corrected_revision.json"


def corrected_pdf_path(document_id: str) -> Path:
    """Derived corrected PDF lives beside other document artifacts — never in uploads/."""
    if not document_id.startswith("doc_") or not document_id[4:].isalnum():
        raise ValueError("Invalid document id")
    return settings.engineering_artifacts_dir / document_id / _CORRECTED_NAME


def list_accepted_text_corrections(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return PDF-applicable accepted corrections (effective != original)."""
    accepted_statuses = {
        ReviewStatus.HUMAN_ACCEPTED.value,
        ReviewStatus.AUTO_ACCEPTED.value,
    }
    out: List[Dict[str, Any]] = []
    for ann in document.get("annotations") or []:
        status = ann.get("review_status")
        if status not in accepted_statuses:
            continue
        original = (ann.get("original_text") or "").strip()
        effective = (ann.get("effective_text") or "").strip()
        if not effective or effective == original:
            continue
        bbox = ann.get("semantic_bbox")
        page = ann.get("page")
        if not bbox or len(bbox) < 4 or not page:
            continue
        out.append(
            {
                "annotation_id": ann.get("annotation_id"),
                "page": int(page),
                "original_text": original,
                "effective_text": effective,
                "semantic_bbox": [float(v) for v in bbox[:4]],
            }
        )
    return out


def corrections_revision(corrections: Sequence[Dict[str, Any]]) -> str:
    """Stable short hash of the applied correction set (cache-bust + stale detect)."""
    if not corrections:
        return "none"
    parts = [
        f"{c.get('annotation_id')}:{c.get('page')}:{c.get('effective_text')}"
        for c in sorted(corrections, key=lambda x: (x.get("page") or 0, x.get("annotation_id") or ""))
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def corrected_pdf_public_url(document_id: str, revision: str) -> Optional[str]:
    if not revision or revision == "none":
        return None
    return f"/api/documents/{document_id}/semantic/corrected-pdf?v={revision}"


def _replace_label(page: fitz.Page, bbox: Sequence[float], new_text: str) -> None:
    rect = fitz.Rect(bbox)
    cover = fitz.Rect(rect.x0 - 0.8, rect.y0 - 0.6, rect.x1 + 0.8, rect.y1 + 0.6)
    page.draw_rect(cover, color=None, fill=(1, 1, 1), width=0)
    height = max(5.0, rect.y1 - rect.y0)
    fs = min(12.0, height * 0.92)
    width_est = fitz.get_text_length(new_text, fontname="helv", fontsize=fs)
    avail = max(4.0, cover.x1 - cover.x0)
    if width_est > avail:
        fs = max(5.0, fs * (avail / width_est))
    insert_point = fitz.Point(rect.x0, rect.y1 - max(0.5, height * 0.12))
    page.insert_text(insert_point, new_text, fontsize=fs, fontname="helv", color=(0, 0, 0))


def build_corrected_pdf(document_id: str, document: Dict[str, Any]) -> Path:
    """Write ``semantic_corrected.pdf`` under the document artifact dir.

    Always starts from the original source PDF (never from a prior corrected
    file), then applies every accepted text correction.
    """
    source = document_source(document_id)
    if not source.exists():
        raise FileNotFoundError(f"Original PDF missing for {document_id}")

    corrections = list_accepted_text_corrections(document)
    out_path = corrected_pdf_path(document_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    skipped: List[str] = []
    # Open the immutable original; write only to the derived artifact path.
    doc = fitz.open(source)
    try:
        for item in corrections:
            page_index = item["page"] - 1
            if page_index < 0 or page_index >= doc.page_count:
                skipped.append(item["annotation_id"])
                continue
            page = doc[page_index]
            _replace_label(page, item["semantic_bbox"], item["effective_text"])
        doc.save(out_path, garbage=3, deflate=True)
    finally:
        doc.close()

    revision = corrections_revision(corrections)
    write_artifact(
        document_id,
        "semantic_corrected_summary.json",
        {
            "document_id": document_id,
            "correction_count": len(corrections),
            "skipped_annotation_ids": skipped,
            "artifact": _CORRECTED_NAME,
            "revision": revision,
            "source_pdf": str(source),
        },
    )
    write_artifact(
        document_id,
        _REVISION_NAME,
        {"revision": revision, "correction_count": len(corrections)},
    )
    return out_path


def describe_corrected_pdf(document_id: str, document: Dict[str, Any]) -> Dict[str, Any]:
    """Metadata the API returns so the viewer can load a cache-busted URL."""
    corrections = list_accepted_text_corrections(document)
    revision = corrections_revision(corrections)
    return {
        "available": bool(corrections),
        "revision": revision,
        "correction_count": len(corrections),
        "url": corrected_pdf_public_url(document_id, revision),
    }


def sync_corrected_pdf(document_id: str, document: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild or clear the derived PDF so it matches persisted semantic state."""
    corrections = list_accepted_text_corrections(document)
    path = corrected_pdf_path(document_id)
    if not corrections:
        if path.exists():
            path.unlink()
        write_artifact(
            document_id,
            _REVISION_NAME,
            {"revision": "none", "correction_count": 0},
        )
        return describe_corrected_pdf(document_id, document)
    build_corrected_pdf(document_id, document)
    return describe_corrected_pdf(document_id, document)


def corrected_pdf_download_name(document_id: str, original_name: Optional[str] = None) -> str:
    base = Path(original_name or document_id).stem
    return f"{base}_corrected.pdf"
