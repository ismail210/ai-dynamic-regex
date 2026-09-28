#!/usr/bin/env python3
"""E1 — Dense-page geometry CAP cost experiment (R&D, measurement only).

Measures how much visible-member target geometry is lost specifically because of
the dense-page path cap. The ONLY experimental variable is the cap value.

Production helpers are reused unchanged. Classification, filtering, retrieval,
and human gold are not modified.

Usage (from backend/):
    python scripts/rd_geometry_integration/cap_cost_experiment.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from services.engineering import geometry_extractor as GX  # noqa: E402  read-only
from services.engineering.drawing_scale import (  # noqa: E402
    association_radius_pdf_points,
    detect_page_scales,
    resolve_page_scale,
)
from services.engineering.geometry_normalizer import merge_collinear_fragments  # noqa: E402
from services.engineering.models import GeometryKind  # noqa: E402

DOC_ID = "doc_0d910a43b4a021e3"
ARTIFACT = ROOT / "training" / "engineering_artifacts" / DOC_ID / "multimodal"
PDF_PATH = ROOT / "uploads" / "Burrville ES - ST.pdf"
OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
GOLD_PATH = OUT / "review_kit" / "gold_outcomes.jsonl"
AUDIT_PATH = OUT / "extraction_audit.jsonl"

PAGES = (8, 18, 24)
CAP_VARIANTS: List[Tuple[str, Optional[int]]] = [
    ("CAP_450", 450),
    ("CAP_900", 900),
    ("CAP_1800", 1800),
    ("CAP_NO_LIMIT", None),
]

# Member-eligible kinds for "available to candidate generation" (extraction stage).
# Leaders / dimensions / symbols are intentionally excluded — that is classification,
# not a further filter after the cap.
_MEMBER_KINDS = {"line", "polyline", "rectangle", "arc"}
_CALLOUT_KINDS = {"leader", "dimension", "symbol"}


# ---------------------------------------------------------------------------
# geometry helpers (local; production code untouched)
# ---------------------------------------------------------------------------
def _segments(drawing: Dict[str, Any]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    out: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for it in drawing.get("items") or []:
        if not isinstance(it, (list, tuple)) or not it:
            continue
        kind = str(it[0]).lower()
        if kind == "re" and len(it) > 1:
            r = it[1]
            corners = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
            for i in range(4):
                out.append((corners[i], corners[(i + 1) % 4]))
            continue
        pts: List[Tuple[float, float]] = []
        for idx in range(1, 5):
            if len(it) > idx and it[idx] is not None:
                pt = it[idx]
                if hasattr(pt, "x"):
                    pts.append((float(pt.x), float(pt.y)))
                elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    pts.append((float(pt[0]), float(pt[1])))
        for i in range(len(pts) - 1):
            out.append((pts[i], pts[i + 1]))
    return out


def _path_length(drawing: Dict[str, Any]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in _segments(drawing))


def _point_to_segment(
    px: float, py: float, a: Sequence[float], b: Sequence[float]
) -> Tuple[float, float]:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return math.hypot(px - ax, py - ay), 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / denom
    tc = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + tc * dx), py - (ay + tc * dy)), t


def _nearest_on_path(px: float, py: float, drawing: Dict[str, Any]) -> Tuple[float, float]:
    best = (1e12, 0.0)
    for a, b in _segments(drawing):
        d, t = _point_to_segment(px, py, a, b)
        if d < best[0]:
            best = (d, t)
    return best


def _drawing_fingerprint(drawing: Dict[str, Any]) -> Tuple[Any, ...]:
    """Stable identity for a raw PyMuPDF drawing (independent of ordinal/cap)."""
    rect = drawing.get("rect")
    if rect is None:
        return ("none",)
    return (
        round(float(rect.x0), 2),
        round(float(rect.y0), 2),
        round(float(rect.x1), 2),
        round(float(rect.y1), 2),
        round(_path_length(drawing), 2),
        len(drawing.get("items") or []),
    )


def _bbox_fingerprint(bbox: Sequence[float], length: Optional[float] = None) -> Tuple[Any, ...]:
    bb = [round(float(v), 2) for v in bbox]
    if length is None:
        return tuple(bb)
    return (*bb, round(float(length), 2))


# ---------------------------------------------------------------------------
# Cap ranking (mirrors production structural_first exactly)
# ---------------------------------------------------------------------------
def _structural_first_order(
    drawings: List[dict], *, page_width: float, page_height: float
) -> Tuple[List[dict], Dict[int, int], Dict[int, str]]:
    """Return (ordered pool, raw_id -> 1-based retention rank, raw_id -> exclusion).

    Rank is the position in the list that ``_select_under_dense_cap`` would keep
    from: long strokes by score, then short strokes by score. Tiny / page-frame
    drawings are excluded from the ranked pool (same as production).
    """
    exclusion: Dict[int, str] = {}
    pool: List[dict] = []
    for item in drawings:
        if GX._is_tiny_noise_drawing(item):
            exclusion[id(item)] = "dense_cap_excluded_tiny_noise"
            continue
        if GX._is_page_frame_drawing(item, page_width, page_height):
            exclusion[id(item)] = "dense_cap_excluded_page_frame"
            continue
        pool.append(item)

    scored = sorted(pool, key=GX._structural_keep_score, reverse=True)
    long_strokes = [
        item for item in scored if max(GX._drawing_wh(item)) >= GX._STRUCTURAL_MIN_SPAN_PT
    ]
    short_strokes = [
        item for item in scored if max(GX._drawing_wh(item)) < GX._STRUCTURAL_MIN_SPAN_PT
    ]
    ordered = long_strokes + short_strokes
    rank = {id(item): i + 1 for i, item in enumerate(ordered)}
    return ordered, rank, exclusion


def _select_cap(
    drawings: List[dict],
    *,
    page_width: float,
    page_height: float,
    cap: Optional[int],
) -> List[dict]:
    if cap is None:
        # NO_LIMIT: still apply the structural_first *exclusions* (tiny / page-frame)
        # so we isolate the numeric cap, not the tiny-noise prefilter.
        ordered, _rank, _excl = _structural_first_order(
            drawings, page_width=page_width, page_height=page_height
        )
        return list(ordered)
    return GX._select_under_dense_cap(
        drawings,
        page_width=page_width,
        page_height=page_height,
        cap=cap,
        strategy="structural_first",
    )


# ---------------------------------------------------------------------------
# Classify kept drawings with production helpers (cap is already applied)
# ---------------------------------------------------------------------------
def _classify_kept(
    kept: List[dict],
    *,
    page_number: int,
    document: Dict[str, Any],
    page_scales,
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    resolved = resolve_page_scale(document, page_number, page_scales=page_scales)
    page_scale = (
        page_scales.get(page_number) if resolved.get("scale_reason") == "page_scale" else None
    )
    radius = association_radius_pdf_points(page_scale) * (48.0 / 160.0)
    nearby_radius = max(24.0, min(96.0, radius))
    line_grid: Dict[Tuple[int, int], List[dict]] = {}
    for line in document.get("lines") or []:
        if int(line.get("page_number") or 0) != page_number:
            continue
        center = line.get("center") or [0, 0]
        key = (
            int(float(center[0]) // nearby_radius),
            int(float(center[1]) // nearby_radius),
        )
        line_grid.setdefault(key, []).append(line)

    objects: List[Dict[str, Any]] = []
    by_raw: Dict[int, Dict[str, Any]] = {}
    for drawing in kept:
        items = list(drawing.get("items") or [])
        rect = drawing.get("rect")
        points: List[List[float]] = []
        item_dicts: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, (list, tuple)) or not it:
                continue
            kind = str(it[0]).lower()
            entry: Dict[str, Any] = {"type": kind}
            if kind == "re" and len(it) > 1:
                r = it[1]
                entry["rect"] = r
                points.extend(
                    [
                        [float(r.x0), float(r.y0)],
                        [float(r.x1), float(r.y0)],
                        [float(r.x1), float(r.y1)],
                        [float(r.x0), float(r.y1)],
                    ]
                )
            else:
                for idx, key in enumerate(("p1", "p2", "p3", "p4"), start=1):
                    if len(it) > idx and it[idx] is not None:
                        pt = it[idx]
                        if hasattr(pt, "x"):
                            entry[key] = [float(pt.x), float(pt.y)]
                            points.append([float(pt.x), float(pt.y)])
                        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            entry[key] = [float(pt[0]), float(pt[1])]
                            points.append([float(pt[0]), float(pt[1])])
            item_dicts.append(entry)

        if rect is not None:
            bbox = GX._round([rect.x0, rect.y0, rect.x1, rect.y1])
        elif points:
            bbox = GX._bbox_from_points(points)
        else:
            continue

        kind = GX._classify_path(item_dicts, rect)
        before = kind.value
        length = (
            GX._length_of_segments(points)
            if len(points) >= 2
            else round(math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]), 3)
        )
        center = [round((bbox[0] + bbox[2]) / 2.0, 2), round((bbox[1] + bbox[3]) / 2.0, 2)]
        nearby = GX._nearby_text(
            center, page_number, document, radius=nearby_radius, line_grid=line_grid
        )
        reclass = None
        if GX._looks_like_leader(kind, length, bbox):
            kind = GeometryKind.LEADER
            reclass = "looks_like_leader"
        elif GX._looks_like_dimension(kind, length, nearby):
            kind = GeometryKind.DIMENSION
            reclass = "looks_like_dimension"
        width = round(abs(bbox[2] - bbox[0]), 3)
        height = round(abs(bbox[3] - bbox[1]), 3)
        area = round(width * height, 3)
        if kind in {GeometryKind.RECTANGLE, GeometryKind.CIRCLE} and area < 400:
            kind = GeometryKind.SYMBOL
            reclass = "small_closed_shape_to_symbol"

        obj = {
            "geometry_id": GX._gid(page_number, len(objects), bbox, kind.value),
            "kind": kind.value,
            "classified_kind_before_reclass": before,
            "reclassified_by": reclass,
            "bbox": bbox,
            "length": length,
            "center": center,
            "page_number": page_number,
            "_raw_id": id(drawing),
            "_fp": _drawing_fingerprint(drawing),
        }
        objects.append(obj)
        by_raw[id(drawing)] = obj

    merged, _stats = merge_collinear_fragments(
        [{k: v for k, v in o.items() if not k.startswith("_")} for o in objects],
        scale=page_scale,
    )
    # Attach merge survival: raw object survives filtering if it has a post-merge id
    # (either itself or as a merge contributor). Track by bbox fingerprint.
    merged_fps = {_bbox_fingerprint(o["bbox"], o.get("length")) for o in merged}
    consumed: Dict[str, str] = {}
    for o in merged:
        for src in o.get("merged_from") or []:
            consumed[str(src)] = o["geometry_id"]
    for o in objects:
        gid = o["geometry_id"]
        final = consumed.get(gid, gid)
        o["final_geometry_id"] = final
        o["survives_merge"] = True  # every classified object enters merge
        # If merged into another id, still "survives filtering"
        o["post_merge_geometry_id"] = final

    return objects, by_raw


# ---------------------------------------------------------------------------
# Target identity
# ---------------------------------------------------------------------------
def _find_nearest_label_stroke(
    raw: List[dict], lx: float, ly: float, *, perp_max: float = 14.0, min_len: float = 15.0
) -> Optional[dict]:
    best: Optional[Tuple[float, dict]] = None
    for drawing in raw:
        rect = drawing.get("rect")
        if rect is None:
            continue
        if not (rect.x0 - 80 <= lx <= rect.x1 + 80 and rect.y0 - 80 <= ly <= rect.y1 + 80):
            continue
        dist, t = _nearest_on_path(lx, ly, drawing)
        if dist > perp_max or not (-0.02 <= t <= 1.02):
            continue
        if _path_length(drawing) < min_len:
            continue
        if best is None or dist < best[0]:
            best = (dist, drawing)
    return None if best is None else best[1]


def _match_audit_near(
    raw: List[dict], audit_hit: Dict[str, Any], lx: float, ly: float
) -> Optional[dict]:
    """Re-identify the audit's near_label_raw stroke among raw drawings."""
    target_len = float(audit_hit.get("path_length") or 0.0)
    target_w = float(audit_hit.get("bbox_w") or 0.0)
    target_h = float(audit_hit.get("bbox_h") or 0.0)
    target_perp = float(audit_hit.get("perp_distance") or 0.0)
    best: Optional[Tuple[float, dict]] = None
    for drawing in raw:
        rect = drawing.get("rect")
        if rect is None:
            continue
        length = _path_length(drawing)
        w, h = abs(float(rect.width)), abs(float(rect.height))
        if abs(length - target_len) > 0.5:
            continue
        if abs(w - target_w) > 0.5 or abs(h - target_h) > 0.5:
            continue
        dist, t = _nearest_on_path(lx, ly, drawing)
        if abs(dist - target_perp) > 0.5:
            continue
        score = abs(dist - target_perp) + abs(length - target_len)
        if best is None or score < best[0]:
            best = (score, drawing)
    return None if best is None else best[1]


