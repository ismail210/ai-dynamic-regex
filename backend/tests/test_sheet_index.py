"""Sheet index: sheet number / title / issue / revisions / scale from the title block."""

from __future__ import annotations

import unittest

from services.engineering.page_space import to_pdf
from services.engineering.sheet_index import sheet_index

W, H = 1000.0, 700.0


def _boilerplate():
    return [
        ("PROJECT TITLE:", (905, 420, 960, 428), 6),
        ("ACME TOWER", (905, 432, 980, 444), 10),
        ("DRAWING TITLE:", (905, 560, 960, 566), 5),
        ("BID SET", (905, 672, 940, 678), 6),
        ("11/14/2022", (905, 684, 945, 690), 6),
    ]


def _sheet(sheet_id, title_lines, *, scale="As indicated", extra=(), boilerplate=True, title_label=True):
    lines = list(_boilerplate()) if boilerplate else []
    if not title_label:
        lines = [l for l in lines if l[0] != "DRAWING TITLE:"]
    y = 570
    for text in title_lines:
        lines.append((text, (905, y, 990, y + 10), 10))
        y += 12
    if scale is not None:
        lines += [("SCALE:", (905, 620, 925, 626), 5), (scale, (930, 620, 965, 626), 5)]
    lines.append((sheet_id, (920, 640, 980, 665), 22))
    return lines + list(extra)


def _document(sheets, *, rotation=0):
    pages, lines = [], []
    for number, sheet in enumerate(sheets, start=1):
        pages.append({"page_number": number, "width": W, "height": H, "rotation": rotation})
        for text, box, size in sheet:
            lines.append({
                "page_number": number, "text": text, "font_size": size,
                "bbox": to_pdf(rotation, W, H, box),
                "rotation": -rotation if rotation in (90, 270) else 0.0,
            })
    return {"pages": pages, "lines": lines}


def _set(*sheets, rotation=0):
    return sheet_index(_document(sheets, rotation=rotation))["pages"]


class SheetIdTests(unittest.TestCase):
    def test_normal_structural_sheet(self):
        pages = _set(_sheet("S101", ["SECOND FLOOR", "FRAMING PLAN"]), _sheet("S102", ["ROOF FRAMING PLAN"]),
                     _sheet("S201", ["TYPICAL DETAILS"]))
        self.assertEqual([p["sheet_id"] for p in pages], ["S101", "S102", "S201"])
        self.assertEqual(pages[0]["sheet_id_status"], "read")
        self.assertEqual(pages[0]["sheet_title"], "SECOND FLOOR FRAMING PLAN")
        self.assertEqual(pages[0]["source_bbox"], [920.0, 640.0, 980.0, 665.0])

    def test_alphanumeric_dotted_and_hyphenated_ids_are_kept_as_printed(self):
        pages = _set(_sheet("S101A", ["PLAN A"]), _sheet("S2.01", ["PLAN B"]), _sheet("S-122-O", ["PLAN C"]))
        self.assertEqual([p["sheet_id"] for p in pages], ["S101A", "S2.01", "S-122-O"])

    def test_rotated_pages_are_read_as_displayed(self):
        pages = _set(_sheet("S2.01", ["PARTIAL FLOOR AND", "ROOF FRAMING PLAN", "- AREA A"]),
                     _sheet("S2.02", ["SECTIONS"]), _sheet("S2.03", ["DETAILS"]), rotation=90)
        self.assertEqual(pages[0]["rotation"], 90)
        self.assertEqual([p["sheet_id"] for p in pages], ["S2.01", "S2.02", "S2.03"])
        self.assertEqual(pages[0]["sheet_title"], "PARTIAL FLOOR AND ROOF FRAMING PLAN - AREA A")
        self.assertEqual(pages[0]["source_bbox"], [920.0, 640.0, 980.0, 665.0])

    def test_detail_references_and_callout_sheet_numbers_are_not_the_sheet_id(self):
        callouts = [
            ("S-221-O", (760, 300, 790, 308), 7), ("4/S-401-O", (720, 640, 770, 648), 7),
            ("S-421-O", (950, 200, 975, 208), 7), ("12", (980, 120, 990, 130), 9),
        ]
        pages = _set(_sheet("S-122-O", ["SECOND FLOOR PLAN"], extra=callouts),
                     _sheet("S-123-O", ["ROOF PLAN"], extra=callouts), _sheet("S-124-O", ["DETAILS"]))
        self.assertEqual([p["sheet_id"] for p in pages], ["S-122-O", "S-123-O", "S-124-O"])

    def test_largest_sheet_number_on_the_page_is_not_assumed_to_be_the_sheet_id(self):
        decoy = [("S-501", (720, 100, 860, 160), 60)]
        pages = _set(_sheet("S101", ["PLAN"], extra=decoy), _sheet("S102", ["PLAN 2"]), _sheet("S103", ["PLAN 3"]))
        self.assertEqual(pages[0]["sheet_id"], "S101")

    def test_page_without_a_sheet_number_in_the_slot_is_unresolved_with_candidates(self):
        stray = [("S-501", (720, 100, 760, 110), 8)]
        sheets = [_sheet("S101", ["PLAN"]), _sheet("S102", ["PLAN 2"]),
                  [l for l in _sheet("S103", ["PLAN 3"], extra=stray) if l[0] != "S103"]]
        page = _set(*sheets)[2]
        self.assertIsNone(page["sheet_id"])
        self.assertEqual(page["sheet_id_status"], "unresolved")
        self.assertEqual([c["text"] for c in page["sheet_id_candidates"]], ["S-501"])


