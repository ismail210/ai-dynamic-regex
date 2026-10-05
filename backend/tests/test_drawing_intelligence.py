"""Drawing Intelligence Profile -- grounding, TYP detection, schedule /
scope safety, and the deterministic narrative fallback."""

from __future__ import annotations

import unittest

from services.engineering.drawing_intelligence import (
    build_drawing_intelligence,
    evidence_packet,
)
from services.engineering.drawing_summary_llm import summarize


def _doc(pages: dict, *, page_count=None, tokens=None, schedules=None, title_blocks=None):
    blocks = []
    for page, text in pages.items():
        blocks.append({"page_number": page, "text": text})
    return {
        "page_count": page_count or (max(pages) if pages else 0),
        "text": "\n".join(pages.values()),
        "blocks": blocks,
        "pages": [
            {"page_number": p, "text_length": len(t), "engineering_relevance_score": 5}
            for p, t in pages.items()
        ],
        "engineering_tokens": tokens or [],
        "schedules": schedules or [],
        "title_blocks": title_blocks or [],
    }


def _tok(text, page=1):
    return {"text": text, "normalized_text": text, "page": page, "takeoff_eligible": True}


class GroundingTests(unittest.TestCase):
    def test_no_evidence_makes_no_claim(self):
        prof = build_drawing_intelligence(_doc({1: "STRUCTURAL FRAMING PLAN\n" + "x " * 40}))
        n = prof["narrative"]
        self.assertIn("no catalog-valid steel", n["project_overview"].lower())
        self.assertEqual(n["drawing_language"], "No project-specific shorthand substitutions were found.")
        self.assertIn("No TYP", n["typical_conditions"])
        self.assertIn("No structural schedules", n["schedules"])

    def test_only_supported_families_are_named(self):
        prof = build_drawing_intelligence(_doc(
            {1: "FRAMING PLAN"},
            tokens=[_tok("W14X22"), _tok("W16X26"), _tok("W16X26"), _tok("HSS6X6X1/4")],
        ))
        fams = {f["family"] for f in prof["steel_system"]["families"]}
        self.assertEqual(fams, {"W", "HSS"})
        self.assertNotIn("angle", prof["narrative"]["steel_system"].lower())
        self.assertIn("W16X26", prof["steel_system"]["representative_sections"])
        # label tokens counted once each -- never multiplied
        w = next(f for f in prof["steel_system"]["families"] if f["family"] == "W")
        self.assertEqual(w["explicit_occurrences"], 3)

    def test_representative_sections_not_a_dump(self):
        toks = [_tok(f"W{d}X22") for d in range(8, 40, 2)] * 3
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN"}, tokens=toks))
        for fam in prof["steel_system"]["families"]:
            self.assertLessEqual(len(fam["representative"]), 4)


class TypicalConditionTests(unittest.TestCase):
    def test_typ_evidence_produces_insight(self):
        prof = build_drawing_intelligence(_doc({
            1: "ROOF FRAMING PLAN\nW16X26 TYP.\nW14X22, TYP\nSEE DETAIL SIM.",
        }))
        active = [i for i in prof["typical_conditions"] if i["detail"].get("present")]
        self.assertTrue(active)
        kws = {i["detail"]["keyword"] for i in active}
        self.assertIn("TYP", kws)
        self.assertIn("repeated framing", prof["narrative"]["typical_conditions"])

    def test_no_typ_is_not_invented(self):
        prof = build_drawing_intelligence(_doc({1: "FLOOR FRAMING PLAN\nW16X26 at grid A."}))
        self.assertEqual(
            prof["narrative"]["typical_conditions"],
            "No TYP / U.N.O. / repeated-condition language detected.",
        )

    def test_near_section_context_captured(self):
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN\nW21X44 TYP AT BAYS 1-6"}))
        active = [i for i in prof["typical_conditions"] if i["detail"].get("present")]
        near = {s for i in active for s in i["detail"].get("near_sections", [])}
        self.assertIn("W21X44", near)


