"""Explicitly headed THICKNESS / WIDTH / LENGTH cells of plate schedules
(``schedule_grid._interpret_plate`` with ``plate_schedule``)."""

from __future__ import annotations

import unittest

from services.engineering.schedule_grid import (
    _ruled_grids,
    plate_count_per_member,
    resolve_auxiliary_schedule_mark,
)


def _accept(_text: str):
    return None


def _record(title, header, body, groups=None, page=43):
    record = {
        "page": page, "bbox": [0, 0, 500, 300], "layout": "rows", "title": title, "header": header,
        "body": [{"cells": cells, "bbox": [0, 40 + 20 * i, 500, 60 + 20 * i]} for i, cells in enumerate(body)],
    }
    if groups:
        record["header_groups"] = groups
    return record


# Brandywine S-601 p43 BASE PLATE SCHEDULE, as read from the ruled table.
_BRANDYWINE_HEADER = ["TYPE", "TYPE", "BASE PLATE SIZE THICKNESS", "WIDTH", "LENGTH", "ANCHOR ROD QTY", "Ø",
                      "EMBED", "EDGE DISTANCE", "COLUMN WELD", "PLATE WASHER Ø", "THICKNESS", "COMMENTS"]
_BRANDYWINE_GROUPS = ["TYPE", "TYPE", "BASE PLATE SIZE", "BASE PLATE SIZE", "BASE PLATE SIZE", "ANCHOR ROD",
                      "ANCHOR ROD", "ANCHOR ROD", "ANCHOR ROD", "COLUMN WELD", "PLATE WASHER", "PLATE WASHER",
                      "COMMENTS"]
_BP1 = ["BP1", "A", '1 1/4"', "1'-6\"", "1'-6\"", "4", '1"', '8"', '1 1/2"', '1/4"', '2 3/4"', '1/4"', ""]


class HeadedPlateDimensionTests(unittest.TestCase):
    def _bp1(self, groups=_BRANDYWINE_GROUPS):
        (grid,) = _ruled_grids([_record("BASE PLATE SCHEDULE", _BRANDYWINE_HEADER, [_BP1], groups)], _accept)
        return grid["rows"][0]

    def test_feet_inch_cells_are_present_with_the_printed_text(self):
        row = self._bp1()
        parsed = row["parsed_plate"]
        self.assertEqual(row["plate_status"], "present")
        self.assertEqual(parsed["dimensions"], {"thickness": '1 1/4"', "width": "1'-6\"", "length": "1'-6\""})
        # Numbers sit beside the printed text, never in its place.
        self.assertEqual(parsed["dimension_inches"], {"thickness": 1.25, "width": 18.0, "length": 18.0})
        self.assertEqual(parsed["ordered_dimensions"], ['1 1/4"', "1'-6\"", "1'-6\""])

    def test_a_plate_washer_thickness_is_not_the_plate_thickness(self):
        self.assertEqual(self._bp1()["parsed_plate"]["dimensions"]["thickness"], '1 1/4"')

    def test_a_heading_printed_twice_leaves_the_plate_unresolved(self):
        # Without header groups the two THICKNESS columns cannot be told apart.
        row = self._bp1(groups=None)
        self.assertEqual(row["plate_status"], "unresolved")
        self.assertEqual(row["parsed_plate"]["dimensions"]["thickness"], '1 1/4"')

    def test_production_text_fields_are_unchanged(self):
        row = self._bp1()
        # The printed plate / size cells keep the partner's column routing.
        self.assertEqual(row["plate_text"], '2 3/4"')
        self.assertFalse(row["catalog_valid"])
        self.assertIsNone(row["section"])

    def test_footing_sizes_keep_their_previous_status(self):
        (grid,) = _ruled_grids([_record("SPREAD FOOTING SCHEDULE", ["MARK", "WIDTH", "LENGTH", "THICKNESS"],
                                        [["F5", "5' - 0\"", "5' - 0\"", "1' - 0\""]])], _accept)
        row = grid["rows"][0]
        self.assertEqual(row["plate_status"], "unresolved")
        self.assertNotIn("dimension_inches", row["parsed_plate"])
        self.assertEqual(plate_count_per_member(row), 0)

    def test_bent_plate_schedule_stays_generic(self):
        (grid,) = _ruled_grids([_record("BENT PLATE SCHEDULE", ["MARK", "THICKNESS", "WIDTH", "LENGTH"],
                                        [["BP1", '1/2"', "1'-6\"", "1'-6\""]])], _accept)
        row = grid["rows"][0]
        self.assertNotIn("dimension_inches", row["parsed_plate"])
        self.assertNotIn(row.get("plate_role"), {"base_plate", "bearing_plate"})
        # A bent-plate mark is not a base / bearing plate definition.
        self.assertIsNone(resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": [grid]}))

    def test_one_definition_per_mark_is_still_resolved_once(self):
        grids = _ruled_grids([
            _record("BASE PLATE SCHEDULE", _BRANDYWINE_HEADER, [_BP1], _BRANDYWINE_GROUPS),
            _record("COLUMN SCHEDULE", ["MARK", "SIZE", "BASE PLATE"], [["C1", "W12X65", "BP1"]], page=42),
        ], _accept)
        column = next(row for grid in grids if grid["kind"] == "column" for row in grid["rows"])
        self.assertEqual(column["resolved_plate"]["mark"], "BP1")
        self.assertEqual(column["resolved_plate"]["parsed_plate"]["dimensions"]["width"], "1'-6\"")
        self.assertEqual(column["plate_status"], "present")


if __name__ == "__main__":
    unittest.main()
