"""Column tracing pilot: grid bubbles and axes, column symbol, leaders, and
honest endpoint states. Synthetic plan pages; the real traces are checked in
``test_level_reference_set``."""

from __future__ import annotations

import unittest

import fitz

from services.engineering import column_trace as ct


def _plan(symbol=True, second_axis=False):
    document = fitz.open()
    page = document.new_page(width=800, height=600)
    for name, centre in (("A", (100, 50)), ("2", (50, 300))):
        page.draw_circle(centre, 12, color=(0, 0, 0), width=0.5)
        page.insert_text((centre[0] - 3, centre[1] + 3), name, fontsize=9)
    for y in range(62, 560, 20):                        # dash-dot grid line A
        page.draw_line((100, y), (100, y + 12), width=0.3)
    for x in range(62, 760, 20):                        # grid line 2
        page.draw_line((x, 300), (x + 12, 300), width=0.3)
    if second_axis:                                     # grid A again, on a partial plan
        page.draw_circle((600, 100), 12, color=(0, 0, 0), width=0.5)
        page.insert_text((597, 103), "A", fontsize=9)
        for y in range(112, 560, 20):
            page.draw_line((600, y), (600, y + 12), width=0.3)
        for x in range(500, 760, 20):
            page.draw_line((x, 300), (x + 12, 300), width=0.3)
    if symbol:                                          # heavy I-shape on A / 2
        for a, b in (((95, 292), (105, 292)), ((100, 292), (100, 308)), ((95, 308), (105, 308))):
            page.draw_line(a, b, width=2.0)
    page.draw_line((104, 304), (160, 360), width=0.3)   # leader with a knee
    page.draw_line((160, 360), (200, 360), width=0.3)
    page.insert_text((203, 364), "POST UP", fontsize=8)
    page.insert_text((110, 287), "W14X22", fontsize=6)
    page.insert_text((400, 500), "COLUMN BELOW", fontsize=8)   # far away, no leader
    words = page.get_text("words")
    drawings = page.get_drawings()
    lines = [{"page_number": 1, "text": " ".join(s["text"] for s in line["spans"]), "bbox": list(line["bbox"])}
             for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])]
    return words, drawings, lines


class GridTests(unittest.TestCase):
    def test_grid_axes_come_from_labelled_bubbles(self):
        words, drawings, _ = _plan()
        segments = ct._segment_index(ct._segments(drawings))
        a = ct._axes(ct._bubbles(words, ct._circles(drawings), "A"), segments)
        two = ct._axes(ct._bubbles(words, ct._circles(drawings), "2"), segments)
        self.assertEqual([(x["orientation"], round(x["at"])) for x in a], [("vertical", 100)])
        self.assertEqual([(x["orientation"], round(x["at"])) for x in two], [("horizontal", 300)])

    def test_a_grid_on_two_axes_gives_two_candidates(self):
        words, drawings, _ = _plan(second_axis=True)
        axes = ct._axes(ct._bubbles(words, ct._circles(drawings), "A"), ct._segment_index(ct._segments(drawings)))
        self.assertEqual(sorted(round(x["at"]) for x in axes), [100, 600])


class ObservationTests(unittest.TestCase):
    def observe(self, **kw):
        words, drawings, lines = _plan(**kw)
        return ct._observe(100, 300, lines, drawings, ct._segments(drawings), {"W8X24"})

    def test_column_symbol_and_leader_annotation(self):
        seen = self.observe()
        self.assertIsNotNone(seen["symbol"])
        self.assertEqual([(a["text"], a["how"]) for a in seen["annotations"]],
                         [("POST UP", "leader ends at the column")])
        # Text at the column that is not an annotation stays nearby; far text is not associated.
        self.assertIn("W14X22", [n["text"] for n in seen["nearby_text"]])
        self.assertNotIn("COLUMN BELOW", [a["text"] for a in seen["annotations"]])

    def test_no_symbol_is_not_detected_not_absent(self):
        self.assertIsNone(self.observe(symbol=False)["symbol"])


class EndpointTests(unittest.TestCase):
    def lines(self):
        return [{"page": 13, "block": 1, "y": y, "name": n, "elevation_text": e}
                for y, n, e in ((100.0, "3 ROOF", "30' - 8\""), (240.0, "2 SECOND FLOOR", "15' - 4\""),
                                (330.0, "1 FOUNDATION", "0' - 0\""))]

    def test_ends_on_level_lines_are_established_by_the_schedule(self):
        entry = {"page": 13, "extent": {"top": {"position": "at", "y": 100.0, "line": self.lines()[0]},
                                        "bottom": {"position": "at", "y": 240.0, "line": self.lines()[1]}}}
        spanned, ends, _ = ct._spanned(entry, self.lines())
        self.assertEqual([l["name"] for l in spanned], ["3 ROOF", "2 SECOND FLOOR"])
        self.assertEqual((ends["top"]["state"], ends["bottom"]["level"]), ("established", "2 SECOND FLOOR"))

    def test_an_end_between_lines_is_not_moved_to_a_line(self):
        entry = {"page": 13, "extent": {"top": {"position": "between", "y": 120.0},
                                        "bottom": {"position": "below", "y": 340.0}}}
        spanned, ends, _ = ct._spanned(entry, self.lines())
        self.assertEqual(ends["top"]["state"], "unresolved")
        self.assertIn("not moved to the nearest line", ends["bottom"]["note"])
        self.assertEqual([l["name"] for l in spanned], ["2 SECOND FLOOR", "1 FOUNDATION"])

    def test_plan_matching_by_name_and_by_stated_elevation(self):
        level = {"name": "T.O. ROOF", "elevation_text": "69' - 4\""}
        names = {10: ["SECOND FLOOR PLAN"], 11: ["OSSE FACILITY ROOF PLAN"]}
        elevations = [{"page": 11, "status": "read", "name": "OFFICE ROOF", "plan": None,
                       "value": {"inches": 69 * 12 + 4}}]
        (plan,) = ct._plan_pages(level, names, elevations, schedule_pages={26}, block_levels=[level])
        self.assertEqual(plan["page"], 11)
        self.assertIn("same elevation", plan["matched_by"])
        # The same note at another elevation is not a match.
        elevations[0]["value"]["inches"] = 55 * 12 + 2
        self.assertEqual(ct._plan_pages(level, names, elevations, {26}, [level]), [])


if __name__ == "__main__":
    unittest.main()
