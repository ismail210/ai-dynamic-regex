"""Per-view scale evidence (``view_scale``) and offset placement in the
column-tracing pilot. Synthetic geometry; the real cases (Brandywine S-121 /
S-123 / S-124) are checked in ``test_level_reference_set``."""

from __future__ import annotations

import math
import unittest
from unittest.mock import patch

import fitz

from services.engineering import column_trace as ct
from services.engineering.view_scale import (
    grid_calibration,
    printed_view_scale,
    resolve_view_scale,
)


def _line(text, bbox):
    return {"text": text, "bbox": list(bbox)}


def _axis(angle, c):
    return {"angle": angle, "c": c}


class PrintedScaleTests(unittest.TestCase):
    TITLE = [100, 1000, 500, 1020]

    def test_scale_printed_under_the_view_title(self):
        lines = [_line("LEVEL 2 FRAMING PLAN - OVERALL", self.TITLE), _line('1" = 20\'-0"', (100, 1024, 160, 1034))]
        printed = printed_view_scale(lines, self.TITLE)
        self.assertAlmostEqual(printed["points_per_inch"], 0.3)       # 1" paper per 240" real
        self.assertFalse(printed["nts"])

    def test_nts_under_the_title(self):
        printed = printed_view_scale([_line("NTS", (100, 1024, 130, 1034))], self.TITLE)
        self.assertTrue(printed["nts"])
        self.assertEqual(resolve_view_scale(printed, None, None)["status"], "nts")

    def test_title_block_scale_alone_is_never_used(self):
        # Brandywine: every title block says 1/8" = 1'-0".
        sheet = {"raw": '1/8" = 1\'-0"', "points_per_inch": 0.75}
        resolved = resolve_view_scale(None, sheet, None)
        self.assertEqual((resolved["status"], resolved["points_per_inch"]), ("unresolved", None))

    def test_view_scale_and_contradicting_title_block(self):
        printed = {"raw": '1" = 20\'-0"', "points_per_inch": 0.3, "nts": False}
        sheet = {"raw": '1/8" = 1\'-0"', "points_per_inch": 0.75}
        resolved = resolve_view_scale(printed, sheet, None)
        self.assertEqual(resolved["status"], "printed")
        self.assertIn("title block says", resolved["note"])


class CalibrationTests(unittest.TestCase):
    def grids(self, gap=108.0, angle=90.0):
        # Four parallel grid lines 12'-0" apart at 1/8" = 1'-0" (0.75 pt/in).
        return {name: [_axis(angle, 100 + i * gap)] for i, name in enumerate("ABCD")}

    def dims(self, gap=108.0, angle=90.0, printed="12'-0\""):
        nx, ny = math.sin(math.radians(angle)), -math.cos(math.radians(angle))
        out = []
        for i in range(3):
            c = 100 + i * gap + gap / 2       # between two grid lines
            x, y = nx * c, ny * c            # a point on the normal through the bay centre
            out.append(_line(printed, (x - 10, y - 4, x + 10, y + 4)))
        return out

    def test_three_agreeing_bays_calibrate(self):
        calibration = grid_calibration(self.grids(), self.dims())
        self.assertAlmostEqual(calibration["points_per_inch"], 0.75, places=4)
        self.assertEqual(calibration["bay_count"], 3)

    def test_a_primed_grid_label_is_not_a_dimension(self):
        self.assertIsNone(grid_calibration(self.grids(), self.dims(printed="12'")))

    def test_slanted_grids_calibrate_by_perpendicular_distance(self):
        calibration = grid_calibration(self.grids(angle=80.0), self.dims(angle=80.0))
        self.assertAlmostEqual(calibration["points_per_inch"], 0.75, places=4)

    def test_printed_and_measured_scales(self):
        measured = grid_calibration(self.grids(), self.dims())
        agree = {"raw": '1/8" = 1\'-0"', "points_per_inch": 0.75, "nts": False}
        disagree = {"raw": '1/4" = 1\'-0"', "points_per_inch": 1.5, "nts": False}
        self.assertEqual(resolve_view_scale(agree, None, measured)["status"], "validated")
        self.assertEqual(resolve_view_scale(disagree, None, measured)["status"], "conflicting")
        self.assertEqual(resolve_view_scale(None, None, measured)["status"], "calibrated")

    def test_a_sheet_of_several_views_does_not_calibrate_a_view_alone(self):
        # Grid B drawn twice in one direction (an overall and an enlarged plan).
        grids = {**self.grids(), "B": [_axis(90.0, 208.0), _axis(90.0, 700.0)]}
        calibration = grid_calibration(grids, self.dims())
        self.assertTrue(calibration["several_views"])
        self.assertEqual(resolve_view_scale(None, None, calibration)["status"], "unresolved")
        agree = {"raw": '1/8" = 1\'-0"', "points_per_inch": 0.75, "nts": False}
        self.assertEqual(resolve_view_scale(agree, None, calibration)["status"], "validated")

    def test_calibration_does_not_depend_on_page_rotation(self):
        # The same bays measured on a page turned 90 degrees (x, y) -> (W - y, x).
        turned = {name: [_axis(0.0, -(100 + i * 108.0))] for i, name in enumerate("ABCD")}
        dims = [_line("12'-0\"", (0, 100 + i * 108 + 54 - 4, 20, 100 + i * 108 + 54 + 4)) for i in range(3)]
        self.assertAlmostEqual(grid_calibration(turned, dims)["points_per_inch"], 0.75, places=4)