class ScheduleTests(unittest.TestCase):
    def test_column_schedule_matrix_flagged_not_counted(self):
        sched_text = (
            "COLUMN SCHEDULE\nFIRST FLOOR 0' - 0\"\nSECOND FLOOR 14' - 0\"\n"
            "ROOF 28' - 0\"\nW14X90 W14X90 W12X65"
        )
        prof = build_drawing_intelligence(_doc(
            {1: "S-500 COLUMN SCHEDULE"},
            schedules=[{"schedule_id": "s1", "page_number": 1, "text": sched_text}],
        ))
        sched = prof["schedule_insights"]
        self.assertTrue(sched)
        self.assertEqual(sched[0]["detail"]["kind"], "column_schedule")
        self.assertIn("not a simple member count", sched[0]["detail"]["note"])

    def test_unclear_table_becomes_uncertainty_not_quantity(self):
        prof = build_drawing_intelligence(_doc(
            {1: "PLAN"},
            schedules=[{
                "schedule_id": "s2", "page_number": 3,
                "text": "MARK SIZE W12X26 W14X22 W16X31 W18X35 W21X44 W24X55 W10X12",
            }],
        ))
        kinds = {s["detail"]["kind"] for s in prof["schedule_insights"]}
        self.assertIn("unclassified_steel_table", kinds)
        self.assertTrue(any(
            u["detail"].get("kind") == "schedule_semantics" for u in prof["uncertainties"]
        ))

    def test_non_steel_table_not_surfaced(self):
        prof = build_drawing_intelligence(_doc(
            {1: "PLAN"},
            schedules=[{"schedule_id": "s3", "page_number": 2,
                        "text": "DOOR SCHEDULE\nD1 3070 HM\nD2 3070 WD"}],
        ))
        self.assertEqual(prof["schedule_insights"], [])


class ScopeRevisionTests(unittest.TestCase):
    def test_phase_stamp_from_title_block_only(self):
        prof = build_drawing_intelligence(_doc(
            {1: "FRAMING PLAN\nThe design development phase established the grid."},
            title_blocks=[{"page_number": 1, "text": "ISSUED FOR PERMIT"}],
        ))
        active = [i for i in prof["scope_signals"] if i["detail"].get("present")]
        labels = {i["detail"]["label"] for i in active}
        self.assertIn("Permit set", labels)
        # a prose mention of "design development" must NOT become a phase claim
        self.assertNotIn("Design Development", labels)

    def test_multiple_phases_raise_a_scope_uncertainty(self):
        prof = build_drawing_intelligence(_doc(
            {1: "PLAN"},
            title_blocks=[
                {"page_number": 1, "text": "EARLY STEEL RELEASE PACKAGE"},
                {"page_number": 2, "text": "ISSUED FOR BID"},
            ],
        ))
        self.assertTrue(any(u["detail"].get("kind") == "scope" for u in prof["uncertainties"]))
        self.assertIn("multiple phases present", prof["narrative"]["scope_revision"].lower())

    def test_no_scope_stamp_is_stated_plainly(self):
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN\nW16X26"}))
        self.assertIn("No explicit issue", prof["narrative"]["scope_revision"])


class RenovationTests(unittest.TestCase):
    def test_existing_new_detected(self):
        text = "PLAN\n(E) W14X22\n(N) W16X26\n(E) W12X19\nDEMOLISH (E) W10X12"
        prof = build_drawing_intelligence(_doc({1: text}))
        self.assertTrue(prof["existing_new"]["is_renovation"])
        self.assertIn("existing and new", prof["narrative"]["project_overview"])

    def test_new_construction_not_flagged_renovation(self):
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN\nW16X26\nW14X22"}))
        self.assertFalse(prof["existing_new"]["is_renovation"])


class NarrativeAndPacketTests(unittest.TestCase):
    def test_narrative_has_every_core_section(self):
        prof = build_drawing_intelligence(_doc(
            {1: "ROOF FRAMING PLAN\nW16X26 TYP"}, tokens=[_tok("W16X26")],
        ))
        for key in ("project_overview", "structural_content", "steel_system",
                    "drawing_language", "typical_conditions", "schedules",
                    "scope_revision", "important_notes", "uncertainties"):
            self.assertIn(key, prof["narrative"])

    def test_evidence_packet_is_bounded_and_has_no_token_dump(self):
        toks = [_tok(f"W{d}X{w}") for d in range(8, 40, 2) for w in range(10, 90, 5)]
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN"}, tokens=toks))
        packet = evidence_packet(prof, max_chars=6000)
        self.assertLessEqual(len(packet), 6000)
        self.assertIn("STEEL SYSTEM", packet)
        # a full section dump would be hundreds of lines; the packet caps it
        self.assertLess(packet.count("W"), 200)


