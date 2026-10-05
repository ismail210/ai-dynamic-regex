"""Levels and elevations: parsing, plan notes, schedule level lines.

Strings are copied from real sheets (file / page / sheet in each comment);
expected values were read from the rendered drawing.
"""

from __future__ import annotations

import unittest

from services.engineering.level_evidence import format_elevation, is_see_plan, parse_elevation


class ParseElevationTests(unittest.TestCase):
    def test_feet_inches_with_mixed_fraction_stays_one_value(self):
        # OSSE - ST.pdf p26 S-602-O: T.O. SLAB LOW RAMP 41' - 9 5/8"
        e = parse_elevation("41' - 9 5/8\"")
        self.assertEqual(e["inches"], 41 * 12 + 9.625)
        self.assertEqual(e["unit"], "ft-in")

    def test_decimal_feet(self):
        # Furley Struct.pdf p11 S103A: (28.66') top of steel per roof note 3
        e = parse_elevation("(28.66')")
        self.assertAlmostEqual(e["inches"], 28.66 * 12)
        self.assertEqual(e["unit"], "decimal-ft")
        self.assertEqual(e["enclosure"], "(")

    def test_parentheses_are_not_a_minus_sign(self):
        # Brandywine Structural4.pdf p11: TOP OF STEEL BEAM ELEVATION IS (+13'-6 3/4")
        e = parse_elevation("(+13'-6 3/4\")")
        self.assertEqual(e["inches"], 13 * 12 + 6.75)
        self.assertEqual((e["sign"], e["enclosure"]), ("+", "("))
        self.assertGreater(parse_elevation("(13.00')")["inches"], 0)

    def test_explicit_negative_sign(self):
        # Washington Latin p10 S-102: T/STEEL ELEVATION = (-6-1/4") ...; Brandywine p42: -5'-0"
        self.assertEqual(parse_elevation("(-6-1/4\")")["inches"], -6.25)
        self.assertEqual(parse_elevation("-5'-0\"")["inches"], -60.0)
        self.assertEqual(parse_elevation("-5'-0\"")["sign"], "-")

    def test_other_enclosures_are_kept(self):
        # OSSE p10 S-103-O: <0' - 5 1/4">
        e = parse_elevation("<0' - 5 1/4\">")
        self.assertEqual((e["inches"], e["enclosure"], e["sign"]), (5.25, "<", None))

    def test_things_that_are_not_elevations(self):
        for text in ("A.1'-18", "H.4'-5.8'", "W16x26", "(36)", "25K", "#3@12\"", "D/S-201",
                     "1'-0\"x1'-0\"", "S-602-O", "(L4)", "[14]", "8.1'"):
            self.assertIsNone(parse_elevation(text), text)

    def test_zero_and_inches_only(self):
        self.assertEqual(parse_elevation("0\"")["inches"], 0.0)
        self.assertEqual(parse_elevation("0'-0\"")["inches"], 0.0)

    def test_see_plan(self):
        self.assertTrue(is_see_plan("SEE PLAN"))
        self.assertFalse(is_see_plan("SECOND FLOOR"))


class FormatElevationTests(unittest.TestCase):
    def test_round_trip(self):
        for inches, text in ((14 * 12 + 3, "14'-3\""), (329 * 12 + 5.75, "329'-5 3/4\""),
                             (-5.25, "-0'-5 1/4\""), (0, "0'-0\""), (0.5, "0'-0 1/2\""), (343 * 12 + 0.75, "343'-0 3/4\"")):
            self.assertEqual(format_elevation(inches), text)


def _doc(blocks, lines=(), rotation=0, schedules=()):
    """A minimal extracted document: one block / line per (page, text, bbox)."""

    pages = sorted({b[0] for b in blocks} | {l[0] for l in lines} | {1})
    return {
        "pages": [{"page_number": p, "width": 3024.0, "height": 2160.0, "rotation": rotation} for p in pages],
        "blocks": [{"page_number": p, "text": t, "bbox": list(b), "object_id": f"b{i}"}
                   for i, (p, t, b) in enumerate(blocks)],
        "lines": [{"page_number": p, "text": t, "bbox": list(b), "font_size": f} for p, t, b, f in lines],
        "column_schedules": {"schedules": list(schedules)},
    }


