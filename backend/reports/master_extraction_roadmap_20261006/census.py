"""Native-text census of the benchmark PDFs. Reads text only; writes census.json here."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import fitz

BACKEND = Path(__file__).resolve().parents[2]
DESKTOP = Path("/Users/hibareda/Desktop/Testing Projects")
PDFS = {
    "furley": BACKEND / "uploads" / "Struct.pdf",
    "burrville": BACKEND / "uploads" / "Burrville ES - ST.pdf",
    "brandywine": BACKEND / "uploads" / "Structural4__3aa51f661bdf.pdf",
    "springhill": BACKEND / "uploads" / "ST - Springhill Lake__f6ddc4a7e233.pdf",
    "osse": DESKTOP / "OSSE - ST.pdf",
    "yellowspring": DESKTOP / "ST1.pdf",
    "washlatin": DESKTOP / "New bldg - St.pdf",
    "fortdavis": DESKTOP / "Structure - Copy1 - edit.pdf",
}

SHEET_RE = re.compile(r"\bS-?\d{1,2}(?:\.\d{1,2}|\d{1,2})[A-Z]?\b")
# detail / section callouts written as number-or-letter over sheet id
DETAIL_CALLOUT_RE = re.compile(r"\b([A-Z]?\d{1,2}|[A-Z])\s*/\s*(S-?\d{1,2}(?:\.\d{1,2}|\d{1,2})[A-Z]?(?:-[A-Z]\b)?)")
SEE_RE = re.compile(r"\bSEE\s+(?:DETAIL|SECTION|SHEET|SCHEDULE|PLAN|ARCH\w*|TYP\w*)\b", re.I)
SECTION_AA_RE = re.compile(r"\bSECTION\s+([A-Z0-9])\s*-\s*\1\b")
MATCH_RE = re.compile(r"\bMATCH\s*LINE\b", re.I)
TYP_RE = re.compile(r"\bTYP(?:ICAL)?\.?\b")
SIM_RE = re.compile(r"\bSIM(?:ILAR)?\.?\b")
REV_RE = re.compile(r"\bREV(?:ISION)?\.?\s*(?:NO\.?\s*)?\d+\b|\bADDENDUM\b|\bBULLETIN\b|\bASI\s*#?\d+", re.I)
SCOPE_RE = {
    "existing": re.compile(r"\bEXISTING\b|\(E\)", re.I),
    "new": re.compile(r"\bNEW\b|\(N\)"),
    "demolition": re.compile(r"\bDEMO(?:LITION|LISH)?\b", re.I),
    "alternate": re.compile(r"\bALTERNATE\b|\bADD\s+ALT\b|\bBID\s+ALT", re.I),
    "phase": re.compile(r"\bPHASE\s+\d\b", re.I),
    "future": re.compile(r"\bFUTURE\b", re.I),
}
TITLE_KINDS = {
    "foundation_plan": r"FOUNDATION\s+PLAN|FOOTING\s+PLAN",
    "framing_plan": r"FRAMING\s+PLAN",
    "roof_framing": r"ROOF\s+FRAMING",
    "schedule": r"\b(?:COLUMN|BEAM|LINTEL|PIER|FOOTING|BASE\s+PLATE|BEARING\s+PLATE|BRACE|JOIST)\s+SCHEDULE",
    "details": r"\bDETAILS?\b",
    "sections": r"\bSECTIONS?\b",
    "elevations": r"\bELEVATIONS?\b",
    "general_notes": r"GENERAL\s+NOTES|STRUCTURAL\s+NOTES",
    "special_inspections": r"SPECIAL\s+INSPECTION",
}
STEEL_RE = re.compile(r"\b(?:W\d{1,2}X\d{1,3}|HSS\d+(?:\.\d+)?X\d+(?:\.\d+)?(?:X\d+/\d+|X\.\d+)?|L\d+X\d+(?:X\d+/\d+)?|C\d+X\d+|MC\d+X\d+|WT\d+X\d+)\b", re.I)
INCOMPLETE_L_RE = re.compile(r"\b2?L\d{1,2}X\d{1,2}(?![X\d/])", re.I)
GRID_PAIR_RE = re.compile(r"\b[A-Z]{1,2}(?:\.\d)?'{0,2}\s*-\s*\d{1,2}(?:\.\d)?'{0,2}\b")
GRADE_RE = re.compile(r"\bASTM\s+A\d{2,4}\b|\bA992\b|\bA500\b|\bA36\b|\bF1554\b|\bA325\b|\bA490\b|\bF3125\b", re.I)


def census(key: str, path: Path) -> dict:
    out = {"key": key, "path": str(path), "exists": path.exists()}
    if not path.exists():
        return out
    doc = fitz.open(str(path))
    out["page_count"] = doc.page_count
    totals: Counter = Counter()
    title_pages: dict = {k: [] for k in TITLE_KINDS}
    rotated, low_text, callouts, sheets = [], [], Counter(), set()
    callout_targets = Counter()
    for index, page in enumerate(doc):
        number = index + 1
        text = page.get_text() or ""
        words = len(text.split())
        if page.rotation:
            rotated.append(number)
        if words < 40:
            low_text.append(number)
        up = text.upper()
        for kind, pattern in TITLE_KINDS.items():
            if re.search(pattern, up):
                title_pages[kind].append(number)
        sheets.update(SHEET_RE.findall(up))
        for label, target in DETAIL_CALLOUT_RE.findall(up):
            callouts[number] += 1
            callout_targets[target.replace("-", "")] += 1
        totals["see_refs"] += len(SEE_RE.findall(text))
        totals["section_aa"] += len(SECTION_AA_RE.findall(up))
        totals["match_lines"] += len(MATCH_RE.findall(text))
        totals["typ"] += len(TYP_RE.findall(up))
        totals["sim"] += len(SIM_RE.findall(up))
        totals["revision_signals"] += len(REV_RE.findall(text))
        totals["steel_labels"] += len(STEEL_RE.findall(up))
        totals["incomplete_angles"] += len(INCOMPLETE_L_RE.findall(up))
        totals["grid_pair_like"] += len(GRID_PAIR_RE.findall(up))
        totals["grade_refs"] += len(GRADE_RE.findall(up))
        for scope, pattern in SCOPE_RE.items():
            totals[f"scope_{scope}"] += len(pattern.findall(text))
    out.update({
        "rotated_pages": rotated,
        "low_text_pages": low_text,
        "title_keyword_pages": title_pages,
        "sheet_ids_seen": len(sheets),
        "detail_callouts_total": int(sum(callouts.values())),
        "detail_callout_pages": len(callouts),
        "top_callout_targets": callout_targets.most_common(8),
        "callout_targets_seen_as_sheet_ids": sum(
            1 for target in callout_targets if target in {s.replace("-", "") for s in sheets}
        ),
        "distinct_callout_targets": len(callout_targets),
        **{k: int(v) for k, v in totals.items()},
    })
    return out


if __name__ == "__main__":
    results = [census(key, path) for key, path in PDFS.items()]
    target = Path(__file__).resolve().parent / "census.json"
    target.write_text(json.dumps(results, indent=2))
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k not in {"title_keyword_pages", "path"}}))
