#!/usr/bin/env python3
"""Geometry extraction audit (R&D, read-only).

Replays the production extraction stages for the Burrville audit pages using the
production helpers *without modifying them*, so each representative failure can be
attributed to a stage:

    raw get_drawings -> dense-page cap -> classification -> collinear merge
    -> candidate eligibility -> retrieval -> leader handling

Nothing here is wired into production. Human gold is read, never written.

Usage (from backend/):
    python scripts/rd_geometry_integration/extraction_audit.py [--renders]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
V2_ROWS = OUT / "v2_rows.jsonl"
RENDER_DIR = OUT / "extraction_audit_renders"

# Representative cases (from gold + v2 artifacts; no invented tokens).
AUDIT_TOKENS = [
    # p8 framing plan
    "token_p8_355",  # zero R&D candidates
    "token_p8_348",  # giant bay polyline / W30X90
    "token_p8_337",  # girder next to giant polyline
    "token_p8_381",  # parallel joist
    "token_p8_430",  # parallel joist
    "token_p8_332",  # opening frame
    "token_p8_346",  # short infill joist
    "token_p8_359",  # v2 claimed proxy recovery
    "token_p8_351",  # v2 claimed leader-target recovery
    "token_p8_340",  # CONTROL: human-associated
    "token_p8_367",  # CONTROL: human ambiguous
    # p18 detail / schedule sheet
    "token_p18_1186",  # WT7X19 leader
    "token_p18_1178",  # L4X4X1/4 brace leader
    "token_p18_1169",  # plate leader, v2 claimed recovery
    "token_p18_1162",  # plate leader, v2 claimed recovery
    "token_p18_1143",  # CONTROL: splice schedule cell
    # p24 section sheet
    "token_p24_1361",  # v2 claimed leader recovery
    "token_p24_1360",
    "token_p24_1377",
    "token_p24_1359",
    "token_p24_1385",
]

FAILURE_CLASSES = [
    "RAW_GEOMETRY_MISSING",
    "RAW_GEOMETRY_PRESENT_NOT_NORMALIZED",
    "COMPOUND_PATH_NEEDS_SEGMENTATION",
    "EXTRACTED_BUT_FILTERED",
    "EXTRACTED_BUT_RETRIEVAL_MISS",
    "LEADER_ENDPOINT_FAILURE",
    "LEADER_TARGET_GEOMETRY_MISSING",
    "GIANT_PRIMITIVE_REPRESENTATION",
    "DRAWING_AMBIGUITY",
    "OTHER",
]

# ---------------------------------------------------------------------------
# Reviewer visual verdicts.
#
# Filled in by a human pass over extraction_audit_renders/ (same reference
# standard as the human gold review: what the PDF visibly intends). The
# mechanical stage trace below is computed, not authored. These verdicts do NOT
# modify gold and do not assign geometry ids to gold records.
# ---------------------------------------------------------------------------
VISUAL_VERDICTS: Dict[str, Dict[str, Any]] = {
    "token_p8_355": {
        "visual_observation": (
            "Label sits directly on the short W10X15[9] infill joist between the two "
            "W21X44 girders. The joist is drawn as collinear fragments: the 67.7pt one is "
            "cap-dropped and the 18pt ones are retained but classified 'leader'."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
    },
    "token_p8_348": {
        "visual_observation": (
            "Label sits on the diagonal W30X90 girder, which exists as its own 324pt raw "
            "line and is retained (geom_f35a9d1c5bd7) but classified 'dimension'. The "
            "girder is NOT inside a bay polyline, so this is not a giant-primitive case."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
    },
    "token_p8_337": {
        "visual_observation": (
            "Label sits on the upper W21X44[30] girder. Girder stroke present as a long "
            "diagonal raw line; retrieval instead offered the bay polyline / EJ wall."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
    },
    "token_p8_381": {
        "visual_observation": (
            "Label sits on one of several parallel W18X35 joists. The joist stroke under "
            "the label is present as a long diagonal raw line."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
    },
    "token_p8_430": {
        "visual_observation": (
            "Label sits on a W18X35 joist in a dense parallel bay; the stroke under the "
            "label is present and retained, but classified as a dimension."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
    },
    "token_p8_332": {
        "visual_observation": (
            "Label sits on the W14X22[25] edge of the opening frame. Five local strokes "
            "exist in raw geometry; four were dropped by the cap and the one retained "
            "stroke was classified as a dimension. The retained 'line' that reaches "
            "candidates is a different stroke further out, not the framed edge."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
    },
    "token_p8_346": {
        "visual_observation": (
            "Label sits on the short W10X15[9] joist between girders; the short stroke is "
            "present in raw geometry."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
    },
    "token_p8_359": {
        "visual_observation": (
            "Label text is set along its own W18X40 joist among parallel W18X40s. The "
            "joist stroke is retained AND classified 'line' (geom_9027619e697a), sits "
            "8.9pt from the label center, on-segment, and is in the v2 candidate set."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_RETRIEVAL_MISS",
        "recoverability": "already_available_but_retrieval_misses",
    },
    "token_p8_351": {
        "visual_observation": (
            "Label sits between the slab-edge line and the adjacent W12[8] line; no stroke "
            "sits at the ~9pt label-to-member offset that the rest of the sheet uses. The "
            "nearest retained line is 20.8pt away and visual evidence does not confirm it "
            "as this W18X35."
        ),
        "member_is_visible": True,
        "primary_failure_class": "DRAWING_AMBIGUITY",
        "recoverability": "visually_ambiguous",
    },
    "token_p8_340": {
        "visual_observation": (
            "CONTROL. Human-associated: label sits on the W21X44[50] wall beam and the "
            "gold geometry is the retained wall stroke."
        ),
        "member_is_visible": True,
        "primary_failure_class": "OTHER",
        "recoverability": "already_available_retrieval_succeeds",
        "notes": "Not a failure: control case showing the working path end to end.",
    },
    "token_p8_367": {
        "visual_observation": (
            "CONTROL. Human abstention: opening / stair / W12X16 infill node; the drawing "
            "does not identify one unique member."
        ),
        "member_is_visible": False,
        "primary_failure_class": "DRAWING_AMBIGUITY",
        "recoverability": "visually_ambiguous",
    },
    "token_p18_1186": {
        "visual_observation": (
            "WT7X19 with a single diagonal leader whose arrow lands on the WT stem below "
            "the beam. The leader stroke itself (len 51.1) is dropped by the cap, and the "
            "WT neighborhood holds 137 raw primitives of which only 2 are retained."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
        "notes": "leader_status=leader_stroke_not_retained (dropped by dense-page cap)",
    },
    "token_p18_1178": {
        "visual_observation": (
            "L4X4X1/4 brace callout. The label-anchored stroke (14.5) and the target "
            "cluster at its far end (30.1, 89.4) are all cap-dropped; the only retained "
            "local object is a leader. v2's 'recovered' candidate is not the brace angle."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
        "notes": "leader_status=leader_stroke_not_retained (dropped by dense-page cap)",
    },
    "token_p18_1169": {
        "visual_observation": (
            "PL 1 1/2\" callout on a weld-symbol reference line pointing at the tall shear "
            "plate between beam and column. That plate IS retained "
            "(geom_4e68ef0da179, rectangle 37.8x112.6) and IS in the v2 candidate set."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_RETRIEVAL_MISS",
        "recoverability": "already_available_but_retrieval_misses",
    },
    "token_p18_1162": {
        "visual_observation": (
            "PL 3/8\" is attached to a weld symbol; the retained 'leader' is the weld "
            "reference line, not a pointer. The real arrow strokes (63.7, 48.1) toward the "
            "splice plate are cap-dropped, and the plate region holds 198 raw primitives "
            "of which 6 are retained."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "potentially_recoverable_leader_endpoint",
        "notes": "leader_status=weld_symbol_reference_line_mistaken_for_leader",
    },
    "token_p18_1143": {
        "visual_observation": (
            "CONTROL. STEEL COLUMN SPLICE table cell. No drawn member corresponds to this "
            "text; retrieval returns table rules."
        ),
        "member_is_visible": False,
        "primary_failure_class": "OTHER",
        "recoverability": "not_a_member",
        "notes": "Schedule/table text — correctly has no member to associate.",
    },
    "token_p24_1361": {
        "visual_observation": (
            "L4X4X3/8 HGR is attached to a weld symbol; the retained 'leader' is that weld "
            "reference line. The hanger angle stands to the right: 16 raw primitives there, "
            "4 retained and all classified 'dimension'. v2's hop landed on joist/hatch "
            "geometry, which visual QA rejects."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "potentially_recoverable_leader_endpoint",
        "notes": "leader_status=weld_symbol_reference_line_mistaken_for_leader",
    },
    "token_p24_1360": {
        "visual_observation": (
            "L4x4x3/8 CONT callout. Every label-anchored stroke is cap-dropped; at the "
            "visually indicated angle, 47 raw primitives exist and the retained ones are "
            "unrelated long lines."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
        "notes": "leader_status=leader_stroke_not_retained (dropped by dense-page cap)",
    },
    "token_p24_1377": {
        "visual_observation": (
            "L4x4x3/8 DSA. The long pointer strokes to the angle ARE retained but are "
            "classified 'dimension' (geom_ae18c735015e / geom_7bdc3406efaa), while the "
            "angle at their far end (72.0, 21.5, 13.0) is cap-dropped. The retained "
            "'leader' near the label is the weld reference line."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "potentially_recoverable_leader_endpoint",
        "notes": "leader_status=true_pointer_retained_but_classified_dimension",
    },
    "token_p24_1359": {
        "visual_observation": (
            "L6x3-1/2x3/8 callout. The only label-anchored strokes (10.9, 41.3) are "
            "cap-dropped; the single retained neighbour is a 405pt wall line 21pt from the "
            "tip, which visual evidence does not support as the angle."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
        "notes": "leader_status=leader_stroke_not_retained (dropped by dense-page cap)",
    },
    "token_p24_1385": {
        "visual_observation": (
            "L4x4x3/8 callout. The leader is drawn as a short stub plus a diagonal "
            "continuation; the continuation and every primitive within 25pt of the true "
            "arrow tip are cap-dropped, so nothing local survives at all."
        ),
        "member_is_visible": True,
        "primary_failure_class": "EXTRACTED_BUT_FILTERED",
        "recoverability": "clearly_recoverable_extraction_normalization",
        "notes": "leader_status=leader_fragmented_continuation_not_retained",
    },
}


# ---------------------------------------------------------------------------
# geometry helpers (audit-local; production code is untouched)
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


def _endpoints(drawing: Dict[str, Any]) -> List[Tuple[float, float]]:
    segs = _segments(drawing)
    if not segs:
        return []
    return [segs[0][0], segs[-1][1]]


def _item_types(drawing: Dict[str, Any]) -> List[str]:
    return sorted({str(it[0]).lower() for it in (drawing.get("items") or []) if it})


def _drop_reason(
    drawing: Dict[str, Any], page_width: float, page_height: float
) -> str:
    if GX._is_tiny_noise_drawing(drawing):
        return "dense_cap_excluded_tiny_noise"
    if GX._is_page_frame_drawing(drawing, page_width, page_height):
        return "dense_cap_excluded_page_frame"
    return "dense_cap_below_rank"


# ---------------------------------------------------------------------------
# stage replay — production helpers, production order
# ---------------------------------------------------------------------------
class PageReplay:
    def __init__(self, page: "fitz.Page", page_number: int, document: Dict[str, Any], page_scales):
        self.page_number = page_number
        self.page = page
        self.document = document
        self.raw = page.get_drawings() or []
        self.page_width = float(page.rect.width)
        self.page_height = float(page.rect.height)
        self.kept = GX._select_under_dense_cap(
            self.raw,
            page_width=self.page_width,
            page_height=self.page_height,
            cap=GX._DENSE_PAGE_CAP,
            strategy="structural_first",
        )
        self.kept_ids = {id(item) for item in self.kept}

        resolved = resolve_page_scale(document, page_number, page_scales=page_scales)
        self.page_scale = (
            page_scales.get(page_number) if resolved.get("scale_reason") == "page_scale" else None
        )
        radius = association_radius_pdf_points(self.page_scale) * (48.0 / 160.0)
        self.nearby_radius = max(24.0, min(96.0, radius))
        self.line_grid: Dict[Tuple[int, int], List[dict]] = {}
        for line in document.get("lines") or []:
            if int(line.get("page_number") or 0) != page_number:
                continue
            center = line.get("center") or [0, 0]
            key = (
                int(float(center[0]) // self.nearby_radius),
                int(float(center[1]) // self.nearby_radius),
            )
            self.line_grid.setdefault(key, []).append(line)

        self.objects: List[Dict[str, Any]] = []
        self.object_by_raw: Dict[int, Dict[str, Any]] = {}
        for drawing in self.kept:
            obj = self._build(drawing, len(self.objects))
            if obj is None:
                continue
            self.objects.append(obj)
            self.object_by_raw[id(drawing)] = obj
        self.merged, self.merge_stats = merge_collinear_fragments(
            [dict(o) for o in self.objects], scale=self.page_scale
        )
        self.merged_by_id = {o["geometry_id"]: o for o in self.merged}
        self.consumed_by: Dict[str, str] = {}
        for obj in self.merged:
            for src in obj.get("merged_from") or []:
                self.consumed_by[str(src)] = obj["geometry_id"]

    def _build(self, drawing: Dict[str, Any], ordinal: int) -> Optional[Dict[str, Any]]:
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
            return None

        kind = GX._classify_path(item_dicts, rect)
        raw_kind = kind.value
        length = (
            GX._length_of_segments(points)
            if len(points) >= 2
            else round(math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]), 3)
        )
        center = [round((bbox[0] + bbox[2]) / 2.0, 2), round((bbox[1] + bbox[3]) / 2.0, 2)]
        nearby = GX._nearby_text(
            center,
            self.page_number,
            self.document,
            radius=self.nearby_radius,
            line_grid=self.line_grid,
        )
        reclass = None
        if GX._looks_like_leader(kind, length, bbox):
            kind = GeometryKind.LEADER
            reclass = "looks_like_leader"
        elif GX._looks_like_dimension(kind, length, nearby):
            kind = GeometryKind.DIMENSION
            reclass = "looks_like_dimension(nearby_numeric_text)"
        width = round(abs(bbox[2] - bbox[0]), 3)
        height = round(abs(bbox[3] - bbox[1]), 3)
        area = round(width * height, 3)
        if kind in {GeometryKind.RECTANGLE, GeometryKind.CIRCLE} and area < 400:
            kind = GeometryKind.SYMBOL
            reclass = "small_closed_shape_to_symbol"
        return {
            "geometry_id": GX._gid(self.page_number, ordinal, bbox, kind.value),
            "kind": kind.value,
            "classified_kind_before_reclass": raw_kind,
            "reclassified_by": reclass,
            "bbox": bbox,
            "center": center,
            "length": length,
            "area": area,
            "width": width,
            "height": height,
            "nearby_text": nearby[:80],
            "points": [[round(p[0], 2), round(p[1], 2)] for p in points[:64]],
            "item_types": sorted({e["type"] for e in item_dicts}),
            "n_items": len(item_dicts),
            "page_number": self.page_number,
        }

    def final_id_for(self, drawing: Dict[str, Any]) -> Optional[str]:
        obj = self.object_by_raw.get(id(drawing))
        if obj is None:
            return None
        gid = obj["geometry_id"]
        return self.consumed_by.get(gid, gid)


# ---------------------------------------------------------------------------
# per-case evidence
# ---------------------------------------------------------------------------
def _near_label_raw(
    replay: PageReplay, lx: float, ly: float, *, perp_max: float, min_len: float
) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for drawing in replay.raw:
        rect = drawing.get("rect")
        if rect is None:
            continue
        if not (rect.x0 - 80 <= lx <= rect.x1 + 80 and rect.y0 - 80 <= ly <= rect.y1 + 80):
            continue
        dist, t = _nearest_on_path(lx, ly, drawing)
        if dist > perp_max or not (-0.02 <= t <= 1.02):
            continue
        length = _path_length(drawing)
        if length < min_len:
            continue
        kept = id(drawing) in replay.kept_ids
        obj = replay.object_by_raw.get(id(drawing))
        hits.append(
            {
                "perp_distance": round(dist, 2),
                "projection_t": round(t, 3),
                "path_length": round(length, 2),
                "bbox_w": round(abs(rect.width), 2),
                "bbox_h": round(abs(rect.height), 2),
                "item_types": _item_types(drawing),
                "n_items": len(drawing.get("items") or []),
                "retained_by_cap": kept,
                "drop_reason": None
                if kept
                else _drop_reason(drawing, replay.page_width, replay.page_height),
                "structural_keep_score": round(GX._structural_keep_score(drawing), 1),
                "classified_kind": None if not obj else obj["kind"],
                "classified_before_reclass": None if not obj else obj["classified_kind_before_reclass"],
                "reclassified_by": None if not obj else obj["reclassified_by"],
                "final_geometry_id": replay.final_id_for(drawing),
                "_drawing": drawing,
            }
        )
    hits.sort(key=lambda h: h["perp_distance"])
    return hits


def _leader_trace(replay: PageReplay, lx: float, ly: float) -> Dict[str, Any]:
    leaders: List[Dict[str, Any]] = []
    for drawing in replay.raw:
        rect = drawing.get("rect")
        if rect is None:
            continue
        if not (rect.x0 - 140 <= lx <= rect.x1 + 140 and rect.y0 - 140 <= ly <= rect.y1 + 140):
            continue
        eps = _endpoints(drawing)
        if len(eps) < 2:
            continue
        d_near = min(math.hypot(lx - p[0], ly - p[1]) for p in eps)
        d_far = max(math.hypot(lx - p[0], ly - p[1]) for p in eps)
        length = _path_length(drawing)
        if d_near > 60 or d_far - d_near < 10 or not (8.0 <= length <= 200.0):
            continue
        tip = max(eps, key=lambda p: math.hypot(lx - p[0], ly - p[1]))
        obj = replay.object_by_raw.get(id(drawing))
        leaders.append(
            {
                "near_distance": round(d_near, 2),
                "far_distance": round(d_far, 2),
                "path_length": round(length, 2),
                "tip": [round(tip[0], 2), round(tip[1], 2)],
                "retained_by_cap": id(drawing) in replay.kept_ids,
                "classified_kind": None if not obj else obj["kind"],
                "final_geometry_id": replay.final_id_for(drawing),
                "_drawing": drawing,
            }
        )
    leaders.sort(key=lambda item: item["near_distance"])
    if not leaders:
        return {"leader_present": False, "leaders": [], "tip": None, "tip_targets": []}

    tip = leaders[0]["tip"]
    leader_raw_ids = {id(item["_drawing"]) for item in leaders[:1]}
    targets: List[Dict[str, Any]] = []
    for drawing in replay.raw:
        if id(drawing) in leader_raw_ids:
            continue
        rect = drawing.get("rect")
        if rect is None:
            continue
        if not (
            rect.x0 - 40 <= tip[0] <= rect.x1 + 40 and rect.y0 - 40 <= tip[1] <= rect.y1 + 40
        ):
            continue
        dist, _t = _nearest_on_path(tip[0], tip[1], drawing)
        if dist > 25.0:
            continue
        kept = id(drawing) in replay.kept_ids
        obj = replay.object_by_raw.get(id(drawing))
        length = _path_length(drawing)
        targets.append(
            {
                "tip_distance": round(dist, 2),
                "path_length": round(length, 2),
                "bbox_w": round(abs(rect.width), 2),
                "bbox_h": round(abs(rect.height), 2),
                "item_types": _item_types(drawing),
                "retained_by_cap": kept,
                "drop_reason": None
                if kept
                else _drop_reason(drawing, replay.page_width, replay.page_height),
                "classified_kind": None if not obj else obj["kind"],
                "final_geometry_id": replay.final_id_for(drawing),
                "_drawing": drawing,
            }
        )
    targets.sort(key=lambda item: item["tip_distance"])
    return {
        "leader_present": True,
        "leaders": leaders[:3],
        "tip": tip,
        "tip_targets": targets[:10],
    }


def _page_convention_scan(
    replay: PageReplay, labels: List[Dict[str, Any]], *, min_len: float = 25.0, window: float = 40.0
) -> Dict[str, Any]:
    """For every gold label on a page: what happened to the stroke it sits on?

    Generalises the sampled cases. A structural label on these sheets is set a
    fixed offset from its member, so the nearest on-segment stroke is a usable
    (not proof-grade) stand-in for 'the member the label names'.
    """

    outcome = Counter()
    perps: List[float] = []
    for gold_row in labels:
        bb = gold_row["label_bbox"]
        lx, ly = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
        best: Optional[Tuple[float, Dict[str, Any]]] = None
        for drawing in replay.raw:
            rect = drawing.get("rect")
            if rect is None:
                continue
            if not (
                rect.x0 - window <= lx <= rect.x1 + window
                and rect.y0 - window <= ly <= rect.y1 + window
            ):
                continue
            for a, b in _segments(drawing):
                seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
                if seg_len < min_len:
                    continue
                dist, t = _point_to_segment(lx, ly, a, b)
                if not (0.0 <= t <= 1.0):
                    continue
                if best is None or dist < best[0]:
                    best = (dist, drawing)
        if best is None:
            outcome["no_on_segment_stroke_within_window"] += 1
            continue
        dist, drawing = best
        perps.append(dist)
        if id(drawing) not in replay.kept_ids:
            outcome["dropped_by_dense_page_cap"] += 1
            continue
        obj = replay.object_by_raw.get(id(drawing))
        kind = (obj or {}).get("kind", "unknown")
        if kind in {"leader", "dimension"}:
            outcome[f"retained_but_classified_{kind}"] += 1
        else:
            outcome[f"retained_as_{kind}"] += 1
    perps.sort()
    return {
        "labels_scanned": len(labels),
        "outcomes": dict(outcome),
        "perp_distance_median": round(perps[len(perps) // 2], 2) if perps else None,
        "perp_distance_p90": round(perps[int(0.9 * (len(perps) - 1))], 2) if perps else None,
        "retained_kind_counts": dict(Counter(o["kind"] for o in replay.merged)),
        "giant_primitive_points": [
            len(o.get("points") or [])
            for o in replay.merged
            if max(o["bbox"][2] - o["bbox"][0], o["bbox"][3] - o["bbox"][1]) > 600
        ],
    }


def _strip(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: _strip(v) for k, v in payload.items() if not k.startswith("_")}
    if isinstance(payload, list):
        return [_strip(v) for v in payload]
    return payload


# ---------------------------------------------------------------------------
# renders
# ---------------------------------------------------------------------------
def _render_case(
    pdf: "fitz.Document",
    replay: PageReplay,
    row: Dict[str, Any],
    out_path: Path,
    *,
    pad: float = 150.0,
    zoom: float = 2.2,
) -> bool:
    page = pdf[replay.page_number - 1]
    label_bb = row["label_bbox"]

    def rect(bb, color, width, dashes=None):
        kwargs = {"color": color, "width": width}
        if dashes:
            kwargs["dashes"] = dashes
        page.draw_rect(fitz.Rect(bb), **kwargs)

    def path_stroke(drawing, color, width):
        for a, b in _segments(drawing):
            page.draw_line(fitz.Point(*a), fitz.Point(*b), color=color, width=width)

    # retained (kept) geometry near the label: green
    for hit in row["near_label_raw"][:8]:
        color = (0.05, 0.6, 0.2) if hit["retained_by_cap"] else (0.9, 0.1, 0.1)
        path_stroke(hit["_drawing"], color, 1.4)
    # leader + tip: purple
    trace = row["leader_trace"]
    for lead in trace.get("leaders") or []:
        path_stroke(lead["_drawing"], (0.55, 0.15, 0.75), 1.4)
    if trace.get("tip"):
        page.draw_circle(fitz.Point(*trace["tip"]), 5.0, color=(0.55, 0.15, 0.75), width=1.4)
    for tgt in (trace.get("tip_targets") or [])[:8]:
        color = (0.05, 0.6, 0.2) if tgt["retained_by_cap"] else (0.9, 0.1, 0.1)
        path_stroke(tgt["_drawing"], color, 1.4)
    # gold geometry (associated only): magenta
    if row.get("gold_geometry_bbox"):
        rect(row["gold_geometry_bbox"], (0.8, 0.05, 0.55), 1.8)
    rect(label_bb, (0.1, 0.35, 0.92), 1.8)

    cx = (float(label_bb[0]) + float(label_bb[2])) / 2.0
    cy = (float(label_bb[1]) + float(label_bb[3])) / 2.0
    clip = fitz.Rect(cx - pad, cy - pad, cx + pad, cy + pad)
    page.insert_text(
        fitz.Point(clip.x0 + 6, clip.y0 + 12),
        "blue=label  green=retained raw  RED=raw dropped by cap  purple=leader+tip  magenta=gold",
        fontsize=6.5,
        color=(0, 0, 0),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    pix.save(str(out_path))
    return True


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renders", action="store_true", help="write audit crops")
    args = parser.parse_args()

    gold_sha_before = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    document = json.loads((ARTIFACT / "document.json").read_text())
    artifact_geometry = json.loads((ARTIFACT / "geometry.json").read_text())
    gold = {
        json.loads(line)["token_id"]: json.loads(line)
        for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    }
    v2 = {}
    if V2_ROWS.exists():
        v2 = {
            json.loads(line)["label_id"]: json.loads(line)
            for line in V2_ROWS.read_text().splitlines()
            if line.strip()
        }
    artifact_by_id = {o["geometry_id"]: o for o in artifact_geometry["objects"]}
    page_summaries = {
        int(p["page_number"]): p
        for p in (artifact_geometry.get("metadata") or {}).get("page_summaries") or []
    }
    page_scales = detect_page_scales(document)

    pdf = fitz.open(PDF_PATH)
    pages = sorted({int(gold[t]["page"]) for t in AUDIT_TOKENS})
    replays: Dict[int, PageReplay] = {}
    fidelity: Dict[str, Any] = {}
    for page_number in pages:
        replay = PageReplay(pdf[page_number - 1], page_number, document, page_scales)
        replays[page_number] = replay
        artifact_ids = {
            o["geometry_id"] for o in artifact_geometry["objects"] if o["page_number"] == page_number
        }
        replay_ids = {o["geometry_id"] for o in replay.merged}
        fidelity[str(page_number)] = {
            "raw_drawing_count": len(replay.raw),
            "retained_by_cap": len(replay.kept),
            "dropped_by_cap": len(replay.raw) - len(replay.kept),
            "objects_after_merge": len(replay.merged),
            "artifact_objects": len(artifact_ids),
            "geometry_id_match": len(replay_ids & artifact_ids),
            "replay_faithful": replay_ids == artifact_ids,
            "cap_threshold": GX._DENSE_PAGE_CAP,
            "structural_min_span_pt": GX._STRUCTURAL_MIN_SPAN_PT,
            "artifact_page_summary": {
                k: page_summaries.get(page_number, {}).get(k)
                for k in (
                    "raw_drawing_count",
                    "retained_drawing_count",
                    "drawings_dropped_by_cap",
                    "drawings_excluded_tiny",
                    "zero_area_path_count",
                )
            },
        }

    rows: List[Dict[str, Any]] = []
    for token in AUDIT_TOKENS:
        g = gold[token]
        page_number = int(g["page"])
        replay = replays[page_number]
        bb = g["label_bbox"]
        lx, ly = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0

        near = _near_label_raw(replay, lx, ly, perp_max=14.0, min_len=15.0)
        trace = _leader_trace(replay, lx, ly)
        v2row = v2.get(token, {})
        verdict = VISUAL_VERDICTS[token]

        gold_gid = g.get("selected_geometry_id")
        gold_bbox = artifact_by_id.get(gold_gid, {}).get("bbox") if gold_gid else None

        retained_near = [h for h in near if h["retained_by_cap"]]
        dropped_near = [h for h in near if not h["retained_by_cap"]]
        tip_targets = trace.get("tip_targets") or []
        dropped_tip = [t for t in tip_targets if not t["retained_by_cap"]]
        retained_tip = [t for t in tip_targets if t["retained_by_cap"]]

        raw_found = bool(near) or bool(tip_targets)
        if not raw_found:
            normalization_status = "no_local_raw_primitive_found"
            filter_status = "n/a"
        elif retained_near or retained_tip:
            kinds = sorted(
                {
                    str(h["classified_kind"])
                    for h in (retained_near + retained_tip)
                    if h["classified_kind"]
                }
            )
            normalization_status = "local_primitive_retained_and_normalized"
            filter_status = f"retained_as_kind={','.join(kinds) or 'unknown'}"
        else:
            normalization_status = "raw_present_but_never_normalized"
            filter_status = "dropped_by_dense_page_cap"

        candidate_ids = g.get("candidate_geometry_ids") or []
        v2_ids = v2row.get("v2_candidate_ids") or []
        local_final_ids = {
            h["final_geometry_id"]
            for h in (retained_near + retained_tip)
            if h["final_geometry_id"]
        }
        in_baseline = sorted(local_final_ids & set(candidate_ids))
        in_v2 = sorted(local_final_ids & set(v2_ids))
        if not local_final_ids:
            candidate_status = "no_local_geometry_available_to_candidate_generation"
        elif in_v2 or in_baseline:
            candidate_status = "local_geometry_reached_candidates"
        else:
            candidate_status = "local_geometry_exists_but_excluded_from_candidates"

        if not trace["leader_present"]:
            leader_endpoint_status = "no_leader_near_label"
            target_status = "n/a"
        else:
            leader_endpoint_status = "leader_extracted_tip_resolved"
            if not tip_targets:
                target_status = "no_geometry_within_25pt_of_tip"
            elif retained_tip and any(
                t["classified_kind"] not in {"leader", "dimension"} for t in retained_tip
            ):
                target_status = "retained_non_leader_geometry_near_tip"
            elif retained_tip:
                target_status = "only_leader_or_dimension_retained_near_tip"
            else:
                target_status = "tip_geometry_exists_in_raw_but_all_dropped_by_cap"

        row = {
            "token_id": token,
            "page": page_number,
            "label": g.get("text"),
            "label_bbox": bb,
            "human_decision": g.get("decision"),
            "human_error_bucket": g.get("error_bucket"),
            "gold_geometry_id": gold_gid,
            "gold_geometry_bbox": gold_bbox,
            "visual_observation": verdict["visual_observation"],
            "member_is_visible": verdict["member_is_visible"],
            "raw_geometry_found": raw_found,
            "raw_geometry_ids": sorted(
                {h["final_geometry_id"] for h in near + tip_targets if h["final_geometry_id"]}
            ),
            "raw_geometry_types": sorted(
                {t for h in near + tip_targets for t in (h.get("item_types") or [])}
            ),
            "raw_near_label_count": len(near),
            "raw_near_label_retained": len(retained_near),
            "raw_near_label_dropped_by_cap": len(dropped_near),
            "raw_near_tip_count": len(tip_targets),
            "raw_near_tip_retained": len(retained_tip),
            "raw_near_tip_dropped_by_cap": len(dropped_tip),
            "normalization_status": normalization_status,
            "filter_status": filter_status,
            "candidate_status": candidate_status,
            "baseline_candidate_hit_ids": in_baseline,
            "v2_candidate_hit_ids": in_v2,
            "leader_present": trace["leader_present"],
            "leader_endpoint_status": leader_endpoint_status,
            "target_geometry_status": target_status,
            "primary_failure_class": verdict["primary_failure_class"],
            "recoverability": verdict["recoverability"],
            "v2_retrieval_mechanism": v2row.get("retrieval_mechanism"),
            "v2_proxy_local_coverage": v2row.get("proxy_local_coverage_v2"),
            "v2_proxy_rejected_by_visual_qa": bool(
                v2row.get("proxy_local_coverage_v2")
                and verdict["primary_failure_class"] != "OTHER"
                and g.get("decision") == "no_valid_member"
            ),
            "evidence_notes": verdict.get("notes", ""),
            "near_label_raw": near[:6],
            "leader_trace": trace,
        }
        assert row["primary_failure_class"] in FAILURE_CLASSES, row["primary_failure_class"]
        rows.append(row)

        if args.renders:
            _render_case(
                pdf,
                replay,
                row,
                RENDER_DIR / f"{token}_p{page_number}.png",
            )

    OUT.mkdir(parents=True, exist_ok=True)
    audit_path = OUT / "extraction_audit.jsonl"
    with audit_path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(_strip(row)) + "\n")

    distribution = Counter(r["primary_failure_class"] for r in rows)
    recoverability = Counter(r["recoverability"] for r in rows)
    convention_scan = {
        str(page_number): _page_convention_scan(
            replays[page_number],
            [g for g in gold.values() if int(g["page"]) == page_number],
        )
        for page_number in pages
    }

    summary = {
        "document_id": DOC_ID,
        "pages": pages,
        "n_cases": len(rows),
        "gold_sha256": gold_sha_before,
        "replay_fidelity": fidelity,
        "page_convention_scan": convention_scan,
        "failure_distribution": dict(distribution),
        "recoverability_distribution": dict(recoverability),
        "raw_present_but_dropped_by_cap": sum(
            1 for r in rows if r["filter_status"] == "dropped_by_dense_page_cap"
        ),
        "retained_but_misclassified": sum(
            1
            for r in rows
            if "dimension" in str(r["filter_status"]) or "leader" in str(r["filter_status"])
        ),
    }
    (OUT / "extraction_audit_summary.json").write_text(json.dumps(summary, indent=2))

    gold_sha_after = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if gold_sha_after != gold_sha_before:
        raise RuntimeError("gold_outcomes.jsonl changed during audit — abort")

    print(f"cases: {len(rows)}")
    print("page convention scan:", json.dumps(convention_scan, indent=2))
    print("replay fidelity:", json.dumps({k: v["replay_faithful"] for k, v in fidelity.items()}))
    print("failure distribution:", json.dumps(dict(distribution), indent=2))
    print("recoverability:", json.dumps(dict(recoverability), indent=2))
    print("gold sha256 unchanged:", gold_sha_after)
    print("wrote", audit_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