# Furley Struct.pdf p9 S102C, mechanical room notes (one block)
_FURLEY_MECH = ("1. ELEVATED FLOOR SLAB AT MEACHANICAL ROOM SHALL BE 6\" THICK NORMAL WEIGHT CONCRETE. "
                "2. TOP OF SLAB ELEVATION SHALL BE 19'-4\" ABOVE DATUM ELEVATION. TOP OF STEEL ELEVATION "
                "(BOTTOM OF DECK) SHALL BE 8\" BELOW TOP OF SLAB ELEVATION UNLESS NOTED OTHERWISE THUS: (.....). "
                "3. PROVIDE 2-#5 BARS AT MID-DEPTH OF SLAB AROUND OPENINGS 1'-0\"x1'-0\" OR SMALLER.")
# Furley p10 S102D, second floor notes
_FURLEY_FLOOR = ("2. TOP OF SLAB ELEVATION SHALL BE 14'-8\" ABOVE DATUM ELEVATION. TOP OF STEEL ELEVATION "
                 "(BOTTOM OF DECK) SHALL BE 5\" BELOW TOP OF SLAB ELEVATION UNLESS NOTED OTHERWISE THUS: (.....).")
# Furley p11 S103A, roof notes
_FURLEY_ROOF = ("3. TOP OF STEEL ELEVATION (BOTTOM OF DECK) NOTED ON PLAN THUS: (0.00') IS MEASURED FROM "
                "DATUM ELEVATION (0.00'). 4. INSTALL 4\"x3\"x5/16\" ANGLE FRAME (4 SIDES) AROUND ALL ROOF OPENINGS.")


