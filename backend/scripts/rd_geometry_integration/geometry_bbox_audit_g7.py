#!/usr/bin/env python3
"""G7 — Geometry / bbox representation audit (R&D, read-only).

Answers whether current geometry primitives and bboxes are reliable enough to
support a future text↔geometry association experiment.

Does NOT implement association. Does NOT modify production extraction,
retrieval, CAP, gold, or E3–E5.1 artifacts.

Usage (from backend/):
    python scripts/rd_geometry_integration/geometry_bbox_audit_g7.py [--renders]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fitz  # noqa: E402

import extraction_audit as EA  # noqa: E402  reuse PageReplay / helpers (read-only)
from services.engineering import geometry_extractor as GX  # noqa: E402  read-only
from services.engineering.drawing_scale import detect_page_scales  # noqa: E402

DOC_ID = "doc_0d910a43b4a021e3"
ARTIFACT = ROOT / "training" / "engineering_artifacts" / DOC_ID / "multimodal"
PDF_PATH = ROOT / "uploads" / "Burrville ES - ST.pdf"
OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
GOLD_PATH = OUT / "review_kit" / "gold_outcomes.jsonl"
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
RESULTS_PATH = OUT / "geometry_bbox_audit_g7_results.jsonl"
SUMMARY_PATH = OUT / "geometry_bbox_audit_g7_summary.json"
REPORT_PATH = OUT / "GEOMETRY_BBOX_AUDIT_G7_REPORT.md"
RENDER_DIR = OUT / "geometry_bbox_audit_g7_renders"
REVIEW_HTML = OUT / "geometry_bbox_audit_g7_review.html"

PAGES = (8, 18, 24)
MEMBER_KINDS = {"line", "polyline", "rectangle", "symbol", "path", "arc"}
FILTERED_KINDS = {"dimension", "leader"}

# Representation thresholds (documented; not production knobs).
GIANT_EXTENT_PT = 600.0
LOCAL_EXTENT_PT = 400.0
DEGENERATE_DIM_PT = 0.75
NEAR_LABEL_WINDOW_PT = 80.0
ON_SEGMENT_WINDOW_PT = 40.0
ON_SEGMENT_PERP_MAX_PT = 25.0
SHORT_STROKE_MAX_PT = 80.0
USABLE_MIN_LENGTH_PT = 20.0


# ---------------------------------------------------------------------------
# geometry feature helpers
# ---------------------------------------------------------------------------
def _bbox_metrics(bbox: Sequence[float]) -> Dict[str, float]:
    w = abs(float(bbox[2]) - float(bbox[0]))
    h = abs(float(bbox[3]) - float(bbox[1]))
    area = w * h
    diag = math.hypot(w, h)
    aspect = (w / h) if h > 1e-9 else (float("inf") if w > 1e-9 else 0.0)
    return {
        "width": round(w, 3),
        "height": round(h, 3),
        "area": round(area, 3),
        "diagonal": round(diag, 3),
        "aspect_ratio": round(aspect, 4) if math.isfinite(aspect) else None,
    }


def _centroid(bbox: Sequence[float]) -> List[float]:
    return [
        round((float(bbox[0]) + float(bbox[2])) / 2.0, 3),
        round((float(bbox[1]) + float(bbox[3])) / 2.0, 3),
    ]


def _bbox_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Minimum separation between two axis-aligned boxes (0 if overlap)."""
    ax0, ay0, ax1, ay1 = map(float, a)
    bx0, by0, bx1, by1 = map(float, b)
    dx = max(0.0, max(bx0 - ax1, ax0 - bx1))
    dy = max(0.0, max(by0 - ay1, ay0 - by1))
    return math.hypot(dx, dy)


def _centroid_distance(a: Sequence[float], b: Sequence[float]) -> float:
    ca, cb = _centroid(a), _centroid(b)
    return math.hypot(ca[0] - cb[0], ca[1] - cb[1])


def classify_bbox_quality(
    bbox: Sequence[float],
    *,
    length: Optional[float] = None,
    point_count: Optional[int] = None,
    page_width: float = 3000.0,
    page_height: float = 2200.0,
) -> str:
    m = _bbox_metrics(bbox)
    extent = max(m["width"], m["height"])
    if m["width"] < DEGENERATE_DIM_PT and m["height"] < DEGENERATE_DIM_PT:
        return "DEGENERATE_BBOX"
    page_area = max(page_width * page_height, 1.0)
    if extent >= GIANT_EXTENT_PT or m["area"] >= 0.08 * page_area:
        return "GIANT_BBOX"
    npts = int(point_count or 0)
    length_v = float(length or 0.0)
    if npts >= 5 and length_v > 1.35 * max(m["diagonal"], 1.0):
        return "COMPOUND_BBOX"
    if extent <= LOCAL_EXTENT_PT:
        return "LOCAL_BBOX"
    if extent < GIANT_EXTENT_PT:
        # Mid-size simple stroke — still localized enough for association trials.
        if npts <= 4 and length_v > 0 and length_v <= 1.25 * max(m["diagonal"], 1.0):
            return "LOCAL_BBOX"
        return "UNKNOWN"
    return "UNKNOWN"


def label_class(text: str) -> str:
    t = (text or "").upper().replace(" ", "")
    if t.startswith("PL") or t.startswith("PLATE"):
        return "plate"
    if "HGR" in t or "HANGER" in t:
        return "hanger_angle"
    if t.startswith("WT"):
        return "WT"
    if t.startswith("2L") or re.match(r"^L\d", t):
        return "L_clip_angle"
    m = re.match(r"W(\d+)", t)
    if m:
        d = int(m.group(1))
        if d <= 12:
            return "short_W"
        if d <= 18:
            return "joist_scale_W"
        return "girder_W"
    return "other"


