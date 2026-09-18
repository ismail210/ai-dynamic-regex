#!/usr/bin/env python3
"""PreToolUse guard: block Read/Edit/Write on credential-pattern files unless explicitly allowed.

Covers .env* (except .env.example / .env.sample templates), key/cert files, and common
credential-store filenames. Applies to Read as well as Edit/Write, since the risk is Claude
echoing a secret into the transcript or a report, not just modifying one.

Override: set ALLOW_SECRET_FILE_ACCESS=1 in the environment for a session where the user has
explicitly authorized it.
Exit 0 = allow, exit 2 = block (reason on stderr). Fails open on its own errors.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import PurePath

SAFE_BASENAMES = {".env.example", ".env.sample", ".env.template"}

SECRET_BASENAME_PATTERNS = (
    re.compile(r"^\.env(\..+)?$"),
    re.compile(r"credentials.*\.(json|ya?ml|txt)$", re.I),
    re.compile(r"^id_(rsa|ed25519|ecdsa)$"),
    re.compile(r"\.(pem|key|p12|pfx)$", re.I),
    re.compile(r"^secrets?\.(json|ya?ml|txt)$", re.I),
)


def main() -> int:
    if os.environ.get("ALLOW_SECRET_FILE_ACCESS") == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("path")
    if not raw:
        return 0

    base = PurePath(raw.replace("\\", "/")).name
    if base in SAFE_BASENAMES:
        return 0

    for pattern in SECRET_BASENAME_PATTERNS:
        if pattern.search(base):
            print(
                f"Blocked: {raw} looks like a credential/secret file ({base}). "
                "If the user has explicitly authorized this access, ask them to set "
                "ALLOW_SECRET_FILE_ACCESS=1 for the session, or share only the specific value "
                "needed rather than the whole file.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