class PlanStatementTests(unittest.TestCase):
    def view(self, doc):
        from services.engineering.level_evidence import levels_view

        return levels_view(doc, {9: "S102C", 10: "S102D", 11: "S103A"})

    def test_slab_value_and_stated_offset_derive_steel_within_the_note_only(self):
        doc = _doc([(9, _FURLEY_MECH, (1908, 1383, 2454, 1652)), (10, _FURLEY_FLOOR, (2110, 281, 2653, 563))])
        records = self.view(doc)["plan_elevations"]
        derived = {(r["sheet"], r["value"]["display"]) for r in records if r["status"] == "derived"}
        self.assertEqual(derived, {("S102C", "18'-8\""), ("S102D", "14'-3\"")})
        mech = next(r for r in records if r["status"] == "derived" and r["sheet"] == "S102C")
        self.assertEqual(mech["area"], "MEACHANICAL ROOM")          # printed spelling kept
        self.assertEqual(mech["offset"]["direction"], "below")
        self.assertEqual(len(mech["inputs"]), 2)                     # slab value + offset note
        self.assertTrue(mech["unless_noted"])
        slab = [r for r in records if r["status"] == "read" and r["surface"] == "top of slab"]
        self.assertEqual(sorted(r["value"]["display"] for r in slab), ["14'-8\"", "19'-4\""])

    def test_offset_without_a_direction_is_not_applied(self):
        # OSSE - ST.pdf p10 S-103-O note 2
        text = ("1. DATUM ELEVATION 0'-0\" REFERENCES TOP OF SECOND FLOOR SLAB ELEVATION 55' - 2\". "
                "2. TOP OF STEEL ELEVATION IS <0' - 5 1/4\"> FROM TOP OF SLAB UNLESS NOTED THUS <X'-X\"> ON PLAN.")
        records = self.view(_doc([(10, text, (2555, 371, 2876, 555))]))["plan_elevations"]
        steel = [r for r in records if r["surface"] == "top of steel"]
        self.assertEqual([r["status"] for r in steel], ["unresolved"])
        self.assertIn("not whether it is above or below", steel[0]["note"])
        self.assertEqual([r["value"]["display"] for r in records if r["status"] == "read"], ["55'-2\""])

    def test_explicit_minus_sign_inside_parentheses_is_the_direction(self):
        # Washington Latin p10 S-102: offset note + T/SLAB spot elevation on the plan
        text = ("1. T/SLAB ELEVATION DENOTED AS XXX'-XX\" ON PLAN. 2. ELEVATIONS NOTED THUS (-X') IN PLAN ARE "
                "MEASURED FROM TOP OF SLAB ELEVATION. 3. T/STEEL ELEVATION = (-6-1/4”) AS MEASURED FROM TOP OF SLAB, U.N.O.")
        lines = [(10, "T/SLAB", (1000, 800, 1030, 810), 7.0), (10, "330’-0”", (1000, 812, 1040, 822), 7.0)]
        records = self.view(_doc([(10, text, (1385, 1605, 1920, 1872))], lines))["plan_elevations"]
        derived = [r for r in records if r["status"] == "derived"]
        self.assertEqual([r["value"]["display"] for r in derived], ["329'-5 3/4\""])
        self.assertEqual(derived[0]["offset"]["direction"], "below")

    def test_parenthesised_decimal_feet_follow_the_project_note(self):
        # Furley S103A: "(28.66')" beside beams means top of steel from datum -- only because note 3 says so.
        lines = [(11, "W18x35 (28.66')", (900, 800, 980, 810), 7.0), (11, "(L4)", (1000, 800, 1020, 810), 7.0),
                 (11, "W16x26 [14] (36)", (900, 900, 980, 910), 7.0)]
        view = self.view(_doc([(11, _FURLEY_ROOF, (248, 1440, 768, 1606))], lines))
        noted = view["noted_on_plans"]
        self.assertEqual([(g["count"], g["meaning"]) for g in noted], [(1, ["top of steel (from datum)"])])
        self.assertEqual(noted[0]["examples"][0]["value"], "(28.66')")
        # the note's own example "(0.00')" is not a plan value
        self.assertNotIn("(0.00')", [e["value"] for g in noted for e in g["examples"]])

    def test_bracketed_values_without_a_defining_note_are_not_read(self):
        lines = [(11, "W18x35 (28.66')", (900, 800, 980, 810), 7.0)]
        self.assertEqual(self.view(_doc([(11, "1. BEAMS ARE EQUALLY SPACED.", (0, 0, 10, 10))], lines))["noted_on_plans"], [])

    def test_project_abbreviation_defines_tos(self):
        # Yellow Spring ST1.pdf p5 note 4: TOS is defined by the project, not assumed.
        note = ("4. TOP OF STEEL IS MEASURED FROM TOP OF DATUM SLAB ON GRADE AND IS INDICATED THUS TOS (+0'-0\"). "
                "3. JOIST BEARING ELEVATION IS MEASURED FROM TOP OF DATUM SLAB ON GRADE AND IS INDICATED THUS JBE (+0'-0\").")
        lines = [(5, "TOS(+16'-5 1/8\")", (500, 500, 560, 510), 7.0), (5, "JBE (26'-3\")", (600, 500, 650, 510), 7.0)]
        noted = self.view(_doc([(5, note, (100, 100, 900, 200))], lines))["noted_on_plans"]
        self.assertEqual(noted[0]["count"], 2)
        self.assertEqual(sorted(noted[0]["meaning"]), ["joist bearing (from top of datum slab on grade)",
                                                       "top of steel (from top of datum slab on grade)"])

    def test_reference_elevation_conversion_and_unstated_steel(self):
        # Burrville ST-Burrville.pdf p7 S-102A notes
        text = ("1. REFERENCE ELEVATION IS AT 14'-6\", CORRESPONDING TO THE TRUE ELEVATION OF 112'-0\". "
                "2. TOP OF SLAB IS AT THE REFERENCE ELEVATION UNO THUS ON PLAN RELATIVE TO THE REFERENCE ELEVATION. "
                "3. TOP OF STEEL IS AT BOTTOM OF DECK UNO THUS [+/- X'-X\"] RELATIVE TO REFERENCE ELEVATION.")
        view = self.view(_doc([(7, text, (2104, 1579, 2635, 1700))]))
        slab = next(r for r in view["plan_elevations"] if r["surface"] == "top of slab")
        self.assertEqual((slab["status"], slab["value"]["display"], slab["true_elevation"]["raw"]),
                         ("derived", "14'-6\"", "112'-0\""))
        steel = next(r for r in view["plan_elevations"] if r["surface"] == "top of steel")
        self.assertEqual(steel["status"], "unresolved")
        self.assertIn("reference elevation 14'-6\" corresponds to true elevation 112'-0\"",
                      [d["relation"] for d in view["datums"]])

    def test_blank_reference_sheet_is_reported(self):
        # Brandywine Structural4.pdf p11 S-120 note 1
        text = "1. TOP OF SLAB ELEVATION = +14'-0\". REFERENCE ELEVATION IS DEFINED ON . 2. TOP OF STEEL BEAM ELEVATION IS (+13'-6 3/4\") UNLESS NOTED OTHERWISE."
        view = self.view(_doc([(11, text, (2257, 135, 2640, 155))]))
        self.assertEqual([d["status"] for d in view["datums"]], ["unresolved"])
        steel = next(r for r in view["plan_elevations"] if r["surface"] == "top of steel")
        self.assertEqual((steel["status"], steel["value"]["display"]), ("read", "13'-6 3/4\""))