def _match_audit_tip_target(
    raw: List[dict], tip: Sequence[float], audit_hit: Dict[str, Any]
) -> Optional[dict]:
    target_len = float(audit_hit.get("path_length") or 0.0)
    target_w = float(audit_hit.get("bbox_w") or 0.0)
    target_h = float(audit_hit.get("bbox_h") or 0.0)
    tip_d = float(audit_hit.get("tip_distance") or 0.0)
    tx, ty = float(tip[0]), float(tip[1])
    best: Optional[Tuple[float, dict]] = None
    for drawing in raw:
        rect = drawing.get("rect")
        if rect is None:
            continue
        length = _path_length(drawing)
        w, h = abs(float(rect.width)), abs(float(rect.height))
        if abs(length - target_len) > 0.5:
            continue
        if abs(w - target_w) > 0.5 or abs(h - target_h) > 0.5:
            continue
        dist, _t = _nearest_on_path(tx, ty, drawing)
        if abs(dist - tip_d) > 0.5:
            continue
        score = abs(dist - tip_d) + abs(length - target_len)
        if best is None or score < best[0]:
            best = (score, drawing)
    return None if best is None else best[1]


def _pick_audit_primary_target(
    raw: List[dict], audit_row: Dict[str, Any], gold: Dict[str, Any]
) -> Tuple[Optional[dict], str, str]:
    """Return (drawing, identity_method, notes).

    Prefer the stroke the audit treated as the visible member:
    - nearest near_label_raw hit for label-on-member cases
    - for leader-only cases: longest tip_target that is not the retained leader
      callout; if that cannot be established → TARGET_IDENTITY_UNCERTAIN
    """
    bb = gold["label_bbox"]
    lx, ly = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
    near = audit_row.get("near_label_raw") or []
    if near:
        # Prefer the longest member-scale near-label stroke (len>=25) over short
        # callout fragments that may sit closer to the label center.
        memberish = [h for h in near if float(h.get("path_length") or 0.0) >= 25.0]
        hit = max(memberish, key=lambda h: float(h.get("path_length") or 0.0)) if memberish else near[0]
        drawing = _match_audit_near(raw, hit, lx, ly)
        if drawing is not None:
            method = (
                "audit_near_label_longest_ge25"
                if memberish
                else "audit_near_label_raw[0]"
            )
            return drawing, method, (
                f"perp={hit.get('perp_distance')} len={hit.get('path_length')} "
                f"audit_retained_cap450={hit.get('retained_by_cap')}"
            )
        return None, "TARGET_IDENTITY_UNCERTAIN", "audit near_label hit not re-matched in raw"

    tip = (audit_row.get("leader_trace") or {}).get("tip")
    tip_targets = (audit_row.get("leader_trace") or {}).get("tip_targets") or []
    if tip and tip_targets:
        # Prefer tip targets that were NOT retained-as-leader under CAP_450,
        # then the longest path (member-scale more likely than arrowhead).
        candidates = sorted(
            tip_targets,
            key=lambda t: (
                1 if t.get("classified_kind") == "leader" else 0,
                -(float(t.get("path_length") or 0.0)),
            ),
        )
        for hit in candidates:
            if hit.get("classified_kind") == "leader" and hit.get("retained_by_cap"):
                continue
            drawing = _match_audit_tip_target(raw, tip, hit)
            if drawing is not None:
                return drawing, "audit_tip_target_non_leader", (
                    f"tip_d={hit.get('tip_distance')} len={hit.get('path_length')} "
                    f"audit_retained_cap450={hit.get('retained_by_cap')}"
                )
        # Fall back to longest tip target even if it was a leader fragment.
        hit = max(tip_targets, key=lambda t: float(t.get("path_length") or 0.0))
        drawing = _match_audit_tip_target(raw, tip, hit)
        if drawing is not None:
            return drawing, "audit_tip_target_longest", (
                f"tip_d={hit.get('tip_distance')} len={hit.get('path_length')} "
                f"(may be leader fragment; see notes)"
            )
        return None, "TARGET_IDENTITY_UNCERTAIN", "audit tip targets not re-matched"

    return None, "TARGET_IDENTITY_UNCERTAIN", "no audit near_label or tip_target evidence"


