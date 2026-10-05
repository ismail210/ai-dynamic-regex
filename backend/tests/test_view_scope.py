"""Building / area scope of plan views for the column-tracing pilot
(``view_scope``). Shapes follow OSSE - ST.pdf: an OSSE BUILDING and an OSSE
PARKING graphical schedule on S-602-O, plans titled "OSSE FACILITY ..." and
"OSSE PARKING ..."."""

from __future__ import annotations

import unittest

from services.engineering.view_scope import ScopeResolver, scope_terms, sheet_titles


def _line(page, text, bbox, size=12.6):
    return {"page_number": page, "text": text, "bbox": list(bbox), "font_size": size}


def _document(lines, levels=None):
    levels = levels or {"S1": [("T.O. PARKING DECK SLAB", "50' - 0\"")],
                        "S2": [("T.O. ROOF", "69' - 4\""), ("T.O. SLAB LEVEL 1", "38' - 0\"")]}
    return {
        "pages": [{"page_number": p, "width": 3024.0, "height": 2160.0, "rotation": 0} for p in range(1, 30)],
        "lines": lines,
        "column_schedules": {"schedules": [
            {"id": "S1", "caption": "OSSE PARKING - GCS", "title": "GRAPHICAL COLUMN SCHEDULE",
             "level_lines": [{"name": n, "elevation_text": e} for n, e in levels["S1"]]},
            {"id": "S2", "caption": "OSSE BUILDING - GCS", "title": "GRAPHICAL COLUMN SCHEDULE",
             "level_lines": [{"name": n, "elevation_text": e} for n, e in levels["S2"]]},
        ]},
    }


def _title_block(page, *title_lines):
    lines = [_line(page, "Title:", (2543, 2005, 2557, 2011), 6.6)]
    for i, text in enumerate(title_lines):
        lines.append(_line(page, text, (2565, 2002 + 14 * i, 2745, 2015 + 14 * i)))
    return lines


def _read(page, name, inches, display):
    return {"page": page, "status": "read", "name": name, "value": {"inches": inches, "display": display},
            "source": {"page": page, "text": f"{name} {display}"}}


POINT = [2170, 1487, 2177, 1493]


class ScopeTests(unittest.TestCase):
    def test_scope_words_drop_view_and_level_words(self):
        self.assertEqual(scope_terms("OSSE PARKING FOUNDATION AND FIRST FLOOR PLAN"), {"OSSE", "PARKING"})
        self.assertEqual(scope_terms("OSSE BUILDING - GCS"), {"OSSE", "BUILDING"})

    def test_title_block_title_is_read_next_to_its_label(self):
        doc = _document(_title_block(9, "OSSE FACILITY FOUNDATION", "AND FIRST FLOOR PLAN")
                        + [_line(9, "KMM", (2609, 1982, 2632, 1991), 9.6)])
        self.assertEqual(sheet_titles(doc)[9]["text"], "OSSE FACILITY FOUNDATION AND FIRST FLOOR PLAN")

    def test_another_buildings_view_is_conflicting(self):
        doc = _document(_title_block(5, "OSSE PARKING FOUNDATION", "AND FIRST FLOOR PLAN"))
        scope = ScopeResolver(doc, []).scope("S2", 5, POINT)
        self.assertEqual(scope["status"], "conflicting")       # same "FIRST FLOOR", other building
        self.assertEqual(ScopeResolver(doc, []).scope("S1", 5, POINT)["status"], "consistent")

    def test_a_shared_project_name_alone_is_not_scope(self):
        doc = _document(_title_block(10, "OSSE FACILITY SECOND", "FLOOR PLAN"))
        self.assertEqual(ScopeResolver(doc, []).scope("S2", 10, POINT)["status"], "unresolved")

    def test_datum_ties_a_view_to_one_schedule_and_its_sheet_family(self):
        lines = (_title_block(9, "OSSE FACILITY FOUNDATION", "AND FIRST FLOOR PLAN")
                 + _title_block(10, "OSSE FACILITY SECOND", "FLOOR PLAN"))
        scopes = ScopeResolver(_document(lines), [_read(9, "FIRST FLOOR", 38 * 12, "38'-0\"")])
        self.assertEqual(scopes.scope("S2", 9, POINT)["status"], "supported_by_datum")
        self.assertEqual(scopes.scope("S2", 10, POINT)["status"], "consistent_by_sheet_family")
        self.assertEqual(scopes.scope("S1", 10, POINT)["status"], "unresolved")

    def test_an_elevation_both_schedules_share_proves_nothing(self):
        levels = {"S1": [("T.O. PARKING LOWER DECK", "33' - 0\"")], "S2": [("T.O. PARKING LOWER DECK", "33' - 0\"")]}
        doc = _document(_title_block(9, "OSSE FACILITY FOUNDATION", "AND FIRST FLOOR PLAN"), levels)
        scopes = ScopeResolver(doc, [_read(9, "LOWER DECK", 33 * 12, "33'-0\"")])
        self.assertEqual(scopes.scope("S2", 9, POINT)["status"], "unresolved")

    def test_each_view_on_a_sheet_has_its_own_scope(self):
        # One sheet, two views: titles printed under each view (display space).
        lines = (_title_block(7, "OSSE PARKING FOUNDATION", "& SOUTH STAIR - PART PLAN")
                 + [_line(7, "OSSE PARKING FOUNDATION PLAN", (260, 1862, 588, 1881), 19.1),
                    _line(7, "OSSE BUILDING FOUNDATION PLAN", (1600, 1862, 1990, 1881), 19.1)])
        scopes = ScopeResolver(_document(lines), [])
        self.assertEqual(scopes.scope("S2", 7, [400, 900, 406, 906])["status"], "conflicting")
        self.assertEqual(scopes.scope("S2", 7, [1700, 900, 1706, 906])["status"], "consistent")

    def test_one_schedule_in_the_set_is_not_compared(self):
        doc = _document(_title_block(5, "SECOND FLOOR PLAN"))
        doc["column_schedules"]["schedules"] = doc["column_schedules"]["schedules"][:1]
        self.assertEqual(ScopeResolver(doc, []).scope("S1", 5, POINT)["status"], "single_schedule")


if __name__ == "__main__":
    unittest.main()
