"""
Permanent component identity tracking.

Every extracted structural component receives a stable ID that follows it
through prediction, review, validation, and takeoff export.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional, Sequence


_ROLE_PREFIX = {
    "beam": "Beam",
    "column": "Column",
    "brace": "Brace",
    "plate": "Plate",
    "bolt": "Bolt",
    "connection": "Connection",
    "weld": "Weld",
    "footing": "Footing",
    "member": "Member",
    "steel_section": "Section",
}


def _normalize_role(role: Optional[str]) -> str:
    key = str(role or "member").strip().lower().replace(" ", "_")
    return _ROLE_PREFIX.get(key, "Component")


def allocate_component_id(
    *,
    role: Optional[str] = None,
    page: Optional[int] = None,
    bbox: Optional[Sequence[float]] = None,
    text: Optional[str] = None,
    source_file: Optional[str] = None,
) -> str:
    """
    Create a deterministic component ID such as ``Beam_00452``.

    Determinism keeps the same physical object stable across re-runs of the
    same drawing without requiring a central counter store.
    """

    prefix = _normalize_role(role)
    payload = "|".join(
        [
            str(source_file or ""),
            str(page or 0),
            ",".join(f"{float(v):.1f}" for v in (bbox or [])),
            re.sub(r"\s+", "", str(text or "").upper()),
            prefix,
        ]
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    serial = int(digest[:8], 16) % 100000
    return f"{prefix}_{serial:05d}"
