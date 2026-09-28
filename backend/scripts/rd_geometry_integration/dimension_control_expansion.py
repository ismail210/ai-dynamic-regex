#!/usr/bin/env python3
"""E4 — Genuine-dimension control expansion + V1 false-flip diagnostic (R&D only).

Reuses E3 V1 (``classify_shadow_ignore_own_numbers`` / ``identify_own_label_lines``)
unchanged. Does not modify production classifiers, CAP_450, retrieval, or gold.

Usage (from backend/):
    python scripts/rd_geometry_integration/dimension_control_expansion.py
    python scripts/rd_geometry_integration/dimension_control_expansion.py --renders
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
SCRIPT_DIR = Path(__file__).resolve().parent
DOCS_OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
GOLD_PATH = DOCS_OUT / "review_kit" / "gold_outcomes.jsonl"
E1_PATH = DOCS_OUT / "cap_cost_results.jsonl"
E3_RESULTS = SCRIPT_DIR / "dimension_shadow_results.jsonl"
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)

CONTROL_SET_PATH = SCRIPT_DIR / "dimension_control_set.jsonl"
RESULTS_PATH = SCRIPT_DIR / "dimension_control_results.jsonl"
SUMMARY_PATH = SCRIPT_DIR / "dimension_control_summary.json"
RENDER_DIR = SCRIPT_DIR / "dimension_control_renders"
REPORT_PATH = DOCS_OUT / "GEOMETRY_DIMENSION_CONTROL_E4_REPORT.md"

PAGES = (8, 18, 24)

# E3 regression token ids (must keep established V1 behavior)
E3_OWN_LABEL_TOKENS = (
    "token_p8_332",
    "token_p8_337",
    "token_p8_381",
    "token_p8_430",
)
E3_UNRELATED_TOKEN = "token_p8_348"
E3_GENUINE_TOKEN = "token_p18_1143"

_MEMBER_RE = re.compile(r"^(W|WT|HSS|C|MC)\d", re.I)
_ANGLE_MEMBER_RE = re.compile(r"^L\d+X\d+X", re.I)
_LOAD_RE = re.compile(r"^\s*\d+(\.\d+)?\s*K\s*$", re.I)
_FRAC_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*\"?\s*(TYP)?\s*$", re.I)
_FRAC_LOOSE = re.compile(r"^\s*\d+\s*/\s*\d+")
_LENGTH_RE = re.compile(
    r"^\(?-?\d+'\s*-?\s*\d+(\s*/\s*\d+)?\s*\"?\)?(\s*TYP)?$", re.I
)
_INCH_RE = re.compile(r'^\s*-?\d+(\.\d+)?\s*"\s*(TYP)?\s*$', re.I)
_PLATE_THICK_RE = re.compile(r'^\s*\d+\s*/\s*\d+\s*"?\s*PL\b', re.I)
_MAX_DIM_RE = re.compile(r'^\s*\d+(\s+\d+/\d+)?\s*"?\s*MAX\s*$', re.I)


def _load_e3():
    """Import E3 module so V1 behavior is byte-identical (no rewrite)."""
    path = SCRIPT_DIR / "dimension_shadow_experiment.py"
    spec = importlib.util.spec_from_file_location("dimension_shadow_experiment", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member_token(text: str) -> str:
    """Extract designation token (e.g. W14X22) from an annotation line."""
    t = (text or "").strip()
    m = re.match(r"^((?:W|WT|HSS|C|MC)\d+(?:X\d+(?:X[\d/]+)?)?)", t, re.I)
    if m:
        return m.group(1).upper().replace(" ", "")
    m = re.match(r"^(L\d+X\d+X[\d/]+)", t, re.I)
    if m:
        return m.group(1).upper().replace(" ", "")
    return t.split()[0].upper() if t else ""


def nearby_text_evidence_kind(text: str) -> Optional[str]:
    """Return evidence kind for genuine-dimension-like text, else None."""
    t = (text or "").strip()
    if not t or len(t) > 28:
        return None
    if _LOAD_RE.match(t):
        return None
    if _MEMBER_RE.search(t) or _ANGLE_MEMBER_RE.search(t):
        return None
    if "2026" in t or "2025" in t:
        return None
    if "=" in t:  # scales / equations
        return None
    if any(x in t.upper() for x in ("SOG", "CONC", "JT AT", "T&B", "DWG", "KSI", "EJ")):
        return None
    if t.upper().startswith("TOP-"):
        return None
    if _FRAC_RE.match(t):
        return "fraction"
    if _PLATE_THICK_RE.match(t):
        return "plate_thickness"
    if _MAX_DIM_RE.match(t):
        return "max_clearance"
    if _LENGTH_RE.match(t):
        return "length"
    if _INCH_RE.match(t):
        return "inch"
    if _FRAC_LOOSE.match(t) and len(t) <= 12:
        return "fraction"
    return None


def find_matching_line(
    lines: Sequence[Dict[str, Any]],
    *,
    page: int,
    text: str,
    center: Sequence[float],
    radius: float = 96.0,
) -> Optional[Dict[str, Any]]:
    cx, cy = float(center[0]), float(center[1])
    best = None
    best_d = radius
    for ln in lines:
        if int(ln.get("page_number") or 0) != page:
            continue
        if str(ln.get("text") or "").strip() != text:
            continue
        c = ln.get("center") or [0, 0]
        d = math.hypot(float(c[0]) - cx, float(c[1]) - cy)
        if d < best_d:
            best_d = d
            best = ln
    return best


def nearest_member_line(
    lines: Sequence[Dict[str, Any]],
    *,
    page: int,
    center: Sequence[float],
    radius: float = 100.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
    cx, cy = float(center[0]), float(center[1])
    best = None
    best_d = radius
    for ln in lines:
        if int(ln.get("page_number") or 0) != page:
            continue
        t = str(ln.get("text") or "").strip()
        if not t or _LOAD_RE.match(t):
            continue
        if not (_MEMBER_RE.search(t) or _ANGLE_MEMBER_RE.search(t)):
            continue
        c = ln.get("center") or [0, 0]
        d = math.hypot(float(c[0]) - cx, float(c[1]) - cy)
        if d < best_d:
            best_d = d
            best = ln
    return best, (None if best is None else round(best_d, 2))


def change_type(v0: Dict[str, Any], v1: Dict[str, Any], *, control_status: str) -> str:
    if control_status == "insufficient_evidence":
        return "INSUFFICIENT_EVIDENCE"
    if control_status == "ambiguous":
        if (
            v0.get("is_dimension") == v1.get("is_dimension")
            and v0.get("member_eligible") == v1.get("member_eligible")
            and v0.get("is_leader") == v1.get("is_leader")
        ):
            return "NO_CHANGE"
        return "AMBIGUOUS_CHANGE"
    b_dim = bool(v0.get("is_dimension"))
    s_dim = bool(v1.get("is_dimension"))
    b_el = bool(v0.get("member_eligible"))
    s_el = bool(v1.get("member_eligible"))
    b_lead = bool(v0.get("is_leader"))
    s_lead = bool(v1.get("is_leader"))
    if b_lead != s_lead:
        return "LEADER_CHANGE"
    if b_dim and s_dim and b_el == s_el:
        return "DIMENSION_PRESERVED"
    if b_dim == s_dim and b_el == s_el:
        return "NO_CHANGE"
    if b_dim and not s_dim and s_el and not b_el:
        return "DIMENSION_TO_MEMBER"
    if not b_dim and s_dim and b_el and not s_el:
        return "MEMBER_TO_DIMENSION"
    return "AMBIGUOUS_CHANGE"


def safety_attribution(
    *,
    control_status: str,
    change: str,
    removed_by_v1: Optional[str],
    trigger_text: str,
    own_label_texts: Sequence[str],
) -> str:
    if control_status == "insufficient_evidence":
        return "INSUFFICIENT_EVIDENCE"
    if control_status == "ambiguous" or change == "AMBIGUOUS_CHANGE":
        return "AMBIGUOUS"
    if control_status == "unrelated_numeric" and change in {
        "NO_CHANGE",
        "DIMENSION_PRESERVED",
    }:
        return "UNRELATED_NUMERIC_REMOVAL"
    if change == "DIMENSION_TO_MEMBER":
        # Did V1 strip the genuine dimension trigger?
        if removed_by_v1 and removed_by_v1.strip() == (trigger_text or "").strip():
            if nearby_text_evidence_kind(trigger_text):
                return "DANGEROUS_DIMENSION_EVIDENCE_REMOVAL"
            if any(removed_by_v1 == o for o in own_label_texts):
                return "SAFE_OWN_LABEL_REMOVAL"
            return "AMBIGUOUS"
        if removed_by_v1 and any(removed_by_v1 == o for o in own_label_texts):
            return "SAFE_OWN_LABEL_REMOVAL"
        return "AMBIGUOUS"
    if change in {"NO_CHANGE", "DIMENSION_PRESERVED"}:
        if removed_by_v1 and any(removed_by_v1 == o for o in own_label_texts):
            return "SAFE_OWN_LABEL_REMOVAL"
        # Dimension preserved; V1 did not strip the genuine trigger.
        # Enum has no dedicated "no_removal" value — treat as safe non-event.
        return "SAFE_OWN_LABEL_REMOVAL"
    return "AMBIGUOUS"


def evaluate_pair(
    e3: Any,
    *,
    base_kind: GeometryKind,
    length: float,
    bbox: List[float],
    nearby_text: str,
    nearby_line: Optional[Dict[str, Any]],
    own_label_lines: Sequence[Dict[str, Any]],
    control_status: str,
) -> Dict[str, Any]:
    v0 = e3.classify_baseline(
        base_kind=base_kind, length=length, bbox=bbox, nearby_text=nearby_text or ""
    )
    v0["trigger_text"] = nearby_text or ""
    v0["trigger_bbox"] = None if nearby_line is None else nearby_line.get("bbox")
    v1 = e3.classify_shadow_ignore_own_numbers(
        base_kind=base_kind,
        length=length,
        bbox=bbox,
        nearby_text=nearby_text or "",
        nearby_line=nearby_line,
        own_label_lines=own_label_lines,
    )
    own_texts = [str(o.get("text") or "") for o in own_label_lines]
    own_numeric = [t for t in own_texts if re.search(r"\d", t)]
    removed = v1.get("removed_trigger_text")
    ch = change_type(v0, v1, control_status=control_status)
    attr = safety_attribution(
        control_status=control_status,
        change=ch,
        removed_by_v1=removed,
        trigger_text=nearby_text or "",
        own_label_texts=own_texts,
    )
    # Unrelated numeric preserved without removal
    if control_status == "unrelated_numeric" and ch in {"NO_CHANGE", "DIMENSION_PRESERVED"}:
        attr = "UNRELATED_NUMERIC_REMOVAL"
    return {
        "baseline_is_dimension": v0["is_dimension"],
        "baseline_is_leader": v0["is_leader"],
        "baseline_member_eligible": v0["member_eligible"],
        "baseline_geometry_kind": v0["geometry_kind"],
        "v1_is_dimension": v1["is_dimension"],
        "v1_is_leader": v1["is_leader"],
        "v1_member_eligible": v1["member_eligible"],
        "v1_geometry_kind": v1["geometry_kind"],
        "trigger_text": nearby_text or "",
        "trigger_source": v1.get("trigger_source"),
        "trigger_bbox": v0.get("trigger_bbox"),
        "own_label_text": own_texts,
        "own_label_numeric_text": own_numeric,
        "removed_by_v1": removed,
        "v1_shadow_nearby_text": v1.get("shadow_nearby_text"),
        "change_type": ch,
        "safety_attribution": attr,
        "v0": v0,
        "v1": v1,
    }


def _nearby_radius_for_page(document: dict, page_number: int, page_scales: dict) -> float:
    resolved = resolve_page_scale(document, page_number, page_scales=page_scales)
    page_scale = (
        page_scales.get(page_number) if resolved.get("scale_reason") == "page_scale" else None
    )
    radius = association_radius_pdf_points(page_scale) * (48.0 / 160.0)
    return max(24.0, min(96.0, radius))


def _prod_nearby(
    document: dict,
    lines: Sequence[Dict[str, Any]],
    *,
    center: Sequence[float],
    page_number: int,
    nearby_radius: float,
) -> Tuple[str, Optional[Dict[str, Any]], List[Tuple[float, Dict[str, Any]]]]:
    e3 = _load_e3()
    ranked = e3.collect_nearby_lines(center, page_number, lines, radius=nearby_radius)
    line_grid: Dict[Tuple[int, int], List[dict]] = {}
    for line in lines:
        if int(line.get("page_number") or 0) != page_number:
            continue
        c = line.get("center") or [0, 0]
        key = (int(float(c[0]) // nearby_radius), int(float(c[1]) // nearby_radius))
        line_grid.setdefault(key, []).append(line)
    prod_text = GX._nearby_text(
        list(center), page_number, document, radius=nearby_radius, line_grid=line_grid
    )
    nearby_line = None
    for _d, line in ranked:
        if str(line.get("text") or "") == prod_text:
            nearby_line = line
            break
    return prod_text, nearby_line, ranked


def build_e3_regression_controls(
    e3: Any,
    *,
    document: dict,
    lines: Sequence[Dict[str, Any]],
    gold_by: Dict[str, dict],
    e1_by: Dict[str, dict],
    page_state: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Rebuild E3 regression controls via the same CAP_450 fingerprint path."""
    controls: List[Dict[str, Any]] = []
    specs = [
        *(
            (tid, "D", "own_label_contamination", "e3_own_label_regression")
            for tid in E3_OWN_LABEL_TOKENS
        ),
        (E3_UNRELATED_TOKEN, "E", "unrelated_numeric", "e3_unrelated_nearby"),
        (E3_GENUINE_TOKEN, "A", "genuine_dimension", "e3_genuine_fraction_control"),
    ]
    for token_id, cat, status, evidence_type in specs:
        gold = gold_by[token_id]
        e1 = e1_by[token_id]
        page = int(gold["page"])
        state = page_state[page]
        drawing = None
        if e1.get("RAW_PRESENT") and e1.get("target_fingerprint"):
            drawing = state["fp_index"].get(tuple(e1["target_fingerprint"]))
        assert drawing is not None, f"E3 regression missing drawing: {token_id}"
        assert id(drawing) in state["kept_450"], f"E3 regression not under CAP_450: {token_id}"
        geom = e3._build_geometry(drawing)
        assert geom is not None
        prod_text, nearby_line, _ranked = _prod_nearby(
            document,
            lines,
            center=geom["center"],
            page_number=page,
            nearby_radius=state["nearby_radius"],
        )
        label_text = str(gold.get("text") or "")
        label_bbox = gold["label_bbox"]
        own = e3.identify_own_label_lines(
            lines, label_bbox=label_bbox, label_text=label_text, page_number=page
        )
        controls.append(
            {
                "control_id": f"e3reg_{token_id}",
                "page": page,
                "source": "e3_regression",
                "token_id": token_id,
                "label_text": label_text,
                "bbox": label_bbox,
                "geometry_ids": [e1.get("gold_selected_geometry_id") or token_id],
                "geometry_bbox": geom["bbox"],
                "geometry_length": geom["length"],
                "geometry_center": geom["center"],
                "base_kind": geom["base_kind"].value,
                "nearby_text": prod_text,
                "baseline_classification": "dimension",
                "control_category": cat,
                "evidence_type": evidence_type,
                "evidence_notes": (
                    f"E3 regression token {token_id}; production nearby={prod_text!r}; "
                    f"own_label_lines={[str(o.get('text') or '') for o in own]}"
                ),
                "confidence_level": "high",
                "control_status": status,
                "_runtime": {
                    "base_kind": geom["base_kind"],
                    "length": geom["length"],
                    "geom_bbox": geom["bbox"],
                    "nearby_line": nearby_line,
                    "own_label_lines": own,
                    "prod_text": prod_text,
                },
            }
        )
    return controls