def _plan(symbols, dims=True):
    """Grids A-D vertical 108 pt apart (12'-0" at 1/8"), grid 2 horizontal;
    column symbols at the given x on grid 2."""

    document = fitz.open()
    page = document.new_page(width=900, height=700)
    for i, name in enumerate("ABCD"):
        x = 100 + i * 108
        page.draw_circle((x, 50), 12, color=(0, 0, 0), width=0.5)
        page.insert_text((x - 3, 53), name, fontsize=9)
        for y in range(62, 660, 20):
            page.draw_line((x, y), (x, y + 12), width=0.3)
        if dims and i < 3:
            page.insert_text((x + 40, 90), "12'-0\"", fontsize=7)
    page.draw_circle((40, 300), 12, color=(0, 0, 0), width=0.5)
    page.insert_text((37, 303), "2", fontsize=9)
    for x in range(52, 860, 20):
        page.draw_line((x, 300), (x + 12, 300), width=0.3)
    for sx in symbols:
        for a, b in (((sx - 5, 292), (sx + 5, 292)), ((sx, 292), (sx, 308)), ((sx - 5, 308), (sx + 5, 308))):
            page.draw_line(a, b, width=2.0)
    words = page.get_text("words")
    drawings = page.get_drawings()
    lines = [{"page_number": 1, "text": " ".join(s["text"] for s in ln["spans"]), "bbox": list(ln["bbox"])}
             for block in page.get_text("dict")["blocks"] for ln in block.get("lines", [])]
    return page, words, drawings, lines


class OffsetPlacementTests(unittest.TestCase):
    def place(self, symbols, printed=None, dims=True):
        page, _, _, lines = _plan(symbols, dims)
        _record, context = ct._analyse_plan(page, 1, ["B", "2"], lines, set())
        (crossing,) = context["crossings"]
        scale = resolve_view_scale(printed, None, context["calibration"])
        # B-2(-4'-0"): 4'-0" = 48" = 36 pt at 0.75 pt/in, perpendicular to grid B.
        return ct._place_offset(crossing, "B", {"raw": "-4'-0\"", "inches": -48.0}, scale, context, set())

    def test_the_drawn_side_is_placed_and_named_by_its_grid(self):
        placed = self.place([208 - 36])
        self.assertEqual(placed["status"], "placed")
        self.assertEqual(placed["points"], 36.0)
        self.assertEqual([(s["toward"], bool(s["symbol"])) for s in placed["sides"]], [("A", True), ("C", False)])

    def test_a_column_on_both_sides_leaves_the_side_unresolved(self):
        self.assertEqual(self.place([172, 244])["status"], "unresolved_direction")

    def test_no_column_at_either_side(self):
        self.assertEqual(self.place([])["status"], "unresolved_direction")

    def test_an_unvalidated_printed_scale_only_gives_a_candidate(self):
        printed = {"raw": '1/8" = 1\'-0"', "points_per_inch": 0.75, "nts": False}
        self.assertEqual(self.place([172], printed=printed, dims=False)["status"], "candidate")

    def test_no_scale_places_nothing(self):
        placed = self.place([172], dims=False)
        self.assertEqual((placed["status"], placed["sides"]), ("unresolved_scale", []))

    def test_a_short_offset_inside_the_search_window_is_not_placed(self):
        # 8 pt is less than twice the 6 pt search window plus half the 16 pt mark.
        page, _, _, lines = _plan([200])
        _record, context = ct._analyse_plan(page, 1, ["B", "2"], lines, set())
        (crossing,) = context["crossings"]
        scale = resolve_view_scale(None, None, context["calibration"])
        placed = ct._place_offset(crossing, "B", {"raw": '-10"', "inches": -8 / 0.75}, scale, context, set())
        self.assertEqual(placed["status"], "candidate")
        self.assertTrue(placed["search_window_limited"])
        self.assertNotIn("placed_bbox", placed)
        self.assertNotIn("toward grid", placed["note"])
        self.assertIn("not established", placed["note"])

    def test_a_short_offset_with_no_mark_stays_unresolved(self):
        page, _, _, lines = _plan([])
        _record, context = ct._analyse_plan(page, 1, ["B", "2"], lines, set())
        (crossing,) = context["crossings"]
        scale = resolve_view_scale(None, None, context["calibration"])
        placed = ct._place_offset(crossing, "B", {"raw": '-10"', "inches": -8 / 0.75}, scale, context, set())
        self.assertEqual(placed["status"], "unresolved_direction")

    def test_a_negative_offset_does_not_name_a_direction(self):
        from services.engineering.column_schedule import parse_grid_location

        parsed = parse_grid_location("E-8(-4'-4\")")
        self.assertEqual(parsed["status"], "parsed")
        offset = next(grid["offset"] for grid in parsed["grids"] if grid.get("offset"))
        self.assertLess(offset["inches"], 0)
        self.assertIsNone(offset["direction"])
        self.assertEqual(self.place([172])["status"], "placed")