def _level_schedule(lines, schedule_id="S1", name="COLUMN SCHEDULE", page=26):
    return {"id": schedule_id, "title": name, "caption": None, "pages": [page],
            "level_lines": [{"page": page, "y": 100.0 + 50 * i, "name": n, "elevation_text": e,
                             "name_bbox": [10, 90 + 50 * i, 60, 98 + 50 * i],
                             "elevation_bbox": [10, 102 + 50 * i, 50, 110 + 50 * i] if e else None}
                            for i, (n, e) in enumerate(lines)]}


class LevelRegistryTests(unittest.TestCase):
    def view(self, doc, sheets=None):
        from services.engineering.level_evidence import levels_view

        return levels_view(doc, sheets or {})

    def test_a_differing_plan_value_is_a_conflict_not_a_replacement(self):
        # OSSE S-602-O GCS: T.O. SLAB LEVEL 2 55'-10"; S-103-O note: second floor slab 55'-2"
        schedule = _level_schedule([("T.O. ROOF", "69' - 4\""), ("T.O. SLAB LEVEL 2", "55' - 10\""),
                                    ("T.O. SLAB LEVEL 1", "38' - 0\"")])
        blocks = [(10, "1. DATUM ELEVATION 0'-0\" REFERENCES TOP OF SECOND FLOOR SLAB ELEVATION 55' - 2\".", (0, 0, 9, 9)),
                  (9, "1. DATUM ELEVATION 0'-0\" REFERENCES TOP OF FIRST FLOOR SLAB ELEVATION 38' - 0\".", (0, 0, 9, 9))]
        levels = {l["name"]: l for l in self.view(_doc(blocks, schedules=[schedule]))["schedule_levels"]}
        level2 = levels["T.O. SLAB LEVEL 2"]
        self.assertEqual(level2["printed"], "55' - 10\"")          # schedule value unchanged
        self.assertTrue(level2["conflict"])
        self.assertEqual([v["display"] for m in level2["plan_matches"] for v in m["values"]], ["55'-2\""])
        self.assertFalse(levels["T.O. SLAB LEVEL 1"]["conflict"])
        self.assertEqual(levels["T.O. SLAB LEVEL 1"]["plan_matches"][0]["comparison"], "agrees")
        self.assertEqual(levels["T.O. ROOF"]["plan_matches"], [])   # no matching plan; not guessed

    def test_similar_names_with_different_qualifiers_do_not_match(self):
        from services.engineering.level_evidence import level_keys

        self.assertTrue(level_keys("T.O. SLAB LEVEL 2") & level_keys("SECOND FLOOR FRAMING PLAN"))
        self.assertTrue(level_keys("2 SECOND FLOOR AND LOW ROOF") & level_keys("SECOND FLOOR PLAN"))
        self.assertFalse(level_keys("T.O. ROOF") & level_keys("OFFICE ROOF PLAN"))
        self.assertFalse(level_keys("UPPER ROOF") & level_keys("MAIN ROOF FRAMING PLAN"))
        self.assertFalse(level_keys("LEVEL 2") & level_keys("LEVEL 3 FRAMING PLAN"))

    def test_see_plan_resolves_only_to_a_single_plan_value(self):
        # Washington Latin S-202 levels "SEE PLAN"; S-102 shows one T/SLAB, S-103 shows two.
        schedule = _level_schedule([("SECOND FLOOR", "SEE PLAN"), ("THIRD FLOOR", "SEE PLAN"), ("GROUND FLOOR", "SEE PLAN")],
                                   page=15)
        lines = [(10, "SECOND FLOOR FRAMING PLAN", (100, 2000, 400, 2020), 14.0),
                 (10, "T/SLAB", (1000, 800, 1030, 810), 7.0), (10, "330'-0\"", (1000, 812, 1040, 822), 7.0),
                 (11, "THIRD FLOOR FRAMING PLAN", (100, 2000, 400, 2020), 14.0),
                 (11, "T/SLAB", (1000, 800, 1030, 810), 7.0), (11, "344'-6\"", (1000, 812, 1040, 822), 7.0),
                 (11, "T/SLAB", (2000, 800, 2030, 810), 7.0), (11, "343'-7\"", (2000, 812, 2040, 822), 7.0)]
        levels = {l["name"]: l for l in self.view(_doc([], lines, schedules=[schedule]))["schedule_levels"]}
        self.assertEqual(levels["SECOND FLOOR"]["resolved"]["display"], "330'-0\"")
        self.assertIsNone(levels["THIRD FLOOR"]["resolved"])
        self.assertIn("2 different values", levels["THIRD FLOOR"]["note"])
        self.assertIsNone(levels["GROUND FLOOR"]["resolved"])

    def test_missing_elevation_stays_missing(self):
        # Fort Davis S301: levels without elevations
        schedule = _level_schedule([("HIGH ROOF", None), ("2ND", None)], page=15)
        levels = self.view(_doc([], schedules=[schedule]))["schedule_levels"]
        self.assertEqual([(l["status"], l["elevation"]) for l in levels], [("missing", None), ("missing", None)])

    def test_repeated_labels_in_continued_blocks_are_one_level(self):
        schedule = _level_schedule([("LEVEL 2", "14'-0\""), ("LEVEL 1", "0\"")])
        schedule["level_lines"] += [{**line, "page": 43} for line in schedule["level_lines"]]
        levels = self.view(_doc([], schedules=[schedule]))["schedule_levels"]
        self.assertEqual([(l["name"], l["blocks"]) for l in levels], [("LEVEL 2", 2), ("LEVEL 1", 2)])

    def test_rotated_page_boxes_are_in_display_space(self):
        # Yellow Spring ST1.pdf p13: stored /Rotate 90; "Locations" word
        from services.engineering.level_evidence import display_boxes

        box = display_boxes(_doc([(13, "x", (0, 0, 1, 1))], rotation=90))
        self.assertEqual(box(13, [547.75, 2668.03, 557.2, 2708.28]), [315.7, 547.8, 356.0, 557.2])
        self.assertEqual(display_boxes(_doc([(1, "x", (0, 0, 1, 1))]))(1, [1, 2, 3, 4]), [1.0, 2.0, 3.0, 4.0])


