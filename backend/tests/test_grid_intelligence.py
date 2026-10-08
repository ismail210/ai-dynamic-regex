"""Grid labels need a drawn line. Dimensions, marks, and callouts are not grids."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from services.engineering.grid_intelligence import classify_grid_text, display_segments, merge_chains
from services.engineering.intelligence_layer import build_engineering_intelligence


def _line(text, box, page=1):
    return {"page_number": page, "text": text, "bbox": list(box), "font_size": 12, "rotation": 0}


def _page(lines, segments, views=None):
    profile = {"sheet_index": {"pages": [{
        "page": 1, "sheet_id": "S-101", "sheet_id_status": "read",
        "sheet_title": "FOUNDATION PLAN", "title_status": "read",
        "sheet_role": "foundation_plan", "classification_status": "read",
    }]}}
    document = {
        "page_count": 1,
        "pages": [{"page_number": 1, "width": 1000, "height": 800, "rotation": 0}],
        "lines": lines,
        "grid_line_segments": segments,
    }
    if views:
        document["lines"] = lines + views
    return build_engineering_intelligence(document, profile)


def _h(y, start, end):
    return {"page": 1, "orientation": "horizontal", "axis": y, "start": start, "end": end}


def _v(x, start, end):
    return {"page": 1, "orientation": "vertical", "axis": x, "start": start, "end": end}


class GridTextTests(unittest.TestCase):
    def test_label_grammar_and_rejections(self):
        self.assertEqual(classify_grid_text("A"), "label")
        self.assertEqual(classify_grid_text("10"), "label")
        self.assertEqual(classify_grid_text("A.1"), "label")
        self.assertEqual(classify_grid_text("A-1"), "label")
        self.assertEqual(classify_grid_text("1A"), "label")
        self.assertEqual(classify_grid_text("24K"), "joist_mark")
        self.assertEqual(classify_grid_text("4'-6\""), "dimension")
        self.assertEqual(classify_grid_text("1\""), "dimension")
        self.assertEqual(classify_grid_text("19'-9 5/8\""), "dimension")
        self.assertEqual(classify_grid_text("+14'-6\""), "dimension")
        self.assertEqual(classify_grid_text("C1"), "member_mark")
        self.assertEqual(classify_grid_text("F7"), "member_mark")
        self.assertEqual(classify_grid_text("P1"), "member_mark")
        self.assertEqual(classify_grid_text("D/S401"), "sheet_reference")
        self.assertNotEqual(classify_grid_text("4/S-401"), "label")
        self.assertIsNone(classify_grid_text("TB"))
        self.assertIsNone(classify_grid_text("SEE PLAN"))
        self.assertIsNone(classify_grid_text("ROOM 101"))
        self.assertIsNone(classify_grid_text("W12X40"))

    def test_dashed_segments_merge_and_rotation_follows_display(self):
        dashes = [
            {"orientation": "horizontal", "axis": 100, "start": 0, "end": 20},
            {"orientation": "horizontal", "axis": 101, "start": 50, "end": 400},
        ]
        chains = merge_chains(dashes)
        self.assertEqual(len(chains), 1)
        self.assertGreater(chains[0]["length"], 300)
        point = lambda x, y: SimpleNamespace(x=x, y=y)
        drawings = [{"items": [("l", point(0, 100), point(500, 100))]}]
        segments = display_segments(drawings, 90, 800, 1000)
        self.assertEqual(segments[0]["orientation"], "vertical")


class GridGeometryTests(unittest.TestCase):
    def test_margin_label_on_a_long_line_is_confirmed_and_crosses(self):
        layer = _page([
            _line("A", (40, 200, 60, 216)),
            _line("1", (400, 20, 420, 36)),
            _line("C1", (400, 200, 430, 216)),
        ], [_h(208, 100, 900), _v(410, 40, 700)])
        grids = {item["label"]: item for item in layer["grids"]}
        self.assertEqual(grids["A"]["status"], "confirmed")
        self.assertEqual(grids["A"]["orientation"], "horizontal")
        self.assertEqual(grids["1"]["orientation"], "vertical")
        self.assertEqual(layer["grid_intersections"][0]["display"], "1/A")
        self.assertEqual(layer["grid_intersections"][0]["source_labels"], ["1", "A"])
        allocation = layer["grid_allocations"][0]
        self.assertEqual(allocation["mark"], "C1")
        self.assertEqual(allocation["grid_location"], "1/A")
        self.assertEqual(allocation["allocation_status"], "confirmed")
        self.assertTrue(allocation["evidence"])

    def test_two_separated_copies_of_one_mark_both_stay(self):
        # Furley prints P24 twice, about 88 pt apart, both nearest to one crossing.
        # Same text and same crossing are still two marks; neither is dropped.
        layer = _page([
            _line("A", (40, 200, 60, 216)),
            _line("1", (400, 20, 420, 36)),
            _line("P24", (400, 180, 430, 196)),
            _line("P24", (400, 250, 430, 266)),
        ], [_h(208, 100, 900), _v(410, 40, 700)])
        marks = [item for item in layer["grid_allocations"] if item["mark"] == "P24"]
        self.assertEqual(len(marks), 2)
        self.assertEqual({item["grid_location"] for item in marks}, {"1/A"})
        self.assertGreater(abs(marks[0]["bbox"][1] - marks[1]["bbox"][1]), 40)

    def test_equal_distance_stays_review_required(self):
        layer = _page([
            _line("A", (40, 200, 60, 216)),
            _line("1", (390, 20, 410, 36)),
            _line("2", (470, 20, 490, 36)),
            _line("C2", (425, 200, 455, 216)),
        ], [_h(208, 100, 900), _v(400, 40, 700), _v(480, 40, 700)])
        allocation = next(item for item in layer["grid_allocations"] if item["mark"] == "C2")
        self.assertEqual(allocation["allocation_status"], "review_required")
        self.assertIsNotNone(allocation["grid_location"])

    def test_a_mark_between_grids_stays_unresolved(self):
        layer = _page([
            _line("A", (40, 100, 60, 116)),
            _line("1", (200, 20, 220, 36)),
            _line("C3", (800, 700, 830, 716)),
        ], [_h(108, 80, 600), _v(210, 40, 500)])
        allocation = layer["grid_allocations"][0]
        self.assertEqual(allocation["allocation_status"], "unresolved")
        self.assertIsNone(allocation["grid_location"])

    def test_missing_line_does_not_confirm_and_interior_text_is_rejected(self):
        layer = _page([
            _line("A", (40, 200, 60, 216)),
            _line("12", (400, 400, 430, 416)),
            _line("NOTE", (400, 500, 480, 516)),
        ], [])
        self.assertEqual(layer["grids"][0]["label"], "A")
        self.assertEqual(layer["grids"][0]["status"], "candidate")
        self.assertEqual(layer["grids"][0]["orientation"], "unknown")
        self.assertEqual(layer["grid_intersections"], [])
        self.assertTrue(any(item["text"] == "12" and item["reason"] == "no_grid_line" for item in layer["grid_rejections"]))
        self.assertFalse(any(item["text"] == "NOTE" for item in layer["grid_rejections"]))

    def test_two_view_titles_keep_the_allocation_in_review(self):
        layer = _page([
            _line("A", (40, 200, 60, 216)),
            _line("1", (400, 20, 420, 36)),
            _line("C1", (400, 200, 430, 216)),
            _line("SECTION A", (100, 500, 220, 516)),
            _line("DETAIL D", (400, 500, 520, 516)),
        ], [_h(208, 100, 900), _v(410, 40, 700)])
        self.assertGreaterEqual(sum(1 for view in layer["views"] if view["status"] == "read"), 2)
        self.assertEqual(layer["grid_allocations"][0]["allocation_status"], "review_required")

    def test_a_second_copy_does_not_erase_the_outer_grid(self):
        layer = _page([
            _line("A", (40, 200, 60, 216)),
            _line("A", (400, 20, 420, 36)),
        ], [_h(208, 100, 900), _v(410, 40, 700)])
        confirmed = [item for item in layer["grids"] if item["status"] == "confirmed" and item["label"] == "A"]
        self.assertTrue(any(item["orientation"] == "horizontal" and item["bbox"][0] < 80 for item in confirmed))

    def test_an_inward_digit_on_a_distant_line_is_not_a_grid(self):
        layer = _page([
            _line("A", (20, 200, 40, 216)),
            _line("1", (110, 400, 130, 416)),
            _line("4'-6\"", (20, 500, 90, 516)),
            _line("24K", (20, 540, 70, 556)),
            _line("C1", (20, 580, 60, 596)),
            _line("D/S401", (20, 620, 120, 636)),
            _line("TB", (20, 660, 50, 676)),
        ], [_h(208, 80, 900), _h(408, 500, 950)])
        confirmed = [item["label"] for item in layer["grids"] if item["status"] == "confirmed"]
        self.assertIn("A", confirmed)
        self.assertNotIn("1", confirmed)
        reasons = {item["text"]: item["reason"] for item in layer["grid_rejections"]}
        self.assertEqual(reasons["4'-6\""], "dimension")
        self.assertEqual(reasons["24K"], "joist_mark")
        self.assertEqual(reasons["C1"], "member_mark")
        self.assertEqual(reasons["D/S401"], "sheet_reference")
        self.assertNotIn("TB", confirmed)
        layer = _page([
            _line("A", (40, 200, 60, 216)),
            _line("B", (40, 214, 60, 230)),
        ], [_h(208, 100, 900)])
        by_label = {item["label"]: item["status"] for item in layer["grids"]}
        self.assertEqual(by_label["A"], "confirmed")
        self.assertEqual(by_label["B"], "review_required")
        self.assertEqual(layer["grid_intersections"], [])

    def test_a_partial_line_does_not_invent_a_crossing(self):
        layer = _page([
            _line("A", (40, 200, 60, 216)),
            _line("1", (700, 20, 720, 36)),
        ], [_h(208, 80, 500), _v(710, 40, 700)])
        self.assertEqual(layer["grids"][0]["status"], "confirmed")
        self.assertEqual({item["label"] for item in layer["grids"] if item["status"] == "confirmed"}, {"A", "1"})
        self.assertEqual(layer["grid_intersections"], [])

    def test_an_offset_label_confirms_only_while_it_stays_near_the_line(self):
        near = _page([_line("A", (40, 190, 60, 206))], [_h(210, 80, 900)])
        self.assertEqual(near["grids"][0]["status"], "confirmed")
        far = _page([_line("A", (40, 190, 60, 206))], [_h(280, 80, 900)])
        self.assertEqual(far["grids"][0]["status"], "candidate")
        self.assertEqual(far["grid_intersections"], [])
        layer = _page([
            _line("4'-6\"", (40, 300, 120, 316)),
            _line("C1", (40, 340, 80, 356)),
            _line("D/S401", (40, 380, 140, 396)),
        ], [])
        diagnostics = layer["grid_diagnostics"]
        self.assertGreaterEqual(diagnostics["false_positive_rejections"], 3)
        self.assertEqual(diagnostics["confirmed_grid_labels"], 0)
        self.assertEqual(diagnostics["grid_intersections"], 0)

    def test_dashed_axis_confirms_and_one_short_segment_does_not(self):
        dashes = [_v(400, y, y + 12) for y in range(80, 280, 12)]
        dashed = _page([_line("5", (390, 20, 410, 36))], dashes)
        grid = next(item for item in dashed["grids"] if item["label"] == "5")
        self.assertEqual(grid["status"], "confirmed")
        self.assertEqual(grid["orientation"], "vertical")
        self.assertTrue(grid["line"]["fragmented"])
        self.assertGreaterEqual(grid["line"]["segment_count"], 4)
        short = _page([_line("5", (390, 20, 410, 36))], [_v(400, 80, 280)])
        self.assertEqual(short["grids"][0]["status"], "candidate")

    def test_outside_margin_needs_a_supported_line_at_the_label(self):
        # 0.14 * 800 = 112. y=130 is just outside that band.
        strong = _page([_line("8", (390, 122, 410, 138))], [_v(400, 125, 620)])
        self.assertEqual(strong["grids"][0]["status"], "confirmed")
        middle = _page([_line("8", (390, 400, 410, 416))], [_v(400, 390, 760)])
        self.assertNotIn("8", [item["label"] for item in middle["grids"] if item["status"] == "confirmed"])
        weak = _page([_line("8", (390, 122, 410, 138))], [_v(400, 125, 280)])
        self.assertNotIn("8", [item["label"] for item in weak["grids"] if item["status"] == "confirmed"])

    def test_a_sheet_border_is_not_a_grid_line(self):
        layer = _page([_line("5", (40, 760, 60, 776))], [_h(750, 0, 900)])
        self.assertNotIn("5", [item["label"] for item in layer["grids"] if item["status"] == "confirmed"])

    def test_a_grid_past_the_title_cut_confirms_when_it_continues_a_row(self):
        layer = _page([
            _line("4", (180, 20, 200, 36)),
            _line("3", (330, 20, 350, 36)),
            _line("2", (480, 20, 500, 36)),
            _line("1", (870, 20, 890, 36)),
        ], [_v(880, 40, 520)])
        confirmed = [item for item in layer["grids"] if item["status"] == "confirmed"]
        self.assertEqual([item["label"] for item in confirmed], ["1"])
        self.assertEqual(confirmed[0]["view_id"], None)

    def test_the_same_label_at_both_ends_is_kept_as_one_axis(self):
        layer = _page([
            _line("4", (390, 20, 410, 36)),
            _line("4", (390, 760, 410, 776)),
            _line("A", (40, 400, 60, 416)),
        ], [_v(400, 30, 750), _h(408, 80, 900)])
        ends = [item for item in layer["grids"] if item["label"] == "4" and item["status"] == "confirmed"]
        self.assertEqual(len(ends), 2)
        self.assertEqual(len(layer["grid_intersections"]), 1)
        self.assertIsNone(ends[0]["view_id"])

    def test_a_singleton_off_the_end_of_the_line_is_not_a_grid(self):
        layer = _page([_line("N", (200, 700, 220, 716))], [_v(210, 40, 500)])
        self.assertNotIn("N", [item["label"] for item in layer["grids"] if item["status"] == "confirmed"])

    def test_two_regions_keep_two_copies_of_the_same_label(self):
        layer = _page([
            _line("C", (40, 200, 60, 216)),
            _line("C", (40, 500, 60, 516)),
            _line("5", (290, 20, 310, 36)),
        ], [_h(208, 80, 500), _h(508, 80, 500), _v(300, 40, 700)])
        copies = [item for item in layer["grids"] if item["label"] == "C" and item["status"] == "confirmed"]
        self.assertEqual(len(copies), 2)
        self.assertEqual(sorted(item["display"] for item in layer["grid_intersections"]), ["5/C", "5/C"])
        self.assertNotEqual(copies[0]["bbox"], copies[1]["bbox"])

    def test_the_label_on_the_line_beats_a_farther_margin_label(self):
        # 0.14 * 800 = 112. y=128 is outside that band. The bottom 4 is in the margin
        # but 40px off the line, so it does not own the line that starts at the 6.
        layer = _page([
            _line("6", (392, 118, 408, 138)),
            _line("4", (428, 750, 452, 776)),
        ], [_v(400, 140, 500)])
        confirmed = [item for item in layer["grids"] if item["status"] == "confirmed"]
        self.assertEqual([item["label"] for item in confirmed], ["6"])
        self.assertEqual(confirmed[0]["line"]["axis"], 400)

    def test_a_letter_stacked_on_a_sheet_id_is_not_a_grid(self):
        layer = _page([
            _line("F", (360, 200, 376, 214)),
            _line("S401", (352, 218, 384, 230)),
            _line("A", (40, 400, 56, 416)),
            _line("B", (40, 460, 56, 476)),
            _line("C", (40, 520, 56, 536)),
        ], [_h(207, 80, 700), _h(408, 80, 700), _h(468, 80, 700), _h(528, 80, 700)])
        confirmed = [item["label"] for item in layer["grids"] if item["status"] == "confirmed"]
        self.assertNotIn("F", confirmed)
        self.assertIn("A", confirmed)
        reasons = {item["text"]: item["reason"] for item in layer["grid_rejections"]}
        self.assertEqual(reasons["F"], "sheet_callout")

    def test_a_digit_beside_a_foot_station_is_not_a_grid(self):
        layer = _page([
            _line("0", (200, 740, 214, 756)),
            _line("4'", (230, 740, 250, 756)),
            _line("5", (400, 740, 416, 756)),
            _line("6", (460, 740, 476, 756)),
            _line("7", (520, 740, 536, 756)),
        ], [_v(207, 80, 700), _v(408, 80, 720)])
        confirmed = [item["label"] for item in layer["grids"] if item["status"] == "confirmed"]
        self.assertNotIn("0", confirmed)
        self.assertIn("5", confirmed)
        reasons = {item["text"]: item["reason"] for item in layer["grid_rejections"]}
        self.assertEqual(reasons["0"], "dimension_station")
