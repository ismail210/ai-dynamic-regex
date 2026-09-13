#!/usr/bin/env python3
"""
Legend/drawing-language audit scanner.
Reads real project PDFs, classifies pages, and searches for structural
notation evidence (BENT PL, plate family, rolled sections) with context.
Read-only: does not modify any repo files.
"""
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(r"C:\Users\Bassam\git\ai-dynamic-regex")
PILOT = ROOT / "backend/training/ml_association/real_project_pilot/extracted"
OUT_DIR = Path(r"C:\Users\Bassam\AppData\Local\Temp\claude\C--Users-Bassam-git-ai-dynamic-regex\05dc587c-72b2-42c0-9c89-4fbad88df7be\scratchpad\audit_out")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROJECTS = {
    "1200 K": "1200 K_Permit_Bid_Dwgs - Structural.pdf",
    "Burrville": "Burrville ES - ST.pdf",
    "GCDC Building": "GCDC Building 4 - ST1.pdf",
    "H5 Herndon": "ST.pdf",
    "Ketcham": "Structure - Copy.pdf",
    "Sidwell": "03 - SFSLS_251029_ISSUED FOR BID_2A_STRUCTURAL complied thru add 2.pdf",
    "Springhill ES": "ST - Springhill Lake.pdf",
}

LEGEND_KEYWORDS = [
    "LEGEND", "GENERAL NOTES", "GENERAL STRUCTURAL NOTES", "ABBREVIATION",
    "SYMBOL", "KEY NOTES", "KEYNOTES", "TYPICAL DETAIL", "STANDARD DETAIL",
    "SCHEDULE", "NOTES:", "ERECTION NOTES", "FRAMING NOTES", "STEEL NOTES",
    "MATERIAL NOTES", "WELD SYMBOL", "BOLT NOTES", "SHEET INDEX", "DRAWING INDEX",
    "SPECIAL INSPECTION", "DESIGN CRITERIA", "CODE",
]

ROLLED_SECTION_RE = re.compile(
    r"\b(?:W|S|M|HP|C|MC|L|2L|WT|ST|MT|HSS|TS|PIPE)\s*[-_]?\s*"
    r"\d+(?:\.\d+)?(?:\s*[Xx\u00d7]\s*(?:\d+(?:\.\d+)?|\d+/\d+)){0,3}\b"
)

PLATE_FAMILY_RE = re.compile(
    r"\bBENT\s*[-_.]?\s*PL(?:ATE)?\b"
    r"|\bBENTPL\b"
    r"|\bPL(?:ATE)?\s*[-_.]?\s*\d[^\n]{0,20}?\bBENT\b"
    r"|\bBASE\s*PL(?:ATE)?\b"
    r"|\bCAP\s*PL(?:ATE)?\b"
    r"|\bSTIFF(?:ENER)?\s*PL(?:ATE)?\b"
    r"|\bGUSSET\s*(?:PL(?:ATE)?)?\b"
    r"|\bCLIP\s*(?:L|ANGLE)\b"
    r"|\bBENT\s*(?:ANGLE|BAR|L)\b"
    r"|\bFLAT\s*BAR\b"
    r"|\bCONN(?:ECTION)?\s*PL(?:ATE)?\b",
    re.IGNORECASE,
)

BENT_STRICT_RE = re.compile(r"BENT", re.IGNORECASE)
PL_TOKEN_RE = re.compile(r"\bPL\b|\bPLATE\b", re.IGNORECASE)


def is_raster_page(page):
    text = page.get_text().strip()
    images = page.get_images(full=True)
    return len(text) < 30 and len(images) > 0


def classify_legend_score(text_upper):
    score = 0
    hits = []
    for kw in LEGEND_KEYWORDS:
        c = text_upper.count(kw)
        if c:
            score += c
            hits.append((kw, c))
    return score, hits


def context_window(full_text, start, end, radius=60):
    lo = max(0, start - radius)
    hi = min(len(full_text), end + radius)
    return full_text[lo:hi].replace("\n", " \\n ")


def scan_pdf(project, pdf_path):
    result = {
        "project": project,
        "file": str(pdf_path),
        "page_count": 0,
        "pages": [],
        "legend_candidate_pages": [],
        "bent_hits": [],
        "plate_family_hits": [],
        "rolled_section_hits_by_page": {},
    }
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    result["page_count"] = doc.page_count

    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        try:
            text = page.get_text() or ""
        except Exception as e:
            result["pages"].append({"page": pno + 1, "error": str(e)})
            continue
        text_upper = text.upper()
        raster = is_raster_page(page)
        legend_score, legend_hits = classify_legend_score(text_upper)

        rolled_hits = ROLLED_SECTION_RE.findall(text_upper)
        page_info = {
            "page": pno + 1,
            "text_length": len(text),
            "raster_suspected": raster,
            "legend_score": legend_score,
            "legend_keyword_hits": legend_hits,
            "rolled_section_count": len(rolled_hits),
        }
        result["pages"].append(page_info)
        if legend_score >= 2:
            result["legend_candidate_pages"].append(pno + 1)
        if rolled_hits:
            result["rolled_section_hits_by_page"][pno + 1] = rolled_hits[:40]

        # BENT search with context
        for m in BENT_STRICT_RE.finditer(text):
            ctx = context_window(text, m.start(), m.end())
            result["bent_hits"].append({
                "page": pno + 1,
                "match_context": ctx,
            })

        for m in PLATE_FAMILY_RE.finditer(text):
            ctx = context_window(text, m.start(), m.end())
            result["plate_family_hits"].append({
                "page": pno + 1,
                "match": m.group(0),
                "match_context": ctx,
            })

    doc.close()
    return result


def main():
    summary = {}
    for project, filename in PROJECTS.items():
        pdf_path = PILOT / project / filename
        if not pdf_path.exists():
            summary[project] = {"error": f"missing file {pdf_path}"}
            continue
        print(f"Scanning {project} ...", file=sys.stderr)
        res = scan_pdf(project, pdf_path)
        summary[project] = res
        out_file = OUT_DIR / f"{project.replace(' ', '_')}.json"
        out_file.write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"  pages={res.get('page_count')} legend_candidates={len(res.get('legend_candidate_pages', []))} bent_hits={len(res.get('bent_hits', []))} plate_family_hits={len(res.get('plate_family_hits', []))}", file=sys.stderr)

    # Compact cross-project summary
    compact = {}
    for project, res in summary.items():
        if "error" in res and "page_count" not in res:
            compact[project] = res
            continue
        compact[project] = {
            "page_count": res["page_count"],
            "legend_candidate_pages": res["legend_candidate_pages"],
            "bent_hit_count": len(res["bent_hits"]),
            "bent_hit_pages": sorted(set(h["page"] for h in res["bent_hits"])),
            "plate_family_hit_count": len(res["plate_family_hits"]),
            "plate_family_pages": sorted(set(h["page"] for h in res["plate_family_hits"])),
            "raster_pages": [p["page"] for p in res["pages"] if p.get("raster_suspected")],
        }
    (OUT_DIR / "_summary.json").write_text(json.dumps(compact, indent=2), encoding="utf-8")
    print("DONE", file=sys.stderr)


if __name__ == "__main__":
    main()
