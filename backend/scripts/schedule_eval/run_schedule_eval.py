"""Measure schedule reading against the hand-listed answer key.

Compares the word-cluster baseline (no PDF path) with the ruled-table path
(find_tables first, word clustering as fallback) on the answer-key pages.

    cd backend && python scripts/schedule_eval/run_schedule_eval.py [--json out.json]

Per class it reports how many key rows were found and how many were right:
  steel      mark found in a schedule row; right = same catalog section
             (or no section when the key says null: plate / precast rows)
  non_steel  mark found; right = never mapped to a steel section
  transposed grid location found; right = every expected section present
  extra      marks mapped to a steel section that the key does not list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import fitz  # noqa: E402

from services.database_loader import catalog_form  # noqa: E402
from services.engineering.schedule_grid import (  # noqa: E402
    NON_STEEL_SCHEDULE_KINDS,
    build_document_schedule_grids,
    normalize_schedule_mark,
    schedule_mark_map,
)

ANSWER_KEY = BACKEND / "tests" / "fixtures" / "schedule_answer_key" / "answer_key.json"
CLASSES = ("steel", "non_steel", "transposed")


def load_answer_key(path: Path = ANSWER_KEY) -> Dict[str, Any]:
    return json.loads(path.read_text())


def key_pages(doc: Dict[str, Any]) -> List[int]:
    tables = doc.get("tables", []) + doc.get("transposed", [])
    return sorted({int(table["page"]) for table in tables})


def pdf_words(pdf: Path, pages: List[int]) -> List[Dict[str, Any]]:
    words: List[Dict[str, Any]] = []
    with fitz.open(str(pdf)) as document:
        for page_number in pages:
            for x0, y0, x1, y1, text, *_ in document[page_number - 1].get_text("words"):
                words.append(
                    {"text": text, "bbox": [x0, y0, x1, y1], "page_number": page_number}
                )
    return words


def _section_key(section: Optional[str]) -> str:
    return catalog_form(section or "") or str(section or "").upper().replace(" ", "")


def _tally() -> Dict[str, Dict[str, int]]:
    return {name: {"expected": 0, "found": 0, "correct": 0} for name in CLASSES}


def score_document(doc: Dict[str, Any], grids: List[Dict[str, Any]]) -> Dict[str, Any]:
    tally = _tally()
    misses: List[str] = []
    sources: Dict[str, int] = {}
    mapping = schedule_mark_map(grids)
    by_page: Dict[int, Dict[str, Dict[str, Any]]] = {}
    locations: Dict[int, Dict[str, set]] = {}
    for grid in grids:
        page = int(grid["page"])
        for row in grid["rows"]:
            if row.get("mark_role") == "grid_location":
                locations.setdefault(page, {}).setdefault(row["mark"], set()).add(
                    _section_key(row.get("section"))
                )
            else:
                by_page.setdefault(page, {}).setdefault(
                    normalize_schedule_mark(row["mark"]),
                    {**row, "kind": grid["kind"], "source": grid.get("source")},
                )

    for table in doc.get("tables", []):
        klass = table["class"]
        rows = by_page.get(int(table["page"]), {})
        for mark, expected in table["rows"].items():
            key = normalize_schedule_mark(mark)
            tally[klass]["expected"] += 1
            row = rows.get(key)
            if row is None:
                misses.append(f"{klass} p{table['page']} {mark}: not found")
                continue
            tally[klass]["found"] += 1
            sources[row["source"]] = sources.get(row["source"], 0) + 1
            if klass == "non_steel":
                right = (
                    key not in mapping
                    and not row.get("section")
                    and row["kind"] in NON_STEEL_SCHEDULE_KINDS
                )
            elif expected is None:
                right = not row.get("section")
            else:
                right = _section_key(row.get("section")) == _section_key(expected)
            if right:
                tally[klass]["correct"] += 1
            else:
                misses.append(
                    f"{klass} p{table['page']} {mark}: got {row.get('section')!r} "
                    f"in {row['kind']} table, want {expected!r}"
                )

    for table in doc.get("transposed", []):
        found = locations.get(int(table["page"]), {})
        for location, sections in table["rows"].items():
            tally["transposed"]["expected"] += 1
            got = found.get(location)
            if got is None:
                misses.append(f"transposed p{table['page']} {location}: not found")
                continue
            tally["transposed"]["found"] += 1
            if {_section_key(s) for s in sections} <= got:
                tally["transposed"]["correct"] += 1
            else:
                misses.append(
                    f"transposed p{table['page']} {location}: got {sorted(got)}, want {sections}"
                )
    keyed = {
        normalize_schedule_mark(mark)
        for table in doc.get("tables", [])
        for mark in table["rows"]
    }
    extra_steel = sorted(mark for mark in mapping if mark not in keyed)
    misses.extend(f"extra steel mapping {mark} -> {mapping[mark]}" for mark in extra_steel)
    return {
        "tally": tally,
        "extra_steel": extra_steel,
        "misses": misses,
        "row_sources": sources,
    }


def evaluate(backend: Path = BACKEND, key: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = key or load_answer_key()
    report: Dict[str, Any] = {"documents": {}, "skipped": []}
    totals = {mode: _tally() for mode in ("baseline", "ruled")}
    extra = {mode: 0 for mode in totals}
    for doc in key["documents"]:
        pdf = backend / doc["pdf"]
        if not pdf.is_file():
            report["skipped"].append(doc["key"])
            continue
        pages = key_pages(doc)
        words = pdf_words(pdf, pages)
        doc_report = {}
        for mode, path in (("baseline", None), ("ruled", str(pdf))):
            grids = build_document_schedule_grids(words, pdf_path=path, pages=pages)
            scored = score_document(doc, grids)
            doc_report[mode] = scored
            extra[mode] += len(scored["extra_steel"])
            for klass in CLASSES:
                for field, value in scored["tally"][klass].items():
                    totals[mode][klass][field] += value
        report["documents"][doc["key"]] = doc_report
    report["totals"] = totals
    report["extra_steel"] = extra
    return report


def _format(report: Dict[str, Any]) -> str:
    lines = []
    header = f"{'document':<14}{'mode':<10}" + "".join(f"{c:>18}" for c in CLASSES)
    lines.append(header + f"{'extra':>8}")

    def cells(tally):
        return "".join(
            f"{tally[c]['correct']}/{tally[c]['found']}/{tally[c]['expected']}".rjust(18)
            for c in CLASSES
        )

    for name, modes in report["documents"].items():
        for mode, scored in modes.items():
            lines.append(
                f"{name:<14}{mode:<10}" + cells(scored["tally"])
                + f"{len(scored['extra_steel']):>8}"
            )
    for mode, tally in report["totals"].items():
        lines.append(
            f"{'TOTAL':<14}{mode:<10}" + cells(tally) + f"{report['extra_steel'][mode]:>8}"
        )
    lines.append("cells: correct/found/expected; extra = steel mappings not in the key")
    if report["skipped"]:
        lines.append(f"skipped (PDF missing): {', '.join(report['skipped'])}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument("--misses", action="store_true", help="print ruled-path misses")
    args = parser.parse_args()
    report = evaluate()
    print(_format(report))
    if args.misses:
        for name, modes in report["documents"].items():
            print(f"  {name}: ruled-mode row sources {modes['ruled']['row_sources']}")
            for miss in modes["ruled"]["misses"]:
                print(f"  {name}: {miss}")
    if args.json:
        args.json.write_text(json.dumps(report, indent=1, default=sorted))


if __name__ == "__main__":
    main()
