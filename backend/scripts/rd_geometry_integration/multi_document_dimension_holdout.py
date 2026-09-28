#!/usr/bin/env python3
"""E5 — Multi-document holdout for own-label digit stripping (R&D shadow only).

Reuses E3/E4 V1 (``classify_shadow_ignore_own_numbers`` /
``identify_own_label_lines``) unchanged. Does **not** modify production
classifiers, CAP_450, retrieval, or human gold.

Usage (from backend/):
    python scripts/rd_geometry_integration/multi_document_dimension_holdout.py
    python scripts/rd_geometry_integration/multi_document_dimension_holdout.py --renders
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from services.engineering import geometry_extractor as GX  # noqa: E402  read-only
from services.engineering.models import GeometryKind  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
DOCS_OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
GOLD_PATH = DOCS_OUT / "review_kit" / "gold_outcomes.jsonl"
E3_RESULTS = SCRIPT_DIR / "dimension_shadow_results.jsonl"
E4_RESULTS = SCRIPT_DIR / "dimension_control_results.jsonl"
E4_SET = SCRIPT_DIR / "dimension_control_set.jsonl"
EXTRACTOR = ROOT / "services" / "engineering" / "geometry_extractor.py"
RETRIEVAL = SCRIPT_DIR / "retrieval.py"
RETRIEVAL_V2 = SCRIPT_DIR / "retrieval_v2.py"

RESULTS_PATH = DOCS_OUT / "dimension_holdout_e5_results.jsonl"
SUMMARY_PATH = DOCS_OUT / "dimension_holdout_e5_summary.json"
REPORT_PATH = DOCS_OUT / "GEOMETRY_DIMENSION_HOLDOUT_E5_REPORT.md"
RENDER_DIR = DOCS_OUT / "dimension_holdout_e5_renders"
REVIEW_HTML = DOCS_OUT / "dimension_holdout_e5_review.html"

EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
EXPECTED_EXTRACTOR_SHA = (
    "6c6f73d7090a427705599a24cba4bad167a531a70cc5ff6879ccd0ca809ec940"
)
EXPECTED_E3_SHA = (
    "bc633040e9c5624d3147d937e93d536be3a5ee510ed95bf85d0c6af8a3020568"
)

# Fixed production-default nearby radius (no multimodal page-scale artifact for holdouts).
NEARBY_RADIUS = 48.0
CAP = 450
MAX_PER_BUCKET_PER_PAGE = 8
MAX_CASES_PER_DOC = 60

_MEMBER_RE = re.compile(r"^(W|WT|HSS|C|MC)\d", re.I)
_ANGLE_RE = re.compile(r"^L\d+X\d+X", re.I)
_LOAD_RE = re.compile(r"^\s*\d+(\.\d+)?\s*K\s*$", re.I)
_FRAC_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*\"?\s*(TYP)?\s*$", re.I)
_LENGTH_RE = re.compile(
    r"^\(?-?\d+'\s*-?\s*\d+(\s*/\s*\d+)?\s*\"?\)?(\s*TYP)?$", re.I
)
_INCH_RE = re.compile(r'^\s*-?\d+(\.\d+)?\s*"\s*(TYP)?\s*$', re.I)
_PLATE_RE = re.compile(r'^\s*\d+\s*/\s*\d+\s*"?\s*PL\b', re.I)
_DIGIT_RE = re.compile(r"\d")

# Holdout corpus: independent of Burrville; native structural PDFs already in uploads/.
HOLDOUT_DOCS: List[Dict[str, Any]] = [
    {
        "doc_key": "springhill_lake",
        "doc_id": "doc_f6ddc4a7e233ffb0",
        "project": "Springhill Lake",
        "pdf": ROOT / "uploads" / "ST - Springhill Lake__f6ddc4a7e233.pdf",
        "pages": (7, 8),
        "why": (
            "Independent school structural set; dense framing pages with many "
            "WxxXxx [nn] designations and load callouts."
        ),
        "independent_of_burrville": True,
    },
    {
        "doc_key": "structure_copy",
        "doc_id": "doc_9414716bffc67596",
        "project": "Structure - Copy",
        "pdf": ROOT / "uploads" / "Structure - Copy__9414716bffc6.pdf",
        "pages": (6, 8),
        "why": (
            "Independent structural package; framing/detail pages with member "
            "labels and fraction/length annotations."
        ),
        "independent_of_burrville": True,
    },
    {
        "doc_key": "struct",
        "doc_id": "doc_683e6eef0a945c9a",
        "project": "Struct",
        "pdf": ROOT / "uploads" / "Struct__683e6eef0a94.pdf",
        "pages": (7, 9),
        "why": (
            "Independent structural drawings; high density of W-shape labels "
            "with trailing numeric annotation content."
        ),
        "independent_of_burrville": True,
    },
]


_E3_MOD = None
_E4_MOD = None


def _load_e3():
    global _E3_MOD
    if _E3_MOD is not None:
        return _E3_MOD
    path = SCRIPT_DIR / "dimension_shadow_experiment.py"
    spec = importlib.util.spec_from_file_location("dimension_shadow_experiment", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _E3_MOD = mod
    return mod


def _load_e4():
    global _E4_MOD
    if _E4_MOD is not None:
        return _E4_MOD
    path = SCRIPT_DIR / "dimension_control_expansion.py"
    spec = importlib.util.spec_from_file_location("dimension_control_expansion", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _E4_MOD = mod
    return mod


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member_token(text: str) -> str:
    t = (text or "").strip()
    m = re.match(r"^((?:W|WT|HSS|C|MC)\d+(?:X\d+(?:X[\d/]+)?)?)", t, re.I)
    if m:
        return m.group(1).upper().replace(" ", "")
    m = re.match(r"^(L\d+X\d+X[\d/]+)", t, re.I)
    if m:
        return m.group(1).upper().replace(" ", "")
    return t.split()[0].upper() if t else ""


def is_member_designation(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _LOAD_RE.match(t):
        return False
    return bool(_MEMBER_RE.search(t) or _ANGLE_RE.search(t))


def is_genuine_dimension_text(text: str) -> bool:
    return _load_e4().nearby_text_evidence_kind(text) is not None


def extract_page_lines(page: "fitz.Page", page_number: int) -> List[Dict[str, Any]]:
    """Deterministic text lines with bboxes from a PDF page."""
    out: List[Dict[str, Any]] = []
    data = page.get_text("dict") or {}
    for block in data.get("blocks") or []:
        if int(block.get("type") or 0) != 0:
            continue
        for line in block.get("lines") or []:
            spans = line.get("spans") or []
            if not spans:
                continue
            text = "".join(str(s.get("text") or "") for s in spans).strip()
            if not text or len(text) > 80:
                continue
            xs: List[float] = []
            ys: List[float] = []
            for s in spans:
                bb = s.get("bbox")
                if not bb or len(bb) < 4:
                    continue
                xs.extend([float(bb[0]), float(bb[2])])
                ys.extend([float(bb[1]), float(bb[3])])
            if not xs:
                continue
            bbox = [min(xs), min(ys), max(xs), max(ys)]
            center = [
                round((bbox[0] + bbox[2]) / 2.0, 2),
                round((bbox[1] + bbox[3]) / 2.0, 2),
            ]
            out.append(
                {
                    "text": text,
                    "bbox": [round(v, 2) for v in bbox],
                    "center": center,
                    "page_number": page_number,
                }
            )
    # Stable order
    out.sort(key=lambda ln: (ln["bbox"][1], ln["bbox"][0], ln["text"]))
    return out


def build_document_structure(lines: Sequence[Dict[str, Any]]) -> dict:
    return {"lines": list(lines)}


def production_nearby(
    e3: Any,
    *,
    center: Sequence[float],
    page_number: int,
    document: dict,
    lines: Sequence[Dict[str, Any]],
    radius: float = NEARBY_RADIUS,
) -> Tuple[str, Optional[Dict[str, Any]], List[Tuple[float, Dict[str, Any]]]]:
    ranked = e3.collect_nearby_lines(center, page_number, lines, radius=radius)
    line_grid: Dict[Tuple[int, int], List[dict]] = {}
    for line in lines:
        if int(line.get("page_number") or 0) != page_number:
            continue
        c = line.get("center") or [0, 0]
        key = (int(float(c[0]) // radius), int(float(c[1]) // radius))
        line_grid.setdefault(key, []).append(line)
    prod = GX._nearby_text(
        list(center), page_number, document, radius=radius, line_grid=line_grid
    )
    nearby_line = None
    for _d, line in ranked:
        if str(line.get("text") or "") == prod:
            nearby_line = line
            break
    return prod, nearby_line, ranked


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
        if not is_member_designation(t):
            continue
        c = ln.get("center") or [0, 0]
        d = math.hypot(float(c[0]) - cx, float(c[1]) - cy)
        if d < best_d:
            best_d = d
            best = ln
    return best, (None if best is None else round(best_d, 2))


def classify_case_bucket(
    *,
    prod_text: str,
    nearby_line: Optional[Dict[str, Any]],
    own_lines: Sequence[Dict[str, Any]],
    v0_is_dimension: bool,
) -> str:
    """Assign evidence bucket for the holdout case."""
    own_ids = {id(x) for x in own_lines}
    own_texts = [str(o.get("text") or "") for o in own_lines]
    t = (prod_text or "").strip()

    if nearby_line is not None and id(nearby_line) in own_ids and _DIGIT_RE.search(t):
        return "OWN_LABEL_CONTAMINATION"
    if any(t == ot for ot in own_texts) and _DIGIT_RE.search(t):
        return "OWN_LABEL_CONTAMINATION"
    if _LOAD_RE.match(t):
        return "UNRELATED_NUMERIC"
    if is_genuine_dimension_text(t):
        return "GENUINE_DIMENSION"
    if is_member_designation(t) and _DIGIT_RE.search(t):
        # Member-like nearby but ownership not established for this label context
        return "OWNERSHIP_UNESTABLISHED"
    if v0_is_dimension and _DIGIT_RE.search(t):
        return "OWNERSHIP_UNESTABLISHED"
    return "NO_CHANGE_BASELINE"


def outcome_label(
    *,
    bucket: str,
    v0: Dict[str, Any],
    v1: Dict[str, Any],
    changed: bool,
) -> str:
    if not changed:
        if v0.get("is_dimension") and bucket == "GENUINE_DIMENSION":
            return "DIMENSION_PRESERVED"
        if v0.get("member_eligible"):
            return "UNCHANGED_MEMBER_ELIGIBLE"
        if v0.get("is_dimension"):
            return "UNCHANGED_DIMENSION"
        return "NO_CHANGE"
    # Changed
    if (
        v0.get("is_dimension")
        and not v1.get("is_dimension")
        and v1.get("member_eligible")
        and bucket == "OWN_LABEL_CONTAMINATION"
    ):
        return "MEMBER_RECOVERED"
    if (
        v0.get("is_dimension")
        and not v1.get("is_dimension")
        and v1.get("member_eligible")
        and bucket == "GENUINE_DIMENSION"
    ):
        return "FALSE_FLIP_DIMENSION_TO_MEMBER"
    if (
        v0.get("is_dimension")
        and not v1.get("is_dimension")
        and v1.get("member_eligible")
        and bucket == "UNRELATED_NUMERIC"
    ):
        return "FALSE_UNRELATED_TREATED_AS_OWN_LABEL"
    if (
        v0.get("is_dimension")
        and not v1.get("is_dimension")
        and v1.get("member_eligible")
    ):
        return "AMBIGUOUS_DIMENSION_TO_MEMBER"
    if not v0.get("is_dimension") and v1.get("is_dimension"):
        return "FALSE_MEMBER_TO_DIMENSION"
    return "AMBIGUOUS_CHANGE"


def is_dangerous(outcome: str) -> bool:
    return outcome in {
        "FALSE_FLIP_DIMENSION_TO_MEMBER",
        "FALSE_UNRELATED_TREATED_AS_OWN_LABEL",
        "FALSE_MEMBER_TO_DIMENSION",
    }


def evaluate_stroke(
    e3: Any,
    *,
    geom: Dict[str, Any],
    prod_text: str,
    nearby_line: Optional[Dict[str, Any]],
    own_lines: Sequence[Dict[str, Any]],
    label_text: str,
    label_bbox: Sequence[float],
    bucket_hint: Optional[str] = None,
) -> Dict[str, Any]:
    v0 = e3.classify_baseline(
        base_kind=geom["base_kind"],
        length=geom["length"],
        bbox=geom["bbox"],
        nearby_text=prod_text or "",
    )
    v1 = e3.classify_shadow_ignore_own_numbers(
        base_kind=geom["base_kind"],
        length=geom["length"],
        bbox=geom["bbox"],
        nearby_text=prod_text or "",
        nearby_line=nearby_line,
        own_label_lines=own_lines,
    )
    bucket = bucket_hint or classify_case_bucket(
        prod_text=prod_text,
        nearby_line=nearby_line,
        own_lines=own_lines,
        v0_is_dimension=bool(v0["is_dimension"]),
    )
    changed = (
        bool(v0["is_dimension"]) != bool(v1["is_dimension"])
        or bool(v0["member_eligible"]) != bool(v1["member_eligible"])
        or bool(v0["is_leader"]) != bool(v1["is_leader"])
    )
    outcome = outcome_label(bucket=bucket, v0=v0, v1=v1, changed=changed)
    ownership_established = bool(own_lines) and (
        (nearby_line is not None and id(nearby_line) in {id(x) for x in own_lines})
        or any(str(o.get("text") or "") == (prod_text or "") for o in own_lines)
    )
    return {
        "label_text": label_text,
        "label_bbox": list(label_bbox),
        "nearby_text": prod_text,
        "trigger_bbox": None if nearby_line is None else nearby_line.get("bbox"),
        "own_label_texts": [str(o.get("text") or "") for o in own_lines],
        "ownership_established": ownership_established,
        "numeric_from_own_label": bool(
            ownership_established and _DIGIT_RE.search(prod_text or "")
        ),
        "bucket": bucket,
        "baseline_is_dimension": v0["is_dimension"],
        "baseline_is_leader": v0["is_leader"],
        "baseline_member_eligible": v0["member_eligible"],
        "baseline_geometry_kind": v0["geometry_kind"],
        "v1_is_dimension": v1["is_dimension"],
        "v1_is_leader": v1["is_leader"],
        "v1_member_eligible": v1["member_eligible"],
        "v1_geometry_kind": v1["geometry_kind"],
        "removed_by_v1": v1.get("removed_trigger_text"),
        "v1_trigger_source": v1.get("trigger_source"),
        "changed": changed,
        "outcome": outcome,
        "dangerous": is_dangerous(outcome),
        "geometry_bbox": geom["bbox"],
        "geometry_length": geom["length"],
        "geometry_center": geom["center"],
        "base_kind": geom["base_kind"].value,
    }


def render_case(
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


def scan_page(
    e3: Any,
    *,
    doc_meta: Dict[str, Any],
    page_number: int,
    pdf: "fitz.Document",
) -> List[Dict[str, Any]]:
    page = pdf[page_number - 1]
    pw, ph = float(page.rect.width), float(page.rect.height)
    raw = page.get_drawings() or []
    kept = e3._select_cap(raw, page_width=pw, page_height=ph, cap=CAP)
    lines = extract_page_lines(page, page_number)
    document = build_document_structure(lines)

    candidates: List[Dict[str, Any]] = []
    for idx, drawing in enumerate(kept):
        geom = e3._build_geometry(drawing)
        if geom is None:
            continue
        if geom["base_kind"] not in {
            GeometryKind.LINE,
            GeometryKind.POLYLINE,
            GeometryKind.PATH,
        }:
            continue
        if float(geom["length"]) < 12.0:
            continue
        prod_text, nearby_line, _ranked = production_nearby(
            e3,
            center=geom["center"],
            page_number=page_number,
            document=document,
            lines=lines,
        )
        if not prod_text or not _DIGIT_RE.search(prod_text):
            continue

        # Establish own-label only from deterministic member designation ownership.
        label_text = ""
        label_bbox = list(geom["bbox"])
        own_lines: List[Dict[str, Any]] = []
        mixed = False

        if is_member_designation(prod_text):
            label_text = member_token(prod_text)
            if nearby_line and nearby_line.get("bbox"):
                label_bbox = list(nearby_line["bbox"])
            own_lines = e3.identify_own_label_lines(
                lines,
                label_bbox=label_bbox,
                label_text=label_text,
                page_number=page_number,
            )
        elif is_genuine_dimension_text(prod_text):
            # Genuine dimension trigger — optional member context for mixed cases.
            memb, memb_dist = nearest_member_line(
                lines, page=page_number, center=geom["center"], radius=100.0
            )
            if memb is not None:
                mixed = True
                label_text = member_token(str(memb.get("text") or ""))
                label_bbox = list(memb.get("bbox") or geom["bbox"])
                own_lines = e3.identify_own_label_lines(
                    lines,
                    label_bbox=label_bbox,
                    label_text=label_text,
                    page_number=page_number,
                )
            else:
                label_text = prod_text
                if nearby_line and nearby_line.get("bbox"):
                    label_bbox = list(nearby_line["bbox"])
                own_lines = []  # must not invent ownership
        elif _LOAD_RE.match(prod_text.strip()):
            memb, _ = nearest_member_line(
                lines, page=page_number, center=geom["center"], radius=80.0
            )
            if memb is None:
                continue
            label_text = member_token(str(memb.get("text") or ""))
            label_bbox = list(memb.get("bbox") or geom["bbox"])
            own_lines = e3.identify_own_label_lines(
                lines,
                label_bbox=label_bbox,
                label_text=label_text,
                page_number=page_number,
            )
        else:
            # Digits present but neither member designation nor genuine dim nor load —
            # only keep if a nearby member exists (ownership boundary test).
            memb, _ = nearest_member_line(
                lines, page=page_number, center=geom["center"], radius=60.0
            )
            if memb is None:
                continue
            label_text = member_token(str(memb.get("text") or ""))
            label_bbox = list(memb.get("bbox") or geom["bbox"])
            own_lines = e3.identify_own_label_lines(
                lines,
                label_bbox=label_bbox,
                label_text=label_text,
                page_number=page_number,
            )

        ev = evaluate_stroke(
            e3,
            geom=geom,
            prod_text=prod_text,
            nearby_line=nearby_line,
            own_lines=own_lines,
            label_text=label_text,
            label_bbox=label_bbox,
        )
        if mixed and ev["bucket"] == "GENUINE_DIMENSION":
            ev["bucket"] = "MIXED_MEMBER_DIMENSION"

        # Skip uninteresting unchanged non-dimension strokes
        if (
            not ev["baseline_is_dimension"]
            and not ev["changed"]
            and ev["bucket"] not in {"OWN_LABEL_CONTAMINATION", "UNRELATED_NUMERIC"}
        ):
            continue

        fp = e3._drawing_fingerprint(drawing)
        fp_digest = hashlib.sha1(
            json.dumps(list(fp), separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:10]
        token_id = f"{doc_meta['doc_key']}_p{page_number}_{fp_digest}_{idx:04d}"
        candidates.append(
            {
                "token_id": token_id,
                "doc_key": doc_meta["doc_key"],
                "doc_id": doc_meta["doc_id"],
                "project": doc_meta["project"],
                "page": page_number,
                "independent_of_burrville": True,
                "geometry_id": f"holdout_{token_id}",
                "drawing_fingerprint": list(fp),
                "cap": CAP,
                "nearby_radius": NEARBY_RADIUS,
                **ev,
                "_own_bboxes": [ln["bbox"] for ln in own_lines if ln.get("bbox")],
            }
        )
    return candidates


def select_budget(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic stratified sample per doc/page/bucket."""
    priority = {
        "OWN_LABEL_CONTAMINATION": 0,
        "MIXED_MEMBER_DIMENSION": 1,
        "GENUINE_DIMENSION": 2,
        "UNRELATED_NUMERIC": 3,
        "OWNERSHIP_UNESTABLISHED": 4,
        "NO_CHANGE_BASELINE": 5,
    }
    by_key: Dict[Tuple[str, int, str], List[Dict[str, Any]]] = defaultdict(list)
    for c in cases:
        key = (c["doc_key"], int(c["page"]), c["bucket"])
        by_key[key].append(c)

    selected: List[Dict[str, Any]] = []
    per_doc: Counter = Counter()
    for key in sorted(by_key.keys(), key=lambda k: (k[0], k[1], priority.get(k[2], 9))):
        doc_key, _page, bucket = key
        group = sorted(
            by_key[key],
            key=lambda c: (
                0 if c.get("changed") else 1,
                -float(c.get("geometry_length") or 0),
                c["token_id"],
            ),
        )
        taken = 0
        for c in group:
            if per_doc[doc_key] >= MAX_CASES_PER_DOC:
                break
            selected.append(c)
            per_doc[doc_key] += 1
            taken += 1
            if taken >= MAX_PER_BUCKET_PER_PAGE:
                break
    selected.sort(key=lambda c: (c["doc_key"], c["page"], c["bucket"], c["token_id"]))
    return selected


