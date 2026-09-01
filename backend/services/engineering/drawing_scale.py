"""Trusted drawing-scale detection from title-block / sheet text.

PDF geometry is stored in paper points. Association radii must be converted
to the same paper units using a parsed architectural or metric scale so
label↔member matching is comparable across plot scales.

When scale cannot be parsed, callers keep the historical 160pt radius.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

DEFAULT_ASSOCIATION_PDF_POINTS = 160.0
# ~8 ft of real-world "nearby" when a trusted scale is available.
TARGET_ASSOCIATION_REAL_INCHES = 96.0
MIN_ASSOCIATION_PDF_POINTS = 48.0
MAX_ASSOCIATION_PDF_POINTS = 280.0
# CAD→PDF members often split with a small paper gap (~1/4" real).
TARGET_FRAGMENT_GAP_REAL_INCHES = 0.25
MIN_FRAGMENT_GAP_PDF_POINTS = 4.0
MAX_FRAGMENT_GAP_PDF_POINTS = 18.0
DEFAULT_FRAGMENT_GAP_PDF_POINTS = 8.0

_FRACTION = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
_ARCH_SCALE = re.compile(
    rf"(?:SCALE\s*[:.]?\s*)?({_FRACTION})\s*[\"″]\s*=\s*"
    rf"(\d+)\s*['′](?:\s*-?\s*(\d+)\s*[\"″]?)?",
    re.I,
)
_METRIC_SCALE = re.compile(
    r"SCALE\s*[:.]?\s*1\s*:\s*(\d+(?:\.\d+)?)",
    re.I,
)
@dataclass(frozen=True)
class DrawingScale:
    raw: str
    paper_inches: float
    real_inches: float
    pdf_points_per_real_inch: float
    source: str
    confidence: float

    @property
    def ratio_label(self) -> str:
        return self.raw

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw": self.raw,
            "paper_inches": self.paper_inches,
            "real_inches": self.real_inches,
            "pdf_points_per_real_inch": round(self.pdf_points_per_real_inch, 6),
            "source": self.source,
            "confidence": round(self.confidence, 4),
            "scale_value": self.raw,
        }


def _parse_inches(text: str) -> Optional[float]:
    value = str(text or "").strip()
    if not value:
        return None
    if " " in value and "/" in value:
        whole, frac = value.split(None, 1)
        num, den = frac.split("/", 1)
        try:
            return float(whole) + float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_scale_text(text: str, *, source: str = "text", confidence: float = 0.7) -> Optional[DrawingScale]:
    """Parse the first trusted scale expression in ``text``."""

    blob = str(text or "")
    if not blob.strip():
        return None
    arch = _ARCH_SCALE.search(blob)
    if arch:
        paper = _parse_inches(arch.group(1))
        feet = float(arch.group(2) or 0)
        extra_inches = float(arch.group(3) or 0)
        real = feet * 12.0 + extra_inches
        if paper and paper > 0 and real > 0:
            return DrawingScale(
                raw=arch.group(0).strip(),
                paper_inches=paper,
                real_inches=real,
                pdf_points_per_real_inch=(paper / real) * 72.0,
                source=source,
                confidence=confidence,
            )
    metric = _METRIC_SCALE.search(blob)
    if metric:
        ratio = float(metric.group(1))
        if ratio > 0:
            return DrawingScale(
                raw=metric.group(0).strip(),
                paper_inches=1.0,
                real_inches=ratio,
                pdf_points_per_real_inch=72.0 / ratio,
                source=source,
                confidence=min(confidence, 0.8),
            )
    return None


def _text_blobs(document: Optional[dict]) -> List[tuple[str, str, float]]:
    """(text, source, confidence) ordered by trust."""

    if not document:
        return []
    blobs: List[tuple[str, str, float]] = []
    for block in document.get("title_blocks") or []:
        text = str(block.get("text") or "")
        if text.strip():
            blobs.append((text, "title_block", 0.92))
    for line in document.get("lines") or []:
        text = str(line.get("text") or "")
        if re.search(r"\bSCALE\b", text, re.I):
            blobs.append((text, "sheet_line", 0.85))
    for block in document.get("blocks") or []:
        text = str(block.get("text") or "")
        if re.search(r"\bSCALE\b", text, re.I):
            blobs.append((text, "sheet_block", 0.8))
    return blobs


def detect_drawing_scale(document: Optional[dict]) -> Optional[DrawingScale]:
    """Best scale found on the sheet, preferring title-block text."""

    best: Optional[DrawingScale] = None
    for text, source, confidence in _text_blobs(document):
        parsed = parse_scale_text(text, source=source, confidence=confidence)
        if parsed is None:
            continue
        if best is None or parsed.confidence > best.confidence:
            best = parsed
    return best


def association_radius_pdf_points(
    scale: Optional[DrawingScale],
    *,
    default: float = DEFAULT_ASSOCIATION_PDF_POINTS,
) -> float:
    """Nearby radius in PDF points for label↔member association."""

    if scale is None or scale.pdf_points_per_real_inch <= 0:
        return float(default)
    raw = TARGET_ASSOCIATION_REAL_INCHES * scale.pdf_points_per_real_inch
    return float(
        min(MAX_ASSOCIATION_PDF_POINTS, max(MIN_ASSOCIATION_PDF_POINTS, raw))
    )


def association_radius_from_geometry(
    geometry: Optional[dict],
    *,
    default: float = DEFAULT_ASSOCIATION_PDF_POINTS,
) -> float:
    if not geometry:
        return float(default)
    explicit = geometry.get("association_radius_pdf_points")
    if explicit is not None:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            return float(default)
    scale_info = geometry.get("scale") or {}
    pts = scale_info.get("pdf_points_per_real_inch")
    if not pts:
        return float(default)
    try:
        synthetic = DrawingScale(
            raw=str(scale_info.get("raw") or ""),
            paper_inches=float(scale_info.get("paper_inches") or 1.0),
            real_inches=float(scale_info.get("real_inches") or 1.0),
            pdf_points_per_real_inch=float(pts),
            source=str(scale_info.get("source") or "geometry"),
            confidence=float(scale_info.get("confidence") or 0.0),
        )
    except (TypeError, ValueError):
        return float(default)
    return association_radius_pdf_points(synthetic, default=default)


def real_inches_from_pdf_points(length_pdf: float, scale: Optional[DrawingScale]) -> Optional[float]:
    if scale is None or scale.pdf_points_per_real_inch <= 0:
        return None
    return float(length_pdf) / scale.pdf_points_per_real_inch


def fragment_gap_pdf_points(
    scale: Optional[DrawingScale],
    *,
    default: float = DEFAULT_FRAGMENT_GAP_PDF_POINTS,
) -> float:
    """Max paper gap between collinear CAD fragments of one member."""

    if scale is None or scale.pdf_points_per_real_inch <= 0:
        return float(default)
    raw = TARGET_FRAGMENT_GAP_REAL_INCHES * scale.pdf_points_per_real_inch
    return float(
        min(MAX_FRAGMENT_GAP_PDF_POINTS, max(MIN_FRAGMENT_GAP_PDF_POINTS, raw))
    )
