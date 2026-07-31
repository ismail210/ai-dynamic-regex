"""Persistent document registry for the staged takeoff workflow."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import fitz

from config import settings


_LOCK = threading.RLock()
_STAGES = {
    "uploaded",
    "extracting",
    "extracted",
    "analyzing",
    "analyzed",
    "failed",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(document_id: str) -> Path:
    if not document_id.startswith("doc_") or not document_id[4:].isalnum():
        raise ValueError("Invalid document id")
    return settings.document_registry_dir / f"{document_id}.json"


def _write_manifest(manifest: Dict[str, Any]) -> None:
    target = _manifest_path(str(manifest["document_id"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, separators=(",", ":")), encoding="utf-8"
    )
    temporary.replace(target)


def validate_pdf(path: str | Path) -> Dict[str, Any]:
    """Perform lightweight structural validation without extracting content."""

    source = Path(path)
    if source.suffix.lower() != ".pdf":
        raise ValueError("Only PDF documents are supported")
    with source.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("The uploaded file is not a valid PDF")
    try:
        with fitz.open(source) as document:
            page_count = int(document.page_count or 0)
            if page_count < 1:
                raise ValueError("The PDF contains no pages")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"The PDF structure is invalid: {exc}") from exc
    return {"page_count": page_count, "size_bytes": source.stat().st_size}


def register_document(
    path: str | Path,
    *,
    original_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a stored PDF and return a stable content-addressed document."""

    source = Path(path).resolve()
    validation = validate_pdf(source)
    digest = _sha256(source)
    document_id = f"doc_{digest[:16]}"
    manifest_path = _manifest_path(document_id)
    now = _utc_now()

    with _LOCK:
        existing: Dict[str, Any] = {}
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = {
            **existing,
            "schema_version": "1.0",
            "document_id": document_id,
            "source_file": Path(original_name or source.name).name,
            "stored_file": source.name,
            "source_path": str(source),
            "sha256": digest,
            "page_count": validation["page_count"],
            "size_bytes": validation["size_bytes"],
            "stage": existing.get("stage") or "uploaded",
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "error": None,
        }
        _write_manifest(manifest)
    return public_document(manifest)


def get_document(document_id: str) -> Dict[str, Any]:
    path = _manifest_path(document_id)
    if not path.exists():
        raise FileNotFoundError(f"Document '{document_id}' was not found")
    return json.loads(path.read_text(encoding="utf-8"))


def update_document(
    document_id: str,
    *,
    stage: Optional[str] = None,
    error: Optional[str] = None,
    **fields: Any,
) -> Dict[str, Any]:
    with _LOCK:
        manifest = get_document(document_id)
        if stage is not None:
            if stage not in _STAGES:
                raise ValueError(f"Unknown document stage '{stage}'")
            manifest["stage"] = stage
        manifest.update(fields)
        manifest["error"] = error
        manifest["updated_at"] = _utc_now()
        _write_manifest(manifest)
    return public_document(manifest)


def document_source(document_id: str) -> Path:
    manifest = get_document(document_id)
    source = Path(str(manifest["source_path"])).resolve()
    allowed_roots = {
        settings.uploads_dir.resolve(),
        settings.engineering_uploads_dir.resolve(),
    }
    if not any(source == root or root in source.parents for root in allowed_roots):
        raise ValueError("Registered document path is outside the upload store")
    if not source.exists():
        raise FileNotFoundError("The registered PDF is no longer available")
    return source


def public_document(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Return document metadata without exposing server filesystem paths."""

    return {
        key: value
        for key, value in manifest.items()
        if key not in {"source_path"}
    }
