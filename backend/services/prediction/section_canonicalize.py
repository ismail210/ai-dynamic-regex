"""Accuracy Track A4 — deterministic family-aware canonicalize helpers.

Format-only: never invent missing dimensions. Round HSS decimal walls stay
decimal; rectangular HSS may use fraction walls. Incomplete L/2L cores are
returned unchanged (abstention is owned elsewhere).
"""

from __future__ import annotations

import re
from typing import Optional

from services.database_loader import catalog_form
from services.normalization import normalize_label_text
from services.token_extractor import normalize_engineering_token


_ROUND_HSS_RE = re.compile(
    r"^HSS\s*(\d+(?:\.\d+)?)\s*[Xx×]\s*(\d+(?:\.\d+)?)$",
    re.I,
)
_RECT_HSS_RE = re.compile(
    r"^HSS\s*(\d+(?:\.\d+)?)\s*[Xx×]\s*(\d+(?:\.\d+)?)\s*[Xx×]\s*(.+)$",
    re.I,
)


def canonicalize_section_text(raw: str) -> str:
    """Deterministic representation cleanup for one printed designation."""

    text = str(raw or "").strip()
    if not text:
        return ""
    normalized = normalize_label_text(text).normalized or normalize_engineering_token(
        text
    )
    compact = str(normalized or text).upper().replace("×", "X").replace(" ", "")
    # Incomplete L/2L (two fields only): preserve core; do not invent thickness.
    if re.fullmatch(r"(?:2L|L)\d+(?:\.\d+)?X\d+(?:\.\d+)?", compact):
        return compact
    form = catalog_form(compact) or catalog_form(normalized) or compact
    return str(form)


def is_format_only_change(raw: str, canonical: str) -> bool:
    """True when canonicalize did not add a dimension field."""

    def _compact(value: str) -> str:
        text = str(value or "").upper().replace("×", "X").replace("✕", "X")
        return re.sub(r"[^A-Z0-9./]", "", text)

    left = _compact(raw)
    right = _compact(canonical)
    if not left or not right:
        return False
    # Same family prefix and same number of X-separated fields.
    return left.count("X") == right.count("X")


def round_vs_rect_hss_class(text: str) -> Optional[str]:
    compact = str(text or "").upper().replace(" ", "").replace("×", "X")
    if _RECT_HSS_RE.match(compact):
        return "rectangular"
    if _ROUND_HSS_RE.match(compact):
        return "round"
    return None