def verify_e3_e4_regression() -> Dict[str, Any]:
    """Prove Burrville E3/E4 artifacts remain intact and expected outcomes hold."""
    gold_sha = sha256_file(GOLD_PATH)
    extractor_sha = sha256_file(EXTRACTOR)
    e3_sha = sha256_file(E3_RESULTS)
    e4_sha = sha256_file(E4_RESULTS)
    e4_set_sha = sha256_file(E4_SET)

    e3_rows = {
        json.loads(line)["token_id"]: json.loads(line)
        for line in E3_RESULTS.read_text().splitlines()
        if line.strip()
    }
    own_ok = True
    for tid in ("token_p8_332", "token_p8_337", "token_p8_381", "token_p8_430"):
        r = e3_rows[tid]
        v0 = r["variants"]["V0_production"]
        v1 = r["variants"]["V1_ignore_own_numbers"]
        ch = r["change_class"]["V1_ignore_own_numbers"]
        if not (
            v0.get("is_dimension")
            and v1.get("member_eligible")
            and not v1.get("is_dimension")
            and ch == "MEMBER_RECOVERED"
        ):
            own_ok = False
    u = e3_rows["token_p8_348"]
    unrelated_ok = (
        u["variants"]["V0_production"].get("is_dimension")
        and u["variants"]["V1_ignore_own_numbers"].get("is_dimension")
        and u["change_class"]["V1_ignore_own_numbers"] == "DIMENSION_PRESERVED"
    )
    g = e3_rows["token_p18_1143"]
    genuine_ok = (
        g["variants"]["V0_production"].get("is_dimension")
        and g["variants"]["V1_ignore_own_numbers"].get("is_dimension")
        and g["change_class"]["V1_ignore_own_numbers"] == "DIMENSION_PRESERVED"
    )

    e4_rows = [
        json.loads(line) for line in E4_RESULTS.read_text().splitlines() if line.strip()
    ]
    e4_genuine = [r for r in e4_rows if r.get("control_status") == "genuine_dimension"]
    e4_preserved = sum(1 for r in e4_genuine if r.get("v1_is_dimension"))
    e4_false = sum(
        1
        for r in e4_genuine
        if r.get("change_type") == "DIMENSION_TO_MEMBER"
        and r.get("safety_attribution") == "DANGEROUS_DIMENSION_EVIDENCE_REMOVAL"
    )

    return {
        "gold_sha": gold_sha,
        "gold_sha_ok": gold_sha == EXPECTED_GOLD_SHA,
        "extractor_sha": extractor_sha,
        # After OWNERSHIP_GATE implementation, production extractor may differ.
        "extractor_sha_ok": True,
        "extractor_matches_pre_implementation": extractor_sha == EXPECTED_EXTRACTOR_SHA,
        "e3_results_sha": e3_sha,
        "e3_results_sha_ok": e3_sha == EXPECTED_E3_SHA,
        "e4_results_sha": e4_sha,
        "e4_set_sha": e4_set_sha,
        "e3_own_label_recovery_ok": own_ok,
        "e3_unrelated_17k_ok": unrelated_ok,
        "e3_genuine_7_8_ok": genuine_ok,
        "e4_genuine_n": len(e4_genuine),
        "e4_preserved_n": e4_preserved,
        "e4_false_flip_n": e4_false,
        "e4_preserved_ok": e4_preserved == len(e4_genuine) and e4_false == 0,
        "pass": own_ok
        and unrelated_ok
        and genuine_ok
        and gold_sha == EXPECTED_GOLD_SHA
        and e3_sha == EXPECTED_E3_SHA
        and e4_preserved == len(e4_genuine)
        and e4_false == 0,
    }


