"""Column schedule reading: grid locations, plate sizes, references, visibility.

Expected values are the printed text of real sheets (file / page / sheet in
each comment), read from the rendered drawing, not from parser output.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.column_schedule import (
    _plate_table,
    build_column_schedules,
    column_schedule_view,
    lookup_plate_mark,
    parse_drawing_reference,
    parse_grid_location,
    parse_plate_cell,
    plate_index,
    split_locations,
    visible_phrases,
)
from services.engineering.schedule_grid import build_document_schedule_grids, schedule_mark_map
from services.engineering.schedule_tables import read_ruled_tables


def _grids(text):
    parsed = parse_grid_location(text)
    return [g["label"] for g in parsed["grids"]], parsed


class GridLocationTests(unittest.TestCase):
    def test_conventional_intersection(self):
        labels, parsed = _grids("A-6")
        self.assertEqual(labels, ["A", "6"])
        self.assertEqual(parsed["status"], "parsed")
        self.assertEqual(parsed["raw"], "A-6")

    def test_decimal_grids(self):
        # OSSE - ST.pdf p26 S-602-O: "C.1-5.1", "C.8-8.9"
        self.assertEqual(_grids("C.1-5.1")[0], ["C.1", "5.1"])
        self.assertEqual(_grids("B.2-3.5")[0], ["B.2", "3.5"])

    def test_prime_grids_keep_their_primes(self):
        # Brandywine Structural4.pdf p42 S-600: "A.1'-18"; Burrville p29 S-502: "H.4'-5.8'"
        self.assertEqual(_grids("A.1'-18")[0], ["A.1'", "18"])
        self.assertEqual(_grids("H.4'-5.8'")[0], ["H.4'", "5.8'"])
        self.assertEqual(_grids("C'-15.6")[0], ["C'", "15.6"])
        self.assertEqual(_grids("8.1′-B")[0], ["8.1′", "B"])

    def test_double_prime_grids(self):
        # Brandywine p42: F"-1" -- the overall plan prints grids F" and 1".
        labels, parsed = _grids('F"-1"')
        self.assertEqual(labels, ['F"', '1"'])
        self.assertEqual([g["primes"] for g in parsed["grids"]], [2, 2])

    def test_leading_zero_is_preserved(self):
        labels, _ = _grids("C-02")
        self.assertEqual(labels, ["C", "02"])
        self.assertNotEqual(_grids("C-02")[0], _grids("C-2")[0])

    def test_alphanumeric_grid_names(self):
        # OSSE p26: "R14-RA.1"; Washington Latin p15: "B-X4"
        self.assertEqual(_grids("R14-RA.1")[0], ["R14", "RA.1"])
        self.assertEqual(_grids("B-X4")[0], ["B", "X4"])

    def test_negative_offset_is_not_a_separator(self):
        # Brandywine p42: "C-8(-4'-4")"
        labels, parsed = _grids("C-8(-4'-4\")")
        self.assertEqual(labels, ["C", "8"])
        offset = parsed["grids"][1]["offset"]
        self.assertEqual(offset["raw"], "-4'-4\"")
        self.assertEqual(offset["inches"], -52.0)
        self.assertIsNone(offset["direction"])
        self.assertIsNone(parsed["grids"][0]["offset"])

    def test_offset_on_first_grid(self):
        # Brandywine p42: "C.6(1'-10")-1"; OSSE p26: "R13(5' - 4")-RA.1"
        labels, parsed = _grids("C.6(1'-10\")-1")
        self.assertEqual(labels, ["C.6", "1"])
        self.assertEqual(parsed["grids"][0]["offset"]["inches"], 22.0)
        labels, parsed = _grids("R13(5' - 4\")-RA.1")
        self.assertEqual(labels, ["R13", "RA.1"])
        self.assertEqual(parsed["grids"][0]["offset"]["inches"], 64.0)
        self.assertEqual(parsed["grids"][0]["offset"]["unit"], "ft-in")

    def test_offset_on_second_grid(self):
        labels, parsed = _grids("C.6-2(3'-7\")")
        self.assertEqual(labels, ["C.6", "2"])
        self.assertEqual(parsed["grids"][1]["offset"]["inches"], 43.0)

    def test_unrecognized_text_is_unresolved_not_corrected(self):
        for text in ("SEE PLAN", "A--6", "A-6-7", "C-8(-4'-4\"", ""):
            parsed = parse_grid_location(text)
            self.assertEqual(parsed["status"], "unresolved", text)
            self.assertEqual(parsed["grids"], [], text)
            self.assertEqual(parsed["raw"], text)


class LocationListTests(unittest.TestCase):
    def test_cell_with_several_locations(self):
        # Brandywine p42 S-600, one schedule column
        cell = "A.4'-14, B-4.9, B-6, B-12, C-11, D-9, D-13, E-8(-4'-4\"), C'-15.6"
        self.assertEqual(
            split_locations(cell),
            ["A.4'-14", "B-4.9", "B-6", "B-12", "C-11", "D-9", "D-13", "E-8(-4'-4\")", "C'-15.6"],
        )

    def test_wrapped_offset_and_trailing_comma(self):
        self.assertEqual(
            split_locations("C.6(1'-10\")-1, C.6-2(3'-\n7\"), D.2-2,"),
            ["C.6(1'-10\")-1", "C.6-2(3'- 7\")", "D.2-2"],
        )
        self.assertEqual(parse_grid_location("C.6-2(3'- 7\")")["grids"][1]["offset"]["inches"], 43.0)

    def test_single_location(self):
        self.assertEqual(split_locations(" A-9 "), ["A-9"])
        self.assertEqual(split_locations(""), [])


class PlateCellTests(unittest.TestCase):
    def test_combined_dimensions(self):
        # Fort Davis p15 S301 "18\"x18\"x1\""; Burrville p29 "1 1/4\"x18\"x18\""
        plate = parse_plate_cell('18"x18"x1"')
        self.assertEqual(plate["status"], "dimensions")
        self.assertEqual([d["inches"] for d in plate["dimensions"]], [18.0, 18.0, 1.0])
        self.assertEqual(plate["raw"], '18"x18"x1"')
        plate = parse_plate_cell('1 1/4"x18"x18"')
        self.assertEqual([d["raw"] for d in plate["dimensions"]], ['1 1/4"', '18"', '18"'])
        self.assertEqual(plate["dimensions"][0]["inches"], 1.25)

    def test_feet_inch_and_hyphen_mixed_numbers(self):
        # Washington Latin p15 S-202 "1 1/4\"x14\"x1'-2\""; Furley p2 S002 "20\"x14\"x1-1/4\""
        plate = parse_plate_cell("1 1/4\"x14\"x1'-2\"")
        self.assertEqual([d["inches"] for d in plate["dimensions"]], [1.25, 14.0, 14.0])
        plate = parse_plate_cell('20"x14"x1-1/4"')
        self.assertEqual([d["inches"] for d in plate["dimensions"]], [20.0, 14.0, 1.25])

    def test_note_marker_is_kept_apart(self):
        # Burrville p29 S-502: '1"x18"x18" *'
        plate = parse_plate_cell('1"x18"x18" *')
        self.assertEqual(plate["status"], "dimensions")
        self.assertEqual(plate["markers"], ["*"])
        self.assertEqual(len(plate["dimensions"]), 3)

    def test_plate_prefix(self):
        plate = parse_plate_cell('PL 14"x14"x3/4"')
        self.assertEqual([d["inches"] for d in plate["dimensions"]], [14.0, 14.0, 0.75])

    def test_detail_reference(self):
        # Washington Latin p15: base plate cell "D/S-201"
        plate = parse_plate_cell("D/S-201")
        self.assertEqual(plate["status"], "reference")
        self.assertEqual(plate["reference"], {"raw": "D/S-201", "detail": "D", "sheet": "S-201"})
        self.assertEqual(plate["dimensions"], [])

    def test_blank_and_not_applicable_are_distinct(self):
        self.assertEqual(parse_plate_cell("")["status"], "blank")
        self.assertEqual(parse_plate_cell("  ")["status"], "blank")
        for text in ("-", "—", "N/A", "NONE"):
            self.assertEqual(parse_plate_cell(text)["status"], "not_applicable", text)

    def test_unreadable_text_is_not_forced_into_dimensions(self):
        plate = parse_plate_cell('SEE NOTE 4')
        self.assertEqual(plate["status"], "unreadable")
        self.assertEqual(plate["dimensions"], [])
        plate = parse_plate_cell('14"x14"')
        self.assertEqual(plate["status"], "dimensions")
        self.assertEqual(len(plate["dimensions"]), 2)   # incomplete, not padded


class DrawingReferenceTests(unittest.TestCase):
    def test_numeric_and_alphabetic_details(self):
        self.assertEqual(parse_drawing_reference("7/S400"), {"raw": "7/S400", "detail": "7", "sheet": "S400"})
        self.assertEqual(parse_drawing_reference("A/S400")["detail"], "A")
        # Furley p2 S002 bearing plate BP7 remark "SEE S/S502"
        self.assertEqual(parse_drawing_reference("SEE S/S502"), {"raw": "S/S502", "detail": "S", "sheet": "S502"})

    def test_fractions_are_not_references(self):
        self.assertIsNone(parse_drawing_reference('3/4"'))
        self.assertIsNone(parse_drawing_reference("1 1/4"))


# --------------------------------------------------------------------------
# Synthetic sheets through the real read_ruled_tables path
# --------------------------------------------------------------------------
def _grid_lines(page, x0, y0, widths, heights):
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [y0]
    for h in heights:
        ys.append(ys[-1] + h)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    return xs, ys


def _mark_matrix_page(document):
    """Fort Davis S301 shape: marks across the top, row labels on the right.

    C-2's plate cell first said 12"x12"x1/2"; a white box covers it and the
    visible 18"x18"x1" is typed on top (an edited PDF).
    """

    page = document.new_page(width=900, height=700)
    xs, ys = _grid_lines(page, 100, 100, [100, 100, 120], [30, 70, 70, 30, 30])
    for x, mark in ((xs[0], "C-2"), (xs[1], "C-1")):
        page.insert_text((x + 35, ys[0] + 20), mark, fontsize=9)
        page.insert_text((x + 55, ys[3] - 10), "HSS10X10X5/16", fontsize=8, rotate=90)
    page.insert_text((xs[0] + 8, ys[3] + 20), '12"x12"x1/2"', fontsize=9)
    page.draw_rect(fitz.Rect(xs[0] + 3, ys[3] + 3, xs[1] - 3, ys[4] - 3), color=None, fill=(1, 1, 1))
    page.insert_text((xs[0] + 8, ys[3] + 20), '18"x18"x1"', fontsize=9)
    page.insert_text((xs[1] + 8, ys[3] + 20), '18"x18"x3/4"', fontsize=9)
    page.insert_text((xs[1] + 4, ys[4] + 20), "MOMENT FRAME COLUMN", fontsize=7)
    for row, label in enumerate(("MARK", "ROOF", "2ND", "BASE PLATE", "REMARKS")):
        page.insert_text((xs[2] + 6, ys[row] + 20), label, fontsize=9)


def _location_matrix_page(document):
    """Brandywine S-600 shape: levels on the left, locations along the bottom,
    BP leader marks at the column bases; a base plate schedule and a
    location-keyed plate-type table elsewhere on the sheet."""

    page = document.new_page(width=1200, height=900)
    xs, ys = _grid_lines(page, 100, 100, [120, 120, 120, 120], [70, 70, 50])
    page.insert_text((xs[0] + 4, ys[0] + 20), "LEVEL 2", fontsize=9)
    page.insert_text((xs[0] + 4, ys[1] + 20), "LEVEL 1", fontsize=9)
    page.insert_text((xs[0] + 4, ys[2] + 18), "Column Locations", fontsize=9)
    columns = (
        (["A-1,", "B-2(-1'-6\")"], "W12X40", "BP2"),
        (["C.5-7"], "W10X33", None),
        (["D-3"], "W10X33", "BP9"),
    )
    for index, (lines, section, plate_mark) in enumerate(columns, start=1):
        x = xs[index]
        for line_number, text in enumerate(lines):
            page.insert_text((x + 20, ys[2] + 20 + 12 * line_number), text, fontsize=9)
        page.insert_text((x + 60, ys[2] - 10), section, fontsize=8, rotate=90)
        if plate_mark:
            page.insert_text((x + 70, ys[2] - 8), plate_mark, fontsize=7)

    # BASE PLATE SCHEDULE: dimensions in the order of its own headings.
    bx, by = _grid_lines(page, 100, 420, [80, 90, 90, 90, 140], [22, 22, 22])
    page.insert_text((100, 412), "BASE PLATE SCHEDULE", fontsize=10)
    for column, label in enumerate(("MARK", "THICKNESS", "WIDTH", "LENGTH", "REMARKS")):
        page.insert_text((bx[column] + 4, by[0] + 15), label, fontsize=8)
    for column, value in enumerate(("BP2", '3/4"', "1'-6\"", "1'-6\"", "")):
        page.insert_text((bx[column] + 4, by[1] + 15), value, fontsize=8)
    for column, value in enumerate(("BP4", '1"', "2'-0\"", "2'-0\"", "SEE 4/S501")):
        page.insert_text((bx[column] + 4, by[2] + 15), value, fontsize=8)

    # Location-keyed table whose first cell C-6 looks exactly like a mark.
    lx, ly = _grid_lines(page, 700, 420, [110, 110, 110], [22, 22])
    page.insert_text((700, 412), "BASE PLATE TYPE BY LOCATION SCHEDULE", fontsize=10)
    for column, label in enumerate(("LOCATION MARK", "COLUMN SECTION", "BASE PLATE TYPE")):
        page.insert_text((lx[column] + 4, ly[0] + 15), label, fontsize=8)
    for column, value in enumerate(("C-6", "W10X33", "BP2")):
        page.insert_text((lx[column] + 4, ly[1] + 15), value, fontsize=8)


class _SyntheticSheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pdf = Path(cls.tmp.name) / "columns.pdf"
        document = fitz.open()
        _mark_matrix_page(document)
        _location_matrix_page(document)
        document.save(str(cls.pdf))
        document.close()
        with fitz.open(str(cls.pdf)) as document:
            cls.words = [
                {"text": w[4], "bbox": list(w[:4]), "page_number": i + 1}
                for i, page in enumerate(document) for w in page.get_text("words")
            ]
        cls.records = read_ruled_tables(str(cls.pdf), cls.words)
        cls.document = {
            "column_schedules": build_column_schedules(cls.records),
            "schedule_grid": build_document_schedule_grids(
                cls.words, pdf_path=str(cls.pdf), ruled_records=cls.records
            ),
        }
        cls.view = column_schedule_view(cls.document, {1: "S301", 2: "S600", 3: "S501"})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def entry(self, label):
        for entry in self.view["entries"]:
            if entry["mark"] == label or (entry["locations"] and entry["locations"][0]["raw"] == label):
                return entry
        raise AssertionError(f"no entry {label}: {[e['mark'] or e['location_text'] for e in self.view['entries']]}")


class VisibleTextTests(_SyntheticSheet):
    def test_text_painted_over_by_a_later_white_box_is_suppressed(self):
        with fitz.open(str(self.pdf)) as document:
            visible, suppressed = visible_phrases(document[0])
        self.assertIn('18"x18"x1"', [p["text"] for p in visible])
        self.assertNotIn('12"x12"x1/2"', [p["text"] for p in visible])
        self.assertIn('12"x12"x1/2"', [p["text"] for p in suppressed])

    def test_the_masked_value_never_reaches_the_entry(self):
        c2 = self.entry("C-2")
        self.assertEqual(c2["plate"]["printed"], '18"x18"x1"')
        self.assertIn('12"x12"x1/2"', c2["hidden_text"])


class MarkMatrixTests(_SyntheticSheet):
    def test_each_mark_keeps_its_own_plate_even_with_the_same_section(self):
        c1, c2 = self.entry("C-1"), self.entry("C-2")
        self.assertEqual([s["designation"] for s in c1["sections"]], ["HSS10X10X5/16"])
        self.assertEqual([s["designation"] for s in c2["sections"]], ["HSS10X10X5/16"])
        self.assertEqual([d["raw"] for d in c1["plate"]["dimensions"]], ['18"', '18"', '3/4"'])
        self.assertEqual([d["raw"] for d in c2["plate"]["dimensions"]], ['18"', '18"', '1"'])
        self.assertEqual(c1["plate"]["status"], "read")
        self.assertEqual(c1["plate"]["type"], "base plate")
        self.assertEqual(c1["notes"], ["MOMENT FRAME COLUMN"])

    def test_a_mark_spelled_like_a_grid_is_never_a_location(self):
        c2 = self.entry("C-2")
        self.assertEqual(c2["key_role"], "mark")
        self.assertEqual(c2["locations"], [])
        self.assertIn("not a grid intersection", c2["location_note"])

    def test_matrix_schedules_never_feed_the_production_mark_map(self):
        self.assertEqual(schedule_mark_map(self.document["schedule_grid"]), {})
        rows = [r for g in self.document["schedule_grid"] for r in g["rows"] if r.get("mark_role") != "grid_location"]
        self.assertEqual(rows, [])


class LocationMatrixTests(_SyntheticSheet):
    def test_one_entry_lists_several_locations_with_offsets(self):
        entry = self.entry("A-1")
        self.assertEqual(entry["location_text"], "A-1, B-2(-1'-6\")")
        self.assertEqual(entry["listed_location_count"], 2)
        b2 = entry["locations"][1]
        self.assertEqual([g["label"] for g in b2["grids"]], ["B", "2"])
        self.assertEqual(b2["grids"][1]["offset"]["inches"], -18.0)
        self.assertTrue(entry["is_definition_not_quantity"])

    def test_leader_mark_resolves_through_the_base_plate_schedule(self):
        plate = self.entry("A-1")["plate"]
        self.assertEqual(plate["status"], "resolved")
        self.assertEqual(plate["type"], "base plate")
        self.assertEqual(
            [(d["label"], d["raw"]) for d in plate["dimensions"]],
            [("thickness", '3/4"'), ("width", "1'-6\""), ("length", "1'-6\"")],
        )
        self.assertEqual([v["kind"] for v in plate["via"]], ["leader mark", "plate schedule"])
        self.assertEqual(plate["via"][0]["page"], 2)

    def test_undefined_plate_mark_stays_unresolved(self):
        plate = self.entry("D-3")["plate"]
        self.assertEqual(plate["status"], "unresolved")
        self.assertEqual(plate["printed"], "BP9")
        self.assertEqual(plate["dimensions"], [])

    def test_column_without_a_plate_mark_is_not_given_one(self):
        # C.5-7 shares W10X33 with D-3; the section alone never picks a plate.
        plate = self.entry("C.5-7")["plate"]
        self.assertEqual(plate["status"], "not_shown")
        self.assertEqual(plate["dimensions"], [])

    def test_location_keyed_rows_never_become_marks(self):
        self.assertNotIn("C6", schedule_mark_map(self.document["schedule_grid"]))
        tables = self.document["column_schedules"]["location_tables"]
        self.assertEqual([r["location"] for t in tables for r in t["rows"]], ["C-6"])


class PlateTableTests(unittest.TestCase):
    def _record(self, title, header, groups, rows, page=43):
        return {
            "page": page, "bbox": [0, 0, 100, 100], "layout": "rows", "title": title,
            "header": header, "header_groups": groups,
            "body": [{"cells": cells, "bbox": [0, i, 100, i + 1]} for i, cells in enumerate(rows)],
        }

    def test_washer_thickness_is_not_the_plate_thickness(self):
        # Brandywine S-601: BASE PLATE SIZE (THICKNESS | WIDTH | LENGTH) and
        # PLATE WASHER (Ø | THICKNESS) both have a THICKNESS heading.
        record = self._record(
            "BASE PLATE SCHEDULE",
            ["TYPE", "TYPE", "BASE PLATE SIZE THICKNESS", "WIDTH", "LENGTH", "Ø", "THICKNESS"],
            ["TYPE", "TYPE", "BASE PLATE SIZE", "BASE PLATE SIZE", "BASE PLATE SIZE", "PLATE WASHER", "PLATE WASHER"],
            [["BP1", "A", '1 1/4"', "1'-6\"", "1'-6\"", '2 3/4"', '1/4"']],
        )
        row = _plate_table(record)["rows"][0]
        self.assertEqual(row["mark"], "BP1")
        self.assertEqual([(d["label"], d["raw"]) for d in row["dimensions"]],
                         [("thickness", '1 1/4"'), ("width", "1'-6\""), ("length", "1'-6\"")])

    def test_conflicting_definitions_do_not_resolve(self):
        a = self._record("BASE PLATE SCHEDULE", ["MARK", "SIZE"], ["MARK", "SIZE"], [["BP1", '14"x14"x3/4"']])
        b = self._record("BASE PLATE SCHEDULE", ["MARK", "SIZE"], ["MARK", "SIZE"], [["BP1", '16"x16"x1"']], page=44)
        found = lookup_plate_mark("BP-1", plate_index([_plate_table(a), _plate_table(b)]), {})
        self.assertEqual(found["status"], "conflict")
        self.assertEqual([s["page"] for s in found["sources"]], [43, 44])
        same = lookup_plate_mark("BP1", plate_index([_plate_table(a), _plate_table(a)]), {})
        self.assertEqual(same["status"], "resolved")

    def test_bearing_plate_schedule_is_not_a_base_plate(self):
        # Furley S002: BP1-BP7 are bearing plates; column base plates are in the column schedule.
        record = self._record("BEARING PLATE SCHEDULE", ["MARK", "SIZE", "REMARKS"], ["MARK", "SIZE", "REMARKS"],
                              [["BP7", '7"x9"x3/4"', "SEE S/S502"]])
        table = _plate_table(record)
        self.assertEqual(table["kind"], "bearing plate")
        self.assertEqual(table["rows"][0]["reference"], {"raw": "S/S502", "detail": "S", "sheet": "S502"})
        # One SIZE cell: printed order, no heading names a dimension.
        self.assertEqual([(d["label"], d["raw"]) for d in table["rows"][0]["dimensions"]],
                         [(None, '7"'), (None, '9"'), (None, '3/4"')])


if __name__ == "__main__":
    unittest.main()
