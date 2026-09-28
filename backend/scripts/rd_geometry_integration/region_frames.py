"""Title-seeded detail frames + IoU vs auto regions. Soft evidence only."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TITLE = re.compile(
    r"\b(TYPICAL\b.{0,60}\bDETAIL|SECTION(?:\s+\d+)?|DETAIL\s+[A-Z0-9]+)\b",
    re.I,
)


def _center(bbox: Sequence[float]) -> Tuple[float, float]:
    return ((float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0)


def bbox_iou(a: Sequence[float], b: Sequence[float]) -> float:
    x0 = max(float(a[0]), float(b[0]))
    y0 = max(float(a[1]), float(b[1]))
    x1 = min(float(a[2]), float(b[2]))
    y1 = min(float(a[3]), float(b[3]))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area_a = max(0.0, float(a[2]) - float(a[0])) * max(0.0, float(a[3]) - float(a[1]))
    area_b = max(0.0, float(b[2]) - float(b[0])) * max(0.0, float(b[3]) - float(b[1]))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def seed_title_frames(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    page_number: int,
    *,
    grow: float = 220.0,
) -> List[Dict[str, Any]]:
    """Grow a candidate frame from detail/section titles + nearby geometry.

    These are research_proposed_frames, not human gold.
    """
    page_w, page_h = 3024.0, 2160.0
    for page in document.get("pages") or []:
        if int(page.get("page_number") or 0) == page_number:
            page_w = float(page.get("width") or page_w)
            page_h = float(page.get("height") or page_h)
            break

    titles = []
    for token in document.get("engineering_tokens") or []:
        if int(token.get("page") or 0) != page_number:
            continue
        text = str(token.get("text") or "")
        if not token.get("bbox") or not _TITLE.search(text):
            continue
        titles.append({"text": text, "bbox": token["bbox"]})
    if not titles:
        for line in document.get("lines") or []:
            if int(line.get("page_number") or line.get("page") or 0) != page_number:
                continue
            text = str(line.get("text") or "").strip()
            bbox = line.get("bbox")
            if not bbox or not _TITLE.search(text):
                continue
            cx, cy = _center(bbox)
            if cx > page_w * 0.88 or cy > page_h * 0.88:
                continue
            if text.upper() in {"TYPICAL DETAILS", "SECTIONS", "SECTION"}:
                if text.upper() == "SECTION":
                    titles.append({"text": text, "bbox": bbox})
                continue
            titles.append({"text": text, "bbox": bbox})

    geos = [
        o
        for o in (geometry.get("objects") or [])
        if int(o.get("page_number") or o.get("page") or 0) == page_number and o.get("bbox")
    ]
    frames: List[Dict[str, Any]] = []
    for i, title in enumerate(titles):
        tb = title["bbox"]
        tcx, tcy = _center(tb)
        xs0, ys0, xs1, ys1 = [tb[0]], [tb[1]], [tb[2]], [tb[3]]
        geo_n = 0
        for obj in geos:
            bb = obj["bbox"]
            cx, cy = _center(bb)
            if math.hypot(cx - tcx, cy - tcy) <= grow:
                xs0.append(bb[0])
                ys0.append(bb[1])
                xs1.append(bb[2])
                ys1.append(bb[3])
                geo_n += 1
        bbox = [round(min(xs0), 2), round(min(ys0), 2), round(max(xs1), 2), round(max(ys1), 2)]
        frames.append(
            {
                "frame_id": f"p{page_number}_title_frame_{i}",
                "page": page_number,
                "bbox": bbox,
                "title_text": title.get("text"),
                "terminology": "detail_region_candidate",
                "provenance": "research_proposed_frame",
                "evidence": ["title_pattern_seed", f"grow_pt={grow}", "nearby_geometry_union"],
                "contained_geometry_count": geo_n,
                "evidence_status": "candidate",
            }
        )
    frames.sort(key=lambda f: ((f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1])), reverse=True)
    return frames[:8]


def score_frames_against_regions(
    frames: Sequence[Dict[str, Any]],
    auto_regions: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows = []
    for frame in frames:
        best: Optional[Dict[str, Any]] = None
        best_iou = 0.0
        for region in auto_regions:
            iou = bbox_iou(frame["bbox"], region.get("bbox") or [0, 0, 0, 0])
            if iou > best_iou:
                best_iou = iou
                best = region
        rows.append(
            {
                "frame_id": frame.get("frame_id"),
                "page": frame.get("page"),
                "provenance": frame.get("provenance"),
                "best_region_id": (best or {}).get("region_id"),
                "iou": round(best_iou, 4),
                "frame_bbox": frame.get("bbox"),
                "region_bbox": (best or {}).get("bbox"),
            }
        )
    return rows