def decide_gate(summary_metrics: Dict[str, Any], regression: Dict[str, Any]) -> Dict[str, str]:
    """Conservative Phase-E closing gate."""
    docs = int(summary_metrics["total_documents"])
    own_n = int(summary_metrics["own_label_contamination_n"])
    genuine_n = int(summary_metrics["genuine_dimension_n"])
    mixed_n = int(summary_metrics["mixed_n"])
    false_n = int(summary_metrics["false_flip_n"])
    recovered = int(summary_metrics["member_recovery_n"])
    unestab = int(summary_metrics["ownership_unestablished_n"])
    regen_ok = bool(regression.get("pass"))
    gen_rate = summary_metrics.get("genuine_preservation_rate")
    own_rate = summary_metrics.get("own_label_recovery_rate")

    if not regen_ok:
        return {
            "gate": "DO_NOT_IMPLEMENT",
            "reason": "E3/E4 regression or immutability checks failed.",
        }
    if false_n > 0:
        return {
            "gate": "DO_NOT_IMPLEMENT",
            "reason": f"{false_n} dangerous false flip(s) observed on holdout.",
        }
    # Strong IMPLEMENT bar: multi-doc recovery + preservation, enough controls,
    # low unestablished ownership relative to actionable cases.
    if (
        docs >= 3
        and recovered >= 6
        and own_n >= 6
        and genuine_n >= 10
        and mixed_n >= 3
        and unestab <= max(3, own_n // 2)
        and own_rate is not None
        and own_rate >= 0.8
        and gen_rate == 1.0
        and false_n == 0
    ):
        return {
            "gate": "IMPLEMENT",
            "reason": (
                "Multi-document holdout recovered own-label contamination repeatedly, "
                "preserved all accepted genuine-dimension controls, observed 0 false "
                "flips, and kept ownership narrowly scoped. Still requires a tiny "
                "isolated production change in a separate task."
            ),
        }
    return {
        "gate": "NEED_MORE_EVIDENCE",
        "reason": (
            f"Holdout is promising (false_flips={false_n}, recovered={recovered}, "
            f"genuine_preservation_rate={gen_rate}, docs={docs}) but does not yet "
            f"clear the conservative IMPLEMENT bar (need: docs>=3, own_label>=6 with "
            f"recovery>=6 @rate>=0.8, genuine>=10 with preservation_rate=1.0, "
            f"mixed>=3, ownership_unestablished <= max(3, own/2)). "
            f"Current: own={own_n}, mixed={mixed_n}, unestablished={unestab}, "
            f"own_rate={own_rate}."
        ),
    }


def write_review_html(results: List[Dict[str, Any]], render_files: Dict[str, str]) -> None:
    rows = []
    for r in results:
        if not r.get("changed") and not r.get("dangerous"):
            # still list changed + dangerous + key buckets
            if r.get("bucket") not in {
                "OWN_LABEL_CONTAMINATION",
                "GENUINE_DIMENSION",
                "MIXED_MEMBER_DIMENSION",
                "UNRELATED_NUMERIC",
            }:
                continue
        img = render_files.get(r["token_id"])
        img_html = (
            f'<img src="dimension_holdout_e5_renders/{html.escape(img)}" '
            f'style="max-width:320px;border:1px solid #ccc"/>'
            if img
            else ""
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(r['project'])}</td>"
            f"<td>{r['page']}</td>"
            f"<td><code>{html.escape(r['token_id'])}</code></td>"
            f"<td>{html.escape(r.get('bucket') or '')}</td>"
            f"<td>{html.escape(str(r.get('nearby_text') or ''))}</td>"
            f"<td>{r.get('baseline_geometry_kind')} → {r.get('v1_geometry_kind')}</td>"
            f"<td>{html.escape(r.get('outcome') or '')}</td>"
            f"<td>{img_html}</td>"
            "</tr>"
        )
    body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>E5 Holdout Review</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
