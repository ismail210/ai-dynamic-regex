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
_SCALE_LABEL_ONLY = re.compile(r"^SCALE\s*[:.]?\s*$", re.I)
_NOT_TO_SCALE = re.compile(r"\b(?:NOT\s+TO\s+SCALE|NO\s+SCALE|NTS)\b", re.I)


@dataclass(frozen=True)
class DrawingScale:
    raw: str
    paper_inches: float
    real_inches: float
    pdf_points_per_real_inch: float
    source: str
    confidence: float
    page_number: Optional[int] = None

    @property
    def ratio_label(self) -> str:
        return self.raw

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "raw": self.raw,
            "paper_inches": self.paper_inches,
            "real_inches": self.real_inches,
            "pdf_points_per_real_inch": round(self.pdf_points_per_real_inch, 6),
            "source": self.source,
            "confidence": round(self.confidence, 4),
            "scale_value": self.raw,
        }
        if self.page_number is not None:
            payload["page_number"] = self.page_number
        return payload


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


def parse_scale_text(
    text: str,
    *,
    source: str = "text",
    confidence: float = 0.7,
    page_number: Optional[int] = None,
) -> Optional[DrawingScale]:
    """Parse the first trusted scale expression in ``text``."""

    blob = str(text or "")
    if not blob.strip():
        return None
    if _NOT_TO_SCALE.search(blob) and not _ARCH_SCALE.search(blob):
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
                page_number=page_number,
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
                page_number=page_number,
            )
    return None


def _page_of(item: dict) -> Optional[int]:
    for key in ("page_number", "page"):
        value = item.get(key)
        if value is None:
            continue
        try:
            page = int(value)
        except (TypeError, ValueError):
            continue
        if page > 0:
            return page
    return None


def _scale_like_text(text: str) -> bool:
    blob = str(text or "").strip()
    if not blob:
        return False
    if _SCALE_LABEL_ONLY.match(blob):
        return True
    if _ARCH_SCALE.search(blob) or _METRIC_SCALE.search(blob):
        return True
    return bool(re.search(r"\bSCALE\b", blob, re.I))


def _text_blobs(document: Optional[dict]) -> List[tuple[str, str, float, Optional[int]]]:
    """(text, source, confidence, page_number) ordered by trust."""

    if not document:
        return []
    blobs: List[tuple[str, str, float, Optional[int]]] = []
    for block in document.get("title_blocks") or []:
        text = str(block.get("text") or "")
        if _scale_like_text(text) or text.strip():
            blobs.append((text, "title_block", 0.92, _page_of(block)))
    for line in document.get("lines") or []:
        text = str(line.get("text") or "")
        if _scale_like_text(text):
            blobs.append((text, "sheet_line", 0.85, _page_of(line)))
    for block in document.get("blocks") or []:
        text = str(block.get("text") or "")
        if _scale_like_text(text):
            blobs.append((text, "sheet_block", 0.8, _page_of(block)))
    return blobs


def detect_page_scales(document: Optional[dict]) -> Dict[int, DrawingScale]:
    """Best scale found on each page, including SCALE on one line and the ratio on the next."""

    by_page: Dict[int, List[tuple[str, str, float]]] = {}
    unpaged: List[tuple[str, str, float]] = []
    for text, source, confidence, page in _text_blobs(document):
        if page is None:
            unpaged.append((text, source, confidence))
            continue
        by_page.setdefault(page, []).append((text, source, confidence))

    found: Dict[int, DrawingScale] = {}
    for page, blobs in by_page.items():
        parsed = _best_scale_from_blobs(blobs, page_number=page)
        if parsed is not None:
            found[page] = parsed
    if unpaged and not found:
        parsed = _best_scale_from_blobs(unpaged, page_number=None)
        if parsed is not None:
            found[0] = parsed
    return found