class TowardGridTests(unittest.TestCase):
    def _place(self, axes, symbol_on_negative):
        crossing = ((0.0, 0.0), {"R13": axes["R13"][0], "RA.1": {"angle": 0.0, "c": 0.0}})
        context = {"axes": axes, "lines": [], "drawings": [], "segments": []}

        def observe(x, y, *_args):
            symbol = {"bbox": [x - 2, y - 2, x + 2, y + 2]} if symbol_on_negative and x < 0 else None
            return {"point_bbox": [x - 3, y - 3, x + 3, y + 3], "symbol": symbol, "annotations": []}

        with patch.object(ct, "_observe", side_effect=observe):
            return ct._place_offset(crossing, "R13", {"raw": "5' - 4\"", "inches": 30.0},
                                    {"points_per_inch": 1, "status": "validated"}, context, set())

    def test_a_same_family_axis_is_named(self):
        placed = self._place({
            "R13": [{"angle": 90.0, "c": 0.0}],
            "R14": [{"angle": 90.0, "c": -40.0}],
        }, True)
        self.assertEqual(placed["status"], "placed")
        self.assertEqual(placed["sides"][0]["toward"], "R14")
        self.assertIn("toward grid R14", placed["note"])

    def test_a_nearer_axis_of_another_family_is_not_named(self):
        placed = self._place({
            "R13": [{"angle": 90.0, "c": 0.0}],
            "5": [{"angle": 90.0, "c": -10.0}],
            "R14": [{"angle": 90.0, "c": -40.0}],
        }, True)
        self.assertEqual(placed["sides"][0]["toward"], "R14")
        self.assertNotIn("toward grid 5", placed["note"])

    def test_no_same_family_axis_and_an_unknown_label_name_nothing(self):
        placed = self._place({
            "R13": [{"angle": 90.0, "c": 0.0}],
            "5": [{"angle": 90.0, "c": -10.0}],
        }, True)
        self.assertIsNone(placed["sides"][0]["toward"])
        self.assertIn("on one side", placed["note"])
        self.assertIsNone(ct._toward_grid("ROOM", [(4.0, "5")]))


class SlantedGridTests(unittest.TestCase):
    def test_slanted_lines_cross_where_the_geometry_says(self):
        # x = 100 (vertical) and a line through (100, 300) at 10 degrees.
        vertical = {"angle": 90.0, "c": 100.0}
        nx, ny = math.sin(math.radians(10.0)), -math.cos(math.radians(10.0))
        slanted = {"angle": 10.0, "c": nx * 100 + ny * 300}
        x, y = ct._crossing(vertical, slanted)
        self.assertAlmostEqual(x, 100.0, places=6)
        self.assertAlmostEqual(y, 300.0, places=6)
        self.assertIsNone(ct._crossing(vertical, {"angle": 95.0, "c": 50.0}))   # nearly parallel


class CachedOsseOffsetTests(unittest.TestCase):
    """The OSSE extraction cache, when this machine has it. Skipped otherwise."""

    def test_the_short_c4_offset_is_not_placed_and_r13_stays_in_its_own_family(self):
        from services.artifact_store import artifact_path
        from services.staged_pipeline import _current_document, document_source

        path = artifact_path("doc_614ac4c608396a6e", "document.json")
        if not path.is_file():
            self.skipTest("OSSE extraction is not cached")
        document = _current_document("doc_614ac4c608396a6e")
        if document is None:
            self.skipTest("OSSE extraction does not match the current contract")
        before = document.get("schedule_mark_map")
        context = ct.locate_context(document, str(document_source("doc_614ac4c608396a6e")))
        short = ct.locate_location(context, "C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")")
        by_sheet = {view["sheet"]: view for view in short["views"]}
        parking = by_sheet["S101"]
        self.assertNotEqual(parking["state"], "column_symbol_at_offset")
        self.assertTrue(parking["offset"]["search_window_limited"])
        self.assertNotIn("placed_bbox", parking["offset"])
        # The building plan's mark is far enough from the crossing to stay placed.
        self.assertEqual(by_sheet["S121"]["state"], "column_symbol_at_offset")
        ramp = ct.locate_location(context, "R13(5' - 4\")-RA.1")
        named = [view for view in ramp["views"] if view["state"] == "column_symbol_at_offset"]
        self.assertGreaterEqual(len(named), 1)
        for view in named:
            self.assertNotIn("toward grid 5", view["offset"]["note"])
            self.assertNotIn("toward grid 21", view["offset"]["note"])
            self.assertIn("on one side", view["offset"]["note"])
        self.assertEqual(document.get("schedule_mark_map"), before)


if __name__ == "__main__":
    unittest.main()
