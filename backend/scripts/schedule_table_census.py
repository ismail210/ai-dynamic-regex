#!/usr/bin/env python3
"""Read-only census: schedule table titles/headers/marks across structural PDFs.

Compares observed patterns to build_schedule_grids output. Not a production path.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.engineering.schedule_grid import (  # noqa: E402
    build_schedule_grids,
    is_bare_schedule_mark,
    is_schedule_table_mark,
)
from services.pdf_parser import extract_document_structure  # noqa: E402

# Unique structural / ST corpora (skip hashed duplicates, damage tests, arch/mech).
PDFS = [
    BACKEND / "uploads" / "ST.pdf",
    BACKEND / "uploads" / "Struct.pdf",
    BACKEND / "uploads" / "Burrville ES - ST.pdf",
    BACKEND / "uploads" / "1200 K_Permit_Bid_Dwgs - Structural.pdf",
    BACKEND / "uploads" / "GCDC Building 4 - ST1__47dc7ef27f6e.pdf",
    BACKEND / "uploads" / "ST - Springhill Lake__f6ddc4a7e233.pdf",
    BACKEND / "uploads" / "ST-Elmer Wolfe ES__0cbd857dc6c2.pdf",
    BACKEND / "uploads" / "ST-Robert Moton ES__258cb166b79f.pdf",
    BACKEND / "uploads" / "ST-Runnymede ES__4ff5b14a268a.pdf",
    BACKEND
    / "uploads"
    / "03 - SFSLS_251029_ISSUED FOR BID_2A_STRUCTURAL complied thru add 2__6a9a9684bb19.pdf",
    BACKEND / "uploads" / "William Winchester ES - Bid Set - Drawings - 01-30-26__1d5e2cb2e21d.pdf",
    BACKEND / "uploads" / "Structure - Copy.pdf",
    BACKEND
    / "Testing Projects"
    / "51 - Burrvile ES"
    / "Burrville_DD Pricing Set_260317.pdf",
]

_SCHEDULE_TITLE_RE = re.compile(
    r"\b("
    r"(?:EXISTING\s+)?(?:COLUMN|BEAM|GIRDER|LINTEL|JOIST|BRACE|BRACING|"
    r"PIER|FOOTING|PILE(?:\s+CAP)?|FOUNDATION|BASE\s+PLATE|BEARING\s+PLATE|"
    r"MOMENT\s+CONNECTION|SHEAR\s+CONNECTION|WELD(?:ED)?\s+PLATE|"
    r"HSS|PIPE|TUBE|CHANNEL|ANGLE|PLATE|MEMBER|STEEL)\s+SCHEDULE"
    r"|SCHEDULE\s+OF\s+(?:COLUMNS|BEAMS|LINTELS|MEMBERS|PIERS|FOOTINGS)"
    r")\b",
    re.I,
)

_HEADER_WORDS = {
    "MARK",
    "SIZE",
    "SECTION",
    "DESIGNATION",
    "SHAPE",
    "TYPE",
    "PIER",
    "DIAMETER",
    "DIA",
    "PLATE",
    "BASE",
    "BEARING",
    "DEPTH",
    "WIDTH",
    "LENGTH",
    "WEIGHT",
    "QTY",
    "QUANTITY",
    "REMARKS",
    "NOTES",
    "LOCATION",
    "GRADE",
    "MATERIAL",
}

# Generic mark-ish tokens: 1–4 letters + optional sep + digits + optional letter suffix.
_GENERIC_MARK_RE = re.compile(r"^[A-Z]{1,4}[-_]?\d{1,3}[A-Z]?$", re.I)
# Section-shaped (reject as mark).
_SECTIONISH_RE = re.compile(
    r"^(?:W|HSS|HP|M|S|C|MC|L|WT|ST|MT|PL|PIPE|TS)\d",
    re.I,
)


def _page_text_lines(words: list[dict]) -> dict[int, str]:
    by_page: dict[int, list] = defaultdict(list)
    for w in words:
        page = int(w.get("page_number") or w.get("page") or 0)
        by_page[page].append(w)
    lines: dict[int, str] = {}
    for page, pw in by_page.items():
        # Rough reading order: y then x.
        ordered = sorted(
            pw,
            key=lambda w: (
                round(float(w["bbox"][1]) / 6.0),
                float(w["bbox"][0]),
            ),
        )
        lines[page] = " ".join(str(w.get("text") or "") for w in ordered)
    return lines


def _titles_on_pages(page_texts: dict[int, str]) -> list[dict]:
    found = []
    for page, text in page_texts.items():
        for m in _SCHEDULE_TITLE_RE.finditer(text):
            found.append({"page": page, "title": re.sub(r"\s+", " ", m.group(0)).upper()})
    return found


def _header_hits(words: list[dict]) -> dict[int, Counter]:
    by_page: dict[int, Counter] = defaultdict(Counter)
    for w in words:
        label = str(w.get("text") or "").upper().strip()
        if label in _HEADER_WORDS:
            page = int(w.get("page_number") or w.get("page") or 0)
            by_page[page][label] += 1
    return by_page


def _nearby_marks(words: list[dict], page: int, y_center: float | None = None) -> Counter:
    """Count generic mark-shaped tokens on a page (optionally near a y)."""
    counts: Counter = Counter()
    for w in words:
        if int(w.get("page_number") or w.get("page") or 0) != page:
            continue
        if y_center is not None:
            y = float(w["bbox"][1])
            if abs(y - y_center) > 400:
                continue
        text = re.sub(r"\s+", "", str(w.get("text") or ""))
        if not _GENERIC_MARK_RE.fullmatch(text):
            continue
        if _SECTIONISH_RE.match(text):
            continue
        counts[text.upper()] += 1
    return counts


def _prefix_bucket(mark: str) -> str:
    m = re.match(r"^([A-Z]+)", mark.upper())
    return m.group(1) if m else "?"


def census_one(path: Path) -> dict:
    t0 = time.time()
    doc = extract_document_structure(str(path))
    words = doc.get("words") or []
    page_count = int(doc.get("page_count") or 0)
    page_texts = _page_text_lines(words)
    titles = _titles_on_pages(page_texts)
    headers = _header_hits(words)

    # Pages that look like schedules: title hit OR (MARK+SIZE) OR (PIER+SIZE).
    schedule_pages = set()
    for t in titles:
        schedule_pages.add(t["page"])
    for page, ctr in headers.items():
        if (ctr["MARK"] and ctr["SIZE"]) or (ctr["PIER"] and ctr["SIZE"]):
            schedule_pages.add(page)
        if ctr["SECTION"] and (ctr["MARK"] or ctr["TYPE"]):
            schedule_pages.add(page)

    mark_prefixes: Counter = Counter()
    sample_marks: Counter = Counter()
    for page in schedule_pages:
        nearby = _nearby_marks(words, page)
        for mark, n in nearby.items():
            sample_marks[mark] += n
            mark_prefixes[_prefix_bucket(mark)] += n

    # Current implementation output.
    grids = build_schedule_grids(words)
    grid_kinds = Counter(str(g.get("kind") or "?") for g in grids)
    grid_marks = []
    catalog_ok = 0
    catalog_no = 0
    for g in grids:
        for row in g.get("rows") or []:
            mark = str(row.get("mark") or "")
            grid_marks.append(
                {
                    "page": g.get("page"),
                    "kind": g.get("kind"),
                    "mark": mark,
                    "size": (row.get("size_text") or "")[:60],
                    "section": row.get("section"),
                    "catalog_valid": bool(row.get("catalog_valid") or row.get("section")),
                    "impl_accepts_mark": is_schedule_table_mark(mark),
                }
            )
            if row.get("section"):
                catalog_ok += 1
            else:
                catalog_no += 1

    # Marks seen on schedule pages that current regex rejects.
    rejected = []
    for mark, n in sample_marks.most_common(80):
        if not is_schedule_table_mark(mark) and not is_bare_schedule_mark(mark):
            rejected.append({"mark": mark, "count": n, "prefix": _prefix_bucket(mark)})

    elapsed = round(time.time() - t0, 1)
    return {
        "file": path.name,
        "path": str(path),
        "pages": page_count,
        "words": len(words),
        "elapsed_s": elapsed,
        "titles": titles[:40],
        "title_kinds": Counter(
            re.sub(r"\s+SCHEDULE.*", " SCHEDULE", t["title"]).strip() for t in titles
        ),
        "schedule_page_count": len(schedule_pages),
        "schedule_pages": sorted(schedule_pages)[:40],
        "header_combo_pages": {
            str(p): dict(c) for p, c in sorted(headers.items()) if p in schedule_pages
        },
        "mark_prefixes_on_schedule_pages": dict(mark_prefixes.most_common(30)),
        "sample_marks_top": sample_marks.most_common(40),
        "impl_grids": len(grids),
        "impl_kinds": dict(grid_kinds),
        "impl_rows": len(grid_marks),
        "impl_catalog_ok": catalog_ok,
        "impl_catalog_no": catalog_no,
        "impl_row_samples": grid_marks[:30],
        "marks_rejected_by_impl": rejected[:40],
    }


def main() -> None:
    out_dir = BACKEND / "scripts" / "rd_geometry_integration"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    global_titles: Counter = Counter()
    global_prefixes: Counter = Counter()
    global_kinds: Counter = Counter()
    global_rejected_prefixes: Counter = Counter()

    for path in PDFS:
        if not path.is_file():
            results.append({"file": path.name, "error": "missing"})
            print(f"MISSING {path.name}", flush=True)
            continue
        print(f"SCAN {path.name} ...", flush=True)
        try:
            row = census_one(path)
        except Exception as exc:  # noqa: BLE001 — census must continue
            row = {"file": path.name, "path": str(path), "error": str(exc)}
            print(f"  ERROR {exc}", flush=True)
        results.append(row)
        if row.get("error"):
            continue
        global_titles.update(row.get("title_kinds") or {})
        global_prefixes.update(row.get("mark_prefixes_on_schedule_pages") or {})
        global_kinds.update(row.get("impl_kinds") or {})
        for r in row.get("marks_rejected_by_impl") or []:
            global_rejected_prefixes[r["prefix"]] += r["count"]
        print(
            f"  pages={row['pages']} sched_pages={row['schedule_page_count']} "
            f"titles={len(row['titles'])} grids={row['impl_grids']} "
            f"rows={row['impl_rows']} rejected_marks={len(row['marks_rejected_by_impl'])} "
            f"({row['elapsed_s']}s)",
            flush=True,
        )

    summary = {
        "pdf_count": len(results),
        "ok": sum(1 for r in results if not r.get("error")),
        "title_kinds_corpus": dict(global_titles.most_common()),
        "mark_prefixes_corpus": dict(global_prefixes.most_common(40)),
        "impl_kinds_corpus": dict(global_kinds.most_common()),
        "rejected_mark_prefixes_corpus": dict(global_rejected_prefixes.most_common(40)),
        "docs": results,
    }
    out_path = out_dir / "schedule_table_census.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
