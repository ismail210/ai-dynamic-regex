"""Ingest on-drawing schedule tables into prediction tokens.

When a member is listed in a PDF schedule (framing/column table on the
sheet) but not written as a callout next to the drawn linework, text-only
extraction misses it entirely. This module reads schedule regions detected
during extraction and emits synthetic tokens so those members enter the
takeoff and validation comparison.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional, Set

from services.structural_parser import parse_section
from services.token_extractor import normalize_engineering_token

_SHAPE_TOKEN_RE = re.compile(
    r"\b(?:W|WT|S|M|HP|C|MC)\s*\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?\b"
    r"|\bHSS\s*\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?"
    r"(?:\s*[X×]\s*(?:\d+/\d+|\d+(?:\.\d+)?))?\b"
    r"|\b(?:L|2L)\s*\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?"
    r"(?:\s*[X×]\s*(?:\d+/\d+|\d+(?:\.\d+)?))?\b"
    r"|\bPIPE\s*\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
_QTY_RE = re.compile(
    r"\b(?:QTY|QTY\.|QUANTITY|COUNT|CT)\s*[:.]?\s*(\d{1,3})\b",
    re.IGNORECASE,
)
_TRAILING_QTY_RE = re.compile(r"\b(\d{1,3})\s*$")


def _norm(text: str) -> str:
    return normalize_engineering_token(text)


def _existing_shapes(tokens: Iterable[dict]) -> Set[str]:
    shapes: Set[str] = set()
    for token in tokens:
        text = str(token.get("text") or token.get("raw_text") or "").strip()
        if not text:
            continue
        shapes.add(_norm(text))
        for match in _SHAPE_TOKEN_RE.finditer(text):
            shapes.add(_norm(match.group(0)))
    return shapes


def _extract_shape(line: str) -> Optional[str]:
    match = _SHAPE_TOKEN_RE.search(line)
    if not match:
        return None
    shape = _norm(match.group(0))
    if not parse_section(shape):
        return None
    return shape


def _extract_quantity(line: str, *, default: int = 1) -> int:
    for pattern in (_QTY_RE, _TRAILING_QTY_RE):
        match = pattern.search(line.strip())
        if match:
            qty = int(match.group(1))
            if 1 <= qty <= 200:
                return qty
    return default


def _stable_token_id(page: int, shape: str, index: int) -> str:
    seed = f"schedule|{page}|{shape}|{index}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"schedule_{digest}"


def parse_schedule_entries(document: Dict[str, Any]) -> List[dict]:
    """Parse shape + quantity rows from on-drawing schedule regions."""

    entries: List[dict] = []
    seen: Set[tuple] = set()
    sources = list(document.get("schedules") or [])
    for table in document.get("tables") or []:
        if table.get("table_type") != "takeoff":
            continue
        text = "\n".join(
            str(cell)
            for row in (table.get("rows") or [])
            for cell in row
        )
        sources.append(
            {
                "schedule_id": f"table_{table.get('table_id')}",
                "page_number": table.get("page_number"),
                "bbox": table.get("bbox"),
                "text": text,
                "confidence": table.get("confidence", 0.65),
            }
        )

    for schedule in sources:
        page = int(schedule.get("page_number") or 0)
        bbox = schedule.get("bbox") or [0, 0, 0, 0]
        for line in str(schedule.get("text") or "").splitlines():
            cleaned = line.strip()
            if not cleaned or len(cleaned) < 4:
                continue
            shape = _extract_shape(cleaned)
            if not shape:
                continue
            qty = _extract_quantity(cleaned)
            key = (page, shape, qty, cleaned.upper())
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "shape": shape,
                    "quantity": qty,
                    "page_number": page,
                    "bbox": bbox,
                    "schedule_id": schedule.get("schedule_id"),
                    "source_line": cleaned,
                    "confidence": float(schedule.get("confidence") or 0.7),
                }
            )
    return entries


def build_schedule_tokens(
    document: Dict[str, Any],
    *,
    existing_tokens: Optional[List[dict]] = None,
) -> List[dict]:
    """Create engineering tokens for schedule-only members."""

    tokens = list(existing_tokens or document.get("engineering_tokens") or [])
    on_drawing = _existing_shapes(tokens)
    schedule_tokens: List[dict] = []

    for entry in parse_schedule_entries(document):
        shape = entry["shape"]
        if shape in on_drawing:
            continue
        qty = int(entry.get("quantity") or 1)
        page = int(entry.get("page_number") or 1)
        bbox = list(entry.get("bbox") or [0, 0, 0, 0])
        for index in range(qty):
            token_id = _stable_token_id(page, shape, index)
            schedule_tokens.append(
                {
                    "token_id": token_id,
                    "text": shape,
                    "raw_text": shape,
                    "normalized_text": shape,
                    "page": page,
                    "bbox": bbox,
                    "confidence": entry.get("confidence", 0.72),
                    "engineering_object_type": "schedule_member",
                    "schedule_sourced": True,
                    "extraction_method": "schedule_on_drawing",
                    "schedule_id": entry.get("schedule_id"),
                    "schedule_source_line": entry.get("source_line"),
                    "region_id": entry.get("region_id"),
                }
            )
        on_drawing.add(shape)

    return schedule_tokens
