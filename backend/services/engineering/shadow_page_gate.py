"""Measure-only skip of geometry and per-token predict on legend context pages.

Default off. Counts are always available; objects and tokens are removed only
when ``shadow_context_page_gate_enabled`` is set. Pages are taken from
``legend_profile.context_pages`` — never from ``engineering_relevance_score``
and never from a bare ``other`` category.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set


def context_page_ids(document: Dict[str, Any]) -> Set[int]:
    profile = document.get("legend_profile") or {}
    raw = profile.get("context_pages") or {}
    pages: Set[int] = set()
    if isinstance(raw, dict):
        for key in raw:
            try:
                pages.add(int(key))
            except (TypeError, ValueError):
                continue
    return pages


def _page_of(obj: Dict[str, Any]) -> int:
    try:
        return int(obj.get("page_number") or obj.get("page") or 0)
    except (TypeError, ValueError):
        return 0


def shadow_context_report(
    document: Dict[str, Any],
    geometry: Dict[str, Any] | None = None,
    tokens: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Counts only. Does not drop objects."""

    pages = context_page_ids(document)
    objects = list((geometry or {}).get("objects") or [])
    token_list = list(tokens or [])
    return {
        "applied": False,
        "context_pages": sorted(pages),
        "geometry_objects_total": len(objects),
        "geometry_objects_on_context_pages": sum(
            1 for obj in objects if _page_of(obj) in pages
        ),
        "prediction_tokens_total": len(token_list),
        "prediction_tokens_on_context_pages": sum(
            1 for token in token_list if _page_of(token) in pages
        ),
    }


def filter_context_page_objects(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
) -> Dict[str, Any]:
    pages = context_page_ids(document)
    kept = [
        obj
        for obj in (geometry.get("objects") or [])
        if _page_of(obj) not in pages
    ]
    return {**geometry, "objects": kept}


def filter_context_page_tokens(
    document: Dict[str, Any],
    tokens: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    pages = context_page_ids(document)
    return [token for token in tokens if _page_of(token) not in pages]
