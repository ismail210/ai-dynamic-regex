#!/usr/bin/env python3
"""Fast read-only census of schedule tables via pymupdf words (no full document parse)."""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fitz  # noqa: E402

from services.engineering.schedule_grid import (  # noqa: E402
    build_schedule_grids,
    is_bare_schedule_mark,
    is_schedule_table_mark,
)

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
    r"HSS|PIPE|TUBE|CHANNEL|ANGLE|PLATE|MEMBER|STEEL|WALL|SLAB)\s+SCHEDULE"
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

_GENERIC_MARK_RE = re.compile(r"^[A-Z]{1,4}[-_]?\d{1,3}[A-Z]?$", re.I)
_SECTIONISH_RE = re.compile(
    r"^(?:W|HSS|HP|M|S|C|MC|L|WT|ST|MT|PL|PIPE|TS)\d",
    re.I,
)


def _words_from_pdf(path: Path, max_pages: int | None = None) -> tuple[list[dict], int]:
    words: list[dict] = []
    with fitz.open(path) as doc:
        n = doc.page_count
        limit = n if max_pages is None else min(n, max_pages)
        for i in range(limit):
            page = doc.load_page(i)
            for x0, y0, x1, y1, text, *_rest in page.get_text("words"):
                t = str(text or "").strip()
                if not t:
                    continue
                words.append(
                    {
                        "text": t,
                        "bbox": [float(x0), float(y0), float(x1), float(y1)],
                        "page_number": i + 1,
                    }
                )
        return words, n


def _page_blob(words: list[dict]) -> dict[int, str]:
    by_page: dict[int, list] = defaultdict(list)
    for w in words:
        by_page[int(w["page_number"])].append(w)
    out = {}
    for page, pw in by_page.items():
        ordered = sorted(
            pw, key=lambda w: (round(float(w["bbox"][1]) / 6.0), float(w["bbox"][0]))
        )
        out[page] = " ".join(str(w["text"]) for w in ordered)
    return out


def _prefix(mark: str) -> str:
    m = re.match(r"^([A-Z]+)", mark.upper())
    return m.group(1) if m else "?"


