"""Drawing Summary interpretation evidence (OSSE review, October 2026).

Grid-location offsets are locations, not elevations; a legend's own example
is a definition, not an observation; level names link to plans by name *and*
scope, keeping qualifiers; a graphical framing key is read from its leaders;
a schedule note's material applies only to the labels it names; the summary
model's evidence is typed, sourced and never cut mid-record; grounding
rejects unsupported dimensions, resolved conflicts, member lengths and
quantities. Real-drawing checks live in ``test_level_reference_set``.
"""

from __future__ import annotations

import unittest

import fitz

from services.engineering.column_schedule import _material
from services.engineering.drawing_intelligence import build_drawing_intelligence, evidence_packet, summary_facts
from services.engineering.drawing_summary_llm import _grounded
from services.engineering.framing_key import _block, bracket_definition, read_page_keys
from services.engineering.level_evidence import _level_surface, _relation, grid_location_offset, level_keys, levels_view

_LEGEND = "(##' - ##\") BOTTOM OF BASE PLATE ELEVATION RELATIVE TO DATUM"


def _doc(blocks=(), lines=()):
    pages = sorted({b[0] for b in blocks} | {l[0] for l in lines} | {1})
    return {
        "pages": [{"page_number": p, "width": 3024.0, "height": 2160.0, "rotation": 0} for p in pages],
        "blocks": [{"page_number": p, "text": t, "bbox": list(b), "object_id": f"b{i}"}
                   for i, (p, t, b) in enumerate(blocks)],
        "lines": [{"page_number": p, "text": t, "bbox": list(b), "font_size": 9.6} for p, t, b in lines],
        "column_schedules": {"schedules": []},
    }


class GridOffsetTests(unittest.TestCase):
    def offset(self, text):
        start = text.index("(")
        end = text.index(")", start) + 1
        return grid_location_offset(text, start, end)

    def test_offsets_inside_grid_locations_belong_to_the_location(self):
        for text, grid, inches in (("C.1(-6\")-7.3", "C.1", -6.0), ("C.5-7(6\")", "7", 6.0),
                                   ("R13(5' - 4\")-RA.1", "R13", 64.0)):
            found = self.offset(text)
            self.assertEqual((found["grid"], found["offset"]["inches"]), (grid, inches), text)

    def test_two_locations_printed_without_a_separator_are_read_apart(self):
        text = "R13(5' - 4\")-RA.1R13(5' - 4\")-RA.2"
        second = text.index("(", 5)
        found = grid_location_offset(text, second, text.index(")", second) + 1)
        self.assertEqual(found["location"], "R13(5' - 4\")-RA.2")

    def test_a_standalone_bracketed_elevation_is_not_a_location(self):
        for text in ("(98' - 6\")", "B.O. PLATE (98' - 6\")", "W12X26 (36' - 0\")", "(##' - ##\")"):
            self.assertIsNone(self.offset(text), text)

    def test_location_offsets_never_become_base_plate_elevations(self):
        doc = _doc(blocks=[(2, _LEGEND, (2000, 1500, 2400, 1520))],
                   lines=[(25, "C.1(-6\")-7.3", (1100, 1700, 1180, 1712)), (25, "C.5-7(6\")", (1100, 1720, 1180, 1732)),
                          (25, "(98' - 6\")", (500, 500, 560, 512))])
        view = levels_view(doc, {2: "S001", 25: "S601"})
        noted = [e["value"] for g in view["noted_on_plans"] for e in g["examples"]]
        self.assertEqual(noted, ["(98' - 6\")"])                 # the genuine elevation stays
        self.assertEqual([o["location"] for o in view["location_offsets"]], ["C.1(-6\")-7.3", "C.5-7(6\")"])
        self.assertEqual(view["location_offsets"][0]["offset"]["raw"], "-6\"")

    def test_a_legend_example_is_not_a_plan_observation(self):
        doc = _doc(blocks=[(2, "(##' - ##\") TOP OF FRAMING ELEVATION RELATIVE TO DATUM", (2000, 1500, 2400, 1520))],
                   lines=[(2, "W18X40 <+12'-3\">", (554, 1833, 696, 1843)), (7, "W16X26 <+30'-0\">", (900, 900, 1000, 912))])
        doc["blocks"][0]["text"] = "<##' - ##\"> TOP OF FRAMING ELEVATION RELATIVE TO DATUM"
        view = levels_view(doc, {2: "S001", 7: "S103"}, legend_regions={2: [[380, 1700, 730, 1850]]})
        self.assertEqual([g["sheet"] for g in view["noted_on_plans"]], ["S103"])
        self.assertEqual([e["value"] for e in view["legend_examples"]], ["<+12'-3\">"])