class TitleTests(unittest.TestCase):
    def test_viewport_titles_are_not_the_sheet_title(self):
        views = [("SECTION A", (100, 600, 180, 612), 12), ("SCALE: 1/4\" = 1'-0\"", (100, 614, 180, 620), 6),
                 ("TYPICAL BEAM TO COLUMN CONNECTION", (300, 600, 500, 612), 12)]
        pages = _set(_sheet("S501", ["FRAMING SECTIONS"], scale=None, extra=views),
                     _sheet("S502", ["DETAILS"], scale=None), _sheet("S503", ["MORE DETAILS"], scale=None))
        self.assertEqual(pages[0]["sheet_title"], "FRAMING SECTIONS")
        self.assertEqual(pages[0]["title_status"], "read")
        self.assertIsNone(pages[0]["scale"])
        self.assertEqual(pages[0]["scale_status"], "not_shown")

    def test_title_stops_at_the_next_label(self):
        page = _set(_sheet("S101B", ["FOUNDATION AND", "1ST FLOOR", "FRAMING PLAN", "PART B"]),
                    _sheet("S102", ["X PLAN"]), _sheet("S103", ["Y PLAN"]))[0]
        self.assertEqual(page["sheet_title"], "FOUNDATION AND 1ST FLOOR FRAMING PLAN PART B")

    def test_unlabeled_title_is_the_sheet_specific_text_and_says_so(self):
        pages = _set(_sheet("S001", ["GENERAL NOTES"], title_label=False),
                     _sheet("S002", ["INSPECTION TABLES"], title_label=False),
                     _sheet("S003", ["FOUNDATION PLAN"], title_label=False))
        self.assertEqual(pages[0]["sheet_title"], "GENERAL NOTES")
        self.assertEqual(pages[0]["title_status"], "read_unlabeled")
        self.assertNotIn("ACME TOWER", [c["text"] for c in pages[0]["title_candidates"]])

    def test_two_equal_unlabeled_candidates_stay_ambiguous(self):
        pages = _set(_sheet("S001", ["GENERAL NOTES", "SPECIAL INSPECTIONS"], title_label=False),
                     _sheet("S002", ["INSPECTION TABLES"], title_label=False),
                     _sheet("S003", ["FOUNDATION PLAN"], title_label=False))
        self.assertIsNone(pages[0]["sheet_title"])
        self.assertEqual(pages[0]["title_status"], "ambiguous")
        self.assertEqual(len(pages[0]["title_candidates"]), 2)


class IssueRevisionScaleTests(unittest.TestCase):
    def test_issue_date_is_the_one_beside_the_issue_text_not_any_date(self):
        others = [
            ("10/12/2019", (930, 450, 970, 456), 6),            # seal / stamp date
            ("3/17/2025 9:26:43 AM", (905, 693, 980, 699), 6),  # plot timestamp
            ("NO.", (905, 20, 915, 26), 5), ("DESCRIPTION", (925, 20, 965, 26), 5), ("DATE", (970, 20, 990, 26), 5),
            ("1", (907, 30, 910, 36), 5), ("ADDENDUM", (925, 30, 960, 36), 5), ("11/29/2023", (968, 30, 995, 36), 5),
        ]
        pages = _set(_sheet("S101", ["PLAN"], extra=others), _sheet("S102", ["PLAN 2"]), _sheet("S103", ["PLAN 3"]))
        page = pages[0]
        self.assertEqual((page["issue"], page["issue_date"], page["issue_status"]), ("BID SET", "11/14/2022", "read"))
        self.assertEqual(page["revision"]["status"], "read")
        self.assertEqual([(r["number"], r["description"], r["date"]) for r in page["revision"]["rows"]],
                         [("1", "ADDENDUM", "11/29/2023")])

    def test_labeled_date_field_wins_over_other_dates(self):
        extra = [("DATE:", (905, 600, 925, 606), 5), ("03/20/25", (930, 600, 960, 606), 5)]
        sheets = [[l for l in _sheet(s, ["PLAN"], extra=extra) if l[0] not in ("BID SET", "11/14/2022")]
                  for s in ("S2.01", "S2.02", "S2.03")]
        page = _set(*sheets)[0]
        self.assertEqual((page["issue"], page["issue_date"]), (None, "03/20/25"))

    def test_empty_revision_table_is_none_printed(self):
        header = [("NO.", (905, 20, 915, 26), 5), ("DESCRIPTION", (925, 20, 965, 26), 5), ("DATE", (970, 20, 990, 26), 5)]
        page = _set(_sheet("S101", ["PLAN"], extra=header), _sheet("S102", ["P2"]), _sheet("S103", ["P3"]))[0]
        self.assertEqual(page["revision"], {"status": "none_printed", "rows": []})

    def test_scale_field_and_a_different_graphic_caption(self):
        caption = [("SCALE : 1/8\" = 1'-0\"", (930, 600, 990, 606), 5)]
        page = _set(_sheet("S101", ["PLAN"], scale="1\" = 30'-0\"", extra=caption),
                    _sheet("S102", ["P2"]), _sheet("S103", ["P3"]))[0]
        self.assertEqual((page["scale"], page["scale_status"]), ("1\" = 30'-0\"", "read"))
        self.assertIn({"text": "1/8\" = 1'-0\"", "form": "caption"}, page["scale_candidates"])

    def test_sheet_number_on_the_scale_row_is_not_the_scale(self):
        sheet = [l for l in _sheet("S-104", ["PLAN"], scale=None)]
        sheet += [("DRAWING SCALE", (905, 645, 930, 651), 5)]
        pages = _set(sheet, _sheet("S-105", ["P2"], scale=None), _sheet("S-106", ["P3"], scale=None))
        self.assertIsNone(pages[0]["scale"])

    def test_empty_document(self):
        self.assertEqual(sheet_index({})["pages"], [])


if __name__ == "__main__":
    unittest.main()