def census_one(path: Path) -> dict:
    t0 = time.time()
    # Cap huge packages at 80 pages for census speed; ST/Struct usually smaller.
    words, page_count = _words_from_pdf(path, max_pages=80)
    blobs = _page_blob(words)

    titles = []
    for page, text in blobs.items():
        for m in _SCHEDULE_TITLE_RE.finditer(text):
            titles.append(
                {
                    "page": page,
                    "title": re.sub(r"\s+", " ", m.group(0)).upper().strip(),
                }
            )

    headers: dict[int, Counter] = defaultdict(Counter)
    for w in words:
        label = str(w["text"]).upper().strip()
        if label in _HEADER_WORDS:
            headers[int(w["page_number"])][label] += 1

    schedule_pages = {t["page"] for t in titles}
    for page, ctr in headers.items():
        if (ctr["MARK"] and ctr["SIZE"]) or (ctr["PIER"] and ctr["SIZE"]):
            schedule_pages.add(page)
        if ctr["SECTION"] and (ctr["MARK"] or ctr["TYPE"]):
            schedule_pages.add(page)

    mark_prefixes: Counter = Counter()
    sample_marks: Counter = Counter()
    for w in words:
        page = int(w["page_number"])
        if page not in schedule_pages:
            continue
        text = re.sub(r"\s+", "", str(w["text"]))
        if not _GENERIC_MARK_RE.fullmatch(text):
            continue
        if _SECTIONISH_RE.match(text):
            # C8 / L4X4-style: keep only pure mark-like (no X in middle).
            if "X" in text.upper()[1:]:
                continue
            # Bare C12 could be channel section OR column mark — keep for census.
        sample_marks[text.upper()] += 1
        mark_prefixes[_prefix(text)] += 1

    grids = build_schedule_grids(words)
    grid_kinds = Counter(str(g.get("kind") or "?") for g in grids)
    rows_out = []
    catalog_ok = catalog_no = 0
    for g in grids:
        for row in g.get("rows") or []:
            mark = str(row.get("mark") or "")
            ok = bool(row.get("section"))
            catalog_ok += int(ok)
            catalog_no += int(not ok)
            rows_out.append(
                {
                    "page": g.get("page"),
                    "kind": g.get("kind"),
                    "mark": mark,
                    "size": str(row.get("size_text") or "")[:70],
                    "section": row.get("section"),
                    "impl_accepts_mark": is_schedule_table_mark(mark),
                }
            )

    rejected = []
    for mark, n in sample_marks.most_common(100):
        if not is_schedule_table_mark(mark):
            rejected.append({"mark": mark, "count": n, "prefix": _prefix(mark)})

    # Header vocabulary on schedule pages only.
    header_vocab: Counter = Counter()
    for page in schedule_pages:
        header_vocab.update(headers.get(page, Counter()))

    return {
        "file": path.name,
        "pages": page_count,
        "pages_scanned": min(page_count, 80),
        "words": len(words),
        "elapsed_s": round(time.time() - t0, 1),
        "titles": titles[:50],
        "title_kinds": dict(
            Counter(
                re.sub(r"^(EXISTING\s+)", "", t["title"]) for t in titles
            ).most_common()
        ),
        "schedule_page_count": len(schedule_pages),
        "schedule_pages": sorted(schedule_pages)[:50],
        "header_vocab": dict(header_vocab.most_common()),
        "mark_prefixes": dict(mark_prefixes.most_common(40)),
        "sample_marks_top": sample_marks.most_common(35),
        "impl_grids": len(grids),
        "impl_kinds": dict(grid_kinds),
        "impl_rows": len(rows_out),
        "impl_catalog_ok": catalog_ok,
        "impl_catalog_no": catalog_no,
        "impl_row_samples": rows_out[:40],
        "marks_rejected_by_impl": rejected[:40],
    }


def main() -> None:
    results = []
    global_titles: Counter = Counter()
    global_prefixes: Counter = Counter()
    global_kinds: Counter = Counter()
    global_headers: Counter = Counter()
    global_rejected: Counter = Counter()

    for path in PDFS:
        if not path.is_file():
            print(f"MISSING {path.name}", flush=True)
            results.append({"file": path.name, "error": "missing"})
            continue
        print(f"SCAN {path.name} ...", flush=True)
        try:
            row = census_one(path)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {exc}", flush=True)
            results.append({"file": path.name, "error": str(exc)})
            continue
        results.append(row)
        global_titles.update(row.get("title_kinds") or {})
        global_prefixes.update(row.get("mark_prefixes") or {})
        global_kinds.update(row.get("impl_kinds") or {})
        global_headers.update(row.get("header_vocab") or {})
        for r in row.get("marks_rejected_by_impl") or []:
            global_rejected[r["prefix"]] += r["count"]
        print(
            f"  pages={row['pages']} sched={row['schedule_page_count']} "
            f"titles={len(row['titles'])} grids={row['impl_grids']} "
            f"rows={row['impl_rows']} rej={len(row['marks_rejected_by_impl'])} "
            f"{row['elapsed_s']}s",
            flush=True,
        )

    summary = {
        "pdf_count_ok": sum(1 for r in results if not r.get("error")),
        "title_kinds_corpus": dict(global_titles.most_common()),
        "header_vocab_corpus": dict(global_headers.most_common()),
        "mark_prefixes_corpus": dict(global_prefixes.most_common(50)),
        "impl_kinds_corpus": dict(global_kinds.most_common()),
        "rejected_mark_prefixes_corpus": dict(global_rejected.most_common(40)),
        "docs": results,
    }
    out = BACKEND / "scripts" / "rd_geometry_integration" / "schedule_table_census.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)


if __name__ == "__main__":
    main()