def describe_artifact_obj(obj: Dict[str, Any], page_w: float, page_h: float) -> Dict[str, Any]:
    bbox = list(obj.get("bbox") or [0, 0, 0, 0])
    points = obj.get("points") or obj.get("coordinates") or []
    length = obj.get("length")
    if length is None and len(points) >= 2:
        length = GX._length_of_segments(points)
    metrics = _bbox_metrics(bbox)
    quality = classify_bbox_quality(
        bbox,
        length=length,
        point_count=len(points),
        page_width=page_w,
        page_height=page_h,
    )
    return {
        "geometry_id": obj.get("geometry_id"),
        "kind": obj.get("kind"),
        "bbox": [round(float(v), 3) for v in bbox],
        "bbox_metrics": metrics,
        "length": None if length is None else round(float(length), 3),
        "point_count": len(points),
        "orientation": obj.get("orientation"),
        "center": obj.get("center") or _centroid(bbox),
        "bbox_quality": quality,
        "closed_open": "unavailable",
        "start_end": (
            [
                [round(float(points[0][0]), 3), round(float(points[0][1]), 3)],
                [round(float(points[-1][0]), 3), round(float(points[-1][1]), 3)],
            ]
            if len(points) >= 2
            else None
        ),
    }


def population_census(
    objects: List[Dict[str, Any]], page: int, page_w: float, page_h: float
) -> Dict[str, Any]:
    page_objs = [o for o in objects if int(o.get("page_number") or 0) == page]
    kinds = Counter(o.get("kind") for o in page_objs)
    qualities = Counter()
    giants: List[Dict[str, Any]] = []
    short_retained = 0
    usable_local = 0
    for o in page_objs:
        desc = describe_artifact_obj(o, page_w, page_h)
        qualities[desc["bbox_quality"]] += 1
        length = float(desc["length"] or 0.0)
        if desc["bbox_quality"] == "GIANT_BBOX":
            giants.append(
                {
                    "geometry_id": desc["geometry_id"],
                    "kind": desc["kind"],
                    "bbox": desc["bbox"],
                    "point_count": desc["point_count"],
                    "path_length": desc["length"],
                    "bbox_quality": desc["bbox_quality"],
                }
            )
        if o.get("kind") in MEMBER_KINDS and length <= SHORT_STROKE_MAX_PT:
            short_retained += 1
        if (
            o.get("kind") in MEMBER_KINDS
            and desc["bbox_quality"] == "LOCAL_BBOX"
            and length >= USABLE_MIN_LENGTH_PT
        ):
            usable_local += 1
    giants.sort(key=lambda g: -(_bbox_metrics(g["bbox"])["area"]))
    return {
        "page": page,
        "n_objects": len(page_objs),
        "kinds": dict(kinds),
        "bbox_quality_counts": dict(qualities),
        "n_giant_bbox": qualities.get("GIANT_BBOX", 0),
        "n_local_bbox": qualities.get("LOCAL_BBOX", 0),
        "n_degenerate_bbox": qualities.get("DEGENERATE_BBOX", 0),
        "n_compound_bbox": qualities.get("COMPOUND_BBOX", 0),
        "n_short_member_kind_retained": short_retained,
        "n_usable_local_member_kind": usable_local,
        "giant_examples": giants[:12],
        "available_fields_sample": sorted(page_objs[0].keys()) if page_objs else [],
    }


def nearest_on_segment_raw(
    replay: EA.PageReplay, lx: float, ly: float, *, min_len: float = 15.0
) -> Optional[Dict[str, Any]]:
    hits = EA._near_label_raw(
        replay, lx, ly, perp_max=ON_SEGMENT_PERP_MAX_PT, min_len=min_len
    )
    # Prefer strokes whose bbox actually contains / is near the label center.
    for hit in hits:
        if hit["perp_distance"] <= ON_SEGMENT_PERP_MAX_PT:
            return hit
    # Fallback: widen slightly via direct scan (ambiguous band).
    best = None
    for drawing in replay.raw:
        rect = drawing.get("rect")
        if rect is None:
            continue
        if not (
            rect.x0 - ON_SEGMENT_WINDOW_PT <= lx <= rect.x1 + ON_SEGMENT_WINDOW_PT
            and rect.y0 - ON_SEGMENT_WINDOW_PT <= ly <= rect.y1 + ON_SEGMENT_WINDOW_PT
        ):
            continue
        dist, t = EA._nearest_on_path(lx, ly, drawing)
        if dist > ON_SEGMENT_WINDOW_PT or not (0.0 <= t <= 1.0):
            continue
        length = EA._path_length(drawing)
        if length < min_len:
            continue
        if best is None or dist < best[0]:
            best = (dist, drawing, length, t)
    if best is None:
        return None
    dist, drawing, length, t = best
    kept = id(drawing) in replay.kept_ids
    obj = replay.object_by_raw.get(id(drawing))
    rect = drawing["rect"]
    return {
        "perp_distance": round(dist, 2),
        "projection_t": round(t, 3),
        "path_length": round(length, 2),
        "bbox_w": round(abs(rect.width), 2),
        "bbox_h": round(abs(rect.height), 2),
        "item_types": EA._item_types(drawing),
        "n_items": len(drawing.get("items") or []),
        "retained_by_cap": kept,
        "drop_reason": None
        if kept
        else EA._drop_reason(drawing, replay.page_width, replay.page_height),
        "classified_kind": None if not obj else obj["kind"],
        "classified_before_reclass": None if not obj else obj["classified_kind_before_reclass"],
        "reclassified_by": None if not obj else obj["reclassified_by"],
        "final_geometry_id": replay.final_id_for(drawing),
        "_drawing": drawing,
        "_ambiguous_band": dist > ON_SEGMENT_PERP_MAX_PT,
    }


