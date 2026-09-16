"""Phase C benchmark: GHX-inspired shadow association vs. the existing
centroid-distance association, on one real benchmark drawing.

Read-only: calls existing extract/geometry functions exactly like
``measure_phase1_association.py`` (see that script for the established
methodology this reuses) and the new, additive
``services.semantic_preprocessor.geometry_route_association`` module. Never
touches takeoff, never writes into any production artifact path, never
promotes anything -- this is a shadow-mode measurement only (Section 31/33
item L).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.engineering.geometry_adapters import extract_geometry_document
from services.engineering.member_geometry import build_member_candidates
from services.extraction_engine import extract_engineering_document
from services.semantic.models import GeometryEvidence, GeometryProvider, SemanticAnnotation
from services.semantic_preprocessor.association import associate_via_nearest_geometry
from services.semantic_preprocessor.geometry_route_association import (
    AssociationConfig,
    compare_with_existing,
    run_shadow_association,
)
from services.structural_parser import parse_section

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "uploads"
OUT_PATH = ROOT.parent / "docs" / "validation" / "phase_c_shadow_association_measurement.json"

DOCUMENT = {
    "id": "Burrville",
    "path": UPLOADS / "Burrville ES - ST__0d910a43b4a0.pdf",
    "pages": [1, 3, 5, 8],
}


def _is_section_label(token: dict) -> bool:
    text = str(token.get("normalized_text") or token.get("text") or token.get("raw_text") or "")
    if not text.strip():
        return False
    parsed = parse_section(text)
    return bool(parsed and parsed.family)


def _member_candidates_to_geometry_evidence(candidates: List[dict]) -> Dict[int, List[GeometryEvidence]]:
    by_page: Dict[int, List[GeometryEvidence]] = {}
    for c in candidates:
        page = int(c.get("page_number") or c.get("page") or 0)
        orientation = c.get("orientation")
        by_page.setdefault(page, []).append(GeometryEvidence(
            geometry_id=str(c["geometry_id"]),
            provider=GeometryProvider.PDF_VECTOR,
            geometry_type="beam_curve",  # member_geometry does not yet distinguish curved/misc; Phase D work
            points=c.get("points") or None,
            bbox=c.get("bbox"),
            centroid=c.get("center"),
            length=c.get("length"),
            orientation=[float(orientation)] if orientation is not None else None,
        ))
    return by_page


def _tokens_to_annotations(tokens: List[dict], doc_id: str) -> List[SemanticAnnotation]:
    annotations = []
    for i, t in enumerate(tokens):
        bbox = t.get("bbox")
        if not bbox:
            continue
        text = str(t.get("normalized_text") or t.get("text") or t.get("raw_text") or "")
        anchor = [(float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0]
        rotation = t.get("rotation")
        axis = None
        if rotation is not None:
            import math
            rad = math.radians(float(rotation))
            axis = [math.cos(rad), math.sin(rad)]
        annotations.append(SemanticAnnotation(
            annotation_id=f"{doc_id}_tok_{i}",
            original_text=text,
            primary_label=text,
            page=int(t.get("page") or 0),
            original_anchor=anchor,
            original_axis=axis,
        ))
    return annotations


def main() -> None:
    spec = DOCUMENT
    if not spec["path"].exists():
        print(f"missing benchmark PDF: {spec['path']}")
        sys.exit(1)

    print(f"extracting {spec['id']} ...")
    document = extract_engineering_document(spec["path"])
    geometry = extract_geometry_document(spec["path"], document_structure=document)

    pages = set(spec["pages"])
    tokens = [
        t for t in (document.get("engineering_tokens") or [])
        if int(t.get("page") or 0) in pages and _is_section_label(t)
    ]
    print(f"section-like labels on sampled pages: {len(tokens)}")

    member_candidates = build_member_candidates(geometry)
    member_candidates = [c for c in member_candidates if int(c.get("page_number") or 0) in pages]
    print(f"member candidates (strokes) on sampled pages: {len(member_candidates)}")

    geometry_by_page = _member_candidates_to_geometry_evidence(member_candidates)
    annotations = _tokens_to_annotations(tokens, spec["id"])

    # ---- New: GHX-inspired shadow route engine ----
    new_evidence = run_shadow_association(annotations, geometry_by_page, config=AssociationConfig())

    # ---- Existing: centroid-distance associate_via_nearest_geometry (no transform: same frame) ----
    existing_geometry_id_by_annotation: Dict[str, str] = {}
    flat_geometry = [g for page_list in geometry_by_page.values() for g in page_list]
    for ann in annotations:
        result = associate_via_nearest_geometry(ann, flat_geometry, transform=None)
        if result is not None:
            existing_geometry_id_by_annotation[ann.annotation_id] = result.geometry_id

    comparison = compare_with_existing(new_evidence, existing_geometry_id_by_annotation)

    new_status_counts = {"associated": 0, "unmatched": 0}
    new_reason_counts: Dict[str, int] = {}
    new_origin_counts: Dict[str, int] = {}
    for ev in new_evidence:
        new_status_counts[ev.status] = new_status_counts.get(ev.status, 0) + 1
        new_origin_counts[ev.association_origin] = new_origin_counts.get(ev.association_origin, 0) + 1
        for r in ev.reason_codes:
            new_reason_counts[r] = new_reason_counts.get(r, 0) + 1

    result = {
        "document": spec["id"],
        "sampled_pages": sorted(pages),
        "label_count": len(annotations),
        "member_candidate_count": len(member_candidates),
        "new_engine": {
            "status_counts": new_status_counts,
            "origin_counts": new_origin_counts,
            "reason_code_counts": new_reason_counts,
            "coverage": round(new_status_counts.get("associated", 0) / len(annotations), 4) if annotations else None,
        },
        "existing_engine": {
            "associated_count": len(existing_geometry_id_by_annotation),
            "coverage": round(len(existing_geometry_id_by_annotation) / len(annotations), 4) if annotations else None,
        },
        "comparison": {k: v for k, v in comparison.items() if k != "details"},
        "comparison_details_sample": comparison["details"][:20],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "comparison_details_sample"}, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