def _row(mark, size_text, section=None, plate_text="", roles=()):
    return {
        "mark": mark, "size_text": size_text, "section": section,
        "catalog_valid": bool(section), "plate_text": plate_text,
        "plate_role": "bearing_plate" if plate_text else None,
        "member_plate_roles": list(roles),
    }


def _schedule_doc():
    """Struct.pdf S002 in miniature: four schedules on a sheet whose notes
    made the legend profile call it a SPECIFICATIONS page, plus a detail
    sheet that only says "SEE LINTEL SCHEDULE"."""

    page2 = (
        "STATEMENT OF SPECIAL INSPECTIONS\nCOLUMN SCHEDULE\nLINTEL SCHEDULE\n"
        "BEARING PLATE SCHEDULE\nICF LINTEL SCHEDULE"
    )
    page3 = "TYPICAL LINTEL DETAILS\nLOOSE LINTEL, SEE LINTEL SCHEDULE\nW8X21 W8X21 W8X21 W8X21 W8X21 W8X21"
    page4 = "FRAMING PLAN W14x22 [8] " * 12
    doc = _doc(
        {2: page2, 3: page3, 4: page4},
        page_count=4,
        schedules=[
            {"page_number": 2, "text": "STATEMENT OF SPECIAL INSPECTIONS: NOTE 1 ..."},
            {"page_number": 3, "text": page3},
        ],
    )
    for page in doc["pages"]:
        page.update(width=3024.0, height=2160.0)
    doc["blocks"] += [
        {"page_number": 2, "bbox": [2900, 2000, 2990, 2020], "text": "S002 INSPECTION TABLES AND SCHEDULES"},
        {"page_number": 3, "bbox": [2900, 2000, 2990, 2020], "text": "S502 DETAILS"},
        {"page_number": 2, "bbox": [2019, 1900, 2800, 1960],
         "text": "NOTES: 1. REFER TO SHEET S303 FOR LINTEL CONFIGURATIONS. "
                 "2. BEARING PLATE SIZE APPLIES TO EACH END UNLESS NOTED OTHERWISE."},
    ]
    marks = {"L1": 1770, "L1A": 1788, "L5": 1878, "C1": 134, "BP3": 1203, "CL1": 1422, "CL5": 1520}
    doc["words"] = [
        {"page_number": 2, "text": m, "bbox": [2020.0, y, 2032.0, y + 10.0]} for m, y in marks.items()
    ]
    doc["schedule_grid"] = [
        {"page": 2, "kind": "lintel", "rows": [
            _row("L1", "W8x21 WITH BOTTOM PLATE", "W8X21", '6"x6"x1/2"', ["bottom_plate"]),
            _row("L1A", "W8x21 WITH HUNG PLATE", "W8X21", '6"x6"x1/2"', ["hung_plate"]),
            _row("L5", "12F16-IB PRECAST LINTEL", None, "-"),
        ]},
        {"page": 2, "kind": "column", "rows": [
            _row("C1", 'HSS 6"x6"x1/2"', "HSS6X6X1/2", '14"x14"x3/4"'),
        ]},
        {"page": 2, "kind": "bearing_plate", "rows": [
            _row("BP3", '6"x6"x5/8"', None, '6"x6"x5/8"'),
        ]},
        {"page": 2, "kind": "icf_lintel", "rows": [
            _row("CL1", "3. DOCUMENT ACCEPTANCE STANDARD WALL WITH 2-#5 AT HEAD",
                 None, 'LOOSE ANGLE 5"x5"x3/8" REFER TO DETAIL'),
            _row("CL5", "STANDARD WALL WITH 2-#6 AT HEAD", None, "N/A N/A"),
        ]},
    ]
    return doc


class ScheduleDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.doc = _schedule_doc()
        self.prof = build_drawing_intelligence(self.doc, context_pages={"2": "SPECIFICATIONS"})
        self.by_mark = {d["mark"]: d for d in self.prof["definitions"]}

    def test_page2_schedules_are_found_despite_notes_role(self):
        self.assertEqual(self.prof["page_categories"]["2"], "schedule")
        self.assertEqual(self.by_mark["L1"]["page"], 2)
        self.assertEqual(self.by_mark["L1"]["sheet"], "S002")
        self.assertEqual(self.by_mark["L1"]["bbox"], [2020.0, 1770, 2032.0, 1780.0])
        self.assertIn("S002", self.prof["overview"])

    def test_l1_and_l1a_share_a_section_but_not_a_configuration(self):
        l1, l1a = self.by_mark["L1"], self.by_mark["L1A"]
        self.assertEqual((l1["designation"], l1a["designation"]), ("W8X21", "W8X21"))
        self.assertEqual(l1["designation_source"], "AISC v16 catalog")
        self.assertEqual(l1["configuration"], ["bottom plate"])
        self.assertEqual(l1a["configuration"], ["hung plate"])
        bearing = {"role": "bearing plate", "printed": '6"x6"x1/2"', "designation": None}
        self.assertEqual(l1["parts"], [bearing])
        self.assertEqual(l1a["parts"], [bearing])

    def test_c1_and_cl1_stay_in_their_own_schedules(self):
        c1, cl1 = self.by_mark["C1"], self.by_mark["CL1"]
        self.assertEqual((c1["component"], c1["designation"]), ("column", "HSS6X6X1/2"))
        self.assertEqual(c1["parts"][0]["role"], "base plate")
        self.assertEqual((cl1["component"], cl1["designation"]), ("icf_lintel", "L5X5X3/8"))
        self.assertEqual(cl1["configuration"], ["loose angle"])  # a condition, not a badge

    def test_bearing_plate_mark_gets_no_invented_designation(self):
        bp3 = self.by_mark["BP3"]
        self.assertEqual(bp3["mark"], "BP3")
        self.assertEqual(bp3["relation"], "mark defines plate")
        self.assertEqual(bp3["role"], "bearing plate")
        self.assertEqual(bp3["printed"], '6"x6"x5/8"')   # printed order kept
        self.assertIsNone(bp3["designation"])            # no plate designation in the catalog
        self.assertNotIn("bent", repr(bp3).lower())

    def test_no_catalog_designation_for_plate_marks(self):
        # The only "BP" in the AISC files is BP8X8, a *historical* bearing-pile
        # row outside the active catalog; plates have no catalog designation.
        from services.engineering.drawing_intelligence import _catalog_designation

        self.assertIsNone(_catalog_designation("BP8X8"))
        self.assertIsNone(_catalog_designation("BP3"))
        self.assertIsNone(_catalog_designation("PL3/4X4X6"))
        self.assertIsNone(_catalog_designation('6"x6"x5/8"'))
        self.assertEqual(_catalog_designation("L5X5X3/8"), "L5X5X3/8")

    def test_precast_and_na_rows_are_not_steel(self):
        l5, cl5 = self.by_mark["L5"], self.by_mark["CL5"]
        self.assertEqual((l5["relation"], l5["status"]), ("mark defines non-steel item", "precast"))
        self.assertIsNone(l5["designation"])
        self.assertEqual((cl5["relation"], cl5["status"]), ("mark defines no steel item", "no steel"))

    def test_packet_line_keeps_mark_designation_and_configuration(self):
        from services.engineering.drawing_intelligence import definition_line

        self.assertEqual(
            definition_line(self.by_mark["L1A"]), 'L1A → W8X21 | hung plate | bearing plate 6"x6"x1/2"'
        )
        self.assertEqual(
            definition_line(self.by_mark["BP3"]), 'BP3 → bearing plate 6"x6"x5/8" (printed size)'
        )

    def test_see_schedule_reference_is_not_a_schedule(self):
        kinds = {(s["detail"]["kind"], s["detail"]["page"]) for s in self.prof["schedule_insights"]}
        self.assertNotIn(("lintel_schedule", 3), kinds)
        refs = [r for r in self.prof["interpretation_rules"] if r["scope"] == "schedule reference"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["pages"], [3])
        self.assertIn("S002 · PDF p. 2", refs[0]["text"])

    def test_schedule_notes_become_typed_rules(self):
        by_text = {r["text"]: r for r in self.prof["interpretation_rules"]}
        each_end = by_text["BEARING PLATE SIZE APPLIES TO EACH END UNLESS NOTED OTHERWISE."]
        self.assertEqual(each_end["relation"], "default unless otherwise noted")
        self.assertEqual(each_end["scope"], "Lintel schedule")
        self.assertEqual(by_text["REFER TO SHEET S303 FOR LINTEL CONFIGURATIONS."]["relation"], "detail reference")

    def test_mixed_cells_and_undefined_brackets_are_actionable(self):
        kinds = {u["kind"]: u for u in self.prof["unresolved"]}
        self.assertIn("CL1", kinds["mixed_schedule_cells"]["text"])
        self.assertNotIn("L1,", kinds["mixed_schedule_cells"]["text"])
        self.assertIn("do not read them as member quantities", kinds["undefined_bracket_tag"]["text"])

    def test_definitions_are_never_quantities_and_tokens_untouched(self):
        self.assertTrue(all(d["is_definition_not_quantity"] for d in self.prof["definitions"]))
        self.assertIn("NOT a quantity", evidence_packet(self.prof))
        before = repr(self.doc["engineering_tokens"]) + repr(self.doc["schedule_grid"])
        build_drawing_intelligence(self.doc, context_pages={"2": "SPECIFICATIONS"})
        self.assertEqual(before, repr(self.doc["engineering_tokens"]) + repr(self.doc["schedule_grid"]))

    def test_no_schedule_grid_means_no_definitions(self):
        prof = build_drawing_intelligence(_doc({1: "ROOF FRAMING PLAN\nW16X26 TYP"}, tokens=[_tok("W16X26")]))
        self.assertEqual(prof["definitions"], [])
        self.assertIn("no MARK/SIZE schedule definitions", prof["overview"])

    def test_ruled_grid_locations_are_not_mark_definitions(self):
        self.doc["schedule_grid"].append({"page": 2, "kind": "column", "rows": [
            {**_row("A-1", "W10X33", "W10X33", ""), "mark_role": "grid_location"},
        ]})
        profile = build_drawing_intelligence(self.doc)
        self.assertNotIn("A-1", {d["mark"] for d in profile["definitions"]})

    def test_transposed_column_schedule_is_display_only(self):
        from services.engineering.schedule_grid import (
            lookup_schedule_row,
            resolve_schedule_mark,
            schedule_mark_map,
        )

        before_definitions = self.prof["definitions"]
        before_map = schedule_mark_map(self.doc["schedule_grid"])
        self.doc["schedule_grid"].append({
            "page": 2, "kind": "column", "layout": "transposed", "source": "ruled_table",
            "title": "COLUMN SCHEDULE", "bbox": [100.0, 100.0, 900.0, 400.0],
            "rows": [
                {**_row("A-1", "W10X33", "W10X33", '14"x14"x3/4"'),
                 "mark_role": "grid_location", "level": "LEVEL 1", "bbox": None},
                {**_row("B-2", "L4X4", None, ""),
                 "mark_role": "grid_location", "level": "ROOF", "bbox": None},
            ],
        })
        snapshot = repr(self.doc["schedule_grid"])
        profile = build_drawing_intelligence(self.doc, context_pages={"2": "SPECIFICATIONS"})

        a1, b2 = profile["column_locations"]
        self.assertEqual(a1, {
            "location": "A-1", "level": "LEVEL 1", "printed_size": "W10X33",
            "catalog_designation": "W10X33", "printed_base_plate": '14"x14"x3/4"',
            "schedule": "COLUMN SCHEDULE", "bbox": [100.0, 100.0, 900.0, 400.0],
            "source": "schedule_grid", "is_definition_not_quantity": True,
            "page": 2, "sheet": "S002",
        })
        # printed text only: no catalog confirmation, no completion of L4X4
        self.assertIsNone(b2["catalog_designation"])
        self.assertEqual(b2["printed_size"], "L4X4")
        self.assertIsNone(b2["printed_base_plate"])
        self.assertEqual(b2.keys(), a1.keys())  # no count / quantity field

        self.assertEqual(profile["definitions"], before_definitions)
        self.assertEqual(schedule_mark_map(self.doc["schedule_grid"]), before_map)
        self.assertEqual(repr(self.doc["schedule_grid"]), snapshot)
        self.doc["schedule_mark_map"] = schedule_mark_map(self.doc["schedule_grid"])
        self.assertEqual(resolve_schedule_mark("A-1", self.doc), "")
        self.assertIsNone(lookup_schedule_row("A-1", self.doc))
        self.assertNotIn("A-1", evidence_packet(profile))

    def test_no_transposed_schedule_means_no_column_locations(self):
        self.assertEqual(self.prof["column_locations"], [])

    def test_parsed_location_is_display_metadata_not_a_definition(self):
        parsed = {
            "raw": "A-6",
            "kind": "grid",
            "occurrences": [
                {"raw": "A-6", "grids": ["A", "6"], "offset": None, "uncertain": False}
            ],
            "uncertain": False,
        }
        self.doc["schedule_grid"].append({
            "page": 2, "kind": "column", "layout": "transposed", "source": "ruled_table",
            "title": "COLUMN SCHEDULE", "bbox": [100.0, 100.0, 900.0, 400.0],
            "rows": [{
                **_row("A-6", "W10X33", "W10X33", ""),
                "mark_role": "grid_location", "level": "ROOF", "bbox": None,
                "parsed_location": parsed,
            }],
        })
        profile = build_drawing_intelligence(self.doc)
        self.assertEqual(profile["column_locations"][0]["location"], "A-6")
        self.assertEqual(profile["column_locations"][0]["parsed_location"], parsed)
        self.assertTrue(profile["column_locations"][0]["is_definition_not_quantity"])
        self.assertNotIn("quantity", profile["column_locations"][0])
        self.assertNotIn("A-6", {item["mark"] for item in profile["definitions"]})

    def test_parsed_plate_is_copied_beside_the_printed_plate(self):
        parsed = {
            "raw": '1"x18"x18"',
            "dimensions": {"length": None, "width": None, "thickness": None},
            "ordered_dimensions": ['1"', '18"', '18"'],
            "dimension_source": "combined",
            "uncertain": True,
            "notes": None,
            "reference": None,
        }
        self.doc["schedule_grid"].append({
            "page": 2, "kind": "column", "layout": "transposed", "source": "ruled_table",
            "title": "COLUMN SCHEDULE", "bbox": [100.0, 100.0, 900.0, 400.0],
            "rows": [{
                **_row("A-7", "W10X33", "W10X33", '1"x18"x18"'),
                "mark_role": "grid_location", "level": "ROOF", "bbox": None,
                "parsed_plate": parsed, "plate_status": "present",
            }],
        })
        location = build_drawing_intelligence(self.doc)["column_locations"][0]
        self.assertEqual(location["printed_base_plate"], '1"x18"x18"')
        self.assertEqual(location["parsed_plate"], parsed)
        self.assertEqual(location["plate_status"], "present")
        self.assertNotIn("quantity", location)

    def test_ruled_table_source_ignores_same_mark_elsewhere_on_page(self):
        self.doc["schedule_grid"] = [{
            "page": 2, "kind": "column", "bbox": [100, 100, 500, 300],
            "rows": [_row("C-1", "W10X33", "W10X33", "")],
        }]
        self.doc["words"] = [
            {"page_number": 2, "text": "C-1", "bbox": [900, 900, 920, 910]},
            {"page_number": 2, "text": "C-1", "bbox": [110, 150, 130, 160]},
        ]
        profile = build_drawing_intelligence(self.doc)
        self.assertEqual(profile["definitions"][0]["bbox"], [110, 150, 130, 160])