class MaskedLabelTests(unittest.TestCase):
    def test_a_masked_spot_label_is_not_read(self):
        # Washington Latin p13 S-105: "T/SLAB" painted over, "T/DECK" typed on top of 372'-9".
        import tempfile
        from pathlib import Path

        import fitz

        from services.engineering.level_evidence import masked_spot_labels, spot_elevations

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "spot.pdf"
            document = fitz.open()
            page = document.new_page(width=600, height=400)
            page.insert_text((100, 100), "T/SLAB", fontsize=9)
            page.draw_rect(fitz.Rect(98, 90, 140, 102), color=None, fill=(1, 1, 1))
            page.insert_text((100, 100), "T/DECK", fontsize=9)
            page.insert_text((100, 113), "372'-9\"", fontsize=9)
            document.save(str(pdf))
            document.close()
            with fitz.open(str(pdf)) as reopened:
                lines = [(1, " ".join(s["text"] for s in ln["spans"]), ln["bbox"], 9.0)
                         for b in reopened[0].get_text("dict")["blocks"] for ln in b.get("lines", [])]
            doc = _doc([], lines)
            unmasked = spot_elevations(doc, {})
            doc["masked_text"] = masked_spot_labels(doc, str(pdf))
            spots = spot_elevations(doc, {})
        self.assertIn("top of slab", [s["surface"] for s in unmasked])     # the raw text layer has both
        self.assertEqual([(s["surface"], s["value"]["display"]) for s in spots], [("top of deck", "372'-9\"")])

    def test_bottom_of_is_not_top_of(self):
        from services.engineering.level_evidence import _surface

        self.assertEqual(_surface("BOTTOM OF FOOTING"), "bottom of footing")
        self.assertEqual(_surface("BOTTOM OF BASE PLATE"), "bottom of base plate")
        self.assertEqual(_surface("TOP OF STEEL BEAMS"), "top of steel")


