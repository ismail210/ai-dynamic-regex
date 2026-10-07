"""Drawing Summary evidence (OSSE review, October 2026): table-only column
locations, coverage counts, labels linked to their definitions, the
multi-source level review, boxed plan elevations, plan callouts, locating a
grid location on a plan, scope-aware model facts and grounding. Synthetic
inputs; the real drawings are checked in ``test_level_reference_set``."""

from __future__ import annotations

import copy
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
from services.engineering import column_trace as ct
from services.engineering.column_schedule import column_schedule_view
from services.engineering.drawing_intelligence import (
    _link_printed_labels,
    _representative_columns,
    evidence_packet,
    summary_facts,
)
from services.engineering.drawing_summary_llm import _claims_ok, _grounded, summarize
from services.engineering.level_review import (
    boxed_values,
    elevation_markers,
    level_review,
    plan_callouts,
)
from services.engineering.schedule_tables import (
    _title_above,
    read_display_tables,
    read_ruled_tables,
)


def _column(key, printed, page=26, supports=None):
    return {"key": key, "key_bbox": [0, 0, 10, 10], "key_repeats": [], "page": page,
            "sections": [{"printed": printed, "section": printed.upper()}], "plate_marks": [], "plates": [],
            "notes": [], "supplementary": {}, "suppressed_text": [], "bbox": [0, 0, 10, 10], "extent": None,
            **({"supports": supports} if supports else {})}


def _plate_row(mark, width, length, thickness):
    return {"mark": mark, "reference": None, "source_text": f"{mark} | {width} | {length} | {thickness}", "bbox": [0, 0, 1, 1],
            "dimensions": [{"label": "width", "raw": width}, {"label": "length", "raw": length},
                           {"label": "thickness", "raw": thickness}]}


