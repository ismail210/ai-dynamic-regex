#!/usr/bin/env python3
"""Build HUMAN-CURATED extraction gold from native PDF words (isolated eval).

Rules (applied deliberately; regex candidates are NOT auto-accepted):
  ACCEPT section designations W/WT/S/M/HP/MC/C#X#/HSS/L/2L/PL/PIPE on selected pages
  ACCEPT product-supported marks BP#, CL#, C#, L#, and hyphenated C-# / L-#
  REJECT bare C/L when context is area labels, grid lines, or camber (c = …)
  REJECT sheet refs S-### and material grades
  Unique key: (document_id, page, normalized) — presence on page

Usage (from backend/):
  python scripts/extraction_gold_eval/build_gold.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"

DOCS = {
    "struct": {
        "path": "/Users/hibareda/Desktop/Estima 3D/Struct.pdf",
        "name": "Struct.pdf",
        "project": "Estima 3D — Struct (known high-density structural)",
        "why": "Primary high-density native-text ST package; dense W/HSS + BP/CL marks",
        "pages": [8, 10, 14],
    },
    "burrville_st": {
        "path": str(ROOT / "uploads" / "Burrville ES - ST__0d910a43b4a0.pdf"),
        "name": "Burrville ES - ST.pdf",
        "project": "51 - Burrville ES (ST package in uploads)",
        "why": "Explicitly requested ST PDF; framing + detail + schedule pages",
        "pages": [7, 10, 18, 29],
    },
    "st_generic": {
        "path": str(ROOT / "uploads" / "ST.pdf"),
        "name": "ST.pdf",
        "project": "uploads/ST.pdf structural package",
        "why": "Additional native ST set with HSS columns and hyphenated C-# marks",
        "pages": [8, 9, 19],
    },
    "spring_garden": {
        "path": "/Users/hibareda/Desktop/Estima 3D/ST-Spring Garden ES.pdf",
        "name": "ST-Spring Garden ES.pdf",
        "project": "Estima 3D — Spring Garden ES ST",
        "why": "Smaller ST set with column marks C1–C5 and lintel L1/L1A",
        "pages": [3, 8],
    },
}

SECTION_RE = re.compile(
    r"^(?:W|WT|M|HP|MC|C|S)\d+(?:\.\d+)?X\d+(?:\.\d+)?$",
    re.I,
)
HSS_RE = re.compile(
    r"^HSS\d+(?:\.\d+)?(?:X\d+(?:\.\d+)?){1,2}(?:X(?:\d+/\d+|\d+(?:\.\d+)?))?$",
    re.I,
)
ANGLE_RE = re.compile(
    r"^(?:2L|L)\d+(?:-\d+/\d+)?(?:X\d+(?:-\d+/\d+)?){1,2}"
    r"(?:X(?:\d+/\d+|\d+(?:\.\d+)?))?$",
    re.I,
)
PL_RE = re.compile(
    r"^PL(?:ATE)?(?:\d+(?:\.\d+)?|\d+/\d+)(?:X(?:\d+(?:\.\d+)?|\d+/\d+)){0,2}$",
    re.I,
)
PIPE_RE = re.compile(r"^PIPE\d+(?:\.\d+)?$", re.I)
MARK_RE = re.compile(r"^(?:BP|CL|L|C)-?\d+[A-Z]?$", re.I)
BARE_RE = re.compile(r"^(?:BP|CL|C|L)$", re.I)


def _norm(raw: str) -> str:
    return re.sub(r"\s+", "", str(raw or "")).upper().replace("×", "X")


def _category(u: str) -> str:
    if u == "C":
        return "annotation_C"
    if u == "L":
        return "annotation_L"
    if u == "CL":
        return "annotation_CL"
    if u == "BP":
        return "annotation_BP"
    if re.match(r"^BP-?\d", u):
        return "annotation_BP"
    if re.match(r"^CL-?\d", u):
        return "annotation_CL"
    if re.match(r"^C-?\d", u) and MARK_RE.match(u):
        return "member_mark"
    if re.match(r"^L-?\d", u) and MARK_RE.match(u):
        return "member_mark"
    if u.startswith("HSS"):
        return "HSS"
    if u.startswith("2L") or (u.startswith("L") and "X" in u):
        return "angle_designation"
    if u.startswith("PL"):
        return "plate"
    if u.startswith("C") and "X" in u:
        return "channel"
    if u.startswith(("W", "WT", "M", "HP", "MC", "S")):
        return "section_designation"
    return "other_supported_steel"


def _incomplete_angle(u: str) -> bool:
    if not re.match(r"^(?:2L|L)\d", u):
        return False
    body = u[2:] if u.startswith("2L") else u[1:]
    return body.count("X") == 1


def _reject_bare(normalized: str, context: str) -> tuple[bool, str]:
    ctx = (context or "").upper()
    if normalized == "C":
        if "AREA C" in ctx or re.search(r"\bAREA\s+C\b", ctx):
            return True, "area_label_not_steel"
        if re.search(r"\bC\s*=", ctx) or "CAMBER" in ctx:
            return True, "camber_notation"
        # Detail callout letter pointing at a sheet: "C S503", "C S-501"
        if re.search(r"\bC\s+S-?\d", ctx):
            return True, "sheet_detail_callout_letter"
        if not any(t in ctx for t in ("W", "HSS", "BP", "CL", "BEAM", "COL", "STEEL", "CHANNEL", "C12", "C8")):
            return True, "insufficient_steel_context"
        return False, "possible_steel_abbrev"
    if normalized == "L":
        if re.search(r"\bK\.?\d*\s+L\s+M", ctx) or re.search(r"\bL\s+M\.?\d*", ctx):
            return True, "grid_line_letter"
        if re.search(r"\bL\s+S-?\d", ctx):
            return True, "sheet_detail_callout_letter"
        if "ENGINEERS LANE" in ctx or "DOCUMENTS WERE PREPARED" in ctx:
            return True, "title_block_noise"
        if not any(t in ctx for t in ("W", "HSS", "ANGLE", "L4", "L5", "2L", "BP", "CL")):
            return True, "insufficient_steel_context"
        return False, "possible_steel_abbrev"
    if normalized in ("CL", "BP"):
        return False, "bare_abbrev"
    return False, "ok"


def build() -> dict:
    gold_items: list[dict] = []
    rejected: list[dict] = []
    doc_meta: list[dict] = []

    for doc_id, meta in DOCS.items():
        path = Path(meta["path"])
        if not path.exists():
            raise FileNotFoundError(path)
        doc = fitz.open(path)
        sample_words = sum(len(doc[i].get_text("words")) for i in range(min(3, doc.page_count)))
        native = sample_words > 50
        doc_meta.append(
            {
                "document_id": doc_id,
                "document_name": meta["name"],
                "path": str(path),
                "project": meta["project"],
                "why_selected": meta["why"],
                "page_count": doc.page_count,
                "native_text_vs_scanned": "native_text" if native else "likely_scanned_or_empty",
                "gold_pages": meta["pages"],
            }
        )
        for pn in meta["pages"]:
            page = doc[pn - 1]
            words = page.get_text("words")
            for w in words:
                raw = w[4]
                compact = _norm(raw)
                kind = None
                if (
                    SECTION_RE.match(compact)
                    or HSS_RE.match(compact)
                    or ANGLE_RE.match(compact)
                    or PL_RE.match(compact)
                    or PIPE_RE.match(compact)
                ):
                    kind = "designation"
                elif MARK_RE.match(compact):
                    kind = "mark"
                elif BARE_RE.match(compact):
                    kind = "bare_annotation"
                else:
                    continue

                cx = (w[0] + w[2]) / 2
                cy = (w[1] + w[3]) / 2
                nearby = [
                    w2[4]
                    for w2 in words
                    if abs(((w2[0] + w2[2]) / 2) - cx) < 130
                    and abs(((w2[1] + w2[3]) / 2) - cy) < 45
                ]
                context = " ".join(nearby[:14])

                if kind == "bare_annotation":
                    reject, reason = _reject_bare(compact, context)
                    if reject:
                        rejected.append(
                            {
                                "document_id": doc_id,
                                "page": pn,
                                "raw_text": raw,
                                "normalized": compact,
                                "reason": reason,
                                "context": context[:160],
                            }
                        )
                        continue

                gold_items.append(
                    {
                        "document_id": doc_id,
                        "document": meta["name"],
                        "page": pn,
                        "raw_text": raw,
                        "normalized": compact,
                        "category": _category(compact),
                        "kind": kind,
                        "bbox": [round(v, 1) for v in (w[0], w[1], w[2], w[3])],
                        "context": context[:180],
                        "source": "pdf_native_word_human_curated",
                        "evidence": "visible on structural sheet (native PDF text)",
                        "ambiguity_flag": kind == "bare_annotation",
                        "incomplete_angle": _incomplete_angle(compact),
                        "human_verified": True,
                        "verification_notes": (
                            "Accepted after context review"
                            if kind == "bare_annotation"
                            else "Unique page presence of in-scope steel designation/mark"
                        ),
                    }
                )
        doc.close()

    uniq: dict[tuple, dict] = {}
    for item in gold_items:
        key = (item["document_id"], item["page"], item["normalized"])
        if key not in uniq:
            uniq[key] = item

    rows = []
    for i, item in enumerate(
        sorted(uniq.values(), key=lambda r: (r["document_id"], r["page"], r["normalized"]))
    ):
        item = dict(item)
        item["gold_id"] = f"xg{i+1:04d}"
        rows.append(item)

    payload = {
        "schema": "extraction_gold_eval_v1",
        "purpose": "EXTRACTION-ONLY human-curated gold; not takeoff/prediction gold",
        "unit": "unique (document, page, normalized) presence",
        "documents": doc_meta,
        "rejected_bare_annotations": rejected,
        "count": len(rows),
        "human_verified_count": len(rows),
        "rows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "extraction_gold.json"
    path.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(rows)} gold items -> {path}")
    print(f"Rejected bare annotations: {len(rejected)}")
    print("by category:", Counter(r["category"] for r in rows).most_common())
    print("incomplete_angle:", sum(1 for r in rows if r["incomplete_angle"]))
    print("by doc:", Counter(r["document_id"] for r in rows))
    return payload


if __name__ == "__main__":
    build()
