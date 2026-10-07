"""Views, references, grids, and labels stay evidence. Dimensions are not grids."""

from __future__ import annotations

import unittest

from services.engineering.intelligence_layer import (
    build_engineering_intelligence,
    classify_view_title,
    compact_sheet,
    is_dimension_text,
    resolve_reference,
)


def _line(text, box=(10, 10, 80, 22)):
    return {"page_number": 1, "text": text, "bbox": list(box), "font_size": 10, "rotation": 0}


def _document(lines, page=1, width=1000, height=800):
    return {
        "page_count": 1,
        "pages": [{"page_number": page, "width": width, "height": height, "rotation": 0}],
        "lines": lines,
    }


class ViewTitleTests(unittest.TestCase):
    def test_printed_titles(self):
        section = classify_view_title("SECTION A")
        self.assertEqual(section["view_type"], "section")
        self.assertEqual(section["view_number"], "A")
        detail = classify_view_title("DETAIL D")
        self.assertEqual(detail["view_type"], "detail")
        self.assertEqual(detail["view_number"], "D")
        self.assertEqual(classify_view_title("FOUNDATION PLAN")["view_type"], "foundation_plan")
        self.assertEqual(classify_view_title("LOW ROOF FRAMING")["view_type"], "roof_plan")

    def test_a_sentence_is_not_a_view(self):
        self.assertIsNone(classify_view_title("SEE SECTION A ON THE FOUNDATION PLAN FOR THE DOWELS"))
        self.assertIsNone(classify_view_title("The column schedule is on this sheet."))
        self.assertIsNone(classify_view_title("SECTION"))
        self.assertEqual(classify_view_title("SECTION", scale_nearby=True)["view_type"], "section")


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.sheets = {
            compact_sheet("S401"): [{"sheet_id": "S401", "page": 19}],
            compact_sheet("S-122-O"): [{"sheet_id": "S-122-O", "page": 10}],
        }
        self.views = {19: [{"view_id": "V9", "view_number": "D", "status": "read", "pdf_page": 19}]}

    def test_view_number_must_be_printed(self):
        missing_view = resolve_reference("N", "S401", "bubble", self.sheets, self.views, "S101A")
        self.assertEqual(missing_view["status"], "target_sheet_only")
        self.assertIsNone(missing_view["target_view"])
        found = resolve_reference("D", "S401", "bubble", self.sheets, self.views, "S101A")
        self.assertEqual(found["status"], "target_view_found")
        self.assertEqual(found["target_view"], "V9")

    def test_missing_sheet_and_suffix(self):
        missing = resolve_reference("1", "S999", "bubble", self.sheets, self.views, "S101")
        self.assertEqual(missing["status"], "target_missing")
        osse = resolve_reference("2", "S122-O", "bubble", self.sheets, {}, "S-101-O")
        self.assertEqual(osse["target_sheet"], "S-122-O")
        self.assertEqual(osse["status"], "target_sheet_only")

    def test_see_plan_without_a_sheet_stays_ambiguous(self):
        got = resolve_reference(None, None, "plan", self.sheets, self.views, "S-101")
        self.assertEqual(got["status"], "ambiguous")


