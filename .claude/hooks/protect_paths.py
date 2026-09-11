#!/usr/bin/env python3
"""PreToolUse guard: block Claude writes to protected / generated / high-risk paths.

Denies Edit/Write/MultiEdit/NotebookEdit whose target is the immutable AISC reference, a
versioned model/experiment artifact, a serialized model binary, a bulk local-data dir, or a
build/cache output. Runtime-updated training files (training/*.csv|*.jsonl|*.json and
training/documents/**) are explicitly allowed — they are normal to edit.

Exit 0 = allow, exit 2 = block (reason on stderr). Fails open on its own errors.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import PurePath

# Paths relative to the repo root.
PROTECTED_PREFIXES = (
    "backend/database/",                       # immutable AISC reference + frozen reports
    "backend/training/models/",                # versioned model registry
    "backend/training/experiments/",           # frozen experiment outputs
    "backend/training/datasets/",              # gitignored bulk data
    "backend/training/pdf/",
    "backend/training/pdfs/",
    "backend/training/excel/",
    "backend/training/excels/",
    "backend/training/engineering_artifacts/",
    "backend/training/takeoff_exports/",
    "backend/training/legend_profiles/",
    "backend/training/ml_association/real_project_pilot/",
    "backend/uploads/",
    "backend/catboost_info/",
    "frontend/dist/",
    "research/",
)

PROTECTED_SUFFIXES = (
    ".pt", ".pth", ".pkl", ".joblib", ".onnx", ".cbm",
    ".h5", ".safetensors", ".bin", ".xlsx", ".xls", ".pdf",
)

# Directory segments that are always vendored / generated.
PROTECTED_SEGMENTS = {"node_modules", "__pycache__", ".pytest_cache", ".vite", ".mypy_cache"}


def _reason(rel: str) -> str | None:
    rel = rel.replace("\\", "/").lstrip("./")
    parts = PurePath(rel).parts
    base = parts[-1].lower() if parts else rel.lower()

    if PROTECTED_SEGMENTS.intersection(parts):
        return f"{rel} is inside a vendored/generated directory"
    for pref in PROTECTED_PREFIXES:
        if rel.startswith(pref):
            return f"{rel} is under protected path {pref!r}"
    if base.endswith(PROTECTED_SUFFIXES):
        return f"{rel} is a binary/model/spreadsheet/PDF artifact"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover
        print(f"protect_paths: unreadable hook input: {exc}", file=sys.stderr)
        return 0

    tool_input = payload.get("tool_input") or {}
    raw = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("notebook_path")
    )
    if not raw:
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    try:
        abs_target = os.path.realpath(
            raw if os.path.isabs(raw) else os.path.join(root, raw)
        )
        rel = os.path.relpath(abs_target, os.path.realpath(root))
    except ValueError:
        return 0  # different drive / outside root

    if rel.startswith(".."):
        return 0

    reason = _reason(rel)
    if reason:
        print(
            f"Blocked write: {reason}. This is a protected/generated artifact and is not "
            "hand-edited. If the task genuinely requires regenerating it, tell the user and "
            "have them confirm, or regenerate it via the documented training/build scripts. "
            "(Runtime training files like training/*.csv|*.jsonl|*.json and training/documents/ "
            "are allowed.)",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
