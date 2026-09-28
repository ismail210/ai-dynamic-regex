#!/usr/bin/env python3
"""E2 — Classification cost experiment (R&D, measurement only).

Measures how many cap-surviving visible-member targets are made ineligible by
production classification helpers ``_looks_like_dimension`` /
``_looks_like_leader`` (and any subsequent symbol/eligibility rule).

Production helpers are called unchanged. Cap variants are diagnostic only;
production cap is not modified.

Usage (from backend/):
    python scripts/rd_geometry_integration/classification_cost_experiment.py
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
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
from services.engineering.models import GeometryKind  # noqa: E402

DOC_ID = "doc_0d910a43b4a021e3"
ARTIFACT = ROOT / "training" / "engineering_artifacts" / DOC_ID / "multimodal"
PDF_PATH = ROOT / "uploads" / "Burrville ES - ST.pdf"
OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
GOLD_PATH = OUT / "review_kit" / "gold_outcomes.jsonl"
E1_PATH = OUT / "cap_cost_results.jsonl"
AUDIT_PATH = OUT / "extraction_audit.jsonl"
V2_PATH = OUT / "v2_rows.jsonl"

PAGES = (8, 18, 24)
CAP_VARIANTS: List[Tuple[str, Optional[int]]] = [
    ("CAP_450", 450),
    ("CAP_NO_LIMIT", None),
]

_MEMBER_KINDS = {"line", "polyline", "rectangle", "arc"}
_CALLOUT_KINDS = {"leader", "dimension", "symbol"}
_DIGIT_RE = re.compile(r"\d+(\.\d+)?")


# ---------------------------------------------------------------------------
# Local geometry helpers (production untouched)
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


def _drawing_fingerprint(drawing: Dict[str, Any]) -> Tuple[Any, ...]:
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


def _structural_first_order(
    drawings: List[dict], *, page_width: float, page_height: float
) -> List[dict]:
    pool = [
        item
        for item in drawings
        if not GX._is_tiny_noise_drawing(item)
        and not GX._is_page_frame_drawing(item, page_width, page_height)
    ]
    scored = sorted(pool, key=GX._structural_keep_score, reverse=True)
    long_strokes = [
        item for item in scored if max(GX._drawing_wh(item)) >= GX._STRUCTURAL_MIN_SPAN_PT
    ]
    short_strokes = [
        item for item in scored if max(GX._drawing_wh(item)) < GX._STRUCTURAL_MIN_SPAN_PT
    ]
    return long_strokes + short_strokes


def _select_cap(
    drawings: List[dict], *, page_width: float, page_height: float, cap: Optional[int]
) -> List[dict]:
    if cap is None:
        return _structural_first_order(drawings, page_width=page_width, page_height=page_height)
    return GX._select_under_dense_cap(
        drawings,
        page_width=page_width,
        page_height=page_height,
        cap=cap,
        strategy="structural_first",
    )


def _build_items(drawing: Dict[str, Any]) -> Tuple[List[dict], List[List[float]], Optional[List[float]]]:
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
        return item_dicts, points, None
    return item_dicts, points, bbox


def _nearby_text_detail(
    center: List[float],
    page_number: int,
    document: Dict[str, Any],
    *,
    radius: float,
    line_grid: Dict[Tuple[int, int], List[dict]],
) -> Dict[str, Any]:
    """Mirror ``_nearby_text`` but also expose the winning line and distance."""
    best = ""
    best_d = radius
    best_line: Optional[dict] = None
    cx = int(center[0] // radius)
    cy = int(center[1] // radius)
    lines = [
        line
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for line in line_grid.get((cx + dx, cy + dy), [])
    ]
    for line in lines:
        if int(line.get("page_number") or 0) != page_number:
            continue
        c = line.get("center") or [0, 0]
        d = math.hypot(float(c[0]) - center[0], float(c[1]) - center[1])
        if d < best_d:
            best_d = d
            best = str(line.get("text") or "")
            best_line = line
    # Confirm production helper returns the same string
    prod = GX._nearby_text(
        center, page_number, document, radius=radius, line_grid=line_grid
    )
    return {
        "nearby_text": prod,
        "nearby_text_distance": None if not best else round(best_d, 2),
        "nearby_text_line_bbox": None if not best_line else best_line.get("bbox"),
        "nearby_text_matches_helper": prod == best,
        "digit_match": None
        if not prod
        else (None if not _DIGIT_RE.search(prod) else _DIGIT_RE.search(prod).group(0)),
    }


def _leader_predicate_detail(kind: GeometryKind, length: float, bbox: List[float]) -> Dict[str, Any]:
    """Expose each conjunct of production ``_looks_like_leader`` without changing it."""
    kind_ok = kind in {GeometryKind.LINE, GeometryKind.POLYLINE}
    w = abs(bbox[2] - bbox[0])
    h = abs(bbox[3] - bbox[1])
    length_ok = 8.0 <= length <= 72.0
    thin_ok = min(w, h) < 24.0
    fired = GX._looks_like_leader(kind, length, bbox)
    trigger = "NOT_REACHED"
    if not kind_ok:
        trigger = "kind_not_line_or_polyline"
    elif not length_ok:
        trigger = "length_outside_8_72" if fired is False else "TRIGGER_NOT_EXPOSED"
    elif not thin_ok:
        trigger = "min_bbox_span_ge_24"
    else:
        trigger = "kind_ok AND 8<=length<=72 AND min(w,h)<24"
    # Sanity: reconstructed predicate must match production
    reconstructed = bool(kind_ok and length_ok and thin_ok)
    return {
        "looks_like_leader": fired,
        "leader_kind_ok": kind_ok,
        "leader_length_ok": length_ok,
        "leader_thin_ok": thin_ok,
        "leader_bbox_w": round(w, 2),
        "leader_bbox_h": round(h, 2),
        "leader_trigger": trigger if reconstructed == fired else "TRIGGER_NOT_EXPOSED",
        "leader_predicate_matches_helper": reconstructed == fired,
    }


def _dimension_predicate_detail(
    kind: GeometryKind, length: float, nearby_text: str
) -> Dict[str, Any]:
    kind_ok = kind in {GeometryKind.LINE, GeometryKind.POLYLINE, GeometryKind.PATH}
    length_ok = length >= 12.0
    digit = _DIGIT_RE.search(nearby_text or "")
    digit_ok = bool(digit)
    fired = GX._looks_like_dimension(kind, length, nearby_text)
    reconstructed = bool(kind_ok and length_ok and digit_ok)
    if not kind_ok:
        trigger = "kind_not_line_polyline_or_path"
    elif not length_ok:
        trigger = "length_lt_12"
    elif not digit_ok:
        trigger = "nearby_text_has_no_digit"
    else:
        trigger = "kind_ok AND length>=12 AND nearby_text_contains_digit"
    return {
        "looks_like_dimension": fired,
        "dimension_kind_ok": kind_ok,
        "dimension_length_ok": length_ok,
        "dimension_digit_ok": digit_ok,
        "dimension_digit_match": None if not digit else digit.group(0),
        "dimension_trigger": trigger if reconstructed == fired else "TRIGGER_NOT_EXPOSED",
        "dimension_predicate_matches_helper": reconstructed == fired,
    }


def _classify_drawing(
    drawing: Dict[str, Any],
    *,
    page_number: int,
    document: Dict[str, Any],
    nearby_radius: float,
    line_grid: Dict[Tuple[int, int], List[dict]],
    ordinal: int,
) -> Optional[Dict[str, Any]]:
    item_dicts, points, bbox = _build_items(drawing)
    if bbox is None:
        return None
    base_kind = GX._classify_path(item_dicts, drawing.get("rect"))
    length = (
        GX._length_of_segments(points)
        if len(points) >= 2
        else round(math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]), 3)
    )
    center = [round((bbox[0] + bbox[2]) / 2.0, 2), round((bbox[1] + bbox[3]) / 2.0, 2)]
    text_detail = _nearby_text_detail(
        center, page_number, document, radius=nearby_radius, line_grid=line_grid
    )
    nearby = text_detail["nearby_text"]

    leader_detail = _leader_predicate_detail(base_kind, length, bbox)
    dimension_detail = _dimension_predicate_detail(base_kind, length, nearby)

    kind = base_kind
    applied = None
    # Exact production order
    if GX._looks_like_leader(kind, length, bbox):
        kind = GeometryKind.LEADER
        applied = "looks_like_leader"
    elif GX._looks_like_dimension(kind, length, nearby):
        kind = GeometryKind.DIMENSION
        applied = "looks_like_dimension"

    width = round(abs(bbox[2] - bbox[0]), 3)
    height = round(abs(bbox[3] - bbox[1]), 3)
    area = round(width * height, 3)
    symbol_reclass = False
    if kind in {GeometryKind.RECTANGLE, GeometryKind.CIRCLE} and area < 400:
        kind = GeometryKind.SYMBOL
        applied = "small_closed_shape_to_symbol"
        symbol_reclass = True

    eligible = kind.value in _MEMBER_KINDS
    return {
        "geometry_id": GX._gid(page_number, ordinal, bbox, kind.value),
        "bbox": bbox,
        "center": center,
        "length": length,
        "width": width,
        "height": height,
        "area": area,
        "n_items": len(item_dicts),
        "n_points": len(points),
        "base_kind": base_kind.value,
        "classification": kind.value,
        "reclassified_by": applied,
        "looks_like_leader": leader_detail["looks_like_leader"],
        "looks_like_dimension": dimension_detail["looks_like_dimension"],
        "symbol_reclass": symbol_reclass,
        "final_geometry_eligible": eligible,
        "candidate_available": eligible,  # extraction-stage eligibility
        "leader_detail": leader_detail,
        "dimension_detail": dimension_detail,
        "text_detail": text_detail,
        "both_predicates_true": (
            leader_detail["looks_like_leader"] and dimension_detail["looks_like_dimension"]
        ),
        "leader_took_precedence": (
            leader_detail["looks_like_leader"]
            and dimension_detail["looks_like_dimension"]
            and applied == "looks_like_leader"
        ),
    }


def _primary_stage(
    *,
    raw_present: bool,
    cap_survives: Optional[bool],
    classification: Optional[str],
    looks_like_dimension: Optional[bool],
    looks_like_leader: Optional[bool],
    eligible: Optional[bool],
    human_decision: str,
    in_candidates: Optional[bool],
) -> str:
    if human_decision == "ambiguous":
        return "AMBIGUOUS"
    if not raw_present:
        return "OTHER"
    if cap_survives is False:
        return "CAP_LOSS"
    if classification == "NOT_REACHED" or classification is None:
        return "OTHER_FILTER"  # degenerate / dropped before classify
    if not eligible:
        # Production applies leader before dimension; attribute to the applied cause.
        if classification == "dimension" and looks_like_dimension:
            return "DIMENSION_CLASSIFICATION"
        if classification == "leader" and looks_like_leader:
            return "LEADER_CLASSIFICATION"
        if classification == "symbol":
            return "OTHER_FILTER"
        return "OTHER_FILTER"
    # Eligible after extraction/classification
    if in_candidates is False:
        return "RETRIEVAL_STAGE_ONLY"
    if in_candidates is True:
        return "OTHER"  # survives; not a failure (control / available)
    # Eligible but retrieval not evaluated (no gold gid / miss without inventing)
    return "OTHER"


# ---------------------------------------------------------------------------
def main() -> int:
    gold_sha_before = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    document = json.loads((ARTIFACT / "document.json").read_text())
    gold_rows = [
        json.loads(line) for line in GOLD_PATH.read_text().splitlines() if line.strip()
    ]
    gold_by = {r["token_id"]: r for r in gold_rows}
    e1_audited = {
        r["token_id"]: r
        for r in (json.loads(line) for line in E1_PATH.read_text().splitlines() if line.strip())
        if r.get("population") == "audited_21"
    }
    e1_associated = {
        r["token_id"]: r
        for r in (json.loads(line) for line in E1_PATH.read_text().splitlines() if line.strip())
        if r.get("population") == "associated"
    }
    audit_by = {
        json.loads(line)["token_id"]: json.loads(line)
        for line in AUDIT_PATH.read_text().splitlines()
        if line.strip()
    }
    v2_by = {}
    if V2_PATH.exists():
        v2_by = {
            json.loads(line)["label_id"]: json.loads(line)
            for line in V2_PATH.read_text().splitlines()
            if line.strip()
        }
    page_scales = detect_page_scales(document)
    pdf = fitz.open(PDF_PATH)

    # ---- per-page raw + caps ----
    page_state: Dict[int, Dict[str, Any]] = {}
    for page_number in PAGES:
        page = pdf[page_number - 1]
        raw = page.get_drawings() or []
        pw, ph = float(page.rect.width), float(page.rect.height)
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

        fp_index = {_drawing_fingerprint(d): d for d in raw}
        kept_by: Dict[str, List[dict]] = {}
        kept_ids: Dict[str, set] = {}
        classified_by: Dict[str, Dict[int, Dict[str, Any]]] = {}
        for name, cap in CAP_VARIANTS:
            kept = _select_cap(raw, page_width=pw, page_height=ph, cap=cap)
            kept_by[name] = kept
            kept_ids[name] = {id(d) for d in kept}
            by_raw: Dict[int, Dict[str, Any]] = {}
            for i, drawing in enumerate(kept):
                obj = _classify_drawing(
                    drawing,
                    page_number=page_number,
                    document=document,
                    nearby_radius=nearby_radius,
                    line_grid=line_grid,
                    ordinal=i,
                )
                if obj is not None:
                    by_raw[id(drawing)] = obj
            classified_by[name] = by_raw

        page_state[page_number] = {
            "raw": raw,
            "fp_index": fp_index,
            "kept_ids": kept_ids,
            "classified_by": classified_by,
            "nearby_radius": nearby_radius,
            "line_grid": line_grid,
        }
        print(
            f"p{page_number}: raw={len(raw)} "
            + " ".join(f"{n}={len(kept_by[n])}" for n, _ in CAP_VARIANTS)
        )

    def resolve_drawing(token: str, page_number: int, e1_row: Optional[Dict[str, Any]]) -> Optional[dict]:
        if not e1_row or not e1_row.get("RAW_PRESENT") or not e1_row.get("target_fingerprint"):
            return None
        fp = tuple(e1_row["target_fingerprint"])
        return page_state[page_number]["fp_index"].get(fp)

    def evaluate(
        gold: Dict[str, Any],
        *,
        population: str,
        e1_row: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        token = gold["token_id"]
        page_number = int(gold["page"])
        state = page_state[page_number]
        drawing = resolve_drawing(token, page_number, e1_row)
        raw_present = drawing is not None

        # Candidate membership (retrieval stage), only when we have a concrete geometry id
        gold_gid = gold.get("selected_geometry_id")
        baseline_cands = set(gold.get("candidate_geometry_ids") or [])
        v2_cands = set((v2_by.get(token) or {}).get("v2_candidate_ids") or [])

        row: Dict[str, Any] = {
            "token_id": token,
            "page": page_number,
            "label": gold.get("text"),
            "population": population,
            "human_decision": gold.get("decision"),
            "human_error_bucket": gold.get("error_bucket"),
            "leader_required": bool(gold.get("leader_required")),
            "gold_selected_geometry_id": gold_gid,
            "raw_present": raw_present,
            "target_fingerprint": None if not e1_row else e1_row.get("target_fingerprint"),
            "target_path_length": None if not e1_row else e1_row.get("target_path_length"),
            "target_cap_rank": None if not e1_row else e1_row.get("target_cap_rank"),
            "cap_results": {},
            "audit_primary_failure": (audit_by.get(token) or {}).get("primary_failure_class"),
        }

        for name, _cap in CAP_VARIANTS:
            if not raw_present:
                row["cap_results"][name] = {
                    "raw_present": False,
                    "cap_survives": None,
                    "normalized_present": None,
                    "classification": "NOT_REACHED",
                    "looks_like_dimension": None,
                    "looks_like_leader": None,
                    "other_classification_flags": {},
                    "filtered_after_classification": None,
                    "final_geometry_eligible": None,
                    "candidate_available": None,
                    "primary_stage": "OTHER",
                }
                continue

            survives = id(drawing) in state["kept_ids"][name]
            if not survives:
                row["cap_results"][name] = {
                    "raw_present": True,
                    "cap_survives": False,
                    "normalized_present": False,
                    "classification": "NOT_REACHED",
                    "looks_like_dimension": None,
                    "looks_like_leader": None,
                    "other_classification_flags": {},
                    "filtered_after_classification": None,
                    "final_geometry_eligible": False,
                    "candidate_available": False,
                    "primary_stage": "CAP_LOSS",
                    "base_kind": None,
                    "reclassified_by": None,
                    "nearby_text": None,
                    "dimension_trigger": None,
                    "leader_trigger": None,
                    "geometry_id": None,
                }
                continue

            obj = state["classified_by"][name].get(id(drawing))
            if obj is None:
                row["cap_results"][name] = {
                    "raw_present": True,
                    "cap_survives": True,
                    "normalized_present": False,
                    "classification": "NOT_REACHED",
                    "looks_like_dimension": None,
                    "looks_like_leader": None,
                    "other_classification_flags": {"degenerate_after_cap": True},
                    "filtered_after_classification": True,
                    "final_geometry_eligible": False,
                    "candidate_available": False,
                    "primary_stage": "OTHER_FILTER",
                }
                continue

            gid = obj["geometry_id"]
            in_cands = None
            if gold_gid:
                # Associated control: is the gold geometry among baseline candidates?
                in_cands = gold_gid in baseline_cands or gid in baseline_cands or gid in v2_cands
            elif population == "audited_21" and obj["final_geometry_eligible"]:
                # Eligible audited miss: candidate lists may contain the geometry id
                # without that proving correct association. Prefer audit evidence for
                # RETRIEVAL_STAGE_ONLY when the audit already classified the case as
                # an extraction-complete retrieval miss.
                audit_fail = (audit_by.get(token) or {}).get("primary_failure_class")
                in_lists = gid in baseline_cands or gid in v2_cands
                if audit_fail == "EXTRACTED_BUT_RETRIEVAL_MISS":
                    in_cands = False  # eligible + prior audit says retrieval stage
                elif in_lists:
                    in_cands = True
                else:
                    in_cands = None

            primary = _primary_stage(
                raw_present=True,
                cap_survives=True,
                classification=obj["classification"],
                looks_like_dimension=obj["looks_like_dimension"],
                looks_like_leader=obj["looks_like_leader"],
                eligible=obj["final_geometry_eligible"],
                human_decision=str(gold.get("decision") or ""),
                in_candidates=in_cands,
            )
            # Ambiguous override
            if gold.get("decision") == "ambiguous":
                primary = "AMBIGUOUS"

            row["cap_results"][name] = {
                "raw_present": True,
                "cap_survives": True,
                "normalized_present": True,
                "classification": obj["classification"],
                "base_kind": obj["base_kind"],
                "reclassified_by": obj["reclassified_by"],
                "looks_like_dimension": obj["looks_like_dimension"],
                "looks_like_leader": obj["looks_like_leader"],
                "both_predicates_true": obj["both_predicates_true"],
                "leader_took_precedence": obj["leader_took_precedence"],
                "other_classification_flags": {
                    "symbol_reclass": obj["symbol_reclass"],
                    "base_kind": obj["base_kind"],
                },
                "filtered_after_classification": not obj["final_geometry_eligible"],
                "final_geometry_eligible": obj["final_geometry_eligible"],
                "candidate_available": obj["candidate_available"],
                "geometry_id": gid,
                "nearby_text": obj["text_detail"]["nearby_text"],
                "nearby_text_distance": obj["text_detail"]["nearby_text_distance"],
                "nearby_text_line_bbox": obj["text_detail"]["nearby_text_line_bbox"],
                "digit_match": obj["text_detail"]["digit_match"],
                "dimension_trigger": obj["dimension_detail"]["dimension_trigger"],
                "dimension_detail": obj["dimension_detail"],
                "leader_trigger": obj["leader_detail"]["leader_trigger"],
                "leader_detail": obj["leader_detail"],
                "length": obj["length"],
                "bbox": obj["bbox"],
                "n_points": obj["n_points"],
                "in_candidates": in_cands,
                "primary_stage": primary,
            }
        return row

    rows: List[Dict[str, Any]] = []

    # Population: audited 21
    for token, e1 in e1_audited.items():
        gold = gold_by[token]
        rows.append(evaluate(gold, population="audited_21", e1_row=e1))

    # Associated 8
    for gold in gold_rows:
        if gold.get("decision") != "associated" or int(gold["page"]) not in PAGES:
            continue
        e1 = e1_associated.get(gold["token_id"]) or e1_audited.get(gold["token_id"])
        rows.append(evaluate(gold, population="associated", e1_row=e1))

    # Ambiguous 2
    for gold in gold_rows:
        if gold.get("decision") != "ambiguous" or int(gold["page"]) not in PAGES:
            continue
        e1 = next(
            (
                r
                for r in (
                    json.loads(line)
                    for line in E1_PATH.read_text().splitlines()
                    if line.strip()
                )
                if r.get("token_id") == gold["token_id"] and r.get("population") == "ambiguous"
            ),
            e1_audited.get(gold["token_id"]),
        )
        rows.append(evaluate(gold, population="ambiguous", e1_row=e1))

    # ---- p8 convention scan: all gold labels' nearest on-segment stroke ----
    p8_scan: List[Dict[str, Any]] = []
    state8 = page_state[8]
    raw8 = state8["raw"]
    for gold in gold_rows:
        if int(gold["page"]) != 8:
            continue
        bb = gold["label_bbox"]
        lx, ly = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
        best: Optional[Tuple[float, dict]] = None
        for drawing in raw8:
            rect = drawing.get("rect")
            if rect is None:
                continue
            if not (rect.x0 - 40 <= lx <= rect.x1 + 40 and rect.y0 - 40 <= ly <= rect.y1 + 40):
                continue
            dist, t = _nearest_on_path(lx, ly, drawing)
            if not (0.0 <= t <= 1.0) or dist > 40.0:
                continue
            if _path_length(drawing) < 25.0:
                continue
            if best is None or dist < best[0]:
                best = (dist, drawing)
        if best is None:
            p8_scan.append(
                {
                    "token_id": gold["token_id"],
                    "label": gold.get("text"),
                    "decision": gold.get("decision"),
                    "raw_present": False,
                }
            )
            continue
        dist, drawing = best
        survives_450 = id(drawing) in state8["kept_ids"]["CAP_450"]
        obj = state8["classified_by"]["CAP_450"].get(id(drawing)) if survives_450 else None
        p8_scan.append(
            {
                "token_id": gold["token_id"],
                "label": gold.get("text"),
                "decision": gold.get("decision"),
                "raw_present": True,
                "perp_distance": round(dist, 2),
                "path_length": round(_path_length(drawing), 2),
                "cap_survives_450": survives_450,
                "classification": None if not obj else obj["classification"],
                "looks_like_dimension": None if not obj else obj["looks_like_dimension"],
                "looks_like_leader": None if not obj else obj["looks_like_leader"],
                "nearby_text": None if not obj else obj["text_detail"]["nearby_text"],
                "digit_match": None if not obj else obj["text_detail"]["digit_match"],
                "dimension_trigger": None if not obj else obj["dimension_detail"]["dimension_trigger"],
                "eligible": None if not obj else obj["final_geometry_eligible"],
            }
        )

    def funnel(population: str, cap_name: str) -> Dict[str, Any]:
        subset = [r for r in rows if r["population"] == population]
        raw_n = sum(1 for r in subset if r["raw_present"])
        cap_yes = [
            r for r in subset if r["cap_results"][cap_name].get("cap_survives") is True
        ]
        eligible = [
            r for r in cap_yes if r["cap_results"][cap_name].get("final_geometry_eligible")
        ]
        attr = Counter(r["cap_results"][cap_name]["primary_stage"] for r in subset)
        dim = sum(
            1
            for r in cap_yes
            if r["cap_results"][cap_name]["primary_stage"] == "DIMENSION_CLASSIFICATION"
        )
        lead = sum(
            1
            for r in cap_yes
            if r["cap_results"][cap_name]["primary_stage"] == "LEADER_CLASSIFICATION"
        )
        other_f = sum(
            1
            for r in cap_yes
            if r["cap_results"][cap_name]["primary_stage"] == "OTHER_FILTER"
        )
        retrieval = sum(
            1
            for r in subset
            if r["cap_results"][cap_name]["primary_stage"] == "RETRIEVAL_STAGE_ONLY"
        )
        cap_loss = sum(
            1 for r in subset if r["cap_results"][cap_name]["primary_stage"] == "CAP_LOSS"
        )
        return {
            "n_cases": len(subset),
            "raw_present": raw_n,
            "survive_cap": len(cap_yes),
            "lost_at_cap": cap_loss,
            "classification_survival_rate": round(100.0 * len(eligible) / len(cap_yes), 1)
            if cap_yes
            else None,
            "survive_classification_eligible": len(eligible),
            "lost_to_dimension": dim,
            "lost_to_leader": lead,
            "lost_to_other_filter": other_f,
            "retrieval_stage_only": retrieval,
            "primary_stage_counts": dict(attr),
            "dimension_flag_true_among_cap_survivors": sum(
                1 for r in cap_yes if r["cap_results"][cap_name].get("looks_like_dimension")
            ),
            "leader_flag_true_among_cap_survivors": sum(
                1 for r in cap_yes if r["cap_results"][cap_name].get("looks_like_leader")
            ),
            "both_flags_true_among_cap_survivors": sum(
                1 for r in cap_yes if r["cap_results"][cap_name].get("both_predicates_true")
            ),
        }

    p8_outcomes = Counter()
    for s in p8_scan:
        if not s.get("raw_present"):
            p8_outcomes["no_stroke"] += 1
        elif not s.get("cap_survives_450"):
            p8_outcomes["cap_dropped"] += 1
        elif s.get("classification") == "dimension":
            p8_outcomes["retained_dimension"] += 1
        elif s.get("classification") == "leader":
            p8_outcomes["retained_leader"] += 1
        elif s.get("eligible"):
            p8_outcomes["retained_eligible"] += 1
        else:
            p8_outcomes["retained_other"] += 1

    # Highlight W30X90
    w30 = next((r for r in rows if r["token_id"] == "token_p8_348"), None)

    summary = {
        "document_id": DOC_ID,
        "pages": list(PAGES),
        "gold_sha256": gold_sha_before,
        "experimental_variable": "cap_condition_only_for_population_reach; classification_helpers_unchanged",
        "classification_predicates": {
            "looks_like_leader": "kind in {LINE,POLYLINE} AND 8<=length<=72 AND min(w,h)<24",
            "looks_like_dimension": "kind in {LINE,POLYLINE,PATH} AND length>=12 AND nearby_text matches /\\d+(\\.\\d+)?/",
            "application_order": "leader first, else dimension, then small rectangle/circle -> symbol",
            "nearby_text": "nearest document line center within nearby_radius of geometry center",
        },
        "funnels": {
            "audited_21": {
                "CAP_450": funnel("audited_21", "CAP_450"),
                "CAP_NO_LIMIT": funnel("audited_21", "CAP_NO_LIMIT"),
            },
            "associated_8": {
                "CAP_450": funnel("associated", "CAP_450"),
                "CAP_NO_LIMIT": funnel("associated", "CAP_NO_LIMIT"),
            },
            "ambiguous_2": {
                "CAP_450": funnel("ambiguous", "CAP_450"),
                "CAP_NO_LIMIT": funnel("ambiguous", "CAP_NO_LIMIT"),
            },
        },
        "p8_label_stroke_scan": {
            "labels_scanned": len(p8_scan),
            "outcomes_under_cap450": dict(p8_outcomes),
            "dimension_with_digit_from_own_labelish_text": sum(
                1
                for s in p8_scan
                if s.get("classification") == "dimension"
                and s.get("digit_match")
                and s.get("nearby_text")
            ),
        },
        "token_p8_348_w30x90": None
        if not w30
        else {
            "CAP_450": w30["cap_results"]["CAP_450"],
            "CAP_NO_LIMIT": w30["cap_results"]["CAP_NO_LIMIT"],
        },
        "n_jsonl_rows": len(rows),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    jsonl_path = OUT / "classification_cost_results.jsonl"
    with jsonl_path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
        # Append p8 scan as separate records for analysis (tagged)
        for s in p8_scan:
            fh.write(json.dumps({"record_type": "p8_label_stroke_scan", **s}) + "\n")
    (OUT / "classification_cost_summary.json").write_text(json.dumps(summary, indent=2))

    gold_sha_after = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if gold_sha_after != gold_sha_before:
        raise RuntimeError("gold changed during E2 — abort")

    print("\n=== AUDITED_21 FUNNELS ===")
    for cap in ("CAP_450", "CAP_NO_LIMIT"):
        f = summary["funnels"]["audited_21"][cap]
        print(json.dumps({cap: f}, indent=2))
    print("\np8 scan:", dict(p8_outcomes))
    if w30:
        print("\nW30X90 CAP_450:", json.dumps(w30["cap_results"]["CAP_450"], indent=2, default=str)[:1200])
    print("gold unchanged:", gold_sha_after)
    print("wrote", jsonl_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