class GridAndLabelTests(unittest.TestCase):
    def test_dimensions_are_not_grids(self):
        for text in ('4\'-6"', '10\'-0"', '14\'-8"', "+14'-6\"", "-0'-6\""):
            self.assertTrue(is_dimension_text(text), text)

    def test_incomplete_angle_is_not_completed(self):
        profile = {"sheet_index": {"pages": [{
            "page": 1, "sheet_id": "S301", "sheet_id_status": "read",
            "sheet_title": "TYPICAL DETAILS", "title_status": "read", "sheet_role": "detail",
            "classification_status": "read",
        }]}}
        document = _document([_line("L4X4 AT THE EDGE")])
        layer = build_engineering_intelligence(document, profile)
        self.assertEqual(layer["incomplete_labels"][0]["printed_fact"], "L4X4")
        self.assertIsNone(layer["incomplete_labels"][0]["resolved_definition"])
        self.assertEqual(layer["incomplete_labels"][0]["status"], "review_required")

    def test_a_word_after_s_is_not_a_sheet_and_a_bare_number_is_not_a_dimension(self):
        self.assertFalse(is_dimension_text("12"))
        self.assertTrue(is_dimension_text("4'-6\""))
        profile = {"sheet_index": {"pages": [
            {"page": 1, "sheet_id": "S101", "sheet_id_status": "read", "sheet_role": "foundation_plan",
             "sheet_title": "FOUNDATION PLAN", "title_status": "read", "classification_status": "read"},
            {"page": 19, "sheet_id": "S-401-O", "sheet_id_status": "read", "sheet_role": "section",
             "sheet_title": "SECTIONS", "title_status": "read", "classification_status": "read"},
        ]}}
        document = _document([
            _line("W/ SPEC", (100, 100, 180, 114)),
            _line("D/S-401-O", (100, 140, 220, 154)),
            _line("12", (200, 180, 230, 194)),
            _line("4'-6\"", (100, 220, 170, 234)),
        ])
        layer = build_engineering_intelligence(document, profile)
        texts = [ref["reference_text"] for ref in layer["references"]]
        self.assertNotIn("W/ SPEC", texts)
        self.assertIn("D/S-401-O", texts)
        self.assertEqual(layer["references"][0]["status"], "target_sheet_only")
        self.assertEqual(layer["references"][0]["target_sheet"], "S-401-O")
        self.assertNotIn("12", [item["value"] for item in layer["dimensions"]])
        self.assertEqual(layer["dimensions"][0]["value"], "4'-6\"")
        self.assertNotIn("12", [item["label"] for item in layer["grids"]])
        self.assertTrue(any(item["text"] == "12" and item["reason"] == "no_grid_line" for item in layer["grid_rejections"]))

    def test_plan_dimension_is_a_dimension_and_not_a_grid(self):
        profile = {"sheet_index": {"pages": [{
            "page": 1, "sheet_id": "S101A", "sheet_id_status": "read",
            "sheet_title": "FOUNDATION PLAN", "title_status": "read",
            "sheet_role": "foundation_plan", "classification_status": "read", "scale": None,
        }]}}
        document = _document([
            _line("4'-6\"", (100, 200, 160, 214)),
            _line("A", (100, 300, 120, 314)),
            _line("DETAIL D", (100, 400, 200, 418)),
        ])
        layer = build_engineering_intelligence(document, profile)
        self.assertEqual(layer["dimensions"][0]["value"], "4'-6\"")
        self.assertNotIn("4'-6\"", [g["label"] for g in layer["grids"]])
        self.assertTrue(any(item["reason"] == "dimension" for item in layer["grid_rejections"]))
        self.assertEqual(layer["grids"][0]["label"], "A")
        self.assertEqual(layer["grids"][0]["status"], "candidate")
        self.assertEqual(layer["grids"][0]["orientation"], "unknown")
        titles = [v["view_title"] for v in layer["views"] if v["status"] == "read"]
        self.assertIn("DETAIL D", titles)

    def test_occurrence_is_not_a_quantity(self):
        profile = {
            "sheet_index": {"pages": [
                {"page": 1, "sheet_id": "S101", "sheet_id_status": "read", "sheet_role": "foundation_plan",
                 "sheet_title": "FOUNDATION PLAN", "title_status": "read", "classification_status": "read"},
                {"page": 2, "sheet_id": "S501", "sheet_id_status": "read", "sheet_role": "schedule",
                 "sheet_title": "COLUMN SCHEDULE", "title_status": "read", "classification_status": "read"},
            ]},
            "definitions": [{"id": "D1", "mark": "C1", "page": 2, "sheet": "S501",
                             "component": "column", "designation": "W12X40"}],
            "levels": {"schedule_levels": [{
                "name": "LEVEL 2", "printed": "55'-10\"", "sheet": "S501", "page": 2,
                "plan_matches": [{"comparison": "differs", "sheet": "S-122-O", "page": 10, "values": [
                    {"raw": "55'-2\"", "surface": "top of slab"},
                ]}],
            }], "plan_elevations": []},
        }
        document = {
            "pages": [
                {"page_number": 1, "width": 1000, "height": 800, "rotation": 0},
                {"page_number": 2, "width": 1000, "height": 800, "rotation": 0},
            ],
            "lines": [
                {"page_number": 1, "text": "C1", "bbox": [100, 100, 130, 114], "font_size": 10},
                {"page_number": 2, "text": "C1", "bbox": [100, 100, 130, 114], "font_size": 10},
                {"page_number": 1, "text": "D/S401", "bbox": [200, 200, 280, 214], "font_size": 10},
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        row = layer["occurrences"][0]
        self.assertEqual(row["status"], "defined_and_seen")
        self.assertIsNone(row["quantity"])
        self.assertEqual(row["occurrence_count"], 1)
        self.assertEqual(layer["levels"]["building_levels"][0]["status"], "conflict")
        self.assertEqual(layer["references"][0]["status"], "target_missing")
        self.assertTrue(any(w["type"] == "level_conflict" for w in layer["warnings"]))


if __name__ == "__main__":
    unittest.main()