class LevelNameTests(unittest.TestCase):
    def test_a_qualifier_the_schedule_does_not_print_is_kept(self):
        keys = level_keys("T.O. ROOF")
        self.assertEqual(_relation(keys, "OFFICE ROOF", set()), {"relation": "qualified", "plan_qualifiers": ["OFFICE"]})
        # building / project words are scope, not a level qualifier
        self.assertEqual(_relation(keys, "OSSE FACILITY ROOF PLAN", {"OSSE", "FACILITY"})["relation"], "same")

    def test_different_qualifiers_never_match(self):
        self.assertIsNone(_relation(level_keys("UPPER ROOF"), "LOWER ROOF PLAN", set()))
        self.assertIsNone(_relation(level_keys("T.O. SLAB LEVEL 2"), "FIRST FLOOR PLAN", set()))

    def test_surfaces_stay_distinct(self):
        self.assertEqual(_level_surface("T.O. SLAB LEVEL 2"), "top of slab")
        self.assertEqual(_level_surface("T.O. PARKING DECK SLAB"), "top of slab")
        self.assertEqual(_level_surface("T.O. PARKING LOWER DECK"), "top of deck")
        self.assertEqual(_level_surface("T.O. STEEL ROOF"), "top of steel")
        self.assertIsNone(_level_surface("T.O. ROOF"))


_WHITE = (1, 1, 1)
_STUD_LABEL = (96, 168, 200, 196)          # around "# OF SHEAR STUDS." / "SEE TYPICAL DETAIL"


def _key_page(leaders=True, *, stud_background=False, mask_studs=None, replacement=None, second_label=None):
    """A framing key in miniature: heading, example callout, three labels and
    (optionally) arrow-tipped leaders from each part to its label.

    ``stud_background``: a white box drawn *before* the stud label (a cell
    background). ``mask_studs``: a white box drawn *after* it over that rect
    (an obsolete label masked). ``replacement``: visible text printed over
    the mask. ``second_label``: another visible label with a second leader
    from ``[35]`` (two visible definitions)."""

    doc = fitz.open()
    page = doc.new_page(width=1200, height=800)
    page.insert_text((300, 100), "STRUCTURAL STEEL FRAMING KEY", fontsize=12)
    page.insert_text((300, 300), "W18X40 [35]  c=1 1/4\"  <+12'-3\">", fontsize=9.6)
    if stud_background:
        page.draw_rect(fitz.Rect(*_STUD_LABEL), color=None, fill=_WHITE)
    page.insert_text((100, 180), "# OF SHEAR STUDS.", fontsize=9.6)
    page.insert_text((100, 191), "SEE TYPICAL DETAIL", fontsize=9.6)
    if mask_studs:
        page.draw_rect(fitz.Rect(*mask_studs), color=None, fill=_WHITE)
    if replacement:
        page.insert_text((100, 180), replacement, fontsize=9.6)
    page.insert_text((620, 180), "CAMBER", fontsize=9.6)
    page.insert_text((620, 230), "TOP OF STEEL ELEVATION", fontsize=9.6)
    if second_label:
        page.insert_text((300, 180), second_label, fontsize=9.6)
        r = page.search_for("[35]")[0]
        page.draw_line(((r.x0 + r.x1) / 2 + 2, r.y0 - 1), (330, 185), width=0.24)
    if leaders:
        boxes = {t: page.search_for(t)[0] for t in ("[35]", "c=1 1/4\"", "<+12'-3\">")}
        for token, (lx, ly) in (("[35]", (200, 185)), ("c=1 1/4\"", (615, 176)), ("<+12'-3\">", (615, 226))):
            r = boxes[token]
            tip = ((r.x0 + r.x1) / 2, r.y0 - 1)
            page.draw_line(tip, (lx, ly), width=0.24)
            page.draw_line(tip, (tip[0] - 3, tip[1] - 8), width=0.24)   # arrowhead strokes
            page.draw_line(tip, (tip[0] + 3, tip[1] - 8), width=0.24)
    return doc, page