class SummaryLlmGroundingTests(unittest.TestCase):
    def setUp(self):
        self.prof = build_drawing_intelligence(_schedule_doc(), context_pages={"2": "SPECIFICATIONS"})
        self.ids = {d["mark"]: d["id"] for d in self.prof["definitions"]}
        self.packet = evidence_packet(self.prof)

    def _run(self, response):
        class P:
            def propose(self, *_a):
                if isinstance(response, Exception):
                    raise response
                return response

        return summarize(self.prof, provider=P(), evidence_text=self.packet)

    def test_grounded_selection_is_accepted(self):
        res = self._run({
            "overview": "Schedules on S002 define the lintel marks L1 and L1A.",
            "key_facts": [{"id": self.ids["L1A"], "why": "An L1A callout is a W8X21 with a hung plate, not L1."}],
            "cautions": [],
        })
        self.assertEqual(res.method, "llm_enhanced")
        self.assertEqual(res.summary["overview_source"], "llm")
        self.assertEqual(res.summary["key_facts"][0]["id"], self.ids["L1A"])

    def test_unsupported_claims_are_rejected(self):
        res = self._run({
            "overview": "Schedules define mark L9 as a W40X593.",  # invented mark + section
            "key_facts": [
                {"id": "D99", "why": "Unknown fact."},
                {"id": self.ids["L1"], "why": "L1 is a W10X49 column."},  # section not in D(L1)
                {"id": self.ids["C1"], "why": "C1 reads as an HSS6X6X1/2 column."},
            ],
            "cautions": [{"id": self.ids["L1"], "why": "Definitions are not cautions."}],
        })
        self.assertEqual([i["id"] for i in res.summary["key_facts"]], [self.ids["C1"]])
        self.assertEqual(res.summary["cautions"], [])
        self.assertEqual(res.summary["overview_source"], "deterministic")
        self.assertEqual(res.summary["overview"], self.prof["overview"])
        self.assertIn("overview", res.dropped_claims)
        self.assertIn("key_facts:D99", res.dropped_claims)

    def test_note_that_only_restates_its_fact_is_dropped(self):
        res = self._run({
            "overview": "Schedules on S002 define the lintel marks.",
            "key_facts": [{"id": self.ids["L1"], "why": "Defines the section for lintel mark L1."}],
            "cautions": [],
        })
        self.assertEqual(res.summary["key_facts"], [])
        self.assertIn(f"key_facts:{self.ids['L1']}", res.dropped_claims)

    def test_quantity_claims_are_rejected(self):
        res = self._run({
            "overview": "The set has 12 lintels.",
            "key_facts": [{"id": self.ids["L1"], "why": "Count two beams per L1 row."}],
            "cautions": [],
        })
        self.assertIsNone(res.summary)
        self.assertEqual(res.error, "all_claims_rejected")

    def test_new_ruled_table_mark_spellings_must_be_grounded(self):
        from services.engineering.drawing_summary_llm import _grounded

        for mark in ("C-99", "BP_9", "P-1", "F5X3", "LB-101"):
            text = f"Verify {mark} before interpreting the plan callout."
            with self.subTest(mark=mark):
                self.assertIsNone(_grounded(text, "L1 defines W8X21", 220))
                self.assertEqual(_grounded(text, f"{mark} defines W8X21", 220), text)

    def test_malformed_and_failed_responses_fall_back(self):
        for response, error in (("not a dict", "non_dict_response"), (RuntimeError("boom"), "RuntimeError: boom")):
            with self.subTest(error=error):
                res = self._run(response)
                self.assertIsNone(res.summary)
                self.assertEqual(res.method, "deterministic")
                self.assertEqual(res.error, error)
        res = self._run({"overview": 3, "key_facts": ["D1", None], "cautions": "x"})
        self.assertIsNone(res.summary)