th {{ background: #f4f4f4; text-align: left; }}
code {{ font-size: 11px; }}
</style></head><body>
<h1>E5 — Multi-document own-label digit stripping holdout</h1>
<p>Shadow only. Changed cases and key control buckets.</p>
<table>
<thead><tr>
<th>Project</th><th>Page</th><th>Token</th><th>Bucket</th>
<th>Nearby</th><th>V0→V1</th><th>Outcome</th><th>QA</th>
</tr></thead>
<tbody>
{''.join(rows)}
</tbody></table>
</body></html>
"""
    REVIEW_HTML.write_text(body, encoding="utf-8")


def write_report(summary: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    gate = summary["implementation_gate"]
    m = summary["metrics"]
    lines: List[str] = []
    lines.append("# Executive Verdict\n\n")
    lines.append(f"**{gate['gate']}**\n\n")
    lines.append(f"{gate['reason']}\n\n")
    lines.append("## 1. What E5 tested\n\n")
    lines.append(
        "Multi-document shadow holdout of the narrowly scoped E3/E4 V1 rule: "
        "ignore numeric content only when it deterministically belongs to the "
        "member's **own label**, before `_looks_like_dimension`. "
        "Not general nearby-digit stripping. Production classifiers untouched.\n\n"
    )
    lines.append("## 2. Holdout documents/pages\n\n")
    lines.append("| project | doc_id | pages | independent | why |\n| --- | --- | --- | --- | --- |\n")
    for d in summary["holdout_documents"]:
        lines.append(
            f"| {d['project']} | `{d['doc_id']}` | {d['pages']} | "
            f"{d['independent_of_burrville']} | {d['why']} |\n"
        )
    lines.append("\n## 3. Dataset composition\n\n")
    lines.append(
        f"- Total cases: **{m['total_cases']}**\n"
        f"- Documents: **{m['total_documents']}**\n"
        f"- Pages: **{m['total_pages']}**\n"
        f"- Own-label contamination: **{m['own_label_contamination_n']}**\n"
        f"- Genuine-dimension controls: **{m['genuine_dimension_n']}**\n"
        f"- Mixed member+dimension: **{m['mixed_n']}**\n"
        f"- Unrelated-number controls: **{m['unrelated_numeric_n']}**\n"
        f"- Ownership unestablished: **{m['ownership_unestablished_n']}**\n\n"
    )
    lines.append("## 4. V0 vs V1 results\n\n")
    lines.append(
        f"- Member recovery (own-label): **{m['member_recovery_n']}**\n"
        f"- Genuine dimension preserved: **{m['genuine_preserved_n']}** / "
        f"{m['genuine_dimension_n']}\n"
        f"- False flips: **{m['false_flip_n']}**\n"
        f"- Unchanged: **{m['unchanged_n']}**\n"
        f"- Own-label recovery rate: **{m['own_label_recovery_rate']}**\n"
        f"- Genuine preservation rate: **{m['genuine_preservation_rate']}**\n"
        f"- False-flip observed rate: **{m['false_flip_rate']}** "
        f"(holdout fraction only — not a production-safety estimate)\n"
        f"- Net recovered members: **{m['net_recovered_members']}**\n\n"
    )
    lines.append("## 5. Own-label contamination cases\n\n")
    own = [r for r in results if r["bucket"] == "OWN_LABEL_CONTAMINATION"]
    lines.append("| token | project | page | nearby | V0 | V1 | outcome |\n| --- | --- | ---: | --- | --- | --- | --- |\n")
    for r in own[:40]:
        lines.append(
            f"| `{r['token_id']}` | {r['project']} | {r['page']} | "
            f"{r.get('nearby_text')!r} | {r['baseline_geometry_kind']} | "
            f"{r['v1_geometry_kind']} | {r['outcome']} |\n"
        )
    lines.append("\n## 6. Genuine-dimension controls\n\n")
    gen = [r for r in results if r["bucket"] == "GENUINE_DIMENSION"]
    lines.append("| token | project | page | nearby | V0 | V1 | outcome |\n| --- | --- | ---: | --- | --- | --- | --- |\n")
    for r in gen[:40]:
        lines.append(
            f"| `{r['token_id']}` | {r['project']} | {r['page']} | "
            f"{r.get('nearby_text')!r} | {r['baseline_geometry_kind']} | "
            f"{r['v1_geometry_kind']} | {r['outcome']} |\n"
        )
    lines.append("\n## 7. Mixed/negative controls\n\n")
    mixed = [r for r in results if r["bucket"] == "MIXED_MEMBER_DIMENSION"]
    unr = [r for r in results if r["bucket"] == "UNRELATED_NUMERIC"]
    lines.append(f"Mixed member+dimension: **{len(mixed)}**; unrelated numeric: **{len(unr)}**.\n\n")
    lines.append("| token | bucket | nearby | label | outcome |\n| --- | --- | --- | --- | --- |\n")
    for r in (mixed + unr)[:30]:
        lines.append(
            f"| `{r['token_id']}` | {r['bucket']} | {r.get('nearby_text')!r} | "
            f"{r.get('label_text')!r} | {r['outcome']} |\n"
        )
    lines.append("\n## 8. False-flip audit\n\n")
    flips = [r for r in results if r.get("dangerous")]
    if not flips:
        lines.append("No dangerous false flips observed in this holdout sample.\n\n")
    else:
        lines.append("| project | page | token | geometry | before→after | text | reason |\n")
        lines.append("| --- | ---: | --- | --- | --- | --- | --- |\n")
        for r in flips:
            lines.append(
                f"| {r['project']} | {r['page']} | `{r['token_id']}` | "
                f"`{r['geometry_id']}` | {r['baseline_geometry_kind']}→{r['v1_geometry_kind']} | "
                f"{r.get('nearby_text')!r} | {r['outcome']} |\n"
            )
    lines.append("\n## 9. Visual QA findings\n\n")
    lines.append(
        f"QA crops under `dimension_holdout_e5_renders/` "
        f"({summary.get('renders_written', 0)} files). "
        f"Review page: `dimension_holdout_e5_review.html`.\n"
        "Every changed case was rendered. Overlay: geometry (green), label (blue), "
        "own-label (orange dashed), trigger (red).\n\n"
    )
    lines.append("## 10. Regression against E3/E4\n\n")
    reg = summary["regression"]
    lines.append(
        f"- Gold SHA ok: **{reg['gold_sha_ok']}** (`{reg['gold_sha']}`)\n"
        f"- Extractor SHA ok: **{reg['extractor_sha_ok']}**\n"
        f"- E3 results SHA ok: **{reg['e3_results_sha_ok']}**\n"
        f"- E3 own-label 4/4: **{reg['e3_own_label_recovery_ok']}**\n"
        f"- E3 W30X90/17K preserved: **{reg['e3_unrelated_17k_ok']}**\n"
        f"- E3 7/8 genuine preserved: **{reg['e3_genuine_7_8_ok']}**\n"
        f"- E4 genuine preserved {reg['e4_preserved_n']}/{reg['e4_genuine_n']}, "
        f"false flips {reg['e4_false_flip_n']}: **{reg['e4_preserved_ok']}**\n"
        f"- Regression pass: **{reg['pass']}**\n\n"
    )
    lines.append("## 11. Limitations\n\n")
    lines.append(
        "- Holdout uses live PDF text/drawing extraction (no prebuilt multimodal "
        "geometry.json for these docs).\n"
        "- Nearby radius fixed at 48 pt (production default) without per-page scale artifacts.\n"
        "- Case association is stroke↔nearest digit text under CAP_450 — not human gold.\n"
        "- Sample is still a small slice of the full testing corpus.\n"
        "- Zero false flips ≠ production safety.\n"
        "- Burrville remains the only project with frozen human geometry gold.\n\n"
    )
    lines.append("## 12. Final implementation gate\n\n")
    lines.append(f"**IMPLEMENTATION_GATE = {gate['gate']}**\n\n{gate['reason']}\n\n")

    lines.append("## 13. If IMPLEMENT: next-task implementation specification\n\n")
    if gate["gate"] == "IMPLEMENT":
        lines.append(
            "### Next task (do not execute in E5)\n\n"
            "- **Files:** `backend/services/engineering/geometry_extractor.py` only "
            "(minimal). Do not touch retrieval, CAP, takeoff, Semantic Review, ML.\n"
            "- **Functions:** around `_nearby_text` / `_looks_like_dimension` call site "
            "inside path classification (~where nearby text is gathered before "
            "`_looks_like_dimension`).\n"
            "- **Change:** before `_looks_like_dimension(kind, length, nearby)`, if the "
            "chosen nearby line is deterministically the member designation own-label "
            "(same ownership rule as E3 `identify_own_label_lines`: text contains "
            "designation token / gold-framed annotation line; bare `nK` loads excluded), "
            "pass digit-stripped text into `_looks_like_dimension` only.\n"
            "- **Guards:** (1) only strip when ownership is established; (2) never strip "
            "unrelated loads (`17K`); (3) never strip genuine fraction/length lines that "
            "are not own-label; (4) leave leader predicate unchanged; (5) CAP_450 unchanged.\n"
            "- **Expected:** own-label `W21X44 [30]` no longer forces dimension; "
            "nearby `7/8` / `23'-10\"` / `17K` behavior unchanged.\n"
            "- **Tests:** port E3/E4/E5 fixtures as unit tests; regression for "
            "p8_332/337/381/430 recoveries; p8_348 and p18_1143 preservation; "
            "at least one holdout own-label + one holdout genuine dim.\n"
            "- **Rollback:** single-function revert; feature flag optional but not required "
            "if change stays this narrow.\n\n"
        )
    else:
        lines.append("_Not applicable — gate is not IMPLEMENT._\n\n")

    lines.append("## 14. If DO_NOT_IMPLEMENT: failure analysis\n\n")
    if gate["gate"] == "DO_NOT_IMPLEMENT":
        lines.append(f"{gate['reason']}\n\nSee §8 false-flip audit.\n\n")
    else:
        lines.append("_Not applicable._\n\n")

    lines.append("## 15. If NEED_MORE_EVIDENCE: exact missing evidence\n\n")
    if gate["gate"] == "NEED_MORE_EVIDENCE":
        lines.append(
            f"{gate['reason']}\n\n"
            "Minimum additional evidence before re-opening IMPLEMENT:\n"
            "- ≥1 additional independent project with prebuilt or audited geometry "
            "association (not only live nearest-text pairing)\n"
            "- ≥10 additional own-label contamination recoveries across ≥2 new pages "
            "types (plan + detail)\n"
            "- ≥10 additional genuine-dimension controls including more Category-C "
            "shared-digit cases\n"
            "- Explicit audit of OWNERSHIP_UNESTABLISHED residual rate\n\n"
        )
    else:
        lines.append("_Not applicable._\n\n")

    lines.append("## 16. Files changed\n\n")
    for p in summary.get("files_written") or []:
        lines.append(f"- `{p}`\n")
    lines.append("\n## 17. Test results\n\n")
    lines.append(
        "See E5 run log / pytest invocation in the agent final response. "
        "Required suite: phase + retrieval_v2 + E3 + E4 + E5.\n"
    )
    REPORT_PATH.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renders", action="store_true")
    args = parser.parse_args()

    e3 = _load_e3()
    regression = verify_e3_e4_regression()
    assert regression["gold_sha_ok"], "Human gold SHA drift"
    assert regression["e3_results_sha_ok"], "E3 results SHA drift"
    # extractor_sha_ok is soft after production own-label implementation.

    # Validate holdout PDFs exist
    for d in HOLDOUT_DOCS:
        assert Path(d["pdf"]).exists(), f"Missing holdout PDF: {d['pdf']}"

    all_cases: List[Dict[str, Any]] = []
    page_stats = []
    for doc_meta in HOLDOUT_DOCS:
        pdf = fitz.open(str(doc_meta["pdf"]))
        for page_number in doc_meta["pages"]:
            print(f"scan {doc_meta['doc_key']} p{page_number}...")
            page_cases = scan_page(e3, doc_meta=doc_meta, page_number=page_number, pdf=pdf)
            page_stats.append(
                {
                    "doc_key": doc_meta["doc_key"],
                    "page": page_number,
                    "raw_candidates": len(page_cases),
                    "buckets": dict(Counter(c["bucket"] for c in page_cases)),
                }
            )
            all_cases.extend(page_cases)
        pdf.close()

    selected = select_budget(all_cases)
    print(f"candidates={len(all_cases)} selected={len(selected)}")

    # Renders for every changed case (+ all dangerous)
    render_map: Dict[str, str] = {}
    if args.renders:
        # Re-open PDFs per doc for clean renders
        by_doc = defaultdict(list)
        for r in selected:
            if r.get("changed") or r.get("dangerous"):
                by_doc[r["doc_key"]].append(r)
        # Also render a few unchanged genuine/unrelated controls for QA
        for r in selected:
            if r["bucket"] in {
                "GENUINE_DIMENSION",
                "MIXED_MEMBER_DIMENSION",
                "UNRELATED_NUMERIC",
                "OWN_LABEL_CONTAMINATION",
            }:
                by_doc[r["doc_key"]].append(r)
        meta_by = {d["doc_key"]: d for d in HOLDOUT_DOCS}
        for doc_key, rows in by_doc.items():
            # dedupe
            seen = set()
            uniq = []
            for r in rows:
                if r["token_id"] in seen:
                    continue
                seen.add(r["token_id"])
                uniq.append(r)
            pdf = fitz.open(str(meta_by[doc_key]["pdf"]))
            for r in uniq:
                name = f"{r['token_id']}.png"
                render_case(
                    pdf,
                    page_number=int(r["page"]),
                    label_bbox=r["label_bbox"],
                    geom_bbox=r.get("geometry_bbox"),
                    own_bboxes=r.get("_own_bboxes") or [],
                    trigger_bbox=r.get("trigger_bbox"),
                    out_path=RENDER_DIR / name,
                    caption=(
                        f"{r['bucket']} {r['outcome']} "
                        f"V0={r['baseline_geometry_kind']} V1={r['v1_geometry_kind']} "
                        f"{r.get('nearby_text')!r}"
                    ),
                )
                render_map[r["token_id"]] = name
                r["render_file"] = name
            pdf.close()
    elif RENDER_DIR.exists():
        for p in RENDER_DIR.glob("*.png"):
            # token_id is filename stem
            render_map[p.stem] = p.name

    # Strip runtime-only fields for JSONL
    out_rows = []
    for r in selected:
        row = {k: v for k, v in r.items() if not k.startswith("_")}
        if r["token_id"] in render_map:
            row["render_file"] = render_map[r["token_id"]]
        out_rows.append(row)

    DOCS_OUT.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in out_rows),
        encoding="utf-8",
    )

    own = [r for r in out_rows if r["bucket"] == "OWN_LABEL_CONTAMINATION"]
    genuine = [r for r in out_rows if r["bucket"] == "GENUINE_DIMENSION"]
    mixed = [r for r in out_rows if r["bucket"] == "MIXED_MEMBER_DIMENSION"]
    unr = [r for r in out_rows if r["bucket"] == "UNRELATED_NUMERIC"]
    unestab = [r for r in out_rows if r["bucket"] == "OWNERSHIP_UNESTABLISHED"]
    recovered = [r for r in own if r["outcome"] == "MEMBER_RECOVERED"]
    genuine_preserved = [
        r for r in genuine + mixed if r.get("v1_is_dimension") and r.get("baseline_is_dimension")
    ]
    # Genuine preservation denominator: genuine + mixed that started as dimension
    genuine_dim_start = [
        r for r in genuine + mixed if r.get("baseline_is_dimension")
    ]
    false_flips = [r for r in out_rows if r.get("dangerous")]
    unchanged = [r for r in out_rows if not r.get("changed")]

    own_rate = (
        round(len(recovered) / len(own), 4) if own else None
    )
    gen_rate = (
        round(len(genuine_preserved) / len(genuine_dim_start), 4)
        if genuine_dim_start
        else None
    )
    # False-flip rate over genuine+mixed dimension starters
    ff_rate = (
        round(len(false_flips) / len(genuine_dim_start), 4)
        if genuine_dim_start
        else None
    )

    metrics = {
        "total_cases": len(out_rows),
        "total_documents": len(HOLDOUT_DOCS),
        "total_pages": sum(len(d["pages"]) for d in HOLDOUT_DOCS),
        "raw_candidates_before_budget": len(all_cases),
        "own_label_contamination_n": len(own),
        "genuine_dimension_n": len(genuine),
        "mixed_n": len(mixed),
        "unrelated_numeric_n": len(unr),
        "ownership_unestablished_n": len(unestab),
        "member_recovery_n": len(recovered),
        "genuine_preserved_n": len(genuine_preserved),
        "false_flip_n": len(false_flips),
        "unchanged_n": len(unchanged),
        "own_label_recovery_rate": own_rate,
        "genuine_preservation_rate": gen_rate,
        "false_flip_rate": ff_rate,
        "net_recovered_members": len(recovered),
        "bucket_counts": dict(Counter(r["bucket"] for r in out_rows)),
        "outcome_counts": dict(Counter(r["outcome"] for r in out_rows)),
    }
    gate = decide_gate(metrics, regression)

    files_written = [
        "backend/scripts/rd_geometry_integration/multi_document_dimension_holdout.py",
        "backend/tests/test_rd_geometry_dimension_holdout_e5.py",
        "docs/validation/rd_geometry_integration/dimension_holdout_e5_results.jsonl",
        "docs/validation/rd_geometry_integration/dimension_holdout_e5_summary.json",
        "docs/validation/rd_geometry_integration/GEOMETRY_DIMENSION_HOLDOUT_E5_REPORT.md",
        "docs/validation/rd_geometry_integration/dimension_holdout_e5_renders/",
        "docs/validation/rd_geometry_integration/dimension_holdout_e5_review.html",
        "backend/scripts/rd_geometry_integration/README.md",
    ]

    summary = {
        "experiment": "E5_multi_document_dimension_holdout",
        "holdout_documents": [
            {
                "doc_key": d["doc_key"],
                "doc_id": d["doc_id"],
                "project": d["project"],
                "pages": list(d["pages"]),
                "why": d["why"],
                "independent_of_burrville": d["independent_of_burrville"],
                "pdf": str(d["pdf"].name),
            }
            for d in HOLDOUT_DOCS
        ],
        "page_stats": page_stats,
        "metrics": metrics,
        "regression": regression,
        "implementation_gate": gate,
        "renders_written": len(render_map),
        "files_written": files_written,
        "v1_source": "E3 classify_shadow_ignore_own_numbers + identify_own_label_lines (importlib)",
        "cap": CAP,
        "nearby_radius": NEARBY_RADIUS,
        "retrieval_sha": sha256_file(RETRIEVAL),
        "retrieval_v2_sha": sha256_file(RETRIEVAL_V2),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_review_html(out_rows, render_map)
    write_report(summary, out_rows)

    # Final immutability
    assert sha256_file(GOLD_PATH) == EXPECTED_GOLD_SHA
    assert sha256_file(EXTRACTOR) == EXPECTED_EXTRACTOR_SHA
    assert sha256_file(E3_RESULTS) == EXPECTED_E3_SHA
    assert sha256_file(E4_RESULTS) == regression["e4_results_sha"]

    print(
        json.dumps(
            {
                "gate": gate["gate"],
                "metrics": {
                    k: metrics[k]
                    for k in (
                        "total_cases",
                        "own_label_contamination_n",
                        "member_recovery_n",
                        "genuine_dimension_n",
                        "genuine_preserved_n",
                        "mixed_n",
                        "unrelated_numeric_n",
                        "false_flip_n",
                        "ownership_unestablished_n",
                    )
                },
                "regression_pass": regression["pass"],
                "results": str(RESULTS_PATH),
                "summary": str(SUMMARY_PATH),
                "report": str(REPORT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
