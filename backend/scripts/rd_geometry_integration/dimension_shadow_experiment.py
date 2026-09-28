#!/usr/bin/env python3
"""E3 — Member-vs-callout dimension shadow experiment (R&D, measurement only).

Shadow-tests whether ignoring numeric text that belongs to the candidate's own
annotation reduces false ``_looks_like_dimension`` flips on real member strokes,
without changing production classifiers.

Usage (from backend/):
    python scripts/rd_geometry_integration/dimension_shadow_experiment.py
    python scripts/rd_geometry_integration/dimension_shadow_experiment.py --renders
"""

from __future__ import annotations

import argparse
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
E2_PATH = OUT / "classification_cost_results.jsonl"
RENDER_DIR = OUT / "dimension_shadow_renders"

_DIGIT_RE = re.compile(r"\d+(\.\d+)?")
_MEMBER_KINDS = {"line", "polyline", "rectangle", "arc"}


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------
def bbox_intersects(a: Sequence[float], b: Sequence[float], *, pad: float = 0.0) -> bool:
    ax0, ay0, ax1, ay1 = map(float, a)
    bx0, by0, bx1, by1 = map(float, b)
    return not (
        ax1 + pad < bx0
        or bx1 + pad < ax0
        or ay1 + pad < by0
        or by1 + pad < ay0
    )


def bbox_iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax0, ay0, ax1, ay1 = map(float, a)
    bx0, by0, bx1, by1 = map(float, b)
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def strip_digits(text: str) -> str:
    return _DIGIT_RE.sub("", text or "")


def identify_own_label_lines(
    lines: Sequence[Dict[str, Any]],
    *,
    label_bbox: Sequence[float],
    label_text: str,
    page_number: int,
) -> List[Dict[str, Any]]:
    """Mark document lines that belong to the candidate annotation.

    Gold has no ``source_word_ids``. Ownership is demonstrated by:
    1. line text contains the gold label token text, or
    2. gold label center lies inside the line bbox AND the line is not a
       bare load/reaction callout (e.g. ``17K`` / ``29K``).

    Simple bbox intersection alone is insufficient — reaction loads often
    sit adjacent to and overlap the truncated gold label bbox.
    """
    own: List[Dict[str, Any]] = []
    label_norm = re.sub(r"\s+", "", (label_text or "").upper())
    cx = (float(label_bbox[0]) + float(label_bbox[2])) / 2.0
    cy = (float(label_bbox[1]) + float(label_bbox[3])) / 2.0
    bare_load = re.compile(r"^\s*\d+(\.\d+)?\s*K\s*$", re.I)
    for line in lines:
        if int(line.get("page_number") or 0) != page_number:
            continue
        lb = line.get("bbox")
        if not lb or len(lb) < 4:
            continue
        text = str(line.get("text") or "")
        text_norm = re.sub(r"\s+", "", text.upper())
        if bare_load.match(text.strip()):
            continue
        text_match = bool(label_norm) and label_norm in text_norm
        center_in_line = (
            float(lb[0]) <= cx <= float(lb[2]) and float(lb[1]) <= cy <= float(lb[3])
        )
        # Gold bbox largely contained in the annotation line bbox
        gold_inside = (
            float(lb[0]) <= float(label_bbox[0]) + 1.0
            and float(lb[1]) <= float(label_bbox[1]) + 1.0
            and float(lb[2]) >= float(label_bbox[2]) - 1.0
            and float(lb[3]) >= float(label_bbox[3]) - 1.0
        )
        if text_match or (center_in_line and (text_match or gold_inside)):
            own.append(line)
        elif gold_inside and not bare_load.match(text.strip()) and label_norm:
            # Full annotation line that frames the gold crop
            if label_norm[:4] in text_norm or label_norm in text_norm:
                own.append(line)
    # Deduplicate by object identity
    seen = set()
    uniq = []
    for line in own:
        if id(line) in seen:
            continue
        seen.add(id(line))
        uniq.append(line)
    return uniq


def collect_nearby_lines(
    center: Sequence[float],
    page_number: int,
    lines: Sequence[Dict[str, Any]],
    *,
    radius: float,
) -> List[Tuple[float, Dict[str, Any]]]:
    """All page lines with center distance < radius, sorted nearest-first."""
    cx, cy = float(center[0]), float(center[1])
    out: List[Tuple[float, Dict[str, Any]]] = []
    for line in lines:
        if int(line.get("page_number") or 0) != page_number:
            continue
        c = line.get("center") or [0, 0]
        d = math.hypot(float(c[0]) - cx, float(c[1]) - cy)
        if d < radius:
            out.append((d, line))
    out.sort(key=lambda item: item[0])
    return out


