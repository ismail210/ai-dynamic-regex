"""Phase D2 Part B: merge_collinear_fragments provenance + phantom-geometry
forensics on real Burrville data. Read-only, diagnostic only -- does not
modify merge_collinear_fragments or any production behavior. Runs AFTER the
Part A rotation fix (backend/services/pdf_parser.py), so any finding here is
attributable to candidate-geometry quality specifically, not conflated with
the (now-fixed) text-rotation bug.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.engineering.geometry_adapters import extract_geometry_document
from services.engineering.geometry_normalizer import merge_collinear_fragments
from services.engineering.member_geometry import (
    build_member_candidates,
    distance_point_to_geometry,
)
from services.extraction_engine import extract_engineering_document
from services.semantic.models import GeometryEvidence, GeometryProvider, SemanticAnnotation
from services.semantic_preprocessor.geometry_route_association import (
    AssociationConfig,
    run_shadow_association,
)
from services.structural_parser import parse_section

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "uploads"
OUT_DIR = ROOT.parent / "docs" / "validation"
PDF_PATH = UPLOADS / "Burrville ES - ST__0d910a43b4a0.pdf"
PAGES = [1, 3, 5, 8]

_STRUCT_KINDS = {"line", "polyline", "path"}


def is_label(t: dict) -> bool:
    text = str(t.get("normalized_text") or t.get("text") or t.get("raw_text") or "")
    if not text.strip():
        return False
    parsed = parse_section(text)
    return bool(parsed and parsed.family)


def orientation_of(p0, p1) -> float:
    return round(math.degrees(math.atan2(float(p1[1]) - float(p0[1]), float(p1[0]) - float(p0[0]))), 2)


def length_of(p0, p1) -> float:
    return math.hypot(float(p1[0]) - float(p0[0]), float(p1[1]) - float(p0[1]))


def main() -> None:
    print(f"extracting {PDF_PATH.name} ...")
    document = extract_engineering_document(PDF_PATH)
    geometry = extract_geometry_document(PDF_PATH, document_structure=document)

    pages = set(PAGES)
    tokens = [t for t in (document.get("engineering_tokens") or []) if int(t.get("page") or 0) in pages]
    labels = [t for t in tokens if is_label(t)]

    raw_objects = [o for o in (geometry.get("objects") or []) if int(o.get("page_number") or 0) in pages]
    raw_by_id = {str(o.get("geometry_id")): o for o in raw_objects}
    raw_struct_by_page: Dict[int, List[dict]] = defaultdict(list)
    for o in raw_objects:
        if str(o.get("kind") or "").lower() in _STRUCT_KINDS:
            raw_struct_by_page[int(o.get("page_number") or 0)].append(o)

    # ---- Reproduce member_geometry.build_member_candidates' own merge call
    #      directly (same args: no scale, default gap) so we keep BOTH the
    #      merged output and can look up each source fragment's own record.
    merged_by_page: Dict[int, List[dict]] = {}
    merge_stats_by_page: Dict[int, dict] = {}
    for page, objs in raw_struct_by_page.items():
        merged, stats = merge_collinear_fragments(objs)
        merged_by_page[page] = merged
        merge_stats_by_page[page] = stats

    member_candidates = build_member_candidates(geometry)
    member_candidates = [c for c in member_candidates if int(c.get("page_number") or 0) in pages]
    print(f"member candidates (post build_member_candidates filter/min-length): {len(member_candidates)}")
    print(f"merge stats by page: {json.dumps(merge_stats_by_page, indent=2)}")

    # ---- Section 12: merge provenance for every merged candidate ----------
    provenance_rows = []
    for c in member_candidates:
        source_ids = c.get("source_primitive_ids") or []
        if len(source_ids) <= 1:
            continue
        sources = []
        total_source_length = 0.0
        for sid in source_ids:
            raw = raw_by_id.get(str(sid))
            if raw is None:
                continue
            pts = raw.get("points") or []
            p0, p1 = (pts[0], pts[-1]) if len(pts) >= 2 else (None, None)
            src_len = float(raw.get("length") or (length_of(p0, p1) if p0 and p1 else 0.0))
            total_source_length += src_len
            sources.append({
                "geometry_id": sid,
                "start": p0, "end": p1,
                "length": round(src_len, 2),
                "orientation": raw.get("orientation"),
            })
        merged_length = float(c.get("length") or 0.0)
        longest_source = max((s["length"] for s in sources), default=0.0)
        provenance_rows.append({
            "geometry_id": c["geometry_id"],
            "page": c.get("page_number"),
            "final_start": (c.get("points") or [None])[0],
            "final_end": (c.get("points") or [None, None])[-1],
            "final_length": round(merged_length, 2),
            "final_orientation": c.get("orientation"),
            "role_hint": c.get("role_hint"),
            "source_fragment_count": len(sources),
            "source_fragments": sources,
            "total_source_fragment_length": round(total_source_length, 2),
            "merged_length_over_longest_source": round(merged_length / longest_source, 3) if longest_source > 0 else None,
            "merged_length_over_sum_sources": round(merged_length / total_source_length, 3) if total_source_length > 0 else None,
        })

    with open(OUT_DIR / "phase_d2_merge_forensics.json", "w", encoding="utf-8") as f:
        json.dump(provenance_rows, f, indent=2)
    if provenance_rows:
        flat_fieldnames = ["geometry_id", "page", "final_length", "final_orientation", "role_hint",
                            "source_fragment_count", "total_source_fragment_length",
                            "merged_length_over_longest_source", "merged_length_over_sum_sources"]
        with open(OUT_DIR / "phase_d2_merge_forensics.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=flat_fieldnames)
            writer.writeheader()
            for row in provenance_rows:
                writer.writerow({k: row[k] for k in flat_fieldnames})

    print(f"merged-from-multiple-fragments candidates: {len(provenance_rows)}")

    # ---- Section 13: suspicion signal distributions ------------------------
    signals = Counter()
    for row in provenance_rows:
        if row["source_fragment_count"] > 1:
            signals["MULTI_FRAGMENT"] += 1
        if row["final_length"] >= 1000.0:
            signals["EXTREME_LENGTH"] += 1
        if row["merged_length_over_longest_source"] and row["merged_length_over_longest_source"] >= 3.0:
            signals["LARGE_GROWTH_RATIO"] += 1
        if row["source_fragment_count"] >= 4:
            signals["MANY_SOURCE_FRAGMENTS"] += 1
        if row["role_hint"] == "brace_like":
            signals["BRACE_LIKE"] += 1
    print(f"suspicion signal distribution: {dict(signals)}")

    # ---- Build GeometryEvidence + run association (post rotation-fix) -----
    geometry_by_page: Dict[int, List[GeometryEvidence]] = {}
    for c in member_candidates:
        page = int(c.get("page_number") or 0)
        orientation = c.get("orientation")
        geometry_by_page.setdefault(page, []).append(GeometryEvidence(
            geometry_id=str(c["geometry_id"]), provider=GeometryProvider.PDF_VECTOR, geometry_type="beam_curve",
            points=c.get("points") or None, bbox=c.get("bbox"), centroid=c.get("center"), length=c.get("length"),
            orientation=[float(orientation)] if orientation is not None else None,
        ))

    annotations = []
    for i, t in enumerate(labels):
        bbox = t.get("bbox")
        if not bbox:
            continue
        page = int(t.get("page") or 0)
        anchor = [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0]
        raw_rotation = t.get("rotation")
        axis = None
        if raw_rotation is not None:
            rad = math.radians(float(raw_rotation))
            axis = [math.cos(rad), math.sin(rad)]
        annotations.append(SemanticAnnotation(
            annotation_id=f"burrville_tok_{i}", original_text=t.get("text") or "", primary_label=t.get("text") or "",
            page=page, original_anchor=anchor, original_axis=axis,
        ))

    merged_evidence = run_shadow_association(annotations, geometry_by_page, config=AssociationConfig())

    # ---- Section 14: high-value phantom test on the top merged candidates -
    candidate_usage = Counter()
    for ev in merged_evidence:
        if ev.geometry_id:
            candidate_usage[ev.geometry_id] += 1
    # Also count candidate_count-weighted appearance across ALL ranked
    # candidates, not just the winner, by re-deriving nearest-N per label.
    top_candidate_label_map: Dict[str, List[dict]] = defaultdict(list)
    for c in member_candidates:
        if len(c.get("source_primitive_ids") or []) < 2:
            continue
        geom_dict = {"points": c.get("points"), "bbox": c.get("bbox")}
        for ann in annotations:
            if int(ann.page or 0) != int(c.get("page_number") or 0):
                continue
            d = distance_point_to_geometry(ann.original_anchor, geom_dict)
            if d <= 150.0:
                top_candidate_label_map[c["geometry_id"]].append({
                    "annotation_id": ann.annotation_id, "text": ann.original_text,
                    "distance": round(d, 2), "anchor": ann.original_anchor,
                })

    phantom_report = []
    for row in provenance_rows:
        if row["final_length"] < 1000.0:
            continue
        labels_nearby = top_candidate_label_map.get(row["geometry_id"], [])
        if len(labels_nearby) < 2:
            continue
        # contiguity check: are consecutive source fragments' endpoints close
        # to each other (already guaranteed by the merge gap), and do they
        # span a bounding box much larger than any single label neighborhood?
        srcs = row["source_fragments"]
        max_gap_bridged = 0.0
        for i in range(len(srcs) - 1):
            if srcs[i]["end"] and srcs[i + 1]["start"]:
                max_gap_bridged = max(max_gap_bridged, length_of(srcs[i]["end"], srcs[i + 1]["start"]))
        phantom_report.append({
            "geometry_id": row["geometry_id"],
            "final_length": row["final_length"],
            "source_fragment_count": row["source_fragment_count"],
            "max_gap_bridged_between_consecutive_sources": round(max_gap_bridged, 2),
            "role_hint": row["role_hint"],
            "labels_that_rank_it_as_a_nearby_candidate": labels_nearby,
            "num_distinct_labels_nearby": len(labels_nearby),
            "assessment": (
                "LIKELY_PHANTOM_MERGE_ARTIFACT" if len(labels_nearby) >= 2 and row["source_fragment_count"] >= 2
                else "INCONCLUSIVE"
            ),
        })

    with open(OUT_DIR / "phase_d2_phantom_candidates.json", "w", encoding="utf-8") as f:
        json.dump(phantom_report, f, indent=2)
    print(f"long (>=1000pt) merged candidates acting as neighbor to >=2 labels: {len(phantom_report)}")

    # ---- Section 16: raw vs merged nearest-candidate comparison ------------
    raw_geometry_by_page: Dict[int, List[GeometryEvidence]] = {}
    for page, objs in raw_struct_by_page.items():
        for o in objs:
            length = float(o.get("length") or 0.0)
            if length < 1.0:
                continue
            orientation = o.get("orientation")
            raw_geometry_by_page.setdefault(page, []).append(GeometryEvidence(
                geometry_id=str(o["geometry_id"]), provider=GeometryProvider.PDF_VECTOR, geometry_type="beam_curve",
                points=o.get("points"), bbox=o.get("bbox"), centroid=o.get("center"), length=length,
                orientation=[float(orientation)] if orientation is not None else None,
            ))

    raw_evidence = run_shadow_association(annotations, raw_geometry_by_page, config=AssociationConfig())
    raw_by_ann = {e.source_text_id: e for e in raw_evidence}
    merged_by_ann = {e.source_text_id: e for e in merged_evidence}

    flip_orientation_bad_to_good = 0
    flip_orientation_good_to_bad = 0
    comparison_rows = []
    for ann in annotations:
        r = raw_by_ann.get(ann.annotation_id)
        m = merged_by_ann.get(ann.annotation_id)
        if r is None or m is None:
            continue
        r_ok = r.status == "associated"
        m_ok = m.status == "associated"
        if not r_ok and m_ok:
            flip_orientation_bad_to_good += 1
        if r_ok and not m_ok:
            flip_orientation_good_to_bad += 1
        comparison_rows.append({
            "annotation_id": ann.annotation_id, "text": ann.original_text,
            "raw_status": r.status, "raw_geometry_id": r.geometry_id, "raw_distance": r.distance,
            "merged_status": m.status, "merged_geometry_id": m.geometry_id, "merged_distance": m.distance,
        })

    raw_coverage = sum(1 for e in raw_evidence if e.status == "associated") / max(len(raw_evidence), 1)
    merged_coverage = sum(1 for e in merged_evidence if e.status == "associated") / max(len(merged_evidence), 1)

    # ---- Section 17: shadow ablation summary --------------------------------
    ablation = {
        "association_a_merged_candidates": {
            "coverage": round(merged_coverage, 4),
            "associated": sum(1 for e in merged_evidence if e.status == "associated"),
            "orientation_mismatch": sum(1 for e in merged_evidence if "ORIENTATION_MISMATCH" in e.reason_codes),
            "already_claimed": sum(1 for e in merged_evidence if "GEOMETRY_ALREADY_CLAIMED" in e.reason_codes),
        },
        "association_b_raw_unmerged_geometry": {
            "coverage": round(raw_coverage, 4),
            "associated": sum(1 for e in raw_evidence if e.status == "associated"),
            "orientation_mismatch": sum(1 for e in raw_evidence if "ORIENTATION_MISMATCH" in e.reason_codes),
            "already_claimed": sum(1 for e in raw_evidence if "GEOMETRY_ALREADY_CLAIMED" in e.reason_codes),
        },
        "labels_flipped_unmatched_to_associated_by_merging": flip_orientation_bad_to_good,
        "labels_flipped_associated_to_unmatched_by_merging": flip_orientation_good_to_bad,
    }
    with open(OUT_DIR / "phase_d2_raw_vs_merged_ablation.json", "w", encoding="utf-8") as f:
        json.dump({"summary": ablation, "per_label": comparison_rows}, f, indent=2)

    print(json.dumps(ablation, indent=2))
    print(f"\nwrote outputs to {OUT_DIR}")


if __name__ == "__main__":
    main()