class LevelDifferenceTests(unittest.TestCase):
    def ends(self, top, bottom):
        return {"top": top, "bottom": bottom}

    def at(self, name, elevation):
        return {"position": "at", "y": 0, "line": {"name": name, "elevation_text": elevation, "y": 0}}

    def test_difference_between_two_printed_levels(self):
        from services.engineering.level_evidence import level_difference

        # OSSE C.8-8.9: drawn from T.O. ROOF down to T.O. SLAB LEVEL 1 (on its pier)
        diff = level_difference(self.ends(self.at("T.O. ROOF", "69' - 4\""), self.at("T.O. SLAB LEVEL 1", "38' - 0\"")))
        self.assertEqual((diff["status"], diff["display"]), ("computed", "31'-4\""))

    def test_end_between_lines_gives_no_height(self):
        from services.engineering.level_evidence import level_difference

        between = {"position": "between", "y": 0, "near": "upper",
                   "upper": {"name": "LEVEL 2", "elevation_text": "14'-0\"", "y": 0},
                   "lower": {"name": "LEVEL 1", "elevation_text": "0\"", "y": 0}}
        diff = level_difference(self.ends(between, self.at("LEVEL 1", "0\"")))
        self.assertEqual(diff["status"], "unresolved")
        self.assertNotIn("display", diff)

    def test_see_plan_or_missing_elevation_gives_no_height(self):
        from services.engineering.level_evidence import level_difference

        diff = level_difference(self.ends(self.at("ROOF LEVEL", "SEE PLAN"), self.at("FIRST FLOOR", "SEE PLAN")))
        self.assertEqual(diff["status"], "unresolved")
        self.assertEqual(level_difference(self.ends(self.at("HIGH ROOF", None), self.at("2ND", None)))["status"],
                         "unresolved")

    def test_steel_and_slab_levels_are_not_subtracted(self):
        from services.engineering.level_evidence import level_difference

        diff = level_difference(self.ends(self.at("T.O. STEEL ROOF", "30'-0\""), self.at("T.O. SLAB LEVEL 1", "0\"")))
        self.assertEqual(diff["status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