def _osse_like_document():
    building = {"id": "S2", "title": "GRAPHICAL COLUMN SCHEDULE", "caption": "OSSE BUILDING - GCS", "key_role": "location",
                "layout": "graphical", "levels": [], "pages": [26], "blocks": [{"page": 26, "bbox": [0, 0, 100, 100]}],
                "notes": [], "suppressed_text": [], "level_lines": [],
                "entries": [_column("C.1-5.1", "W10x33"), _column("R14-RA.1", "W8x31"),
                            _column("C.8-8.9", "W10x33", supports=[{"printed": "P1 - 18 x 20", "mark": "P1",
                                                                    "label_band": None, "bbox": [1, 2, 3, 4]}])]}
    rows = [("C.1-5.1", "W10x33", "CBP-2"), ("C.8-8.9", "W10x33", "CBP-2"),
            ('C.1(-6")-7.3', "HSS3-1/2X3-1/2 X3/8", "CBP-1"),
            ("C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")", "HSS16X4X5/8", "CBP-3")]
    return {"column_schedules": {
        "schedules": [building],
        "location_tables": [{"title": "BASE PLATE SCHEDULE", "page": 25, "bbox": [0, 0, 50, 50], "rows": [
            {"location": loc, "section_text": sec, "plate_mark": plate, "source_text": f"{loc} | {sec} | {plate}",
             "bbox": [0, i, 50, i + 1]} for i, (loc, sec, plate) in enumerate(rows)]}],
        "plate_tables": [{"kind": "base plate", "title": "BASE PLATE TYPE SCHEDULE", "page": 25, "bbox": [0, 60, 50, 90],
                          "rows": [_plate_row("CBP-1", '12"', '12"', '3/4"'), _plate_row("CBP-2", '12"', '18"', '3/4"'),
                                   _plate_row("CBP-3", '16"', '18"', '1 1/4"'), _plate_row("CBP-5", '16"', '18"', '1 1/4"'),
                                   _plate_row("CBP-7", '12"', '12"', '1/2"')]}],
    }}


class TableOnlyLocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = column_schedule_view(_osse_like_document(), {25: "S601", 26: "S602"})

    def entry(self, location):
        return next(e for e in self.view["entries"] if e["location_text"] == location)

    def test_locations_only_a_table_lists_are_entries_of_their_own(self):
        table_only = [e for e in self.view["entries"] if e.get("assignment_only")]
        self.assertEqual([e["location_text"] for e in table_only],
                         ['C.1(-6")-7.3', "C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")"])
        schedule = next(s for s in self.view["schedules"] if s["id"] == "L1")
        self.assertEqual((schedule["source"], schedule["scope_schedule_id"]), ("location_table", "S2"))
        hss = self.entry('C.1(-6")-7.3')
        # The wrapped designation reads as one; the printed text is kept.
        self.assertEqual(hss["sections"], [{"designation": "HSS3-1/2X3-1/2X3/8", "printed": "HSS3-1/2X3-1/2 X3/8"}])
        self.assertEqual((hss["plate"]["printed"], hss["plate"]["status"]), ("CBP-1", "resolved"))
        self.assertIsNone(hss["extent"])
        self.assertIn("vertical extent is not established", hss["extent_note"])
        both = self.entry("C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")")["locations"][0]["grids"]
        self.assertEqual([(g["label"], g["offset"]["raw"]) for g in both], [("C.4", "1' - 7 3/8\""), ("7.5", "-2' - 4 1/2\"")])

    def test_counts_are_printed_records_and_the_table_reconciles(self):
        table = self.view["location_tables"][0]
        self.assertEqual((table["rows"], table["matched"], table["assignment_only"]), (4, {"S2": 2}, 2))
        building = next(s for s in self.view["schedules"] if s["id"] == "S2")
        self.assertEqual(building["coverage"]["entries"], 3)
        self.assertEqual(building["coverage"]["plates_linked"], 2)
        self.assertEqual(building["coverage"]["plates_not_shown"], 1)

    def test_a_plate_not_shown_says_where_it_was_looked_for(self):
        plate = self.entry("R14-RA.1")["plate"]
        self.assertEqual(plate["status"], "not_shown")
        self.assertIn("no row of BASE PLATE SCHEDULE (S601, 4 location rows) lists this location", plate["note"])

    def test_unused_marks_are_listed_and_equal_sizes_stay_distinct(self):
        plates = self.view["plate_tables"][0]
        self.assertEqual(plates["unused_marks"], ["CBP-5", "CBP-7"])
        self.assertEqual(self.entry("C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")")["plate"]["printed"], "CBP-3")

    def test_a_pier_label_links_to_its_schedule_row_and_a_size_difference_is_a_review_item(self):
        profile = {"column_schedule": self.view, "unresolved": [], "definitions": [{
            "mark": "P1", "page": 25, "sheet": "S601", "bbox": [5, 6, 7, 8], "schedule_title": "PIER SCHEDULE",
            "cells": [{"heading": "WIDTH", "path": ["SIZE", "WIDTH"], "text": '18"'},
                      {"heading": "LENGTH", "path": ["SIZE", "LENGTH"], "text": '24"'}]}],
            "supporting_schedules": [{"title": "PIER SCHEDULE", "kind": "pier", "page": 25, "sheet": "S601",
                                      "unread_rows": []}]}
        _link_printed_labels(profile)
        support = self.entry("C.8-8.9")["supports"][0]
        self.assertEqual((support["definition"]["mark"], support["definition"]["sizes"]), ("P1", "differ"))
        (item,) = profile["unresolved"]
        self.assertEqual(item["kind"], "support_label_differs")
        self.assertIn('width 18", length 24"', item["text"])
        self.assertIn("both are kept", item["text"])
        self.assertEqual(sorted(s["page"] for s in item["sources"]), [25, 26])


class FactSelectionTests(unittest.TestCase):
    def test_examples_stay_within_a_schedule_and_cover_kinds_of_evidence(self):
        view = column_schedule_view(_osse_like_document(), {25: "S601", 26: "S602"})
        chosen = _representative_columns(view)
        schedules = {e["schedule_id"] for _designation, _group, e in chosen}
        self.assertEqual(schedules, {"S2", "L1"})
        # Grouped within one schedule: a building group never pools table-only rows.
        for _designation, group, _entry in chosen:
            self.assertEqual(len({e["schedule_id"] for e in group}), 1)
        kinds = {e["plate"]["status"] for _d, _g, e in chosen}
        self.assertIn("not_shown", kinds)
        self.assertTrue(any(e.get("assignment_only") for _d, _g, e in chosen))

    def test_inventory_facts_give_complete_counts_and_the_packet_says_examples_are_examples(self):
        view = column_schedule_view(_osse_like_document(), {25: "S601", 26: "S602"})
        profile = {"column_schedule": view, "levels": {}, "definitions": [], "interpretation_rules": [],
                   "unresolved": [], "page_count": 26, "scope_signals": [], "steel_system": {"families": []},
                   "overview": "x"}
        profile["facts"] = summary_facts(profile)
        inventory = [f["text"] for f in profile["facts"] if f["type"] == "inventory"]
        self.assertTrue(any("3 printed location entries; 2 with a linked plate; 1 with no plate shown (R14-RA.1)" in t
                            for t in inventory))
        self.assertTrue(any("4 location rows; 2 are locations of OSSE BUILDING - GCS; 2 are in no column schedule" in t
                            for t in inventory))
        self.assertTrue(any("CBP-5, CBP-7 not assigned" in t for t in inventory))
        packet = evidence_packet(profile)
        self.assertIn("COVERAGE INVENTORY", packet)
        self.assertIn("NOT the complete inventory", packet)


class GroundingTests(unittest.TestCase):
    def test_a_disagreement_is_never_placed_inside_the_schedule(self):
        for text in ("The column schedule has conflicting elevations between levels.",
                     "There are conflicting values in the schedule for Level 2."):
            with self.subTest(text=text):
                self.assertFalse(_claims_ok(text, "", "X"))
        self.assertTrue(_claims_ok("The S122 plan note and the column schedule disagree on Level 2.", "", "X"))

    def test_the_real_model_output_on_osse_is_judged_by_content_not_form(self):
        # llama3.1:8b on the OSSE packet: ids echoed in brackets, a coverage
        # count named as such, and the overview's own "steel column schedule".
        facts = {"I1": "[I1] OSSE PARKING - GCS (S602 · PDF p. 26): 74 printed location entries; precast concrete C1",
                 "C1": "[C1] OSSE BUILDING - GCS (S602 · PDF p. 26): column at C.3-7.1 -> W10X49; base plate CBP-3"}
        evidence = "\n".join(facts.values()) + "\nOVERVIEW: steel column schedule on S602; location table on S601"
        provider = MagicMock()
        provider.propose.return_value = {
            "overview": "A structural set with a steel column schedule on S602 and a column location table on S601.",
            "key_facts": [{"id": "[I1]", "why": "Complete count of printed location entries for the parking schedule"},
                          {"id": "C1", "why": "Count of columns with this section to check against the plans"},
                          {"id": "[C1]", "why": "Shows which plate a W10X49 callout at C.3-7.1 carries"}],
            "cautions": [],
        }
        with patch("services.engineering.drawing_intelligence.evidence_facts", return_value=facts):
            result = summarize({"overview": "x"}, provider=provider, evidence_text=evidence)
        self.assertEqual([f["id"] for f in result.summary["key_facts"]], ["I1", "C1"])
        self.assertEqual(result.summary["overview_source"], "llm")
        self.assertIn("key_facts:C1", result.dropped_claims)  # a member count stays rejected
        self.assertFalse(_claims_ok("The C1 columns are steel columns.", "precast concrete C1", "M"))


class TitleAboveTests(unittest.TestCase):
    def test_a_title_continues_past_a_ruling_read_in_part(self):
        words = [(100, 80, 140, 90, "BASE"), (143, 80, 180, 90, "PLATE"), (183, 80, 240, 90, "SCHEDULE"),
                 (400, 80, 440, 90, "OTHER")]
        self.assertEqual(_title_above([90, 100, 200, 200], words), "BASE PLATE SCHEDULE")


def _ruled_pdf(path, title, header, body):
    document = fitz.open()
    page = document.new_page(width=800, height=600)
    rows = [header, *body]
    x0, y0, widths, row_h = 100.0, 120.0, [70.0, 90.0, 260.0], 20.0
    page.insert_text((x0, y0 - 8), title, fontsize=10)
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    for i in range(len(rows) + 1):
        page.draw_line((x0, y0 + i * row_h), (xs[-1], y0 + i * row_h))
    for x in xs:
        page.draw_line((x, y0), (x, y0 + len(rows) * row_h))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            page.insert_text((xs[c] + 4, y0 + r * row_h + 14), text, fontsize=8)
    document.save(str(path))
    document.close()
    with fitz.open(str(path)) as pdf:
        return [{"text": w[4], "bbox": list(w[:4]), "page_number": 1} for w in pdf[0].get_text("words")]


class DisplayTableTests(unittest.TestCase):
    def test_a_slab_schedule_is_read_for_display_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "slab.pdf"
            words = _ruled_pdf(pdf, "SLAB/DECK SCHEDULE", ["MARK", "TOTAL DEPTH", "COMPOSITION"],
                               [["S5.25", '5 1/4"', '3.25" CONCRETE ON 2" METAL DECK'], ["S12", '12"', "#6 @ 10\""]])
            production = read_ruled_tables(str(pdf), words)
            display = read_display_tables(str(pdf), words, production)
        self.assertEqual(production, [])
        (record,) = display
        self.assertTrue(record["display_only"])
        self.assertEqual(record["title"], "SLAB/DECK SCHEDULE")
        self.assertEqual([row["cells"][0] for row in record["body"]], ["S5.25", "S12"])


def _block(page, text, bbox):
    return {"page_number": page, "text": text, "bbox": bbox}


class LevelMarkerTests(unittest.TestCase):
    def document(self):
        return {"blocks": [
            _block(17, "T.O. SLAB LEVEL 2", [550, 287, 635, 297]), _block(17, "EL. 55' - 10\"", [584, 297, 636, 307]),
            _block(17, "1 SECTION", [174, 525, 287, 544]),
            _block(17, "T.O. SLAB", [1763, 312, 1808, 321]), _block(17, "EL. 55' - 10\"", [1756, 327, 1808, 336]),
            _block(17, "SEE SECTION 8/S-421-O FOR ASSUMED CONNECTIONS", [1708, 436, 1847, 489]),
            _block(17, "3 SECTION", [1081, 525, 1194, 544]),
            _block(12, "T.O. STEEL LEVEL 2 EL. 55' - 4 3/4\"", [826, 443, 900, 460]),
        ], "words": [
            {"page_number": 10, "text": "3", "bbox": [1410, 300, 1416, 310]},
            {"page_number": 10, "text": "S-421-O", "bbox": [1398, 312, 1434, 322]},
        ]}

    def test_markers_carry_their_value_surface_and_the_view_titled_under_them(self):
        markers = {(m["page"], m["name"]): m for m in elevation_markers(self.document(), {17: "S421", 12: "S221"})}
        slab2 = markers[(17, "T.O. SLAB LEVEL 2")]
        self.assertEqual((slab2["surface"], slab2["value"]["inches"], slab2["view"]["id"]), ("top of slab", 670.0, "1"))
        # The title under a marker, not a note that mentions a section.
        self.assertEqual(markers[(17, "T.O. SLAB")]["view"]["id"], "3")
        self.assertEqual(markers[(12, "T.O. STEEL LEVEL 2")]["value"]["inches"], 664.75)

    def test_callouts_name_the_view_and_sheet(self):
        self.assertEqual([(c["view"], c["sheet_ref"]) for c in plan_callouts(self.document(), 10)], [("3", "S-421-O")])


def _level2_review(markers, boxed=(), callouts=(), steps=(), others=None):
    level = {"name": "T.O. SLAB LEVEL 2", "schedule": "OSSE BUILDING - GCS", "schedule_id": "S2", "printed": "55' - 10\"",
             "elevation": {"inches": 670.0}, "surface": "top of slab", "page": 26, "sheet": "S602", "bbox": [1, 2, 3, 4]}
    match = {"page": 10, "sheet": "S122", "values": [{"raw": "55' - 2\"", "inches": 662.0, "surface": "top of slab",
                                                      "compared": True, "source": {"page": 10, "sheet": "S122", "bbox": [9, 9, 9, 9]}}]}
    rule = {"offset": {"raw": "<0' - 5 1/4\">", "inches": 5.25}, "source": {"page": 10, "sheet": "S122", "text": "TOP OF STEEL ..."}}
    return level_review(level, match, markers=markers, boxed=list(boxed), callouts=list(callouts), tags=[],
                        steps=list(steps), steel_rule=rule,
                        other_levels=others if others is not None else [{"level": "T.O. ROOF", "sheet": "S123", "comparison": "agrees"}])


class LevelReviewTests(unittest.TestCase):
    def markers(self):
        return elevation_markers(LevelMarkerTests().document(), {17: "S421", 12: "S221"})

    def test_every_printed_source_is_an_item_and_nothing_is_chosen(self):
        review = _level2_review(self.markers(),
                                boxed=[{"text": "55' - 10\"", "inches": 670.0, "box_bbox": [100, 100, 140, 112]}],
                                callouts=plan_callouts(LevelMarkerTests().document(), 10))
        self.assertEqual([i["role"] for i in review["items"]],
                         ["schedule", "general_note", "local_annotation", "section", "section_local"])
        self.assertTrue(review["headline"].startswith("Level 2 elevation requires review: the general datum note states 55'-2\""))
        self.assertIn("Their applicable areas have not been fully reconciled", review["headline"])
        local = next(i for i in review["items"] if i["role"] == "section_local")
        self.assertIn("a local condition", local["scope"])

    def test_the_printed_number_check_finds_the_steel_level_for_one_value_only(self):
        review = _level2_review(self.markers())
        checks = {c["slab"]: c for c in review["checks"]}
        self.assertEqual(checks["55'-10\""]["result"], "55'-4 3/4\"")
        self.assertEqual([p["sheet"] for p in checks["55'-10\""]["printed"]], ["S221"])
        self.assertEqual(checks["55'-2\""]["printed"], [])
        self.assertIn("does not establish which value governs",
                      next(e for e in review["explanations"] if e["id"] == "steel_check")["basis"])

    def test_explanations_need_printed_evidence_to_be_supported_or_ruled_out(self):
        review = _level2_review(self.markers())
        status = {e["id"]: e["status"] for e in review["explanations"]}
        self.assertEqual(status["surfaces"], "not_supported")
        self.assertEqual(status["datum"], "not_supported")
        self.assertEqual(status["local_elevations"], "unresolved")
        self.assertEqual(status["general_note_scope"], "unresolved")
        self.assertEqual(status["inconsistent"], "unresolved")
        stepped = _level2_review(self.markers(),
                                 boxed=[{"text": "55' - 10\"", "inches": 670.0, "box_bbox": [100, 100, 140, 112]}],
                                 steps=[{"text": "SLAB STEP", "bbox": [150, 100, 200, 110], "page": 10}])
        self.assertEqual({e["id"]: e["status"] for e in stepped["explanations"]}["local_elevations"], "supported")
        lone = _level2_review(self.markers(), others=[])
        self.assertEqual({e["id"]: e["status"] for e in lone["explanations"]}["datum"], "unresolved")


class BoxedValueTests(unittest.TestCase):
    def test_only_a_value_in_a_drawn_box_near_a_schedule_level_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.pdf"
            document = fitz.open()
            page = document.new_page(width=600, height=400)
            for text, at in (("55' - 10\"", (100, 100)), ("55' - 10\"", (300, 100)), ("14' - 10\"", (100, 300))):
                page.insert_text(at, text, fontsize=8)
            page.draw_rect(fitz.Rect(97, 90, 136, 104), width=0.5)
            page.draw_rect(fitz.Rect(97, 291, 140, 303), width=0.5)
            document.save(str(path))
            document.close()
            with fitz.open(str(path)) as pdf:
                lines = [{"page_number": 1, "text": " ".join(s["text"] for s in line["spans"]), "bbox": list(line["bbox"])}
                         for block in pdf[0].get_text("dict")["blocks"] for line in block.get("lines", [])]
            found = boxed_values({"lines": lines, "column_schedules": {"schedules": [
                {"level_lines": [{"elevation_text": "55' - 10\""}]}]}}, str(path))
        self.assertEqual([(v["text"], round(v["bbox"][0])) for v in found["1"]], [("55' - 10\"", 100)])


def _plan_pdf(path):
    """Grids A, A.1 (vertical) and 2 (horizontal); a column symbol on A.1 / 2."""

    document = fitz.open()
    page = document.new_page(width=800, height=600)
    for name, centre in (("A", (100, 50)), ("A.1", (160, 50)), ("2", (50, 300))):
        page.draw_circle(centre, 12, color=(0, 0, 0), width=0.5)
        page.insert_text((centre[0] - 6, centre[1] + 3), name, fontsize=7)
    for x in (100, 160):
        for y in range(62, 560, 20):
            page.draw_line((x, y), (x, y + 12), width=0.3)
    for x in range(62, 760, 20):
        page.draw_line((x, 300), (x + 12, 300), width=0.3)
    for a, b in (((155, 292), (165, 292)), ((160, 292), (160, 308)), ((155, 308), (165, 308))):
        page.draw_line(a, b, width=2.0)
    document.save(str(path))
    document.close()
    with fitz.open(str(path)) as pdf:
        page = pdf[0]
        words = [{"text": w[4], "bbox": list(w[:4]), "page_number": 1} for w in page.get_text("words")]
        lines = [{"page_number": 1, "text": " ".join(s["text"] for s in line["spans"]), "bbox": list(line["bbox"])}
                 for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])]
    return {"words": words, "lines": lines, "blocks": [], "page_count": 1,
            "pages": [{"page_number": 1, "width": 800, "height": 600, "rotation": 0}],
            "column_schedules": {"schedules": []}}


class LocateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pdf = Path(cls.tmp.name) / "plan.pdf"
        cls.context = ct.locate_context(_plan_pdf(cls.pdf), str(cls.pdf))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_decimal_grid_is_its_own_axis_not_an_offset(self):
        found = ct.locate_location(self.context, "A.1-2")
        self.assertEqual(found["status"], "column_symbol")
        (view,) = found["views"]
        self.assertEqual(view["state"], "column_symbol")
        x = (view["target_bbox"][0] + view["target_bbox"][2]) / 2
        self.assertAlmostEqual(x, 160, delta=6)

    def test_an_intersection_without_a_symbol_is_not_absence(self):
        found = ct.locate_location(self.context, "A-2")
        self.assertEqual(found["views"][0]["state"], "intersection_only")
        self.assertEqual(found["status"], "intersection_only")

    def test_missing_grids_and_offsets_without_scale_stay_unresolved(self):
        self.assertEqual(ct.locate_location(self.context, "B-2")["status"], "plan_not_found")
        offset = ct.locate_location(self.context, "A(1' - 0\")-2(6\")")
        self.assertEqual(offset["views"][0]["state"], "offset_unresolved")
        self.assertEqual(offset["views"][0]["offset"]["status"], "unresolved_scale")

    def test_page_geometry_is_read_once_per_page(self):
        ct.locate_location(self.context, "A-2")
        ct.locate_location(self.context, "A.1-2")
        self.assertEqual(list(self.context["geometry"]), [1])


if __name__ == "__main__":
    unittest.main()


class ReviewRegressionTests(unittest.TestCase):
    def test_inventory_wording_cannot_become_member_counts(self):
        evidence = "74 printed location entries; precast concrete C1"
        for text in ("Count of columns for the parking structure", "Number of members to order",
                     "Total of steel columns", "74 installed members", "999 printed location entries",
                     "C1 columns are steel columns"):
            self.assertIsNone(_grounded(text, evidence, 300, "I"), text)
        self.assertIsNotNone(_grounded("Count of printed location entries for the parking schedule", evidence, 300, "I"))

    def test_two_offsets_measure_perpendicularly_to_skew_grids(self):
        axes = {"A": {"angle": 0}, "2": {"angle": math.pi / 3}}
        offsets = {"A": {"inches": 10}, "2": {"inches": 20}}
        points = []
        def observe(x, y, *_args):
            points.append((x, y))
            return {"point_bbox": [x, y, x, y], "symbol": None, "annotations": []}
        with patch.object(ct, "_observe", side_effect=observe):
            ct._place_two_offsets(((0, 0), axes), offsets,
                                  {"points_per_inch": 1, "status": "calibrated"},
                                  {"lines": [], "drawings": [], "segments": []})
        self.assertEqual(len(points), 4)
        for x, y in points:
            for grid, distance in (("A", 10), ("2", 20)):
                nx, ny = ct._normal(axes[grid]["angle"])
                self.assertAlmostEqual(abs(nx * x + ny * y), distance)

    def test_crop_rotation_bounds_and_invalid_coordinates(self):
        from services.pdf_pages import render_page_crop
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rotated.pdf"
            with fitz.open() as pdf:
                page = pdf.new_page(width=200, height=300)
                page.draw_rect((10, 20, 50, 60), color=(1, 0, 0), fill=(1, 0, 0))
                page.set_rotation(90)
                bounds = tuple(fitz.Rect(10, 20, 50, 60) * page.rotation_matrix)
                pdf.save(path)
            pix = fitz.Pixmap(render_page_crop(path, 1, bounds, 400))
            self.assertEqual((pix.width, pix.height), (400, 400))
            self.assertEqual(pix.pixel(200, 200)[:3], (255, 0, 0))
            tall = fitz.Pixmap(render_page_crop(path, 1, (10, 0, 14, 200), 1200))
            self.assertLessEqual(tall.height, 1200)
            for bounds in ((0, 0, float("nan"), 100), (0, 0, float("inf"), 100), (0, 0, 1, 1)):
                with self.assertRaises(ValueError):
                    render_page_crop(path, 1, bounds)
            with self.assertRaises(IndexError):
                render_page_crop(path, 2, (0, 0, 100, 100))


class ScopeReviewTests(unittest.TestCase):
    def test_assignment_scope_is_not_chosen_by_majority_or_last_matching_schedule(self):
        document = _osse_like_document()
        schedules = document["column_schedules"]["schedules"]
        other = copy.deepcopy(schedules[0])
        other.update(id="S3", caption="OTHER BUILDING - GCS")
        other["entries"] = other["entries"][:1]
        schedules.append(other)
        view = column_schedule_view(document, {25: "S601", 26: "S602"})
        table = view["location_tables"][0]
        self.assertEqual(table["matched"], {"S2": 2, "S3": 1})
        self.assertIsNone(table["scope_schedule_id"])
        self.assertIsNone(next(s for s in view["schedules"] if s["id"] == "L1")["scope_schedule_id"])


class LocateApiAccessTests(unittest.TestCase):
    def test_locate_and_crop_require_access_and_registered_documents(self):
        from dataclasses import replace

        from app import app
        from config import settings
        from fastapi.testclient import TestClient
        client = TestClient(app)
        paths = ["/api/documents/missing/locate?location=A-2",
                 "/api/documents/missing/page-crop?page=1&x0=0&y0=0&x1=20&y1=20"]
        with patch("app.settings", replace(settings, api_access_token="test-only-access-key")):
            for path in paths:
                self.assertEqual(client.get(path).status_code, 401)
                with patch("routers.documents.document_source", side_effect=FileNotFoundError("Document not found")):
                    self.assertEqual(client.get(path, headers={"Authorization": "Bearer test-only-access-key"}).status_code, 404)


class ConcreteDefinitionSizeTests(unittest.TestCase):
    def test_tie_size_and_spacing_are_not_concrete_section_dimensions(self):
        entry = {"sections": [{"printed": 'RC1 - 24" x 24"'}]}
        profile = {"column_schedule": {"entries": [entry]}, "unresolved": [], "definitions": [],
                   "supporting_schedules": [{"title": "CONCRETE SCHEDULE", "page": 25, "kind": "concrete",
                    "unread_rows": [{"printed_mark": 'RC1 - 24" x 24"', "bbox": [1, 2, 3, 4], "cells": [
                        {"heading": "WIDTH", "path": ["SIZE", "WIDTH"], "text": '24"'},
                        {"heading": "LENGTH", "path": ["SIZE", "LENGTH"], "text": '24"'},
                        {"heading": "SIZE & SPACING OF TIES", "text": '#3@12" O.C.'}]}]}]}
        _link_printed_labels(profile)
        self.assertEqual(entry["definition"]["sizes"], "agree")
