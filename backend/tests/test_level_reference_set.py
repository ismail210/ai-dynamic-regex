"""Levels and elevations on the real reference drawings (Phase 2).

Runs the production extraction path (PDF -> schedule grid -> drawing
intelligence) and checks ``profile["levels"]`` and the column-schedule
extents against values read from the rendered sheets
(``fixtures/column_schedule/reference_levels.json``). Skips a document whose
PDF is not present; the PDFs are not in git.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "column_schedule" / "reference_levels.json"
_ROOT = Path(os.environ.get(
    "ESTIMA3D_TESTING_PROJECTS",
    r"C:\Users\Bassam\Downloads\Testing Projects-20260912T094727Z-1-001\Testing Projects",
))
_REFERENCE = json.loads(_FIXTURE.read_text(encoding="utf-8"))
_CACHE: dict = {}


def _run(spec):
    if spec["key"] not in _CACHE:
        from services.engineering import drawing_intelligence as di
        from services.engineering.schedule_grid import attach_schedule_grid
        from services.pdf_parser import extract_document_structure

        pdf = _ROOT / spec["pdf"]
        document = extract_document_structure(str(pdf))
        attach_schedule_grid(document, pdf_path=str(pdf))
        _CACHE[spec["key"]] = (document, di.build_drawing_intelligence(document))
    return _CACHE[spec["key"]]


class LevelReferenceTests(unittest.TestCase):
    def _check(self, spec):
        if not (_ROOT / spec["pdf"]).is_file():
            self.skipTest(f"{spec['pdf']} is not available locally")
        document, profile = _run(spec)
        view = profile["levels"]
        levels = view["schedule_levels"]
        by_name = {level["name"]: level for level in levels}

        for schedule, expected in spec.get("schedule_levels", {}).items():
            got = [(l["name"], l["printed"]) for l in levels if l["schedule"] == schedule]
            self.assertEqual(got, [tuple(e) for e in expected], schedule)
        for name, plan_value in spec.get("conflicts", {}).items():
            self.assertTrue(by_name[name]["conflict"], name)
            self.assertIn(plan_value, [v["display"] for m in by_name[name]["plan_matches"] for v in m["values"]])
        for name, plan_value in spec.get("agrees", {}).items():
            self.assertFalse(by_name[name]["conflict"], name)
            self.assertIn("agrees", [m["comparison"] for m in by_name[name]["plan_matches"]], name)
        for name, value in spec.get("resolved", {}).items():
            self.assertEqual((by_name[name]["resolved"] or {}).get("display"), value, name)
        for name in spec.get("unresolved_see_plan", []):
            self.assertIsNone(by_name[name]["resolved"], name)

        records = view["plan_elevations"]

        def has(status, sheet, surface, value=None, area="any"):
            return any(
                r["status"] == status and r["sheet"] == sheet and r["surface"] == surface
                and (value is None or (r["value"] or {}).get("display") == value)
                and (area == "any" or r["area"] == area)
                for r in records
            )

        for sheet, surface, value in spec.get("plan_read", []):
            self.assertTrue(has("read", sheet, surface, value), (sheet, surface, value))
        for sheet, surface, value, area in spec.get("plan_derived", []):
            self.assertTrue(has("derived", sheet, surface, value, area), (sheet, surface, value, area))
        for sheet, surface in spec.get("plan_unresolved", []):
            self.assertTrue(has("unresolved", sheet, surface), (sheet, surface))
        for sheet, meaning in spec.get("noted", []):
            self.assertIn(meaning, next(g["meaning"] for g in view["noted_on_plans"] if g["sheet"] == sheet))
        for relation in spec.get("datums", []):
            self.assertIn(relation, [d["relation"] for d in view["datums"]])
        for sheet in spec.get("datum_unresolved", []):
            self.assertIn("unresolved", [d["status"] for d in view["datums"] if d["sheet"] == sheet])
        for sample, meaning in spec.get("notations", []):
            self.assertIn((sample, meaning), [(n["sample"][0], n["meaning"]) for n in view["notations"]])
        for text in spec.get("masked_not_used", []):
            self.assertNotIn(text, [l["printed"] for l in levels])

        entries = {e["location_text"] or e["mark"]: e for e in profile["column_schedule"]["entries"]}
        for key, value in spec.get("differences", {}).items():
            self.assertEqual(entries[key]["level_difference"]["display"], value, key)
        for key in spec.get("no_difference", []):
            self.assertEqual(entries[key]["level_difference"]["status"], "unresolved", key)
        if spec.get("no_computed_differences"):
            self.assertFalse([e for e in entries.values() if (e.get("level_difference") or {}).get("status") == "computed"])
        for key, box in spec.get("entry_box", {}).items():
            self.assertEqual([round(v) for v in entries[key]["bbox"]], [round(v) for v in box])

        from services.engineering.drawing_intelligence import _sheet_ids

        sheets = _sheet_ids(document)
        for page, sheet in spec.get("sheet_ids", {}).items():
            self.assertEqual(sheets.get(int(page)), sheet, page)
        for page in spec.get("no_production_rows_on_pages", []):
            # Rotated pages are read for evidence only, never into the production grid.
            self.assertFalse([g for g in document["schedule_grid"] if g["page"] == page and g["rows"]], page)
        for sheet, count in spec.get("flagged", {}).items():
            self.assertEqual(next(g["flagged"] for g in view["noted_on_plans"] if g["sheet"] == sheet), count, sheet)
        bands = {b["printed"]: b for b in view.get("level_bands") or []}
        for printed, (upper, lower) in spec.get("bands", {}).items():
            self.assertEqual((bands[printed]["upper"]["name"], bands[printed]["lower"]["name"]), (upper, lower))
            self.assertGreater(bands[printed]["schedule_rows"], 0)
        rows = {r["mark"]: r for g in document["schedule_grid"] for r in g["rows"]}
        for mark, plate in spec.get("plates", {}).items():
            self.assertEqual(rows[mark]["plate_status"], plate["status"])
            self.assertEqual(rows[mark]["parsed_plate"]["dimensions"],
                             {k: plate[k] for k in ("thickness", "width", "length")})
        if spec.get("traces"):
            from services.engineering.column_trace import trace_column

            for location, expected in spec["traces"].items():
                trace = trace_column(document, str(_ROOT / spec["pdf"]), location)
                self.assertEqual(trace["summary"]["levels_with_symbol"], expected["levels_with_symbol"], location)
                self.assertEqual(trace["ends"]["bottom"]["level"], expected["bottom"])
                if "bottom_annotation" in expected:
                    self.assertIn(tuple(expected["bottom_annotation"]),
                                  [(a["sheet"], a["text"]) for a in trace["ends"]["bottom"]["plan_annotations"]])


def _make(spec):
    def test(self):
        self._check(spec)

    return test


for _spec in _REFERENCE["documents"]:
    setattr(LevelReferenceTests, f"test_{_spec['key']}", _make(_spec))


if __name__ == "__main__":
    unittest.main()
