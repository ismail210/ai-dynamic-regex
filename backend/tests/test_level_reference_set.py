"""Levels and elevations on the real reference drawings (Phase 2).

Runs the production extraction path (PDF -> schedule grid -> drawing
intelligence) and checks ``profile["levels"]`` and the column-schedule
extents against values read from the rendered sheets
(``fixtures/column_schedule/reference_levels.json``). Skips a document whose
PDF is not present; the PDFs are not in git.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "column_schedule" / "reference_levels.json"
_ROOT = Path(os.environ.get(
    "ESTIMA3D_TESTING_PROJECTS",
    r"C:\Users\Bassam\Downloads\Testing Projects-20260912T094727Z-1-001\Testing Projects",
))
_REFERENCE = json.loads(_FIXTURE.read_text(encoding="utf-8"))
_CACHE: dict = {}


def _run(spec):
    if spec["key"] not in _CACHE:
        from services.engineering import drawing_intelligence as di
        from services.engineering.schedule_grid import attach_schedule_grid
        from services.pdf_parser import extract_document_structure

        pdf = _ROOT / spec["pdf"]
        document = extract_document_structure(str(pdf))
        attach_schedule_grid(document, pdf_path=str(pdf))
        _CACHE[spec["key"]] = (document, di.build_drawing_intelligence(document))
    return _CACHE[spec["key"]]


class LevelReferenceTests(unittest.TestCase):
    def _check_summary(self, expected, document, profile):
        """Drawing Summary interpretation on the real sheets: offsets are
        locations, the framing key defines the bracket, levels link by name
        and scope, parking stays concrete, conflicts keep both values."""

        view = profile["levels"]
        by_name = {(l["schedule"], l["name"]): l for l in view["schedule_levels"]}
        building = {name: l for (schedule, name), l in by_name.items() if "BUILDING" in schedule}
        for name, (sheet, qualifiers, comparison) in expected["linked"].items():
            (match,) = [m for m in building[name]["plan_matches"] if m["association"] == "supported"]
            self.assertEqual((match["sheet"], match["plan_qualifiers"], match["comparison"]), (sheet, qualifiers, comparison), name)
            self.assertEqual(building[name]["association"], "linked")
        for name, sheets in expected["excluded_scope"].items():
            self.assertEqual([x["sheet"] for x in building[name]["excluded_scope"]], sheets)
            self.assertNotIn(sheets[0], building[name]["also_titled"])
        self.assertEqual([[o["sheet"], o["location"], o["grid"], o["offset"]["inches"]] for o in view["location_offsets"]],
                         expected["location_offsets"])
        noted = {g["sheet"] for g in view["noted_on_plans"]}
        self.assertFalse(noted & set(expected["no_values_noted_on"]))
        self.assertEqual([[e["sheet"], e["value"]] for e in view["legend_examples"]], expected["legend_examples"])
        (key,) = [r for r in profile["interpretation_rules"] if r.get("kind") == "framing_key"]
        self.assertEqual({p["token"]: p["meaning"] for p in key["parts"]}, expected["framing_key"])
        self.assertEqual([u["kind"] for u in profile["unresolved"]], expected["unresolved_kinds"])
        schedules = profile["column_schedule"]["schedules"]
        self.assertEqual({s["name"]: s["material_group"] for s in schedules if s["name"] in expected["schedule_groups"]},
                         expected["schedule_groups"])
        for mark, (material, count) in expected["material"].items():
            found = [e for e in profile["column_schedule"]["entries"] if (e.get("material") or {}).get("mark") == mark]
            self.assertEqual((found[0]["material"]["material"], len(found)), (material, count))
        self.assertEqual(profile["existing_new"]["is_renovation"], expected["renovation"])
        level, schedule_value, plan_value, difference = expected["conflict_fact"]
        (fact,) = [f for f in profile["facts"] if f["type"] == "level_conflict"]
        self.assertEqual((fact["level"], fact["schedule_value"], fact["plan_value"], fact["difference"]),
                         (level, schedule_value, plan_value, difference))
        # Each printed cell under its full printed heading; blanks stay blank.
        for mark, cells in expected["definition_cells"].items():
            definition = next(d for d in profile["definitions"] if d["mark"] == mark)
            self.assertEqual([[" > ".join(c["path"]), c["text"]] for c in definition["cells"]], cells)
        for mark, reference in expected["references"].items():
            self.assertEqual(next(d for d in profile["definitions"] if d["mark"] == mark).get("reference"), reference)
        coverage = {s["title"]: [s["printed_rows"], s["extracted_rows"], [u["printed_mark"] for u in s["unread_rows"]]]
                    for s in profile["supporting_schedules"]}
        for title, expected_coverage in expected["coverage"].items():
            self.assertEqual(coverage[title], expected_coverage)
        unresolved = [[e["sheet"], e["relative_to"], e["offset"]["inches"], [lv["name"] for lv in e["levels"]]]
                      for e in profile["levels"]["plan_elevations"] if e["status"] == "unresolved"]
        self.assertEqual(unresolved, expected["unresolved_steel"])
        if "table_only" in expected:
            self._check_review(expected, profile)
        # Display-only: the production mark map is untouched by the cells.
        self.assertFalse(any("cells" in str(v) for v in (document.get("schedule_mark_map") or {}).values()))

    def _check_review(self, expected, profile):
        """OSSE coverage audit: table-only locations, table reconciliation,
        plate marks, labels linked to definitions and the Level 2 review."""

        column = profile["column_schedule"]
        table_only = [[e["location_text"], e["sections"][0]["designation"], e["plate"]["printed"]]
                      for e in column["entries"] if e.get("assignment_only")]
        self.assertEqual(table_only, expected["table_only"])
        title, rows, matched, only = expected["location_table"]
        (table,) = column["location_tables"]
        self.assertEqual([table["title"], table["rows"], table["matched"], table["assignment_only"]], [title, rows, matched, only])
        building = next(s for s in column["schedules"] if "BUILDING" in s["name"])
        self.assertEqual({k: building["coverage"][k] for k in expected["building_coverage"]}, expected["building_coverage"])
        self.assertEqual(column["plate_tables"][0]["unused_marks"], expected["unused_plates"])
        location, printed, schedule, sizes = expected["support"]
        support = next(e for e in column["entries"] if e["location_text"] == location)["supports"][0]
        self.assertEqual([support["printed"], support["definition"]["schedule_title"], support["definition"]["sizes"]],
                         [printed, schedule, sizes])
        rc1_title, rc1_count = expected["rc1_definition"]
        self.assertEqual(len([e for e in column["entries"] if (e.get("definition") or {}).get("schedule_title") == rc1_title]),
                         rc1_count)
        printed_rows = {s["title"]: s["printed_rows"] for s in profile["supporting_schedules"]}
        for title, count in expected["more_coverage"].items():
            self.assertEqual(printed_rows[title], count, title)
        (review,) = profile["level_reviews"]
        spec = expected["level_review"]
        self.assertEqual([[i["role"], i["source"]["sheet"]] for i in review["items"]], spec["roles"])
        self.assertEqual(next(i for i in review["items"] if i["role"] == "local_annotation")["tag"]["mark"], spec["tag"])
        check = next(c for c in review["checks"] if c["printed"])
        self.assertEqual(sorted({p["sheet"] for p in check["printed"]}), spec["steel_printed_on"])
        self.assertTrue(all(not c["printed"] for c in review["checks"] if c is not check))
        status = {e["id"]: e["status"] for e in review["explanations"]}
        self.assertEqual({k: status[k] for k in spec["explanations"]}, spec["explanations"])
        self.assertEqual(sorted({p for s in profile["schedule_insights"] for p in s["source_pages"]}),
                         expected["schedule_insight_pages"])

    def _check(self, spec):
        if not (_ROOT / spec["pdf"]).is_file():
            self.skipTest(f"{spec['pdf']} is not available locally")
        document, profile = _run(spec)
        view = profile["levels"]
        levels = view["schedule_levels"]
        by_name = {level["name"]: level for level in levels}

        for schedule, expected in spec.get("schedule_levels", {}).items():
            got = [(l["name"], l["printed"]) for l in levels if l["schedule"] == schedule]
            self.assertEqual(got, [tuple(e) for e in expected], schedule)
        for name, plan_value in spec.get("conflicts", {}).items():
            self.assertTrue(by_name[name]["conflict"], name)
            self.assertIn(plan_value, [v["display"] for m in by_name[name]["plan_matches"] for v in m["values"]])
        for name, plan_value in spec.get("agrees", {}).items():
            self.assertFalse(by_name[name]["conflict"], name)
            self.assertIn("agrees", [m["comparison"] for m in by_name[name]["plan_matches"]], name)
        for name, value in spec.get("resolved", {}).items():
            self.assertEqual((by_name[name]["resolved"] or {}).get("display"), value, name)
        for name in spec.get("unresolved_see_plan", []):
            self.assertIsNone(by_name[name]["resolved"], name)

        records = view["plan_elevations"]

        def has(status, sheet, surface, value=None, area="any"):
            return any(
                r["status"] == status and r["sheet"] == sheet and r["surface"] == surface
                and (value is None or (r["value"] or {}).get("display") == value)
                and (area == "any" or r["area"] == area)
                for r in records
            )

        for sheet, surface, value in spec.get("plan_read", []):
            self.assertTrue(has("read", sheet, surface, value), (sheet, surface, value))
        for sheet, surface, value, area in spec.get("plan_derived", []):
            self.assertTrue(has("derived", sheet, surface, value, area), (sheet, surface, value, area))
        for sheet, surface in spec.get("plan_unresolved", []):
            self.assertTrue(has("unresolved", sheet, surface), (sheet, surface))
        for sheet, meaning in spec.get("noted", []):
            self.assertIn(meaning, next(g["meaning"] for g in view["noted_on_plans"] if g["sheet"] == sheet))
        for relation in spec.get("datums", []):
            self.assertIn(relation, [d["relation"] for d in view["datums"]])
        for sheet in spec.get("datum_unresolved", []):
            self.assertIn("unresolved", [d["status"] for d in view["datums"] if d["sheet"] == sheet])
        for sample, meaning in spec.get("notations", []):
            self.assertIn((sample, meaning), [(n["sample"][0], n["meaning"]) for n in view["notations"]])
        for text in spec.get("masked_not_used", []):
            self.assertNotIn(text, [l["printed"] for l in levels])

        entries = {e["location_text"] or e["mark"]: e for e in profile["column_schedule"]["entries"]}
        for key, value in spec.get("differences", {}).items():
            self.assertEqual(entries[key]["level_difference"]["display"], value, key)
        for key in spec.get("no_difference", []):
            self.assertEqual(entries[key]["level_difference"]["status"], "unresolved", key)
        if spec.get("no_computed_differences"):
            self.assertFalse([e for e in entries.values() if (e.get("level_difference") or {}).get("status") == "computed"])
        for key, box in spec.get("entry_box", {}).items():
            self.assertEqual([round(v) for v in entries[key]["bbox"]], [round(v) for v in box])

        from services.engineering.drawing_intelligence import _sheet_ids

        sheets = _sheet_ids(document)
        for page, sheet in spec.get("sheet_ids", {}).items():
            self.assertEqual(sheets.get(int(page)), sheet, page)
        for page in spec.get("no_production_rows_on_pages", []):
            # Rotated pages are read for evidence only, never into the production grid.
            self.assertFalse([g for g in document["schedule_grid"] if g["page"] == page and g["rows"]], page)
        for sheet, count in spec.get("flagged", {}).items():
            self.assertEqual(next(g["flagged"] for g in view["noted_on_plans"] if g["sheet"] == sheet), count, sheet)
        bands = {b["printed"]: b for b in view.get("level_bands") or []}
        for printed, (upper, lower) in spec.get("bands", {}).items():
            self.assertEqual((bands[printed]["upper"]["name"], bands[printed]["lower"]["name"]), (upper, lower))
            self.assertGreater(bands[printed]["schedule_rows"], 0)
            # Production rows carrying the band say it names two levels; no canonical level.
            carried = [r["level_band"] for g in document["schedule_grid"] for r in g["rows"]
                       if r.get("level_band") and " ".join(r["level_band"]["raw"].split()) == printed]
            self.assertTrue(carried)
            self.assertEqual({(b["pairing"], b["level"] is None) for b in carried}, {("unpaired", True)})
            self.assertEqual({(b["elevation_of"]["level"], b["name_of"]["level"]) for b in carried}, {(upper, lower)})
        rows = {r["mark"]: r for g in document["schedule_grid"] for r in g["rows"]}
        for mark, plate in spec.get("plates", {}).items():
            self.assertEqual(rows[mark]["plate_status"], plate["status"])
            self.assertEqual(rows[mark]["parsed_plate"]["dimensions"],
                             {k: plate[k] for k in ("thickness", "width", "length")})
            self.assertEqual(rows[mark]["plate_text"], plate["plate_text"])
            if "accessory" in plate:
                part, heading, text = plate["accessory"]
                self.assertIn({"part": part, "heading": heading, "text": text},
                              [{k: a[k] for k in ("part", "heading", "text")} for a in rows[mark]["plate_accessories"]])
        if spec.get("summary"):
            self._check_summary(spec["summary"], document, profile)
        if (spec.get("summary") or {}).get("locate"):
            from services.engineering.column_trace import (
                locate_context,
                locate_location,
            )

            context = locate_context(document, str(_ROOT / spec["pdf"]))
            for location, (sheet, state) in spec["summary"]["locate"].items():
                found = locate_location(context, location, "S2")
                self.assertEqual([found["views"][0]["sheet"], found["views"][0]["state"]], [sheet, state], location)
        if spec.get("traces"):
            from services.engineering.column_trace import trace_column

            for location, expected in spec["traces"].items():
                trace = trace_column(document, str(_ROOT / spec["pdf"]), location)
                self.assertEqual(trace["summary"]["levels_with_symbol"], expected["levels_with_symbol"], location)
                self.assertEqual(trace["ends"]["bottom"].get("level"), expected["bottom"])
                if "top" in expected:
                    self.assertEqual(trace["ends"]["top"].get("level"), expected["top"])
                for sheet, (status, toward) in expected.get("offsets", {}).items():
                    # Placed only at a validated / calibrated view scale; the side is the drawn one.
                    (offset,) = [c["offset"] for lvl in trace["levels"] for p in lvl["plans"]
                                 if p["sheet"] == sheet for c in p["candidates"]]
                    self.assertEqual(offset["status"], status, sheet)
                    self.assertEqual([s["toward"] for s in offset["sides"] if s["symbol"]], [toward], sheet)
                if "directional" in expected:
                    # A leadered COL UP is continuation evidence, kept apart from the ends.
                    self.assertEqual([[d["level"], d["sheet"], d["text"], d["direction"]]
                                      for d in trace["directional_evidence"]], expected["directional"])
                for sheet, status in expected.get("scope", {}).items():
                    self.assertIn(status, [c["scope"]["status"] for lvl in trace["levels"] for p in lvl["plans"]
                                           if p["sheet"] == sheet for c in p["candidates"]], sheet)
                for level_name, excluded in expected.get("other_scope", {}).items():
                    # Another building's plan with the same level name is listed apart, never observed.
                    (lvl,) = [lvl for lvl in trace["levels"] if lvl["name"] == level_name]
                    self.assertEqual([o["sheet"] for o in lvl["other_scope_views"]], excluded)
                    self.assertNotIn(excluded[0], [p["sheet"] for p in lvl["plans"]])
                if "top_annotations" in expected:
                    # POST UP starts a column; it never supports the top end.
                    self.assertEqual([a["text"] for a in trace["ends"]["top"]["plan_annotations"]],
                                     expected["top_annotations"])
                if "bottom_annotation" in expected:
                    self.assertIn(tuple(expected["bottom_annotation"]),
                                  [(a["sheet"], a["text"]) for a in trace["ends"]["bottom"]["plan_annotations"]])


def _make(spec):
    def test(self):
        self._check(spec)

    return test


for _spec in _REFERENCE["documents"]:
    setattr(LevelReferenceTests, f"test_{_spec['key']}", _make(_spec))


if __name__ == "__main__":
    unittest.main()
