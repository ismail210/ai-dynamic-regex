"""Normalize separators and OCR glyphs without overwriting raw text."""

from __future__ import annotations

import re
from typing import Any


_SEP = re.compile(r"[xX×✕✖*]|\s*[xX×✕✖]\s*")
_WS = re.compile(r"\s+")
_DEG = re.compile(r"(?:°|deg(?:rees?)?)", re.I)


ORIENTATION_BIN_DEGREES = {
    "horizontal": 0.0,
    "vertical": 90.0,
    "diagonal": 45.0,
}


def as_float(value: Any) -> float | None:
    """Coerce mixed pipeline values to degrees/numbers, never raising.

    Geometry and graph producers may emit coarse orientation bins such as
    ``"horizontal"`` where a numeric angle is expected.
    """

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    binned = ORIENTATION_BIN_DEGREES.get(text.lower())
    if binned is not None:
        return binned
    try:
        return float(text)
    except ValueError:
        return None


def as_int(value: Any) -> int | None:
    """Coerce page numbers and counters without raising."""

    number = as_float(value)
    return int(number) if number is not None else None


def safe_bbox(value: Any) -> list[float] | None:
    """Return a 4-number bbox, or ``None`` when the value is unusable."""

    if not isinstance(value, (list, tuple)):
        return None
    numbers = [as_float(item) for item in value]
    if len(numbers) != 4 or any(item is None for item in numbers):
        return None
    return [float(item) for item in numbers]


def orientation_bin_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text if text in ORIENTATION_BIN_DEGREES else None


def soft_normalize(text: str) -> str:
    """Case/space/separator normalize; never invents engineering meaning."""

    value = str(text or "").strip()
    value = value.replace("×", "X").replace("✕", "X").replace("✖", "X")
    value = _WS.sub(" ", value)
    return value


def compact_normalize(text: str) -> str:
    value = soft_normalize(text).upper().replace(" ", "")
    value = value.replace("*", "")
    return value


def split_dimension_parts(text: str) -> list[str]:
    """Split ``6x4x5/6`` / ``6 X 4 X 5/6`` into dimension tokens."""

    value = soft_normalize(text)
    value = re.sub(
        r"^(?:\d+/\d+|\d+(?:\.\d+)?)\"?\s*"
        r"(?:BENT\s*PL(?:ATE)?|(?:CAP|CONN(?:ECTION)?)\s+PL(?:ATE)?|PL(?:ATE)?)\s*",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"^(?:(?:CAP|CONN(?:ECTION)?)\s+PL(?:ATE)?|PL|PLATE|BP|BENT\s*PL(?:ATE)?)\s*",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"@\s*.*$", "", value).strip()
    if not value:
        return []
    parts = [part.strip() for part in re.split(r"[xX×✕✖]", value) if part.strip()]
    return parts


def parse_angle_degrees(text: str) -> float | None:
    match = re.search(r"@\s*([-+]?\d+(?:\.\d+)?)\s*(?:°|deg)?", soft_normalize(text), re.I)
    if not match:
        match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(?:°|deg(?:rees?)?)", soft_normalize(text), re.I)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None
