"""Shared synthetic-geometry builders for engineering/geometry test suites."""

from __future__ import annotations


def line_fragment(page: int, x0: float, y0: float, x1: float, y1: float, gid: str) -> dict:
    """A single straight-line CAD fragment, in the raw object shape
    ``services.engineering.geometry_normalizer.merge_collinear_fragments``
    consumes."""
    return {
        "geometry_id": gid,
        "kind": "line",
        "page_number": page,
        "page": page,
        "bbox": [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)],
        "points": [[x0, y0], [x1, y1]],
        "orientation": 0.0,
        "length": abs(x1 - x0) + abs(y1 - y0),
    }
