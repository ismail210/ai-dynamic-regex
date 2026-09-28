#!/usr/bin/env python3
"""Run Step 2 + Step 3 R&D prototypes on Burrville golden pages (read-only).

Uses existing multimodal artifacts — does not modify production pipelines.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare import compare_row, index_nearest_geometry_edges, summarize_comparisons
from demo_page import write_comparison_page
from overlays import render_association_overlay, render_region_overlay
from region_frames import score_frames_against_regions, seed_title_frames
from regions_analysis import _assign_region_ids, analyze_page_regions, contamination_probe
from review_kit import load_gold, prioritize_rows, write_review_kit
from retrieval import geometry_candidate_record, retrieve_candidates_for_label
from scorer import decide_association, evaluate_against_production
from workflow_verify import (
    attach_geometry_sidecar,
    mike_corrected_pdf_checklist,
    sidecar_preserves_semantics,
)

DOC_ID = "doc_0d910a43b4a021e3"
ARTIFACT = ROOT / "training" / "engineering_artifacts" / DOC_ID / "multimodal"
OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"

# Golden pages — small, documented set (plan + multi-detail candidates)
GOLDEN = [
    {
        "page": 8,
        "role": "structural_plan",
        "why": (
            "Burrville framing plan used in docs/validation phase1/phase2 association "
            "samples; dense W-section labels with nearby vector geometry."
        ),
    },
    {
        "page": 18,
        "role": "detail_sheet",
        "why": (
            "Burrville S-205 detail sheet from incomplete-L evidence set "
            "(L4X4X1/4 TYP / brace details); candidate multi-detail layout."
        ),
    },
    {
        "page": 24,
        "role": "detail_sheet_dense",
        "why": (
            "Burrville S-321 roof details page with many L4X4* callouts; "
            "stress-tests region clustering and cross-detail proximity."
        ),
    },
]


def _load_json(name: str) -> Dict[str, Any]:
    path = ARTIFACT / name
    if not path.exists():
        raise FileNotFoundError(f"Missing artifact {path} — run analyze on Burrville first")
    return json.loads(path.read_text())


def _sectionish(text: str) -> bool:
    t = (text or "").upper().replace(" ", "")
    return any(t.startswith(p) for p in ("W", "HSS", "L", "C", "MC", "WT", "HP", "PIPE", "PL", "BP"))


def run_step2(document: Dict[str, Any], geometry: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any]:
    current_by_token = index_nearest_geometry_edges(graph)
    geo_records = [geometry_candidate_record(o) for o in (geometry.get("objects") or [])]

    all_rows: List[Dict[str, Any]] = []
    by_page: Dict[str, Any] = {}

    for spec in GOLDEN:
        page = int(spec["page"])
        labels = [
            t
            for t in (document.get("engineering_tokens") or [])
            if int(t.get("page") or 0) == page and t.get("bbox") and _sectionish(str(t.get("text") or ""))
        ][:50]
        page_geo = [g for g in geo_records if int(g["page_number"]) == page]
        rows = []
        for label in labels:
            cands = retrieve_candidates_for_label(label, page_geo, top_k=5, max_distance=150.0)
            current = current_by_token.get(label.get("token_id") or "")
            # Fallback: match by text node source via page+bbox proximity if token missing
            row = compare_row(label, current, cands)
            row["golden_role"] = spec["role"]
            rows.append(row)
            all_rows.append(row)
        by_page[str(page)] = {
            "spec": spec,
            "labels_compared": len(rows),
            "summary": summarize_comparisons(rows),
            "examples": {
                "agreement": [r for r in rows if r["status"].startswith("agreement")][:5],
                "disagreement": [r for r in rows if r["status"] == "disagreement"][:5],
                "ambiguous": [r for r in rows if "ambiguous" in r["status"]][:5],
                "missing_retrieval": [r for r in rows if r["status"] == "missing_retrieval"][:5],
                "extra_candidates_only": [r for r in rows if r["status"] == "extra_candidates_only"][:5],
            },
        }

    return {
        "document_id": DOC_ID,
        "source_pdf": "Burrville ES - ST.pdf",
        "artifact_dir": str(ARTIFACT),
        "golden_pages": GOLDEN,
        "overall": summarize_comparisons(all_rows),
        "by_page": by_page,
        "rows": all_rows,
    }


def run_step3(document: Dict[str, Any], geometry: Dict[str, Any]) -> Dict[str, Any]:
    pages = {}
    contamination = {}
    for spec in GOLDEN:
        page = int(spec["page"])
        pages[str(page)] = analyze_page_regions(document, geometry, page)
        if spec["role"] != "structural_plan":
            contamination[str(page)] = contamination_probe(document, geometry, page)
        else:
            # Still run probe on plan for baseline (often 1–few regions)
            contamination[str(page)] = contamination_probe(document, geometry, page, max_labels=30)
    return {
        "document_id": DOC_ID,
        "pages": pages,
        "contamination": contamination,
    }


def _render_region_overlay(page_number: int, regions: List[Dict[str, Any]], out_path: Path) -> None:
    """Optional debug PNG — not production UI."""
    pdf_path = ROOT / "uploads" / "Burrville ES - ST.pdf"
    render_region_overlay(pdf_path, page_number, regions, out_path)


def run_g1_evidence(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    graph: Dict[str, Any],
) -> Dict[str, Any]:
    current_by_token = index_nearest_geometry_edges(graph)
    all_rows: List[Dict[str, Any]] = []
    by_page: Dict[str, Any] = {}
    for spec in GOLDEN:
        page = int(spec["page"])
        analysis = analyze_page_regions(document, geometry, page)
        regions = analysis["rd_2d_gap"]["regions"] or analysis["production_x_gap"]["regions"]
        doc = json.loads(json.dumps(document))
        geo = json.loads(json.dumps(geometry))
        _assign_region_ids(doc, geo, page, regions)
        geo_records = [geometry_candidate_record(o) for o in (geo.get("objects") or [])]
        labels = [
            t
            for t in (doc.get("engineering_tokens") or [])
            if int(t.get("page") or 0) == page and t.get("bbox") and _sectionish(str(t.get("text") or ""))
        ][:50]
        page_geo = [g for g in geo_records if int(g["page_number"]) == page]
        rows = []
        for label in labels:
            cands = retrieve_candidates_for_label(
                label,
                page_geo,
                top_k=5,
                max_distance=150.0,
                exclude_leader_as_target=True,
                resolve_leaders=True,
            )
            current = current_by_token.get(label.get("token_id") or "")
            row = compare_row(label, current, cands)
            row["golden_role"] = spec["role"]
            row["shadow_decision"] = decide_association(cands)
            rows.append(row)
            all_rows.append(row)
        by_page[str(page)] = {
            "spec": spec,
            "labels_compared": len(rows),
            "summary": summarize_comparisons(rows),
        }
    return {
        "document_id": DOC_ID,
        "retrieval": "leader_aware_exclude_leader_targets",
        "overall": summarize_comparisons(all_rows),
        "by_page": by_page,
        "rows": all_rows,
    }


def run_g2_frames(document: Dict[str, Any], geometry: Dict[str, Any]) -> Dict[str, Any]:
    pages = {}
    for spec in GOLDEN:
        page = int(spec["page"])
        analysis = analyze_page_regions(document, geometry, page)
        proposed = seed_title_frames(document, geometry, page)
        pages[str(page)] = {
            "proposed_frames": proposed,
            "iou_vs_production": score_frames_against_regions(
                proposed, analysis["production_x_gap"]["regions"]
            ),
            "iou_vs_rd2d": score_frames_against_regions(proposed, analysis["rd_2d_gap"]["regions"]),
            "human_gold_frames": [],
            "note": "Title-seeded frames are research_proposed, not human gold. Region remains a soft feature.",
        }
    return {"document_id": DOC_ID, "pages": pages}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    document = _load_json("document.json")
    geometry = _load_json("geometry.json")
    graph = _load_json("graph.json")
    pdf_path = ROOT / "uploads" / "Burrville ES - ST.pdf"

    step2 = run_step2(document, geometry, graph)
    step3 = run_step3(document, geometry)
    g1 = run_g1_evidence(document, geometry, graph)
    g2 = run_g2_frames(document, geometry)

    (OUT / "golden_pages.json").write_text(json.dumps(GOLDEN, indent=2))
    (OUT / "step2_summary.json").write_text(
        json.dumps({k: step2[k] for k in ("document_id", "source_pdf", "golden_pages", "overall", "by_page")}, indent=2)
    )
    with (OUT / "step2_rows.jsonl").open("w") as fh:
        for row in step2["rows"]:
            fh.write(json.dumps(row) + "\n")
    (OUT / "step3_regions.json").write_text(json.dumps(step3["pages"], indent=2))
    (OUT / "step3_contamination.json").write_text(json.dumps(step3["contamination"], indent=2))
    (OUT / "g1_summary.json").write_text(
        json.dumps({k: g1[k] for k in ("document_id", "retrieval", "overall", "by_page")}, indent=2)
    )
    with (OUT / "g1_rows.jsonl").open("w") as fh:
        for row in g1["rows"]:
            fh.write(json.dumps(row) + "\n")
    (OUT / "g2_frames.json").write_text(json.dumps(g2, indent=2))

    renders = OUT / "renders"
    for page_key, payload in step3["pages"].items():
        extra = g2["pages"][page_key]["proposed_frames"]
        render_region_overlay(
            pdf_path,
            int(page_key),
            payload.get("regions") or [],
            renders / f"p{page_key}_regions.png",
            extra=extra,
        )

    overlay_rel: Dict[str, str] = {}
    priority = prioritize_rows(g1["rows"], limit=108)
    for row in priority[:24]:
        tid = str(row.get("token_id") or "row")
        rel = f"renders/assoc_{tid}.png"
        ok = render_association_overlay(pdf_path, int(row["page"]), row, OUT / rel)
        if ok:
            overlay_rel[tid] = rel

    kit_dir = OUT / "review_kit"
    write_review_kit(priority, kit_dir)
    gold = load_gold(kit_dir / "gold_outcomes.jsonl")
    for row in g1["rows"]:
        row["shadow_decision"] = decide_association(row.get("new_candidates") or [])
    g4 = evaluate_against_production(g1["rows"], gold)
    (OUT / "g4_shadow_metrics.json").write_text(json.dumps(g4, indent=2))

    sample = {"original_text": "L4X4", "primary_label": "L4X4", "takeoff_eligible": False, "completion_status": "missing_thickness"}
    attached = attach_geometry_sidecar(sample, [{"geometry_id": "geom_demo"}])
    from services.semantic.corrected_pdf import corrected_pdf_path

    corrected_exists = corrected_pdf_path(DOC_ID).exists()
    g5 = {
        "sidecar_preserves_semantics": sidecar_preserves_semantics(sample, attached),
        "mike": mike_corrected_pdf_checklist(DOC_ID, corrected_exists),
    }
    (OUT / "g5_workflow_verify.json").write_text(json.dumps(g5, indent=2))

    write_comparison_page(
        priority,
        overlay_rel,
        OUT / "comparison.html",
        metrics={"g1": g1["overall"], "g4": g4, "g5": g5},
    )

    print("Wrote", OUT)
    print("Step2 overall:", json.dumps(step2["overall"], indent=2))
    print("G1 overall:", json.dumps(g1["overall"], indent=2))
    print("G4:", json.dumps(g4, indent=2))
    for page, c in step3["contamination"].items():
        print(
            f"Step3 p{page}: regions={step3['pages'][page]['region_count']} "
            f"cross_tops={c['unconstrained_cross_region_tops']} "
            f"blocked={c['cross_tops_blocked_by_constraint']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