class FramingKeyTests(unittest.TestCase):
    def test_each_part_means_the_label_its_leader_ends_at(self):
        _document, page = _key_page()
        (key,) = read_page_keys(page, 2, "S001")
        meanings = {p["token"]: (p["status"], p.get("field")) for p in key["parts"]}
        self.assertEqual(meanings["[35]"], ("defined", "shear_studs"))
        self.assertEqual(meanings["c=1 1/4\""], ("defined", "camber"))
        self.assertEqual(meanings["<+12'-3\">"], ("defined", "top_of_steel_elevation"))
        definition = bracket_definition([key])
        self.assertEqual(definition["status"], "defined")
        self.assertIn("SHEAR STUDS", definition["meaning"])
        self.assertEqual(definition["sources"][0]["sheet"], "S001")

    def test_without_leaders_nothing_is_decoded(self):
        _document, page = _key_page(leaders=False)
        (key,) = read_page_keys(page, 2, "S001")
        self.assertEqual({p["status"] for p in key["parts"]}, {"no_leader"})
        self.assertEqual(bracket_definition([key])["status"], "undefined")

    def stud_part(self, **kwargs):
        _document, page = _key_page(**kwargs)
        (key,) = read_page_keys(page, 2, "S001")
        return next(p for p in key["parts"] if p["token"] == "[35]"), key

    def test_a_white_background_drawn_before_the_label_hides_nothing(self):
        part, _key = self.stud_part(stud_background=True)
        self.assertEqual(part["status"], "defined")
        self.assertIn("SHEAR STUDS", part["meaning"])

    def test_a_masked_label_defines_nothing_and_keeps_the_warning(self):
        part, key = self.stud_part(mask_studs=_STUD_LABEL)
        self.assertEqual((part["status"], part["meaning"]), ("hidden_label", None))
        self.assertTrue(any("SHEAR STUDS" in t for t in part["hidden_text"]))   # diagnostic only
        self.assertEqual(bracket_definition([key])["status"], "undefined")

    def test_a_visible_replacement_over_a_mask_is_the_label_without_a_conflict(self):
        part, key = self.stud_part(mask_studs=_STUD_LABEL, replacement="NUMBER OF STUDS")
        self.assertEqual((part["status"], part["meaning"]), ("defined", "NUMBER OF STUDS"))
        self.assertEqual(bracket_definition([key])["status"], "defined")

    def test_a_partly_masked_label_stays_uncertain(self):
        # Only the second line of the stud label is masked.
        part, key = self.stud_part(mask_studs=(96, 183, 200, 196))
        self.assertEqual((part["status"], part["meaning"]), ("partially_hidden", None))
        self.assertEqual(bracket_definition([key])["status"], "undefined")

    def test_two_visible_definitions_are_a_conflict(self):
        part, _key = self.stud_part(second_label="CONNECTION REACTION")
        self.assertEqual(part["status"], "conflicting")
        self.assertEqual(len(part["candidates"]), 2)

    def test_transparent_white_fill_does_not_hide_a_label(self):
        _document, page = _key_page()
        page.draw_rect(fitz.Rect(*_STUD_LABEL), color=None, fill=_WHITE, fill_opacity=0.3)
        (key,) = read_page_keys(page, 2, "S001")
        self.assertEqual(bracket_definition([key])["field"], "shear_studs")

    def test_partial_mask_within_a_line_cannot_define_meaning(self):
        _document, page = _key_page()
        word = page.search_for("SHEAR")[0]
        page.draw_rect(word, color=None, fill=_WHITE)
        (key,) = read_page_keys(page, 2, "S001")
        self.assertEqual(bracket_definition([key])["status"], "undefined")
        self.assertEqual(next(p for p in key["parts"] if p["token"] == "[35]")["status"], "partially_hidden")

    def test_multiline_replacement_at_the_masked_second_line(self):
        _document, page = _key_page(mask_studs=_STUD_LABEL, replacement="CONNECTION")
        page.insert_text((100, 191), "REACTION", fontsize=9.6)
        (key,) = read_page_keys(page, 2, "S001")
        definition = bracket_definition([key])
        self.assertEqual(definition["meaning"], "CONNECTION REACTION")
        self.assertEqual(definition["field"], "reaction")

    def test_deeply_overlapping_visible_lines_do_not_join(self):
        first = {"text": "REACTION", "bbox": [100, 160, 190, 180], "masked": False}
        other = {"text": "UNRELATED", "bbox": [100, 162, 195, 174], "masked": False}
        self.assertEqual(_block(first, [first, other]), [first])

    def test_masked_meaning_is_not_an_accepted_model_fact(self):
        from services.engineering.drawing_intelligence import _key_rules

        _document, page = _key_page(mask_studs=_STUD_LABEL, replacement="CONNECTION REACTION")
        keys = read_page_keys(page, 2, "S001")
        profile = build_drawing_intelligence(_doc())
        profile["interpretation_rules"] = [{**rule, "id": f"R{i}"} for i, rule in enumerate(_key_rules(keys))]
        packet = evidence_packet(profile)
        self.assertNotIn("SHEAR STUDS", packet)
        self.assertIn("CONNECTION REACTION", packet)

    def test_keys_that_disagree_stay_a_conflict(self):
        _document, page = _key_page()
        (key,) = read_page_keys(page, 2, "S001")
        other = {**key, "page": 9, "sheet": "S501",
                 "parts": [{**p, "meaning": "CONNECTION REACTION"} if p["token"] == "[35]" else p for p in key["parts"]]}
        result = bracket_definition([key, other])
        self.assertEqual(result["status"], "conflicting")
        self.assertEqual(len(result["meanings"]), 2)

    def test_an_undefined_bracket_keeps_its_warning(self):
        prof = build_drawing_intelligence({
            "page_count": 1, "text": "FRAMING PLAN " + "W14X22 [8] " * 12,
            "blocks": [{"page_number": 1, "text": "FRAMING PLAN " + "W14X22 [8] " * 12}],
            "pages": [{"page_number": 1, "text_length": 10, "engineering_relevance_score": 5}],
            "engineering_tokens": [], "schedules": [], "title_blocks": [],
        })
        (item,) = [u for u in prof["unresolved"] if u["kind"] == "undefined_bracket_tag"]
        self.assertIn("no framing key", item["text"])


