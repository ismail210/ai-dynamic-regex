"""Detail-region segmentation for structural drawing pages.

Clusters text and geometry on each page into spatial regions so label
propagation and geometry association do not jump across unrelated detail
views on the same sheet.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _center(bbox: Sequence[float]) -> Tuple[float, float]:
    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _page_width(document: Dict[str, Any], page_number: int) -> float:
    for page in document.get("pages") or []:
        if int(page.get("page_number") or 0) == page_number:
            width = page.get("width")
            if width:
                return float(width)
    for dim in document.get("dimensions") or []:
        if int(dim.get("page_number") or 0) == page_number:
            width = dim.get("width")
            if width:
                return float(width)
    return 1000.0


def _collect_page_items(
    document: Dict[str, Any],
    geometry: Optional[Dict[str, Any]],
    page_number: int,
) -> List[dict]:
    items: List[dict] = []
    for token in document.get("engineering_tokens") or []:
        if int(token.get("page") or 0) != page_number:
            continue
        bbox = token.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        items.append({"kind": "text", "bbox": bbox, "ref": token})
    if geometry:
        for obj in geometry.get("objects") or []:
            if int(obj.get("page_number") or 0) != page_number:
                continue
            bbox = obj.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            items.append({"kind": "geometry", "bbox": bbox, "ref": obj})
    return items


def cluster_page_regions(
    document: Dict[str, Any],
    geometry: Optional[Dict[str, Any]] = None,
    *,
    gap_fraction: float = 0.12,
) -> Dict[int, List[dict]]:
    """Return ``{page_number: [region, ...]}`` with stable region ids."""

    pages = {
        int(token.get("page") or 0)
        for token in (document.get("engineering_tokens") or [])
        if token.get("page")
    }
    if geometry:
        pages.update(
            int(obj.get("page_number") or 0)
            for obj in (geometry.get("objects") or [])
            if obj.get("page_number")
        )
    for schedule in document.get("schedules") or []:
        if schedule.get("page_number"):
            pages.add(int(schedule["page_number"]))

    regions_by_page: Dict[int, List[dict]] = {}
    for page_number in sorted(pages):
        items = _collect_page_items(document, geometry, page_number)
        if not items:
            continue
        page_w = _page_width(document, page_number)
        gap = max(80.0, page_w * gap_fraction)
        sorted_items = sorted(items, key=lambda item: _center(item["bbox"])[0])
        clusters: List[List[dict]] = []
        for item in sorted_items:
            cx, _ = _center(item["bbox"])
            if not clusters:
                clusters.append([item])
                continue
            last_cluster = clusters[-1]
            last_cx = max(_center(other["bbox"])[0] for other in last_cluster)
            if cx - last_cx <= gap:
                last_cluster.append(item)
            else:
                clusters.append([item])

        page_regions: List[dict] = []
        for index, cluster in enumerate(clusters):
            xs0 = [float(item["bbox"][0]) for item in cluster]
            ys0 = [float(item["bbox"][1]) for item in cluster]
            xs1 = [float(item["bbox"][2]) for item in cluster]
            ys1 = [float(item["bbox"][3]) for item in cluster]
            region_id = f"p{page_number}_r{index}"
            region = {
                "region_id": region_id,
                "page_number": page_number,
                "bbox": [
                    round(min(xs0), 2),
                    round(min(ys0), 2),
                    round(max(xs1), 2),
                    round(max(ys1), 2),
                ],
                "item_count": len(cluster),
            }
            page_regions.append(region)
            for item in cluster:
                ref = item["ref"]
                ref["region_id"] = region_id
        regions_by_page[page_number] = page_regions
    return regions_by_page


def assign_detail_regions(
    document: Dict[str, Any],
    geometry: Optional[Dict[str, Any]] = None,
) -> Dict[int, List[dict]]:
    """Attach ``region_id`` to tokens/geometry and store page region index."""

    regions = cluster_page_regions(document, geometry)
    document["detail_regions"] = regions
    return regions


def region_for_point(
    regions: Dict[int, List[dict]],
    page_number: int,
    center: Sequence[float],
) -> Optional[str]:
    """Pick the region whose bbox contains ``center``, else nearest."""

    page_regions = regions.get(int(page_number)) or []
    if not page_regions:
        return None
    cx, cy = float(center[0]), float(center[1])
    containing = [
        region
        for region in page_regions
        if region["bbox"][0] <= cx <= region["bbox"][2]
        and region["bbox"][1] <= cy <= region["bbox"][3]
    ]
    if containing:
        return containing[0]["region_id"]
    best_id = page_regions[0]["region_id"]
    best_dist = float("inf")
    for region in page_regions:
        rx = (region["bbox"][0] + region["bbox"][2]) / 2.0
        ry = (region["bbox"][1] + region["bbox"][3]) / 2.0
        dist = (rx - cx) ** 2 + (ry - cy) ** 2
        if dist < best_dist:
            best_dist = dist
            best_id = region["region_id"]
    return best_id


def same_region(
    left: Optional[str],
    right: Optional[str],
) -> bool:
    if not left or not right:
        return True
    return left == right
