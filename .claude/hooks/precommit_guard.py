#!/usr/bin/env python3
"""PreToolUse guard for `git commit`: inspect the staged set and block risky commits.

Runs only when Claude runs a git-commit command (scoped by the hook `if` field).

Blocks when the staged set contains:
  - a serialized model binary (.pt/.pkl/.joblib/.onnx/...) anywhere;
  - a versioned model/experiment artifact or the immutable AISC reference
    (backend/training/models|experiments/**, backend/database/**);
  - another binary blob type (.xlsx/.pdf/.zip/...);
  - whitespace errors in a *source* file (git diff --cached --check).

It deliberately does NOT block large `backend/training/*.csv|*.jsonl|*.json` or
`backend/training/documents/**` — the team commits those during the normal learning loop.

Override: put the literal token [allow-artifacts] in the commit message.
Exit 0 = allow, exit 2 = block. Fails open on its own errors.
"""

from __future__ import annotations

import json
import subprocess
import sys

BLOCK_PREFIXES = (
    "backend/database/",
    "backend/training/models/",
    "backend/training/experiments/",
)
BLOCK_SUFFIXES = (
    ".pt", ".pth", ".pkl", ".joblib", ".onnx", ".cbm",
    ".h5", ".safetensors", ".bin", ".xlsx", ".xls", ".pdf", ".zip",
)
# Whitespace check applies only to hand-written source, never to data files.
CODE_SUFFIXES = (".py", ".js", ".jsx", ".css", ".html")


def _run(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False
    ).stdout


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")
    if "[allow-artifacts]" in command:
        return 0

    staged = [
        line.split("\t", 1)
        for line in _run("diff", "--cached", "--name-status").splitlines()
        if line.strip()
    ]
    if not staged:
        return 0

    problems: list[str] = []
    code_paths: list[str] = []
    for entry in staged:
        if len(entry) != 2:
            continue
        status, path = entry[0].strip(), entry[1].strip().replace("\\", "/")
        if status.startswith("D"):
            continue
        low = path.lower()
        if any(path.startswith(p) for p in BLOCK_PREFIXES):
            problems.append(f"protected artifact path: {path}")
        elif low.endswith(BLOCK_SUFFIXES):
            problems.append(f"binary/model artifact: {path}")
        if low.endswith(CODE_SUFFIXES) and not path.startswith("backend/training/"):
            code_paths.append(path)

    if code_paths:
        ws = _run("diff", "--cached", "--check", "--", *code_paths)
        if ws.strip():
            problems.append("whitespace errors in staged source (git diff --cached --check)")

    if problems:
        print(
            "Commit blocked by precommit_guard:\n  - "
            + "\n  - ".join(dict.fromkeys(problems))
            + "\n\nUnstage these paths, or — if committing them is genuinely intended (e.g. a "
            "promoted runtime model, an intentional catalog update) — re-run the commit with "
            "[allow-artifacts] in the message.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
