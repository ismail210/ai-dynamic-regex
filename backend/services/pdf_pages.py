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
from typing import Any, Generator, Iterable, List, Optional, Tuple

import fitz


logger = logging.getLogger("takeoff.pdf")


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