def _pick_population_target(
    raw: List[dict], gold: Dict[str, Any]
) -> Tuple[Optional[dict], str, str]:
    """Conservative identity for non-audited visible-member misses.

    Label-on-member (not leader_required): nearest on-segment stroke.
    Leader-required without audit evidence: TARGET_IDENTITY_UNCERTAIN.
    """
    if gold.get("leader_required"):
        return None, "TARGET_IDENTITY_UNCERTAIN", (
            "leader_required and not in extraction audit — refusing to invent tip target"
        )
    bb = gold["label_bbox"]
    lx, ly = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
    drawing = _find_nearest_label_stroke(raw, lx, ly)
    if drawing is None:
        return None, "TARGET_IDENTITY_UNCERTAIN", "no on-segment stroke within perp<=14 len>=15"
    return drawing, "nearest_on_segment_label_stroke", (
        f"len={round(_path_length(drawing), 2)} "
        f"perp={round(_nearest_on_path(lx, ly, drawing)[0], 2)}"
    )


def _find_associated_raw(
    raw: List[dict],
    objects_450: List[Dict[str, Any]],
    by_raw_450: Dict[int, Dict[str, Any]],
    gold_gid: str,
    artifact_obj: Dict[str, Any],
) -> Tuple[Optional[dict], str]:
    """Locate the raw drawing that produced the gold geometry under CAP_450."""
    for obj in objects_450:
        if obj["geometry_id"] == gold_gid:
            rid = obj["_raw_id"]
            for drawing in raw:
                if id(drawing) == rid:
                    return drawing, "gold_selected_geometry_id_via_cap450"
    # Fallback: match artifact bbox among CAP_450 objects
    ab = artifact_obj.get("bbox") or []
    al = artifact_obj.get("length")
    target_fp = _bbox_fingerprint(ab, al)
    for obj in objects_450:
        if _bbox_fingerprint(obj["bbox"], obj.get("length")) == target_fp:
            rid = obj["_raw_id"]
            for drawing in raw:
                if id(drawing) == rid:
                    return drawing, "gold_bbox_fingerprint_via_cap450"
    return None, "TARGET_IDENTITY_UNCERTAIN"