def classify_baseline(
    *,
    base_kind: GeometryKind,
    length: float,
    bbox: List[float],
    nearby_text: str,
) -> Dict[str, Any]:
    """Faithful production order: leader, else dimension, else symbol for small closed."""
    kind = base_kind
    reason = None
    leader = GX._looks_like_leader(kind, length, bbox)
    dimension = GX._looks_like_dimension(kind, length, nearby_text)
    if leader:
        kind = GeometryKind.LEADER
        reason = "looks_like_leader"
    elif dimension:
        kind = GeometryKind.DIMENSION
        reason = "looks_like_dimension"
    width = abs(bbox[2] - bbox[0])
    height = abs(bbox[3] - bbox[1])
    area = width * height
    if kind in {GeometryKind.RECTANGLE, GeometryKind.CIRCLE} and area < 400:
        kind = GeometryKind.SYMBOL
        reason = "small_closed_shape_to_symbol"
    return {
        "geometry_kind": kind.value,
        "is_dimension": kind == GeometryKind.DIMENSION,
        "is_leader": kind == GeometryKind.LEADER,
        "member_eligible": kind.value in _MEMBER_KINDS,
        "looks_like_leader": leader,
        "looks_like_dimension": dimension,
        "filter_reason": reason,
        "nearby_text_used": nearby_text,
    }