def build_genuine_controls_from_geometry(
    e3: Any,
    *,
    document: dict,
    lines: Sequence[Dict[str, Any]],
    geometry_objects: Sequence[Dict[str, Any]],
    page_radii: Dict[int, float],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Discover genuine / ambiguous / insufficient candidates from Burrville geometry."""
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    seen = set()

    dims = [
        o
        for o in geometry_objects
        if int(o.get("page_number") or 0) in PAGES and o.get("kind") == "dimension"
    ]
    # Stable order
    dims = sorted(
        dims,
        key=lambda o: (
            int(o["page_number"]),
            round(float(o["center"][1]), 1),
            round(float(o["center"][0]), 1),
            o.get("geometry_id") or "",
        ),
    )

    for obj in dims:
        page = int(obj["page_number"])
        center = obj["center"]
        length = float(obj.get("length") or 0.0)
        if length < 12.0:
            rejected.append(
                {
                    "geometry_id": obj.get("geometry_id"),
                    "reason": "length_lt_12",
                    "nearby_text": obj.get("nearby_text"),
                }
            )
            continue
        radius = page_radii[page]
        prod_text, nearby_line, _ = _prod_nearby(
            document, lines, center=center, page_number=page, nearby_radius=radius
        )
        # Prefer recomputed production nearby; fall back to stored
        text = (prod_text or str(obj.get("nearby_text") or "")).strip()
        kind = nearby_text_evidence_kind(text)
        memb, memb_dist = nearest_member_line(lines, page=page, center=center, radius=100.0)

        # Member designations with embedded fractions are not dimension controls
        if _ANGLE_MEMBER_RE.search(text) or (
            _MEMBER_RE.search(text) and "/" in text and "PL" not in text.upper()
        ):
            rejected.append(
                {
                    "control_id": f"rej_{obj.get('geometry_id')}",
                    "page": page,
                    "source": "geometry_json",
                    "label_text": text,
                    "bbox": obj.get("bbox"),
                    "geometry_ids": [obj.get("geometry_id")],
                    "nearby_text": text,
                    "baseline_classification": "dimension",
                    "control_category": "A",
                    "evidence_type": "member_designation_with_digits",
                    "evidence_notes": "Nearby text is a member designation, not a dimension annotation.",
                    "confidence_level": "high",
                    "control_status": "insufficient_evidence",
                }
            )
            continue

        if kind is None:
            rejected.append(
                {
                    "geometry_id": obj.get("geometry_id"),
                    "reason": "nearby_not_dimension_like",
                    "nearby_text": text,
                }
            )
            continue

        # Dedup by page + text + coarse location
        dedup_key = (
            page,
            text,
            round(float(center[0]) / 40.0),
            round(float(center[1]) / 40.0),
        )
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        category = "A" if kind in {"fraction", "plate_thickness"} else "B"
        if kind == "max_clearance":
            category = "B"
        if memb is not None and memb_dist is not None and memb_dist <= 100.0:
            category = "C"

        # Confidence: fractions/lengths with long dimension strokes are stronger
        conf = "high"
        if kind == "inch" and length < 40:
            conf = "medium"
        if kind == "plate_thickness":
            conf = "medium"

        # Ambiguous elevation-like / schedule edge cases already filtered;
        # mark short bare inches far from any extension-like length as medium.
        status = "genuine_dimension"
        evidence_notes = (
            f"Production kind=dimension; length={length}; nearby={text!r} "
            f"(evidence_kind={kind}); geometry_id={obj.get('geometry_id')}."
        )
        if memb is not None:
            evidence_notes += (
                f" Nearby member {str(memb.get('text') or '')!r} at {memb_dist} pt."
            )

        label_text = ""
        label_bbox = list(obj["bbox"])
        own_lines: List[Dict[str, Any]] = []
        if memb is not None and category == "C":
            label_text = member_token(str(memb.get("text") or ""))
            label_bbox = list(memb.get("bbox") or obj["bbox"])
            own_lines = e3.identify_own_label_lines(
                lines,
                label_bbox=label_bbox,
                label_text=label_text,
                page_number=page,
            )
            evidence_notes += (
                " Category C: V1 own-label is the nearby member designation; "
                "genuine dimension text must remain available as trigger if it is nearest."
            )
        else:
            # No member own-label: V1 must not invent exclusions
            label_text = text
            if nearby_line and nearby_line.get("bbox"):
                label_bbox = list(nearby_line["bbox"])
            # Own-label intentionally empty for pure dimension controls so V1
            # cannot strip the genuine dimension trigger via own-label matching.
            own_lines = []
            evidence_notes += (
                " Pure dimension control: own_label_lines empty by design "
                "(member designation not present within 100 pt)."
            )

        # Infer base kind: dimension filter only fires on line-like kinds
        base_kind = GeometryKind.LINE
        control_id = f"gdim_p{page}_{obj.get('geometry_id')}"
        accepted.append(
            {
                "control_id": control_id,
                "page": page,
                "source": "geometry_json+document_nearby",
                "label_text": label_text,
                "bbox": label_bbox,
                "geometry_ids": [obj.get("geometry_id")],
                "geometry_bbox": obj.get("bbox"),
                "geometry_length": length,
                "geometry_center": center,
                "base_kind": base_kind.value,
                "nearby_text": text,
                "baseline_classification": "dimension",
                "control_category": category,
                "evidence_type": kind,
                "evidence_notes": evidence_notes,
                "confidence_level": conf,
                "control_status": status,
                "nearby_member_text": None if memb is None else str(memb.get("text") or ""),
                "nearby_member_dist": memb_dist,
                "_runtime": {
                    "base_kind": base_kind,
                    "length": length,
                    "geom_bbox": list(obj["bbox"]),
                    "nearby_line": nearby_line,
                    "own_label_lines": own_lines,
                    "prod_text": text,
                },
            }
        )

    return accepted, rejected


def select_control_budget(genuine: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep a targeted 10–30 set without forcing weak examples."""
    buckets: Dict[str, List[Dict[str, Any]]] = {"A": [], "B": [], "C": []}
    for c in genuine:
        buckets.setdefault(c["control_category"], []).append(c)

    selected: List[Dict[str, Any]] = []
    selected_ids: set = set()

    def take(items: List[Dict[str, Any]], n: int) -> None:
        ordered = sorted(
            items,
            key=lambda c: (
                0 if c.get("confidence_level") == "high" else 1,
                c["page"],
                c["control_id"],
            ),
        )
        added = 0
        for c in ordered:
            if c["control_id"] in selected_ids:
                continue
            selected.append(c)
            selected_ids.add(c["control_id"])
            added += 1
            if added >= n:
                break

    # Soft quotas: ~10 A, ~6 B, ~8 C; cap 28 before regressions
    take(buckets.get("A") or [], 10)
    take(buckets.get("B") or [], 6)
    take(buckets.get("C") or [], 8)

    if len(selected) < 12:
        rest = [c for c in genuine if c["control_id"] not in selected_ids]
        take(rest, 12 - len(selected))

    return selected[:28]


def _render_control(
    pdf: "fitz.Document",
    *,
    page_number: int,
    label_bbox: Sequence[float],
    geom_bbox: Optional[Sequence[float]],
    own_bboxes: Sequence[Sequence[float]],
    trigger_bbox: Optional[Sequence[float]],
    out_path: Path,
    caption: str,
    pad: float = 140.0,
    zoom: float = 2.0,
) -> None:
    page = pdf[page_number - 1]
    if geom_bbox:
        page.draw_rect(fitz.Rect(geom_bbox), color=(0.05, 0.55, 0.15), width=1.6)
    page.draw_rect(fitz.Rect(label_bbox), color=(0.1, 0.35, 0.9), width=1.6)
    for bb in own_bboxes:
        page.draw_rect(fitz.Rect(bb), color=(0.85, 0.55, 0.05), width=1.2, dashes="[2 2]")
    if trigger_bbox:
        page.draw_rect(fitz.Rect(trigger_bbox), color=(0.85, 0.1, 0.1), width=1.6)
    cx = (float(label_bbox[0]) + float(label_bbox[2])) / 2.0
    cy = (float(label_bbox[1]) + float(label_bbox[3])) / 2.0
    if geom_bbox:
        cx = (cx + (float(geom_bbox[0]) + float(geom_bbox[2])) / 2.0) / 2.0
        cy = (cy + (float(geom_bbox[1]) + float(geom_bbox[3])) / 2.0) / 2.0
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


def write_report(summary: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    genuine = [r for r in results if r["control_status"] == "genuine_dimension"]
    flips = [r for r in genuine if r["change_type"] == "DIMENSION_TO_MEMBER"]
    preserved = [
        r
        for r in genuine
        if r["change_type"] in {"DIMENSION_PRESERVED", "NO_CHANGE"} and r.get("v1_is_dimension")
    ]
    e3_reg = [r for r in results if r.get("source") == "e3_regression"]
    comp = summary["control_composition"]
    lines: List[str] = []
    lines.append("# E4 — Genuine-Dimension Control Expansion + V1 False-Flip Diagnostic\n")
    lines.append("## 1. Executive conclusion\n")
    lines.append(
        f"- Defensible genuine-dimension controls identified: "
        f"**{summary['metrics']['genuine_dimension_n']}**\n"
        f"- Remained dimension under V1: **{summary['metrics']['preserved_n']}**\n"
        f"- False dimension→member flips: **{summary['metrics']['false_flip_n']}**\n"
        f"- E3 own-label recovery regression: **{summary['e3_regression']['own_label_recovery']}**\n"
        f"- V1 production-ready? **No.** "
        f"{summary['recommendation_text']}\n"
    )
    lines.append("\n## 2. Scope\n")
    lines.append(
        "- Burrville pages **p8, p18, p24** (`doc_0d910a43b4a021e3`)\n"
        "- Sources: `geometry.json` dimension objects + `document.json` nearby text; "
        "E3 regression tokens via CAP_450 fingerprints\n"
        "- Control set expanded because E3 had only **n=1** genuine-dimension control\n"
        "- Acceptance rule: production `kind=dimension`, length≥12, nearby text matches "
        "fraction / length / inch / plate-thickness patterns, not member designations, "
        "loads, dates, or scales. Insufficient cases recorded but not counted as genuine.\n"
        "- V1 reused from E3 (`classify_shadow_ignore_own_numbers`) without modification\n"
    )
    lines.append("\n## 3. Control-set composition\n")
    lines.append("| category | inspected | accepted | ambiguous | insufficient |\n")
    lines.append("| --- | ---: | ---: | ---: | ---: |\n")
    for cat in ("A", "B", "C", "D", "E"):
        row = comp.get(cat, {})
        lines.append(
            f"| {cat} | {row.get('inspected', 0)} | {row.get('accepted', 0)} | "
            f"{row.get('ambiguous', 0)} | {row.get('insufficient', 0)} |\n"
        )
    lines.append(
        "\nCategories: A=fraction, B=length/inch, C=near member, "
        "D=own-label contamination, E=unrelated numeric.\n"
    )
    lines.append("\n## 4. V0 vs V1 results\n")
    lines.append("| control category | V0 dimension | V1 dimension | changes | false flips |\n")
    lines.append("| --- | ---: | ---: | ---: | ---: |\n")
    for cat, row in summary["v0_v1_by_category"].items():
        lines.append(
            f"| {cat} | {row['v0_dimension']} | {row['v1_dimension']} | "
            f"{row['changes']} | {row['false_flips']} |\n"
        )
    lines.append("\n## 5. Genuine-dimension safety\n")
    if not flips:
        lines.append(
            "No genuine-dimension control flipped dimension→member under V1 "
            "in this Burrville control set.\n"
        )
    else:
        lines.append("| control_id | page | text | baseline | V1 | removed text | interpretation |\n")
        lines.append("| --- | ---: | --- | --- | --- | --- | --- |\n")
        for r in flips:
            lines.append(
                f"| {r['control_id']} | {r['page']} | {r['trigger_text']!r} | "
                f"dimension | {r['v1_geometry_kind']} | {r.get('removed_by_v1')!r} | "
                f"{r.get('safety_attribution')} |\n"
            )
    lines.append("\n## 6. Difficult member + dimension cases\n")
    cat_c = [r for r in results if r.get("control_category") == "C"]
    if not cat_c:
        lines.append("No Category C controls were defensibly accepted.\n")
    else:
        lines.append("| control_id | page | member | trigger | V0 | V1 | change | safety |\n")
        lines.append("| --- | ---: | --- | --- | --- | --- | --- | --- |\n")
        for r in cat_c:
            lines.append(
                f"| {r['control_id']} | {r['page']} | {r.get('nearby_member_text') or r.get('label_text')!r} | "
                f"{r['trigger_text']!r} | "
                f"{'dim' if r['baseline_is_dimension'] else 'other'} | "
                f"{'dim' if r['v1_is_dimension'] else 'other'} | "
                f"{r['change_type']} | {r['safety_attribution']} |\n"
            )
        lines.append(
            "\nInterpretation: V1 only strips digits when the production nearby line is "
            "identified as the member's own annotation. Genuine dimension text that is "
            "merely nearby is not treated as own-label evidence.\n"
        )
    lines.append("\n## 7. E3 regression check\n")
    lines.append("| token | expected | V0 dim | V1 dim | V1 member | change | pass |\n")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |\n")
    for r in e3_reg:
        tid = r.get("token_id")
        if tid in E3_OWN_LABEL_TOKENS:
            exp = "V0=dim, V1=member recovered"
            ok = (
                r["baseline_is_dimension"]
                and r["v1_member_eligible"]
                and not r["v1_is_dimension"]
            )
        elif tid == E3_UNRELATED_TOKEN:
            exp = "V0=dim, V1=dim (17K unrelated)"
            ok = r["baseline_is_dimension"] and r["v1_is_dimension"]
        else:
            exp = "V0=dim, V1=dim (7/8 genuine)"
            ok = r["baseline_is_dimension"] and r["v1_is_dimension"]
        lines.append(
            f"| {tid} | {exp} | {r['baseline_is_dimension']} | {r['v1_is_dimension']} | "
            f"{r['v1_member_eligible']} | {r['change_type']} | {'YES' if ok else 'NO'} |\n"
        )
    lines.append("\n## 8. Visual QA\n")
    lines.append(
        f"Renders written under `backend/scripts/rd_geometry_integration/dimension_control_renders/` "
        f"({summary.get('renders_written', 0)} files). Overlays: geometry (green), "
        f"label (blue), own-label (orange dashed), trigger text (red).\n"
    )
    for name in summary.get("render_files") or []:
        lines.append(f"- `{name}`\n")
    lines.append("\n## 9. Metrics\n")
    m = summary["metrics"]
    lines.append(
        f"- genuine_dimension_n: **{m['genuine_dimension_n']}**\n"
        f"- preserved_n: **{m['preserved_n']}**\n"
        f"- false_flip_n: **{m['false_flip_n']}**\n"
        f"- false_flip_rate: **{m['false_flip_rate']}** "
        f"(observed Burrville fraction only — not a production-safety estimate)\n"
        f"- ambiguous_n: **{m['ambiguous_n']}**\n"
        f"- insufficient_n: **{m['insufficient_n']}**\n"
        f"- own_label_regression_n: **{m['own_label_regression_n']}**\n"
        f"- unrelated_numeric_n: **{m['unrelated_numeric_n']}**\n"
        f"- category_C_genuine_n: **{m.get('category_c_genuine_n')}**\n"
        f"- own_label_context_genuine_n: **{m.get('own_label_context_genuine_n')}**\n"
        f"- E3 known own-label recovery (separate): **4/4** "
        f"(regression pass={summary['e3_regression']['own_label_pass']})\n"
    )
    lines.append(
        "\nFalse-flip rate is an observed fraction on this Burrville control set only; "
        "it is **not** a reliable production-safety estimate.\n"
    )
    lines.append("\n## 10. Evidence limitations\n")
    lines.append(
        "- Sample limited to Burrville p8/p18/p24 R&D pages only\n"
        "- Many schedule-table fractions on p18 share similar geometry; dedupe reduces "
        "effective diversity\n"
        "- Category C population is sparse at ≤100 pt member↔dimension pairing\n"
        "- Plate-thickness callouts (`3/8\" PL TYP`) accepted as dimension-like with "
        "medium confidence — not traditional length dimensions\n"
        "- Visual QA is diagnostic, not a substitute for multi-project sampling\n"
        "- E4 does **not** establish production safety for V1\n"
    )
    lines.append("\n## 11. Recommendation\n")
    lines.append(f"**{summary['recommendation']}** — {summary['recommendation_text']}\n")
    if summary["recommendation"] == "A":
        lines.append(
            "\nIf pursued later (not in E4): smallest next step would be a narrowly "
            "scoped shadow flag gated to member-designation own-label digit stripping "
            "only, with a multi-document false-flip holdout — **not implemented here**.\n"
        )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renders", action="store_true")
    args = parser.parse_args()

    e3 = _load_e3()
    gold_sha_before = sha256_file(GOLD_PATH)
    assert gold_sha_before == EXPECTED_GOLD_SHA, (
        f"Human gold SHA drift: {gold_sha_before} != {EXPECTED_GOLD_SHA}"
    )
    extractor_sha = sha256_file(ROOT / "services" / "engineering" / "geometry_extractor.py")
    retrieval_sha = sha256_file(SCRIPT_DIR / "retrieval.py")
    retrieval_v2_sha = sha256_file(SCRIPT_DIR / "retrieval_v2.py")
    e3_results_sha = sha256_file(E3_RESULTS)

    document = json.loads((ARTIFACT / "document.json").read_text())
    geometry = json.loads((ARTIFACT / "geometry.json").read_text())
    lines = document.get("lines") or []
    geo_objects = geometry.get("objects") or []

    gold_by = {
        json.loads(line)["token_id"]: json.loads(line)
        for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    }
    e1_by = {
        r["token_id"]: r
        for r in (json.loads(line) for line in E1_PATH.read_text().splitlines() if line.strip())
        if r.get("population") == "audited_21"
    }

    page_scales = detect_page_scales(document)
    page_radii = {p: _nearby_radius_for_page(document, p, page_scales) for p in PAGES}

    pdf = fitz.open(PDF_PATH)
    page_state: Dict[int, Dict[str, Any]] = {}
    for page_number in PAGES:
        page = pdf[page_number - 1]
        raw = page.get_drawings() or []
        pw, ph = float(page.rect.width), float(page.rect.height)
        kept = e3._select_cap(raw, page_width=pw, page_height=ph, cap=450)
        page_state[page_number] = {
            "raw": raw,
            "fp_index": {e3._drawing_fingerprint(d): d for d in raw},
            "kept_450": {id(d) for d in kept},
            "nearby_radius": page_radii[page_number],
        }
        print(f"p{page_number}: raw={len(raw)} cap450={len(kept)} radius={page_radii[page_number]}")

    # --- Build controls ---
    e3_controls = build_e3_regression_controls(
        e3,
        document=document,
        lines=lines,
        gold_by=gold_by,
        e1_by=e1_by,
        page_state=page_state,
    )
    genuine_all, rejected = build_genuine_controls_from_geometry(
        e3,
        document=document,
        lines=lines,
        geometry_objects=geo_objects,
        page_radii=page_radii,
    )
    # Exclude E3 genuine geometry if duplicated by geometry scan (token_p18_1143)
    e3_geom_ids = set()
    for c in e3_controls:
        for gid in c.get("geometry_ids") or []:
            if gid:
                e3_geom_ids.add(gid)
    genuine_all = [
        c
        for c in genuine_all
        if not set(c.get("geometry_ids") or []) & e3_geom_ids
        and c.get("token_id") not in {E3_GENUINE_TOKEN}
    ]
    # Also drop controls whose geometry_id matches the E3 genuine case by nearby+page
    genuine_selected = select_control_budget(genuine_all)

    # Record some insufficient examples explicitly (not counted as genuine)
    insufficient_examples: List[Dict[str, Any]] = []
    for r in rejected:
        if r.get("control_status") == "insufficient_evidence":
            insufficient_examples.append(r)
        if len(insufficient_examples) >= 5:
            break
    # Add a few programmatic insufficient records for member-with-fraction nearby
    if len(insufficient_examples) < 3:
        for obj in geo_objects:
            if int(obj.get("page_number") or 0) not in PAGES:
                continue
            t = str(obj.get("nearby_text") or "")
            if _ANGLE_MEMBER_RE.search(t) and obj.get("kind") == "dimension":
                insufficient_examples.append(
                    {
                        "control_id": f"insuff_{obj.get('geometry_id')}",
                        "page": int(obj["page_number"]),
                        "source": "geometry_json",
                        "label_text": t,
                        "bbox": obj.get("bbox"),
                        "geometry_ids": [obj.get("geometry_id")],
                        "nearby_text": t,
                        "baseline_classification": "dimension",
                        "control_category": "A",
                        "evidence_type": "member_designation_with_digits",
                        "evidence_notes": "Angle/HSS designation containing digits — not a dimension annotation.",
                        "confidence_level": "high",
                        "control_status": "insufficient_evidence",
                    }
                )
            if len(insufficient_examples) >= 5:
                break

    controls: List[Dict[str, Any]] = []
    controls.extend(e3_controls)
    controls.extend(genuine_selected)
    controls.extend(insufficient_examples)

    # Stable order
    controls = sorted(
        controls,
        key=lambda c: (c["page"], c.get("control_category") or "", c["control_id"]),
    )

    # Write control set (strip runtime)
    control_set_rows = []
    for c in controls:
        row = {k: v for k, v in c.items() if not k.startswith("_")}
        control_set_rows.append(row)
    CONTROL_SET_PATH.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in control_set_rows),
        encoding="utf-8",
    )

    # --- Evaluate ---
    results: List[Dict[str, Any]] = []
    for c in controls:
        runtime = c.get("_runtime")
        if runtime is None:
            # insufficient / static — no V0/V1 geometry evaluation
            results.append(
                {
                    **{k: v for k, v in c.items() if not k.startswith("_")},
                    "baseline_is_dimension": None,
                    "baseline_is_leader": None,
                    "baseline_member_eligible": None,
                    "v1_is_dimension": None,
                    "v1_is_leader": None,
                    "v1_member_eligible": None,
                    "trigger_text": c.get("nearby_text"),
                    "trigger_source": None,
                    "own_label_text": [],
                    "own_label_numeric_text": [],
                    "removed_by_v1": None,
                    "change_type": "INSUFFICIENT_EVIDENCE",
                    "safety_attribution": "INSUFFICIENT_EVIDENCE",
                }
            )
            continue
        ev = evaluate_pair(
            e3,
            base_kind=runtime["base_kind"],
            length=float(runtime["length"]),
            bbox=list(runtime["geom_bbox"]),
            nearby_text=runtime["prod_text"],
            nearby_line=runtime["nearby_line"],
            own_label_lines=runtime["own_label_lines"],
            control_status=c["control_status"],
        )
        out = {k: v for k, v in c.items() if not k.startswith("_")}
        out.update({k: v for k, v in ev.items() if k not in {"v0", "v1"}})
        results.append(out)

    RESULTS_PATH.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in results),
        encoding="utf-8",
    )

    # --- Metrics ---
    genuine = [r for r in results if r["control_status"] == "genuine_dimension"]
    preserved = [r for r in genuine if r.get("v1_is_dimension")]
    false_flips = [
        r
        for r in genuine
        if r.get("change_type") == "DIMENSION_TO_MEMBER"
        and r.get("safety_attribution") == "DANGEROUS_DIMENSION_EVIDENCE_REMOVAL"
    ]
    # Any dim→member on genuine controls counts toward false_flip_n for reporting;
    # safety_attribution distinguishes dangerous vs safe own-label.
    dim_to_member = [r for r in genuine if r.get("change_type") == "DIMENSION_TO_MEMBER"]
    dangerous_flips = [
        r
        for r in dim_to_member
        if r.get("safety_attribution") == "DANGEROUS_DIMENSION_EVIDENCE_REMOVAL"
    ]
    false_flip_n = len(dangerous_flips)
    # If attribution missed but change occurred on genuine with removed genuine text
    for r in dim_to_member:
        if r in dangerous_flips:
            continue
        if nearby_text_evidence_kind(str(r.get("trigger_text") or "")) and r.get(
            "removed_by_v1"
        ) == r.get("trigger_text"):
            false_flip_n += 1
            dangerous_flips.append(r)

    n_g = len(genuine)
    # Rate reported only as an observed Burrville fraction — not a production-safety estimate.
    false_flip_rate: Optional[float]
    if n_g >= 10:
        false_flip_rate = round(false_flip_n / n_g, 4)
    else:
        false_flip_rate = None

    composition: Dict[str, Dict[str, int]] = {
        cat: {"inspected": 0, "accepted": 0, "ambiguous": 0, "insufficient": 0}
        for cat in ("A", "B", "C", "D", "E")
    }
    # inspected ≈ accepted + rejected-ish for A/B/C from genuine_all + regressions
    for c in genuine_all:
        cat = c["control_category"]
        composition[cat]["inspected"] += 1
    for c in e3_controls:
        cat = c["control_category"]
        composition[cat]["inspected"] += 1
    for r in results:
        cat = r.get("control_category") or "?"
        if cat not in composition:
            continue
        st = r.get("control_status")
        if st == "genuine_dimension" or st == "own_label_contamination" or st == "unrelated_numeric":
            if r.get("source") == "e3_regression" or st == "genuine_dimension":
                if st in {"genuine_dimension", "own_label_contamination", "unrelated_numeric"}:
                    composition[cat]["accepted"] += 1
        elif st == "ambiguous":
            composition[cat]["ambiguous"] += 1
        elif st == "insufficient_evidence":
            composition[cat]["insufficient"] += 1

    v0_v1: Dict[str, Dict[str, int]] = {}
    for cat in ("A", "B", "C", "D", "E"):
        rows = [r for r in results if r.get("control_category") == cat and r.get("baseline_is_dimension") is not None]
        v0_v1[cat] = {
            "v0_dimension": sum(1 for r in rows if r.get("baseline_is_dimension")),
            "v1_dimension": sum(1 for r in rows if r.get("v1_is_dimension")),
            "changes": sum(
                1
                for r in rows
                if r.get("change_type")
                not in {"NO_CHANGE", "DIMENSION_PRESERVED", "INSUFFICIENT_EVIDENCE"}
            ),
            "false_flips": sum(
                1
                for r in rows
                if r.get("control_status") == "genuine_dimension"
                and r.get("change_type") == "DIMENSION_TO_MEMBER"
                and r.get("safety_attribution") == "DANGEROUS_DIMENSION_EVIDENCE_REMOVAL"
            ),
        }

    # E3 regression assertions data
    e3_rows = {r.get("token_id"): r for r in results if r.get("source") == "e3_regression"}
    own_ok = all(
        e3_rows[t]["baseline_is_dimension"]
        and e3_rows[t]["v1_member_eligible"]
        and not e3_rows[t]["v1_is_dimension"]
        for t in E3_OWN_LABEL_TOKENS
    )
    unrelated_ok = (
        e3_rows[E3_UNRELATED_TOKEN]["baseline_is_dimension"]
        and e3_rows[E3_UNRELATED_TOKEN]["v1_is_dimension"]
    )
    genuine_ok = (
        e3_rows[E3_GENUINE_TOKEN]["baseline_is_dimension"]
        and e3_rows[E3_GENUINE_TOKEN]["v1_is_dimension"]
    )

    # Recommendation: conservative. A only with 0 dangerous flips, E3 pass,
    # and enough Category-C / own-label-context cases. Still not "production-safe".
    cat_c_n = sum(
        1
        for r in results
        if r.get("control_category") == "C" and r.get("control_status") == "genuine_dimension"
    )
    own_context_n = sum(1 for r in genuine if r.get("own_label_text"))
    if false_flip_n > 0:
        recommendation = "B"
        recommendation_text = (
            "Dangerous dimension-evidence removals were observed; run another "
            "deterministic diagnostic before any production scoping."
        )
    elif not (own_ok and unrelated_ok and genuine_ok):
        recommendation = "C"
        recommendation_text = (
            "E3 regression checks failed; stop before production work."
        )
    elif n_g < 10 or cat_c_n < 3 or own_context_n < 5:
        recommendation = "B"
        recommendation_text = (
            "E4 provides additional evidence but does not establish production "
            "safety. Expand Category C / own-label-context coverage before any "
            "production-change experiment."
        )
    elif false_flip_n == 0:
        recommendation = "A"
        recommendation_text = (
            "E4 provides additional evidence but does not establish production "
            "safety. Zero dangerous false flips on the Burrville control set "
            f"(genuine n={n_g}, Category C n={cat_c_n}) supports considering a "
            "narrowly scoped production-change experiment later — not implemented "
            "in E4. Multi-document holdout still required."
        )
    else:
        recommendation = "C"
        recommendation_text = "Evidence is insufficient or inconsistent; stop before production work."

    # Renders
    render_files: List[str] = []
    if args.renders:
        # reopen clean page drawings (avoid permanent markup accumulation issues)
        pdf.close()
        pdf = fitz.open(PDF_PATH)
        want: List[Dict[str, Any]] = []
        # E3 regressions
        want.extend([r for r in results if r.get("token_id") in E3_OWN_LABEL_TOKENS])
        want.extend([r for r in results if r.get("token_id") == E3_UNRELATED_TOKEN])
        want.extend([r for r in results if r.get("token_id") == E3_GENUINE_TOKEN])
        # genuine samples
        g_samples = [r for r in genuine if r.get("source") != "e3_regression"][:8]
        want.extend(g_samples)
        # category C
        want.extend([r for r in results if r.get("control_category") == "C"][:4])
        # all dangerous flips
        want.extend(dangerous_flips)
        seen_ids = set()
        for r in want:
            cid = r["control_id"]
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            if r.get("baseline_is_dimension") is None:
                continue
            # Need bboxes — reload from controls
            src = next(c for c in controls if c["control_id"] == cid)
            rt = src.get("_runtime") or {}
            own_bbs = [
                ln["bbox"]
                for ln in (rt.get("own_label_lines") or [])
                if ln.get("bbox")
            ]
            out_name = f"{cid}_p{r['page']}.png"
            _render_control(
                pdf,
                page_number=int(r["page"]),
                label_bbox=src["bbox"],
                geom_bbox=src.get("geometry_bbox"),
                own_bboxes=own_bbs,
                trigger_bbox=r.get("trigger_bbox"),
                out_path=RENDER_DIR / out_name,
                caption=(
                    f"{cid} {r['change_type']} V0={'D' if r['baseline_is_dimension'] else '-'} "
                    f"V1={'D' if r['v1_is_dimension'] else 'M' if r['v1_member_eligible'] else '-'} "
                    f"trig={r.get('trigger_text')!r}"
                ),
            )
            render_files.append(out_name)
    elif RENDER_DIR.exists():
        render_files = sorted(p.name for p in RENDER_DIR.glob("*.png"))

    summary = {
        "experiment": "E4_dimension_control_expansion",
        "doc_id": DOC_ID,
        "pages": list(PAGES),
        "gold_sha": gold_sha_before,
        "extractor_sha": extractor_sha,
        "retrieval_sha": retrieval_sha,
        "retrieval_v2_sha": retrieval_v2_sha,
        "e3_results_sha": e3_results_sha,
        "control_composition": composition,
        "v0_v1_by_category": v0_v1,
        "metrics": {
            "total_controls": len(results),
            "genuine_dimension_n": n_g,
            "preserved_n": len(preserved),
            "false_flip_n": false_flip_n,
            "false_flip_rate": false_flip_rate,
            "dim_to_member_raw_n": len(dim_to_member),
            "ambiguous_n": sum(1 for r in results if r["control_status"] == "ambiguous"),
            "insufficient_n": sum(
                1 for r in results if r["control_status"] == "insufficient_evidence"
            ),
            "own_label_regression_n": sum(
                1 for r in results if r["control_status"] == "own_label_contamination"
            ),
            "unrelated_numeric_n": sum(
                1 for r in results if r["control_status"] == "unrelated_numeric"
            ),
            "genuine_candidates_discovered": len(genuine_all),
            "genuine_selected": len(genuine_selected),
            "category_c_genuine_n": cat_c_n,
            "own_label_context_genuine_n": own_context_n,
        },
        "e3_regression": {
            "own_label_recovery": "4/4" if own_ok else "REGRESSION",
            "own_label_pass": own_ok,
            "unrelated_17k_pass": unrelated_ok,
            "genuine_7_8_pass": genuine_ok,
        },
        "recommendation": recommendation,
        "recommendation_text": recommendation_text,
        "renders_written": len(render_files),
        "render_files": render_files,
        "v1_refactor": (
            "E4 imports E3 helpers via importlib; no V1 logic rewrite. "
            "evaluate_pair wraps classify_baseline + classify_shadow_ignore_own_numbers."
        ),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(summary, results)

    gold_sha_after = sha256_file(GOLD_PATH)
    assert gold_sha_after == gold_sha_before == EXPECTED_GOLD_SHA
    assert sha256_file(ROOT / "services" / "engineering" / "geometry_extractor.py") == extractor_sha
    assert sha256_file(SCRIPT_DIR / "retrieval.py") == retrieval_sha
    assert sha256_file(SCRIPT_DIR / "retrieval_v2.py") == retrieval_v2_sha
    assert sha256_file(E3_RESULTS) == e3_results_sha

    print(
        json.dumps(
            {
                "genuine_n": n_g,
                "preserved_n": len(preserved),
                "false_flip_n": false_flip_n,
                "false_flip_rate": false_flip_rate,
                "recommendation": recommendation,
                "e3_own_label": summary["e3_regression"]["own_label_recovery"],
                "control_set": str(CONTROL_SET_PATH),
                "results": str(RESULTS_PATH),
                "summary": str(SUMMARY_PATH),
                "report": str(REPORT_PATH),
            },
            indent=2,
        )
    )
    pdf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
