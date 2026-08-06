"""
Coalescing and throttling for the heavy document stages.

Extraction and analysis are CPU-bound. Two problems appear without control:
duplicate clicks or browser retries start the same work twice, and several
stages running at once make every one of them slower because they compete for
the GIL while also starving the upload endpoint.

A stage therefore runs at most once per document at a time, later callers join
the run already in progress, and the number of concurrent stages is bounded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Dict, TypeVar

from config import settings


logger = logging.getLogger("takeoff.stages")

T = TypeVar("T")

_INFLIGHT: Dict[str, "asyncio.Task"] = {}
_DOCUMENT_LOCKS: Dict[str, asyncio.Lock] = {}
_LIMITERS: Dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def _limiter() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    limiter = _LIMITERS.get(loop)
    if limiter is None:
        limiter = asyncio.Semaphore(max(1, int(settings.stage_concurrency)))
        _LIMITERS[loop] = limiter
    return limiter


def _document_lock(document_id: str) -> asyncio.Lock:
    lock = _DOCUMENT_LOCKS.get(document_id)
    if lock is None:
        lock = asyncio.Lock()
        _DOCUMENT_LOCKS[document_id] = lock
    return lock


def inflight_stages() -> Dict[str, float]:
    """Return running stage keys with their elapsed seconds."""

    now = time.perf_counter()
    return {
        key: round(now - getattr(task, "_stage_started", now), 1)
        for key, task in _INFLIGHT.items()
        if not task.done()
    }


async def run_shared_stage(
    *,
    stage: str,
    document_id: str,
    runner: Callable[[], Awaitable[T]],
) -> T:
    """Run one stage per document, sharing the result with parallel callers."""

    key = f"{stage}:{document_id}"
    running = _INFLIGHT.get(key)
    if running is not None and not running.done():
        logger.info("%s joined in-flight run document=%s", stage, document_id)
        # Shielding keeps the shared run alive when one client disconnects.
        return await asyncio.shield(running)

    async def _execute() -> T:
        async with _document_lock(document_id):
            async with _limiter():
                return await runner()

    task = asyncio.create_task(_execute())
    task._stage_started = time.perf_counter()  # type: ignore[attr-defined]
    _INFLIGHT[key] = task
    task.add_done_callback(
        lambda finished: _INFLIGHT.pop(key, None)
        if _INFLIGHT.get(key) is finished
        else None
    )
    return await asyncio.shield(task)
