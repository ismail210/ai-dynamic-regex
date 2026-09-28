"""Ruled schedule tables: find_tables reader, kinds from titles, Revit grids, cross-check."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from services.engineering.schedule_grid import (
    _ruled_grids,
    build_document_schedule_grids,
    lookup_schedule_row,
    schedule_kind_from_title,
    schedule_mark_crosscheck,
    schedule_mark_map,
)
from services.engineering.schedule_tables import read_ruled_tables


_SECTIONS = {"W8X24", "W8X31", "W10X33", "W12X65", "HSS6X6X1/2", "W16X36"}


def _accept(token: str) -> bool:
    return token.upper() in _SECTIONS


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


if __name__ == "__main__":
    unittest.main()
