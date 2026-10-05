"""Page coordinate spaces and the conversions between them.

Two spaces exist for a page stored with ``/Rotate``:

* **PDF space** -- unrotated page coordinates, as PyMuPDF text extraction
  returns them. Everything stored on the extracted document is in PDF space:
  ``words`` / ``lines`` / ``blocks``, ``schedule_grid``, ruled-table records,
  ``column_schedules`` and ``masked_text``. Production geometry never changes
  space.
* **Display space** -- the page as shown, after ``/Rotate``. ``pages[]``
  ``width`` / ``height`` are display dimensions, and the source viewer draws
  highlights in display space.

Drawing Summary sections are the only consumers of display space. Each
section converts once, at its own boundary, with the functions below. For an
unrotated page both spaces are the same.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

BOX_KEYS = frozenset({"bbox", "name_bbox", "elevation_bbox", "key_bbox"})

Box = Callable[[int, Any], Optional[List[float]]]


def to_display(rotation: int, width: float, height: float, bbox: Any) -> List[float]:
    """PDF-space ``bbox`` on a page displayed ``width`` x ``height`` after ``rotation``."""

    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    rotation %= 360
    if rotation == 90:
        x0, y0, x1, y1 = width - y1, x0, width - y0, x1
    elif rotation == 180:
        x0, y0, x1, y1 = width - x1, height - y1, width - x0, height - y0
    elif rotation == 270:
        x0, y0, x1, y1 = y0, height - x1, y1, height - x0
    return [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]


def to_pdf(rotation: int, width: float, height: float, bbox: Any) -> List[float]:
    """Inverse of :func:`to_display`."""

    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    rotation %= 360
    if rotation == 90:
        x0, y0, x1, y1 = y0, width - x1, y1, width - x0
    elif rotation == 180:
        x0, y0, x1, y1 = width - x1, height - y1, width - x0, height - y0
    elif rotation == 270:
        x0, y0, x1, y1 = height - y1, x0, height - y0, x1
    return [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]


def display_boxes(document: Dict[str, Any]) -> Box:
    """``box(page, bbox)``: a PDF-space box of ``document`` in display space."""

    meta = {int(p.get("page_number") or 0): p for p in document.get("pages") or []}

    def box(page: int, bbox: Any) -> Optional[List[float]]:
        if not bbox or len(bbox) < 4:
            return None
        info = meta.get(int(page or 0)) or {}
        return to_display(int(info.get("rotation") or 0), float(info.get("width") or 0),
                          float(info.get("height") or 0), bbox)

    return box


def convert_boxes(value: Any, box: Box, page: Optional[int] = None) -> Any:
    """Copy of ``value`` with every :data:`BOX_KEYS` entry passed through
    ``box(page, bbox)``, where ``page`` is the nearest enclosing ``"page"``."""

    if isinstance(value, dict):
        page = value.get("page", page) if isinstance(value.get("page", page), int) else page
        return {
            key: (box(page, item) if key in BOX_KEYS and isinstance(item, (list, tuple)) and page
                  else convert_boxes(item, box, page))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [convert_boxes(item, box, page) for item in value]
    return value
