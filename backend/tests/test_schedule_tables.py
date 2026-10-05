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
from services.engineering.schedule_tables import _transposed_record, read_ruled_tables


_SECTIONS = {"W8X24", "W8X31", "W10X33", "W12X65", "HSS6X6X1/2", "W16X36"}


def _accept(token: str) -> bool:
    return token.upper() in _SECTIONS


def _placed(items, page=2):
    return [
        {"text": text, "bbox": [x, y, x + 40, y + 8], "page_number": page}
        for text, x, y in items
    ]


def _rows_record(title, header, body, page=2):
    return {
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


if __name__ == "__main__":
    unittest.main()
