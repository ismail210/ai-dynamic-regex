#!/usr/bin/env python3
"""G8 — Representation repair / candidate population experiment (R&D, read-only).

Recovers member-level geometry *candidates* from raw PyMuPDF drawings without
changing production extraction, CAP_450, retrieval, association, or gold.

Usage (from backend/):
    python scripts/rd_geometry_integration/representation_repair_g8.py [--renders]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fitz  # noqa: E402

import extraction_audit as EA  # noqa: E402
import geometry_bbox_audit_g7 as G7  # noqa: E402
from services.engineering import geometry_extractor as GX  # noqa: E402
from services.engineering.drawing_scale import detect_page_scales  # noqa: E402

DOC_ID = "doc_0d910a43b4a021e3"
ARTIFACT = ROOT / "training" / "engineering_artifacts" / DOC_ID / "multimodal"
PDF_PATH = ROOT / "uploads" / "Burrville ES - ST.pdf"
OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
GOLD_PATH = OUT / "review_kit" / "gold_outcomes.jsonl"
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
RESULTS_PATH = OUT / "representation_repair_g8_results.jsonl"
SUMMARY_PATH = OUT / "representation_repair_g8_summary.json"
REPORT_PATH = OUT / "GEOMETRY_REPRESENTATION_REPAIR_G8_REPORT.md"
RENDER_DIR = OUT / "representation_repair_g8_renders"
REVIEW_HTML = OUT / "representation_repair_g8_review.html"

PAGES = (8, 18, 24)
MEMBER_KINDS = G7.MEMBER_KINDS
FILTERED_KINDS = G7.FILTERED_KINDS

# R&D thresholds (not production knobs)
NEAR_LABEL_PT = 80.0
ON_LABEL_PERP_PT = 25.0
SHORT_MAX_PT = 80.0
MEMBER_MIN_LEN_PT = 18.0
MEMBER_MAX_EXTENT_PT = 500.0
GIANT_EXTENT_PT = 600.0
COMPOUND_LEN_RATIO = 1.35
SEGMENT_MIN_LEN_PT = 25.0
SEGMENT_MAX_EXTENT_PT = 400.0
TIP_RADIUS_PT = 40.0
LEADER_LEN_MIN = 8.0
LEADER_LEN_MAX = 200.0

CANDIDATE_KINDS = {
    "LINE_MEMBER_CANDIDATE",
    "SEGMENT_MEMBER_CANDIDATE",
    "PLATE_MEMBER_CANDIDATE",
    "SMALL_TARGET_CANDIDATE",
    "LEADER_TARGET_CANDIDATE",
    "NON_MEMBER",
    "UNKNOWN",
}

LOSS_CLASSES = {
    "RAW_PRESENT",
    "CAP_DROPPED",
    "RECLASSIFIED_DIMENSION",
    "RECLASSIFIED_LEADER",
    "OTHER_FILTER",
    "RETAINED_MEMBER",
    "RAW_AMBIGUOUS",
    "RAW_MISSING",
}

GIANT_CLASSES = {
    "SIMPLE_LONG_STROKE",
    "COMPOUND_POLYLINE",
    "PAGE_FRAME",
    "BAY_BOUNDARY",
    "UNKNOWN",
}


# ---------------------------------------------------------------------------
# raw identity / geometry helpers
# ---------------------------------------------------------------------------
def raw_drawing_index(page_number: int, drawing: Dict[str, Any], ordinal: int) -> str:
    """Stable deterministic raw id (no invention of production geometry_ids)."""
    rect = drawing.get("rect")
    if rect is not None:
        payload = (
            f"{page_number}|{ordinal}|"
            f"{float(rect.x0):.2f},{float(rect.y0):.2f},"
            f"{float(rect.x1):.2f},{float(rect.y1):.2f}|"
            f"{len(drawing.get('items') or [])}"
        )
    else:
        payload = f"{page_number}|{ordinal}|norect|{len(drawing.get('items') or [])}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"raw_p{page_number}_{ordinal}_{digest}"


def drawing_points(drawing: Dict[str, Any]) -> List[List[float]]:
    pts: List[List[float]] = []
    for a, b in EA._segments(drawing):
        if not pts:
            pts.append([float(a[0]), float(a[1])])
        pts.append([float(b[0]), float(b[1])])
    return pts


def drawing_bbox(drawing: Dict[str, Any]) -> Optional[List[float]]:
    rect = drawing.get("rect")
    if rect is None:
        return None
    return [
        round(float(rect.x0), 3),
        round(float(rect.y0), 3),
        round(float(rect.x1), 3),
        round(float(rect.y1), 3),
    ]


def classify_giant(
    bbox: Sequence[float],
    *,
    length: float,
    point_count: int,
    page_w: float,
    page_h: float,
    item_types: Optional[Sequence[str]] = None,
) -> str:
    m = G7._bbox_metrics(bbox)
    extent = max(m["width"], m["height"])
    if is_page_frame_bbox(bbox, page_w, page_h):
        return "PAGE_FRAME"
    npts = int(point_count or 0)
    diag = max(m["diagonal"], 1.0)
    # Compound can be mid-size; detect before the non-giant early-out.
    if npts >= 5 and length > COMPOUND_LEN_RATIO * diag:
        return "COMPOUND_POLYLINE"
    if extent < GIANT_EXTENT_PT and m["area"] < 0.08 * page_w * page_h:
        return "UNKNOWN"  # not giant
    if npts <= 2 and length <= 1.25 * diag:
        return "SIMPLE_LONG_STROKE"
    if npts <= 4 and extent >= GIANT_EXTENT_PT:
        return "BAY_BOUNDARY"
    if npts >= 5:
        return "COMPOUND_POLYLINE"
    return "UNKNOWN"


def is_page_frame_bbox(bbox: Sequence[float], page_w: float, page_h: float) -> bool:
    m = G7._bbox_metrics(bbox)
    return m["width"] > 0.85 * page_w and m["height"] > 0.85 * page_h


def stroke_role_guess(
    *,
    length: float,
    bbox: Sequence[float],
    point_count: int,
    item_types: Sequence[str],
    classified_kind: Optional[str],
    page_w: float,
    page_h: float,
) -> str:
    """Heuristic role for R&D only — not a member identity claim."""
    if is_page_frame_bbox(bbox, page_w, page_h):
        return "border_frame"
    types = set(item_types or [])
    if "re" in types and length < 120 and G7._bbox_metrics(bbox)["area"] < 8000:
        return "plate_or_symbol"
    if classified_kind == "leader" or (
        LEADER_LEN_MIN <= length <= LEADER_LEN_MAX
        and max(G7._bbox_metrics(bbox)["width"], G7._bbox_metrics(bbox)["height"]) < 180
    ):
        # thin short-mid strokes often leaders; keep as suspect
        if length <= 72 and point_count <= 3:
            return "leader_like"
    giant = classify_giant(
        bbox, length=length, point_count=point_count, page_w=page_w, page_h=page_h
    )
    if giant == "PAGE_FRAME":
        return "border_frame"
    if giant in {"COMPOUND_POLYLINE", "BAY_BOUNDARY"}:
        return "layout_or_compound"
    if giant == "SIMPLE_LONG_STROKE":
        return "simple_long_stroke"
    if length < 8:
        return "noise_or_hatch"
    if length < MEMBER_MIN_LEN_PT:
        return "too_short"
    extent = max(G7._bbox_metrics(bbox)["width"], G7._bbox_metrics(bbox)["height"])
    if extent <= MEMBER_MAX_EXTENT_PT and length >= MEMBER_MIN_LEN_PT:
        return "member_like"
    return "unrelated_or_ambiguous"


def segment_polyline(
    raw_id: str,
    drawing: Dict[str, Any],
    *,
    page: int,
    page_w: float,
    page_h: float,
) -> List[Dict[str, Any]]:
    """Deterministic vertex split for compound paths only (R&D)."""
    segs = EA._segments(drawing)
    if len(segs) < 2:
        return []
    points = drawing_points(drawing)
    bbox = drawing_bbox(drawing)
    if not bbox:
        return []
    length = EA._path_length(drawing)
    giant = classify_giant(
        bbox, length=length, point_count=len(points), page_w=page_w, page_h=page_h
    )
    if giant != "COMPOUND_POLYLINE":
        return []

    out: List[Dict[str, Any]] = []
    for i, (a, b) in enumerate(segs):
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg_len < SEGMENT_MIN_LEN_PT:
            continue
        sb = [
            round(min(a[0], b[0]), 3),
            round(min(a[1], b[1]), 3),
            round(max(a[0], b[0]), 3),
            round(max(a[1], b[1]), 3),
        ]
        extent = max(abs(sb[2] - sb[0]), abs(sb[3] - sb[1]))
        if extent > SEGMENT_MAX_EXTENT_PT:
            # keep but mark as still large
            pass
        orient = round(GX._orientation_deg(a, b), 2)
        cand_id = f"{raw_id}#seg{i}"
        out.append(
            make_candidate(
                candidate_id=cand_id,
                source_raw_id=raw_id,
                source_type="compound_polyline_segment",
                page=page,
                bbox=sb,
                length=round(seg_len, 3),
                orientation=orient,
                point_count=2,
                candidate_kind=(
                    "SEGMENT_MEMBER_CANDIDATE"
                    if extent <= SEGMENT_MAX_EXTENT_PT
                    else "UNKNOWN"
                ),
                derivation="vertex_split",
                confidence_basis=(
                    "compound_path_length_exceeds_bbox_diagonal;"
                    "segment_length_ge_min;"
                    "no_member_identity_assigned"
                ),
                provenance={
                    "source_page": page,
                    "source_raw_id": raw_id,
                    "source_geometry_id": None,
                    "derivation_type": "vertex_split",
                    "original_bbox": bbox,
                    "derived_bbox": sb,
                    "original_point_count": len(points),
                    "derived_point_count": 2,
                    "segment_index": i,
                },
            )
        )
    return out


def make_candidate(**kwargs: Any) -> Dict[str, Any]:
    kind = kwargs["candidate_kind"]
    assert kind in CANDIDATE_KINDS, kind
    return {
        "candidate_id": kwargs["candidate_id"],
        "source_raw_id": kwargs["source_raw_id"],
        "source_type": kwargs["source_type"],
        "page": kwargs["page"],
        "bbox": kwargs["bbox"],
        "length": kwargs["length"],
        "orientation": kwargs.get("orientation"),
        "point_count": kwargs["point_count"],
        "candidate_kind": kind,
        "derivation": kwargs["derivation"],
        "confidence_basis": kwargs["confidence_basis"],
        "provenance": kwargs["provenance"],
    }


def candidate_kind_for_role(role: str, *, closed_rect: bool = False) -> str:
    if role == "member_like":
        return "LINE_MEMBER_CANDIDATE"
    if role == "plate_or_symbol":
        return "PLATE_MEMBER_CANDIDATE" if closed_rect else "SMALL_TARGET_CANDIDATE"
    if role == "simple_long_stroke":
        # Representable, but not auto-promoted as a member candidate (giant control).
        return "UNKNOWN"
    if role in {"border_frame", "layout_or_compound", "leader_like", "noise_or_hatch", "too_short"}:
        return "NON_MEMBER"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# per-case audit
# ---------------------------------------------------------------------------
def nearest_on_label(
    replay: EA.PageReplay, lx: float, ly: float
) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    best: Optional[Tuple[float, int, Dict[str, Any]]] = None
    for idx, drawing in enumerate(replay.raw):
        rect = drawing.get("rect")
        if rect is None:
            continue
        if not (
            rect.x0 - NEAR_LABEL_PT <= lx <= rect.x1 + NEAR_LABEL_PT
            and rect.y0 - NEAR_LABEL_PT <= ly <= rect.y1 + NEAR_LABEL_PT
        ):
            continue
        dist, t = EA._nearest_on_path(lx, ly, drawing)
        if dist > ON_LABEL_PERP_PT or not (-0.05 <= t <= 1.05):
            continue
        length = EA._path_length(drawing)
        if length < 8:
            continue
        if best is None or dist < best[0]:
            best = (dist, idx, drawing)
    if best is None:
        # ambiguous band
        for idx, drawing in enumerate(replay.raw):
            rect = drawing.get("rect")
            if rect is None:
                continue
            if not (
                rect.x0 - NEAR_LABEL_PT <= lx <= rect.x1 + NEAR_LABEL_PT
                and rect.y0 - NEAR_LABEL_PT <= ly <= rect.y1 + NEAR_LABEL_PT
            ):
                continue
            dist, t = EA._nearest_on_path(lx, ly, drawing)
            if dist > NEAR_LABEL_PT or not (0.0 <= t <= 1.0):
                continue
            length = EA._path_length(drawing)
            if length < 12:
                continue
            if best is None or dist < best[0]:
                best = (dist, idx, drawing)
        if best is None:
            return None, None
        return {
            "_ambiguous": True,
            "_perp": best[0],
            "_drawing": best[2],
            "_ordinal": best[1],
        }, best[1]
    return {
        "_ambiguous": False,
        "_perp": best[0],
        "_drawing": best[2],
        "_ordinal": best[1],
    }, best[1]


def describe_raw_hit(
    replay: EA.PageReplay, hit: Dict[str, Any]
) -> Dict[str, Any]:
    drawing = hit["_drawing"]
    ordinal = hit["_ordinal"]
    raw_id = raw_drawing_index(replay.page_number, drawing, ordinal)
    bbox = drawing_bbox(drawing) or [0, 0, 0, 0]
    length = EA._path_length(drawing)
    points = drawing_points(drawing)
    kept = id(drawing) in replay.kept_ids
    obj = replay.object_by_raw.get(id(drawing))
    final_id = replay.final_id_for(drawing)
    drop = None if kept else EA._drop_reason(drawing, replay.page_width, replay.page_height)
    kind = None if not obj else obj.get("kind")
    before = None if not obj else obj.get("classified_kind_before_reclass")
    reclass = None if not obj else obj.get("reclassified_by")
    role = stroke_role_guess(
        length=length,
        bbox=bbox,
        point_count=len(points),
        item_types=EA._item_types(drawing),
        classified_kind=kind,
        page_w=replay.page_width,
        page_h=replay.page_height,
    )
    proposed_kind = candidate_kind_for_role(role, closed_rect="re" in set(EA._item_types(drawing)))
    return {
        "token_trace": {
            "raw_geometry_id_or_index": raw_id,
            "raw_bbox": bbox,
            "raw_length": round(length, 3),
            "raw_point_count": len(points),
            "raw_item_types": EA._item_types(drawing),
            "retained_by_cap": kept,
            "current_final_geometry_id": final_id,
            "current_kind": kind,
            "classified_kind_before_reclass": before,
            "reclassified_by": reclass,
            "drop_reason": drop,
            "proposed_rnd_candidate_kind": proposed_kind,
            "proposed_reason": role,
            "perp_distance": round(float(hit["_perp"]), 3),
            "ambiguous_band": bool(hit.get("_ambiguous")),
        },
        "_drawing": drawing,
        "_raw_id": raw_id,
        "_role": role,
        "_length": length,
        "_bbox": bbox,
        "_points": points,
        "_kept": kept,
        "_kind": kind,
        "_final_id": final_id,
    }


def loss_class_from_hit(hit_desc: Optional[Dict[str, Any]], gold: Dict[str, Any]) -> str:
    if gold.get("error_bucket") == "schedule_table_not_member":
        return "RAW_MISSING"
    if hit_desc is None:
        return "RAW_MISSING"
    tr = hit_desc["token_trace"]
    if tr.get("ambiguous_band"):
        return "RAW_AMBIGUOUS"
    if not tr["retained_by_cap"]:
        return "CAP_DROPPED"
    kind = tr.get("current_kind")
    if kind == "dimension" or (tr.get("reclassified_by") or "").startswith("looks_like_dimension"):
        return "RECLASSIFIED_DIMENSION"
    if kind == "leader" or (tr.get("reclassified_by") or "") == "looks_like_leader":
        return "RECLASSIFIED_LEADER"
    if kind in MEMBER_KINDS:
        return "RETAINED_MEMBER"
    if kind in FILTERED_KINDS:
        return "OTHER_FILTER"
    return "OTHER_FILTER"


def build_candidate_from_raw(
    replay: EA.PageReplay,
    hit_desc: Dict[str, Any],
    *,
    derivation: str,
) -> Optional[Dict[str, Any]]:
    role = hit_desc["_role"]
    kind = candidate_kind_for_role(
        role, closed_rect="re" in set(hit_desc["token_trace"]["raw_item_types"])
    )
    if kind == "NON_MEMBER":
        return None
    if kind == "UNKNOWN":
        return None
    # Exclude giants that aren't localized member-scale strokes
    giant = classify_giant(
        hit_desc["_bbox"],
        length=hit_desc["_length"],
        point_count=len(hit_desc["_points"]),
        page_w=replay.page_width,
        page_h=replay.page_height,
    )
    if giant in {"PAGE_FRAME", "COMPOUND_POLYLINE", "BAY_BOUNDARY", "SIMPLE_LONG_STROKE"}:
        return None
    extent = max(
        G7._bbox_metrics(hit_desc["_bbox"])["width"],
        G7._bbox_metrics(hit_desc["_bbox"])["height"],
    )
    if extent >= GIANT_EXTENT_PT:
        return None
    if extent > MEMBER_MAX_EXTENT_PT and hit_desc["_length"] > MEMBER_MAX_EXTENT_PT:
        return None
    pts = hit_desc["_points"]
    orient = None
    if len(pts) >= 2:
        orient = round(GX._orientation_deg(pts[0], pts[-1]), 2)
    raw_id = hit_desc["_raw_id"]
    return make_candidate(
        candidate_id=f"rnd_{raw_id}",
        source_raw_id=raw_id,
        source_type="raw_drawing",
        page=replay.page_number,
        bbox=hit_desc["_bbox"],
        length=round(hit_desc["_length"], 3),
        orientation=orient,
        point_count=len(pts),
        candidate_kind=kind,
        derivation=derivation,
        confidence_basis=f"role={role};loss_recovery;no_section_identity",
        provenance={
            "source_page": replay.page_number,
            "source_raw_id": raw_id,
            "source_geometry_id": hit_desc.get("_final_id"),
            "derivation_type": derivation,
            "original_bbox": hit_desc["_bbox"],
            "derived_bbox": hit_desc["_bbox"],
            "original_point_count": len(pts),
            "derived_point_count": len(pts),
            "current_kind": hit_desc.get("_kind"),
            "retained_by_cap": hit_desc.get("_kept"),
        },
    )


def nearby_raw_candidates(
    replay: EA.PageReplay, label_bbox: Sequence[float], limit: int = 12
) -> List[Dict[str, Any]]:
    lx = (float(label_bbox[0]) + float(label_bbox[2])) / 2.0
    ly = (float(label_bbox[1]) + float(label_bbox[3])) / 2.0
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for idx, drawing in enumerate(replay.raw):
        bbox = drawing_bbox(drawing)
        if not bbox:
            continue
        if G7._bbox_distance(label_bbox, bbox) > NEAR_LABEL_PT:
            if G7._centroid_distance(label_bbox, bbox) > NEAR_LABEL_PT * 1.6:
                continue
        length = EA._path_length(drawing)
        if length < MEMBER_MIN_LEN_PT:
            continue
        hit = {
            "_ambiguous": False,
            "_perp": EA._nearest_on_path(lx, ly, drawing)[0],
            "_drawing": drawing,
            "_ordinal": idx,
        }
        desc = describe_raw_hit(replay, hit)
        cand = build_candidate_from_raw(
            replay,
            desc,
            derivation=(
                "cap_restore"
                if not desc["_kept"]
                else (
                    "reclass_restore"
                    if desc.get("_kind") in FILTERED_KINDS
                    else "retained_member"
                )
            ),
        )
        if cand is None:
            continue
        scored.append((cand["provenance"].get("source_geometry_id") is None, hit["_perp"], cand))
    scored.sort(key=lambda t: (t[1], t[0]))
    # unique by candidate_id
    seen = set()
    out = []
    for _flag, _d, cand in scored:
        if cand["candidate_id"] in seen:
            continue
        seen.add(cand["candidate_id"])
        out.append(cand)
        if len(out) >= limit:
            break
    return out


def compound_segments_near_label(
    replay: EA.PageReplay, label_bbox: Sequence[float]
) -> List[Dict[str, Any]]:
    lx = (float(label_bbox[0]) + float(label_bbox[2])) / 2.0
    ly = (float(label_bbox[1]) + float(label_bbox[3])) / 2.0
    out: List[Dict[str, Any]] = []
    for idx, drawing in enumerate(replay.raw):
        bbox = drawing_bbox(drawing)
        if not bbox:
            continue
        if G7._centroid_distance(label_bbox, bbox) > 350:
            continue
        points = drawing_points(drawing)
        length = EA._path_length(drawing)
        giant = classify_giant(
            bbox,
            length=length,
            point_count=len(points),
            page_w=replay.page_width,
            page_h=replay.page_height,
        )
        if giant != "COMPOUND_POLYLINE":
            continue
        raw_id = raw_drawing_index(replay.page_number, drawing, idx)
        for seg in segment_polyline(
            raw_id, drawing, page=replay.page_number, page_w=replay.page_width, page_h=replay.page_height
        ):
            if G7._bbox_distance(label_bbox, seg["bbox"]) > NEAR_LABEL_PT:
                if G7._centroid_distance(label_bbox, seg["bbox"]) > NEAR_LABEL_PT * 1.5:
                    continue
            # prefer segments near label center
            dist, _t = EA._point_to_segment(lx, ly, seg["bbox"][:2], seg["bbox"][2:])
            # crude; also check endpoints
            a = [seg["bbox"][0], (seg["bbox"][1] + seg["bbox"][3]) / 2]
            # use provenance segment
            out.append(seg)
    # dedupe
    seen = set()
    uniq = []
    for s in out:
        if s["candidate_id"] in seen:
            continue
        seen.add(s["candidate_id"])
        uniq.append(s)
    return uniq[:20]


def leader_target_audit(
    gold: Dict[str, Any], replay: EA.PageReplay, lx: float, ly: float
) -> Dict[str, Any]:
    if not gold.get("leader_required"):
        return {
            "leader_target_status": "not_applicable",
            "leaders": [],
            "tip": None,
            "tip_candidates": [],
        }
    trace = EA._leader_trace(replay, lx, ly)
    if not trace.get("leader_present"):
        return {
            "leader_target_status": "LEADER_MISSING",
            "leaders": EA._strip(trace.get("leaders") or []),
            "tip": None,
            "tip_candidates": [],
        }
    tip = trace["tip"]
    tip_cands: List[Dict[str, Any]] = []
    status = "NO_TARGET_EVIDENCE"
    memberlike = 0
    nonmember = 0
    ambiguous = 0
    missing_cap = 0
    missing_class = 0

    for tgt in trace.get("tip_targets") or []:
        drawing = tgt.get("_drawing")
        if drawing is None:
            continue
        # find ordinal
        ordinal = next((i for i, d in enumerate(replay.raw) if d is drawing), -1)
        raw_id = raw_drawing_index(replay.page_number, drawing, max(ordinal, 0))
        bbox = drawing_bbox(drawing) or [0, 0, 0, 0]
        length = float(tgt.get("path_length") or EA._path_length(drawing))
        points = drawing_points(drawing)
        role = stroke_role_guess(
            length=length,
            bbox=bbox,
            point_count=len(points),
            item_types=tgt.get("item_types") or EA._item_types(drawing),
            classified_kind=tgt.get("classified_kind"),
            page_w=replay.page_width,
            page_h=replay.page_height,
        )
        kept = bool(tgt.get("retained_by_cap"))
        kind = tgt.get("classified_kind")
        entry = {
            "raw_id": raw_id,
            "bbox": bbox,
            "length": length,
            "role": role,
            "retained_by_cap": kept,
            "classified_kind": kind,
            "tip_distance": tgt.get("tip_distance"),
        }
        tip_cands.append(entry)
        if role == "member_like" or role == "plate_or_symbol" or role == "simple_long_stroke":
            if kept and kind in MEMBER_KINDS:
                memberlike += 1
            elif kept and kind in FILTERED_KINDS:
                missing_class += 1
            elif not kept:
                missing_cap += 1
            else:
                memberlike += 1
        elif role in {"leader_like", "border_frame", "noise_or_hatch"}:
            nonmember += 1
        else:
            ambiguous += 1

    # Also scan tip neighborhood raw drawings not in tip_targets
    if tip:
        for idx, drawing in enumerate(replay.raw):
            bbox = drawing_bbox(drawing)
            if not bbox:
                continue
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            if math.hypot(cx - tip[0], cy - tip[1]) > TIP_RADIUS_PT:
                dist, _ = EA._nearest_on_path(tip[0], tip[1], drawing)
                if dist > TIP_RADIUS_PT:
                    continue
            length = EA._path_length(drawing)
            if length < MEMBER_MIN_LEN_PT:
                continue
            # skip the leader itself
            if any(abs(length - float(L.get("path_length") or 0)) < 0.5 for L in (trace.get("leaders") or [])[:1]):
                # weak skip
                pass
            role = stroke_role_guess(
                length=length,
                bbox=bbox,
                point_count=len(drawing_points(drawing)),
                item_types=EA._item_types(drawing),
                classified_kind=(replay.object_by_raw.get(id(drawing)) or {}).get("kind"),
                page_w=replay.page_width,
                page_h=replay.page_height,
            )
            if role in {"member_like", "plate_or_symbol"}:
                kept = id(drawing) in replay.kept_ids
                kind = (replay.object_by_raw.get(id(drawing)) or {}).get("kind")
                tip_cands.append(
                    {
                        "raw_id": raw_drawing_index(replay.page_number, drawing, idx),
                        "bbox": bbox,
                        "length": round(length, 3),
                        "role": role,
                        "retained_by_cap": kept,
                        "classified_kind": kind,
                        "tip_distance": round(
                            EA._nearest_on_path(tip[0], tip[1], drawing)[0], 3
                        ),
                        "from_neighborhood_scan": True,
                    }
                )
                if kept and kind in FILTERED_KINDS:
                    missing_class += 1
                elif not kept:
                    missing_cap += 1
                else:
                    memberlike += 1

    # Prefer memberlike tip targets; also recover CAP/class-filtered memberlike tips.
    if memberlike > 0:
        status = "TARGET_PRESENT_MEMBERLIKE"
    elif missing_cap > 0 and memberlike == 0:
        status = "TARGET_MISSING_AFTER_CAP"
    elif missing_class > 0 and memberlike == 0:
        status = "TARGET_MISSING_AFTER_CLASSIFICATION"
    elif nonmember > 0 and ambiguous == 0:
        status = "TARGET_PRESENT_NON_MEMBER"
    elif tip_cands:
        status = "TARGET_PRESENT_AMBIGUOUS"
    else:
        status = "NO_TARGET_EVIDENCE"

    # Build recoverable tip candidates (R&D) — memberlike / plate only.
    recoverable = []
    for entry in tip_cands:
        if entry["role"] not in {"member_like", "plate_or_symbol"}:
            continue
        extent = max(
            G7._bbox_metrics(entry["bbox"])["width"],
            G7._bbox_metrics(entry["bbox"])["height"],
        )
        if extent >= GIANT_EXTENT_PT:
            continue
        ck = (
            "LEADER_TARGET_CANDIDATE"
            if entry["role"] == "member_like"
            else "PLATE_MEMBER_CANDIDATE"
        )
        recoverable.append(
            make_candidate(
                candidate_id=f"rnd_tip_{entry['raw_id']}",
                source_raw_id=entry["raw_id"],
                source_type="leader_tip_neighborhood",
                page=replay.page_number,
                bbox=entry["bbox"],
                length=entry["length"],
                orientation=None,
                point_count=2,
                candidate_kind=ck,
                derivation="leader_tip_neighborhood",
                confidence_basis="near_leader_tip;role_heuristic;not_the_leader_stroke",
                provenance={
                    "source_page": replay.page_number,
                    "source_raw_id": entry["raw_id"],
                    "source_geometry_id": None,
                    "derivation_type": "leader_tip_neighborhood",
                    "original_bbox": entry["bbox"],
                    "derived_bbox": entry["bbox"],
                    "original_point_count": None,
                    "derived_point_count": 2,
                    "tip": tip,
                    "retained_by_cap": entry.get("retained_by_cap"),
                    "classified_kind": entry.get("classified_kind"),
                },
            )
        )

    return {
        "leader_target_status": status,
        "leaders": EA._strip(trace.get("leaders") or [])[:3],
        "tip": tip,
        "tip_candidates": tip_cands[:12],
        "recoverable_tip_candidates": recoverable[:8],
        "counts": {
            "memberlike": memberlike,
            "nonmember": nonmember,
            "ambiguous": ambiguous,
            "missing_cap": missing_cap,
            "missing_class": missing_class,
        },
    }


def a_status(gold: Dict[str, Any], artifact_by_id: Dict[str, Any], loss: str) -> str:
    if gold.get("decision") == "associated":
        gid = gold.get("selected_geometry_id")
        if gid and gid in artifact_by_id:
            return "A_GOLD_PRESENT"
        return "A_GOLD_MISSING"
    if gold.get("error_bucket") == "schedule_table_not_member":
        return "A_SCHEDULE_NOT_MEMBER"
    if loss == "RETAINED_MEMBER":
        return "A_MEMBER_RETAINED"
    if loss == "CAP_DROPPED":
        return "A_CAP_DROPPED"
    if loss in {"RECLASSIFIED_DIMENSION", "RECLASSIFIED_LEADER"}:
        return "A_RECLASSIFIED"
    if loss == "RAW_MISSING":
        return "A_RAW_MISSING"
    if loss == "RAW_AMBIGUOUS":
        return "A_RAW_AMBIGUOUS"
    return "A_NO_USABLE_MEMBER"


def b_status(
    cands: List[Dict[str, Any]],
    loss: str,
    gold: Dict[str, Any],
    *,
    primary_recovered: bool,
) -> str:
    memberish = [
        c
        for c in cands
        if c["candidate_kind"]
        in {
            "LINE_MEMBER_CANDIDATE",
            "SEGMENT_MEMBER_CANDIDATE",
            "PLATE_MEMBER_CANDIDATE",
            "SMALL_TARGET_CANDIDATE",
            "LEADER_TARGET_CANDIDATE",
        }
    ]
    if gold.get("decision") == "associated":
        return "B_GOLD_PRESERVED"
    if gold.get("error_bucket") == "schedule_table_not_member":
        return "B_SCHEDULE_NOT_MEMBER"
    if primary_recovered:
        return "B_RECOVERED"
    if memberish:
        return "B_HAS_CANDIDATES"
    if loss == "RAW_MISSING":
        return "B_STILL_MISSING"
    return "B_NO_SAFE_CANDIDATE"


def audit_case(
    gold: Dict[str, Any],
    replay: EA.PageReplay,
    artifact_by_id: Dict[str, Dict[str, Any]],
    page_objs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    bb = gold["label_bbox"]
    lx = (bb[0] + bb[2]) / 2.0
    ly = (bb[1] + bb[3]) / 2.0

    hit, _ord = nearest_on_label(replay, lx, ly)
    hit_desc = describe_raw_hit(replay, hit) if hit else None
    loss = loss_class_from_hit(hit_desc, gold)

    cands: List[Dict[str, Any]] = []
    primary_recovered = False
    # Primary on-label recovery
    if hit_desc is not None:
        primary = build_candidate_from_raw(
            replay,
            hit_desc,
            derivation=(
                "cap_restore"
                if loss == "CAP_DROPPED"
                else (
                    "reclass_restore"
                    if loss in {"RECLASSIFIED_DIMENSION", "RECLASSIFIED_LEADER"}
                    else "on_label_retained"
                )
            ),
        )
        if primary:
            cands.append(primary)
            if loss in {"CAP_DROPPED", "RECLASSIFIED_DIMENSION", "RECLASSIFIED_LEADER"}:
                primary_recovered = True
            if loss == "RETAINED_MEMBER":
                primary_recovered = True

    # Neighborhood restore
    for c in nearby_raw_candidates(replay, bb):
        if c["candidate_id"] not in {x["candidate_id"] for x in cands}:
            cands.append(c)

    # Compound segmentation near label
    seg_cands = compound_segments_near_label(replay, bb)
    for c in seg_cands:
        if c["candidate_id"] not in {x["candidate_id"] for x in cands}:
            cands.append(c)

    leader = leader_target_audit(gold, replay, lx, ly)
    for c in leader.get("recoverable_tip_candidates") or []:
        if c["candidate_id"] not in {x["candidate_id"] for x in cands}:
            cands.append(c)

    # Associated gold: ensure representation preserved via artifact object
    gold_present = False
    if gold.get("selected_geometry_id"):
        obj = artifact_by_id.get(gold["selected_geometry_id"])
        gold_present = obj is not None and int(obj.get("page_number") or 0) == int(gold["page"])
        if gold_present and obj:
            # add provenance-linked candidate mirroring gold geom (not changing gold)
            cands.insert(
                0,
                make_candidate(
                    candidate_id=f"rnd_gold_{gold['selected_geometry_id']}",
                    source_raw_id=f"artifact:{gold['selected_geometry_id']}",
                    source_type="artifact_geometry",
                    page=int(gold["page"]),
                    bbox=list(obj["bbox"]),
                    length=float(obj.get("length") or 0),
                    orientation=obj.get("orientation"),
                    point_count=len(obj.get("points") or []),
                    candidate_kind="LINE_MEMBER_CANDIDATE",
                    derivation="associated_gold_artifact_mirror",
                    confidence_basis="human_gold_selected_geometry;representation_only",
                    provenance={
                        "source_page": int(gold["page"]),
                        "source_raw_id": f"artifact:{gold['selected_geometry_id']}",
                        "source_geometry_id": gold["selected_geometry_id"],
                        "derivation_type": "associated_gold_artifact_mirror",
                        "original_bbox": list(obj["bbox"]),
                        "derived_bbox": list(obj["bbox"]),
                        "original_point_count": len(obj.get("points") or []),
                        "derived_point_count": len(obj.get("points") or []),
                    },
                ),
            )

    member_cands = [
        c
        for c in cands
        if c["candidate_kind"]
        in {
            "LINE_MEMBER_CANDIDATE",
            "SEGMENT_MEMBER_CANDIDATE",
            "PLATE_MEMBER_CANDIDATE",
            "SMALL_TARGET_CANDIDATE",
            "LEADER_TARGET_CANDIDATE",
        }
    ]

    # Giant flags among local artifact objects
    giant_before = 0
    for o in page_objs:
        if G7._centroid_distance(bb, o.get("bbox") or [0, 0, 0, 0]) > 200:
            continue
        gq = G7.classify_bbox_quality(
            o["bbox"],
            length=o.get("length"),
            point_count=len(o.get("points") or []),
            page_width=replay.page_width,
            page_height=replay.page_height,
        )
        if gq in {"GIANT_BBOX", "COMPOUND_BBOX"}:
            giant_before += 1

    giant_after = sum(
        1
        for c in member_cands
        if max(G7._bbox_metrics(c["bbox"])["width"], G7._bbox_metrics(c["bbox"])["height"])
        >= GIANT_EXTENT_PT
    )

    a = a_status(gold, artifact_by_id, loss)
    # Leader tip recovery also counts as primary-quality recovery for leader cases.
    if gold.get("leader_required") and int(len(leader.get("recoverable_tip_candidates") or [])) > 0:
        if leader.get("leader_target_status") in {
            "TARGET_PRESENT_MEMBERLIKE",
            "TARGET_MISSING_AFTER_CAP",
            "TARGET_MISSING_AFTER_CLASSIFICATION",
        }:
            primary_recovered = primary_recovered or (
                leader.get("leader_target_status") == "TARGET_PRESENT_MEMBERLIKE"
                or len(leader.get("recoverable_tip_candidates") or []) > 0
            )
    b = b_status(member_cands, loss, gold, primary_recovered=primary_recovered)
    change = "unchanged"
    if a.startswith("A_") and b.startswith("B_"):
        if b == "B_RECOVERED" and a not in {"A_MEMBER_RETAINED", "A_GOLD_PRESENT"}:
            change = "improved"
        elif b == "B_HAS_CANDIDATES" and a not in {"A_MEMBER_RETAINED", "A_GOLD_PRESENT"}:
            change = "improved_neighborhood_only"
        elif b in {"B_STILL_MISSING", "B_NO_SAFE_CANDIDATE"} and a in {
            "A_MEMBER_RETAINED",
            "A_GOLD_PRESENT",
        }:
            change = "regressed"
        elif b == "B_GOLD_PRESERVED":
            change = "preserved"

    # False-candidate signals (heuristic examples for report)
    false_examples = [
        c
        for c in member_cands
        if c["derivation"] == "vertex_split"
        and float(c["length"] or 0) > 350
    ][:3]

    return {
        "token_id": gold["token_id"],
        "page": int(gold["page"]),
        "label_text": gold.get("text"),
        "label_class": G7.label_class(gold.get("text") or ""),
        "label_bbox": list(bb),
        "gold_decision": gold.get("decision"),
        "gold_geometry_id": gold.get("selected_geometry_id"),
        "visible_member_on_drawing": bool(gold.get("visible_member_on_drawing")),
        "leader_required": bool(gold.get("leader_required")),
        "error_bucket": gold.get("error_bucket"),
        "loss_class": loss,
        "raw_trace": None if hit_desc is None else hit_desc["token_trace"],
        "A_status": a,
        "B_status": b,
        "B_candidate_count": len(member_cands),
        "B_candidates": member_cands[:15],
        "segment_candidate_count": sum(
            1 for c in member_cands if c["candidate_kind"] == "SEGMENT_MEMBER_CANDIDATE"
        ),
        "leader_status": leader.get("leader_target_status"),
        "leader_audit": {
            k: leader.get(k)
            for k in (
                "leader_target_status",
                "tip",
                "counts",
                "tip_candidates",
            )
        },
        "leader_recoverable_n": len(leader.get("recoverable_tip_candidates") or []),
        "giant_nearby_before": giant_before,
        "giant_member_candidates_after": giant_after,
        "gold_geometry_present": gold_present,
        "representation_change": change,
        "false_candidate_examples": false_examples,
        "notes": (
            f"loss={loss}; members={len(member_cands)}; "
            f"leader={leader.get('leader_target_status')}; change={change}"
        ),
    }


# ---------------------------------------------------------------------------
# metrics / gate / report
# ---------------------------------------------------------------------------
def decide_gate(summary: Dict[str, Any]) -> str:
    m = summary["metrics"]
    if m["associated_gold_preserved"] < 8:
        return "REPRESENTATION_STILL_NOT_READY"
    if m["rnd_recovered_among_visible_miss"] < 12:
        return "REPRESENTATION_STILL_NOT_READY"
    if m["short_stroke_recovered"] < 5:
        return "REPRESENTATION_STILL_NOT_READY"
    leader = summary["leader_metrics"]
    if leader["leader_required_n"] >= 10:
        if leader["target_memberlike_or_recoverable"] < max(6, leader["leader_required_n"] // 3):
            return "REPRESENTATION_STILL_NOT_READY"
    # Giant control: R&D must not inflate giant member-candidate count.
    if m["giant_member_candidates_after_total"] > max(2, m["giant_nearby_before_total"]):
        return "REPRESENTATION_STILL_NOT_READY"
    if not summary.get("provenance_complete"):
        return "REPRESENTATION_STILL_NOT_READY"
    if (
        m["rnd_recovered_among_visible_miss"] >= 20
        and m["short_stroke_recovered"] >= 8
        and leader["target_memberlike_or_recoverable"] >= 8
        and m["associated_gold_preserved"] == 8
        and m["giant_member_candidates_after_total"] <= m["giant_nearby_before_total"]
    ):
        return "REPRESENTATION_READY_FOR_ASSOCIATION"
    return "REPRESENTATION_STILL_NOT_READY"


def write_report(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    m = summary["metrics"]
    gate = summary["g8_gate"]
    lines: List[str] = []
    lines.append("# Geometry Representation Repair (G8)\n")
    lines.append(
        "R&D-only candidate population experiment. No association, no production "
        "extraction/CAP/retrieval changes, gold untouched.\n"
    )
    lines.append(f"**Document:** `{DOC_ID}`  ")
    lines.append(f"**Gold SHA:** `{summary['gold_sha256']}`  ")
    lines.append(f"**Cases:** {summary['n_cases']}  ")
    lines.append(f"**G8_GATE = `{gate}`**\n")

    lines.append("## 1. Question\n")
    lines.append(
        "Can we recover member-level geometry *candidates* from raw PyMuPDF drawings "
        "without changing production extraction or association?\n"
    )

    lines.append("## 2. Global metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    for key, label in [
        ("relevant_visible_n", "Raw visible-member cases"),
        ("raw_geometry_present_n", "Raw geometry present"),
        ("cap_retained_on_label_n", "CAP retained (on-label)"),
        ("current_member_kind_retained_n", "Current member-kind retained"),
        ("rnd_candidate_cases_n", "Cases with ≥1 R&D member candidate"),
        ("rnd_recovered_among_visible_miss", "Visible-miss recovered (R&D)"),
        ("short_stroke_recovered", "Short-stroke recovered"),
        ("segment_candidates_total", "Compound segmentation candidates"),
        ("associated_gold_preserved", "Associated gold preserved"),
        ("giant_nearby_before_total", "Giant nearby (A)"),
        ("giant_member_candidates_after_total", "Giant among B member cands"),
    ]:
        lines.append(f"| {label} | {m[key]} |")
    lines.append("")

    lines.append("## 3. Per-page breakdown\n")
    for page, pm in summary["page_metrics"].items():
        lines.append(f"### p{page}\n")
        lines.append("| Metric | Value |")
        lines.append("|---|---:|")
        for k, v in pm.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    lines.append("## 4. Loss-class histogram\n")
    for k, v in summary["loss_class_counts"].items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    lines.append("## 5. Short-stroke findings\n")
    lines.append("| Class | n | CAP_DROPPED | RECLASS_* | RETAINED_MEMBER | B recovered |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cls, st in summary["class_audit"].items():
        lines.append(
            f"| {cls} | {st['n']} | {st['cap_dropped']} | {st['reclassified']} | "
            f"{st['retained_member']} | {st['b_recovered']} |"
        )
    lines.append("")

    lines.append("## 6. Compound / segmentation\n")
    cs = summary["segmentation"]
    lines.append(
        f"- Compound paths considered: **{cs['compound_paths_n']}**\n"
        f"- Derived segments: **{cs['derived_segments_n']}**\n"
        f"- Segments near gold labels: **{cs['segments_near_labels_n']}**\n"
        f"- Useful member-scale segments (extent≤{SEGMENT_MAX_EXTENT_PT}): "
        f"**{cs['useful_member_scale_n']}**\n"
        f"- Obvious false/large segments: **{cs['false_or_large_n']}**\n"
    )
    lines.append(
        "Segmentation is vertex-split only, preserves `raw_id#segN` provenance, "
        "and never assigns beam/member identity.\n"
    )

    lines.append("## 7. Leader-target findings\n")
    lm = summary["leader_metrics"]
    lines.append("| Status | Count |")
    lines.append("|---|---:|")
    for k, v in lm["status_counts"].items():
        lines.append(f"| {k} | {v} |")
    lines.append(
        f"\nLeader-required: {lm['leader_required_n']}. "
        f"Memberlike or recoverable: {lm['target_memberlike_or_recoverable']}.\n"
    )

    lines.append("## 8. Top before/after examples\n")
    lines.append("| token | label | gold | A | B | B_n | change |")
    lines.append("|---|---|---|---|---|---:|---|")
    examples = summary.get("top_examples") or []
    for r in examples:
        lines.append(
            f"| `{r['token_id']}` | {r['label_text']} | {r['gold_decision']} | "
            f"{r['A_status']} | {r['B_status']} | {r['B_candidate_count']} | "
            f"{r['representation_change']} |"
        )
    lines.append("")

    lines.append("## 9. False / ambiguous candidate examples\n")
    for ex in summary.get("false_candidate_examples") or []:
        lines.append(
            f"- `{ex.get('token_id')}`: {ex.get('candidate_id')} "
            f"kind={ex.get('candidate_kind')} len={ex.get('length')} "
            f"({ex.get('note')})"
        )
    if not summary.get("false_candidate_examples"):
        lines.append("- (none flagged beyond large vertex-split segments)")
    lines.append("")
    for ex in summary.get("ambiguous_examples") or []:
        lines.append(f"- `{ex['token_id']}`: {ex['notes']}")
    lines.append("")

    lines.append("## 10. Verdict\n")
    lines.append(f"**G8_GATE = `{gate}`**\n")
    if gate == "REPRESENTATION_READY_FOR_ASSOCIATION":
        lines.append(
            "R&D candidate population is sufficient to begin an isolated association "
            "experiment. Production extraction remains unchanged; association is not "
            "implemented here.\n"
        )
    else:
        lines.append(
            "Representation is still not ready for association. Population recovery, "
            "leader-target coverage, and/or giant control remain insufficient under the "
            "stated gate criteria.\n"
        )

    lines.append("## 11. Next phase recommendation\n")
    if gate == "REPRESENTATION_READY_FOR_ASSOCIATION":
        lines.append(
            "Next: isolated association experiment over R&D candidates only "
            "(shadow ranking, no production wiring), stratified by loss class and leader.\n"
        )
    else:
        lines.append(
            "Next: deepen short-stroke CAP restore + leader-tip target recovery with "
            "stricter non-member rejection; keep segmentation read-only until false "
            "candidates are controlled.\n"
        )

    lines.append("## 12. Safety\n")
    lines.append(
        f"- Gold SHA unchanged: `{summary['gold_sha256']}`\n"
        f"- Production extractor / retrieval / CAP untouched by this script\n"
        f"- Associated gold 8/8 preserved: {m['associated_gold_preserved'] == 8}\n"
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_review_html(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>G8 Representation Repair</title>",
        "<style>body{font-family:ui-sans-serif,system-ui;margin:24px}table{border-collapse:collapse;"
        "width:100%;font-size:12px}th,td{border:1px solid #ccc;padding:4px 6px}"
        "th{background:#f4f4f4}.improved{background:#e8ffe8}.still{background:#fff4e8}</style></head><body>",
        f"<h1>G8 Representation Repair</h1><p><b>G8_GATE={html.escape(summary['g8_gate'])}</b></p>",
        "<table><tr><th>token</th><th>page</th><th>text</th><th>loss</th><th>A</th><th>B</th>"
        "<th>B_n</th><th>leader</th><th>change</th></tr>",
    ]
    for r in rows:
        cls = "improved" if r["representation_change"] == "improved" else "still"
        parts.append(
            f"<tr class='{cls}'><td>{html.escape(r['token_id'])}</td><td>{r['page']}</td>"
            f"<td>{html.escape(str(r.get('label_text') or ''))}</td>"
            f"<td>{html.escape(r['loss_class'])}</td>"
            f"<td>{html.escape(r['A_status'])}</td>"
            f"<td>{html.escape(r['B_status'])}</td>"
            f"<td>{r['B_candidate_count']}</td>"
            f"<td>{html.escape(str(r.get('leader_status') or ''))}</td>"
            f"<td>{html.escape(r['representation_change'])}</td></tr>"
        )
    parts.append("</table></body></html>")
    REVIEW_HTML.write_text("\n".join(parts), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renders", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    gold_sha = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if gold_sha != EXPECTED_GOLD_SHA:
        raise SystemExit(f"Gold SHA mismatch: {gold_sha}")

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
    for page in PAGES:
        replays[page] = EA.PageReplay(pdf[page - 1], page, document, page_scales)

    # Page-level compound inventory
    seg_stats = {
        "compound_paths_n": 0,
        "derived_segments_n": 0,
        "segments_near_labels_n": 0,
        "useful_member_scale_n": 0,
        "false_or_large_n": 0,
    }
    label_bbs = {int(g["page"]): [] for g in gold_rows}
    for g in gold_rows:
        label_bbs[int(g["page"])].append(g["label_bbox"])

    for page, replay in replays.items():
        for idx, drawing in enumerate(replay.raw):
            bbox = drawing_bbox(drawing)
            if not bbox:
                continue
            pts = drawing_points(drawing)
            length = EA._path_length(drawing)
            giant = classify_giant(
                bbox,
                length=length,
                point_count=len(pts),
                page_w=replay.page_width,
                page_h=replay.page_height,
            )
            if giant != "COMPOUND_POLYLINE":
                continue
            seg_stats["compound_paths_n"] += 1
            raw_id = raw_drawing_index(page, drawing, idx)
            segs = segment_polyline(
                raw_id,
                drawing,
                page=page,
                page_w=replay.page_width,
                page_h=replay.page_height,
            )
            seg_stats["derived_segments_n"] += len(segs)
            for s in segs:
                extent = max(
                    G7._bbox_metrics(s["bbox"])["width"],
                    G7._bbox_metrics(s["bbox"])["height"],
                )
                if extent <= SEGMENT_MAX_EXTENT_PT:
                    seg_stats["useful_member_scale_n"] += 1
                else:
                    seg_stats["false_or_large_n"] += 1
                near = any(
                    G7._centroid_distance(bb, s["bbox"]) < 200 for bb in label_bbs.get(page, [])
                )
                if near:
                    seg_stats["segments_near_labels_n"] += 1

    rows: List[Dict[str, Any]] = []
    for gold in gold_rows:
        page = int(gold["page"])
        page_objs = [o for o in objects if int(o.get("page_number") or 0) == page]
        row = audit_case(gold, replays[page], artifact_by_id, page_objs)
        rows.append(row)

    # --- metrics ---
    visible = [
        r
        for r in rows
        if r.get("visible_member_on_drawing") and r.get("error_bucket") != "schedule_table_not_member"
    ]
    visible_miss = [
        r
        for r in rows
        if r["gold_decision"] == "no_valid_member" and r.get("visible_member_on_drawing")
    ]
    assoc = [r for r in rows if r["gold_decision"] == "associated"]

    loss_counts = Counter(r["loss_class"] for r in rows)
    raw_present = sum(
        1
        for r in visible
        if r["loss_class"]
        in {
            "CAP_DROPPED",
            "RECLASSIFIED_DIMENSION",
            "RECLASSIFIED_LEADER",
            "OTHER_FILTER",
            "RETAINED_MEMBER",
            "RAW_PRESENT",
        }
        or r.get("raw_trace")
    )
    # refine raw present
    raw_present = sum(1 for r in visible if r["loss_class"] not in {"RAW_MISSING"})
    cap_retained = sum(
        1
        for r in visible
        if r.get("raw_trace") and r["raw_trace"].get("retained_by_cap")
    )
    member_retained = sum(1 for r in visible if r["loss_class"] == "RETAINED_MEMBER")
    rnd_cases = sum(1 for r in rows if r["B_candidate_count"] > 0)
    recovered_miss = sum(1 for r in visible_miss if r["B_status"] == "B_RECOVERED")
    neighborhood_only_miss = sum(
        1 for r in visible_miss if r["B_status"] == "B_HAS_CANDIDATES"
    )
    short_rows = [
        r
        for r in rows
        if r.get("raw_trace")
        and float(r["raw_trace"].get("raw_length") or 0) <= SHORT_MAX_PT
        and r["loss_class"] != "RAW_MISSING"
    ]
    short_recovered = sum(
        1
        for r in short_rows
        if r["B_candidate_count"] > 0
        and r["loss_class"] in {"CAP_DROPPED", "RECLASSIFIED_DIMENSION", "RECLASSIFIED_LEADER"}
    )

    leader_req = [r for r in rows if r.get("leader_required")]
    leader_status_counts = Counter(r.get("leader_status") for r in leader_req)
    leader_recoverable = sum(
        1
        for r in leader_req
        if r.get("leader_status") == "TARGET_PRESENT_MEMBERLIKE"
        or int(r.get("leader_recoverable_n") or 0) > 0
    )

    class_audit: Dict[str, Dict[str, int]] = {}
    for r in rows:
        cls = r["label_class"]
        slot = class_audit.setdefault(
            cls,
            {
                "n": 0,
                "cap_dropped": 0,
                "reclassified": 0,
                "retained_member": 0,
                "b_recovered": 0,
            },
        )
        slot["n"] += 1
        if r["loss_class"] == "CAP_DROPPED":
            slot["cap_dropped"] += 1
        if r["loss_class"] in {"RECLASSIFIED_DIMENSION", "RECLASSIFIED_LEADER"}:
            slot["reclassified"] += 1
        if r["loss_class"] == "RETAINED_MEMBER":
            slot["retained_member"] += 1
        if r["representation_change"] == "improved" or r["B_status"] in {
            "B_RECOVERED",
            "B_HAS_CANDIDATES",
        }:
            if r["gold_decision"] != "associated":
                slot["b_recovered"] += 1

    page_metrics: Dict[str, Dict[str, int]] = {}
    for page in PAGES:
        pr = [r for r in rows if r["page"] == page]
        pv = [
            r
            for r in pr
            if r.get("visible_member_on_drawing")
            and r.get("error_bucket") != "schedule_table_not_member"
        ]
        page_metrics[str(page)] = {
            "n": len(pr),
            "visible": len(pv),
            "raw_present": sum(1 for r in pv if r["loss_class"] != "RAW_MISSING"),
            "member_retained": sum(1 for r in pv if r["loss_class"] == "RETAINED_MEMBER"),
            "b_candidates_cases": sum(1 for r in pr if r["B_candidate_count"] > 0),
            "improved": sum(1 for r in pr if r["representation_change"] == "improved"),
            "leader_required": sum(1 for r in pr if r.get("leader_required")),
            "leader_recoverable": sum(
                1
                for r in pr
                if r.get("leader_required")
                and (
                    r.get("leader_status") == "TARGET_PRESENT_MEMBERLIKE"
                    or int(r.get("leader_recoverable_n") or 0) > 0
                )
            ),
        }

    # Provenance completeness
    provenance_complete = True
    for r in rows:
        for c in r.get("B_candidates") or []:
            prov = c.get("provenance") or {}
            for key in (
                "source_page",
                "source_raw_id",
                "derivation_type",
                "original_bbox",
                "derived_bbox",
            ):
                if key not in prov or prov[key] is None:
                    provenance_complete = False

    # Top examples: mix of improved + preserved + still missing
    improved = [r for r in rows if r["representation_change"] == "improved"]
    preserved = [r for r in assoc]
    still = [r for r in visible_miss if r["B_status"] in {"B_STILL_MISSING", "B_NO_SAFE_CANDIDATE"}]
    top = []
    for bucket in (improved[:4], preserved[:3], still[:3]):
        for r in bucket:
            top.append(
                {
                    "token_id": r["token_id"],
                    "label_text": r["label_text"],
                    "gold_decision": r["gold_decision"],
                    "A_status": r["A_status"],
                    "B_status": r["B_status"],
                    "B_candidate_count": r["B_candidate_count"],
                    "representation_change": r["representation_change"],
                }
            )
    top = top[:10]

    false_examples = []
    for r in rows:
        for c in r.get("false_candidate_examples") or []:
            false_examples.append(
                {
                    "token_id": r["token_id"],
                    "candidate_id": c.get("candidate_id"),
                    "candidate_kind": c.get("candidate_kind"),
                    "length": c.get("length"),
                    "note": "large vertex-split segment",
                }
            )
            if len(false_examples) >= 8:
                break
        if len(false_examples) >= 8:
            break

    ambiguous_examples = [
        {
            "token_id": r["token_id"],
            "notes": r["notes"],
        }
        for r in rows
        if r["loss_class"] == "RAW_AMBIGUOUS" or r.get("leader_status") == "TARGET_PRESENT_AMBIGUOUS"
    ][:8]

    metrics = {
        "relevant_visible_n": len(visible),
        "raw_geometry_present_n": raw_present,
        "cap_retained_on_label_n": cap_retained,
        "current_member_kind_retained_n": member_retained,
        "rnd_candidate_cases_n": rnd_cases,
        "rnd_recovered_among_visible_miss": recovered_miss,
        "rnd_neighborhood_only_among_visible_miss": neighborhood_only_miss,
        "short_stroke_raw_n": len(short_rows),
        "short_stroke_recovered": short_recovered,
        "segment_candidates_total": sum(r["segment_candidate_count"] for r in rows),
        "associated_gold_preserved": sum(1 for r in assoc if r.get("gold_geometry_present")),
        "giant_nearby_before_total": sum(r.get("giant_nearby_before") or 0 for r in rows),
        "giant_member_candidates_after_total": sum(
            r.get("giant_member_candidates_after") or 0 for r in rows
        ),
    }

    summary: Dict[str, Any] = {
        "document_id": DOC_ID,
        "pages": list(PAGES),
        "n_cases": len(rows),
        "gold_sha256": gold_sha,
        "metrics": metrics,
        "page_metrics": page_metrics,
        "loss_class_counts": dict(loss_counts),
        "class_audit": class_audit,
        "segmentation": seg_stats,
        "leader_metrics": {
            "leader_required_n": len(leader_req),
            "status_counts": dict(leader_status_counts),
            "target_memberlike_or_recoverable": leader_recoverable,
        },
        "provenance_complete": provenance_complete,
        "top_examples": top,
        "false_candidate_examples": false_examples,
        "ambiguous_examples": ambiguous_examples,
        "ab_status_counts": {
            "A": dict(Counter(r["A_status"] for r in rows)),
            "B": dict(Counter(r["B_status"] for r in rows)),
            "change": dict(Counter(r["representation_change"] for r in rows)),
        },
    }
    summary["g8_gate"] = decide_gate(summary)

    OUT.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(EA._strip(r), sort_keys=True) + "\n")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(summary, rows)
    write_review_html(rows, summary)

    if args.renders:
        RENDER_DIR.mkdir(parents=True, exist_ok=True)
        for r in rows:
            page = pdf[r["page"] - 1]
            bb = r["label_bbox"]
            page.draw_rect(fitz.Rect(bb), color=(0.1, 0.35, 0.92), width=1.6)
            for c in (r.get("B_candidates") or [])[:6]:
                color = (0.05, 0.55, 0.15)
                if c["candidate_kind"] == "SEGMENT_MEMBER_CANDIDATE":
                    color = (0.7, 0.35, 0.05)
                if c["candidate_kind"] == "LEADER_TARGET_CANDIDATE":
                    color = (0.55, 0.15, 0.75)
                page.draw_rect(fitz.Rect(c["bbox"]), color=color, width=1.2)
            cx = (bb[0] + bb[2]) / 2.0
            cy = (bb[1] + bb[3]) / 2.0
            clip = fitz.Rect(cx - 160, cy - 160, cx + 160, cy + 160)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=clip, alpha=False)
            pix.save(str(RENDER_DIR / f"{r['token_id']}.png"))

    after = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if after != EXPECTED_GOLD_SHA:
        raise SystemExit("Gold SHA changed during G8 — abort")

    print(f"G8_GATE = {summary['g8_gate']}")
    print(
        f"cases={len(rows)} recovered_miss={metrics['rnd_recovered_among_visible_miss']}/"
        f"{len(visible_miss)} short_recovered={metrics['short_stroke_recovered']} "
        f"leader_rec={leader_recoverable}/{len(leader_req)} "
        f"gold_preserved={metrics['associated_gold_preserved']}/8"
    )
    print(f"wrote {RESULTS_PATH}")
    print(f"wrote {SUMMARY_PATH}")
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
