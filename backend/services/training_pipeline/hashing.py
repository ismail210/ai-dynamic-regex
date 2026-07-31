"""Checksum and deterministic identity helpers for versioned artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(stable_json(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(*, modality: str, payload: dict) -> str:
    return sha256_json({"modality": modality, **payload})


def sample_id(*, modality: str, source_type: str, source_id: str, content: str) -> str:
    return sha256_text(f"{modality}|{source_type}|{source_id}|{content}")[:24]


def checksum_paths(paths: Iterable[Path]) -> dict:
    return {
        path.name: sha256_file(path) for path in paths if path.exists() and path.is_file()
    }
