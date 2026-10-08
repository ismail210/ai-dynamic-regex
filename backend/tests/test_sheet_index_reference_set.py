"""Sheet index on the real reference drawings (Phase 0 ground truth).

Runs PDF -> document structure -> drawing intelligence and checks
``profile["sheet_index"]`` against values read from the rendered title blocks
(``fixtures/sheet_index/ground_truth.json``), verbatim. Skips a document whose
PDF is not present; the PDFs are not in git.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "sheet_index" / "ground_truth.json"
_ROOT = Path(os.environ.get(
    "ESTIMA3D_TESTING_PROJECTS",
    r"C:\Users\Bassam\Downloads\Testing Projects-20260912T094727Z-1-001\Testing Projects",
))
_TRUTH = json.loads(_FIXTURE.read_text(encoding="utf-8"))["pages"]
_CACHE: dict = {}


def _index(pdf):
    if pdf not in _CACHE:
        from services.engineering import drawing_intelligence as di
        from services.pdf_parser import extract_document_structure

        document = extract_document_structure(str(_ROOT / pdf))
        _CACHE[pdf] = {p["page"]: p for p in di.build_drawing_intelligence(document)["sheet_index"]["pages"]}
    return _CACHE[pdf]


def _text(value):
    return " ".join(value.split()) if isinstance(value, str) else value


class SheetIndexReferenceTests(unittest.TestCase):
    def _page(self, project, page):
        truth = next(t for t in _TRUTH if t["project"] == project and t["page"] == page)
        if not (_ROOT / truth["pdf"]).is_file():
            self.skipTest(f"{truth['pdf']} is not available locally")
        return truth, _index(truth["pdf"])[page]

    def test_every_ground_truth_page(self):
        checked = 0
        for truth in _TRUTH:
            if not (_ROOT / truth["pdf"]).is_file():
                continue
            got = _index(truth["pdf"])[truth["page"]]
            where = f"{truth['project']} p{truth['page']}"
            with self.subTest(where):
                self.assertEqual(got["sheet_id"], truth["sheet_id"], where)
                self.assertEqual(got["rotation"], truth["rotation"], where)
                self.assertEqual(_text(got["sheet_title"]), truth["sheet_title"], where)
                self.assertEqual(got["issue"], truth["issue"], where)
                self.assertEqual(got["issue_date"], truth["issue_date"], where)
                self.assertEqual(got["scale"], truth["scale"], where)
                if truth["revision_inspected"]:
                    rows = [[r["number"], _text(r["description"]), r["date"]] for r in got["revision"]["rows"]]
                    self.assertEqual(rows, truth["revision_rows"], where)
            checked += 1
        if not checked:
            self.skipTest("no reference PDFs available locally")

    def test_osse_building_suffix_sheet_number(self):
        truth, got = self._page("osse", 10)
        self.assertEqual(got["sheet_id"], "S-122-O")
        self.assertEqual(got["sheet_id_status"], "read")
        self.assertEqual(got["sheet_title"], truth["sheet_title"])
        self.assertIsNone(got["scale"])

    def test_rotated_sheets_read_in_display_orientation(self):
        for page in (1, 5, 13, 25, 40):
            truth, got = self._page("yellowspring", page)
            self.assertEqual(got["rotation"], 90)
            self.assertEqual(got["sheet_id"], truth["sheet_id"])


if __name__ == "__main__":
    unittest.main()
