"""
Upload transport layer shared by every multipart endpoint.

Responsibilities are strictly infrastructural: stream a multipart file to
disk, enforce type/size limits, and run blocking analysis in a worker thread
so the event loop keeps answering requests while a drawing is processed.

No prediction, extraction, or scoring logic lives here.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from config import settings
from services.artifact_store import free_bytes, prune_documents


logger = logging.getLogger("takeoff.upload")

CHUNK_SIZE = 1024 * 1024
PDF_SUFFIXES: tuple[str, ...] = (".pdf",)
EXCEL_SUFFIXES: tuple[str, ...] = (".xlsx", ".xls", ".xlsm")

T = TypeVar("T")


def _human_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.0f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} bytes"


def _safe_name(filename: str | None, *, field: str) -> str:
    """Reject empty names and strip any directory component."""

    name = Path(str(filename or "")).name.strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail=f"No filename received for '{field}'.",
        )
    return name


def _require_free_space(destination_dir: Path, *, field: str) -> None:
    """
    Refuse an upload the volume cannot hold, after reclaiming stale artifacts.

    Failing here returns a clear 507 instead of letting the write succeed and
    the analysis die later with ``[Errno 28] No space left on device``.
    """

    needed = settings.max_upload_bytes
    if free_bytes(destination_dir) >= needed:
        return
    prune_documents()
    available = free_bytes(destination_dir)
    if available >= needed:
        return
    logger.error(
        "upload refused field=%s reason=disk_full available=%s needed=%s",
        field,
        available,
        needed,
    )
    raise HTTPException(
        status_code=507,
        detail=(
            f"Not enough server disk space to accept '{field}': "
            f"{_human_bytes(available)} free, {_human_bytes(needed)} required."
        ),
    )


def _staging_path(destination_dir: Path, name: str) -> Path:
    """
    Stage each upload under a private name before publishing it.

    Writing directly to the final path lets a re-upload corrupt an in-flight
    read of the same drawing, which surfaces as MuPDF errors such as
    ``cannot find page N in page tree``.
    """

    return destination_dir / f".incoming__{uuid.uuid4().hex}{Path(name).suffix}"


def _content_destination(destination_dir: Path, name: str, digest: str) -> Path:
    """Final path keyed by content, so re-uploads reuse one stored copy."""

    stem = Path(name).stem
    return destination_dir / f"{stem}__{digest[:12]}{Path(name).suffix}"


async def save_upload(
    file: UploadFile,
    destination_dir: Path,
    *,
    allowed_suffixes: Sequence[str] = PDF_SUFFIXES,
    field: str = "file",
) -> Path:
    """
    Stream one multipart file to ``destination_dir`` and return its path.

    Streaming in fixed chunks keeps memory flat for large drawings, and an
    oversized upload is refused with 413 instead of exhausting the worker.
    """

    name = _safe_name(file.filename, field=field)
    suffix = Path(name).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{field}' must be one of {', '.join(allowed_suffixes)} "
                f"(received '{suffix or name}')."
            ),
        )

    logger.info(
        "upload received field=%s filename=%s content_type=%s",
        field,
        name,
        file.content_type,
    )
    destination_dir.mkdir(parents=True, exist_ok=True)
    _require_free_space(destination_dir, field=field)
    staging = _staging_path(destination_dir, name)
    started = time.perf_counter()
    digest = hashlib.sha256()
    total = 0
    try:
        with staging.open("wb") as buffer:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    buffer.close()
                    staging.unlink(missing_ok=True)
                    logger.warning(
                        "upload rejected filename=%s reason=too_large limit_bytes=%s",
                        name,
                        settings.max_upload_bytes,
                    )
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"'{field}' exceeds the maximum upload size of "
                            f"{_human_bytes(settings.max_upload_bytes)}."
                        ),
                    )
                digest.update(chunk)
                buffer.write(chunk)
    except HTTPException:
        raise
    except OSError as exc:
        staging.unlink(missing_ok=True)
        logger.exception("upload write failed filename=%s", name)
        if exc.errno == errno.ENOSPC:
            raise HTTPException(
                status_code=507,
                detail=(
                    f"The server ran out of disk space while storing '{name}'. "
                    "Free space and retry."
                ),
            ) from exc
        raise HTTPException(
            status_code=500,
            detail=f"Could not store '{name}' on the server: {exc}",
        ) from exc
    finally:
        await file.close()

    if total == 0:
        staging.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"'{field}' arrived empty; nothing was uploaded.",
        )

    path = _content_destination(destination_dir, name, digest.hexdigest())
    reused = path.exists() and path.stat().st_size == total
    if reused:
        staging.unlink(missing_ok=True)
    else:
        staging.replace(path)

    logger.info(
        "upload saved original=%s stored_as=%s bytes=%s reused=%s path=%s elapsed_ms=%.1f",
        name,
        path.name,
        total,
        reused,
        path,
        (time.perf_counter() - started) * 1000,
    )
    return path


async def run_analysis(
    stage: str,
    func: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """
    Execute blocking analysis off the event loop and map failures to HTTP.

    A CPU-bound call cannot be interrupted, so a timeout returns 504 while the
    worker thread finishes in the background instead of leaving the socket open
    with no response.
    """

    budget = settings.upload_analysis_timeout_seconds if timeout is None else timeout
    logger.info("%s started timeout_s=%s", stage, budget)
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            run_in_threadpool(func, *args, **kwargs),
            timeout=budget,
        )
    except asyncio.TimeoutError as exc:
        logger.error(
            "%s timed out after %.1fs", stage, time.perf_counter() - started
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"{stage} exceeded the {budget:.0f}s server budget. "
                "The drawing is still being processed; retry with a smaller "
                "page range or raise UPLOAD_ANALYSIS_TIMEOUT_SECONDS."
            ),
        ) from exc
    except HTTPException:
        raise
    except OSError as exc:
        logger.exception("%s failed", stage)
        if exc.errno == errno.ENOSPC:
            prune_documents()
            raise HTTPException(
                status_code=507,
                detail=(
                    f"{stage} ran out of disk space. Stale analysis artifacts "
                    "were reclaimed; retry the upload."
                ),
            ) from exc
        raise HTTPException(
            status_code=500,
            detail=f"{stage} failed: {type(exc).__name__}: {exc}",
        ) from exc
    except Exception as exc:
        # Full traceback goes to the server log; the client gets the reason.
        logger.exception("%s failed", stage)
        raise HTTPException(
            status_code=500,
            detail=f"{stage} failed: {type(exc).__name__}: {exc}",
        ) from exc

    logger.info(
        "%s finished elapsed_ms=%.1f", stage, (time.perf_counter() - started) * 1000
    )
    return result
