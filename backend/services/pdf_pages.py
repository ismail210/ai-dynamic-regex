"""
Safe PDF page loading for imperfect CAD / permit drawing sets.

Some large structural PDFs report a page_count that includes broken page-tree
entries. Iterating ``for page in doc`` then raises MuPDF ``FzErrorFormat``
(e.g. "cannot find page 15 in page tree") and aborts the whole upload.

Callers should use these helpers so corrupt pages are skipped with a warning
instead of returning HTTP 500.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Generator, Iterable, List, Optional, Tuple

import fitz


logger = logging.getLogger("takeoff.pdf")


def render_page_crop(path: str, page_number: int, bounds: tuple, width: int = 480) -> bytes:
    """Render display-space bounds, with both output dimensions capped at 1200px."""
    if not all(math.isfinite(v) for v in bounds):
        raise ValueError("Crop coordinates must be finite")
    if not 64 <= width <= 1200:
        raise ValueError("Crop width must be between 64 and 1200")
    with fitz.open(str(path)) as pdf:
        if not 1 <= page_number <= pdf.page_count:
            raise IndexError("Page not found")
        sheet = pdf[page_number - 1]
        x0, y0, x1, y1 = bounds
        shown = fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)) & sheet.rect
        if shown.is_empty or shown.width < 4 or shown.height < 4:
            raise ValueError("Empty region")
        zoom = min(width / shown.width, 1200 / shown.height)
        # get_pixmap clips in rotated display space, just like the PDF viewer.
        return sheet.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=shown).tobytes("png")


def iter_pdf_pages(
    document: fitz.Document,
    *,
    skipped: Optional[List[dict]] = None,
) -> Generator[Tuple[int, fitz.Page], None, None]:
    """
    Yield ``(page_index, page)`` for every page that MuPDF can actually load.

    ``page_index`` is 0-based. Failed pages are appended to ``skipped`` when
    provided and never interrupt the caller.
    """

    page_count = int(document.page_count or 0)
    for page_index in range(page_count):
        try:
            page = document.load_page(page_index)
        except Exception as exc:  # MuPDF raises FzErrorFormat / RuntimeError
            record = {
                "page_index": page_index,
                "page_number": page_index + 1,
                "error": f"{type(exc).__name__}: {exc}",
            }
            if skipped is not None:
                skipped.append(record)
            logger.warning(
                "skipping unreadable PDF page %s/%s: %s",
                page_index + 1,
                page_count,
                exc,
            )
            continue
        yield page_index, page


def collect_page_texts(document: fitz.Document) -> Tuple[List[str], List[dict]]:
    """Return per-page text aligned to ``page_count``, with empty strings for skips."""

    skipped: List[dict] = []
    texts = [""] * int(document.page_count or 0)
    for page_index, page in iter_pdf_pages(document, skipped=skipped):
        try:
            texts[page_index] = page.get_text() or ""
        except Exception as exc:
            skipped.append(
                {
                    "page_index": page_index,
                    "page_number": page_index + 1,
                    "error": f"get_text failed: {type(exc).__name__}: {exc}",
                }
            )
            logger.warning("page %s text extraction failed: %s", page_index + 1, exc)
    return texts, skipped


def open_pdf(path: str) -> fitz.Document:
    """Open a PDF path; raise a clear error if the file itself cannot be opened."""

    try:
        return fitz.open(path)
    except Exception as exc:
        raise RuntimeError(
            f"Could not open PDF '{path}': {type(exc).__name__}: {exc}"
        ) from exc