class MaterialTests(unittest.TestCase):
    RULES = [{"prefix": "C", "material": "precast concrete", "source": {"text": "NOTE: ALL C_ COLUMNS ARE PRECAST"}}]

    def test_the_note_applies_to_the_labels_it_names(self):
        entry = {"sections": [{"designation": None, "printed": "C1 - 24\"x24\""}]}
        material = _material(entry, self.RULES)
        self.assertEqual((material["material"], material["mark"]), ("precast concrete", "C1"))
        self.assertEqual([d["inches"] for d in material["size"]["dimensions"]], [24.0, 24.0])
        self.assertEqual(material["size"]["raw"], "24\"x24\"")

    def test_other_concrete_labels_need_their_own_evidence(self):
        for printed in ("RC1 - 24\" x 24\"", "P1", "W10X33"):
            self.assertIsNone(_material({"sections": [{"designation": None, "printed": printed}]}, self.RULES), printed)


def _profile_with_levels():
    level = {"schedule_id": "S2", "schedule": "OSSE BUILDING - GCS", "name": "T.O. SLAB LEVEL 2", "printed": "55' - 10\"",
             "elevation": {"inches": 670.0}, "page": 26, "sheet": "S602", "bbox": [1, 2, 3, 4],
             "plan_matches": [{"page": 10, "sheet": "S122", "association": "supported", "comparison": "differs",
                               "values": [{"surface": "top of slab", "raw": "55' - 2\"", "display": "55'-2\"", "inches": 662.0,
                                           "compared": True, "source": {"page": 10, "sheet": "S122", "bbox": [5, 6, 7, 8]}}]}]}
    return {"levels": {"schedule_levels": [level], "location_offsets": []},
            "column_schedule": {"schedules": [], "entries": []}}


