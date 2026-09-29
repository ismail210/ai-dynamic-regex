"""Development-only identity of this backend process.

The Vite dev server proxies to whatever listens on its target port, and
several worktrees of this repo run side by side. The frontend compares this
identity with its own so it never renders another worktree's API responses.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter

from services.engineering.drawing_intelligence import DRAWING_INTELLIGENCE_VERSION

router = APIRouter()

# The worktree is derived from this source file, never from the interpreter,
# because one venv is routinely shared by several worktrees.
WORKTREE = Path(__file__).resolve().parents[2]


def _startup_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=WORKTREE,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


STARTUP_REVISION = _startup_revision()


@router.get("/dev/identity")
def dev_identity():
    return {
        "worktree": str(WORKTREE),
        "revision": STARTUP_REVISION,
        "summary_api": DRAWING_INTELLIGENCE_VERSION,
    }