class SummaryLlmProviderSchemaTests(unittest.TestCase):
    """Regression: the Ollama provider must be told to emit the Drawing
    Summary section keys. When it was pinned to the project-rule schema the
    model could never produce project_overview/... so every summary silently
    fell back to deterministic."""

    def test_ollama_provider_honours_response_schema_override(self):
        from services.engineering import legend_llm_provider as llm
        from services.engineering import drawing_summary_llm as ds

        summary_prov = llm.get_default_provider(
            enabled=True,
            provider_name="ollama",
            api_key_env="X",
            model="llama3.1:8b",
            ollama_base_url="http://localhost:11434",
            response_schema=ds.RESPONSE_SCHEMA,
        )
        self.assertEqual(
            sorted(summary_prov._format["properties"]),
            sorted(ds.RESPONSE_SCHEMA["properties"]),
        )
        self.assertNotIn("rules", summary_prov._format["properties"])

    def test_ollama_provider_default_schema_is_still_the_project_rule_schema(self):
        from services.engineering import legend_llm_provider as llm

        default_prov = llm.get_default_provider(
            enabled=True,
            provider_name="ollama",
            api_key_env="X",
            model="m",
            ollama_base_url="u",
        )
        self.assertIn("rules", default_prov._format["properties"])


if __name__ == "__main__":
    unittest.main()
