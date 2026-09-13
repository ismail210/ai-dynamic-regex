"""DEPRECATED shim -- serialization now lives in
``services.semantic.serialization`` (one canonical ``drawing_semantics.json``
path, Section 29/30). Kept only for existing import paths.
"""

from __future__ import annotations

from services.semantic.serialization import to_dict as to_dict  # noqa: F401
from services.semantic.serialization import to_json as to_json  # noqa: F401
