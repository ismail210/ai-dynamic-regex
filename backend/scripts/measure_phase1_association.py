"""Phase 1 association measurement on real sheets.

Read-only: calls existing extract / geometry / region / graph functions.
Does not run fusion, ranker, GraphSAGE, or MobileNet encoding.
Geometry is extracted only for a small set of representative pages per PDF
(existing extract_geometry skips pages without engineering tokens).
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.engineering.detail_regions import assign_detail_regions
from services.engineering.drawing_scale import (
    _NOT_TO_SCALE,
    detect_drawing_scale,
    detect_page_scales,
)
from services.engineering.geometry_adapters import extract_geometry_document
from services.engineering.graph_builder import build_graph
from services.extraction_engine import extract_engineering_document
from services.structural_parser import parse_section

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "uploads"
OUT_DIR = ROOT.parent / "docs" / "validation"
SAMPLE_DIR = OUT_DIR / "phase1_samples"

DOCUMENTS = [
    {
        "id": "ST",
        "path": UPLOADS / "ST.pdf",
        "pages": [1, 3, 5, 8],
        "notes": "23-page structural set; scale often on later sheets",
    },
    {
        "id": "Struct",
        "path": UPLOADS / "Struct.pdf",
        "pages": [1, 3, 5, 8],
        "notes": "24-page structural set",
    },
    {
        "id": "GCDC",
        "path": UPLOADS / "GCDC Building 4 - ST1__47dc7ef27f6e.pdf",
        "pages": [1, 5, 21, 25],
        "notes": "81-page / 45MB; sampled pages only",
    },
    {
        "id": "Burrville",
        "path": UPLOADS / "Burrville ES - ST.pdf",
        "pages": [1, 3, 5, 8],
        "notes": "29-page school structural set",
    },
    {
        "id": "K1200",
        "path": UPLOADS / "1200 K_Permit_Bid_Dwgs - Structural.pdf",
        "pages": [1, 3, 22, 23],
        "notes": "39-page dense permit set (additional complex PDF)",
    },
]

_SECTIONISH = re.compile(
    r"\b(?:W|WT|HSS|C|L|MC|S|M|HP|PIPE|TS)\s*\d",
    re.I,
)
_SHORT_STROKE_PT = 12.0


def _page_text(document: dict, page_number: int) -> str:
    parts: List[str] = []
    for line in document.get("lines") or []:
        if int(line.get("page_number") or line.get("page") or 0) == page_number:
            parts.append(str(line.get("text") or ""))
    for block in document.get("blocks") or []:
        if int(block.get("page_number") or block.get("page") or 0) == page_number:
            parts.append(str(block.get("text") or ""))
    for token in document.get("engineering_tokens") or []:
        if int(token.get("page") or 0) == page_number:
            parts.append(str(token.get("text") or token.get("raw_text") or ""))
    return "\n".join(parts)


def _is_section_label(token: dict) -> bool:
    text = str(token.get("normalized_text") or token.get("text") or token.get("raw_text") or "")
    if not text.strip():
        return False
    parsed = parse_section(text)
    if parsed and parsed.family:
        return True
    return bool(_SECTIONISH.search(text))


def _center(bbox: List[float]) -> List[float]:
    return [
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    ]


def _angle_diff(a: float, b: float) -> float:
    diff = abs(float(a) - float(b)) % 180.0
    return min(diff, 180.0 - diff)


def _looks_filled(obj: dict) -> bool:
    fill = obj.get("fill")
    opacity = obj.get("fill_opacity")
    if opacity is not None:
        try:
            if float(opacity) > 0.15:
                return True
        except (TypeError, ValueError):
            pass
    return bool(fill)


def _sample_doc_for_geometry(document: dict, pages: List[int]) -> dict:
    sample = copy.deepcopy(document)
    wanted = set(pages)
    sample["engineering_tokens"] = [
        t
        for t in (document.get("engineering_tokens") or [])
        if int(t.get("page") or 0) in wanted
    ]
    return sample


def classify_association(row: dict) -> str:
    """Heuristic class for Phase 1 ranking. Visual review may override."""

    if not row.get("has_association"):
        return "F_orphan"
    if row.get("cross_region"):
        return "C_cross_detail"
    kind = str(row.get("target_kind") or "").lower()
    if kind in {"dimension"} or row.get("target_is_dimension"):
        return "G_dimension_target"
    if kind == "leader" or row.get("target_is_leader"):
        return "D_leader_or_hatch"
    if row.get("target_looks_filled") and kind in {"path", "rectangle", "curve"}:
        return "D_leader_or_hatch"
    if row.get("nearby_parallel") and not row.get("leader_resolved"):
        return "E_parallel_candidate"
    return "ASSOCIATED_UNVERIFIED"


def measure_document(spec: dict) -> dict:
    path: Path = spec["path"]
    pages: List[int] = spec["pages"]
    timings: Dict[str, float] = {}

    t0 = time.perf_counter()
    document = extract_engineering_document(path)
    timings["extraction_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    t0 = time.perf_counter()
    page_scales = detect_page_scales(document)
    document_scale = detect_drawing_scale(document)
    timings["scale_detect_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    sample = _sample_doc_for_geometry(document, pages)
    t0 = time.perf_counter()
    geometry = extract_geometry_document(path, document_structure=sample)
    timings["geometry_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    t0 = time.perf_counter()
    regions = assign_detail_regions(sample, geometry)
    timings["regions_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    t0 = time.perf_counter()
    graph = build_graph(sample, geometry)
    timings["graph_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    geom_by_id = {str(o.get("geometry_id")): o for o in (geometry.get("objects") or [])}
    nodes_by_id = {n["node_id"]: n for n in (graph.get("nodes") or [])}
    nearest_edges = [
        e
        for e in (graph.get("edges") or [])
        if e.get("relationship") == "nearest_geometry"
        and int(e.get("page_number") or 0) in set(pages)
    ]
    edge_by_source = {}
    for edge in nearest_edges:
        edge_by_source.setdefault(edge["source"], edge)

    objects_by_page: Dict[int, List[dict]] = defaultdict(list)
    for obj in geometry.get("objects") or []:
        objects_by_page[int(obj.get("page_number") or 0)].append(obj)

    summaries_by_page = {
        int(s.get("page_number") or 0): s
        for s in (
            geometry.get("page_summaries")
            or (geometry.get("metadata") or {}).get("page_summaries")
            or []
        )
    }
    merge_global = geometry.get("fragment_merge") or {}

    page_rows = []
    association_rows = []
    for page in pages:
        page_text = _page_text(document, page)
        nts = bool(_NOT_TO_SCALE.search(page_text))
        local = page_scales.get(page)
        fallback = local is None and document_scale is not None
        leak = False
        if fallback and document_scale is not None:
            src_page = document_scale.page_number
            leak = src_page is not None and int(src_page) != int(page)

        tokens = [
            t
            for t in (sample.get("engineering_tokens") or [])
            if int(t.get("page") or 0) == page
        ]
        labels = [t for t in tokens if _is_section_label(t)]
        geoms = objects_by_page.get(page, [])
        region_list = regions.get(page) or []
        label_regions = Counter(str(t.get("region_id") or "") for t in labels)
        geom_regions = Counter(str(g.get("region_id") or "") for g in geoms)
        orphan_labels = sum(1 for t in labels if not t.get("region_id"))
        orphan_geoms = sum(1 for g in geoms if not g.get("region_id"))
        assigned = (len(labels) - orphan_labels) + (len(geoms) - orphan_geoms)
        total_items = len(labels) + len(geoms)
        coverage = assigned / total_items if total_items else None

        merged = [g for g in geoms if g.get("merged_from")]
        short = [
            g
            for g in geoms
            if float(g.get("length") or 0) < _SHORT_STROKE_PT
            and str(g.get("kind") or "") in {"line", "polyline", "path"}
        ]
        suspicious_merge = 0
        for g in merged:
            kinds = []
            for gid in g.get("merged_from") or []:
                src = geom_by_id.get(str(gid))
                if src:
                    kinds.append(str(src.get("kind") or ""))
            if any(k in {"leader", "dimension"} for k in kinds):
                suspicious_merge += 1
            elif len(g.get("merged_from") or []) >= 12:
                suspicious_merge += 1

        cap = summaries_by_page.get(page) or {}
        applied_scale = cap.get("scale_value")
        applied_source = cap.get("scale_source")
        applied_fallback = bool(cap.get("scale_fallback"))
        applied_nts = cap.get("is_nts")
        if applied_nts is None:
            applied_nts = nts
        page_rows.append(
            {
                "page": page,
                "scale_value": applied_scale,
                "scale_source": applied_source,
                "scale_reason": cap.get("scale_reason"),
                "scale_detected_on_page": local is not None,
                "scale_missing_on_page": local is None,
                "nts": bool(applied_nts),
                "fallback": applied_fallback,
                "other_page_scale_leak_possible": applied_fallback,
                "document_scale_page": document_scale.page_number if document_scale else None,
                "document_scale_value": document_scale.raw if document_scale else None,
                "association_radius_pdf_points": cap.get("association_radius_pdf_points"),
                "region_count": len(region_list),
                "section_labels": len(labels),
                "geometry_objects": len(geoms),
                "orphan_labels": orphan_labels,
                "orphan_geometry": orphan_geoms,
                "region_coverage": None if coverage is None else round(coverage, 4),
                "label_region_counts": dict(label_regions),
                "geometry_region_counts": dict(geom_regions),
                "merged_members": len(merged),
                "short_leftover_strokes": len(short),
                "suspicious_merges": suspicious_merge,
                "drawing_cap_applied": bool(cap.get("drawing_cap_applied")),
                "raw_drawing_count": cap.get("raw_drawing_count"),
                "retained_drawing_count": cap.get("retained_drawing_count"),
                "drawings_dropped_by_cap": cap.get("drawings_dropped_by_cap"),
                "drawings_excluded_page_frame": cap.get("drawings_excluded_page_frame"),
                "kinds": dict(Counter(str(g.get("kind") or "unknown") for g in geoms)),
            }
        )

        page_geoms = geoms
        for token in labels:
            bbox = token.get("bbox")
            if not bbox:
                continue
            text = str(token.get("text") or token.get("raw_text") or "")
            # Match graph text nodes: build_text_nodes uses token identity via node_id.
            matching_nodes = [
                n
                for n in (graph.get("nodes") or [])
                if n.get("kind") in {"text", "label", "beam", "column", "plate", "brace", "steel_section"}
                and int(n.get("page_number") or 0) == page
                and str(n.get("text") or "") == text
            ]
            node = None
            if matching_nodes:
                tcenter = _center(bbox)
                node = min(
                    matching_nodes,
                    key=lambda n: math.hypot(
                        float((n.get("center") or [0, 0])[0]) - tcenter[0],
                        float((n.get("center") or [0, 0])[1]) - tcenter[1],
                    ),
                )
            edge = edge_by_source.get(node["node_id"]) if node else None
            target = nodes_by_id.get(edge["target"]) if edge else None
            target_obj = geom_by_id.get(str((target or {}).get("source_id") or "")) if target else None
            label_region = token.get("region_id") or (node or {}).get("region_id")
            target_region = (target_obj or {}).get("region_id") or (target or {}).get("region_id")
            nearby_parallel = False
            if target_obj:
                torient = float(target_obj.get("orientation") or 0)
                tcenter = target_obj.get("center") or _center(target_obj.get("bbox") or [0, 0, 0, 0])
                for other in page_geoms:
                    if other is target_obj:
                        continue
                    if str(other.get("kind") or "") not in {"line", "polyline", "path"}:
                        continue
                    if _angle_diff(torient, float(other.get("orientation") or 0)) > 8:
                        continue
                    oc = other.get("center") or _center(other.get("bbox") or [0, 0, 0, 0])
                    dist = math.hypot(float(tcenter[0]) - float(oc[0]), float(tcenter[1]) - float(oc[1]))
                    if 4.0 < dist < 40.0:
                        nearby_parallel = True
                        break
            meta = (edge or {}).get("meta") or {}
            row = {
                "page": page,
                "label_text": text[:80],
                "label_bbox": bbox,
                "label_region": label_region,
                "has_association": edge is not None,
                "distance": (edge or {}).get("distance"),
                "target_id": (target_obj or {}).get("geometry_id"),
                "target_kind": (target_obj or {}).get("kind") or (target or {}).get("geometry_kind"),
                "target_region": target_region,
                "cross_region": bool(
                    edge
                    and label_region
                    and target_region
                    and str(label_region) != str(target_region)
                ),
                "leader_resolved": bool(meta.get("leader_resolved")),
                "association_sources": list(meta.get("association_sources") or []),
                "candidate_count": meta.get("candidate_count"),
                "target_is_leader": str((target_obj or {}).get("kind") or "") == "leader",
                "target_is_dimension": str((target_obj or {}).get("kind") or "") == "dimension",
                "target_looks_filled": _looks_filled(target_obj) if target_obj else False,
                "target_length": (target_obj or {}).get("length"),
                "nearby_parallel": nearby_parallel,
            }
            row["heuristic_class"] = classify_association(row)
            association_rows.append(row)

    graph_diag = graph.get("diagnostics") or graph.get("page_diagnostics") or []
    return {
        "id": spec["id"],
        "path": path.name,
        "notes": spec["notes"],
        "pdf_pages": document.get("page_count"),
        "sampled_pages": pages,
        "timings_ms": timings,
        "document_scale": document_scale.to_dict() if document_scale else None,
        "page_scale_map": {
            str(p): s.to_dict() for p, s in sorted(page_scales.items()) if p > 0
        },
        "pages_with_scale": sorted(p for p in page_scales if p > 0),
        "fragment_merge": merge_global,
        "graph_nodes": len(graph.get("nodes") or []),
        "graph_edges": len(graph.get("edges") or []),
        "nearest_geometry_edges": len(nearest_edges),
        "page_metrics": page_rows,
        "associations": association_rows,
        "heuristic_class_counts": dict(Counter(r["heuristic_class"] for r in association_rows)),
        "geometry_ai": geometry.get("geometry_ai"),
        "graph_diagnostics_present": bool(graph_diag),
    }


def render_samples(pdf_path: Path, associations: List[dict], dest: Path, limit: int = 6) -> List[str]:
    dest.mkdir(parents=True, exist_ok=True)
    chosen: List[dict] = []
    by_class: Dict[str, List[dict]] = defaultdict(list)
    for row in associations:
        by_class[row["heuristic_class"]].append(row)
    order = [
        "C_cross_detail",
        "D_leader_or_hatch",
        "E_parallel_candidate",
        "G_dimension_target",
        "ASSOCIATED_UNVERIFIED",
        "F_orphan",
    ]
    for cls in order:
        for row in by_class.get(cls, [])[:2]:
            chosen.append(row)
            if len(chosen) >= limit:
                break
        if len(chosen) >= limit:
            break
    from PIL import Image
    import io

    paths = []
    with fitz.open(str(pdf_path)) as doc:
        for idx, row in enumerate(chosen, start=1):
            page = doc.load_page(int(row["page"]) - 1)
            zoom = 1.4
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            x0, y0, x1, y1 = (float(v) * zoom for v in row["label_bbox"])
            pad = 90.0 * zoom
            box = (
                max(0, int(x0 - pad)),
                max(0, int(y0 - pad)),
                min(image.width, int(x1 + pad)),
                min(image.height, int(y1 + pad)),
            )
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            crop = image.crop(box)
            img_path = dest / f"p{row['page']}_{idx}_{row['heuristic_class']}.png"
            crop.save(img_path)
            sidecar = img_path.with_suffix(".json")
            sidecar.write_text(json.dumps(row, indent=2), encoding="utf-8")
            try:
                rel = str(img_path.relative_to(OUT_DIR.parent))
            except ValueError:
                rel = str(img_path)
            paths.append(rel)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", nargs="*", default=[d["id"] for d in DOCUMENTS])
    parser.add_argument(
        "--output",
        default=str(OUT_DIR / "phase1_association_measurements.json"),
    )
    parser.add_argument(
        "--sample-dir",
        default=str(SAMPLE_DIR),
    )
    args = parser.parse_args()
    wanted = set(args.docs)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sample_root = Path(args.sample_dir)
    sample_root.mkdir(parents=True, exist_ok=True)

    results = []
    for spec in DOCUMENTS:
        if spec["id"] not in wanted:
            continue
        if not spec["path"].exists():
            results.append({"id": spec["id"], "error": f"missing {spec['path']}"})
            continue
        print(f"measuring {spec['id']} ...", flush=True)
        row = measure_document(spec)
        try:
            row["sample_images"] = render_samples(
                spec["path"], row["associations"], sample_root / spec["id"]
            )
        except Exception as exc:  # measurement must still complete
            row["sample_images_error"] = str(exc)
        results.append(row)
        print(
            f"  extract={row['timings_ms']['extraction_ms']}ms "
            f"geom={row['timings_ms']['geometry_ms']}ms "
            f"graph={row['timings_ms']['graph_ms']}ms "
            f"labels={len(row['associations'])} "
            f"classes={row['heuristic_class_counts']}",
            flush=True,
        )

    payload = {
        "pipeline_note": (
            "Phase 1 measurement only. Geometry extracted for sampled pages. "
            "No fusion/ranker/GraphSAGE/MobileNet encoding."
        ),
        "documents": results,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