class FactTests(unittest.TestCase):
    def test_a_conflict_keeps_both_values_and_sources(self):
        (fact,) = summary_facts(_profile_with_levels())
        self.assertEqual((fact["id"], fact["status"]), ("X1", "conflicting"))
        self.assertEqual((fact["schedule_value"], fact["plan_value"], fact["difference"]), ("55' - 10\"", "55' - 2\"", "8\""))
        self.assertEqual([s["page"] for s in fact["sources"]], [26, 10])
        self.assertIn("does not say which governs", fact["text"])

    def test_the_packet_keeps_whole_facts_and_says_what_it_left_out(self):
        prof = build_drawing_intelligence({
            "page_count": 1, "text": "PLAN", "blocks": [{"page_number": 1, "text": "PLAN"}],
            "pages": [{"page_number": 1, "text_length": 4, "engineering_relevance_score": 5}],
            "engineering_tokens": [], "schedules": [], "title_blocks": [],
        })
        prof["facts"] = [{"id": f"C{i}", "type": "column", "text": f"Column fact {i}: " + "x" * 300} for i in range(1, 40)]
        packet = evidence_packet(prof, max_chars=2500)
        self.assertLessEqual(len(packet), 2500)
        rows = [line for line in packet.splitlines() if line.startswith("  [C")]
        self.assertTrue(rows and all(line.endswith("x" * 300) for line in rows))   # never cut mid-record
        self.assertIn("further facts left out for length", packet)