# ---------------------------------------------------------------------------
# Neighborhood metric (secondary; for dense tip regions like p18_1186)
# ---------------------------------------------------------------------------
def _neighborhood_counts(
    raw: List[dict],
    kept_ids: Dict[str, set],
    center: Sequence[float],
    *,
    radius: float = 22.0,
    min_len: float = 8.0,
) -> Dict[str, Any]:
    cx, cy = float(center[0]), float(center[1])
    nearby: List[dict] = []
    for drawing in raw:
        rect = drawing.get("rect")
        if rect is None:
            continue
        if not (
            rect.x0 - radius <= cx <= rect.x1 + radius
            and rect.y0 - radius <= cy <= rect.y1 + radius
        ):
            continue
        dist, _t = _nearest_on_path(cx, cy, drawing)
        if dist > radius:
            continue
        if _path_length(drawing) < min_len:
            continue
        nearby.append(drawing)
    out: Dict[str, Any] = {"raw_nearby": len(nearby)}
    for name, ids in kept_ids.items():
        out[f"survives_{name}"] = sum(1 for d in nearby if id(d) in ids)
    return out


# ---------------------------------------------------------------------------
def main() -> int:
    gold_sha_before = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    document = json.loads((ARTIFACT / "document.json").read_text())
    artifact_geometry = json.loads((ARTIFACT / "geometry.json").read_text())
    artifact_by_id = {o["geometry_id"]: o for o in artifact_geometry["objects"]}
    gold_rows = [
        json.loads(line)
        for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    ]
    gold_by = {r["token_id"]: r for r in gold_rows}
    audit_by = {
        json.loads(line)["token_id"]: json.loads(line)
        for line in AUDIT_PATH.read_text().splitlines()
        if line.strip()
    }
    page_scales = detect_page_scales(document)

    pdf = fitz.open(PDF_PATH)

    # ---- per-page extraction under each cap ----
    page_state: Dict[int, Dict[str, Any]] = {}
    for page_number in PAGES:
        page = pdf[page_number - 1]
        raw = page.get_drawings() or []
        pw, ph = float(page.rect.width), float(page.rect.height)
        ordered, rank, exclusion = _structural_first_order(raw, page_width=pw, page_height=ph)
        n_long = sum(
            1 for item in ordered if max(GX._drawing_wh(item)) >= GX._STRUCTURAL_MIN_SPAN_PT
        )
        n_short = len(ordered) - n_long

        kept_by_cap: Dict[str, List[dict]] = {}
        kept_ids: Dict[str, set] = {}
        objects_by_cap: Dict[str, List[Dict[str, Any]]] = {}
        by_raw_by_cap: Dict[str, Dict[int, Dict[str, Any]]] = {}

        for name, cap in CAP_VARIANTS:
            kept = _select_cap(raw, page_width=pw, page_height=ph, cap=cap)
            kept_by_cap[name] = kept
            kept_ids[name] = {id(d) for d in kept}
            objects, by_raw = _classify_kept(
                kept, page_number=page_number, document=document, page_scales=page_scales
            )
            objects_by_cap[name] = objects
            by_raw_by_cap[name] = by_raw

        # Fidelity check: CAP_450 post-merge ids must match artifact
        objs_450 = objects_by_cap["CAP_450"]
        # Re-merge already done inside _classify_kept; compare pre-merge id set
        # against artifact by replaying merge on CAP_450 objects.
        resolved = resolve_page_scale(document, page_number, page_scales=page_scales)
        page_scale = (
            page_scales.get(page_number) if resolved.get("scale_reason") == "page_scale" else None
        )
        merged_450, _ = merge_collinear_fragments(
            [
                {k: v for k, v in o.items() if not k.startswith("_")}
                for o in objs_450
            ],
            scale=page_scale,
        )
        art_ids = {
            o["geometry_id"]
            for o in artifact_geometry["objects"]
            if o["page_number"] == page_number
        }
        replay_ids = {o["geometry_id"] for o in merged_450}
        page_state[page_number] = {
            "raw": raw,
            "page_width": pw,
            "page_height": ph,
            "ordered": ordered,
            "rank": rank,
            "exclusion": exclusion,
            "n_long_strokes": n_long,
            "n_short_strokes": n_short,
            "structural_min_span_pt": GX._STRUCTURAL_MIN_SPAN_PT,
            "kept_by_cap": kept_by_cap,
            "kept_ids": kept_ids,
            "objects_by_cap": objects_by_cap,
            "by_raw_by_cap": by_raw_by_cap,
            "fidelity": {
                "artifact_count": len(art_ids),
                "cap450_merged_count": len(merged_450),
                "geometry_id_match": len(replay_ids & art_ids),
                "replay_faithful": replay_ids == art_ids,
            },
        }
        print(
            f"p{page_number}: raw={len(raw)} "
            + " ".join(f"{n}={len(kept_by_cap[n])}" for n, _ in CAP_VARIANTS)
            + f" faithful={page_state[page_number]['fidelity']['replay_faithful']}"
        )

    # ---- populations ----
    associated = [g for g in gold_rows if g.get("decision") == "associated"]
    ambiguous = [g for g in gold_rows if g.get("decision") == "ambiguous"]
    visible_misses = [
        g
        for g in gold_rows
        if g.get("decision") == "no_valid_member"
        and g.get("error_bucket") != "schedule_table_not_member"
        and int(g.get("page") or 0) in PAGES
    ]
    audited_tokens = set(audit_by.keys())
    audited_cases = [gold_by[t] for t in audit_by.keys() if t in gold_by]

    def evaluate_case(
        gold: Dict[str, Any],
        *,
        population: str,
        force_audit: bool = False,
    ) -> Dict[str, Any]:
        token = gold["token_id"]
        page_number = int(gold["page"])
        state = page_state[page_number]
        raw = state["raw"]
        drawing: Optional[dict] = None
        identity_method = "TARGET_IDENTITY_UNCERTAIN"
        identity_notes = ""

        if gold.get("decision") == "associated" and gold.get("selected_geometry_id"):
            art = artifact_by_id.get(gold["selected_geometry_id"], {})
            drawing, identity_method = _find_associated_raw(
                raw,
                state["objects_by_cap"]["CAP_450"],
                state["by_raw_by_cap"]["CAP_450"],
                gold["selected_geometry_id"],
                art,
            )
            identity_notes = f"gold_gid={gold['selected_geometry_id']}"
        elif token in audit_by and (force_audit or population in {"audited_21", "associated", "ambiguous", "visible_member_miss"}):
            drawing, identity_method, identity_notes = _pick_audit_primary_target(
                raw, audit_by[token], gold
            )
        elif population == "visible_member_miss":
            drawing, identity_method, identity_notes = _pick_population_target(raw, gold)

        row: Dict[str, Any] = {
            "token_id": token,
            "page": page_number,
            "label": gold.get("text"),
            "population": population,
            "human_decision": gold.get("decision"),
            "human_error_bucket": gold.get("error_bucket"),
            "leader_required": bool(gold.get("leader_required")),
            "gold_selected_geometry_id": gold.get("selected_geometry_id"),
            "in_extraction_audit": token in audit_by,
            "target_identity_method": identity_method,
            "target_identity_notes": identity_notes,
            "RAW_PRESENT": drawing is not None,
            "target_fingerprint": None if drawing is None else list(_drawing_fingerprint(drawing)),
            "target_path_length": None if drawing is None else round(_path_length(drawing), 2),
            "target_structural_keep_score": None
            if drawing is None
            else round(GX._structural_keep_score(drawing), 1),
            "target_cap_rank": None,
            "target_excluded_before_rank": None,
            "cap_results": {},
            "neighborhood_22pt": None,
        }

        if drawing is None:
            for name, _cap in CAP_VARIANTS:
                row["cap_results"][name] = {
                    "SURVIVES_CAP": None,
                    "SURVIVES_FILTERING": None,
                    "CLASSIFICATION": None,
                    "reclassified_by": None,
                    "available_to_candidate_generation": None,
                    "geometry_id": None,
                }
            return row

        rid = id(drawing)
        row["target_cap_rank"] = state["rank"].get(rid)
        row["target_excluded_before_rank"] = state["exclusion"].get(rid)

        # Neighborhood around the target (secondary density evidence)
        rect = drawing.get("rect")
        if rect is not None:
            center = [(rect.x0 + rect.x1) / 2.0, (rect.y0 + rect.y1) / 2.0]
            row["neighborhood_22pt"] = _neighborhood_counts(
                raw, state["kept_ids"], center, radius=22.0
            )

        for name, _cap in CAP_VARIANTS:
            survives_cap = rid in state["kept_ids"][name]
            obj = state["by_raw_by_cap"][name].get(rid)
            survives_filtering = bool(obj)  # classified into an object (not degenerate)
            classification = None if not obj else obj["kind"]
            reclass = None if not obj else obj.get("reclassified_by")
            available = bool(
                survives_cap and survives_filtering and classification in _MEMBER_KINDS
            )
            row["cap_results"][name] = {
                "SURVIVES_CAP": survives_cap,
                "SURVIVES_FILTERING": survives_filtering,
                "CLASSIFICATION": classification,
                "reclassified_by": reclass,
                "available_to_candidate_generation": available,
                "geometry_id": None if not obj else obj.get("geometry_id"),
                "loss_stage": (
                    "not_in_raw"
                    if False
                    else (
                        "excluded_before_rank"
                        if state["exclusion"].get(rid) and not survives_cap
                        else (
                            "dropped_by_cap"
                            if not survives_cap
                            else (
                                "classified_as_callout"
                                if classification in _CALLOUT_KINDS
                                else "survives_all_extraction_stages"
                            )
                        )
                    )
                ),
            }
        return row

    rows: List[Dict[str, Any]] = []

    # 21 audited (primary comparison set)
    for gold in audited_cases:
        pop = "audited_21"
        if gold.get("decision") == "associated":
            # Still include in audited_21; also evaluate under associated below
            pass
        rows.append(evaluate_case(gold, population=pop, force_audit=True))

    # 8 associated (regression control) — use gold GID identity
    for gold in associated:
        if int(gold["page"]) not in PAGES:
            continue
        rows.append(evaluate_case(gold, population="associated"))

    # 2 ambiguous
    for gold in ambiguous:
        if int(gold["page"]) not in PAGES:
            continue
        rows.append(evaluate_case(gold, population="ambiguous", force_audit=True))

    # 58 visible-member misses
    for gold in visible_misses:
        rows.append(evaluate_case(gold, population="visible_member_miss", force_audit=True))

    # ---- aggregates ----
    def survival_table(population: str) -> Dict[str, Any]:
        subset = [r for r in rows if r["population"] == population]
        identifiable = [r for r in subset if r["RAW_PRESENT"] and r["target_identity_method"] != "TARGET_IDENTITY_UNCERTAIN"]
        uncertain = [r for r in subset if r["target_identity_method"] == "TARGET_IDENTITY_UNCERTAIN"]
        out: Dict[str, Any] = {
            "n_cases": len(subset),
            "identifiable_targets": len(identifiable),
            "uncertain_targets": len(uncertain),
            "by_cap": {},
        }
        for name, _cap in CAP_VARIANTS:
            survive = sum(
                1 for r in identifiable if r["cap_results"][name]["SURVIVES_CAP"] is True
            )
            avail = sum(
                1
                for r in identifiable
                if r["cap_results"][name]["available_to_candidate_generation"] is True
            )
            callout = sum(
                1
                for r in identifiable
                if r["cap_results"][name]["SURVIVES_CAP"]
                and r["cap_results"][name]["CLASSIFICATION"] in _CALLOUT_KINDS
            )
            out["by_cap"][name] = {
                "survive_cap": survive,
                "survival_pct": round(100.0 * survive / len(identifiable), 1)
                if identifiable
                else None,
                "available_to_candidates": avail,
                "survives_cap_but_classified_callout": callout,
            }
        # incremental
        names = [n for n, _ in CAP_VARIANTS]
        incremental = {}
        for i in range(1, len(names)):
            prev, cur = names[i - 1], names[i]
            added = sum(
                1
                for r in identifiable
                if r["cap_results"][prev]["SURVIVES_CAP"] is False
                and r["cap_results"][cur]["SURVIVES_CAP"] is True
            )
            lost = sum(
                1
                for r in identifiable
                if r["cap_results"][prev]["SURVIVES_CAP"] is True
                and r["cap_results"][cur]["SURVIVES_CAP"] is False
            )
            incremental[f"{prev}_to_{cur}"] = {
                "additional_surviving": added,
                "regressions": lost,
            }
        out["incremental"] = incremental
        return out

    page_level = {}
    for page_number, state in page_state.items():
        raw_n = len(state["raw"])
        page_level[str(page_number)] = {
            "raw_paths": raw_n,
            "ranked_pool": len(state["ordered"]),
            "long_strokes_in_pool": state["n_long_strokes"],
            "short_strokes_in_pool": state["n_short_strokes"],
            "structural_min_span_pt": state["structural_min_span_pt"],
            "excluded_tiny_or_frame": raw_n - len(state["ordered"]),
            "fidelity": state["fidelity"],
            "caps": {
                name: {
                    "retained": len(state["kept_by_cap"][name]),
                    "dropped_from_raw": raw_n - len(state["kept_by_cap"][name]),
                    "pct_raw_retained": round(
                        100.0 * len(state["kept_by_cap"][name]) / raw_n, 2
                    ),
                    "post_classify_objects": len(state["objects_by_cap"][name]),
                }
                for name, _ in CAP_VARIANTS
            },
        }

    # Cap vs classification for audited_21
    audited_rows = [r for r in rows if r["population"] == "audited_21" and r["RAW_PRESENT"]]
    stage_buckets = Counter()
    for r in audited_rows:
        c450 = r["cap_results"]["CAP_450"]
        if not c450["SURVIVES_CAP"]:
            stage_buckets["lost_at_cap_450"] += 1
        elif c450["CLASSIFICATION"] in _CALLOUT_KINDS:
            stage_buckets["survives_cap_but_classified_callout"] += 1
        elif c450["available_to_candidate_generation"]:
            stage_buckets["survives_all_extraction_stages"] += 1
        else:
            stage_buckets["survives_cap_other"] += 1

    # Associated regression detail
    assoc_rows = [r for r in rows if r["population"] == "associated"]
    assoc_regressions = []
    for r in assoc_rows:
        for name, _ in CAP_VARIANTS:
            if r["RAW_PRESENT"] and r["cap_results"][name]["SURVIVES_CAP"] is False:
                assoc_regressions.append(
                    {
                        "token_id": r["token_id"],
                        "cap": name,
                        "gold_gid": r["gold_selected_geometry_id"],
                        "cap_rank": r["target_cap_rank"],
                    }
                )

    # Highlight examples
    example_tokens = [
        "token_p8_355",
        "token_p8_348",
        "token_p18_1186",
        "token_p18_1162",
        "token_p24_1385",
        "token_p8_340",
    ]
    examples = {
        t: next((r for r in rows if r["token_id"] == t and r["population"] == "audited_21"), None)
        or next((r for r in rows if r["token_id"] == t), None)
        for t in example_tokens
    }

    summary = {
        "document_id": DOC_ID,
        "pages": list(PAGES),
        "cap_variants": [{"name": n, "cap": c} for n, c in CAP_VARIANTS],
        "gold_sha256": gold_sha_before,
        "experimental_variable": "dense_page_path_cap_only",
        "cap_selection_mechanism": (
            "structural_first: exclude tiny (<3pt) and page-frame; score by "
            "_structural_keep_score; keep long strokes (span>=STRUCTURAL_MIN_SPAN_PT) "
            "first up to cap, then fill with short strokes. Rank = position in that order."
        ),
        "page_level": page_level,
        "target_survival": {
            "audited_21": survival_table("audited_21"),
            "associated_8": survival_table("associated"),
            "visible_member_miss_58": survival_table("visible_member_miss"),
            "ambiguous_2": survival_table("ambiguous"),
        },
        "cap_vs_classification_audited_21": dict(stage_buckets),
        "associated_regressions": assoc_regressions,
        "examples": {k: v for k, v in examples.items() if v is not None},
        "n_jsonl_rows": len(rows),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    jsonl_path = OUT / "cap_cost_results.jsonl"
    with jsonl_path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    (OUT / "cap_cost_summary.json").write_text(json.dumps(summary, indent=2))

    gold_sha_after = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if gold_sha_after != gold_sha_before:
        raise RuntimeError("gold_outcomes.jsonl changed during E1 — abort")

    print("\n=== TARGET SURVIVAL (identifiable) ===")
    for pop, label in [
        ("audited_21", "audited_21"),
        ("associated_8", "associated"),
        ("visible_member_miss_58", "visible_member_miss"),
    ]:
        t = summary["target_survival"][pop]
        print(f"\n{pop}: identifiable={t['identifiable_targets']} uncertain={t['uncertain_targets']}")
        for name, _ in CAP_VARIANTS:
            b = t["by_cap"][name]
            print(
                f"  {name}: survive={b['survive_cap']}/{t['identifiable_targets']} "
                f"({b['survival_pct']}%)  "
                f"callout={b['survives_cap_but_classified_callout']}  "
                f"candidate_avail={b['available_to_candidates']}"
            )
        print("  incremental:", t["incremental"])
    print("\ncap vs classification (audited_21 identifiable raw):", dict(stage_buckets))
    print("associated regressions:", assoc_regressions)
    print("gold sha256 unchanged:", gold_sha_after)
    print("wrote", jsonl_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
