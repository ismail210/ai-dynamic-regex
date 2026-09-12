"""``drawing_semantics.json`` sidecar serialization (Section 38).

The JSON is the authoritative semantic ledger; a corrected PDF (not
implemented in this session -- Section 39) is a compatibility artifact
derived from it later. Round-tripping through JSON must be lossless for
every field on ``SemanticDocument``.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from services.semantic_preprocessor.models import SemanticDocument


def to_json(document: SemanticDocument, *, indent: int = 2) -> str:
    return json.dumps(document.to_dict(), indent=indent, sort_keys=False)


def to_dict(document: SemanticDocument) -> Dict[str, Any]:
    return document.to_dict()