def classify_shadow_ignore_own_numbers(
    *,
    base_kind: GeometryKind,
    length: float,
    bbox: List[float],
    nearby_text: str,
    nearby_line: Optional[Dict[str, Any]],
    own_label_lines: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """V1: strip digits from nearby text when that text belongs to own annotation."""
    own_ids = {id(x) for x in own_label_lines}
    removed = None
    text = nearby_text or ""
    if nearby_line is not None and id(nearby_line) in own_ids:
        removed = text
        text = strip_digits(text)
    # Also: if nearby_text string equals an own-label line's text, strip digits
    elif any(str(o.get("text") or "") == nearby_text for o in own_label_lines):
        removed = text
        text = strip_digits(text)
    result = classify_baseline(
        base_kind=base_kind, length=length, bbox=bbox, nearby_text=text
    )
    result["removed_trigger_text"] = removed
    result["shadow_nearby_text"] = text
    result["trigger_source"] = (
        "own_label_digits_stripped"
        if removed is not None
        else "unchanged_non_own_or_empty"
    )
    return result


def classify_shadow_ignore_own_label(
    *,
    base_kind: GeometryKind,
    length: float,
    bbox: List[float],
    nearby_ranked: Sequence[Tuple[float, Dict[str, Any]]],
    own_label_lines: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """V2: exclude entire own-label lines; use next nearest non-own line."""
    own_ids = {id(x) for x in own_label_lines}
    removed = None
    chosen_text = ""
    for _d, line in nearby_ranked:
        if id(line) in own_ids:
            if removed is None:
                removed = str(line.get("text") or "")
            continue
        chosen_text = str(line.get("text") or "")
        break
    result = classify_baseline(
        base_kind=base_kind, length=length, bbox=bbox, nearby_text=chosen_text
    )
    result["removed_trigger_text"] = removed
    result["shadow_nearby_text"] = chosen_text
    result["trigger_source"] = (
        "own_label_line_excluded"
        if removed is not None
        else "no_own_label_in_nearby"
    )
    return result


def classify_shadow_spatial_separation(
    *,
    base_kind: GeometryKind,
    length: float,
    bbox: List[float],
    nearby_ranked: Sequence[Tuple[float, Dict[str, Any]]],
    own_label_bbox_union: Optional[Sequence[float]],
) -> Dict[str, Any]:
    """V3: digit-bearing lines count only if they do not intersect own-label bbox.

    No invented distance threshold: separation = no bbox intersection with the
    own-label annotation region (union of gold label_bbox and overlapping lines).
    """
    if own_label_bbox_union is None:
        # No own-label region → cannot apply; fall back to production nearest text
        nearest = nearby_ranked[0][1] if nearby_ranked else None
        text = "" if nearest is None else str(nearest.get("text") or "")
        result = classify_baseline(
            base_kind=base_kind, length=length, bbox=bbox, nearby_text=text
        )
        result["removed_trigger_text"] = None
        result["shadow_nearby_text"] = text
        result["trigger_source"] = "no_own_label_bbox_fallback_production"
        result["variant_evaluable"] = False
        return result

    chosen_text = ""
    skipped = []
    for _d, line in nearby_ranked:
        lb = line.get("bbox")
        text = str(line.get("text") or "")
        if not _DIGIT_RE.search(text):
            # non-digit lines don't create dimension evidence; skip for digit hunt
            # but if we never find a digit line, nearby stays empty for dim check
            continue
        if lb and bbox_intersects(own_label_bbox_union, lb):
            skipped.append(text)
            continue
        chosen_text = text
        break
    result = classify_baseline(
        base_kind=base_kind, length=length, bbox=bbox, nearby_text=chosen_text
    )
    result["removed_trigger_text"] = skipped[0] if skipped else None
    result["shadow_nearby_text"] = chosen_text
    result["trigger_source"] = "digit_lines_outside_own_label_bbox"
    result["variant_evaluable"] = True
    result["skipped_overlapping_digit_texts"] = skipped
    return result


def union_bboxes(bboxes: Sequence[Sequence[float]]) -> Optional[List[float]]:
    if not bboxes:
        return None
    return [
        min(float(b[0]) for b in bboxes),
        min(float(b[1]) for b in bboxes),
        max(float(b[2]) for b in bboxes),
        max(float(b[3]) for b in bboxes),
    ]


def classify_change(
    *,
    cap_survives: bool,
    baseline: Dict[str, Any],
    shadow: Dict[str, Any],
    attribution: str,
    human_decision: str,
) -> str:
    if not cap_survives:
        return "NOT_APPLICABLE_CAP_LOSS"
    if human_decision == "ambiguous":
        if baseline.get("is_dimension") == shadow.get("is_dimension") and baseline.get(
            "member_eligible"
        ) == shadow.get("member_eligible"):
            return "NO_CHANGE"
        return "AMBIGUOUS_CHANGE"
    b_dim = bool(baseline.get("is_dimension"))
    s_dim = bool(shadow.get("is_dimension"))
    b_el = bool(baseline.get("member_eligible"))
    s_el = bool(shadow.get("member_eligible"))
    if b_dim == s_dim and b_el == s_el:
        if b_dim:
            return "DIMENSION_PRESERVED"
        return "NO_CHANGE"
    if b_dim and not s_dim and s_el and not b_el:
        if attribution == "DIMENSION_GENUINE":
            return "FALSE_MEMBER_RECOVERY"
        if attribution in {
            "DIMENSION_OWN_LABEL_CONTAMINATION",
            "DIMENSION_UNRELATED_NEARBY_TEXT",
        }:
            return "MEMBER_RECOVERED"
        return "AMBIGUOUS_CHANGE"
    if not b_dim and s_dim:
        return "FALSE_DIMENSION_RECOVERY"
    if b_el and not s_el:
        return "AMBIGUOUS_CHANGE"
    return "INSUFFICIENT_EVIDENCE"


def attribute_dimension_loss(
    *,
    nearby_text: str,
    nearby_line: Optional[Dict[str, Any]],
    own_label_lines: Sequence[Dict[str, Any]],
    is_dimension: bool,
    is_leader: bool,
    member_eligible: bool,
    human_decision: str,
    e2_primary: Optional[str],
) -> str:
    if human_decision == "ambiguous":
        return "AMBIGUOUS"
    if is_leader:
        return "LEADER"
    if e2_primary == "RETRIEVAL_STAGE_ONLY" or (
        member_eligible and e2_primary == "RETRIEVAL_STAGE_ONLY"
    ):
        return "RETRIEVAL_STAGE"
    if member_eligible:
        return "UNKNOWN"  # eligible — not a classification loss
    if not is_dimension:
        return "OTHER_FILTER"
    own_ids = {id(x) for x in own_label_lines}
    if nearby_line is not None and id(nearby_line) in own_ids:
        return "DIMENSION_OWN_LABEL_CONTAMINATION"
    if any(str(o.get("text") or "") == nearby_text for o in own_label_lines):
        return "DIMENSION_OWN_LABEL_CONTAMINATION"
    # Schedule/table digit that is not the member label — treat as genuine callout evidence
    # for control purposes when text looks like a fraction/dimension fragment.
    if nearby_text and _DIGIT_RE.search(nearby_text):
        # Own-label contamination already handled; remaining digits are unrelated nearby.
        # Whether they are "genuine dimension" vs "unrelated" is evidence-based:
        # fraction-like (a/b) or length-ish with " → lean genuine; load-like *K → unrelated.
        t = nearby_text.strip()
        if re.search(r"\d+\s*/\s*\d+", t) or '"' in t or "'" in t:
            return "DIMENSION_GENUINE"
        if re.search(r"\d+\s*K\b", t, re.I):
            return "DIMENSION_UNRELATED_NEARBY_TEXT"
        return "DIMENSION_UNRELATED_NEARBY_TEXT"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Drawing / page replay (mirrors E1/E2; production helpers read-only)
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
    long_s = [i for i in scored if max(GX._drawing_wh(i)) >= GX._STRUCTURAL_MIN_SPAN_PT]
    short_s = [i for i in scored if max(GX._drawing_wh(i)) < GX._STRUCTURAL_MIN_SPAN_PT]
    return long_s + short_s


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


def _build_geometry(drawing: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    base_kind = GX._classify_path(item_dicts, rect)
    length = (
        GX._length_of_segments(points)
        if len(points) >= 2
        else round(math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]), 3)
    )
    center = [round((bbox[0] + bbox[2]) / 2.0, 2), round((bbox[1] + bbox[3]) / 2.0, 2)]
    return {
        "base_kind": base_kind,
        "bbox": bbox,
        "center": center,
        "length": length,
        "n_points": len(points),
    }


def _render_case(
    pdf: "fitz.Document",
    *,
    page_number: int,
    label_bbox: Sequence[float],
    geom_bbox: Optional[Sequence[float]],
    own_bboxes: Sequence[Sequence[float]],
    trigger_bbox: Optional[Sequence[float]],
    excluded_bboxes: Sequence[Sequence[float]],
    out_path: Path,
    caption: str,
    pad: float = 120.0,
    zoom: float = 2.2,
) -> None:
    page = pdf[page_number - 1]
    if geom_bbox:
        page.draw_rect(fitz.Rect(geom_bbox), color=(0.05, 0.55, 0.15), width=1.6)
    page.draw_rect(fitz.Rect(label_bbox), color=(0.1, 0.35, 0.9), width=1.6)
    for bb in own_bboxes:
        page.draw_rect(fitz.Rect(bb), color=(0.85, 0.55, 0.05), width=1.2, dashes="[2 2]")
    if trigger_bbox:
        page.draw_rect(fitz.Rect(trigger_bbox), color=(0.85, 0.1, 0.1), width=1.6)
    for bb in excluded_bboxes:
        page.draw_rect(fitz.Rect(bb), color=(0.55, 0.15, 0.75), width=1.2, dashes="[1 2]")
    cx = (float(label_bbox[0]) + float(label_bbox[2])) / 2.0
    cy = (float(label_bbox[1]) + float(label_bbox[3])) / 2.0
    clip = fitz.Rect(cx - pad, cy - pad, cx + pad, cy + pad)
    page.insert_text(
        fitz.Point(clip.x0 + 4, clip.y0 + 10),
        caption[:110],
        fontsize=6.5,
        color=(0, 0, 0),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    pix.save(str(out_path))


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renders", action="store_true")
    args = parser.parse_args()

    gold_sha_before = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    extractor_sha = hashlib.sha256(
        (ROOT / "services" / "engineering" / "geometry_extractor.py").read_bytes()
    ).hexdigest()

    document = json.loads((ARTIFACT / "document.json").read_text())
    all_lines = document.get("lines") or []
    gold_by = {
        json.loads(line)["token_id"]: json.loads(line)
        for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    }
    e1_audited = {
        r["token_id"]: r
        for r in (json.loads(line) for line in E1_PATH.read_text().splitlines() if line.strip())
        if r.get("population") == "audited_21"
    }
    e2_audited = {
        r["token_id"]: r
        for r in (json.loads(line) for line in E2_PATH.read_text().splitlines() if line.strip())
        if r.get("population") == "audited_21" and not r.get("record_type")
    }
    assert set(e1_audited) == set(e2_audited), "E1/E2 audited populations diverge"
    assert len(e1_audited) == 21

    page_scales = detect_page_scales(document)
    pdf = fitz.open(PDF_PATH)
    pages = sorted({int(gold_by[t]["page"]) for t in e1_audited})

    page_state: Dict[int, Dict[str, Any]] = {}
    for page_number in pages:
        page = pdf[page_number - 1]
        raw = page.get_drawings() or []
        pw, ph = float(page.rect.width), float(page.rect.height)
        kept = _select_cap(raw, page_width=pw, page_height=ph, cap=450)
        kept_nl = _select_cap(raw, page_width=pw, page_height=ph, cap=None)
        resolved = resolve_page_scale(document, page_number, page_scales=page_scales)
        page_scale = (
            page_scales.get(page_number) if resolved.get("scale_reason") == "page_scale" else None
        )
        radius = association_radius_pdf_points(page_scale) * (48.0 / 160.0)
        nearby_radius = max(24.0, min(96.0, radius))
        page_state[page_number] = {
            "raw": raw,
            "fp_index": {_drawing_fingerprint(d): d for d in raw},
            "kept_450": {id(d) for d in kept},
            "kept_nl": {id(d) for d in kept_nl},
            "nearby_radius": nearby_radius,
        }
        print(f"p{page_number}: raw={len(raw)} cap450={len(kept)} radius={nearby_radius}")

    rows: List[Dict[str, Any]] = []
    render_specs: List[Dict[str, Any]] = []

    for token in sorted(e1_audited.keys(), key=lambda t: (gold_by[t]["page"], t)):
        gold = gold_by[token]
        e1 = e1_audited[token]
        e2 = e2_audited[token]
        page_number = int(gold["page"])
        state = page_state[page_number]
        label_bbox = gold["label_bbox"]
        label_text = str(gold.get("text") or "")

        drawing = None
        if e1.get("RAW_PRESENT") and e1.get("target_fingerprint"):
            drawing = state["fp_index"].get(tuple(e1["target_fingerprint"]))
        raw_present = drawing is not None
        cap_survives = bool(raw_present and id(drawing) in state["kept_450"])

        own_lines = identify_own_label_lines(
            all_lines,
            label_bbox=label_bbox,
            label_text=label_text,
            page_number=page_number,
        )
        own_bboxes = [ln["bbox"] for ln in own_lines if ln.get("bbox")]
        own_union = union_bboxes([label_bbox, *own_bboxes])

        row: Dict[str, Any] = {
            "token_id": token,
            "page": page_number,
            "label": label_text,
            "label_bbox": label_bbox,
            "human_decision": gold.get("decision"),
            "human_error_bucket": gold.get("error_bucket"),
            "e2_primary_stage_cap450": e2["cap_results"]["CAP_450"].get("primary_stage"),
            "raw_present": raw_present,
            "cap_survives": cap_survives,
            "target_fingerprint": e1.get("target_fingerprint"),
            "own_label_line_texts": [str(ln.get("text") or "") for ln in own_lines],
            "own_label_identification": "text_contains_gold_label_or_gold_framed_by_annotation_line; bare_load_Kx_excluded; no source_word_ids",
            "variants": {},
        }

        if not raw_present or not cap_survives:
            for name in ("V0_production", "V1_ignore_own_numbers", "V2_exclude_own_label", "V3_spatial_separation"):
                row["variants"][name] = {
                    "is_dimension": None,
                    "is_leader": None,
                    "member_eligible": None,
                    "change_class": "NOT_APPLICABLE_CAP_LOSS",
                }
            row["attribution"] = "NOT_APPLICABLE_CAP_LOSS"
            row["change_class"] = {
                "V1_ignore_own_numbers": "NOT_APPLICABLE_CAP_LOSS",
                "V2_exclude_own_label": "NOT_APPLICABLE_CAP_LOSS",
                "V3_spatial_separation": "NOT_APPLICABLE_CAP_LOSS",
            }
            rows.append(row)
            continue

        geom = _build_geometry(drawing)
        assert geom is not None
        center = geom["center"]
        nearby_radius = state["nearby_radius"]
        ranked = collect_nearby_lines(
            center, page_number, all_lines, radius=nearby_radius
        )
        # Production nearby text (exact helper)
        line_grid: Dict[Tuple[int, int], List[dict]] = {}
        for line in all_lines:
            if int(line.get("page_number") or 0) != page_number:
                continue
            c = line.get("center") or [0, 0]
            key = (int(float(c[0]) // nearby_radius), int(float(c[1]) // nearby_radius))
            line_grid.setdefault(key, []).append(line)
        prod_text = GX._nearby_text(
            center, page_number, document, radius=nearby_radius, line_grid=line_grid
        )
        # Identify which line object produced that text (nearest matching)
        nearby_line = None
        for _d, line in ranked:
            if str(line.get("text") or "") == prod_text:
                nearby_line = line
                break

        v0 = classify_baseline(
            base_kind=geom["base_kind"],
            length=geom["length"],
            bbox=geom["bbox"],
            nearby_text=prod_text,
        )
        v0["trigger_text"] = prod_text
        v0["trigger_bbox"] = None if nearby_line is None else nearby_line.get("bbox")
        v0["trigger_distance"] = None if not ranked else round(ranked[0][0], 2)

        attribution = attribute_dimension_loss(
            nearby_text=prod_text,
            nearby_line=nearby_line,
            own_label_lines=own_lines,
            is_dimension=v0["is_dimension"],
            is_leader=v0["is_leader"],
            member_eligible=v0["member_eligible"],
            human_decision=str(gold.get("decision") or ""),
            e2_primary=e2["cap_results"]["CAP_450"].get("primary_stage"),
        )
        # Eligible survivors: refine retrieval attribution from E2
        if v0["member_eligible"] and e2["cap_results"]["CAP_450"].get("primary_stage") == "RETRIEVAL_STAGE_ONLY":
            attribution = "RETRIEVAL_STAGE"
        elif v0["member_eligible"]:
            attribution = "UNKNOWN"

        v1 = classify_shadow_ignore_own_numbers(
            base_kind=geom["base_kind"],
            length=geom["length"],
            bbox=geom["bbox"],
            nearby_text=prod_text,
            nearby_line=nearby_line,
            own_label_lines=own_lines,
        )
        v2 = classify_shadow_ignore_own_label(
            base_kind=geom["base_kind"],
            length=geom["length"],
            bbox=geom["bbox"],
            nearby_ranked=ranked,
            own_label_lines=own_lines,
        )
        v3 = classify_shadow_spatial_separation(
            base_kind=geom["base_kind"],
            length=geom["length"],
            bbox=geom["bbox"],
            nearby_ranked=ranked,
            own_label_bbox_union=own_union,
        )

        row["normalized_present"] = True
        row["geometry_bbox"] = geom["bbox"]
        row["geometry_length"] = geom["length"]
        row["base_kind"] = geom["base_kind"].value
        row["attribution"] = attribution
        row["production_nearby_text"] = prod_text
        row["production_nearby_line_bbox"] = v0["trigger_bbox"]
        row["variants"] = {
            "V0_production": v0,
            "V1_ignore_own_numbers": v1,
            "V2_exclude_own_label": v2,
            "V3_spatial_separation": v3,
        }
        row["change_class"] = {
            "V1_ignore_own_numbers": classify_change(
                cap_survives=True,
                baseline=v0,
                shadow=v1,
                attribution=attribution,
                human_decision=str(gold.get("decision") or ""),
            ),
            "V2_exclude_own_label": classify_change(
                cap_survives=True,
                baseline=v0,
                shadow=v2,
                attribution=attribution,
                human_decision=str(gold.get("decision") or ""),
            ),
            "V3_spatial_separation": classify_change(
                cap_survives=True,
                baseline=v0,
                shadow=v3,
                attribution=attribution,
                human_decision=str(gold.get("decision") or ""),
            ),
        }
        rows.append(row)

        # Collect render candidates
        if token in {
            "token_p8_348",
            "token_p8_337",
            "token_p8_381",
            "token_p8_430",
            "token_p8_332",
            "token_p18_1143",
            "token_p8_367",
        } or row["change_class"]["V1_ignore_own_numbers"] in {
            "MEMBER_RECOVERED",
            "FALSE_MEMBER_RECOVERY",
            "AMBIGUOUS_CHANGE",
        }:
            render_specs.append(
                {
                    "token_id": token,
                    "page": page_number,
                    "label_bbox": label_bbox,
                    "geom_bbox": geom["bbox"],
                    "own_bboxes": own_bboxes,
                    "trigger_bbox": v0["trigger_bbox"],
                    "excluded_bboxes": own_bboxes,
                    "caption": (
                        f"{token} {label_text} V0={v0['geometry_kind']} "
                        f"trig={prod_text!r} V1={v1['geometry_kind']} "
                        f"chg={row['change_class']['V1_ignore_own_numbers']}"
                    ),
                }
            )

    # ---- summary metrics ----
    survivors = [r for r in rows if r["cap_survives"]]
    cap_loss = [r for r in rows if not r["cap_survives"]]

    def variant_metrics(vname: str) -> Dict[str, Any]:
        dims = sum(
            1
            for r in survivors
            if r["variants"][vname].get("is_dimension")
        )
        elig = sum(
            1
            for r in survivors
            if r["variants"][vname].get("member_eligible")
        )
        leaders = sum(
            1 for r in survivors if r["variants"][vname].get("is_leader")
        )
        if vname == "V0_production":
            return {
                "dimension": dims,
                "leader": leaders,
                "member_eligible": elig,
                "recovered_members": 0,
                "dimension_to_member_flips": 0,
                "member_to_dimension_flips": 0,
                "ambiguous_changes": 0,
                "insufficient_evidence": 0,
                "change_classes": {},
            }
        classes = Counter(r["change_class"][vname] for r in survivors)
        return {
            "dimension": dims,
            "leader": leaders,
            "member_eligible": elig,
            "recovered_members": classes.get("MEMBER_RECOVERED", 0),
            "dimension_to_member_flips": classes.get("MEMBER_RECOVERED", 0)
            + classes.get("FALSE_MEMBER_RECOVERY", 0)
            + classes.get("AMBIGUOUS_CHANGE", 0),
            "member_to_dimension_flips": classes.get("FALSE_DIMENSION_RECOVERY", 0),
            "ambiguous_changes": classes.get("AMBIGUOUS_CHANGE", 0),
            "insufficient_evidence": classes.get("INSUFFICIENT_EVIDENCE", 0),
            "false_member_recovery": classes.get("FALSE_MEMBER_RECOVERY", 0),
            "dimension_preserved": classes.get("DIMENSION_PRESERVED", 0),
            "change_classes": dict(classes),
        }

    # E2 dimension-loss population (primary)
    e2_dim_loss = [
        r
        for r in survivors
        if r["e2_primary_stage_cap450"] == "DIMENSION_CLASSIFICATION"
    ]

    def recovery_on_dim_loss(vname: str) -> Dict[str, Any]:
        recovered = sum(
            1
            for r in e2_dim_loss
            if r["change_class"][vname] == "MEMBER_RECOVERED"
            or (
                r["variants"][vname].get("member_eligible")
                and not r["variants"]["V0_production"].get("member_eligible")
            )
        )
        return {
            "n": len(e2_dim_loss),
            "recovered": recovered,
            "still_dimension": sum(
                1 for r in e2_dim_loss if r["variants"][vname].get("is_dimension")
            ),
            "details": [
                {
                    "token_id": r["token_id"],
                    "label": r["label"],
                    "trigger": r.get("production_nearby_text"),
                    "attribution": r["attribution"],
                    "change": r["change_class"][vname],
                    "v0": r["variants"]["V0_production"]["geometry_kind"],
                    "shadow": r["variants"][vname]["geometry_kind"],
                }
                for r in e2_dim_loss
            ],
        }

    # Genuine dimension controls among survivors
    genuine_controls = [r for r in survivors if r["attribution"] == "DIMENSION_GENUINE"]
    unrelated = [r for r in survivors if r["attribution"] == "DIMENSION_UNRELATED_NEARBY_TEXT"]
    own_label = [r for r in survivors if r["attribution"] == "DIMENSION_OWN_LABEL_CONTAMINATION"]

    w30 = next(r for r in rows if r["token_id"] == "token_p8_348")

    summary = {
        "document_id": DOC_ID,
        "gold_sha256": gold_sha_before,
        "extractor_sha256": extractor_sha,
        "population": "audited_21_from_e1_e2",
        "n_targets": len(rows),
        "cap_450_survivors": len(survivors),
        "cap_450_losses": len(cap_loss),
        "own_label_id_method": "bbox_overlap_or_center_in_line_or_text_contains_gold_label; no source_word_ids in gold",
        "variants": {
            "V0_production": "current _looks_like_dimension / _looks_like_leader / nearby_text",
            "V1_ignore_own_numbers": "strip digits from nearby text when that line is own-label",
            "V2_exclude_own_label": "exclude own-label lines; use next nearest non-own nearby text",
            "V3_spatial_separation": "digit lines count only if bbox does not intersect own-label union bbox (no distance threshold)",
        },
        "baseline_funnel": {
            "raw": 21,
            "cap_survivors": len(survivors),
            "member_eligible_v0": variant_metrics("V0_production")["member_eligible"],
            "dimension_v0": variant_metrics("V0_production")["dimension"],
            "leader_v0": variant_metrics("V0_production")["leader"],
        },
        "variant_metrics": {
            "V0_production": variant_metrics("V0_production"),
            "V1_ignore_own_numbers": variant_metrics("V1_ignore_own_numbers"),
            "V2_exclude_own_label": variant_metrics("V2_exclude_own_label"),
            "V3_spatial_separation": variant_metrics("V3_spatial_separation"),
        },
        "e2_dimension_loss_recovery": {
            "V1_ignore_own_numbers": recovery_on_dim_loss("V1_ignore_own_numbers"),
            "V2_exclude_own_label": recovery_on_dim_loss("V2_exclude_own_label"),
            "V3_spatial_separation": recovery_on_dim_loss("V3_spatial_separation"),
        },
        "attribution_among_survivors": dict(Counter(r["attribution"] for r in survivors)),
        "own_label_contamination_cases": [r["token_id"] for r in own_label],
        "unrelated_nearby_text_cases": [r["token_id"] for r in unrelated],
        "genuine_dimension_controls": [r["token_id"] for r in genuine_controls],
        "genuine_dimension_control_count": len(genuine_controls),
        "false_flip_safety": (
            f"weakly measurable: {len(genuine_controls)} genuine-dimension control(s) in audited survivors; "
            "insufficient for production confidence"
            if genuine_controls
            else "not measurable from the current gold population"
        ),
        "token_p8_348_w30x90": {
            "attribution": w30["attribution"],
            "own_label_lines": w30.get("own_label_line_texts"),
            "production_nearby_text": w30.get("production_nearby_text"),
            "production_nearby_bbox": w30.get("production_nearby_line_bbox"),
            "V0": w30["variants"].get("V0_production"),
            "V1": w30["variants"].get("V1_ignore_own_numbers"),
            "V2": w30["variants"].get("V2_exclude_own_label"),
            "V3": w30["variants"].get("V3_spatial_separation"),
            "change_class": w30.get("change_class"),
            "trigger_belongs_to_w30x90_annotation": (
                w30.get("production_nearby_text") in (w30.get("own_label_line_texts") or [])
            ),
        },
    }

    if args.renders:
        # reopen clean for drawing (previous draws persist on page objects)
        pdf.close()
        pdf = fitz.open(PDF_PATH)
        for spec in render_specs:
            # fresh page annotations per save by reopening is expensive; draw then save crop
            _render_case(
                pdf,
                page_number=spec["page"],
                label_bbox=spec["label_bbox"],
                geom_bbox=spec["geom_bbox"],
                own_bboxes=spec["own_bboxes"],
                trigger_bbox=spec["trigger_bbox"],
                excluded_bboxes=spec["excluded_bboxes"],
                out_path=RENDER_DIR / f"{spec['token_id']}_p{spec['page']}.png",
                caption=spec["caption"],
            )
            # reload page state by closing/reopening to avoid stacked drawings
            pdf.close()
            pdf = fitz.open(PDF_PATH)

    OUT.mkdir(parents=True, exist_ok=True)
    jsonl_path = OUT / "dimension_shadow_results.jsonl"
    with jsonl_path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    # Also write under scripts dir as requested
    script_jsonl = Path(__file__).resolve().parent / "dimension_shadow_results.jsonl"
    script_summary = Path(__file__).resolve().parent / "dimension_shadow_summary.json"
    with script_jsonl.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    (OUT / "dimension_shadow_summary.json").write_text(json.dumps(summary, indent=2))
    script_summary.write_text(json.dumps(summary, indent=2))

    gold_sha_after = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if gold_sha_after != gold_sha_before:
        raise RuntimeError("gold changed during E3")
    extractor_sha_after = hashlib.sha256(
        (ROOT / "services" / "engineering" / "geometry_extractor.py").read_bytes()
    ).hexdigest()
    if extractor_sha_after != extractor_sha:
        raise RuntimeError("geometry_extractor.py changed during E3")

    print("\n=== E3 SUMMARY ===")
    print("survivors", len(survivors), "cap_loss", len(cap_loss))
    print("attribution", summary["attribution_among_survivors"])
    print("V0 eligible", summary["variant_metrics"]["V0_production"]["member_eligible"])
    print("V1 metrics", summary["variant_metrics"]["V1_ignore_own_numbers"])
    print("V2 metrics", summary["variant_metrics"]["V2_exclude_own_label"])
    print("V3 metrics", summary["variant_metrics"]["V3_spatial_separation"])
    print("dim-loss recovery V1", summary["e2_dimension_loss_recovery"]["V1_ignore_own_numbers"])
    print("W30X90", json.dumps(summary["token_p8_348_w30x90"], indent=2, default=str)[:1500])
    print("false_flip_safety:", summary["false_flip_safety"])
    print("gold sha unchanged:", gold_sha_after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