def local_population_candidates(
    page_objs: List[Dict[str, Any]],
    label_bbox: Sequence[float],
    page_w: float,
    page_h: float,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for o in page_objs:
        if o.get("kind") not in MEMBER_KINDS:
            continue
        bbox = o.get("bbox")
        if not bbox:
            continue
        # Keep objects whose bbox is near the label OR whose centroid is near.
        if _bbox_distance(label_bbox, bbox) > NEAR_LABEL_WINDOW_PT:
            if _centroid_distance(label_bbox, bbox) > NEAR_LABEL_WINDOW_PT * 1.5:
                continue
        desc = describe_artifact_obj(o, page_w, page_h)
        length = float(desc["length"] or 0.0)
        if length < USABLE_MIN_LENGTH_PT and desc["bbox_quality"] != "LOCAL_BBOX":
            continue
        desc["label_bbox_distance"] = round(_bbox_distance(label_bbox, bbox), 3)
        desc["centroid_distance"] = round(_centroid_distance(label_bbox, bbox), 3)
        out.append(desc)
    out.sort(key=lambda d: (d["centroid_distance"], -(d["length"] or 0)))
    return out


def leader_target_status(
    gold: Dict[str, Any],
    replay: EA.PageReplay,
    lx: float,
    ly: float,
    local_cands: List[Dict[str, Any]],
) -> str:
    if not gold.get("leader_required"):
        return "AMBIGUOUS" if gold.get("decision") == "ambiguous" else "LEADER_MISSING"
    trace = EA._leader_trace(replay, lx, ly)
    if not trace.get("leader_present"):
        return "LEADER_MISSING"
    tip_targets = trace.get("tip_targets") or []
    retained_targets = [t for t in tip_targets if t.get("retained_by_cap")]
    member_retained = [
        t
        for t in retained_targets
        if (t.get("classified_kind") or "") in MEMBER_KINDS
        or (t.get("classified_kind") or "") not in FILTERED_KINDS
    ]
    # Prefer tip targets that are not the leader itself and have non-trivial length.
    member_retained = [t for t in member_retained if float(t.get("path_length") or 0) >= 12.0]
    if member_retained:
        return "TARGET_GEOMETRY_PRESENT"
    if tip_targets and not retained_targets:
        return "LEADER_PRESENT_TARGET_MISSING"
    if retained_targets and not member_retained:
        # Leader tip lands on dimension/leader-classified geometry only.
        return "LEADER_PRESENT_TARGET_MISSING"
    # Leader present but no tip-neighborhood raw geometry found.
    if local_cands:
        return "AMBIGUOUS"
    return "TARGET_GEOMETRY_MISSING"


def likely_failure_stage(
    *,
    gold: Dict[str, Any],
    raw_status: str,
    extracted_status: str,
    bbox_quality: Optional[str],
    leader_status: str,
    usable_local_n: int,
    giant_nearby: bool,
) -> str:
    if gold.get("error_bucket") == "schedule_table_not_member":
        return "not_a_member_schedule"
    if gold.get("decision") == "associated":
        if bbox_quality == "GIANT_BBOX":
            return "segmentation_gap"
        return "representation_sufficient_for_case"
    # Leader-driven detail/section labels: tip-target availability dominates.
    if gold.get("leader_required") and leader_status in {
        "LEADER_PRESENT_TARGET_MISSING",
        "TARGET_GEOMETRY_MISSING",
        "LEADER_MISSING",
    }:
        return "leader_target_gap"
    if raw_status == "RAW_NOT_FOUND":
        return "raw_geometry_gap"
    if extracted_status == "FILTERED":
        return "geometry_population_gap"
    if giant_nearby or bbox_quality in {"GIANT_BBOX", "COMPOUND_BBOX"}:
        return "segmentation_gap"
    if extracted_status == "RETAINED" and usable_local_n > 0:
        return "retrieval_gap_not_representation"
    if extracted_status == "RETAINED" and usable_local_n == 0:
        return "bbox_quality_gap"
    return "unknown"


def audit_case(
    gold: Dict[str, Any],
    replay: EA.PageReplay,
    page_objs: List[Dict[str, Any]],
    artifact_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    bb = gold["label_bbox"]
    lx = (bb[0] + bb[2]) / 2.0
    ly = (bb[1] + bb[3]) / 2.0
    page_w, page_h = replay.page_width, replay.page_height

    nearest = nearest_on_segment_raw(replay, lx, ly)
    local_cands = local_population_candidates(page_objs, bb, page_w, page_h)
    usable_local = [
        c
        for c in local_cands
        if c["bbox_quality"] == "LOCAL_BBOX"
        and (c["length"] or 0) >= USABLE_MIN_LENGTH_PT
        and c["kind"] in MEMBER_KINDS
    ]

    # RAW status
    if gold.get("error_bucket") == "schedule_table_not_member":
        raw_status = "RAW_NOT_FOUND"
    elif nearest is None:
        raw_status = "RAW_NOT_FOUND"
    elif nearest.get("_ambiguous_band") or nearest["perp_distance"] > ON_SEGMENT_PERP_MAX_PT:
        raw_status = "RAW_AMBIGUOUS"
    else:
        raw_status = "RAW_PRESENT"

    # EXTRACTED status for the stroke under the label
    if nearest is None:
        extracted_status = "UNKNOWN"
    elif not nearest.get("retained_by_cap"):
        extracted_status = "FILTERED"
    else:
        kind = nearest.get("classified_kind") or ""
        if kind in FILTERED_KINDS:
            extracted_status = "FILTERED"
        elif nearest.get("final_geometry_id"):
            # Present in population; whether gold candidates include it is retrieval.
            gid = nearest["final_geometry_id"]
            cand_ids = set(gold.get("candidate_geometry_ids") or [])
            if gold.get("decision") == "associated":
                extracted_status = "RETAINED"
            elif gid in cand_ids or usable_local:
                extracted_status = "RETAINED"
            else:
                extracted_status = "NOT_RETRIEVED"
        else:
            extracted_status = "UNKNOWN"

    gold_gid = gold.get("selected_geometry_id")
    gold_present = False
    gold_geom_desc = None
    if gold_gid:
        obj = artifact_by_id.get(gold_gid)
        gold_present = obj is not None and int(obj.get("page_number") or 0) == int(gold["page"])
        if obj:
            gold_geom_desc = describe_artifact_obj(obj, page_w, page_h)

    # Primary bbox quality: gold geom if associated, else nearest retained usable, else nearest raw.
    bbox_quality = "UNKNOWN"
    primary_geom = None
    if gold_geom_desc:
        bbox_quality = gold_geom_desc["bbox_quality"]
        primary_geom = gold_geom_desc
    elif usable_local:
        primary_geom = usable_local[0]
        bbox_quality = primary_geom["bbox_quality"]
    elif nearest and nearest.get("final_geometry_id"):
        obj = artifact_by_id.get(nearest["final_geometry_id"])
        if obj:
            primary_geom = describe_artifact_obj(obj, page_w, page_h)
            bbox_quality = primary_geom["bbox_quality"]
    elif nearest:
        # Raw-only bbox from drawing rect
        drawing = nearest.get("_drawing")
        if drawing and drawing.get("rect") is not None:
            r = drawing["rect"]
            raw_bb = [r.x0, r.y0, r.x1, r.y1]
            bbox_quality = classify_bbox_quality(
                raw_bb,
                length=nearest.get("path_length"),
                point_count=nearest.get("n_items"),
                page_width=page_w,
                page_height=page_h,
            )

    giant_nearby = any(c["bbox_quality"] == "GIANT_BBOX" for c in local_cands[:8])
    short_flag = False
    if nearest and float(nearest.get("path_length") or 0) <= SHORT_STROKE_MAX_PT:
        short_flag = True
    if primary_geom and float(primary_geom.get("length") or 0) <= SHORT_STROKE_MAX_PT:
        short_flag = True

    leader_status = leader_target_status(gold, replay, lx, ly, local_cands)
    if not gold.get("leader_required"):
        leader_status = "LEADER_MISSING"  # not applicable; keep enum closed

    # Distances label ↔ primary geom
    label_to_geom = {}
    if primary_geom and primary_geom.get("bbox"):
        label_to_geom = {
            "bbox_distance": round(_bbox_distance(bb, primary_geom["bbox"]), 3),
            "centroid_distance": round(_centroid_distance(bb, primary_geom["bbox"]), 3),
            "orientation_diff_deg": None,
        }
        lo = None
        # Label orientation unavailable in gold; report geometry orientation only.
        if primary_geom.get("orientation") is not None:
            label_to_geom["geometry_orientation"] = primary_geom["orientation"]

    failure = likely_failure_stage(
        gold=gold,
        raw_status=raw_status,
        extracted_status=extracted_status,
        bbox_quality=bbox_quality,
        leader_status=leader_status if gold.get("leader_required") else "LEADER_MISSING",
        usable_local_n=len(usable_local),
        giant_nearby=giant_nearby,
    )

    notes_parts = []
    if gold.get("reason"):
        notes_parts.append(gold["reason"][:180])
    if nearest:
        notes_parts.append(
            f"nearest_raw: len={nearest.get('path_length')} perp={nearest.get('perp_distance')} "
            f"kept={nearest.get('retained_by_cap')} kind={nearest.get('classified_kind')} "
            f"drop={nearest.get('drop_reason')}"
        )
    notes_parts.append(f"usable_local_member_kind={len(usable_local)}")

    return {
        "token_id": gold["token_id"],
        "page": int(gold["page"]),
        "label_text": gold.get("text"),
        "label_class": label_class(gold.get("text") or ""),
        "label_bbox": list(bb),
        "gold_decision": gold.get("decision"),
        "gold_geometry_id": gold_gid,
        "visible_member_on_drawing": bool(gold.get("visible_member_on_drawing")),
        "leader_required": bool(gold.get("leader_required")),
        "error_bucket": gold.get("error_bucket"),
        "raw_geometry_status": raw_status,
        "extracted_geometry_status": extracted_status,
        "candidate_geometry_count": len(gold.get("candidate_geometry_ids") or []),
        "usable_local_geometry_count": len(usable_local),
        "local_population_candidate_count": len(local_cands),
        "gold_geometry_present_in_current_population": gold_present,
        "gold_geometry_bbox": None if not gold_geom_desc else gold_geom_desc["bbox"],
        "gold_geometry_kind": None if not gold_geom_desc else gold_geom_desc["kind"],
        "bbox_quality": bbox_quality,
        "giant_geometry_flag": bbox_quality == "GIANT_BBOX" or giant_nearby,
        "short_geometry_flag": short_flag,
        "leader_target_status": (
            leader_status if gold.get("leader_required") else "not_applicable"
        ),
        "likely_failure_stage": failure,
        "nearest_raw": EA._strip(nearest) if nearest else None,
        "primary_geometry": primary_geom,
        "label_geometry_distances": label_to_geom,
        "usable_local_top": usable_local[:5],
        "notes": " | ".join(notes_parts),
    }


def feature_readiness_table() -> List[Dict[str, str]]:
    """Static evidence table from geometry.json schema + audit observations."""
    rows = [
        ("geometry bbox", "YES", "PARTIAL", "YES", "Present on all objects; giant/compound bboxes are common on framing pages."),
        ("centroid", "YES", "YES", "YES", "Derived from bbox; reliable when bbox is LOCAL."),
        ("path length", "YES", "YES", "YES", "Always populated for retained strokes."),
        ("orientation", "YES", "YES", "YES", "Present for lines; useful with label alignment later."),
        ("start/end", "PARTIAL", "PARTIAL", "YES", "Available via points[0]/points[-1] when points exist."),
        ("point count", "YES", "YES", "PARTIAL", "Useful for compound detection; not a member signal alone."),
        ("closed/open", "NO", "NO", "PARTIAL", "Not an explicit field; only inferable from kind/points."),
        ("geometry kind", "YES", "PARTIAL", "YES", "Reliable as extractor output; dimension/leader reclass still filters members."),
        ("label bbox", "YES", "YES", "YES", "Present in gold and document tokens."),
        ("label orientation", "NO", "NO", "YES", "Not stored on gold rows; would need derivation from text span."),
        ("text→geometry distance", "PARTIAL", "YES", "YES", "Computable from bboxes/centroids; not pre-stored."),
        ("leader endpoint", "PARTIAL", "PARTIAL", "YES", "Inferable from raw endpoints; often cap-dropped before retention."),
        ("source/path ID", "PARTIAL", "YES", "PARTIAL", "geometry_id stable in artifact; raw drawing id not persisted."),
    ]
    return [
        {
            "feature": f,
            "exists": e,
            "reliable": r,
            "useful_for_association": u,
            "notes": n,
        }
        for f, e, r, u, n in rows
    ]


def decide_gate(summary: Dict[str, Any]) -> str:
    """Gate decision from quantified blockers — representation readiness only."""
    metrics = summary["metrics"]
    blockers = summary["dominant_blockers"]
    # Hard blockers for association work.
    pop_gap = blockers.get("GEOMETRY_POPULATION_GAP", 0)
    seg_gap = blockers.get("SEGMENTATION_GAP", 0)
    leader_gap = blockers.get("LEADER_TARGET_GAP", 0)
    visible_miss = metrics["missing_candidate_visible_member_n"]
    usable_among_visible = metrics["visible_miss_with_usable_local_geometry"]
    retention_rate = metrics["current_retention_rate_among_raw_present"]
    gold_cov = metrics["gold_geometry_coverage_among_associated"]

    if gold_cov < 1.0:
        return "REPRESENTATION_NOT_READY"
    if retention_rate < 0.55:
        return "REPRESENTATION_NOT_READY"
    if usable_among_visible / max(visible_miss, 1) < 0.45:
        return "REPRESENTATION_NOT_READY"
    if pop_gap >= 20 or leader_gap >= 10 or seg_gap >= 8:
        return "REPRESENTATION_NOT_READY"
    if pop_gap == 0 and seg_gap == 0 and leader_gap == 0 and metrics["bbox_usable_rate"] >= 0.8:
        return "ASSOCIATION_READY_NOW"
    return "REPRESENTATION_READY_FOR_ASSOCIATION"


def write_report(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    m = summary["metrics"]
    gate = summary["g7_gate"]
    lines: List[str] = []
    lines.append("# Geometry / BBox Representation Audit (G7)\n")
    lines.append(
        "Read-only audit of Burrville human-gold pages (p8 / p18 / p24) before any "
        "new text↔geometry association work.\n"
    )
    lines.append(f"**Document:** `{DOC_ID}`  ")
    lines.append(f"**Gold SHA:** `{summary['gold_sha256']}`  ")
    lines.append(f"**Cases:** {summary['n_cases']}  ")
    lines.append(f"**G7_GATE = `{gate}`**\n")

    lines.append("## 1. Question\n")
    lines.append(
        "Before touching text↔geometry association, do we have reliable member-level "
        "geometry primitives and usable bounding boxes?\n"
    )

    lines.append("## 2. Population census (current artifact)\n")
    for page, census in summary["page_population"].items():
        lines.append(
            f"- **p{page}:** {census['n_objects']} objects; "
            f"kinds={census['kinds']}; "
            f"LOCAL={census['n_local_bbox']}, GIANT={census['n_giant_bbox']}, "
            f"COMPOUND={census['n_compound_bbox']}, DEGENERATE={census['n_degenerate_bbox']}; "
            f"usable_local_member_kind={census['n_usable_local_member_kind']}; "
            f"short_member_kind_retained={census['n_short_member_kind_retained']}"
        )
    lines.append("")

    lines.append("## 3. Key metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Raw present (relevant visible-member cases) | {m['raw_present_relevant']} / {m['relevant_visible_n']} ({m['raw_presence_rate']:.2f}) |")
    lines.append(f"| Current retention among raw-present | {m['retained_among_raw_present']} / {m['raw_present_n']} ({m['current_retention_rate_among_raw_present']:.2f}) |")
    lines.append(f"| Usable LOCAL bbox among retained primary | {m['bbox_usable_n']} / {m['retained_primary_n']} ({m['bbox_usable_rate']:.2f}) |")
    lines.append(f"| Giant/compound flag rate (all cases) | {m['giant_or_compound_n']} / {m['n_cases']} ({m['giant_bbox_rate']:.2f}) |")
    lines.append(f"| Short-stroke nearest retained | {m['short_stroke_retained_n']} / {m['short_stroke_raw_n']} |")
    lines.append(f"| Leader-required with target present | {m['leader_target_present_n']} / {m['leader_required_n']} |")
    lines.append(f"| Gold geometry coverage (8 associated) | {m['gold_geometry_present_n']} / 8 ({m['gold_geometry_coverage_among_associated']:.2f}) |")
    lines.append(f"| Visible-miss cases with usable local geometry now | {m['visible_miss_with_usable_local_geometry']} / {m['missing_candidate_visible_member_n']} |")
    lines.append("")
    lines.append(
        "> **Interpretation note:** `usable local geometry` counts any retained "
        "member-kind LOCAL bbox near the label. It does **not** prove that the "
        "correct labeled member survived. The on-label stroke retention rate "
        f"({m['current_retention_rate_among_raw_present']:.2f}) is the stricter "
        "representation signal.\n"
    )

    lines.append("## 4. Dominant blockers\n")
    for k, v in summary["dominant_blockers"].items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    lines.append("Failure-stage histogram (per gold case):")
    for k, v in summary["failure_stage_counts"].items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    lines.append("## 5. Giant polyline audit\n")
    lines.append(
        "Giant/compound primitives remain in the retained population on framing pages. "
        "Simple long lines (2 points, length ≈ bbox diagonal) are distinguishable from "
        "multi-point compound polylines via point_count + length/diagonal, but the current "
        "primitive is still one bbox for the whole path — **segmentation would be required** "
        "before treating giant bay polylines as member-level candidates.\n"
    )
    for page, census in summary["page_population"].items():
        if not census["giant_examples"]:
            continue
        lines.append(f"### p{page} giant examples\n")
        lines.append("| geometry_id | kind | point_count | path_length | bbox |")
        lines.append("|---|---|---:|---:|---|")
        for g in census["giant_examples"][:6]:
            lines.append(
                f"| `{g['geometry_id']}` | {g['kind']} | {g['point_count']} | "
                f"{g['path_length']} | `{g['bbox']}` |"
            )
        lines.append("")

    lines.append("## 6. Small / short-stroke classes\n")
    lines.append("| Class | n_gold | raw_present | retained | usable_local |")
    lines.append("|---|---:|---:|---:|---:|")
    for cls, stats in summary["class_audit"].items():
        lines.append(
            f"| {cls} | {stats['n']} | {stats['raw_present']} | "
            f"{stats['retained']} | {stats['usable_local']} |"
        )
    lines.append("")

    lines.append("## 7. Leader target geometry\n")
    lines.append(
        f"Leader-required gold cases: **{m['leader_required_n']}**. "
        f"Target present: **{m['leader_target_present_n']}**. "
        f"Leader present / target missing: **{m['leader_present_target_missing_n']}**. "
        f"Leader missing: **{m['leader_missing_n']}**.\n"
    )
    lines.append(
        "A leader stroke is not the member. Many detail/section callouts lose either the "
        "leader or the tip-neighborhood target under CAP_450 / classification.\n"
    )

    lines.append("## 8. Feature readiness for future association\n")
    lines.append("| Feature | Exists? | Reliable? | Useful for association? | Notes |")
    lines.append("|---|---|---|---|---|")
    for row in summary["feature_table"]:
        lines.append(
            f"| {row['feature']} | {row['exists']} | {row['reliable']} | "
            f"{row['useful_for_association']} | {row['notes']} |"
        )
    lines.append("")

    lines.append("## 9. Associated gold coverage\n")
    assoc = [r for r in rows if r["gold_decision"] == "associated"]
    lines.append("| token_id | gold_geometry_id | present | kind | bbox_quality |")
    lines.append("|---|---|---|---|---|")
    for r in assoc:
        lines.append(
            f"| `{r['token_id']}` | `{r['gold_geometry_id']}` | "
            f"{r['gold_geometry_present_in_current_population']} | "
            f"{r['gold_geometry_kind']} | {r['bbox_quality']} |"
        )
    lines.append("")

    lines.append("## 10. What this does **not** conclude\n")
    lines.append(
        "This audit does not score association accuracy. Retrieval may still rank the wrong "
        "LOCAL candidate even when representation is adequate for that neighborhood.\n"
    )

    lines.append("## 11. Verdict\n")
    lines.append(f"**G7_GATE = `{gate}`**\n")
    if gate == "REPRESENTATION_NOT_READY":
        lines.append(
            "Member-level geometry population and/or bbox localization are still materially "
            "insufficient for a clean association experiment. Fix population retention "
            "(short strokes / detail targets), reduce giant-compound candidate dominance, "
            "and/or restore leader-target primitives before association work.\n"
        )
    elif gate == "REPRESENTATION_READY_FOR_ASSOCIATION":
        lines.append(
            "Core features (bbox, length, orientation, kind) exist and associated gold "
            "geometries are present, but residual population/leader/segmentation gaps remain. "
            "A dedicated association experiment is allowed only with those gaps tracked as "
            "explicit exclusion / stratification axes — not assumed solved.\n"
        )
    else:
        lines.append(
            "Representation blockers are not material; association itself can be the next "
            "isolated focus.\n"
        )

    lines.append("## 12. Safety\n")
    lines.append(
        f"- Gold SHA unchanged: `{summary['gold_sha256']}`\n"
        f"- Production files not modified by this audit script\n"
        f"- Own-label dimension fix left untouched\n"
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_review_html(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>G7 Geometry BBox Audit</title>",
        "<style>body{font-family:ui-sans-serif,system-ui;margin:24px}"
        "table{border-collapse:collapse;width:100%;font-size:12px}"
        "th,td{border:1px solid #ccc;padding:4px 6px;vertical-align:top}"
        "th{background:#f4f4f4;position:sticky;top:0}.giant{background:#ffe8e8}"
        ".ok{background:#e8ffe8}</style></head><body>",
        f"<h1>G7 Geometry / BBox Audit</h1>",
        f"<p><b>G7_GATE = {html.escape(summary['g7_gate'])}</b> · "
        f"{summary['n_cases']} cases · gold "
        f"<code>{html.escape(summary['gold_sha256'][:16])}…</code></p>",
        "<table><tr>"
        "<th>token</th><th>page</th><th>text</th><th>gold</th>"
        "<th>raw</th><th>extracted</th><th>bbox_q</th><th>usable_local</th>"
        "<th>leader</th><th>failure</th><th>crop</th></tr>",
    ]
    for r in rows:
        cls = "giant" if r.get("giant_geometry_flag") else ""
        if r.get("gold_decision") == "associated" and r.get(
            "gold_geometry_present_in_current_population"
        ):
            cls = "ok"
        crop = RENDER_DIR / f"{r['token_id']}.png"
        img = (
            f"<img src='geometry_bbox_audit_g7_renders/{html.escape(r['token_id'])}.png' width='160'/>"
            if crop.exists()
            else ""
        )
        parts.append(
            f"<tr class='{cls}'>"
            f"<td>{html.escape(r['token_id'])}</td>"
            f"<td>{r['page']}</td>"
            f"<td>{html.escape(str(r.get('label_text') or ''))}</td>"
            f"<td>{html.escape(str(r.get('gold_decision') or ''))}</td>"
            f"<td>{html.escape(r['raw_geometry_status'])}</td>"
            f"<td>{html.escape(r['extracted_geometry_status'])}</td>"
            f"<td>{html.escape(str(r.get('bbox_quality') or ''))}</td>"
            f"<td>{r.get('usable_local_geometry_count')}</td>"
            f"<td>{html.escape(str(r.get('leader_target_status') or ''))}</td>"
            f"<td>{html.escape(str(r.get('likely_failure_stage') or ''))}</td>"
            f"<td>{img}</td></tr>"
        )
    parts.append("</table></body></html>")
    REVIEW_HTML.write_text("\n".join(parts), encoding="utf-8")


def render_case(
    pdf: "fitz.Document",
    replay: EA.PageReplay,
    row: Dict[str, Any],
    artifact_by_id: Dict[str, Dict[str, Any]],
) -> None:
    page = pdf[row["page"] - 1]
    label_bb = row["label_bbox"]
    # Draw usable local in green, giants in orange, gold in magenta, label in blue.
    for cand in row.get("usable_local_top") or []:
        bb = cand.get("bbox")
        if bb:
            page.draw_rect(fitz.Rect(bb), color=(0.05, 0.55, 0.15), width=1.3)
    if row.get("giant_geometry_flag"):
        for cand in (row.get("usable_local_top") or [])[:1]:
            pass
        # Highlight nearest raw if giant
    if row.get("gold_geometry_bbox"):
        page.draw_rect(fitz.Rect(row["gold_geometry_bbox"]), color=(0.8, 0.05, 0.55), width=1.8)
    # Also outline any giant page objects near label from artifact
    for o in replay.merged:
        qm = classify_bbox_quality(
            o["bbox"],
            length=o.get("length"),
            point_count=len(o.get("points") or []),
            page_width=replay.page_width,
            page_height=replay.page_height,
        )
        if qm != "GIANT_BBOX":
            continue
        if _bbox_distance(label_bb, o["bbox"]) < 200:
            page.draw_rect(fitz.Rect(o["bbox"]), color=(0.95, 0.45, 0.05), width=1.2)
    page.draw_rect(fitz.Rect(label_bb), color=(0.1, 0.35, 0.92), width=1.8)
    cx = (label_bb[0] + label_bb[2]) / 2.0
    cy = (label_bb[1] + label_bb[3]) / 2.0
    clip = fitz.Rect(cx - 160, cy - 160, cx + 160, cy + 160)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=clip, alpha=False)
    pix.save(str(RENDER_DIR / f"{row['token_id']}.png"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renders", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    gold_bytes = GOLD_PATH.read_bytes()
    gold_sha = hashlib.sha256(gold_bytes).hexdigest()
    if gold_sha != EXPECTED_GOLD_SHA:
        raise SystemExit(f"Gold SHA mismatch: {gold_sha} != {EXPECTED_GOLD_SHA}")

    gold_rows = [
        json.loads(line)
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(gold_rows) != 75:
        raise SystemExit(f"Expected 75 gold rows, got {len(gold_rows)}")

    document = json.loads((ARTIFACT / "document.json").read_text(encoding="utf-8"))
    artifact_geometry = json.loads((ARTIFACT / "geometry.json").read_text(encoding="utf-8"))
    objects = artifact_geometry["objects"]
    artifact_by_id = {o["geometry_id"]: o for o in objects}
    page_scales = detect_page_scales(document)

    if not PDF_PATH.exists():
        raise SystemExit(f"PDF missing: {PDF_PATH}")

    pdf = fitz.open(str(PDF_PATH))
    replays: Dict[int, EA.PageReplay] = {}
    page_population: Dict[str, Any] = {}
    for page in PAGES:
        replay = EA.PageReplay(pdf[page - 1], page, document, page_scales)
        replays[page] = replay
        page_population[str(page)] = population_census(
            objects, page, replay.page_width, replay.page_height
        )

    rows: List[Dict[str, Any]] = []
    for gold in gold_rows:
        page = int(gold["page"])
        replay = replays[page]
        page_objs = [o for o in objects if int(o.get("page_number") or 0) == page]
        row = audit_case(gold, replay, page_objs, artifact_by_id)
        rows.append(row)
        if args.renders:
            # Use a fresh page clone via re-open clip drawing on same doc — redraws accumulate;
            # for QA crops this is acceptable; shapes are ephemeral on pixmap clip.
            render_case(pdf, replay, row, artifact_by_id)

    # --- metrics ---
    relevant = [
        r
        for r in rows
        if r.get("visible_member_on_drawing")
        or r["gold_decision"] == "associated"
    ]
    # Exclude schedule cells from "relevant visible".
    relevant_visible = [
        r
        for r in rows
        if r.get("visible_member_on_drawing") and r["error_bucket"] != "schedule_table_not_member"
    ]
    raw_present = [r for r in relevant_visible if r["raw_geometry_status"] == "RAW_PRESENT"]
    retained = [r for r in raw_present if r["extracted_geometry_status"] == "RETAINED"]
    filtered = [r for r in raw_present if r["extracted_geometry_status"] == "FILTERED"]

    retained_primary = [
        r
        for r in rows
        if r["extracted_geometry_status"] == "RETAINED" or r["gold_decision"] == "associated"
    ]
    bbox_usable = [r for r in retained_primary if r["bbox_quality"] == "LOCAL_BBOX"]

    visible_miss = [
        r
        for r in rows
        if r["gold_decision"] == "no_valid_member" and r.get("visible_member_on_drawing")
    ]
    visible_miss_usable = [r for r in visible_miss if r["usable_local_geometry_count"] > 0]

    assoc = [r for r in rows if r["gold_decision"] == "associated"]
    gold_present_n = sum(1 for r in assoc if r["gold_geometry_present_in_current_population"])

    leader_req = [r for r in rows if r.get("leader_required")]
    leader_present_target = [
        r for r in leader_req if r["leader_target_status"] == "TARGET_GEOMETRY_PRESENT"
    ]
    leader_pt_missing = [
        r for r in leader_req if r["leader_target_status"] == "LEADER_PRESENT_TARGET_MISSING"
    ]
    leader_missing = [r for r in leader_req if r["leader_target_status"] == "LEADER_MISSING"]

    short_raw = [r for r in rows if r.get("short_geometry_flag") and r["raw_geometry_status"] == "RAW_PRESENT"]
    short_ret = [r for r in short_raw if r["extracted_geometry_status"] == "RETAINED"]

    giant_n = sum(1 for r in rows if r.get("giant_geometry_flag") or r["bbox_quality"] in {"GIANT_BBOX", "COMPOUND_BBOX"})

    # Class audit
    class_audit: Dict[str, Dict[str, int]] = {}
    for r in rows:
        cls = r["label_class"]
        slot = class_audit.setdefault(
            cls, {"n": 0, "raw_present": 0, "retained": 0, "usable_local": 0}
        )
        slot["n"] += 1
        if r["raw_geometry_status"] == "RAW_PRESENT":
            slot["raw_present"] += 1
        if r["extracted_geometry_status"] == "RETAINED":
            slot["retained"] += 1
        if r["usable_local_geometry_count"] > 0:
            slot["usable_local"] += 1

    failure_counts = Counter(r["likely_failure_stage"] for r in rows)

    # Map failure stages → blocker categories
    blocker_map = {
        "geometry_population_gap": "GEOMETRY_POPULATION_GAP",
        "bbox_quality_gap": "BBOX_QUALITY_GAP",
        "segmentation_gap": "SEGMENTATION_GAP",
        "leader_target_gap": "LEADER_TARGET_GAP",
        "retrieval_gap_not_representation": "RETRIEVAL_GAP",
        "raw_geometry_gap": "GEOMETRY_POPULATION_GAP",
        "representation_sufficient_for_case": "NO_MAJOR_REPRESENTATION_GAP",
        "not_a_member_schedule": "NO_MAJOR_REPRESENTATION_GAP",
        "unknown": "FEATURE_GAP",
    }
    dominant_blockers: Counter = Counter()
    for stage, n in failure_counts.items():
        dominant_blockers[blocker_map.get(stage, "FEATURE_GAP")] += n

    metrics = {
        "n_cases": len(rows),
        "relevant_visible_n": len(relevant_visible),
        "raw_present_relevant": len(raw_present),
        "raw_present_n": len(raw_present),
        "raw_presence_rate": round(len(raw_present) / max(len(relevant_visible), 1), 4),
        "retained_among_raw_present": len(retained),
        "filtered_among_raw_present": len(filtered),
        "current_retention_rate_among_raw_present": round(
            len(retained) / max(len(raw_present), 1), 4
        ),
        "retained_primary_n": len(retained_primary),
        "bbox_usable_n": len(bbox_usable),
        "bbox_usable_rate": round(len(bbox_usable) / max(len(retained_primary), 1), 4),
        "giant_or_compound_n": giant_n,
        "giant_bbox_rate": round(giant_n / max(len(rows), 1), 4),
        "short_stroke_raw_n": len(short_raw),
        "short_stroke_retained_n": len(short_ret),
        "leader_required_n": len(leader_req),
        "leader_target_present_n": len(leader_present_target),
        "leader_present_target_missing_n": len(leader_pt_missing),
        "leader_missing_n": len(leader_missing),
        "gold_geometry_present_n": gold_present_n,
        "gold_geometry_coverage_among_associated": round(gold_present_n / max(len(assoc), 1), 4),
        "missing_candidate_visible_member_n": len(visible_miss),
        "visible_miss_with_usable_local_geometry": len(visible_miss_usable),
        "visible_miss_usable_rate": round(
            len(visible_miss_usable) / max(len(visible_miss), 1), 4
        ),
    }

    summary: Dict[str, Any] = {
        "document_id": DOC_ID,
        "pages": list(PAGES),
        "n_cases": len(rows),
        "gold_sha256": gold_sha,
        "metrics": metrics,
        "page_population": page_population,
        "class_audit": class_audit,
        "failure_stage_counts": dict(failure_counts),
        "dominant_blockers": dict(dominant_blockers),
        "feature_table": feature_readiness_table(),
        "raw_status_counts": dict(Counter(r["raw_geometry_status"] for r in rows)),
        "extracted_status_counts": dict(
            Counter(r["extracted_geometry_status"] for r in rows)
        ),
        "bbox_quality_counts": dict(Counter(r["bbox_quality"] for r in rows)),
        "leader_status_counts": dict(
            Counter(r["leader_target_status"] for r in rows if r.get("leader_required"))
        ),
        "segmentation_required": True,
        "segmentation_evidence": (
            "Multi-point polylines and page-scale bboxes coexist with member-scale strokes; "
            "point_count+length/diagonal can flag compounds but cannot split them into "
            "member-level primitives without segmentation."
        ),
    }
    summary["g7_gate"] = decide_gate(summary)

    OUT.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(EA._strip(r), sort_keys=True) + "\n")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(summary, rows)
    write_review_html(rows, summary)

    # Gold integrity after write
    gold_sha_after = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if gold_sha_after != EXPECTED_GOLD_SHA:
        raise SystemExit("Gold SHA changed during audit — abort")

    print(f"G7_GATE = {summary['g7_gate']}")
    print(f"wrote {RESULTS_PATH}")
    print(f"wrote {SUMMARY_PATH}")
    print(f"wrote {REPORT_PATH}")
    print(f"cases={len(rows)} raw_present_rate={metrics['raw_presence_rate']} "
          f"retention={metrics['current_retention_rate_among_raw_present']} "
          f"visible_miss_usable={metrics['visible_miss_with_usable_local_geometry']}/{metrics['missing_candidate_visible_member_n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