class GroundingTests(unittest.TestCase):
    CONFLICT = ("OSSE BUILDING - GCS: T.O. SLAB LEVEL 2 is 55' - 10\" in the column schedule (S602 · PDF p. 26); "
                "the S122 plan note gives top of slab 55' - 2\" (S122 · PDF p. 10). Difference 8\". Both values "
                "stand; the drawing does not say which governs.")
    COLUMN = ("OSSE BUILDING - GCS (S602 · PDF p. 26): column at C.8-8.9 -> W10X33; base plate CBP-2 (width 12\", "
              "length 18\", thickness 3/4\"). Drawn from T.O. SLAB LEVEL 1 (38' - 0\") to T.O. ROOF (69' - 4\"): "
              "elevation difference 31'-4\", calculated from the schedule's elevations; not a fabricated member length.")
    MATERIAL = "OSSE PARKING - GCS: C1 columns are precast concrete per the schedule note. Not steel."

    def check(self, fact, text):
        kind = {self.CONFLICT: "X", self.COLUMN: "C", self.MATERIAL: "M"}[fact]   # the cited fact's id letter
        return _grounded(text, fact, 220, kind) is not None

    def test_supported_explanations_pass(self):
        self.assertTrue(self.check(self.CONFLICT, "Check whether 55'-10\" or 55'-2\" applies; the drawing does not say which governs."))
        self.assertTrue(self.check(self.COLUMN, "Grid C.8-8.9 uses a W10X33 on plate CBP-2, 12\" wide and 3/4\" thick."))
        self.assertTrue(self.check(self.COLUMN, "The 31'-4\" is an elevation difference, not a member length."))
        self.assertTrue(self.check(self.MATERIAL, "C1 columns are precast concrete; exclude them from the steel takeoff."))
        self.assertTrue(self.check(self.CONFLICT, "The schedule and the S122 plan note disagree on T.O. SLAB LEVEL 2."))

    def test_invented_or_overconfident_claims_are_rejected(self):
        for fact, text in (
            (self.CONFLICT, "The schedule value 55'-10\" is correct; the plan note is a typo."),
            (self.CONFLICT, "Use the average of 55'-10\" and 55'-2\"."),
            (self.CONFLICT, "Level 2 differs by 9\" between the sources."),
            (self.COLUMN, "The C.8-8.9 column is 31'-4\" long."),
            (self.COLUMN, "The C.8-8.9 column sits on base plate CBP-7."),
            (self.COLUMN, "Grid C.8-8.7 uses a W10X33."),
            (self.COLUMN, "Plate CBP-2 is 1\" thick."),
            (self.COLUMN, "There are 26 installed steel columns like this."),
            (self.MATERIAL, "C1 columns are steel columns."),
            # a value cut off mid-way (seen from llama3.1:8b on OSSE)
            (self.CONFLICT, "conflicting values for T.O. SLAB LEVEL 2 in column schedule (55' - 10"),
            # the conflict is between the schedule and a plan note, not inside the schedule
            (self.CONFLICT, "The column schedule has conflicting values for T.O. SLAB LEVEL 2."),
        ):
            self.assertFalse(self.check(fact, text), text)


class RenovationTests(unittest.TestCase):
    def test_existing_construction_in_general_notes_is_not_existing_and_new_framing(self):
        text = ("GENERAL NOTES. GROUND IMPROVEMENT OF EXISTING SOILS. CLEAN ALL EXISTING CONCRETE SURFACES. "
                "EXISTING REINFORCING BARS MAY CONFLICT. REVIEW THE EXISTING STRUCTURAL DRAWINGS. "
                "EXISTING CONCRETE SLAB. DRILLED INTO EXISTING SLAB. EXISTING SLAB. EXISTING SOILS. "
                "ABBREVIATIONS: DEMO DEMOLITION/DEMOLISH")
        prof = build_drawing_intelligence({
            "page_count": 1, "text": text, "blocks": [{"page_number": 1, "text": text}],
            "pages": [{"page_number": 1, "text_length": len(text), "engineering_relevance_score": 5}],
            "engineering_tokens": [], "schedules": [], "title_blocks": [],
        })
        self.assertFalse(prof["existing_new"]["is_renovation"])
        self.assertNotIn("existing and new", prof["overview"])

    def test_framing_named_existing_and_new_supports_the_claim(self):
        text = "FRAMING PLAN. EXISTING BEAM TO REMAIN. EXISTING STEEL. NEW STEEL BEAM. NEW BEAM W12X26 TO EXISTING BEAM."
        prof = build_drawing_intelligence({
            "page_count": 3, "text": text, "blocks": [{"page_number": 3, "text": text}],
            "pages": [{"page_number": 3, "text_length": len(text), "engineering_relevance_score": 5}],
            "engineering_tokens": [], "schedules": [], "title_blocks": [],
        })
        self.assertTrue(prof["existing_new"]["is_renovation"])
        self.assertEqual(prof["existing_new"]["pages"], [3])
        self.assertIn("existing and new", prof["overview"])


if __name__ == "__main__":
    unittest.main()
