"""Score the sheet index against the Phase 0 ground truth and write
SHEET_INDEX_RESULTS.csv. Also compares the legacy ``_sheet_ids`` reading.

python reports/sheet_index_phase1_20261006/evaluate.py [--all-pages]
Extracted documents are cached under /tmp/sheet_index_docs (pickle) so the
reader can be re-run quickly; delete the cache to re-extract.
"""

from __future__ import annotations

import csv
import json
import os
import pickle
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from services.engineering.drawing_intelligence import _sheet_ids  # noqa: E402
from services.engineering.sheet_index import sheet_index  # noqa: E402
from services.pdf_parser import extract_document_structure  # noqa: E402

OUT = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("ESTIMA3D_TESTING_PROJECTS", OUT / "pdf_root"))
CACHE = Path("/tmp/sheet_index_docs")
TRUTH = json.loads((BACKEND / "tests" / "fixtures" / "sheet_index" / "ground_truth.json").read_text())


def _document(pdf: str) -> dict:
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / (pdf.replace("/", "_") + ".pkl")
    if cached.exists():
        return pickle.loads(cached.read_bytes())
    document = extract_document_structure(str(ROOT / pdf))
    cached.write_bytes(pickle.dumps(document))
    return document


def _same(a, b) -> bool:
    return (a or None) == (b or None) if not isinstance(a, str) or not isinstance(b, str) else a.strip().upper() == b.strip().upper()


def main() -> None:
    by_pdf: dict = {}
    for row in TRUTH["pages"]:
        by_pdf.setdefault(row["pdf"], []).append(row)
    results, stats = [], {
        "sheet_id": [0, 0, 0], "title": [0, 0, 0], "issue": [0, 0, 0],
        "issue_date": [0, 0, 0], "scale": [0, 0, 0], "revision": [0, 0, 0], "legacy_sheet_id": [0, 0, 0],
    }
    layouts = {}
    for pdf, rows in by_pdf.items():
        document = _document(pdf)
        index = sheet_index(document)
        layouts[rows[0]["project"]] = index["layout"]
        legacy = _sheet_ids(document)
        pages = {r["page"]: r for r in index["pages"]}
        for truth in rows:
            got = pages.get(truth["page"], {})

            def score(name, expected, predicted):
                if predicted in (None, ""):
                    if expected in (None, ""):
                        stats[name][0] += 1   # not printed, not read
                        return "correct"
                    stats[name][2] += 1   # printed, not read
                    return "unresolved"
                if expected in (None, ""):
                    stats[name][1] += 1   # read something that is not printed
                    return "wrong"
                if _same(expected, predicted):
                    stats[name][0] += 1
                    return "correct"
                stats[name][1] += 1
                return "wrong"

            sid = score("sheet_id", truth["sheet_id"], got.get("sheet_id"))
            if sid == "correct" and got.get("sheet_id"):
                pass
            leg = score("legacy_sheet_id", truth["sheet_id"].replace("-", ""), legacy.get(truth["page"]))
            ttl = score("title", truth["sheet_title"], got.get("sheet_title"))
            iss = score("issue", truth["issue"], got.get("issue"))
            idt = score("issue_date", truth["issue_date"], got.get("issue_date"))
            scl = score("scale", truth["scale"], got.get("scale"))
            rev_rows = [[r["number"], r["description"], r["date"]] for r in got.get("revision", {}).get("rows", [])]
            if truth["revision_inspected"]:
                if rev_rows == truth["revision_rows"]:
                    stats["revision"][0] += 1
                    rev = "correct"
                else:
                    stats["revision"][1] += 1
                    rev = "wrong"
            else:
                rev = "not_inspected"
            results.append({
                "project": truth["project"], "pdf": Path(pdf).name, "page": truth["page"],
                "rotation": got.get("rotation"),
                "expected_sheet_id": truth["sheet_id"], "predicted_sheet_id": got.get("sheet_id"),
                "sheet_id_status": got.get("sheet_id_status"), "sheet_id_result": sid,
                "legacy_sheet_id": legacy.get(truth["page"]), "legacy_result": leg,
                "expected_title": truth["sheet_title"], "predicted_title": got.get("sheet_title"),
                "title_status": got.get("title_status"), "title_result": ttl,
                "expected_issue": truth["issue"], "predicted_issue": got.get("issue"), "issue_result": iss,
                "expected_issue_date": truth["issue_date"], "predicted_issue_date": got.get("issue_date"), "issue_date_result": idt,
                "expected_scale": truth["scale"], "predicted_scale": got.get("scale"),
                "scale_status": got.get("scale_status"), "scale_result": scl,
                "expected_revisions": json.dumps(truth["revision_rows"]) if truth["revision_inspected"] else "not inspected",
                "predicted_revisions": json.dumps(rev_rows), "revision_status": got.get("revision", {}).get("status"),
                "revision_result": rev,
                "evidence": "; ".join(got.get("evidence") or []) + (" | " + "; ".join(got.get("issue_evidence") or []) if got.get("issue_evidence") else ""),
                "notes": truth["notes"],
            })
    with (OUT / "SHEET_INDEX_RESULTS.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    for row in results:
        bad = [k for k in ("sheet_id_result", "title_result", "issue_result", "issue_date_result", "scale_result", "revision_result")
               if row[k] in ("wrong", "unresolved")]
        if bad:
            print(row["project"], row["page"], {k: (row[k.replace("_result", "").replace("sheet_id", "predicted_sheet_id")] if False else row[k]) for k in bad},
                  "| id", row["predicted_sheet_id"], "| title", row["predicted_title"], "| issue", row["predicted_issue"],
                  row["predicted_issue_date"], "| scale", row["predicted_scale"], "| rev", row["predicted_revisions"])
    print(json.dumps({k: {"correct": v[0], "wrong": v[1], "unresolved": v[2]} for k, v in stats.items()}, indent=1))
    print(json.dumps(layouts, indent=1))
    (OUT / "evaluation_summary.json").write_text(json.dumps(
        {"stats": {k: {"correct": v[0], "wrong": v[1], "unresolved": v[2]} for k, v in stats.items()}, "layouts": layouts},
        indent=2))


if __name__ == "__main__":
    main()