def _best_scale_from_blobs(
    blobs: List[tuple[str, str, float]],
    *,
    page_number: Optional[int],
) -> Optional[DrawingScale]:
    best: Optional[DrawingScale] = None
    joined = " ".join(text for text, _source, _conf in blobs)
    candidates = list(blobs)
    if joined.strip():
        source = blobs[0][1] if blobs else "text"
        confidence = max((conf for _text, _source, conf in blobs), default=0.7)
        candidates.append((joined, source, confidence))
    for text, source, confidence in candidates:
        parsed = parse_scale_text(
            text, source=source, confidence=confidence, page_number=page_number
        )
        if parsed is None:
            continue
        if best is None or parsed.confidence > best.confidence:
            best = parsed
    return best


def page_is_nts(document: Optional[dict], page_number: int) -> bool:
    """True when this page's text contains NTS / NOT TO SCALE / NO SCALE."""

    if not document or int(page_number) <= 0:
        return False
    wanted = int(page_number)
    blobs: List[str] = []
    for collection in (
        document.get("title_blocks") or [],
        document.get("lines") or [],
        document.get("blocks") or [],
        document.get("engineering_tokens") or [],
    ):
        for item in collection:
            page = _page_of(item)
            if page != wanted:
                continue
            blobs.append(str(item.get("text") or item.get("raw_text") or ""))
    return bool(_NOT_TO_SCALE.search("\n".join(blobs)))


def resolve_page_scale(
    document: Optional[dict],
    page_number: int,
    *,
    page_scales: Optional[Dict[int, DrawingScale]] = None,
) -> Dict[str, Any]:
    """Scale for one page. Never copies another page's title block.

    A local architectural/metric scale on the same page wins even if the
    page also says NTS (typical: notes sheet with a title-block scale).
    An NTS page with no local scale stays unknown. A page with neither
    stays unknown — document-level ``detect_drawing_scale`` is metadata
    only and is not applied here.
    """

    scales = page_scales if page_scales is not None else detect_page_scales(document)
    local = scales.get(int(page_number))
    nts = page_is_nts(document, page_number)
    if local is not None:
        payload = local.to_dict()
        payload.update(
            {
                "is_nts": nts,
                "scale_fallback": False,
                "scale_reason": "page_scale",
            }
        )
        return payload
    if nts:
        return {
            "scale_value": None,
            "scale_source": "nts",
            "is_nts": True,
            "scale_fallback": False,
            "scale_reason": "nts",
            "raw": None,
            "confidence": 0.0,
        }
    return {
        "scale_value": None,
        "scale_source": None,
        "is_nts": False,
        "scale_fallback": False,
        "scale_reason": "unknown",
        "raw": None,
        "confidence": 0.0,
    }


def detect_drawing_scale(document: Optional[dict]) -> Optional[DrawingScale]:
    """Best document-level scale, preferring title-block text then any page."""

    page_scales = detect_page_scales(document)
    titled = [item for item in page_scales.values() if item.source == "title_block"]
    if titled:
        return max(titled, key=lambda item: item.confidence)
    if page_scales:
        # Prefer an actual sheet page over the unpaged bucket (0).
        numbered = [item for page, item in page_scales.items() if page > 0]
        pool = numbered or list(page_scales.values())
        return min(pool, key=lambda item: item.page_number or 10**9)
    best: Optional[DrawingScale] = None
    for text, source, confidence, page in _text_blobs(document):
        parsed = parse_scale_text(
            text, source=source, confidence=confidence, page_number=page
        )
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


def page_association_radius(
    geometry: Optional[dict],
    page_number: int,
    *,
    default: float = DEFAULT_ASSOCIATION_PDF_POINTS,
) -> float:
    """Association radius for one page. Does not inherit another page's scale."""

    for summary in (geometry or {}).get("page_summaries") or []:
        if int(summary.get("page_number") or 0) != int(page_number):
            continue
        explicit = summary.get("association_radius_pdf_points")
        if explicit is None:
            break
        try:
            return float(explicit)
        except (TypeError, ValueError):
            break
    return float(default)


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
