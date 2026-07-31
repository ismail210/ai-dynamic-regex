"""
Bounded artifact persistence for pipeline outputs.

Analysis artifacts are debug/training caches derived from the source drawing,
so they must never be allowed to fill the disk. Three guarantees:

* compact JSON (no pretty-print padding),
* a retention cap on stored documents,
* a free-space check before writing, and ENOSPC surfaced as HTTP 507.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from config import settings


logger = logging.getLogger("takeoff.artifacts")


def artifact_path(document_id: str, name: str) -> Path:
    """Resolve one staged artifact under the canonical layout."""

    if not document_id.startswith("doc_") or not document_id[4:].isalnum():
        raise ValueError("Invalid document id")
    safe_name = Path(name).name
    if safe_name != name or not safe_name.endswith(".json"):
        raise ValueError("Invalid artifact name")
    return (
        settings.engineering_artifacts_dir
        / document_id
        / "multimodal"
        / safe_name
    )


def read_artifact(document_id: str, name: str) -> Any | None:
    """Load an artifact, returning ``None`` when the cache entry is absent."""

    path = artifact_path(document_id, name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def free_bytes(path: Path | None = None) -> int:
    """Return free bytes on the volume holding ``path``."""

    target = path or settings.engineering_artifacts_dir
    try:
        return shutil.disk_usage(target).free
    except OSError:  # pragma: no cover - unreadable mount
        return 0


def has_free_space(path: Path | None = None) -> bool:
    return free_bytes(path) >= settings.artifact_min_free_bytes


def prune_documents(keep: int | None = None) -> dict[str, Any]:
    """
    Delete the oldest document directories beyond the retention limit.

    Returns a summary so callers can log or surface what was reclaimed.
    """

    limit = settings.artifact_retention_documents if keep is None else keep
    root = settings.engineering_artifacts_dir
    if limit <= 0 or not root.exists():
        return {"removed": 0, "freed_bytes": 0, "kept": 0}

    directories = sorted(
        (item for item in root.iterdir() if item.is_dir()),
        key=lambda item: item.stat().st_mtime,
    )
    stale = directories[:-limit] if len(directories) > limit else []
    freed = 0
    for directory in stale:
        try:
            freed += sum(
                file.stat().st_size
                for file in directory.rglob("*")
                if file.is_file()
            )
            shutil.rmtree(directory, ignore_errors=True)
        except OSError:  # pragma: no cover - concurrent removal
            continue

    if stale:
        logger.info(
            "pruned %s stale artifact document(s), reclaimed %.1f MB",
            len(stale),
            freed / (1024 * 1024),
        )
    return {
        "removed": len(stale),
        "freed_bytes": freed,
        "kept": min(len(directories), limit),
    }


def write_artifact(document_id: str, name: str, payload: Any) -> str | None:
    """
    Write one artifact compactly; return its path, or ``None`` when skipped.

    Persistence is best-effort: a full disk degrades diagnostics but must never
    fail an otherwise successful analysis.
    """

    path = artifact_path(document_id, name)
    directory = path.parent
    if not has_free_space(settings.engineering_artifacts_dir):
        prune_documents()
    if not has_free_space(settings.engineering_artifacts_dir):
        logger.warning(
            "skipping artifact %s/%s: only %.0f MB free (need %.0f MB)",
            document_id,
            name,
            free_bytes() / (1024 * 1024),
            settings.artifact_min_free_bytes / (1024 * 1024),
        )
        return None

    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Compact separators roughly halve the size of these nested payloads.
        path.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )
        return str(path)
    except OSError as exc:
        # Remove the partial file so a truncated artifact is never read back.
        try:
            (directory / name).unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass
        logger.warning("artifact %s/%s could not be written: %s", document_id, name, exc)
        return None
