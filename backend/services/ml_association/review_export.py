"""Deterministic reviewer export: JSON group metadata + page-local SVG.

Uses PyMuPDF's own ``Page.get_svg_image()`` for the base page render
(no new rendering dependency, per the Phase 2 spec's explicit
instruction) and overlays a highlight ``<g>`` group with the source
label, numbered candidate geometries, an estimated leader path where
resolved, and the current heuristic's pick (shown as evidence, not
truth). Both outputs are byte-identical across repeated runs given the
same inputs (see backend/tests/test_ml_association_review_export.py's
reproducibility test) -- there is no timestamp, random ID, or
wall-clock value anywhere in either artifact.

This is a backend/offline artifact only in this phase. It does not
touch, build, or import anything under frontend/ -- see the Phase 2
spec's explicit instruction not to modify the production React Results
page.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import fitz

from services.ml_association.schemas import (
    NO_MATCH_CANDIDATE_TOKEN,
    LabelGroup,
    ReviewExportPayload,
)

_LABEL_COLOR = "#1d4ed8"  # blue
_CANDIDATE_COLOR = "#059669"  # green
_HEURISTIC_COLOR = "#d97706"  # amber
_LEADER_PATH_COLOR = "#7c3aed"  # violet
_NEARBY_LABEL_COLOR = "#6b7280"  # gray


def _rect_markup(bbox, *, color: str, stroke_width: float = 2.0, dash: Optional[str] = None) -> str:
    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    x, y = min(x0, x1), min(y0, y1)
    width, height = abs(x1 - x0), abs(y1 - y0)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(width, 1):.2f}" '
        f'height="{max(height, 1):.2f}" fill="none" stroke="{color}" '
        f'stroke-width="{stroke_width}"{dash_attr} />'
    )


def _line_markup(a, b, *, color: str, dash: str = "4,3") -> str:
    return (
        f'<line x1="{float(a[0]):.2f}" y1="{float(a[1]):.2f}" '
        f'x2="{float(b[0]):.2f}" y2="{float(b[1]):.2f}" stroke="{color}" '
        f'stroke-width="1.5" stroke-dasharray="{dash}" />'
    )


def _text_markup(x: float, y: float, text: str, *, color: str, size: float = 9.0) -> str:
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" fill="{color}" font-size="{size}" '
        f'font-family="monospace">{escaped}</text>'
    )


def build_overlay_markup(
    group: LabelGroup,
    *,
    heuristic_selection_candidate_id: Optional[str],
    nearby_label_bboxes: Optional[dict] = None,
) -> str:
    """Build the SVG ``<g>`` overlay for one label group.

    Deterministic: candidates are drawn in the group's already-stable
    order (``group.candidates``, itself sorted by ``candidate_dataset``),
    so rank numbers and draw order never vary between runs.
    """

    parts = ['<g id="ml_association_overlay" font-weight="bold">']

    label = group.label
    parts.append(_rect_markup(label.text_bbox, color=_LABEL_COLOR, stroke_width=2.5))
    parts.append(
        _text_markup(
            label.text_bbox[0],
            max(label.text_bbox[1] - 4, 8),
            f"LABEL: {label.raw_text}",
            color=_LABEL_COLOR,
        )
    )

    rank = 0
    for candidate in group.candidates:
        if candidate.is_no_match_placeholder or candidate.geometry is None:
            continue
        rank += 1
        is_heuristic_pick = candidate.association_candidate_id == heuristic_selection_candidate_id
        color = _HEURISTIC_COLOR if is_heuristic_pick else _CANDIDATE_COLOR
        parts.append(_rect_markup(candidate.geometry.geometry_bbox, color=color))
        caption = f"#{rank} {candidate.association_candidate_id[:12]}"
        if is_heuristic_pick:
            caption += " (current heuristic pick -- evidence, not truth)"
        parts.append(
            _text_markup(
                candidate.geometry.geometry_bbox[0],
                max(candidate.geometry.geometry_bbox[1] - 4, 8),
                caption,
                color=color,
            )
        )

        if candidate.relationship.leader_support_evidence:
            # Approximate leader path: label center -> candidate center.
            # A true multi-segment leader polyline would need raw line
            # points, which are not carried onto graph/geometry-evidence
            # nodes -- see feature_builder.py's docstring for the same
            # documented approximation.
            parts.append(
                _line_markup(
                    label.text_center, candidate.geometry.geometry_center, color=_LEADER_PATH_COLOR
                )
            )

    for nearby_id, bbox in (nearby_label_bboxes or {}).items():
        parts.append(_rect_markup(bbox, color=_NEARBY_LABEL_COLOR, stroke_width=1.0, dash="2,2"))

    parts.append(
        _text_markup(
            8,
            16,
            f"no-valid-target option id: {NO_MATCH_CANDIDATE_TOKEN} | multi-target supported",
            color=_NEARBY_LABEL_COLOR,
            size=8.0,
        )
    )
    parts.append("</g>")
    return "".join(parts)


@lru_cache(maxsize=256)
def render_page_svg(pdf_path: str, page_number: int) -> str:
    """Render one page's base SVG via PyMuPDF (deterministic, vector).

    Cached per ``(pdf_path, page_number)``. Real structural sheets can
    carry hundreds of label groups on a single page (Phase 2.5 pilot
    found pages with 200+), and ``write_group_export`` is called once
    per group -- without this cache, a dense real page re-opens the PDF
    and re-renders the identical multi-megabyte base SVG once per group,
    which is what caused the pilot to time out on real project data.
    The render is a pure function of its two arguments (PyMuPDF's
    ``get_svg_image()`` has no side effects and no hidden state), so
    caching cannot introduce staleness within one process.
    """

    with fitz.open(pdf_path) as doc:
        page = doc[page_number - 1]
        return page.get_svg_image()


def compose_export_svg(base_svg: str, overlay_markup: str) -> str:
    """Inject the highlight overlay into a PyMuPDF-rendered base SVG."""

    marker = "</svg>"
    index = base_svg.rfind(marker)
    if index == -1:
        # Defensive: still return something usable/diffable rather than
        # raising, since this is an offline reviewer artifact, not a
        # production response.
        return base_svg + overlay_markup
    return base_svg[:index] + overlay_markup + base_svg[index:]


def build_export_payload(
    group: LabelGroup,
    *,
    svg_relative_path: str,
) -> ReviewExportPayload:
    return ReviewExportPayload(
        group=group,
        svg_relative_path=svg_relative_path,
        heuristic_selection_candidate_id=group.selected_candidate_id(),
    )


def write_group_export(
    group: LabelGroup,
    *,
    pdf_path: str,
    output_dir: Path,
    nearby_label_bboxes: Optional[dict] = None,
) -> ReviewExportPayload:
    """Write one group's JSON metadata + SVG to ``output_dir``.

    File names are derived from the deterministic ``group.group_id``,
    so re-running an export for the same group overwrites the same two
    files with (given identical inputs) identical bytes, rather than
    accumulating timestamped duplicates.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    svg_filename = f"{group.group_id}.svg"
    json_filename = f"{group.group_id}.json"

    base_svg = render_page_svg(pdf_path, group.page_number)
    overlay = build_overlay_markup(
        group,
        heuristic_selection_candidate_id=group.selected_candidate_id(),
        nearby_label_bboxes=nearby_label_bboxes,
    )
    full_svg = compose_export_svg(base_svg, overlay)
    (output_dir / svg_filename).write_text(full_svg, encoding="utf-8")

    payload = build_export_payload(group, svg_relative_path=svg_filename)
    (output_dir / json_filename).write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload
