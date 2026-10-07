"""Sheet role is the printed title. Revision words are not the issue."""

from __future__ import annotations

import unittest

from services.engineering.drawing_intelligence import _deterministic_overview
from services.engineering.sheet_navigation import (
    annotate_sheet_roles,
    classify_sheet_title,
    printed_issue,
)

# Titles printed on Burrville, OSSE, Struct.pdf, and Brandywine Structural4.
_TITLES = [
    ("GENERAL NOTES", "read_unlabeled", "general_notes", "General notes"),
    ("GENERAL NOTES & ABBREVIATIONS", "read", "general_notes", "General notes"),
    ("STATEMENT OF SPECIAL INSPECTIONS FORM", "read", "general_notes", "General notes"),
    ("SPECIAL INSPECTIONS", "read", "general_notes", "General notes"),
    ("SPECIAL INSPECTIONS, LEGEND, ABBREVIATIONS AND NOTATIONS", "read", "general_notes", "General notes"),
    ("FLOOR LOADING PLAN", "read", "loading", "Loading"),
    ("ROOF JOIST LOADING PLAN", "read", "loading", "Loading"),
    ("LOADING PLANS", "read", "loading", "Loading"),
    ("FOUNDATION AND SLAB ON GRADE PLAN - AREA A", "read_unlabeled", "foundation_plan", "Foundation plan"),
    ("FOUNDATION PLAN - OVERALL", "read", "foundation_plan", "Foundation plan"),
    ("FOUNDATION AND 1ST FLOOR FRAMING PLAN PART A", "read", "foundation_plan", "Foundation and framing plan"),
    ("FOUNDATION AND FIRST FLOOR FRAMING PLAN - PART A", "read", "foundation_plan", "Foundation and framing plan"),
    ("OSSE PARKING FOUNDATION AND FIRST FLOOR PLAN", "read", "foundation_plan", "Foundation and floor plan"),
    ("OSSE PARKING FOUNDATION & SOUTH STAIR - PART PLAN", "read", "foundation_plan", "Foundation plan"),
    ("LOW ROOF FRAMING - AREA A", "read_unlabeled", "roof_plan", "Roof plan"),
    ("ROOF FRAMING PLAN PART A", "read", "roof_plan", "Roof plan"),
    ("UPPER ROOF FRAMING PLAN", "read", "roof_plan", "Roof plan"),
    ("HIGH ROOF FRAMING PLAN - OVERALL", "read", "roof_plan", "Roof plan"),
    ("OSSE FACILITY ROOF PLAN", "read", "roof_plan", "Roof plan"),
    ("SECOND FLOOR FRAMING - AREA C", "read_unlabeled", "framing_plan", "Framing plan"),
    ("UPPER FLOOR FRAMING PLAN PART A", "read", "framing_plan", "Framing plan"),
    ("LEVEL 2 FRAMING PLAN - OVERALL", "read", "framing_plan", "Framing plan"),
    ("ENLARGED FRAMING PLANS", "read", "framing_plan", "Framing plan"),
    ("OSSE FACILITY SECOND FLOOR PLAN", "read", "framing_plan", "Floor plan"),
    ("BRACED FRAME ELEVATIONS", "read", "elevation", "Elevation"),
    ("ELEVATIONS", "read", "elevation", "Elevation"),
    ("OSSE BUILDING SCREEN WALL ELEVATIONS", "read", "elevation", "Elevation"),
    ("FOUNDATION SECTIONS", "read_unlabeled", "section", "Section"),
    ("FRAMING SECTIONS", "read_unlabeled", "section", "Section"),
    ("SECTIONS", "read", "section", "Section"),
    ("SUPERSTURCTURE SECTIONS", "read", "section", "Section"),
    ("TYPICAL DETAILS", "read", "detail", "Detail"),
    ("TYPICAL FOUNDATION DETAILS", "read", "foundation_details", "Foundation details"),
    ("TYPICAL SLAB ON GRADE DETAILS", "read", "foundation_details", "Foundation details"),
    ("CONCRETE TYPICAL DETAILS", "read", "concrete_details", "Concrete details"),
    ("STEEL TYPICAL DETAILS", "read", "steel_details", "Steel details"),
    ("TYPICAL STEEL FRAMING DETAILS", "read", "steel_details", "Steel details"),
    ("TYPICAL STEEL JOIST FRAMING DETAILS", "read", "steel_details", "Steel details"),
    ("STEEL MOMENT FRAME DETAILS", "read", "steel_details", "Steel details"),
    ("MASONRY TYPICAL DETAILS", "read", "masonry_details", "Masonry details"),
    ("MASONRY DETAILS", "read", "masonry_details", "Masonry details"),
    ("BRACED FRAME DETAILS", "read", "detail", "Detail"),
    ("TYPICAL COMPOSITE FRAMING DETAILS", "read", "detail", "Detail"),
    ("INSPECTION TABLES AND SCHEDULES", "read_unlabeled", "schedule", "Schedule"),
    ("COLUMN SCHEDULE", "read", "schedule", "Schedule"),
    ("SCHEDULES", "read", "schedule", "Schedule"),
    ("OSSE PARKING AND OSSE BUILDING COLUMN SCHEDULE", "read", "schedule", "Schedule"),
]


class SheetRoleTests(unittest.TestCase):
    def test_printed_titles_from_the_four_sets(self):
        for title, status, role, label in _TITLES:
            with self.subTest(title):
                got = classify_sheet_title(title, status)
                self.assertEqual(got["sheet_role"], role)
                self.assertEqual(got["sheet_role_label"], label)
                self.assertEqual(got["classification_status"], "read")

    def test_two_drawing_types_stay_review(self):
        got = classify_sheet_title("NORTH STAIR & ELEVATOR PLANS AND ELEVATIONS", "read")
        self.assertIsNone(got["sheet_role"])
        self.assertEqual(got["classification_status"], "review")
        self.assertCountEqual(got["role_candidates"], ["plan", "elevation"])

    def test_untitled_and_unnamed_titles_are_not_guessed(self):
        unnamed = classify_sheet_title("DESIGN TABLES", "read")
        self.assertIsNone(unnamed["sheet_role"])
        self.assertEqual(unnamed["classification_status"], "review")
        missing = classify_sheet_title(None, "unresolved")
        self.assertEqual(missing["classification_status"], "unresolved")
        ambiguous = classify_sheet_title("GENERAL NOTES", "ambiguous")
        self.assertEqual(ambiguous["classification_status"], "review")
        self.assertIsNone(ambiguous["sheet_role"])

    def test_a_dimension_is_not_a_sheet_role(self):
        for text in ("4'-6\"", "10'-0\"", "14'-8\""):
            got = classify_sheet_title(text, "read")
            self.assertIsNone(got["sheet_role"], text)
            self.assertEqual(got["classification_status"], "review")

    def test_annotation_keeps_the_sheet_id_and_does_not_mutate(self):
        index = {"version": "sheet_index_v1", "pages": [{
            "page": 10, "sheet_id": "S-122-O", "sheet_id_status": "read",
            "sheet_title": "OSSE FACILITY SECOND FLOOR PLAN", "title_status": "read",
        }]}
        annotated = annotate_sheet_roles(index)
        self.assertNotIn("sheet_role", index["pages"][0])
        self.assertEqual(annotated["pages"][0]["sheet_id"], "S-122-O")
        self.assertEqual(annotated["pages"][0]["sheet_role"], "framing_plan")
        self.assertEqual(annotated["role_version"], "sheet_role_v1")


class IssueSentenceTests(unittest.TestCase):
    def test_revision_row_is_not_the_issue(self):
        pages = [{
            "page": 1, "issue": "65% DESIGN DEVELOPMENT", "issue_status": "read",
            "revision": {"rows": [{"description": "FTG PERMIT"}]},
        }]
        self.assertEqual(printed_issue(pages), "65% DESIGN DEVELOPMENT")
        self.assertNotIn("PERMIT", printed_issue(pages))

    def test_a_split_issue_is_counted(self):
        pages = [
            {"issue": "BID SET", "issue_status": "read"},
            {"issue": "BID SET", "issue_status": "read"},
            {"issue": "ADDENDUM 1", "issue_status": "read"},
        ]
        self.assertEqual(printed_issue(pages), "BID SET (2 of 3 sheets)")

    def test_overview_quotes_the_title_block_issue_and_keeps_the_hyphen(self):
        text = _deterministic_overview({
            "page_count": 43,
            "scope_signals": [{"detail": {"present": True, "label": "Permit set"}}],
            "column_schedule": {"schedules": [
                {"page": 42, "sheet": "S600", "material_group": "steel"},
            ]},
            "definitions": [],
            "steel_system": {"families": []},
            "existing_new": {},
            "sheet_index": {"pages": [{
                "page": 42, "sheet_id": "S-600", "sheet_id_status": "read",
                "issue": "65% DESIGN DEVELOPMENT", "issue_status": "read",
            }]},
        })
        self.assertIn("issue: 65% DESIGN DEVELOPMENT", text)
        self.assertIn("S-600", text)
        self.assertNotIn("S600", text)
        self.assertNotIn("ermit", text)


if __name__ == "__main__":
    unittest.main()
