"""Shared helpers for the corpus R&D pipeline: hashing, safe read-only file
walking, and resumable JSONL writing.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Iterator

logger = logging.getLogger("corpus")

RELEVANT_EXTENSIONS = {
    ".pdf": "pdf",
    ".xls": "excel",
    ".xlsx": "excel",
    ".xlsm": "excel",
    ".dwg": "dwg",
    ".dxf": "dxf",
    ".3dm": "3dm",
    ".3dmbak": "3dm_backup",
    ".gh": "grasshopper",
    ".ghx": "grasshopper",
    ".rhl": "rhino_log",
    ".zip": "archive",
    ".rar": "archive",
    ".7z": "archive",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
}


def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_project_dirs(root: Path) -> Iterator[Path]:
    for child in sorted(root.iterdir()):
        if child.is_dir():
            yield child


def iter_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def classify_extension(path: Path) -> str:
    return RELEVANT_EXTENSIONS.get(path.suffix.lower(), "other")


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class ResumableCache:
    """Keyed-by-sha256 on-disk cache so a long corpus run can resume after a
    crash on one malformed document instead of losing all prior work.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str, pipeline_version: str) -> Path:
        return self.cache_dir / f"{key}__{pipeline_version}.json"

    def get(self, key: str, pipeline_version: str) -> dict | None:
        path = self._path(key, pipeline_version)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def set(self, key: str, pipeline_version: str, payload: dict) -> None:
        write_json(self._path(key, pipeline_version), payload)
