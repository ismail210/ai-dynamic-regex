"""Debug overlays for association evidence. Not production UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Sequence


def render_association_overlay(
    pdf_path: Path,
    page_number: int,
    row: Dict[str, Any],
    out_path: Path,
    *,
    zoom: float = 1.2,
) -> bool:
    try:
        import fitz
    except ImportError:
        return False
    if not pdf_path.exists():
        return False
    doc = fitz.open(pdf_path)
    if page_number < 1 or page_number > doc.page_count:
        doc.close()
        return False
    page = doc[page_number - 1]
    label_bb = row.get("label_bbox")
    if label_bb and len(label_bb) >= 4:
        page.draw_rect(fitz.Rect(label_bb), color=(0.1, 0.35, 0.9), width=1.6)
    for cand in (row.get("new_candidates") or [])[:5]:
        bb = cand.get("geometry_bbox")
        if not bb or len(bb) < 4:
            continue
        color = (0.15, 0.65, 0.25) if cand.get("rank") == 1 else (0.55, 0.55, 0.55)
        page.draw_rect(fitz.Rect(bb), color=color, width=1.1)
        cl = cand.get("centerline") or []
        if len(cl) >= 2:
            page.draw_line(fitz.Point(*cl[0]), fitz.Point(*cl[-1]), color=color, width=0.8)
    current = row.get("current_association") or {}
    curr_bb = current.get("geometry_bbox")
    if curr_bb and len(curr_bb) >= 4:
        page.draw_rect(fitz.Rect(curr_bb), color=(0.85, 0.35, 0.05), width=1.0, dashes="[2 2]")
    clip = _clip_rect(label_bb, row)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    pix.save(str(out_path))
    doc.close()
    return True


def _clip_rect(label_bb, row: Dict[str, Any]):
    import fitz

    boxes = []
    if label_bb and len(label_bb) >= 4:
        boxes.append(label_bb)
    for cand in (row.get("new_candidates") or [])[:3]:
        if cand.get("geometry_bbox"):
            boxes.append(cand["geometry_bbox"])
    current = (row.get("current_association") or {}).get("geometry_bbox")
    if current:
        boxes.append(current)
    if not boxes:
        return None
    pad = 40.0
    x0 = min(b[0] for b in boxes) - pad
    y0 = min(b[1] for b in boxes) - pad
    x1 = max(b[2] for b in boxes) + pad
    y1 = max(b[3] for b in boxes) + pad
    return fitz.Rect(x0, y0, x1, y1)


def render_v2_comparison_overlay(
    pdf_path: Path,
    page_number: int,
    row: Dict[str, Any],
    out_path: Path,
    *,
    zoom: float = 1.35,
    pad: float = 220.0,
) -> bool:
    """Label-centered crop: gold / baseline / v2 / leader. Does not alter the PDF."""
    try:
        import fitz
    except ImportError:
        return False
    if not pdf_path.exists():
        return False
    doc = fitz.open(pdf_path)
    if page_number < 1 or page_number > doc.page_count:
        doc.close()
        return False
    page = doc[page_number - 1]
    label_bb = row.get("label_bbox")

    def _stroke(bb, color, width, dashes=None):
        if not bb or len(bb) < 4:
            return
        kwargs = {"color": color, "width": width}
        if dashes:
            kwargs["dashes"] = dashes
        page.draw_rect(fitz.Rect(bb), **kwargs)

    def _line(cl, color, width):
        if not cl or len(cl) < 2:
            return
        page.draw_line(fitz.Point(*cl[0]), fitz.Point(*cl[-1]), color=color, width=width)

    # Baseline candidates (gray); top-1 dashed orange
    for cand in (row.get("baseline_candidates") or [])[:5]:
        color = (0.90, 0.45, 0.05) if cand.get("rank") == 1 else (0.55, 0.55, 0.55)
        _stroke(cand.get("geometry_bbox"), color, 1.0, dashes="[2 2]")
        _line(cand.get("centerline"), color, 0.7)
    # V2 candidates (green)
    for cand in (row.get("v2_candidates") or [])[:5]:
        color = (0.05, 0.62, 0.22) if cand.get("rank") == 1 else (0.20, 0.72, 0.40)
        _stroke(cand.get("geometry_bbox"), color, 1.3)
        _line(cand.get("centerline"), color, 1.0)
        ev = cand.get("leader_evidence") or {}
        lid = ev.get("leader_geometry_id")
        if lid:
            for lead in row.get("leader_overlays") or []:
                _stroke(lead.get("geometry_bbox"), (0.55, 0.15, 0.75), 1.1)
                _line(lead.get("centerline") or lead.get("points"), (0.55, 0.15, 0.75), 1.1)
            tp = ev.get("target_point")
            if tp and len(tp) >= 2:
                page.draw_circle(fitz.Point(tp[0], tp[1]), 4.5, color=(0.55, 0.15, 0.75), width=1.2)
    # Human gold (magenta)
    gold_bb = row.get("human_gold_bbox")
    _stroke(gold_bb, (0.80, 0.05, 0.55), 1.8)
    _line(row.get("human_gold_centerline"), (0.80, 0.05, 0.55), 1.6)
    # Label last so it stays readable
    _stroke(label_bb, (0.10, 0.35, 0.92), 2.0)
    if label_bb and len(label_bb) >= 4:
        page.insert_text(
            fitz.Point(label_bb[0], max(8, label_bb[1] - 6)),
            str(row.get("label_text") or row.get("text") or ""),
            fontsize=7,
            color=(0.10, 0.35, 0.92),
        )
    legend_y = (label_bb[1] - 18) if label_bb else 12
    legend_x = (label_bb[0]) if label_bb else 12
    page.insert_text(
        fitz.Point(legend_x, max(10, legend_y)),
        "blue=label  gray/orange=baseline  green=v2  magenta=gold  purple=leader",
        fontsize=6,
        color=(0.1, 0.1, 0.1),
    )

    clip = None
    if label_bb and len(label_bb) >= 4:
        cx = (float(label_bb[0]) + float(label_bb[2])) / 2.0
        cy = (float(label_bb[1]) + float(label_bb[3])) / 2.0
        clip = fitz.Rect(cx - pad, cy - pad, cx + pad, cy + pad)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    pix.save(str(out_path))
    doc.close()
    return True


def render_region_overlay(
    pdf_path: Path,
    page_number: int,
    regions: Sequence[Dict[str, Any]],
    out_path: Path,
    *,
    extra: Sequence[Dict[str, Any]] = (),
    zoom: float = 0.35,
) -> bool:
    try:
        import fitz
    except ImportError:
        return False
    if not pdf_path.exists():
        return False
    doc = fitz.open(pdf_path)
    if page_number < 1 or page_number > doc.page_count:
        doc.close()
        return False
    page = doc[page_number - 1]
    for region in regions:
        bb = region.get("bbox")
        if not bb or len(bb) < 4:
            continue
        page.draw_rect(fitz.Rect(bb), color=(1, 0.2, 0.1), width=1.4)
        page.insert_text(
            fitz.Point(bb[0] + 2, bb[1] + 10),
            str(region.get("region_id") or "region"),
            fontsize=8,
            color=(1, 0, 0),
        )
    for frame in extra:
        bb = frame.get("bbox")
        if not bb or len(bb) < 4:
            continue
        page.draw_rect(fitz.Rect(bb), color=(0.1, 0.2, 0.85), width=1.8)
        page.insert_text(
            fitz.Point(bb[0] + 2, bb[1] + 22),
            str(frame.get("frame_id") or "frame"),
            fontsize=8,
            color=(0.1, 0.2, 0.85),
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(str(out_path))
    doc.close()
    return True
