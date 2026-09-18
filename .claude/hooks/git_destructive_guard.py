#!/usr/bin/env python3
"""PreToolUse guard for Bash: block destructive git commands unless explicitly confirmed.

Blocks: push --force/-f (incl. --force-with-lease is allowed through, it's the safer form),
reset --hard, clean -f/-fd/-fdx, branch -D, checkout -f, and rebase (any form, since this repo
uses partner-branch integration where rebase can silently drop merged partner history).

Override: put the literal token [confirmed-destructive] in the command.
Exit 0 = allow, exit 2 = block (reason on stderr). Fails open on its own errors.
"""

from __future__ import annotations

import json
import re
import sys

DESTRUCTIVE_PATTERNS = (
    (re.compile(r"\bgit\s+push\b.*(\s-f\b|\s--force\b(?!-with-lease))"), "force-push (rewrites remote history)"),
    (re.compile(r"\bgit\s+reset\b.*--hard\b"), "git reset --hard (discards uncommitted work)"),
    (re.compile(r"\bgit\s+clean\b.*-[a-z]*f"), "git clean -f (deletes untracked files)"),
    (re.compile(r"\bgit\s+branch\b.*-D\b"), "git branch -D (force-deletes a branch)"),
    (re.compile(r"\bgit\s+checkout\b.*-f\b"), "git checkout -f (discards local changes)"),
    (re.compile(r"\bgit\s+rebase\b"), "git rebase (repo uses worktrees/partner-merge; rebase can drop history)"),
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0
    if "[confirmed-destructive]" in command:
        return 0

    for pattern, reason in DESTRUCTIVE_PATTERNS:
        if pattern.search(command):
            print(
                f"Blocked: {reason}.\nCommand: {command}\n"
                "This repository's CLAUDE.md requires explicit user approval before destructive "
                "git operations. Confirm with the user first; if they approve, re-run with the "
                "literal token [confirmed-destructive] in the command.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
