"""Sheet index over every page of the 8 benchmark PDFs (not only Phase 0).

Writes ALL_PAGES.csv and prints per-project status counts, duplicate sheet
ids, and pages where the legacy reader disagrees.
python reports/sheet_index_phase1_20261006/all_pages.py
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from evaluate import TRUTH, _document  # noqa: F401  (same cache and root)

from services.engineering.drawing_intelligence import _sheet_ids
from services.engineering.sheet_index import sheet_index

OUT = Path(__file__).resolve().parent


def main() -> None:
    pdfs = {}
    for row in TRUTH["pages"]:
        pdfs.setdefault(row["project"], row["pdf"])
    rows, summary = [], {}
    for project, pdf in pdfs.items():
        document = _document(pdf)
        index = sheet_index(document)
        legacy = _sheet_ids(document)
        ids = Counter(r["sheet_id"] for r in index["pages"] if r["sheet_id"])
        summary[project] = {
            "pages": len(index["pages"]),
            "sheet_id": Counter(r["sheet_id_status"] for r in index["pages"]),
            "title": Counter(r["title_status"] for r in index["pages"]),
            "issue": Counter(r["issue_status"] for r in index["pages"]),
            "scale": Counter(r["scale_status"] for r in index["pages"]),
            "revision": Counter(r["revision"]["status"] for r in index["pages"]),
            "duplicate_ids": {k: v for k, v in ids.items() if v > 1},
            "legacy_disagrees": [
                (r["page"], r["sheet_id"], legacy.get(r["page"]))
                for r in index["pages"]
                if (r["sheet_id"] or "").replace("-", "") != (legacy.get(r["page"]) or "")
            ],
        }
        for r in index["pages"]:
            rows.append({
                "project": project, "page": r["page"], "rotation": r["rotation"],
                "sheet_id": r["sheet_id"], "sheet_id_status": r["sheet_id_status"],
                "legacy_sheet_id": legacy.get(r["page"]),
                "sheet_title": r["sheet_title"], "title_status": r["title_status"],
                "issue": r["issue"], "issue_date": r["issue_date"], "issue_status": r["issue_status"],
                "scale": r["scale"], "scale_status": r["scale_status"],
                "scale_candidates": json.dumps([c["text"] for c in r["scale_candidates"]]),
                "revision_status": r["revision"]["status"],
                "revision_rows": json.dumps([[x["number"], x["description"], x["date"]] for x in r["revision"]["rows"]]),
            })
    with (OUT / "ALL_PAGES.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=1, default=dict))


if __name__ == "__main__":
    main()
