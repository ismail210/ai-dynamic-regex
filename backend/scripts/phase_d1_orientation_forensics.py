"""Phase D1: orientation + candidate-geometry forensics on a real benchmark
drawing (Burrville). Read-only, additive, shadow-only -- see the Phase D1
task brief. Does NOT modify services.pdf_parser, services.document_intelligence,
or any production extraction/association code. Where this script needs a
REAL (bug-free) text rotation for comparison, it re-derives one directly
from raw PyMuPDF data, entirely inside this script, for measurement purposes
only.

Root cause already confirmed (see docs/validation/phase_d1_orientation_forensics.md):
``services.pdf_parser._span_rotation`` reads ``span.get("dir")``, but
PyMuPDF only populates ``dir`` on the LINE dict, not the span -- so every
span's computed rotation silently defaults to 0.0. This script reads
``line.get("dir")`` directly (the real value) to see what text orientation
actually looks like once that bug is bypassed, WITHOUT fixing the bug in
production code.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.engineering.geometry_adapters import extract_geometry_document
from services.engineering.member_geometry import (
    build_member_candidates,
    distance_point_to_geometry,
)
from services.extraction_engine import extract_engineering_document
from services.semantic.models import GeometryEvidence, GeometryProvider, SemanticAnnotation
from services.semantic_preprocessor.association import associate_via_nearest_geometry
from services.semantic_preprocessor.geometry_route_association import (
    AssociationConfig,
    PageSpatialIndexCache,
    classify_orientation,
    is_text_orientation_reliable,
    route_for_geometry,
    run_shadow_association,
)
from services.structural_parser import parse_section

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "uploads"
OUT_DIR = ROOT.parent / "docs" / "validation"
PDF_PATH = UPLOADS / "Burrville ES - ST__0d910a43b4a0.pdf"
PAGES = [1, 3, 5, 8]


# ---------------------------------------------------------------------------
# 1. Real (bug-free) per-page line direction, read directly from PyMuPDF.
#    Local to this script only -- does not touch services.pdf_parser.
# ---------------------------------------------------------------------------

def _intersection_ratio(a: List[float], b: List[float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(1e-6, (ax1 - ax0) * (ay1 - ay0))
    return inter / area_a


def real_line_directions_by_page(pdf_path: Path, pages: List[int]) -> Dict[int, List[Tuple[List[float], float]]]:
    """Returns {page_number: [(line_bbox, real_angle_deg), ...]} using the
    REAL ``line.get("dir")`` vector PyMuPDF provides -- the value
    ``services.pdf_parser._span_rotation`` fails to read (Section 4/16)."""

    result: Dict[int, List[Tuple[List[float], float]]] = {}
    with fitz.open(str(pdf_path)) as doc:
        for p in pages:
            page = doc.load_page(p - 1)
            raw = page.get_text("dict")
            entries: List[Tuple[List[float], float]] = []
            for block in raw.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue
                for line in block.get("lines", []):
                    d = line.get("dir")
                    bbox = list(line.get("bbox") or [])
                    if not d or len(d) < 2 or len(bbox) < 4:
                        continue
                    dx, dy = float(d[0]), float(d[1])
                    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                        continue
                    angle = math.degrees(math.atan2(dy, dx)) % 180.0
                    entries.append((bbox, angle))
            result[p] = entries
    return result


def real_rotation_for_bbox(bbox: List[float], page_lines: List[Tuple[List[float], float]]) -> Optional[float]:
    best_overlap = 0.0
    best_angle: Optional[float] = None
    for line_bbox, angle in page_lines:
        overlap = _intersection_ratio(bbox, line_bbox)
        if overlap > best_overlap:
            best_overlap = overlap
            best_angle = angle
    return best_angle if best_overlap > 0.0 else None


# ---------------------------------------------------------------------------
# 2. Extraction (same real pipeline as measure_route_association_shadow.py)
# ---------------------------------------------------------------------------

def is_label(t: dict) -> bool:
    text = str(t.get("normalized_text") or t.get("text") or t.get("raw_text") or "")
    if not text.strip():
        return False
    parsed = parse_section(text)
    return bool(parsed and parsed.family)


def main() -> None:
    print(f"extracting {PDF_PATH.name} ...")
    document = extract_engineering_document(PDF_PATH)
    geometry = extract_geometry_document(PDF_PATH, document_structure=document)

    pages = set(PAGES)
    tokens = [t for t in (document.get("engineering_tokens") or []) if int(t.get("page") or 0) in pages]
    labels = [t for t in tokens if is_label(t)]
    print(f"section-like labels: {len(labels)}")

    member_candidates = build_member_candidates(geometry)
    member_candidates = [c for c in member_candidates if int(c.get("page_number") or 0) in pages]
    print(f"member candidates: {len(member_candidates)}")

    real_lines = real_line_directions_by_page(PDF_PATH, PAGES)

    # ---- Section 6: candidate-geometry audit -------------------------------
    candidate_audit = []
    for c in member_candidates:
        pts = c.get("points") or []
        candidate_audit.append({
            "geometry_id": c["geometry_id"],
            "geometry_type": c.get("member_geometry_kind"),
            "page": c.get("page_number"),
            "start": pts[0] if pts else None,
            "end": pts[-1] if len(pts) > 1 else None,
            "length": c.get("length"),
            "orientation": c.get("orientation"),
            "role_hint": c.get("role_hint"),
            "source_primitive_count": len(c.get("source_primitive_ids") or []),
            "looks_like_merged_fragment": len(c.get("source_primitive_ids") or []) > 1,
        })

    # ---- Build GeometryEvidence + SemanticAnnotation exactly like the Phase C benchmark ----
    geometry_by_page: Dict[int, List[GeometryEvidence]] = {}
    for c in member_candidates:
        page = int(c.get("page_number") or 0)
        orientation = c.get("orientation")
        geometry_by_page.setdefault(page, []).append(GeometryEvidence(
            geometry_id=str(c["geometry_id"]), provider=GeometryProvider.PDF_VECTOR,
            geometry_type="beam_curve", points=c.get("points") or None, bbox=c.get("bbox"),
            centroid=c.get("center"), length=c.get("length"),
            orientation=[float(orientation)] if orientation is not None else None,
        ))

    annotations: List[SemanticAnnotation] = []
    annotation_audit = []
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
        ann_id = f"burrville_tok_{i}"
        annotations.append(SemanticAnnotation(
            annotation_id=ann_id, original_text=t.get("text") or "", primary_label=t.get("text") or "",
            page=page, original_anchor=anchor, original_axis=axis,
        ))
        real_angle = real_rotation_for_bbox(bbox, real_lines.get(page, []))
        annotation_audit.append({
            "annotation_id": ann_id,
            "page": page,
            "raw_text": t.get("raw_text"),
            "resolved_label": t.get("normalized_text") or t.get("text"),
            "original_anchor": anchor,
            "pipeline_rotation_deg": raw_rotation,
            "pipeline_rotation_present": raw_rotation is not None,
            "pipeline_rotation_is_suspicious_default": (raw_rotation is not None and float(raw_rotation) % 180.0 == 0.0),
            "real_line_rotation_deg": real_angle,
            "real_rotation_source": "line.dir (direct PyMuPDF re-extraction)",
            "pipeline_vs_real_agree": (
                None if real_angle is None or raw_rotation is None
                else abs((float(raw_rotation) % 180.0) - (real_angle % 180.0)) < 1.0
                or abs((float(raw_rotation) % 180.0) - (real_angle % 180.0) - 180.0) < 1.0
            ),
        })

    with open(OUT_DIR / "phase_d1_annotation_orientation_audit.json", "w", encoding="utf-8") as f:
        json.dump(annotation_audit, f, indent=2)
    with open(OUT_DIR / "phase_d1_candidate_geometry_audit.json", "w", encoding="utf-8") as f:
        json.dump(candidate_audit, f, indent=2)

    agree_count = sum(1 for a in annotation_audit if a["pipeline_vs_real_agree"] is True)
    disagree_count = sum(1 for a in annotation_audit if a["pipeline_vs_real_agree"] is False)
    real_nonzero = sum(1 for a in annotation_audit if a["real_line_rotation_deg"] not in (None, 0.0) and a["real_line_rotation_deg"] % 180.0 != 0.0)
    print(f"pipeline-vs-real rotation: agree={agree_count} disagree={disagree_count} "
          f"real_nonzero_rotation_found={real_nonzero}/{len(annotation_audit)}")

    # ---- Run hard-gate engine (Phase C default) ----------------------------
    hard_cfg = AssociationConfig()
    hard_evidence = run_shadow_association(annotations, geometry_by_page, config=hard_cfg)

    # ---- Run three-state engine using PIPELINE rotation (current, buggy) --
    three_state_cfg = AssociationConfig(use_three_state_orientation=True)
    three_state_pipeline_evidence = run_shadow_association(annotations, geometry_by_page, config=three_state_cfg)

    # ---- Run three-state engine using REAL rotation (bug bypassed) --------
    real_annotations = []
    real_by_id = {a["annotation_id"]: a["real_line_rotation_deg"] for a in annotation_audit}
    for ann in annotations:
        real_angle = real_by_id.get(ann.annotation_id)
        axis = None
        if real_angle is not None:
            rad = math.radians(real_angle)
            axis = [math.cos(rad), math.sin(rad)]
        real_annotations.append(SemanticAnnotation(
            annotation_id=ann.annotation_id, original_text=ann.original_text, primary_label=ann.primary_label,
            page=ann.page, original_anchor=ann.original_anchor, original_axis=axis,
        ))
    three_state_real_evidence = run_shadow_association(real_annotations, geometry_by_page, config=three_state_cfg)

    # ---- Existing engine (associate_via_nearest_geometry) ------------------
    flat_geometry = [g for lst in geometry_by_page.values() for g in lst]
    existing_by_id: Dict[str, Optional[str]] = {}
    for ann in annotations:
        result = associate_via_nearest_geometry(ann, flat_geometry, transform=None)
        existing_by_id[ann.annotation_id] = result.geometry_id if result else None

    def summarize(evidence_list, label):
        status_counts = Counter(e.status for e in evidence_list)
        origin_counts = Counter(e.association_origin for e in evidence_list)
        reason_counts = Counter(r for e in evidence_list for r in e.reason_codes)
        print(f"--- {label} --- status={dict(status_counts)} origin={dict(origin_counts)}")
        return {
            "status_counts": dict(status_counts),
            "origin_counts": dict(origin_counts),
            "reason_code_counts": dict(reason_counts),
            "coverage": round(status_counts.get("associated", 0) / len(evidence_list), 4) if evidence_list else None,
        }

    hard_summary = summarize(hard_evidence, "HARD GATE (Phase C default)")
    three_state_pipeline_summary = summarize(three_state_pipeline_evidence, "THREE-STATE (pipeline/buggy rotation)")
    three_state_real_summary = summarize(three_state_real_evidence, "THREE-STATE (real re-extracted rotation)")
    existing_coverage = sum(1 for v in existing_by_id.values() if v is not None) / max(len(existing_by_id), 1)
    print(f"--- EXISTING (associate_via_nearest_geometry) --- coverage={existing_coverage:.4f}")

    # ---- Section 7/8: forensic dataset for ORIENTATION_MISMATCH cases ------
    index = PageSpatialIndexCache(geometry_by_page)
    ann_by_id = {a.annotation_id: a for a in annotations}
    forensic_rows = []
    angle_bands = Counter()
    both_present = missing_text = missing_geom = 0
    class_crosstab = Counter()

    def band_for(delta):
        bands = [(5, "0-5"), (10, "5-10"), (20, "10-20"), (45, "20-45"), (80, "45-80"), (100, "80-100"), (135, "100-135"), (180, "135-180")]
        for upper, label in bands:
            if delta <= upper:
                return label
        return "135-180"

    for ev in hard_evidence:
        if ev.status != "unmatched" or "ORIENTATION_MISMATCH" not in ev.reason_codes:
            continue
        ann = ann_by_id[ev.source_text_id]
        text_angle = None
        if ann.original_axis:
            dx, dy = ann.original_axis
            text_angle = math.degrees(math.atan2(dy, dx)) % 180.0
        text_class = classify_orientation(text_angle)
        text_reliable = is_text_orientation_reliable(text_angle)

        local = index.query(ann.page or 0, ann.original_anchor, 200.0)
        routable = [g for g in local if route_for_geometry(g) is not None]
        nearest = None
        nearest_d = None
        if routable:
            nearest = min(routable, key=lambda g: distance_point_to_geometry(ann.original_anchor, g.to_dict()))
            nearest_d = distance_point_to_geometry(ann.original_anchor, nearest.to_dict())
        geom_angle = None
        if nearest is not None and nearest.orientation:
            geom_angle = float(nearest.orientation[0]) % 180.0
        geom_class = classify_orientation(geom_angle)

        if text_angle is None:
            missing_text += 1
        if geom_angle is None:
            missing_geom += 1
        if text_angle is not None and geom_angle is not None:
            both_present += 1
            delta = abs(text_angle - geom_angle) % 180.0
            delta = min(delta, 180.0 - delta)
            angle_bands[band_for(delta)] += 1
            class_crosstab[f"{text_class.value if text_class else 'none'}_vs_{geom_class.value if geom_class else 'none'}"] += 1

        forensic_rows.append({
            "annotation_id": ann.annotation_id,
            "raw_text": ann.original_text,
            "page": ann.page,
            "text_angle": text_angle,
            "text_orientation_class": text_class.value if text_class else None,
            "text_orientation_reliable": text_reliable,
            "nearest_geometry_id": nearest.geometry_id if nearest else None,
            "nearest_geometry_angle": geom_angle,
            "nearest_geometry_orientation_class": geom_class.value if geom_class else None,
            "axial_angle_delta": (min(abs(text_angle - geom_angle) % 180.0, 180.0 - (abs(text_angle - geom_angle) % 180.0)) if text_angle is not None and geom_angle is not None else None),
            "distance_to_geometry": round(nearest_d, 3) if nearest_d is not None else None,
            "current_existing_match_geometry_id": existing_by_id.get(ann.annotation_id),
            "shadow_candidate_ids": [g.geometry_id for g in routable[:5]],
            "rejection_reason": "ORIENTATION_MISMATCH",
        })

    with open(OUT_DIR / "phase_d1_orientation_forensics.json", "w", encoding="utf-8") as f:
        json.dump(forensic_rows, f, indent=2)

    if forensic_rows:
        with open(OUT_DIR / "phase_d1_orientation_forensics.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(forensic_rows[0].keys()))
            writer.writeheader()
            for row in forensic_rows:
                writer.writerow({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in row.items()})

    print(f"forensic ORIENTATION_MISMATCH rows: {len(forensic_rows)}")
    print(f"angle-diff bands (both orientations present, n={both_present}): {dict(angle_bands)}")
    print(f"missing text angle: {missing_text}  missing geometry angle: {missing_geom}  both present: {both_present}")
    print(f"orientation-class crosstab: {dict(class_crosstab)}")

    # ---- Section 14: manual ground-truth review sample ---------------------
    sample_rows = []
    hard_by_id = {e.source_text_id: e for e in hard_evidence}
    for ann in annotations[:50]:
        ev = hard_by_id.get(ann.annotation_id)
        sample_rows.append({
            "annotation_id": ann.annotation_id,
            "text": ann.original_text,
            "page": ann.page,
            "anchor": ann.original_anchor,
            "existing_selected_geometry_id": existing_by_id.get(ann.annotation_id),
            "new_top_candidate_geometry_id": ev.geometry_id if ev else None,
            "distance": ev.distance if ev else None,
            "orientation": ev.text_orientation if ev else None,
            "status": ev.status if ev else None,
            "reason_codes": ";".join(ev.reason_codes) if ev else "",
        })
    with open(OUT_DIR / "phase_d1_manual_review_sample.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sample_rows[0].keys()))
        writer.writeheader()
        writer.writerows(sample_rows)
    print(f"manual review sample rows: {len(sample_rows)}")

    # ---- Final summary JSON --------------------------------------------
    summary = {
        "document": "Burrville",
        "pages": PAGES,
        "label_count": len(annotations),
        "member_candidate_count": len(member_candidates),
        "rotation_source_audit": {
            "pipeline_vs_real_agree": agree_count,
            "pipeline_vs_real_disagree": disagree_count,
            "real_nonzero_rotation_found": real_nonzero,
            "total": len(annotation_audit),
        },
        "engines": {
            "existing_associate_via_nearest_geometry": {"coverage": round(existing_coverage, 4)},
            "hard_gate_phase_c_default": hard_summary,
            "three_state_pipeline_rotation": three_state_pipeline_summary,
            "three_state_real_rotation": three_state_real_summary,
        },
        "orientation_mismatch_forensics": {
            "total_rejected_rows": len(forensic_rows),
            "angle_diff_bands": dict(angle_bands),
            "missing_text_angle": missing_text,
            "missing_geometry_angle": missing_geom,
            "both_present": both_present,
            "class_crosstab": dict(class_crosstab),
        },
        "candidate_geometry_quality": {
            "total_candidates": len(candidate_audit),
            "merged_from_multiple_fragments": sum(1 for c in candidate_audit if c["looks_like_merged_fragment"]),
            "role_hint_counts": dict(Counter(c["role_hint"] for c in candidate_audit)),
        },
    }
    with open(OUT_DIR / "phase_d1_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(f"\nwrote outputs to {OUT_DIR}")


if __name__ == "__main__":
    main()
