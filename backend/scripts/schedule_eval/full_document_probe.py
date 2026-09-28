"""Whole-document schedule read: runtime, tables found, mark map size, cross-check.

Complements ``run_schedule_eval.py`` (answer-key pages only) by showing what the
ruled path emits on every page, including pages outside the answer key.

    cd backend && python scripts/schedule_eval/full_document_probe.py [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import fitz  # noqa: E402

from services.engineering.schedule_grid import (  # noqa: E402
    build_document_schedule_grids,
    schedule_mark_crosscheck,
    schedule_mark_map,
)

PDFS = {
    "ST": "uploads/ST.pdf",
    "Struct": "uploads/Struct.pdf",
    "BurrvilleST": "uploads/Burrville ES - ST.pdf",
    "1200K": "uploads/1200 K_Permit_Bid_Dwgs - Structural.pdf",
    "GCDC": "uploads/GCDC Building 4 - ST1__47dc7ef27f6e.pdf",
    "Springhill": "uploads/ST - Springhill Lake__f6ddc4a7e233.pdf",
    "Elmer": "uploads/ST-Elmer Wolfe ES__0cbd857dc6c2.pdf",
    "Moton": "uploads/ST-Robert Moton ES__258cb166b79f.pdf",
    "Runnymede": "uploads/ST-Runnymede ES__4ff5b14a268a.pdf",
    "SFSLS": "uploads/03 - SFSLS_251029_ISSUED FOR BID_2A_STRUCTURAL complied thru add 2__6a9a9684bb19.pdf",
    "StructureCopy": "uploads/Structure - Copy.pdf",
    "BurrvilleDD": "Testing Projects/51 - Burrvile ES/Burrville_DD Pricing Set_260317.pdf",
}


def all_words(pdf: Path) -> list:
    with fitz.open(str(pdf)) as document:
        return [
            {"text": w[4], "bbox": list(w[:4]), "page_number": index + 1}
            for index, page in enumerate(document)
            for w in page.get_text("words")
        ]


def probe(name: str, pdf: Path) -> dict:
    words = all_words(pdf)
    result = {"document": name}
    for mode, path in (("baseline", None), ("ruled", str(pdf))):
        started = time.time()
        grids = build_document_schedule_grids(words, pdf_path=path)
        document = {"words": words, "schedule_grid": grids}
        result[mode] = {
            "seconds": round(time.time() - started, 1),
            "tables": [
                {
                    "page": grid["page"],
                    "kind": grid["kind"],
                    "source": grid.get("source"),
                    "layout": grid.get("layout", "rows"),
                    "title": (grid.get("title") or "")[:60],
                    "rows": len(grid["rows"]),
                }
                for grid in grids
            ],
            "mark_map": schedule_mark_map(grids),
            "crosscheck": schedule_mark_crosscheck(document),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    parser.add_argument("only", nargs="*")
    args = parser.parse_args()
    results = []
    for name, rel in PDFS.items():
        if args.only and name not in args.only:
            continue
        pdf = BACKEND / rel
        if not pdf.is_file():
            print(f"{name}: missing")
            continue
        result = probe(name, pdf)
        results.append(result)
        for mode in ("baseline", "ruled"):
            data = result[mode]
            print(
                f"{name:<14}{mode:<9}{data['seconds']:>6}s tables={len(data['tables'])} "
                f"map={len(data['mark_map'])}"
            )
        for table in result["ruled"]["tables"]:
            print(f"    p{table['page']:<4}{table['kind']:<13}{table['source']:<13}"
                  f"{table['layout']:<11}rows={table['rows']:<4}{table['title']}")
        check = result["ruled"]["crosscheck"]
        print(f"    map: {result['ruled']['mark_map']}")
        print(f"    missing_from_schedule={check['missing_from_schedule'][:15]}")
        print(f"    unused_schedule_marks={check['unused_schedule_marks'][:15]}")
        print(f"    unscheduled_mark_families={dict(list(check['unscheduled_mark_families'].items())[:8])}")
    if args.json:
        args.json.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
