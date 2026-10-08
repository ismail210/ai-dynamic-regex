"""Ruled schedule tables: find_tables reader, kinds from titles, Revit grids, cross-check."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz

from services.engineering.schedule_grid import (
    _interpret_plate,
    _ruled_grids,
    _split_transposed_level_label,
    attach_level_bands,
    build_schedule_grids,
    build_document_schedule_grids,
    is_bare_schedule_mark,
    lookup_schedule_row,
    parse_column_location,
    plate_count_per_member,
    resolve_auxiliary_schedule_mark,
    schedule_kind_from_title,
    schedule_mark_crosscheck,
    schedule_mark_map,
)
from services.engineering.schedule_grid import column_level_endpoints, link_level_names_to_plans
from services.engineering.schedule_tables import (
    _collapse_overlapping_copies,
    _header_paths,
    _trailing_column,
    _transposed_record,
    read_ruled_tables,
)


_SECTIONS = {"W8X24", "W8X31", "W10X33", "W12X65", "HSS6X6X1/2", "W16X36"}


def _accept(token: str) -> bool:
    return token.upper() in _SECTIONS


def _placed(items, page=2):
    return [
        {"text": text, "bbox": [x, y, x + 40, y + 8], "page_number": page}
        for text, x, y in items
    ]


def _rows_record(title, header, body, page=2, groups=None):
    record = {
        "page": page,
        "bbox": [0, 0, 500, 300],
        "layout": "rows",
        "title": title,
        "header": header,
        "body": [
            {"cells": cells, "bbox": [0, 40 + 20 * i, 500, 60 + 20 * i]}
            for i, cells in enumerate(body)
        ],
    }
    if groups is not None:
        record["header_groups"] = groups
    return record


def _ruled_pdf(path: Path, title: str, header: list, body: list) -> None:
    """One ruled table: title row, header row, body rows, all cells boxed."""

    document = fitz.open()
    page = document.new_page(width=800, height=600)
    rows = [[title] + [""] * (len(header) - 1), header, *body]
    x0, y0, col_w, row_h = 100.0, 100.0, 120.0, 22.0
    width = col_w * len(header)
    for index in range(len(rows) + 1):
        y = y0 + index * row_h
        page.draw_line((x0, y), (x0 + width, y))
    for column in range(len(header) + 1):
        x = x0 + column * col_w
        top = y0 + (row_h if 0 < column < len(header) else 0)
        page.draw_line((x, top), (x, y0 + len(rows) * row_h))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            if text:
                page.insert_text((x0 + c * col_w + 4, y0 + r * row_h + 15), text, fontsize=9)
    document.save(str(path))
    document.close()


def _pdf_words(path: Path) -> list:
    with fitz.open(str(path)) as document:
        return [
            {"text": w[4], "bbox": list(w[:4]), "page_number": i + 1}
            for i, page in enumerate(document)
            for w in page.get_text("words")
        ]


class ScheduleKindTests(unittest.TestCase):
    def test_title_decides_kind(self) -> None:
        cases = {
            "EXISTING COLUMN SCHEDULE": "column",
            "LINTEL SCHEDULE": "lintel",
            "CONCRETE PIER SCHEDULE": "pier",
            "FOOTING SCHEDULE": "footing",
            "GRADE BEAM SCHEDULE": "grade_beam",
            "BEARING PLATE SCHEDULE": "bearing_plate",
            "ICF LINTEL SCHEDULE": "icf_lintel",
            "STEEL BEAM SCHEDULE": "beam",
            "": "schedule",
        }
        for title, kind in cases.items():
            with self.subTest(title=title):
                self.assertEqual(schedule_kind_from_title(title), kind)


class RuledRowsGridTests(unittest.TestCase):
    def test_header_synonyms_pick_mark_and_size_columns(self) -> None:
        record = _rows_record(
            "COLUMN SCHEDULE",
            ["TYPE", "COLUMN SIZE", "BASE PLATE", "REMARKS"],
            [["C1", "HSS6X6X1/2", "PL3/4x12x12", "TYP"], ["C-2", "W8X31", "", ""]],
        )
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual(grid["kind"], "column")
        rows = {row["mark"]: row for row in grid["rows"]}
        self.assertEqual(rows["C1"]["section"], "HSS6X6X1/2")
        self.assertEqual(rows["C1"]["plate_text"], "PL3/4x12x12")
        self.assertEqual(rows["C1"]["plate_role"], "base_plate")
        self.assertEqual(schedule_mark_map([grid]), {"C1": "HSS6X6X1/2", "C2": "W8X31"})

    def test_non_steel_table_never_yields_a_section(self) -> None:
        record = _rows_record(
            "PIER SCHEDULE",
            ["MARK", "SECTION", "REINFORCING"],
            [["P22", "W8X24", "(8) #6"], ["C4", "W8X24", ""]],
        )
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual(grid["kind"], "pier")
        self.assertTrue(all(row["section"] is None for row in grid["rows"]))
        self.assertEqual(schedule_mark_map([grid]), {})
        row = lookup_schedule_row("C4", {"schedule_grid": [grid]})
        self.assertFalse(row["catalog_valid"])

    def test_untitled_table_uses_mark_header_label(self) -> None:
        record = _rows_record("", ["PIER TYPE", "SIZE"], [["P18", "18\" DIA"]])
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual(grid["kind"], "pier")

    def test_unlabeled_first_column_is_mark_only_when_cells_look_like_marks(self) -> None:
        marks = _rows_record("COLUMN SCHEDULE", ["", "SIZE"], [["C1", "W8X24"], ["C2", "W8X31"]])
        levels = _rows_record("COLUMN SCHEDULE", ["", "SIZE"], [["ROOF", "W8X24"], ["LEVEL 2", "W8X31"]])
        self.assertEqual(len(_ruled_grids([marks], _accept)), 1)
        self.assertEqual(_ruled_grids([levels], _accept), [])

    def test_section_shaped_mark_cells_are_rejected(self) -> None:
        record = _rows_record("COLUMN SCHEDULE", ["MARK", "SIZE"], [["W8X24", "W8X24"], ["C3", "W8X24"]])
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual([row["mark"] for row in grid["rows"]], ["C3"])

    def test_plate_and_icf_marks_stay_plate_sidecars(self) -> None:
        bearing = _rows_record("BEARING PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", "PL1/2x8x12"]])
        icf = _rows_record(
            "ICF LINTEL SCHEDULE", ["MARK", "SIZE", "REINFORCING"], [["CL2", "LOOSE ANGLE 5x5x3/8", "(2) #5"]]
        )
        grids = _ruled_grids([bearing, icf], _accept)
        rows = {row["mark"]: row for grid in grids for row in grid["rows"]}
        self.assertIsNone(rows["BP1"]["section"])
        self.assertEqual(rows["BP1"]["plate_text"], "PL1/2x8x12")
        self.assertIsNone(rows["CL2"]["section"])
        self.assertIn("LOOSE ANGLE", rows["CL2"]["plate_text"])


class TransposedGridTests(unittest.TestCase):
    def test_revit_levels_by_locations(self) -> None:
        record = {
            "page": 28,
            "bbox": [0, 0, 600, 400],
            "layout": "transposed",
            "title": "COLUMN SCHEDULE",
            "locations": [
                {"location": "A-8", "x": 100.0},
                {"location": "A-9", "x": 160.0},
                {"location": "B-7", "x": 220.0},
            ],
            "cells": [
                {"text": "W10X33", "x": 130.0, "row_label": "ROOF"},
                {"text": "W12X65", "x": 221.0, "row_label": "ROOF"},
                {"text": "W12X65", "x": 219.0, "row_label": "LEVEL 2"},
                {"text": "PL1x14x14", "x": 100.0, "row_label": "BASE PLATE SIZE"},
                {"text": "LEVEL 1", "x": 400.0, "row_label": "ROOF"},
            ],
        }
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual(grid["layout"], "transposed")
        pairs = {(row["mark"], row["section"]) for row in grid["rows"]}
        self.assertIn(("A-8", "W10X33"), pairs)
        self.assertIn(("B-7", "W12X65"), pairs)
        self.assertEqual(len([p for p in pairs if p[0] == "B-7"]), 1)
        self.assertEqual(len(pairs), 2)
        # Grid locations are instances, not type marks.
        self.assertEqual(schedule_mark_map([grid]), {})
        self.assertIsNone(lookup_schedule_row("C1", {"schedule_grid": [grid]}))


class _Table:
    """find_tables stand-in: equal-width columns, so cell j is centred at 60*j + 30."""

    def __init__(self, rows):
        self.rows = [
            SimpleNamespace(cells=[(60.0 * c, 0.0, 60.0 * (c + 1), 10.0) for c in range(len(row))])
            for row in rows
        ]


_LEVEL = ['29\' - 0" UPPER LEVEL', "W10X33", "W10X33", "W10X33", "W10X33"]
_LOCATIONS = ["Column Locations", "A-1", "A-2", "A-3", "A-4"]


def _plates(rows):
    record = _transposed_record(_Table(rows), rows, rows.index(_LOCATIONS), 29, [0, 0, 300, 100])
    (grid,) = _ruled_grids([record], _accept)
    return {row["mark"]: row["plate_text"] for row in grid["rows"]}


class OverlappingPlateCellTests(unittest.TestCase):
    def test_two_copies_of_a_plate_word_are_read_once(self) -> None:
        # Springhill S-501 p27, M-20 / N-20 / N.2-12: the text layer draws
        # ``1"x18"x18"`` twice, about five points apart, plus note stars.
        # extract() interleaves the copies.
        cell = (504.8, 582.0, 577.1, 618.1)
        words = [
            (517.9, 596.0, 564.1, 605.6, '1"x18"x18"'),
            (512.9, 596.0, 559.0, 605.6, '1"x18"x18"'),
            (561.6, 596.0, 569.1, 605.6, "**"),
        ]
        table = SimpleNamespace(rows=[SimpleNamespace(cells=[cell])])
        extracted = '11"x"1x188"x"1x188" "**'
        (repaired,) = _collapse_overlapping_copies(table, [[extracted]], words)
        self.assertEqual(repaired, ['1"x18"x18" **'])
        parsed, status = _interpret_plate(repaired[0])
        self.assertEqual(status, "present")
        self.assertEqual(parsed["ordered_dimensions"], ['1"', '18"', '18"'])
        self.assertEqual(parsed["notes"], "**")
        self.assertEqual(_interpret_plate(extracted)[1], "unresolved")

    def test_one_word_does_not_replace_a_malformed_extract(self) -> None:
        cell = (0.0, 0.0, 80.0, 20.0)
        words = [(10.0, 4.0, 50.0, 14.0, '1"x18"x18"')]
        table = SimpleNamespace(rows=[SimpleNamespace(cells=[cell])])
        extracted = '11"x"1x188"x"1x188" "**'
        self.assertEqual(
            _collapse_overlapping_copies(table, [[extracted]], words),
            [[extracted]],
        )
        self.assertEqual(_interpret_plate(extracted)[1], "unresolved")

    def test_separate_copies_of_the_same_word_both_stay(self) -> None:
        cell = (0.0, 0.0, 80.0, 12.0)
        words = [(2.0, 1.0, 22.0, 9.0, "N/A"), (40.0, 1.0, 60.0, 9.0, "N/A")]
        table = SimpleNamespace(rows=[SimpleNamespace(cells=[cell])])
        self.assertEqual(
            _collapse_overlapping_copies(table, [["N/A N/A"]], words),
            [["N/A N/A"]],
        )


class TransposedBasePlateTests(unittest.TestCase):
    def test_unlabelled_plate_rows_with_wrapped_value_and_blank_location(self) -> None:
        plates = _plates([
            _LEVEL,
            _LOCATIONS,
            ["", "74", "114", "", "60"],
            ["", '1"x18"x18"', '3/4"x18"x18"', "", ""],
            ["", "", "", "", '1 1/4"x18"x18" *'],
        ])
        self.assertEqual(
            plates,
            {"A-1": '1"x18"x18"', "A-2": '3/4"x18"x18"', "A-3": "", "A-4": '1 1/4"x18"x18" *'},
        )

    def test_label_drawn_over_a_value_cell_is_stripped(self) -> None:
        plates = _plates([
            _LEVEL,
            _LOCATIONS,
            ["", "74", "Unfactored 103 Reaction (kips)", "88", "60"],
            ["", '1"x18"x18"', 'Base Plate 1"x18"x18" Size', '3/4"x18"x18"', '1 1/2"x18"x18" *'],
        ])
        self.assertEqual(plates["A-2"], '1"x18"x18"')
        self.assertEqual(plates["A-4"], '1 1/2"x18"x18" *')

    def test_labelled_plate_row_keeps_existing_behavior(self) -> None:
        plates = _plates([
            _LEVEL,
            _LOCATIONS,
            ["Unfactored Reaction (kips)", "74", "114", "88", "60"],
            ["Base Plate Size", '1"x18"x18"', '3/4"x18"x18"', "", ""],
            ["", "", "", '1"x18"x18"', ""],
        ])
        self.assertEqual(
            plates, {"A-1": '1"x18"x18"', "A-2": '3/4"x18"x18"', "A-3": "", "A-4": ""}
        )

    def test_conflicting_inferred_rows_abstain_for_that_location(self) -> None:
        plates = _plates([
            _LEVEL,
            _LOCATIONS,
            ["", '1"x18"x18"', '3/4"x18"x18"', "", ""],
            ["", '3/4"x18"x18"', "", "", ""],
        ])
        self.assertEqual(plates["A-1"], "")
        self.assertEqual(plates["A-2"], '3/4"x18"x18"')

    def test_dimension_like_rows_that_are_not_plate_sizes_stay_unlabelled(self) -> None:
        plates = _plates([
            _LEVEL,
            _LOCATIONS,
            ["", '3/4" DIA x 12"', '3/4"x18"x18"', "", ""],
            ["", '29\' - 0"', "HSS10X10X1/2", "", ""],
            ["CAP PLATE", "", "", '3/4"x10"x10"', ""],
            ["", "", "", "", '1"x14"x14"'],
        ])
        self.assertEqual(set(plates.values()), {""})


class ReadRuledTablesTests(unittest.TestCase):
    def test_find_tables_reads_title_header_and_cells(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "schedule.pdf"
            _ruled_pdf(
                pdf,
                "COLUMN SCHEDULE",
                ["MARK", "SIZE", "BASE PLATE"],
                [["C1", "HSS6X6X1/2", "PL3/4x12"], ["C2", "W8X31", "-"]],
            )
            records = read_ruled_tables(str(pdf), _pdf_words(pdf))
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["title"], "COLUMN SCHEDULE")
        self.assertEqual(record["header"][:2], ["MARK", "SIZE"])
        self.assertEqual([row["cells"][0] for row in record["body"]], ["C1", "C2"])

    def test_ruled_rows_win_and_word_rows_fill_gaps(self) -> None:
        ruled = [_rows_record("PIER SCHEDULE", ["MARK", "SIZE"], [["P22", "24\" SQ"]])]
        words = [
            {"text": t, "bbox": [x, y, x + 30, y + 8], "page_number": 2}
            for t, x, y in (
                ("COLUMN", 100, 20), ("SCHEDULE", 160, 20),
                ("MARK", 100, 50), ("SIZE", 200, 50),
                ("C1", 100, 70), ("W8X24", 200, 70),
                ("P22", 100, 90), ("W8X31", 200, 90),
            )
        ]
        with patch(
            "services.engineering.schedule_grid.read_ruled_tables", return_value=ruled
        ):
            grids = build_document_schedule_grids(words, pdf_path="x.pdf", catalog_fn=_accept)
        mapping = schedule_mark_map(grids)
        self.assertEqual(mapping.get("C1"), "W8X24")
        self.assertNotIn("P22", mapping)


class AuxiliaryCompatibilityTests(unittest.TestCase):
    def test_ruled_cells_do_not_replace_existing_angle_or_na_resolution(self):
        words = [
            {"text": text, "bbox": [x, y, x + 30, y + 8], "page_number": 2}
            for text, x, y in (
                ("ICF LINTEL SCHEDULE", 100, 20),
                ("MARK", 100, 50), ("SIZE", 200, 50),
                ("CL1", 100, 70), ('LOOSE ANGLE 5"x5"x3/8"', 200, 70),
                ("STEEL DECK", 0, 90), ("CL5", 100, 90),
                ("STANDARD WALL WITH 2-#6 AT HEAD N/A N/A", 200, 90),
            )
        ]
        records = [_rows_record(
            "ICF LINTEL SCHEDULE", ["MARK", "CONCRETE CORE", "BRICK LINTEL TYPE", "ANGLE SIZE"],
            [["CL1", "STANDARD WALL", "LOOSE ANGLE", '5"x5"x3/8"'],
             ["CL5", "STANDARD WALL", "N/A", "N/A"]],
        )]
        with patch("services.engineering.schedule_grid.read_ruled_tables", return_value=records):
            grids = build_document_schedule_grids(words, pdf_path="x.pdf")
        document = {"schedule_grid": grids}
        self.assertEqual(resolve_auxiliary_schedule_mark("CL1", document)["section"], "L5X5X3/8")
        self.assertTrue(resolve_auxiliary_schedule_mark("CL5", document)["abstain"])
        self.assertEqual(grids, build_schedule_grids(words))

    def test_inspection_text_on_the_same_line_stays_out_of_the_schedule(self) -> None:
        # Furley S002: the bearing-plate and ICF rows share a baseline with
        # the inspection table to their left. The plate cell is only the
        # words under MARK | SIZE | REMARKS.
        words = _placed([
            ("BEARING", 200, 0), ("PLATE", 280, 0), ("SCHEDULE", 360, 0),
            ("MARK", 200, 30), ("SIZE", 280, 30), ("REMARKS", 360, 30),
            ("c.", 10, 50), ("PLACEMENT", 40, 50), ("OF", 90, 50), ("REINFORCEMENT", 130, 50),
            ("BP4", 200, 50), ('6"x8"x3/4"', 280, 50),
            ("SI", 10, 70), ("INSPECTOR", 40, 70),
            ("BP5", 200, 70), ('6"x10"x1"', 280, 70),
            ("TYPE", 10, 90), ("OF", 40, 90), ("INSPECTION", 80, 90),
            ("BP6", 200, 90), ('4"x10"x1', 280, 90), ('1/4"', 330, 90),
            ("BP7", 200, 110), ('7"x9"x3/4"', 280, 110), ("SEE", 370, 110), ("S/S502", 420, 110),
            ("ICF", 200, 150), ("LINTEL", 260, 150), ("SCHEDULE", 340, 150),
            ("MARK", 200, 180), ("SIZE", 400, 180),
            ("STEEL", 10, 200), ("DECK", 50, 200),
            ("CL5", 200, 200), ("STANDARD", 250, 200), ("WALL", 300, 200),
            ("N/A", 360, 200), ("N/A", 410, 200),
            ("CL1", 200, 220), ("LOOSE", 250, 220), ("ANGLE", 300, 220),
            ('5"x5"x3/8"', 360, 220),
        ])
        grids = build_schedule_grids(words)
        plates = {
            row["mark"]: row for grid in grids for row in grid["rows"]
            if str(row["mark"]).startswith(("BP", "CL"))
        }
        self.assertEqual(plates["BP4"]["plate_text"], '6"x8"x3/4"')
        self.assertNotIn("PLACEMENT", plates["BP4"]["plate_text"])
        self.assertEqual(plates["BP5"]["plate_text"], '6"x10"x1"')
        self.assertNotIn("INSPECTOR", plates["BP5"]["plate_text"])
        self.assertEqual(plates["BP6"]["plate_text"], '4"x10"x1 1/4"')
        self.assertNotIn("INSPECTION", plates["BP6"]["plate_text"])
        self.assertEqual(plates["BP7"]["plate_text"], '7"x9"x3/4"')
        self.assertIn("S/S502", plates["BP7"]["plate_notes"])
        self.assertEqual(plates["CL5"]["size_text"], "STANDARD WALL N/A N/A")
        self.assertNotIn("STEEL", plates["CL5"]["size_text"])
        self.assertEqual(plates["CL5"]["plate_status"], "unresolved")
        self.assertTrue(resolve_auxiliary_schedule_mark("CL5", {"schedule_grid": grids})["abstain"])
        self.assertEqual(
            resolve_auxiliary_schedule_mark("CL1", {"schedule_grid": grids})["section"],
            "L5X5X3/8",
        )
        self.assertFalse(any(mark.startswith(("BP", "CL")) for mark in schedule_mark_map(grids)))

    def test_masonry_pier_width_is_not_a_plate(self) -> None:
        # Furley S002 masonry pier schedule: WIDTH is the pier, the next
        # column is the vertical bars. Neither is a steel plate or a section.
        record = _rows_record(
            "MASONRY PIER SCHEDULE",
            ["MARK", "WIDTH", "VERTICAL REINFORCEMENT", "REMARKS"],
            [
                ["MP16", '16"', "1-#5", ""],
                ["MP24", '24"', "2-#5", ""],
                ["MP24A", '24"', "2-#5 EACH FACE", ""],
                ["MP32", '32"', "3-#5", ""],
                ["MP32A", '32"', "3-#5 EACH FACE", ""],
            ],
        )
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual(grid["kind"], "pier")
        rows = {row["mark"]: row for row in grid["rows"]}
        expected = {
            "MP16": ('16"', "1-#5"),
            "MP24": ('24"', "2-#5"),
            "MP24A": ('24"', "2-#5 EACH FACE"),
            "MP32": ('32"', "3-#5"),
            "MP32A": ('32"', "3-#5 EACH FACE"),
        }
        self.assertEqual(set(rows), set(expected))
        for mark, (width, bars) in expected.items():
            row = rows[mark]
            self.assertEqual(row["plate_text"], width, mark)
            self.assertEqual(row["size_text"], bars, mark)
            self.assertEqual(row["plate_status"], "unresolved", mark)
            self.assertEqual(plate_count_per_member(row), 0, mark)
            self.assertIsNone(row["plate_role"], mark)
            self.assertIsNone(row["section"], mark)
            dims = row["parsed_plate"]["dimensions"]
            self.assertEqual(dims["width"], width, mark)
            self.assertIsNone(dims["length"], mark)
            self.assertIsNone(dims["thickness"], mark)
            self.assertTrue(row["parsed_plate"]["uncertain"], mark)
        self.assertEqual(schedule_mark_map([grid]), {})

    def test_wrapped_stirrup_line_stays_on_its_own_mark(self) -> None:
        # Furley ICF rows: the stirrup line is the next baseline inside the
        # same cell. The following mark must not inherit it.
        words = _placed([
            ("ICF", 200, 0), ("LINTEL", 280, 0), ("SCHEDULE", 360, 0),
            ("MARK", 200, 20), ("SIZE", 700, 20),
            ("C1", 40, 56), ("W10X49", 80, 56),
            ("CL6A", 200, 50), ("STANDARD", 260, 50), ("WALL", 320, 50),
            ("2-#7", 380, 50), ("HEAD,", 440, 50),
            ('LOOSE ANGLE 5"x5"x3/8"', 520, 50),
            ("#4", 260, 63), ("STIRRUPS", 310, 63), ('12"o.c.', 400, 63),
            ("WELDED", 520, 63), ("PLATE", 580, 63),
            ("CL7", 200, 90), ("STANDARD", 260, 90), ("N/A", 400, 90), ("N/A", 460, 90),
            ("CL8", 200, 120), ("STANDARD", 260, 120), ("2-#8", 340, 120),
            ("#4", 260, 133), ("STIRRUPS", 310, 133), ('12"o.c.', 400, 133),
            ("CL9", 200, 160), ("N/A", 400, 160),
            ("#4", 260, 173), ("STIRRUPS", 310, 173), ('12"o.c.', 400, 173),
            ("LINTEL", 200, 186), ("SCHEDULE", 280, 186),
            ("CL5", 200, 200), ("N/A", 400, 200), ("N/A", 460, 200),
        ])
        grids = build_schedule_grids(words)
        rows = {
            row["mark"]: row for grid in grids for row in grid["rows"]
            if str(row["mark"]).startswith("CL")
        }
        cl6a = rows["CL6A"]["size_text"]
        self.assertLess(cl6a.index("STANDARD"), cl6a.index("#4 STIRRUPS"))
        self.assertIn('12"o.c.', cl6a)
        self.assertIn("WELDED", cl6a)
        self.assertNotIn("CL7", cl6a)
        self.assertNotIn("STIRRUPS", rows["CL7"]["size_text"])
        self.assertLess(rows["CL8"]["size_text"].index("STANDARD"), rows["CL8"]["size_text"].index("STIRRUPS"))
        self.assertNotIn("CL9", rows["CL8"]["size_text"])
        self.assertIn("#4 STIRRUPS", rows["CL9"]["size_text"])
        self.assertIn('12"o.c.', rows["CL9"]["size_text"])
        self.assertNotIn("SCHEDULE", rows["CL9"]["size_text"])
        self.assertNotIn("STIRRUPS", rows["CL5"]["size_text"])
        self.assertEqual(
            resolve_auxiliary_schedule_mark("CL6A", {"schedule_grid": grids})["section"],
            "L5X5X3/8",
        )
        self.assertTrue(resolve_auxiliary_schedule_mark("CL7", {"schedule_grid": grids})["abstain"])
        self.assertEqual(schedule_mark_map(grids), {})

    def test_ruled_only_auxiliary_marks_remain_production_resolutions(self):
        records = [_rows_record("BEARING PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '4"x6"x3/4"']])]
        with patch("services.engineering.schedule_grid.read_ruled_tables", return_value=records):
            grids = build_document_schedule_grids([], pdf_path="x.pdf", catalog_fn=_accept)
        aux = resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": grids})
        self.assertEqual(aux["kind"], "bearing_plate")
        self.assertEqual(aux["plate_text"], '4"x6"x3/4"')
        self.assertEqual(grids[0]["kind"], "bearing_plate")
        self.assertEqual(grids[0]["source"], "ruled_table")
        self.assertNotIn("BP1", schedule_mark_map(grids))

    def test_word_cluster_bearing_mark_replaces_the_ruled_copy(self) -> None:
        records = [_rows_record(
            "BEARING PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '9"x9"x9"']],
        )]
        words = _placed([
            ("BEARING", 100, 0), ("PLATE", 180, 0), ("SCHEDULE", 240, 0),
            ("MARK", 100, 30), ("SIZE", 220, 30),
            ("BP1", 100, 50), ('4"x6"x3/4"', 220, 50),
        ])
        with patch("services.engineering.schedule_grid.read_ruled_tables", return_value=records):
            grids = build_document_schedule_grids(words, pdf_path="x.pdf", catalog_fn=_accept)
        definitions = [row for grid in grids for row in grid["rows"] if row["mark"] == "BP1"]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0]["plate_text"], '4"x6"x3/4"')
        self.assertEqual(definitions[0]["plate_status"], "present")
        aux = resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": grids})
        self.assertEqual(aux["kind"], "bearing_plate")
        self.assertNotIn("ambiguous", aux)
        self.assertNotIn("BP1", schedule_mark_map(grids))


class CrosscheckTests(unittest.TestCase):
    def test_missing_unused_and_unscheduled_families(self) -> None:
        grid = {
            "page": 2,
            "kind": "column",
            "bbox": [0, 0, 100, 100],
            "rows": [
                {"mark": "C1", "section": "W8X24", "catalog_valid": True},
                {"mark": "C2", "section": "W8X31", "catalog_valid": True},
            ],
        }

        def word(text, page=5, x=500):
            return {"text": text, "bbox": [x, 500, x + 20, 510], "page_number": page}

        document = {
            "schedule_grid": [grid],
            "words": [
                {"text": "C2", "bbox": [10, 10, 20, 20], "page_number": 2},
                word("C1"), word("C-4"), word("BF-1"), word("BF-2"), word("BF3"),
                word("S-301"), word("ASTM"), word("C90"),
            ],
        }
        report = schedule_mark_crosscheck(document)
        self.assertEqual(report["missing_from_schedule"], ["C4"])
        self.assertEqual(report["unused_schedule_marks"], ["C2"])
        self.assertEqual(report["unscheduled_mark_families"], {"BF": ["BF1", "BF2", "BF3"]})


def _occurrence(parsed, index=0):
    return parsed["occurrences"][index]


class ColumnLocationParseTests(unittest.TestCase):
    def test_a6_is_two_grids_not_a_mark_or_a_dimension(self) -> None:
        parsed = parse_column_location("A-6")
        self.assertEqual(parsed["raw"], "A-6")
        self.assertEqual(parsed["kind"], "grid")
        self.assertFalse(parsed["uncertain"])
        self.assertEqual(_occurrence(parsed)["grids"], ["A", "6"])
        self.assertIsNone(_occurrence(parsed)["offset"])
        self.assertFalse(is_bare_schedule_mark("A-6"))
        self.assertNotEqual(parsed["kind"], "dimension")

    def test_dotted_grid_names_stay_literal(self) -> None:
        for name in ("B.4", "8.1", "G1.2"):
            with self.subTest(name=name):
                parsed = parse_column_location(name)
                self.assertEqual(parsed["raw"], name)
                self.assertEqual(_occurrence(parsed)["grids"], [name])
                self.assertFalse(parsed["uncertain"])

    def test_letter_prime_is_a_grid_name_not_feet(self) -> None:
        parsed = parse_column_location("B'")
        self.assertEqual(parsed["kind"], "grid")
        self.assertEqual(_occurrence(parsed)["grids"], ["B'"])
        self.assertFalse(parsed["uncertain"])

    def test_feet_inch_string_is_not_a_grid(self) -> None:
        parsed = parse_column_location('41\'-9 5/8"')
        self.assertEqual(parsed["raw"], '41\'-9 5/8"')
        self.assertEqual(parsed["kind"], "dimension")
        self.assertEqual(parsed["occurrences"], [])
        self.assertFalse(parsed["uncertain"])
        self.assertNotIn("41", [grid for item in parsed["occurrences"] for grid in item["grids"]])

    def test_comma_list_keeps_three_locations_on_one_value(self) -> None:
        parsed = parse_column_location("A-6, B-6, C-8")
        self.assertEqual(parsed["raw"], "A-6, B-6, C-8")
        self.assertEqual(
            [item["grids"] for item in parsed["occurrences"]],
            [["A", "6"], ["B", "6"], ["C", "8"]],
        )
        self.assertFalse(parsed["uncertain"])

    def test_repeated_location_inside_one_value_is_one_occurrence(self) -> None:
        for text in ("A-6, A-6", "A-6 A-6"):
            with self.subTest(text=text):
                parsed = parse_column_location(text)
                self.assertEqual(parsed["raw"], text)
                self.assertEqual(len(parsed["occurrences"]), 1)
                self.assertEqual(_occurrence(parsed)["grids"], ["A", "6"])

    def test_signed_offset_stays_with_the_grids(self) -> None:
        parsed = parse_column_location('A-6 + 2\'-0"')
        item = _occurrence(parsed)
        self.assertEqual(parsed["raw"], 'A-6 + 2\'-0"')
        self.assertEqual(item["grids"], ["A", "6"])
        self.assertEqual(item["offset"], '+ 2\'-0"')
        self.assertFalse(parsed["uncertain"])

        negative = parse_column_location('A-6 - 2\'-0"')
        self.assertEqual(_occurrence(negative)["grids"], ["A", "6"])
        self.assertEqual(_occurrence(negative)["offset"], '- 2\'-0"')

    def test_parenthesized_offset_stays_with_its_own_grid(self) -> None:
        for text, grids, offsets in (
            ('E-8(-4\'-4")', ["E", "8"], [("8", '-4\'-4"')]),
            ('C.6(1\'-10")-1', ["C.6", "1"], [("C.6", '1\'-10"')]),
            ('D-13(18\'-2")', ["D", "13"], [("13", '18\'-2"')]),
        ):
            with self.subTest(text=text):
                parsed = parse_column_location(text)
                item = _occurrence(parsed)
                self.assertEqual(parsed["kind"], "grid")
                self.assertFalse(parsed["uncertain"])
                self.assertEqual(item["grids"], grids)
                self.assertIsNone(item["offset"])
                self.assertEqual(
                    [(entry["grid"], entry["offset"]) for entry in item["grid_offsets"]],
                    offsets,
                )
                self.assertTrue(all(entry["direction"] is None for entry in item["grid_offsets"]))

    def test_two_parenthesized_offsets_and_commas_inside_a_list(self) -> None:
        parsed = parse_column_location('K.9\'(-2\'-8")-16\'(-20\'-8"), G.4-11(-1\'-0"), K')
        self.assertEqual(len(parsed["occurrences"]), 3)
        first = _occurrence(parsed)
        self.assertEqual(first["grids"], ["K.9'", "16'"])
        self.assertEqual(
            [(entry["grid"], entry["offset"]) for entry in first["grid_offsets"]],
            [("K.9'", '-2\'-8"'), ("16'", '-20\'-8"')],
        )
        self.assertTrue(first["uncertain"])
        self.assertEqual(_occurrence(parsed, 2)["grids"], ["K"])

    def test_offset_direction_is_kept_only_when_printed(self) -> None:
        printed = _occurrence(parse_column_location('A-6(2\'-0" LEFT)'))
        self.assertEqual(printed["grid_offsets"][0]["direction"], "LEFT")
        plain = _occurrence(parse_column_location('A-6(2\'-0")'))
        self.assertIsNone(plain["grid_offsets"][0]["direction"])

    def test_double_prime_grid_names_are_not_offsets(self) -> None:
        for text, grids in (('F"-1"', ['F"', '1"']), ('D"-3"', ['D"', '3"'])):
            with self.subTest(text=text):
                item = _occurrence(parse_column_location(text))
                self.assertEqual(item["grids"], grids)
                self.assertIsNone(item["offset"])
                self.assertTrue(item["uncertain"])

    def test_cell_fragments_with_broken_parentheses_stay_unparsed(self) -> None:
        for text in ('") O.6\'-18\'', 'K.9\'(-2\'-8")-16\'(-20\'-8'):
            with self.subTest(text=text):
                parsed = parse_column_location(text)
                self.assertEqual(parsed["kind"], "unparsed")
                self.assertTrue(parsed["uncertain"])
                self.assertEqual(parsed["occurrences"][0]["grids"], [])

    def test_numeric_prime_is_kept_and_marked_uncertain(self) -> None:
        parsed = parse_column_location("A-6'")
        item = _occurrence(parsed)
        self.assertEqual(parsed["raw"], "A-6'")
        self.assertEqual(item["grids"], ["A", "6'"])
        self.assertNotEqual(item["grids"], ["A", "6"])
        self.assertTrue(item["uncertain"])
        self.assertTrue(parsed["uncertain"])


class ColumnLocationLivePathTests(unittest.TestCase):
    def test_table_location_reaches_schedule_row_without_a_quantity(self) -> None:
        record = _transposed_record(
            _Table([
                ["ROOF", "W10X33", "W10X33"],
                ["LEVEL 2", "W10X33", ""],
                ["OFFSET", '+ 2\'-0"', ""],
                ["Column Locations", "A-6", "B.4"],
            ]),
            [
                ["ROOF", "W10X33", "W10X33"],
                ["LEVEL 2", "W10X33", ""],
                ["OFFSET", '+ 2\'-0"', ""],
                ["Column Locations", "A-6", "B.4"],
            ],
            3,
            4,
            [0, 0, 240, 80],
        )
        (grid,) = _ruled_grids([record], _accept)
        roof = [row for row in grid["rows"] if row["level"] == "ROOF" and row["mark"] == "A-6"]
        lower = [row for row in grid["rows"] if row["level"] == "LEVEL 2" and row["mark"] == "A-6"]
        dotted = [row for row in grid["rows"] if row["mark"] == "B.4"]
        self.assertEqual(len(roof), 1)
        self.assertEqual(len(lower), 1)
        self.assertEqual(roof[0]["section"], "W10X33")
        self.assertEqual(lower[0]["section"], "W10X33")
        self.assertEqual(roof[0]["parsed_location"]["raw"], "A-6")
        self.assertEqual(roof[0]["parsed_location"]["occurrences"][0]["grids"], ["A", "6"])
        self.assertEqual(roof[0]["parsed_location"]["occurrences"][0]["offset"], '+ 2\'-0"')
        self.assertEqual(dotted[0]["parsed_location"]["occurrences"][0]["grids"], ["B.4"])
        self.assertEqual(schedule_mark_map([grid]), {})
        self.assertTrue(all("quantity" not in row for row in grid["rows"]))
        self.assertTrue(all(row["mark_role"] == "grid_location" for row in grid["rows"]))

    def test_same_location_and_section_on_two_levels_stay_two_rows(self) -> None:
        record = {
            "page": 28,
            "bbox": [0, 0, 600, 400],
            "layout": "transposed",
            "title": "COLUMN SCHEDULE",
            "locations": [
                {"location": "B-7", "raw": "B-7", "x": 220.0},
            ],
            "cells": [
                {"text": "W12X65", "x": 221.0, "row_label": "ROOF"},
                {"text": "W12X65", "x": 219.0, "row_label": "LEVEL 2"},
            ],
        }
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual(
            [(row["mark"], row["section"], row["level"]) for row in grid["rows"]],
            [("B-7", "W12X65", "ROOF"), ("B-7", "W12X65", "LEVEL 2")],
        )
        self.assertEqual(schedule_mark_map([grid]), {})


def _roles(parsed):
    return parsed["dimensions"]


class PlateStructureTests(unittest.TestCase):
    def test_combined_dimensions_keep_order_and_do_not_assign_roles(self) -> None:
        samples = [
            '3/4"x18"x18"',
            '1"x18"x18"',
            '1 1/4"x18"x18"',
            '1 1/2"x18"x18"',
            '4"x10"x1 1/4"',
            '20"x14"x1-1/4"',
        ]
        for text in samples:
            parsed, status = _interpret_plate(text)
            with self.subTest(text=text):
                self.assertEqual(status, "present")
                self.assertEqual(parsed["raw"], text)
                self.assertEqual(len(parsed["ordered_dimensions"]), 3)
                self.assertTrue(parsed["uncertain"])
                self.assertEqual(_roles(parsed), {"length": None, "width": None, "thickness": None})
                self.assertTrue(all(part.strip('"') in text for part in parsed["ordered_dimensions"]))

    def test_separators_are_equivalent(self) -> None:
        parsed = [_interpret_plate(text)[0]["ordered_dimensions"] for text in (
            '1"x18"x18"',
            '1"X18"X18"',
            '1" × 18" × 18"',
        )]
        self.assertEqual(parsed[0], ["1\"", "18\"", "18\""])
        self.assertEqual(parsed[0], parsed[1])
        self.assertEqual(parsed[0], parsed[2])

    def test_headed_dimensions_follow_the_headings(self) -> None:
        length_first = _rows_record(
            "COLUMN SCHEDULE",
            ["MARK", "SIZE", "LENGTH", "WIDTH", "THICKNESS"],
            [["C1", "W12X65", '18"', '18"', '1"']],
        )
        thick_first = _rows_record(
            "COLUMN SCHEDULE",
            ["MARK", "SIZE", "THK", "WIDTH", "LENGTH"],
            [["C1", "W12X65", '1"', '18"', '18"']],
        )
        for record, thickness in ((length_first, '1"'), (thick_first, '1"')):
            (grid,) = _ruled_grids([record], _accept)
            parsed = grid["rows"][0]["parsed_plate"]
            self.assertEqual(parsed["dimension_source"], "headings")
            self.assertFalse(parsed["uncertain"])
            self.assertEqual(parsed["dimensions"]["length"], '18"')
            self.assertEqual(parsed["dimensions"]["width"], '18"')
            self.assertEqual(parsed["dimensions"]["thickness"], thickness)
            self.assertEqual(grid["rows"][0]["section"], "W12X65")

    def test_combined_cell_does_not_treat_the_last_number_as_thickness(self) -> None:
        record = _rows_record(
            "COLUMN SCHEDULE",
            ["MARK", "SIZE", "BASE PLATE"],
            [["C1", "W12X65", '1"x18"x18"']],
        )
        (grid,) = _ruled_grids([record], _accept)
        row = grid["rows"][0]
        self.assertEqual(row["plate_text"], '1"x18"x18"')
        self.assertEqual(row["plate_role"], "base_plate")
        self.assertIsNone(row["parsed_plate"]["dimensions"]["thickness"])
        self.assertEqual(row["parsed_plate"]["ordered_dimensions"], ['1"', '18"', '18"'])

    def test_base_plate_size_group_ignores_washer_anchor_and_weld(self) -> None:
        header = [
            "TYPE", "TYPE", "BASE PLATE SIZE THICKNESS", "WIDTH", "LENGTH",
            "ANCHOR ROD QTY", "Ø", "EMBED", "EDGE DISTANCE", "COLUMN WELD",
            "PLATE WASHER Ø", "THICKNESS", "COMMENTS",
        ]
        groups = [
            "TYPE", "TYPE", "BASE PLATE SIZE", "BASE PLATE SIZE", "BASE PLATE SIZE",
            "ANCHOR ROD", "ANCHOR ROD", "ANCHOR ROD", "ANCHOR ROD", "COLUMN WELD",
            "PLATE WASHER", "PLATE WASHER", "COMMENTS",
        ]
        rows = {
            "BP6": ["BP6", "B", '1 3/4"', "2'-0\"", "2'-0\"", "4", '1 3/4"', "1'-0\"", '2 1/2"', '1/4"', '4"', '5/8"', ""],
            "BP7": ["BP7", "B", '1 1/2"', "1'-8\"", "1'-8\"", "4", '1"', "1'-0\"", '2"', '1/4"', '3"', '3/8"', ""],
            "BP8": ["BP8", "A", '3/4"', "1'-6\"", "1'-6\"", "4", '3/4"', '8"', '1 1/2"', '1/4"', '2 3/4"', '1/4"', ""],
        }
        expected = {
            "BP6": ('1 3/4"', '2\'-0"', '2\'-0"'),
            "BP7": ('1 1/2"', '1\'-8"', '1\'-8"'),
            "BP8": ('3/4"', '1\'-6"', '1\'-6"'),
        }
        record = _rows_record("BASE PLATE SCHEDULE", header, list(rows.values()), groups=groups)
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual(schedule_mark_map([grid]), {})
        by_mark = {row["mark"]: row for row in grid["rows"]}
        for mark, (thickness, width, length) in expected.items():
            row = by_mark[mark]
            dims = row["parsed_plate"]["dimensions"]
            self.assertEqual(row["plate_status"], "present")
            self.assertEqual(row["plate_role"], "base_plate")
            self.assertFalse(row["catalog_valid"])
            self.assertIsNone(row["section"])
            self.assertEqual(dims["thickness"], thickness)
            self.assertEqual(dims["width"], width)
            self.assertEqual(dims["length"], length)
            self.assertEqual(row["plate_text"], f"{thickness} {width} {length}")
            self.assertNotIn('2 3/4"', row["plate_text"])
            aux = resolve_auxiliary_schedule_mark(mark, {"schedule_grid": [grid]})
            self.assertEqual(aux["display"], f"{thickness} {width} {length}")
            self.assertIsNone(aux.get("section"))
            self.assertFalse(aux.get("abstain"))

    def test_two_remaining_thickness_columns_stay_unresolved(self) -> None:
        record = _rows_record(
            "BASE PLATE SCHEDULE",
            ["MARK", "THICKNESS", "WIDTH", "LENGTH", "THICKNESS"],
            [["BP8", '3/4"', '1\'-6"', '1\'-6"', '1"']],
            groups=["MARK", "BASE PLATE SIZE", "BASE PLATE SIZE", "BASE PLATE SIZE", "CAP SIZE"],
        )
        (grid,) = _ruled_grids([record], _accept)
        row = grid["rows"][0]
        # A second THICKNESS heading does not replace the first. The plate
        # stays unresolved, and the first printed thickness is kept.
        self.assertEqual(row["plate_status"], "unresolved")
        self.assertEqual(
            row["parsed_plate"]["dimensions"],
            {"length": "1'-6\"", "width": "1'-6\"", "thickness": '3/4"'},
        )
        self.assertFalse(row["catalog_valid"])
        self.assertEqual(schedule_mark_map([grid]), {})

    def test_empty_plate_values_are_not_plates(self) -> None:
        for text in ("", "-", "–", "—", "N/A", "NA", "NONE", "NO PLATE"):
            record = _rows_record(
                "COLUMN SCHEDULE",
                ["MARK", "SIZE", "BASE PLATE"],
                [["C1", "W12X65", text]],
            )
            (grid,) = _ruled_grids([record], _accept)
            row = grid["rows"][0]
            with self.subTest(text=text):
                self.assertEqual(row["plate_status"], "not_applicable")
                self.assertIsNone(row["plate_role"])
                self.assertEqual(row["parsed_plate"]["ordered_dimensions"], [])
                self.assertEqual(plate_count_per_member(row), 0)
                self.assertEqual(schedule_mark_map([grid]), {"C1": "W12X65"})

    def test_missing_plate_mark_stays_unresolved(self) -> None:
        record = _rows_record(
            "COLUMN SCHEDULE",
            ["MARK", "SIZE", "BASE PLATE"],
            [["C1", "W12X65", "BP999"]],
        )
        (grid,) = _ruled_grids([record], _accept)
        row = grid["rows"][0]
        self.assertEqual(row["plate_text"], "BP999")
        self.assertEqual(row["plate_status"], "unresolved")
        self.assertIsNone(row.get("resolved_plate"))
        self.assertEqual(row["parsed_plate"]["ordered_dimensions"], [])
        self.assertEqual(plate_count_per_member(row), 0)

    def test_dirty_plate_keeps_raw_text_and_extracts_one_triple(self) -> None:
        text = 'TYPE OF INSPECTION 4"x10"x1 1/4"'
        record = _rows_record(
            "BEARING PLATE SCHEDULE",
            ["MARK", "SIZE"],
            [["BP6", text]],
        )
        (grid,) = _ruled_grids([record], _accept)
        row = grid["rows"][0]
        self.assertEqual(row["plate_text"], text)
        self.assertEqual(row["plate_status"], "present")
        self.assertEqual(row["parsed_plate"]["raw"], text)
        self.assertEqual(row["parsed_plate"]["ordered_dimensions"], ['4"', '10"', '1 1/4"'])
        self.assertIn("TYPE OF INSPECTION", row["parsed_plate"]["notes"])
        self.assertIsNone(row["parsed_plate"]["dimensions"]["thickness"])
        self.assertEqual(row["plate_role"], "bearing_plate")

    def test_column_plate_mark_resolves_from_the_base_plate_schedule(self) -> None:
        column = _rows_record(
            "COLUMN SCHEDULE",
            ["MARK", "SIZE", "BASE PLATE"],
            [["C1", "W12X65", "BP1"]],
        )
        plates = _rows_record(
            "BASE PLATE SCHEDULE",
            ["MARK", "SIZE"],
            [["BP1", '1"x18"x18"']],
        )
        grids = _ruled_grids([column, plates], _accept)
        column_row = next(row for grid in grids if grid["kind"] == "column" for row in grid["rows"])
        self.assertEqual(column_row["plate_text"], "BP1")
        self.assertEqual(column_row["section"], "W12X65")
        resolved = column_row["resolved_plate"]
        self.assertEqual(resolved["mark"], "BP1")
        self.assertEqual(resolved["plate_role"], "base_plate")
        self.assertEqual(resolved["source_schedule"], "BASE PLATE SCHEDULE")
        self.assertEqual(resolved["source_page"], 2)
        self.assertEqual(resolved["parsed_plate"]["ordered_dimensions"], ['1"', '18"', '18"'])
        self.assertIsNone(resolved["parsed_plate"]["dimensions"]["thickness"])

    def test_duplicate_plate_marks_are_not_chosen(self) -> None:
        column = _rows_record(
            "COLUMN SCHEDULE",
            ["MARK", "SIZE", "BASE PLATE"],
            [["C1", "W12X65", "BP1"]],
        )
        base = _rows_record("BASE PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '1"x18"x18"']])
        bearing = _rows_record(
            "BEARING PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '3/4"x6"x6"']],
        )
        grids = _ruled_grids([column, base, bearing], _accept)
        column_row = next(row for grid in grids if grid["kind"] == "column" for row in grid["rows"])
        self.assertEqual(column_row["plate_text"], "BP1")
        self.assertEqual(column_row["plate_status"], "ambiguous")
        self.assertIsNone(column_row["resolved_plate"])
        self.assertEqual(len(column_row["plate_candidates"]), 2)
        self.assertEqual(
            {item["plate_role"] for item in column_row["plate_candidates"]},
            {"base_plate", "bearing_plate"},
        )
        self.assertIsNone(resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": grids})["kind"])

    def test_schedule_context_not_the_bp_prefix_sets_the_plate_type(self) -> None:
        base = _ruled_grids([
            _rows_record("BASE PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '1"x18"x18"']])
        ], _accept)
        bearing = _ruled_grids([
            _rows_record("BEARING PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '3/4"x6"x6"']])
        ], _accept)
        self.assertEqual(base[0]["rows"][0]["plate_role"], "base_plate")
        self.assertEqual(bearing[0]["rows"][0]["plate_role"], "bearing_plate")
        self.assertEqual(
            resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": base})["kind"],
            "base_plate",
        )
        self.assertEqual(
            resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": bearing})["kind"],
            "bearing_plate",
        )

    def test_bent_plate_schedule_is_not_a_base_or_bearing_definition(self) -> None:
        column = _rows_record(
            "COLUMN SCHEDULE",
            ["MARK", "SIZE", "BASE PLATE"],
            [["C1", "W12X65", "BP1"]],
        )
        bent = _rows_record("BENT PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '1"x18"x18"']])
        grids = _ruled_grids([column, bent], _accept)
        bent_grid = next(grid for grid in grids if "BENT" in grid["title"])
        column_row = next(row for grid in grids if grid["kind"] == "column" for row in grid["rows"])
        self.assertEqual(bent_grid["kind"], "plate")
        self.assertNotIn(bent_grid["rows"][0]["plate_role"], {"base_plate", "bearing_plate"})
        self.assertEqual(column_row["plate_text"], "BP1")
        self.assertIsNone(column_row.get("resolved_plate"))
        self.assertEqual(column_row["plate_status"], "unresolved")
        self.assertIsNone(resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": grids}))

    def test_transposed_plate_metadata_does_not_change_location_fields(self) -> None:
        record = {
            "page": 28,
            "bbox": [0, 0, 400, 200],
            "layout": "transposed",
            "title": "COLUMN SCHEDULE",
            "locations": [{"location": "A-7", "raw": "A-7", "x": 100.0}],
            "cells": [
                {"text": "W10X33", "x": 100.0, "row_label": "ROOF"},
                {"text": '1"x18"x18"', "x": 100.0, "row_label": "BASE PLATE SIZE"},
            ],
        }
        (grid,) = _ruled_grids([record], _accept)
        row = grid["rows"][0]
        self.assertEqual(row["mark"], "A-7")
        self.assertEqual(row["mark_role"], "grid_location")
        self.assertEqual(row["parsed_location"]["raw"], "A-7")
        self.assertEqual(row["plate_text"], '1"x18"x18"')
        self.assertEqual(row["plate_role"], "base_plate")
        self.assertEqual(row["plate_status"], "present")
        self.assertEqual(row["parsed_plate"]["ordered_dimensions"], ['1"', '18"', '18"'])
        self.assertIsNone(lookup_schedule_row("A-7", {"schedule_grid": [grid]}))
        self.assertEqual(schedule_mark_map([grid]), {})

    def test_live_base_plate_mark_resolves_through_document_grids(self) -> None:
        column = _rows_record(
            "COLUMN SCHEDULE", ["MARK", "SIZE", "BASE PLATE"], [["C1", "W12X65", "BP1"]],
        )
        base = _rows_record("BASE PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '1"x18"x18"']])
        words = _placed([
            ("BASE", 100, 0), ("PLATE", 150, 0), ("SCHEDULE", 210, 0),
            ("MARK", 100, 30), ("SIZE", 220, 30),
            ("BP1", 100, 50), ('1"x18"x18"', 220, 50),
            ("COLUMN", 100, 400), ("SCHEDULE", 180, 400),
            ("MARK", 100, 430), ("SIZE", 180, 430), ("BASE", 300, 430), ("PLATE", 350, 430),
            ("C1", 100, 450), ("W12X65", 180, 450), ("BP1", 320, 450),
        ])
        for name, clustered in (("ruled-only", []), ("word-cluster", words)):
            with self.subTest(name=name):
                with patch(
                    "services.engineering.schedule_grid.read_ruled_tables",
                    return_value=[column, base],
                ):
                    grids = build_document_schedule_grids(
                        clustered, pdf_path="x.pdf", catalog_fn=_accept,
                    )
                self._assert_live_plate(grids, "base_plate", "BASE PLATE SCHEDULE", ['1"', '18"', '18"'])

    def test_live_bearing_plate_mark_resolves_through_document_grids(self) -> None:
        column = _rows_record(
            "COLUMN SCHEDULE", ["MARK", "SIZE", "BASE PLATE"], [["C1", "W12X65", "BP1"]],
        )
        bearing = _rows_record(
            "BEARING PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '4"x6"x3/4"']],
        )
        words = _placed([
            ("BEARING", 100, 200), ("PLATE", 180, 200), ("SCHEDULE", 240, 200),
            ("MARK", 100, 230), ("SIZE", 220, 230),
            ("BP1", 100, 250), ('4"x6"x3/4"', 220, 250),
            ("COLUMN", 100, 400), ("SCHEDULE", 180, 400),
            ("MARK", 100, 430), ("SIZE", 180, 430), ("BASE", 300, 430), ("PLATE", 350, 430),
            ("C1", 100, 450), ("W12X65", 180, 450), ("BP1", 320, 450),
        ])
        for name, clustered in (("ruled-only", []), ("word-cluster", words)):
            with self.subTest(name=name):
                with patch(
                    "services.engineering.schedule_grid.read_ruled_tables",
                    return_value=[column, bearing],
                ):
                    grids = build_document_schedule_grids(
                        clustered, pdf_path="x.pdf", catalog_fn=_accept,
                    )
                self._assert_live_plate(
                    grids, "bearing_plate", "BEARING PLATE SCHEDULE", ['4"', '6"', '3/4"'],
                )

    def test_live_duplicate_plate_marks_stay_ambiguous(self) -> None:
        column = _rows_record(
            "COLUMN SCHEDULE", ["MARK", "SIZE", "BASE PLATE"], [["C1", "W12X65", "BP1"]],
        )
        base = _rows_record("BASE PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '1"x18"x18"']])
        bearing = _rows_record(
            "BEARING PLATE SCHEDULE", ["MARK", "SIZE"], [["BP1", '4"x6"x3/4"']],
        )
        words = _placed([
            ("BASE", 100, 0), ("PLATE", 150, 0), ("SCHEDULE", 210, 0),
            ("MARK", 100, 30), ("SIZE", 220, 30),
            ("BP1", 100, 50), ('1"x18"x18"', 220, 50),
            ("BEARING", 100, 200), ("PLATE", 180, 200), ("SCHEDULE", 240, 200),
            ("MARK", 100, 230), ("SIZE", 220, 230),
            ("BP1", 100, 250), ('4"x6"x3/4"', 220, 250),
            ("COLUMN", 100, 400), ("SCHEDULE", 180, 400),
            ("MARK", 100, 430), ("SIZE", 180, 430), ("BASE", 300, 430), ("PLATE", 350, 430),
            ("C1", 100, 450), ("W12X65", 180, 450), ("BP1", 320, 450),
        ])
        for name, clustered in (("ruled-only", []), ("word-cluster", words)):
            with self.subTest(name=name):
                with patch(
                    "services.engineering.schedule_grid.read_ruled_tables",
                    return_value=[column, base, bearing],
                ):
                    grids = build_document_schedule_grids(
                        clustered, pdf_path="x.pdf", catalog_fn=_accept,
                    )
                column_row = next(row for grid in grids if grid["kind"] == "column" for row in grid["rows"])
                self.assertEqual(column_row["plate_text"], "BP1")
                self.assertEqual(column_row["plate_status"], "ambiguous")
                self.assertIsNone(column_row["resolved_plate"])
                self.assertEqual(len(column_row["plate_candidates"]), 2)
                self.assertEqual(
                    {item["plate_role"] for item in column_row["plate_candidates"]},
                    {"base_plate", "bearing_plate"},
                )
                self.assertIsNone(resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": grids})["kind"])
                self.assertNotIn("BP1", schedule_mark_map(grids))

    def test_live_location_row_stays_out_of_the_mark_map(self) -> None:
        record = {
            "page": 28,
            "bbox": [0, 0, 400, 200],
            "layout": "transposed",
            "title": "COLUMN SCHEDULE",
            "locations": [{"location": "A-7", "raw": "A-7", "x": 100.0}],
            "cells": [
                {"text": "W10X33", "x": 100.0, "row_label": "ROOF"},
                {"text": '1"x18"x18"', "x": 100.0, "row_label": "BASE PLATE SIZE"},
            ],
        }
        with patch("services.engineering.schedule_grid.read_ruled_tables", return_value=[record]):
            grids = build_document_schedule_grids([], pdf_path="x.pdf", catalog_fn=_accept)
        row = grids[0]["rows"][0]
        self.assertEqual(row["mark"], "A-7")
        self.assertEqual(row["mark_role"], "grid_location")
        self.assertEqual(row["parsed_location"]["raw"], "A-7")
        self.assertEqual(row["parsed_location"]["occurrences"][0]["grids"], ["A", "7"])
        self.assertEqual(row["plate_text"], '1"x18"x18"')
        self.assertEqual(schedule_mark_map(grids), {})
        self.assertIsNone(lookup_schedule_row("A-7", {"schedule_grid": grids}))

    def _assert_live_plate(self, grids, role, title, ordered) -> None:
        column_row = next(row for grid in grids if grid["kind"] == "column" for row in grid["rows"])
        definitions = [row for grid in grids for row in grid["rows"] if row["mark"] == "BP1"]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(column_row["plate_text"], "BP1")
        self.assertEqual(column_row["plate_status"], "present")
        resolved = column_row["resolved_plate"]
        self.assertEqual(resolved["plate_role"], role)
        self.assertEqual(resolved["source_schedule"], title)
        self.assertEqual(resolved["source_page"], 2)
        self.assertEqual(resolved["parsed_plate"]["ordered_dimensions"], ordered)
        aux = resolve_auxiliary_schedule_mark("BP1", {"schedule_grid": grids})
        self.assertEqual(aux["kind"], role)
        self.assertEqual(schedule_mark_map(grids), {"C1": "W12X65"})
        self.assertNotIn("BP1", schedule_mark_map(grids))


class TransposedLevelTests(unittest.TestCase):
    def test_datum_and_name_keep_the_printed_prefix(self) -> None:
        split = _split_transposed_level_label('14\' - 6" GROUND LEVEL')
        self.assertEqual(split["level_band"]["printed_elevation"], '14\' - 6"')
        self.assertEqual(split["level_band"]["printed_name"], "GROUND LEVEL")
        self.assertEqual(split["level_band"]["prefix_status"], "present")

    def test_compact_datum_splits_and_stays_unpaired_until_the_lines_say_so(self) -> None:
        # Brandywine S-501: ``14'-0" LEVEL 1`` is one printed band. The parts
        # split; pairing still waits for the drawn lines.
        band = _split_transposed_level_label('14\'-0" LEVEL 1')["level_band"]
        self.assertEqual(band["raw"], '14\'-0" LEVEL 1')
        self.assertEqual(band["printed_elevation"], '14\'-0"')
        self.assertEqual(band["printed_name"], "LEVEL 1")
        self.assertEqual(band["prefix_status"], "present")
        self.assertEqual((band["pairing"], band["level"]), ("unresolved", None))

    def test_spaced_first_floor_datum_splits(self) -> None:
        band = _split_transposed_level_label('14\' - 0" FIRST FLOOR')["level_band"]
        self.assertEqual(band["printed_elevation"], '14\' - 0"')
        self.assertEqual(band["printed_name"], "FIRST FLOOR")
        self.assertEqual(band["prefix_status"], "present")
        self.assertEqual(band["pairing"], "unresolved")

    def test_negative_and_zero_datums_split(self) -> None:
        negative = _split_transposed_level_label('-5\'-0" LOWER LEVEL')["level_band"]
        self.assertEqual(negative["printed_elevation"], '-5\'-0"')
        self.assertEqual(negative["printed_name"], "LOWER LEVEL")
        zero = _split_transposed_level_label('0\'-0"')["level_band"]
        self.assertEqual(zero["printed_elevation"], '0\'-0"')
        self.assertIsNone(zero["printed_name"])
        fraction = _split_transposed_level_label('13\'-6 3/4" TOP OF STEEL')["level_band"]
        self.assertEqual(fraction["printed_elevation"], '13\'-6 3/4"')
        self.assertEqual(fraction["printed_name"], "TOP OF STEEL")

    def test_incomplete_and_non_elevation_text_do_not_split(self) -> None:
        for label in ("14'", "A-14", "W14X22", '1"x18"x18"', "LEVEL 1"):
            band = _split_transposed_level_label(label)["level_band"]
            self.assertIsNone(band["printed_elevation"], label)
            self.assertEqual(band["printed_name"], label)
            self.assertEqual(band["prefix_status"], "absent")
        two = _split_transposed_level_label('14\'-0" / 16\'-0" LEVEL')["level_band"]
        self.assertEqual(two["prefix_status"], "unresolved")
        self.assertIsNone(two["printed_elevation"])
        self.assertIsNone(two["printed_name"])

    def test_same_line_pairs_only_when_one_drawn_line_prints_both(self) -> None:
        label = '14\'-0" LEVEL 1'
        grids = [{"page": 42, "rows": [{"mark": "A-1", **_split_transposed_level_label(label)}]}]
        attach_level_bands(grids, {"schedules": [{
            "id": "s",
            "level_lines": [{
                "name": "LEVEL 1", "elevation_text": '14\'-0"', "page": 42,
                "y": 10, "block": 1,
            }],
        }]})
        band = grids[0]["rows"][0]["level_band"]
        self.assertEqual(band["pairing"], "paired")
        self.assertEqual(band["level"], {"name": "LEVEL 1", "elevation_text": '14\'-0"'})

    def test_separate_lines_stay_unpaired(self) -> None:
        # The band between two lines prints the upper elevation and the lower
        # name. Those parts are not one level.
        label = '14\' - 0" FIRST FLOOR'
        grids = [{"page": 26, "rows": [{"mark": "A-1", **_split_transposed_level_label(label)}]}]
        attach_level_bands(grids, {"schedules": [{
            "id": "s",
            "level_lines": [
                {"name": "SECOND FLOOR", "elevation_text": '14\' - 0"', "page": 26, "y": 10, "block": 1},
                {"name": "FIRST FLOOR", "elevation_text": '0\' - 0"', "page": 26, "y": 30, "block": 1},
            ],
        }]})
        band = grids[0]["rows"][0]["level_band"]
        self.assertEqual(band["printed_elevation"], '14\' - 0"')
        self.assertEqual(band["printed_name"], "FIRST FLOOR")
        self.assertEqual(band["pairing"], "unpaired")
        self.assertIsNone(band["level"])
        self.assertEqual(band["elevation_of"]["level"], "SECOND FLOOR")
        self.assertEqual(band["name_of"]["level"], "FIRST FLOOR")

    def test_neighboring_bands_on_different_blocks_stay_unresolved(self) -> None:
        label = '29\' - 0" UPPER LEVEL'
        grids = [{"page": 28, "rows": [{"mark": "A-1", **_split_transposed_level_label(label)}]}]
        attach_level_bands(grids, {"schedules": [{
            "id": "s",
            "level_lines": [
                {"name": "MAIN ROOF", "elevation_text": '29\' - 0"', "page": 28, "y": 10, "block": 1},
                {"name": "UPPER LEVEL", "elevation_text": '14\' - 6"', "page": 28, "y": 40, "block": 2},
            ],
        }]})
        band = grids[0]["rows"][0]["level_band"]
        self.assertEqual(band["printed_name"], "UPPER LEVEL")
        self.assertEqual(band["pairing"], "unresolved")
        self.assertIsNone(band["level"])

    def test_printed_parts_are_not_a_level_until_the_drawn_lines_say_so(self) -> None:
        # Burrville S-501 p28: the band between MAIN ROOF and UPPER LEVEL lines
        # prints MAIN ROOF's 29' - 0" and UPPER LEVEL's name.
        band = _split_transposed_level_label('29\' - 0" UPPER LEVEL')["level_band"]
        self.assertEqual(band["raw"], '29\' - 0" UPPER LEVEL')
        self.assertEqual((band["pairing"], band["level"]), ("unresolved", None))

    def test_zero_datum_has_no_level_name(self) -> None:
        split = _split_transposed_level_label('0\' - 0"')
        self.assertEqual(split["level_band"]["printed_elevation"], '0\' - 0"')
        self.assertIsNone(split["level_band"]["printed_name"])
        self.assertEqual(split["level_band"]["prefix_status"], "present")

    def test_main_roof_and_upper_level_datums(self) -> None:
        roof = _split_transposed_level_label('44\' - 6" MAIN ROOF')
        upper = _split_transposed_level_label('29\' - 0" UPPER LEVEL')
        self.assertEqual(roof["level_band"]["printed_elevation"], '44\' - 6"')
        self.assertEqual(roof["level_band"]["printed_name"], "MAIN ROOF")
        self.assertEqual(roof["level_band"]["prefix_status"], "present")
        self.assertEqual(upper["level_band"]["printed_elevation"], '29\' - 0"')
        self.assertEqual(upper["level_band"]["printed_name"], "UPPER LEVEL")
        self.assertEqual(upper["level_band"]["prefix_status"], "present")

    def test_name_only_label_has_no_elevation(self) -> None:
        split = _split_transposed_level_label("UPPER ROOF")
        self.assertIsNone(split["level_band"]["printed_elevation"])
        self.assertEqual(split["level_band"]["printed_name"], "UPPER ROOF")
        self.assertEqual(split["level_band"]["prefix_status"], "absent")

    def test_reaction_label_is_not_an_elevation(self) -> None:
        split = _split_transposed_level_label("UNFACTORED REACTION (KIPS)")
        self.assertIsNone(split["level_band"]["printed_elevation"])
        self.assertEqual(split["level_band"]["prefix_status"], "absent")

    def test_two_datums_stay_unresolved(self) -> None:
        label = '14\' - 6" / 29\' - 0" LEVEL'
        split = _split_transposed_level_label(label)
        self.assertIsNone(split["level_band"]["printed_elevation"])
        self.assertIsNone(split["level_band"]["printed_name"])
        self.assertEqual(split["level_band"]["prefix_status"], "unresolved")
        buried = _split_transposed_level_label('GROUND LEVEL 14\' - 6"')
        self.assertIsNone(buried["level_band"]["printed_elevation"])
        self.assertIsNone(buried["level_band"]["printed_name"])
        self.assertEqual(buried["level_band"]["prefix_status"], "unresolved")

    def test_same_location_keeps_one_row_per_level(self) -> None:
        record = {
            "page": 28,
            "bbox": [0, 0, 200, 200],
            "layout": "transposed",
            "title": "COLUMN SCHEDULE",
            "locations": [{"location": "A-7", "raw": "A-7", "x": 100.0}],
            "cells": [
                {"text": "W10X33", "x": 100.0, "row_label": '0\' - 0"'},
                {"text": "W10X33", "x": 100.0, "row_label": '14\' - 6" GROUND LEVEL'},
                {"text": "W10X33", "x": 100.0, "row_label": '29\' - 0" UPPER LEVEL'},
                {"text": "120", "x": 100.0, "row_label": "UNFACTORED REACTION (KIPS)"},
                {"text": '1"x18"x18"', "x": 100.0, "row_label": "BASE PLATE SIZE"},
            ],
        }
        (grid,) = _ruled_grids([record], _accept)
        self.assertEqual(
            [(row["level"], row["level_band"]["printed_elevation"], row["level_band"]["printed_name"], row["level_band"]["prefix_status"]) for row in grid["rows"]],
            [
                ('0\' - 0"', '0\' - 0"', None, "present"),
                ('14\' - 6" GROUND LEVEL', '14\' - 6"', "GROUND LEVEL", "present"),
                ('29\' - 0" UPPER LEVEL', '29\' - 0"', "UPPER LEVEL", "present"),
            ],
        )
        self.assertTrue(all(row["mark"] == "A-7" and row["mark_role"] == "grid_location" for row in grid["rows"]))
        self.assertEqual(grid["rows"][0]["parsed_location"]["raw"], "A-7")
        self.assertEqual(grid["rows"][0]["plate_text"], '1"x18"x18"')
        self.assertEqual(schedule_mark_map([grid]), {})
        self.assertIsNone(lookup_schedule_row("A-7", {"schedule_grid": [grid]}))

    def test_ruled_column_rows_do_not_receive_level_elevation_fields(self) -> None:
        (grid,) = _ruled_grids([
            _rows_record(
                "COLUMN SCHEDULE",
                ["MARK", "SIZE", "BASE PLATE"],
                [["C1", "W12X65", "BP1"]],
            )
        ], _accept)
        row = grid["rows"][0]
        self.assertNotIn("level", row)
        self.assertNotIn("level_band", row)
        self.assertEqual(row["plate_text"], "BP1")


class ScheduleHeadingDisplayTests(unittest.TestCase):
    """Display-only reading of printed headings and of rows the grid does not take."""

    def test_merged_header_cells_head_every_column_they_span(self) -> None:
        # MARK | REINFORCEMENT (over 4) / TOP (over 2) | BOTTOM (over 2) / LONG | SHORT | LONG | SHORT
        span = lambda c0, c1: (60.0 * c0, 0.0, 60.0 * c1, 10.0)
        table = SimpleNamespace(rows=[
            SimpleNamespace(cells=[span(0, 1), span(1, 5), None, None, None]),
            SimpleNamespace(cells=[None, span(1, 3), None, span(3, 5), None]),
            SimpleNamespace(cells=[None, span(1, 2), span(2, 3), span(3, 4), span(4, 5)]),
            SimpleNamespace(cells=[span(c, c + 1) for c in range(5)]),
        ])
        raw = [["MARK", "REINFORCEMENT", None, None, None], [None, "TOP", None, "BOTTOM", None],
               [None, "LONG WAY", "SHORT WAY", "LONG WAY", "SHORT WAY"], ["WF1", "(4)-#4", "#4@12", "(4)-#4", "#4@12"]]
        self.assertEqual(_header_paths(table, raw, 0, 3), [
            ["MARK"],
            ["REINFORCEMENT", "TOP", "LONG WAY"], ["REINFORCEMENT", "TOP", "SHORT WAY"],
            ["REINFORCEMENT", "BOTTOM", "LONG WAY"], ["REINFORCEMENT", "BOTTOM", "SHORT WAY"],
        ])

    def test_a_column_outside_the_ruling_read_is_taken_from_the_rule_it_shares(self) -> None:
        record = {"bbox": [0, 0, 200, 60], "body": [{"bbox": [0, 20, 200, 40]}, {"bbox": [0, 40, 200, 60]}]}
        line = lambda x0, x1, y: {"items": [("l", fitz.Point(x0, y), fitz.Point(x1, y))]}
        words = [(250, 5, 300, 15, "REMARKS"), (230, 42, 250, 50, "SEE"), (252, 42, 300, 50, "SECTION"),
                 (420, 25, 460, 35, "ELSEWHERE")]
        rules = [line(0, 400, y) for y in (20, 40, 60)]
        found = _trailing_column(record, words, rules, [])
        self.assertEqual(found["cells"], ["", "SEE SECTION"])
        self.assertEqual(found["bboxes"], [[200, 20, 400, 40], [200, 40, 400, 60]])
        # No rule running past the table: nothing is read beside it.
        self.assertIsNone(_trailing_column(record, words, [line(0, 200, 60)], []))
        # Words inside another table read on the page are never taken.
        self.assertIsNone(_trailing_column(record, words, [line(0, 400, 60)], [[220, 0, 400, 60]]))
        # A merged remarks cell has no row separator: do not assign its words
        # to either of the independently ruled production rows.
        self.assertEqual(_trailing_column(record, words, [line(0, 400, 20), line(0, 400, 60)], [])["cells"], ["", ""])
        # A distant border and a nearby note are not a remarks heading.
        self.assertIsNone(_trailing_column(record, [(250, 5, 300, 15, "NOTES"), *words[1:]], rules, []))
        crossing = [words[0], (230, 35, 300, 46, "CROSSES ROW BOUNDARY")]
        self.assertEqual(_trailing_column(record, crossing, rules, [])["cells"], ["", ""])

    def test_cells_keep_full_paths_and_rows_not_taken_are_listed(self) -> None:
        record = _rows_record(
            "CONCRETE BEAM SCHEDULE",
            ["MARK", "SIZE WIDTH", "DEPTH", "TOP BARS L.E. BARS", "F.L. BARS"],
            [["16RB32", "", "", "", ""], ["CB16x32", '16"', '32"', "", "4-#6"]],
        )
        record["header_paths"] = [["MARK"], ["SIZE", "WIDTH"], ["SIZE", "DEPTH"],
                                  ["REINFORCEMENT", "TOP BARS", "L.E. BARS"], ["REINFORCEMENT", "TOP BARS", "F.L. BARS"]]
        record["trailing_column"] = {"heading": "REMARKS", "cells": ["PRECAST BEAM. SEE PCI TABLES", ""]}
        (grid,) = _ruled_grids([record], _accept)
        (row,) = grid["rows"]
        self.assertEqual(row["mark"], "CB16X32")
        self.assertEqual([(c["path"], c["text"]) for c in row["cells"]], [
            (["SIZE", "WIDTH"], '16"'), (["SIZE", "DEPTH"], '32"'),
            (["REINFORCEMENT", "TOP BARS", "L.E. BARS"], ""), (["REINFORCEMENT", "TOP BARS", "F.L. BARS"], "4-#6"),
            (["REMARKS"], ""),
        ])
        self.assertEqual(grid["printed_rows"], 2)
        (unread,) = grid["unread_rows"]
        self.assertEqual(unread["printed_mark"], "16RB32")
        self.assertEqual(unread["cells"][-1]["text"], "PRECAST BEAM. SEE PCI TABLES")
        self.assertEqual(schedule_mark_map([grid]), {})


class _BandTable:
    """find_tables stand-in with row boxes: label column 0-60, one value column 60-120."""

    def __init__(self, edges):
        self.rows = [
            SimpleNamespace(
                bbox=(0.0, top, 120.0, bottom),
                cells=[(0.0, top, 60.0, bottom), (60.0, top, 120.0, bottom)],
            )
            for top, bottom in zip(edges, edges[1:])
        ]


def _word(text, top, x=5.0):
    return (x, top, x + 30.0, top + 10.0, text)


class PairedLevelLineTests(unittest.TestCase):
    # LEVEL 4 / 42'-0" sit on either side of the edge at y=100, and so on.
    _ROWS = [
        ["LEVEL 4", ""],
        ['42\'-0" LEVEL 3', "W10X33"],
        ['28\'-0" LOWER LEVEL', "W10X33"],
        ['-5\'-0"', ""],
        ["Column Locations", "A-1"],
    ]
    _EDGES = [0.0, 100.0, 200.0, 300.0, 400.0, 430.0]

    def _record(self, words):
        rows = self._ROWS
        return _transposed_record(
            _BandTable(self._EDGES), rows, 4, 42, [0, 0, 120, 430], words
        )

    def _words(self):
        return [
            _word("LEVEL", 85.0), _word("4", 85.0, 40.0), _word('42\'-0"', 105.0),
            _word("LEVEL", 185.0), _word("3", 185.0, 40.0), _word('28\'-0"', 205.0),
            _word("LOWER", 275.0), _word("LEVEL", 286.0), _word('-5\'-0"', 305.0),
        ]

    def test_names_pair_with_the_elevation_below_their_edge(self) -> None:
        record = self._record(self._words())
        self.assertEqual(
            [(line["name"], line["elevation_text"]) for line in record["level_lines"]],
            [("LEVEL 4", "42'-0\""), ("LEVEL 3", "28'-0\""), ("LOWER LEVEL", "-5'-0\"")],
        )
        (grid,) = _ruled_grids([record], _accept)
        rows = [row for row in grid["rows"]]
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["level"], '42\'-0" LEVEL 3')
        self.assertEqual(
            first["level_span"],
            {
                "upper": {"name": "LEVEL 4", "elevation_text": "42'-0\""},
                "lower": {"name": "LEVEL 3", "elevation_text": "28'-0\""},
            },
        )
        band = first["level_band"]
        self.assertEqual(band["raw"], '42\'-0" LEVEL 3')
        self.assertEqual(band["printed_elevation"], '42\'-0"')
        self.assertEqual(band["printed_name"], "LEVEL 3")
        self.assertEqual(band["prefix_status"], "present")
        self.assertEqual(band["pairing"], "unresolved")
        self.assertIsNone(band["level"])
        self.assertNotIn("level_elevation_text", first)
        self.assertEqual(first["mark_role"], "grid_location")
        self.assertEqual(schedule_mark_map([grid]), {})

    def test_an_unpaired_label_line_pairs_nothing(self) -> None:
        words = self._words()[:-1] + [_word("EXTRA", 350.0)]
        record = self._record(words)
        self.assertNotIn("level_lines", record)
        (grid,) = _ruled_grids([record], _accept)
        row = grid["rows"][0]
        self.assertNotIn("level_span", row)
        self.assertEqual(row["level_band"]["printed_elevation"], '42\'-0"')
        self.assertEqual(row["level_band"]["printed_name"], "LEVEL 3")
        self.assertEqual(row["level_band"]["pairing"], "unresolved")
        self.assertIsNone(row["level_band"]["level"])
        self.assertNotIn("level_elevation_text", row)

    @staticmethod
    def _titled(*titles):
        blocks = []
        for page, title in titles:
            blocks.append({"page_number": page, "bbox": [0, 0, 100, 10], "text": "DRAWING TITLE:"})
            blocks.append({"page_number": page, "bbox": [0, 12, 100, 22], "text": title})
        return {"title_blocks": blocks}

    _GRIDS = [
        {
            "page": 42,
            "level_lines": [
                {"name": "LEVEL 1", "elevation_text": '0"', "edge": 1.0},
                {"name": "LEVEL 2", "elevation_text": "14'-0\"", "edge": 2.0},
                {"name": "LOWER LEVEL", "elevation_text": "-5'-0\"", "edge": 3.0},
            ],
        },
        {"page": 43, "level_lines": [{"name": "LEVEL 2", "elevation_text": "14'-0\"", "edge": 2.0}]},
    ]

    def test_plan_titles_link_to_the_printed_level_name_and_elevation(self) -> None:
        document = self._titled(
            (11, "LEVEL 2 FRAMING PLAN - OVERALL 8' 4' 16' 24' 0'"),
            (21, "HIGH ROOF FRAMING PLAN - OVERALL 8' 4' 16' 24' 0'"),
            (6, "FOUNDATION PLAN - OVERALL 8' 4' 16' 24' 0'"),
            (9, "LOWER LEVEL FRAMING PLAN"),
        )
        links = link_level_names_to_plans(document, self._GRIDS)
        self.assertEqual(
            [(l["page"], l["level_name"], l["elevation_text"], l["status"]) for l in links],
            [
                (9, "LOWER LEVEL", "-5'-0\"", "linked"),
                (11, "LEVEL 2", "14'-0\"", "linked"),
            ],
        )
        self.assertEqual(links[1]["title"], "LEVEL 2 FRAMING PLAN - OVERALL")
        self.assertEqual(links[1]["schedule_pages"], [42, 43])

    def test_ambiguous_or_partial_level_names_do_not_link(self) -> None:
        document = self._titled(
            (11, "LEVEL 1 AND LEVEL 2 FRAMING PLAN"),
            (12, "LEVEL 12 FRAMING PLAN"),
        )
        links = link_level_names_to_plans(document, self._GRIDS)
        self.assertEqual(
            [(l["page"], l["status"], l.get("candidates")) for l in links],
            [(11, "ambiguous", ["LEVEL 1", "LEVEL 2"])],
        )

    @staticmethod
    def _level(name, elevation):
        return {"name": name, "elevation_text": elevation}

    def _row(self, mark, upper, lower, section="W10X33"):
        return {
            "mark": mark, "mark_role": "grid_location", "section": section,
            "level_span": {"upper": upper and self._level(*upper), "lower": lower and self._level(*lower)},
        }

    def test_column_endpoints_are_the_named_levels_at_each_end(self) -> None:
        l3, l2, l1 = ("LEVEL 3", "28'-0\""), ("LEVEL 2", "14'-0\""), ("LEVEL 1", '0"')
        grid = {
            "page": 42,
            "level_lines": [{"name": n, "elevation_text": e, "edge": i} for i, (n, e) in enumerate((l3, l2, l1))],
            "rows": [
                self._row("A-1", l3, l2), self._row("A-1", l2, l1, "W10X45"),
                self._row("A-2", l2, l1),
                self._row("A-3", l3, l2), self._row("A-4", None, l3),
            ],
        }
        by_location = {e["location_text"]: e for e in column_level_endpoints([grid])}
        full = by_location["A-1"]
        self.assertEqual((full["start_level"]["name"], full["stop_level"]["name"]), ("LEVEL 1", "LEVEL 3"))
        self.assertEqual(full["start_level"]["elevation_text"], '0"')
        self.assertEqual((full["status"], full["bands"], full["sections"]), ("complete", 2, ["W10X33", "W10X45"]))
        transfer = by_location["A-3"]
        self.assertEqual((transfer["start_level"]["name"], transfer["stop_level"]["name"]), ("LEVEL 2", "LEVEL 3"))
        self.assertEqual(by_location["A-4"]["status"], "open_end")
        self.assertIsNone(by_location["A-4"]["stop_level"])

    def test_a_missing_band_is_a_gap_not_a_run(self) -> None:
        l3, l2, l1, l0 = ("LEVEL 3", "28'-0\""), ("LEVEL 2", "14'-0\""), ("LEVEL 1", '0"'), ("LOWER", "-5'-0\"")
        grid = {
            "page": 42,
            "level_lines": [{"name": n, "elevation_text": e, "edge": i} for i, (n, e) in enumerate((l3, l2, l1, l0))],
            "rows": [self._row("B-1", l3, l2), self._row("B-1", l1, l0)],
        }
        (found,) = column_level_endpoints([grid])
        self.assertEqual(found["status"], "gap")

    def test_rows_without_a_level_span_have_no_endpoints(self) -> None:
        grid = {"page": 1, "level_lines": [], "rows": [{"mark": "A-1", "mark_role": "grid_location", "section": "W10X33"}]}
        self.assertEqual(column_level_endpoints([grid]), [])

    def test_no_schedule_levels_means_no_links(self) -> None:
        document = self._titled((11, "LEVEL 2 FRAMING PLAN"))
        self.assertEqual(link_level_names_to_plans(document, [{"page": 42}]), [])

    def test_conflicting_elevations_for_one_name_are_not_chosen(self) -> None:
        grids = self._GRIDS + [
            {"page": 44, "level_lines": [{"name": "LEVEL 2", "elevation_text": "15'-0\"", "edge": 2.0}]}
        ]
        (link,) = link_level_names_to_plans(self._titled((11, "LEVEL 2 FRAMING PLAN")), grids)
        self.assertEqual(link["status"], "conflicting_elevation")
        self.assertIsNone(link["elevation_text"])

    def test_tables_without_row_boxes_keep_the_spaced_datum_split(self) -> None:
        rows = [['14\' - 6" GROUND LEVEL', "W10X33"], _LOCATIONS[:2]]
        record = _transposed_record(_Table(rows), rows, 1, 29, [0, 0, 300, 100], self._words())
        (grid,) = _ruled_grids([record], _accept)
        row = grid["rows"][0]
        self.assertEqual(row["level_band"]["printed_name"], "GROUND LEVEL")
        self.assertEqual(row["level_band"]["printed_elevation"], '14\' - 6"')
        self.assertEqual(row["level_band"]["prefix_status"], "present")
        self.assertNotIn("level_span", row)
        self.assertNotIn("level_elevation_text", row)


if __name__ == "__main__":
    unittest.main()
