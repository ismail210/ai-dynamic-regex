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


def _line(text, box=(10, 10, 80, 22), page=1):
    return {"page_number": page, "text": text, "bbox": list(box), "font_size": 10, "rotation": 0}


def _document(lines, page=1, width=1000, height=800, pages=None):
    return {
        "page_count": len(pages) if pages else 1,
        "pages": pages or [{"page_number": page, "width": width, "height": height, "rotation": 0}],
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


def _sheet(page, sheet_id, title, role):
    return {
        "page": page, "sheet_id": sheet_id, "sheet_id_status": "read",
        "sheet_title": title, "title_status": "read", "sheet_role": role,
        "classification_status": "read",
    }


def _pages(*pairs):
    return [{"page_number": page, "width": 3024, "height": 2160, "rotation": 0} for page, _ in pairs]


class AdjacentViewNumberTests(unittest.TestCase):
    def test_a_letter_beside_section_is_that_view(self):
        profile = {"sheet_index": {"pages": [
            _sheet(1, "S101A", "FRAMING PLAN", "framing_plan"),
            _sheet(21, "S502", "SECTIONS", "section"),
        ]}}
        document = {
            "pages": _pages((1, None), (21, None)),
            "lines": [
                {"page_number": 1, "text": "N/S502", "bbox": [100, 100, 180, 114], "font_size": 10, "rotation": 0},
                {"page_number": 21, "text": "N", "bbox": [634.2, 2053.8, 649.0, 2078.7], "font_size": 12, "rotation": 0},
                {"page_number": 21, "text": "SECTION", "bbox": [675.1, 2052.7, 766.2, 2077.6], "font_size": 12, "rotation": 0},
                {"page_number": 21, "text": "S502", "bbox": [631.0, 2084.9, 652.1, 2096.0], "font_size": 8, "rotation": 0},
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        view = next(v for v in layer["views"] if v["view_number"] == "N")
        self.assertEqual(view["view_title"], "SECTION")
        self.assertEqual(view["bbox"], [634.2, 2052.7, 766.2, 2078.7])
        self.assertEqual(view["evidence"], "printed view number beside the title")
        ref = next(r for r in layer["references"] if r["reference_text"] == "N/S502")
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_sheet"], "S502")
        self.assertEqual(ref["target_view"], view["view_id"])

    def test_two_numbers_beside_the_title_are_not_chosen(self):
        profile = {"sheet_index": {"pages": [
            _sheet(1, "S101A", "FRAMING PLAN", "framing_plan"),
            _sheet(21, "S502", "SECTIONS", "section"),
        ]}}
        document = {
            "pages": _pages((1, None), (21, None)),
            "lines": [
                {"page_number": 1, "text": "A/S502", "bbox": [100, 100, 180, 114], "font_size": 10, "rotation": 0},
                {"page_number": 21, "text": "A", "bbox": [162, 703, 176, 728], "font_size": 12, "rotation": 0},
                {"page_number": 21, "text": "SECTION", "bbox": [203, 702, 294, 727], "font_size": 12, "rotation": 0},
                {"page_number": 21, "text": "B", "bbox": [320, 703, 334, 728], "font_size": 12, "rotation": 0},
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        self.assertFalse(any(v.get("view_number") in ("A", "B") for v in layer["views"]))
        ref = next(r for r in layer["references"] if r["reference_text"] == "A/S502")
        self.assertEqual(ref["status"], "target_sheet_only")
        self.assertIsNone(ref["target_view"])

    def test_s401_without_the_suffix_stays_missing(self):
        profile = {"sheet_index": {"pages": [
            _sheet(1, "S-101-O", "FRAMING PLAN", "framing_plan"),
            _sheet(15, "S-401-O", "SECTIONS", "section"),
        ]}}
        document = {
            "pages": _pages((1, None), (15, None)),
            "lines": [
                {"page_number": 1, "text": "4/S-401", "bbox": [100, 100, 190, 114], "font_size": 10, "rotation": 0},
                {"page_number": 1, "text": "4/S-401-O", "bbox": [100, 140, 210, 154], "font_size": 10, "rotation": 0},
                {"page_number": 15, "text": "4", "bbox": [100, 200, 114, 225], "font_size": 12, "rotation": 0},
                {"page_number": 15, "text": "SECTION", "bbox": [140, 200, 230, 225], "font_size": 12, "rotation": 0},
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        by_text = {r["reference_text"]: r for r in layer["references"]}
        self.assertEqual(by_text["4/S-401"]["status"], "target_missing")
        self.assertEqual(by_text["4/S-401"]["target_sheet"], "S-401")
        self.assertEqual(by_text["4/S-401-O"]["status"], "target_view_found")
        self.assertEqual(by_text["4/S-401-O"]["target_sheet"], "S-401-O")
        self.assertEqual(by_text["4/S-401-O"]["target_number"], "4")

    def test_a_circle_number_beside_a_scaled_section_is_that_view(self):
        profile = {"sheet_index": {"pages": [
            _sheet(4, "S-101A", "FRAMING PLAN", "framing_plan"),
            _sheet(22, "S-301", "SECTIONS", "section"),
        ]}}
        document = {
            "pages": _pages((4, None), (22, None)),
            "lines": [
                _line("7/S-301", (100, 100, 180, 114), page=4),
                _line("SECTION", (1564, 1337, 1649, 1356), page=22),
                _line("7", (1698, 1338, 1716, 1356), page=22),
                _line('SCALE: 3/4" = 1\'-0"', (1564, 1367, 1649, 1377), page=22),
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        view = next(v for v in layer["views"] if v.get("view_number") == "7")
        self.assertEqual(view["view_type"], "section")
        ref = next(r for r in layer["references"] if r["reference_text"] == "7/S-301")
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_view"], view["view_id"])
        self.assertIn("target_bbox", ref)

    def test_an_elevation_number_beside_the_title_is_that_view(self):
        profile = {"sheet_index": {"pages": [
            _sheet(4, "S-101A", "FRAMING PLAN", "framing_plan"),
            _sheet(26, "S-401", "ELEVATIONS", "elevation"),
        ]}}
        document = {
            "pages": _pages((4, None), (26, None)),
            "lines": [
                _line("2/S-401", (100, 100, 190, 114), page=4),
                _line("ELEVATION", (564, 656, 670, 675), page=26),
                _line("2", (705, 658, 720, 675), page=26),
                _line('SCALE: 3/16" = 1\'-0"', (571, 686, 661, 697), page=26),
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        view = next(v for v in layer["views"] if v.get("view_number") == "2")
        self.assertEqual(view["view_type"], "elevation")
        ref = next(r for r in layer["references"] if r["reference_text"] == "2/S-401")
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_view_type"], "elevation")

    def test_an_abbreviation_legend_is_not_a_view_number(self):
        profile = {"sheet_index": {"pages": [
            _sheet(2, "S-001", "GENERAL NOTES", "general_notes"),
        ]}}
        document = {
            "pages": _pages((2, None)),
            "lines": [
                _line("EL", (2143, 1333, 2156, 1346), page=2),
                _line("ELEVATION", (2206, 1333, 2265, 1346), page=2),
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        self.assertFalse(any(v.get("view_number") == "EL" for v in layer["views"]))

    def test_a_detail_title_takes_the_number_on_its_row(self):
        profile = {"sheet_index": {"pages": [
            _sheet(7, "S-111", "FOUNDATION PLAN", "foundation_plan"),
            _sheet(32, "S-500", "TYPICAL FOUNDATION DETAILS", "detail"),
        ]}}
        document = {
            "pages": _pages((7, None), (32, None)),
            "lines": [
                _line("4/S-500", (100, 100, 190, 114), page=7),
                _line("4", (180, 1417, 196, 1430), page=32),
                _line("TYPICAL FOUNDATION WALL DETAIL", (216, 1408, 520, 1432), page=32),
                _line('1" = 1\'-0"', (220, 1436, 280, 1448), page=32),
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        view = next(v for v in layer["views"] if v.get("view_number") == "4")
        self.assertEqual(view["view_title"], "TYPICAL FOUNDATION WALL DETAIL")
        ref = next(r for r in layer["references"] if r["reference_text"] == "4/S-500")
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_view"], view["view_id"])
        self.assertIn("target_bbox", ref)

    def test_a_number_printed_against_the_title_word_is_that_view(self):
        profile = {"sheet_index": {"pages": [
            _sheet(8, "S-112", "FOUNDATION PLAN", "foundation_plan"),
            _sheet(34, "S-502", "TYPICAL SLAB ON GRADE DETAILS", "detail"),
        ]}}
        document = {
            "pages": _pages((8, None), (34, None)),
            "lines": [
                _line("11/S-502", (100, 100, 200, 114), page=8),
                _line("11TYPICAL EQUIPMENT PAD DETAIL", (200, 1490, 520, 1508), page=34),
                _line('1/2" = 1\'-0"', (200, 1512, 280, 1524), page=34),
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        view = next(v for v in layer["views"] if v.get("view_number") == "11")
        self.assertEqual(view["view_title"], "TYPICAL EQUIPMENT PAD DETAIL")
        ref = next(r for r in layer["references"] if r["reference_text"] == "11/S-502")
        self.assertEqual(ref["status"], "target_view_found")

    def test_a_file_path_beside_a_number_is_not_a_view(self):
        profile = {"sheet_index": {"pages": [
            _sheet(25, "S-200", "BRACED FRAME ELEVATIONS", "elevation"),
        ]}}
        document = {
            "pages": _pages((25, None)),
            "lines": [
                _line("4", (100, 400, 114, 414), page=25),
                _line("Autodesk Docs://building/model.rvt", (134, 398, 500, 416), page=25),
                _line('1/8" = 1\'-0"', (134, 420, 230, 432), page=25),
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        self.assertFalse(any(v.get("view_number") == "4" for v in layer["views"]))

    def test_the_plan_title_with_a_number_is_that_view(self):
        profile = {"sheet_index": {"pages": [
            _sheet(4, "S-003", "FLOOR LOADING PLAN", "loading_plan"),
            _sheet(7, "S-111", "FOUNDATION PLAN - AREA A", "foundation_plan"),
        ]}}
        document = {
            "pages": _pages((4, None), (7, None)),
            "lines": [
                _line("1/S-111", (100, 100, 190, 114), page=4),
                _line("1", (180, 200, 194, 214), page=7),
                _line("FOUNDATION PLAN - AREA A", (214, 198, 520, 216), page=7),
                _line('1/8" = 1\'-0"', (214, 220, 310, 232), page=7),
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        view = next(v for v in layer["views"] if v.get("view_number") == "1")
        self.assertEqual(view["view_title"], "FOUNDATION PLAN - AREA A")
        ref = next(r for r in layer["references"] if r["reference_text"] == "1/S-111")
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_sheet"], "S-111")

    def test_a_mixed_inch_scale_still_marks_the_detail(self):
        profile = {"sheet_index": {"pages": [
            _sheet(7, "S-111", "FOUNDATION PLAN", "foundation_plan"),
            _sheet(40, "S-530", "MASONRY DETAILS", "detail"),
        ]}}
        document = {
            "pages": _pages((7, None), (40, None)),
            "lines": [
                _line("1/S-530", (100, 100, 190, 114), page=7),
                _line("1", (144, 449, 151, 462), page=40),
                _line("CMU CONTROL JOINT", (171, 440, 435, 465), page=40),
                _line('1 1/2" = 1\'-0"', (175, 465, 250, 477), page=40),
            ],
        }
        layer = build_engineering_intelligence(document, profile)
        view = next(v for v in layer["views"] if v.get("view_number") == "1" and v.get("sheet_id") == "S-530")
        self.assertEqual(view["view_title"], "CMU CONTROL JOINT")
        ref = next(r for r in layer["references"] if r["reference_text"] == "1/S-530")
        self.assertEqual(ref["status"], "target_view_found")


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


def _pages_for(rotation, width, height):
    return [
        {"page_number": 1, "width": width, "height": height, "rotation": rotation},
        {"page_number": 2, "width": width, "height": height, "rotation": rotation},
    ]


def _pdf_box(box, rotation, width, height):
    from services.engineering.page_space import to_pdf

    return to_pdf(rotation, width, height, box)


class StackedCalloutTests(unittest.TestCase):
    def _layer(self, source, target, target_sheet="S-301-O", rotation=0, width=1000, height=800):
        profile = {"sheet_index": {"pages": [
            _sheet(1, "S-101-O", "FOUNDATION PLAN", "foundation_plan"),
            _sheet(2, target_sheet, "SECTIONS", "section"),
        ]}}
        lines = []
        for text, box in source:
            lines.append({"page_number": 1, "text": text, "bbox": list(box), "font_size": 10, "rotation": 0})
        for text, box in target:
            lines.append({"page_number": 2, "text": text, "bbox": list(box), "font_size": 10, "rotation": 0})
        document = {
            "pages": _pages_for(rotation, width, height),
            "lines": lines,
            "schedule_mark_map": {"C1": "W12X40"},
        }
        return document, build_engineering_intelligence(document, profile)

    def test_a_number_above_a_sheet_finds_the_printed_section(self):
        _document, layer = self._layer(
            [("6", (118, 10, 132, 22)), ("S-301-O", (100, 26, 170, 38))],
            [("6", (200, 400, 214, 424)), ("SECTION", (230, 400, 320, 424))],
        )
        (ref,) = [item for item in layer["references"] if item["reference_text"] == "6/S-301-O"]
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_sheet"], "S-301-O")
        self.assertEqual(ref["target_number"], "6")
        self.assertEqual(ref["target_view_type"], "section")
        self.assertEqual(ref["target_bbox"], [200.0, 400.0, 320.0, 424.0])
        self.assertIn("one printed Section 6 view", ref["evidence"])
        self.assertEqual(ref["source_sheet"], "S-101-O")
        self.assertEqual(ref["bbox"], [100.0, 10.0, 170.0, 38.0])

    def test_a_letter_above_a_sheet_finds_that_section(self):
        _document, layer = self._layer(
            [("N", (118, 10, 132, 22)), ("S502", (100, 26, 150, 38))],
            [("N", (200, 400, 214, 424)), ("SECTION", (230, 400, 320, 424))],
            target_sheet="S502",
        )
        (ref,) = [item for item in layer["references"] if item["reference_text"] == "N/S502"]
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_number"], "N")

    def test_a_sheet_without_the_view_stays_sheet_only(self):
        _document, layer = self._layer(
            [("6", (118, 10, 132, 22)), ("S-301-O", (100, 26, 170, 38))],
            [],
        )
        (ref,) = layer["references"]
        self.assertEqual(ref["status"], "target_sheet_only")
        self.assertNotIn("target_bbox", ref)

    def test_a_missing_sheet_stays_missing(self):
        profile = {"sheet_index": {"pages": [
            _sheet(1, "S-101-O", "FOUNDATION PLAN", "foundation_plan"),
        ]}}
        document = _document([
            _line("6", (118, 10, 132, 22)),
            _line("S-999", (100, 26, 160, 38)),
        ])
        layer = build_engineering_intelligence(document, profile)
        (ref,) = layer["references"]
        self.assertEqual(ref["status"], "target_missing")
        self.assertEqual(ref["target_sheet"], "S-999")
        self.assertNotIn("target_bbox", ref)

    def test_two_labels_above_one_sheet_make_no_reference(self):
        _document, layer = self._layer(
            [("6", (118, 10, 132, 22)), ("7", (133, 10, 147, 22)), ("S-301-O", (100, 26, 170, 38))],
            [("6", (200, 400, 214, 424)), ("SECTION", (230, 400, 320, 424))],
        )
        self.assertFalse(any("S-301-O" in item["reference_text"] for item in layer["references"]))

    def test_two_views_with_the_same_number_stay_ambiguous(self):
        _document, layer = self._layer(
            [("6", (118, 10, 132, 22)), ("S-301-O", (100, 26, 170, 38))],
            [("6 SECTION", (100, 200, 200, 220)), ("6 SECTION", (100, 300, 200, 320))],
        )
        (ref,) = [item for item in layer["references"] if item["reference_text"] == "6/S-301-O"]
        self.assertEqual(ref["status"], "ambiguous")
        self.assertIsNone(ref["target_view"])
        self.assertNotIn("target_bbox", ref)

    def test_a_callout_in_the_lower_band_is_kept(self):
        _document, layer = self._layer(
            [("7", (808, 1852, 814, 1861)), ("S-301", (799, 1868, 824, 1877))],
            [],
            target_sheet="S-301", width=3024, height=2160,
        )
        found = [item for item in layer["references"] if item["reference_text"] == "7/S-301"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["status"], "target_sheet_only")

    def test_repeated_callouts_are_kept(self):
        _document, layer = self._layer(
            [
                ("7", (118, 10, 132, 22)), ("S-301", (100, 26, 160, 38)),
                ("7", (318, 10, 332, 22)), ("S-301", (300, 26, 360, 38)),
                ("7", (518, 10, 532, 22)), ("S-301", (500, 26, 560, 38)),
                ("7", (718, 10, 732, 22)), ("S-301", (700, 26, 760, 38)),
            ],
            [("7", (200, 400, 214, 424)), ("SECTION", (230, 400, 320, 424))],
            target_sheet="S-301",
        )
        found = [item for item in layer["references"] if item["reference_text"] == "7/S-301"]
        self.assertEqual(len(found), 4)
        self.assertEqual({tuple(item["bbox"]) for item in found}, {
            (100.0, 10.0, 160.0, 38.0),
            (300.0, 10.0, 360.0, 38.0),
            (500.0, 10.0, 560.0, 38.0),
            (700.0, 10.0, 760.0, 38.0),
        })

    def test_an_inline_reference_still_resolves(self):
        _document, layer = self._layer(
            [("N/S502", (100, 100, 180, 114))],
            [("N", (200, 400, 214, 424)), ("SECTION", (230, 400, 320, 424))],
            target_sheet="S502",
        )
        (ref,) = [item for item in layer["references"] if item["reference_text"] == "N/S502"]
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_bbox"], [200.0, 400.0, 320.0, 424.0])

    def test_a_rotated_page_keeps_display_coordinates(self):
        from services.engineering.page_space import to_display

        width, height, rotation = 3024.0, 2160.0, 90
        label = [118.0, 10.0, 132.0, 22.0]
        sheet = [100.0, 26.0, 170.0, 38.0]
        number = [200.0, 400.0, 214.0, 424.0]
        title = [230.0, 400.0, 320.0, 424.0]
        pdf_label = _pdf_box(label, rotation, width, height)
        pdf_sheet = _pdf_box(sheet, rotation, width, height)
        pdf_number = _pdf_box(number, rotation, width, height)
        pdf_title = _pdf_box(title, rotation, width, height)
        _document, layer = self._layer(
            [("4", pdf_label), ("S3.16", pdf_sheet)],
            [("4", pdf_number), ("SECTION", pdf_title)],
            target_sheet="S3.16", rotation=rotation, width=width, height=height,
        )
        (ref,) = [item for item in layer["references"] if item["reference_text"] == "4/S3.16"]
        self.assertEqual(ref["status"], "target_view_found")

        def _union(boxes):
            return [
                min(box[0] for box in boxes), min(box[1] for box in boxes),
                max(box[2] for box in boxes), max(box[3] for box in boxes),
            ]

        shown = [to_display(rotation, width, height, box) for box in (pdf_label, pdf_sheet)]
        self.assertEqual(ref["bbox"], _union(shown))
        self.assertNotEqual(ref["bbox"], _union([pdf_label, pdf_sheet]))
        shown_view = [to_display(rotation, width, height, box) for box in (pdf_number, pdf_title)]
        self.assertEqual(ref["target_bbox"], _union(shown_view))

    def test_named_drawing_callouts_keep_their_status(self):
        _doc, layer = self._layer(
            [("H", (118, 10, 132, 22)), ("S302", (100, 26, 150, 38))],
            [],
            target_sheet="S302",
        )
        (ref,) = [item for item in layer["references"] if item["reference_text"] == "H/S302"]
        self.assertEqual(ref["status"], "target_sheet_only")
        self.assertNotIn("target_bbox", ref)

        profile = {"sheet_index": {"pages": [
            _sheet(1, "S-101-O", "FOUNDATION PLAN", "foundation_plan"),
            _sheet(2, "S-401-O", "SECTIONS", "section"),
        ]}}
        missing = _document([
            _line("4", (118, 10, 132, 22)),
            _line("S-401", (100, 26, 160, 38)),
        ])
        missing_layer = build_engineering_intelligence(missing, profile)
        (ref,) = missing_layer["references"]
        self.assertEqual(ref["reference_text"], "4/S-401")
        self.assertEqual(ref["status"], "target_missing")
        self.assertNotIn("target_bbox", ref)

        found = _document([
            _line("4", (118, 10, 132, 22), page=1),
            _line("S-401-O", (100, 26, 170, 38), page=1),
            _line("4", (200, 400, 214, 424), page=2),
            _line("SECTION", (230, 400, 320, 424), page=2),
        ], pages=_pages_for(0, 1000, 800))
        found_layer = build_engineering_intelligence(found, profile)
        (ref,) = [item for item in found_layer["references"] if item["reference_text"] == "4/S-401-O"]
        self.assertEqual(ref["status"], "target_view_found")
        self.assertEqual(ref["target_bbox"], [200.0, 400.0, 320.0, 424.0])

    def test_unrelated_text_and_a_decimal_are_not_callouts(self):
        profile = {"sheet_index": {"pages": [
            _sheet(1, "S-101", "FOUNDATION PLAN", "foundation_plan"),
            _sheet(2, "S-103", "SECTIONS", "section"),
        ]}}
        document = _document([
            _line("SEE DETAIL"),
            _line("SEE PLAN AND"),
            _line("6"),
            _line("4'-6\""),
            _line("A"),
            _line("W"),
            _line("SPEC"),
            _line("6.1/S-103"),
        ])
        layer = build_engineering_intelligence(document, profile)
        texts = [item["reference_text"] for item in layer["references"]]
        self.assertEqual(texts, [])
        self.assertNotIn("1/S-103", texts)

    def test_references_do_not_change_the_mark_map(self):
        document, layer = self._layer(
            [("6", (118, 10, 132, 22)), ("S-301-O", (100, 26, 170, 38))],
            [("6", (200, 400, 214, 424)), ("SECTION", (230, 400, 320, 424))],
        )
        self.assertEqual(document["schedule_mark_map"], {"C1": "W12X40"})
        self.assertNotIn("schedule_mark_map", layer)
        self.assertTrue(all("quantity" not in item for item in layer["references"]))
        self.assertTrue(layer["references"])

    def test_production_modules_do_not_read_references(self):
        import inspect

        import services.prediction.orchestrator as orchestrator
        import services.structural_parser as structural_parser
        import services.takeoff.quantity_engine as quantity_engine
        import services.takeoff.takeoff_exporter as takeoff_exporter
        import services.wildcard_matcher as wildcard_matcher

        for module in (orchestrator, quantity_engine, takeoff_exporter, structural_parser, wildcard_matcher):
            source = inspect.getsource(module)
            self.assertNotIn("engineering_intelligence", source)
            self.assertNotIn("target_view_found", source)


if __name__ == "__main__":
    unittest.main()
