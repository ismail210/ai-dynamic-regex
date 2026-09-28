"""Detail-page region analysis + cross-detail contamination probe (R&D).

Wraps existing ``detail_regions.cluster_page_regions`` and adds an experimental
2D gap clusterer for research comparison only. Does not change production.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Sequence, Tuple

from services.engineering.detail_regions import cluster_page_regions

from retrieval import geometry_candidate_record, retrieve_candidates_for_label


def _center(bbox: Sequence[float]) -> Tuple[float, float]:
    return (
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    )


def _page_size(document: Dict[str, Any], page_number: int) -> Tuple[float, float]:
    for page in document.get("pages") or []:
        if int(page.get("page_number") or 0) == page_number:
            return float(page.get("width") or 1000.0), float(page.get("height") or 1000.0)
    return 1000.0, 1000.0


def _collect_items(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
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
    for obj in geometry.get("objects") or []:
        if int(obj.get("page_number") or obj.get("page") or 0) != page_number:
            continue
        bbox = obj.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        kind = str(obj.get("kind") or "").lower()
        if kind in {"dimension"}:
            continue
        items.append({"kind": "geometry", "bbox": bbox, "ref": obj, "geo_kind": kind})
    return items


def cluster_regions_2d_rd(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    page_number: int,
    *,
    gap_fraction: float = 0.08,
) -> List[Dict[str, Any]]:
    """Experimental 2D single-linkage clustering on item centers (R&D only)."""
    items = _collect_items(document, geometry, page_number)
    if not items:
        return []
    page_w, page_h = _page_size(document, page_number)
    gap = max(60.0, min(page_w, page_h) * gap_fraction)

    text_items = [i for i in items if i["kind"] == "text"]
    geo_items = [i for i in items if i["kind"] == "geometry"]
    if len(geo_items) > 400:
        geo_items = sorted(
            geo_items,
            key=lambda i: abs(float(i["bbox"][2]) - float(i["bbox"][0]))
            + abs(float(i["bbox"][3]) - float(i["bbox"][1])),
            reverse=True,
        )[:400]
    work = text_items + geo_items
    centers = [_center(i["bbox"]) for i in work]

    parent = list(range(len(work)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(work)):
        cx_i, cy_i = centers[i]
        for j in range(i + 1, len(work)):
            dx = cx_i - centers[j][0]
            dy = cy_i - centers[j][1]
            if math.hypot(dx, dy) <= gap:
                union(i, j)

    clusters: Dict[int, List[dict]] = {}
    for i, item in enumerate(work):
        clusters.setdefault(find(i), []).append(item)

    regions: List[Dict[str, Any]] = []
    for index, cluster in enumerate(clusters.values()):
        xs0 = [float(item["bbox"][0]) for item in cluster]
        ys0 = [float(item["bbox"][1]) for item in cluster]
        xs1 = [float(item["bbox"][2]) for item in cluster]
        ys1 = [float(item["bbox"][3]) for item in cluster]
        region_id = f"p{page_number}_2d_r{index}"
        bbox = [round(min(xs0), 2), round(min(ys0), 2), round(max(xs1), 2), round(max(ys1), 2)]
        if (bbox[2] - bbox[0]) < 40 or (bbox[3] - bbox[1]) < 40:
            continue
        text_n = sum(1 for item in cluster if item["kind"] == "text")
        geo_n = sum(1 for item in cluster if item["kind"] == "geometry")
        region = {
            "region_id": region_id,
            "page": page_number,
            "bbox": bbox,
            "terminology": "detail_region_candidate",
            "evidence": [
                "rd_2d_single_linkage_on_centers",
                f"gap_threshold_pt={round(gap, 1)}",
                "union_bbox_of_cluster",
            ],
            "contained_text_count": text_n,
            "contained_geometry_count": geo_n,
            "item_count": len(cluster),
            "evidence_status": "candidate",
            "method": "rd_2d_gap",
            "neighbor_ids": [],
        }
        regions.append(region)

    regions.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
    for i, region in enumerate(regions):
        for j, other in enumerate(regions):
            if i == j:
                continue
            a, b = region["bbox"], other["bbox"]
            sep_x = 0.0
            if a[2] < b[0]:
                sep_x = b[0] - a[2]
            elif b[2] < a[0]:
                sep_x = a[0] - b[2]
            sep_y = 0.0
            if a[3] < b[1]:
                sep_y = b[1] - a[3]
            elif b[3] < a[1]:
                sep_y = a[1] - b[3]
            if sep_x > 0 or sep_y > 0:
                region["neighbor_ids"].append(
                    {
                        "region_id": other["region_id"],
                        "sep_x": round(sep_x, 1),
                        "sep_y": round(sep_y, 1),
                    }
                )
    return regions


def _quality_flags(region: Dict[str, Any], page_w: float, page_h: float) -> List[str]:
    bb = region["bbox"]
    flags = []
    if page_w and bb[0] < page_w * 0.05 and (bb[2] - bb[0]) > page_w * 0.7:
        flags.append("wide_strip_may_include_title_or_notes")
    if page_h and bb[1] > page_h * 0.85:
        flags.append("bottom_band_titleblock_risk")
    if page_h and bb[3] < page_h * 0.15:
        flags.append("top_band_header_risk")
    if page_w and page_h:
        area = (bb[2] - bb[0]) * (bb[3] - bb[1])
        if area > 0.85 * page_w * page_h:
            flags.append("near_full_page_false_merge_risk")
    return flags


def analyze_page_regions(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    page_number: int,
) -> Dict[str, Any]:
    """Run production X-gap clustering + R&D 2D clustering side by side."""
    doc = copy.deepcopy(document)
    geo = copy.deepcopy(geometry)
    prod = cluster_page_regions(doc, geo).get(int(page_number)) or []
    page_w, page_h = _page_size(doc, page_number)

    prod_enriched = []
    for region in prod:
        rid = region["region_id"]
        text_n = sum(
            1
            for t in (doc.get("engineering_tokens") or [])
            if int(t.get("page") or 0) == page_number and t.get("region_id") == rid
        )
        geo_n = sum(
            1
            for o in (geo.get("objects") or [])
            if int(o.get("page_number") or o.get("page") or 0) == page_number
            and o.get("region_id") == rid
        )
        row = {
            "region_id": rid,
            "page": page_number,
            "bbox": region["bbox"],
            "terminology": "detail_region_candidate",
            "evidence": ["production_gap_cluster_on_x_centers", "union_bbox"],
            "contained_text_count": text_n,
            "contained_geometry_count": geo_n,
            "item_count": region.get("item_count"),
            "evidence_status": "candidate",
            "method": "production_x_gap",
        }
        row["quality_flags"] = _quality_flags(row, page_w, page_h)
        prod_enriched.append(row)

    rd2d = cluster_regions_2d_rd(document, geometry, page_number)
    for row in rd2d:
        row["quality_flags"] = _quality_flags(row, page_w, page_h)

    preferred = rd2d if len(rd2d) > len(prod_enriched) else prod_enriched
    return {
        "page": page_number,
        "page_size": {"width": page_w, "height": page_h},
        "production_x_gap": {
            "region_count": len(prod_enriched),
            "regions": prod_enriched,
            "methodology": "services.engineering.detail_regions.cluster_page_regions",
        },
        "rd_2d_gap": {
            "region_count": len(rd2d),
            "regions": rd2d,
            "methodology": "scripts/rd_geometry_integration 2D single-linkage (experimental)",
        },
        "region_count": len(preferred),
        "regions": preferred,
    }


def _assign_region_ids(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    page_number: int,
    regions: List[Dict[str, Any]],
) -> None:
    for token in document.get("engineering_tokens") or []:
        if int(token.get("page") or 0) != page_number or not token.get("bbox"):
            continue
        cx, cy = _center(token["bbox"])
        token["region_id"] = None
        for region in regions:
            bb = region["bbox"]
            if bb[0] <= cx <= bb[2] and bb[1] <= cy <= bb[3]:
                token["region_id"] = region["region_id"]
                break
    for obj in geometry.get("objects") or []:
        if int(obj.get("page_number") or obj.get("page") or 0) != page_number:
            continue
        bb = obj.get("bbox")
        if not bb:
            continue
        cx, cy = _center(bb)
        obj["region_id"] = None
        for region in regions:
            rb = region["bbox"]
            if rb[0] <= cx <= rb[2] and rb[1] <= cy <= rb[3]:
                obj["region_id"] = region["region_id"]
                break


def contamination_probe(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    page_number: int,
    *,
    max_labels: int = 40,
    max_distance: float = 120.0,
) -> Dict[str, Any]:
    """Compare retrieval without vs with same-region constraint using R&D regions."""
    doc = copy.deepcopy(document)
    geo = copy.deepcopy(geometry)
    analysis = analyze_page_regions(document, geometry, page_number)
    regions = analysis["rd_2d_gap"]["regions"] or analysis["production_x_gap"]["regions"]
    _assign_region_ids(doc, geo, page_number, regions)

    records = [
        geometry_candidate_record(o)
        for o in (geo.get("objects") or [])
        if int(o.get("page_number") or o.get("page") or 0) == page_number
    ]

    labels = [
        t
        for t in (doc.get("engineering_tokens") or [])
        if int(t.get("page") or 0) == page_number and t.get("bbox")
    ][:max_labels]

    cross = 0
    same = 0
    blocked = 0
    examples: List[Dict[str, Any]] = []

    for label in labels:
        unconstrained = retrieve_candidates_for_label(
            label, records, top_k=3, max_distance=max_distance, require_same_region=False
        )
        constrained = retrieve_candidates_for_label(
            label, records, top_k=3, max_distance=max_distance, require_same_region=True
        )
        if not unconstrained:
            continue
        top = unconstrained[0]
        label_region = label.get("region_id")
        top_region = top.get("geo_region_id")
        crossed = bool(label_region and top_region and label_region != top_region)
        if crossed:
            cross += 1
            constrained_ids = {c["geometry_id"] for c in constrained}
            if top["geometry_id"] not in constrained_ids:
                blocked += 1
                if len(examples) < 8:
                    examples.append(
                        {
                            "token_id": label.get("token_id"),
                            "text": label.get("text"),
                            "label_region_id": label_region,
                            "unconstrained_top": top,
                            "constrained_top": constrained[0] if constrained else None,
                            "region_constraint_blocked_cross_detail": True,
                        }
                    )
        else:
            same += 1

    return {
        "page": page_number,
        "region_method_used": "rd_2d_gap" if analysis["rd_2d_gap"]["region_count"] else "production_x_gap",
        "region_count": len(regions),
        "labels_tested": len(labels),
        "unconstrained_cross_region_tops": cross,
        "same_region_tops": same,
        "cross_tops_blocked_by_constraint": blocked,
        "examples": examples,
        "interpretation": (
            "If cross_tops_blocked_by_constraint > 0, region constraints can reduce "
            "cross-detail contamination in nearest-geometry retrieval. This does not "
            "prove regions are true detail boundaries."
        ),
    }
