"""Phase 2 safety defects: duplicate schedule marks, occurrence page role,
and separated quantity vs the 2L family. Each fix is behind a default-off
flag; these tests pin both the legacy default and the guarded behaviour."""

from __future__ import annotations

import unittest

from services.engineering.schedule_grid import (
    build_schedule_evidence,
    build_schedule_grids,
    schedule_mark_map,
)
from services.exact_section_predictor import resolve_trusted_explicit_section
from services.takeoff.quantity_engine import quantity_engine
from services.takeoff.takeoff_exporter import build_takeoff_rows
from services.token_extractor import extract_engineering_token_records
from tests.test_project_rule_resolver import GCDC_RULES
from tests.test_schedule_evidence_shadow import _flags, _rows

_CATALOG = {"W8X21", "W10X33"}


def _accept(token: str) -> bool:
    return token in _CATALOG


def _lintel(page: int, *body) -> list:
    return _rows(
        (100, [(100, "LINTEL"), (160, "SCHEDULE")]),
        (116, [(100, "MARK"), (200, "SIZE"), (400, "BEARING"), (470, "PLATE")]),
        *[(134 + 18 * i, cells) for i, cells in enumerate(body)],
        page=page,
    )


class DuplicateScheduleDefinitionTests(unittest.TestCase):
    def test_identical_duplicates_same_page_merge_with_provenance(self) -> None:
        words = _lintel(1, [(100, "L1"), (200, "W8X21")], [(100, "L1"), (200, "W8X21")])
        shadow = build_schedule_evidence(words, catalog_fn=_accept)
        self.assertEqual(shadow["mark_map"], {"L1": "W8X21"})
        [definition] = shadow["definitions"]
        self.assertEqual(len(definition["sources"]), 2)
        self.assertFalse(definition["review_required"])
        self.assertFalse(definition["countable_occurrence"])

    def test_identical_duplicates_across_repeated_sheets(self) -> None:
        words = _lintel(7, [(100, "L1"), (200, "W8X21")]) + _lintel(8, [(100, "L1"), (200, "W8X21")])
        shadow = build_schedule_evidence(words, catalog_fn=_accept)
        [definition] = shadow["definitions"]
        self.assertEqual({s["page_number"] for s in definition["sources"]}, {7, 8})
        self.assertEqual(shadow["conflicts"], [])

    def test_conflicting_sections_resolve_to_nothing(self) -> None:
        words = _lintel(1, [(100, "L1"), (200, "W8X21")]) + _lintel(2, [(100, "L1"), (200, "W10X33")])
        shadow = build_schedule_evidence(words, catalog_fn=_accept)
        self.assertEqual(shadow["mark_map"], {})
        self.assertEqual(shadow["definitions"], [])
        self.assertEqual(
            {r["rejection_reason"] for r in shadow["records"]}, {"conflicting_duplicate_mark"}
        )
        self.assertEqual(len(shadow["records"]), 2)

    def test_conflicting_plate_attributes_keep_section_and_require_review(self) -> None:
        words = _lintel(1, [(100, "L1"), (200, "W8X21"), (400, '6"x6"x1/2"')]) + _lintel(
            2, [(100, "L1"), (200, "W8X21"), (400, '8"x8"x1/2"')]
        )
        shadow = build_schedule_evidence(words, catalog_fn=_accept)
        [definition] = shadow["definitions"]
        self.assertEqual(definition["primary_section"], "W8X21")
        self.assertTrue(definition["review_required"])
        self.assertEqual(definition["attribute_conflicts"], ["components"])
        self.assertEqual(len(definition["components"]), 2)
        self.assertTrue(all(c["quantity"] is None for c in definition["components"]))

    def test_conflicting_lifecycle_resolves_to_nothing(self) -> None:
        existing = _rows(
            (100, [(100, "EXISTING"), (170, "LINTEL"), (220, "SCHEDULE")]),
            (116, [(100, "MARK"), (200, "SIZE")]),
            (134, [(100, "L1"), (200, "W8X21")]),
            page=2,
        )
        words = _lintel(1, [(100, "L1"), (200, "W8X21")]) + existing
        shadow = build_schedule_evidence(words, catalog_fn=_accept)
        self.assertEqual(shadow["mark_map"], {})
        self.assertEqual(
            {r["rejection_reason"] for r in shadow["records"]}, {"conflicting_lifecycle"}
        )

    def test_reversed_row_order_gives_same_output(self) -> None:
        words = (
            _lintel(1, [(100, "L1"), (200, "W8X21")], [(100, "L2"), (200, "W10X33")])
            + _lintel(2, [(100, "L1"), (200, "W10X33")])
        )
        forward = build_schedule_evidence(words, catalog_fn=_accept)
        backward = build_schedule_evidence(list(reversed(words)), catalog_fn=_accept)
        for key in ("mark_map", "definitions", "conflicts"):
            self.assertEqual(forward[key], backward[key], key)
        grids = build_schedule_grids(words, catalog_fn=_accept)
        reversed_grids = build_schedule_grids(list(reversed(words)), catalog_fn=_accept)
        self.assertEqual(
            schedule_mark_map(grids, drop_conflicts=True),
            schedule_mark_map(reversed_grids, drop_conflicts=True),
        )

    def test_legacy_map_default_is_first_row_guard_drops_conflicts(self) -> None:
        words = _lintel(1, [(100, "L1"), (200, "W8X21")]) + _lintel(2, [(100, "L1"), (200, "W10X33")])
        grids = build_schedule_grids(words, catalog_fn=_accept)
        self.assertEqual(schedule_mark_map(grids), {"L1": "W8X21"})
        self.assertEqual(schedule_mark_map(grids, drop_conflicts=True), {})


class OccurrencePageRoleTests(unittest.TestCase):
    """Identity resolution vs occurrence scope vs eligibility, through the
    real overlay (staged_pipeline._apply_project_rule_resolution)."""

    _PROFILE = {
        "abbreviation_rules": GCDC_RULES,
        "project_rules": [],
        "context_pages": {"5": "ABBREVIATIONS", "3": "GENERAL_NOTES"},
    }

    def _pred(self, page, *, eligible=True):
        return {
            "object_id": f"tok{page}",
            "document_id": "doc-gcdc",
            "source_text": {
                "raw": "HSS8X4",
                "normalized": "HSS8X4",
                "page_number": page,
                "bounding_box": [10, 20, 30, 40],
            },
            "comparison": {"match_status": "missing_dimension_field"},
            "prediction": {"final_label": None},
            "canonical": {"comparison": {"match_status": "missing_dimension_field"}, "prediction": {}},
            "needs_review": True,
            "takeoff_eligible": eligible,
            "prediction_source": "Fusion",
        }

    def _overlay(self, preds, profile=None, *, enabled=True):
        from services.staged_pipeline import _apply_project_rule_resolution

        with _flags(project_rule_page_role_enabled=enabled):
            return _apply_project_rule_resolution(
                preds, profile or self._PROFILE, set(), document_id="doc-gcdc"
            )

    def test_direct_context_call_requires_explicit_opt_in(self) -> None:
        from services.engineering.project_rule_resolver import resolve_token

        diagnostics = []
        rejected = resolve_token(
            raw_token="HSS8X4",
            page_role="LEGEND",
            abbreviation_rules=GCDC_RULES,
            diagnostics=diagnostics,
        )
        self.assertIsNone(rejected)
        self.assertEqual(diagnostics, ["context_page_occurrence"])
        evidence = resolve_token(
            raw_token="HSS8X4",
            page_role="LEGEND",
            allow_context_evidence=True,
            abbreviation_rules=GCDC_RULES,
        )
        self.assertEqual(evidence["resolved_designation"], "HSS8X4X1/4")
        self.assertEqual(evidence["application_policy"], "EVIDENCE_ONLY")
        self.assertTrue(evidence["context_evidence"])

    def test_plan_occurrence_resolves(self) -> None:
        out, applied = self._overlay([self._pred(30)])
        self.assertEqual(len(applied), 1)
        self.assertEqual(out[0]["final_label"], "HSS8X4X1/4")
        self.assertIs(out[0]["takeoff_eligible"], True)

    def test_gcdc_page_5_legend_resolves_as_evidence_only_with_provenance(self) -> None:
        out, applied = self._overlay([self._pred(5, eligible=True)])
        self.assertEqual(len(applied), 1)
        definition = out[0]
        self.assertEqual(definition["final_label"], "HSS8X4X1/4")
        self.assertEqual(definition["object_scope"], "context_definition")
        self.assertEqual(definition["occurrence_scope"], "context_definition")
        self.assertIs(definition["countable_occurrence"], False)
        self.assertIs(definition["takeoff_eligible"], False)
        provenance = definition["project_rule_resolution"]
        self.assertEqual(provenance["source_document_id"], "doc-gcdc")
        self.assertEqual(provenance["occurrence_document_id"], "doc-gcdc")
        self.assertEqual(provenance["source_page"], 5)
        self.assertEqual(provenance["occurrence_page"], 5)
        self.assertEqual(provenance["occurrence_bbox"], [10, 20, 30, 40])
        self.assertTrue(provenance["rule_id"].startswith("project-rule-"))

    def test_general_notes_occurrence_is_evidence_only(self) -> None:
        out, applied = self._overlay([self._pred(3, eligible=True)])
        self.assertEqual(len(applied), 1)
        self.assertEqual(out[0]["occurrence_scope"], "context_definition")
        self.assertIs(out[0]["takeoff_eligible"], False)

    def test_definition_on_drawing_page_resolves_identity_but_never_becomes_countable(self) -> None:
        out, applied = self._overlay([self._pred(30, eligible=False)])
        self.assertEqual(len(applied), 1)
        self.assertIs(out[0]["takeoff_eligible"], False)

    def test_unknown_only_when_role_cannot_be_determined(self) -> None:
        from services.staged_pipeline import _occurrence_page_role

        with _flags(project_rule_page_role_enabled=True):
            self.assertEqual(_occurrence_page_role(self._pred(5), self._PROFILE), "ABBREVIATIONS")
            self.assertEqual(_occurrence_page_role(self._pred(30), self._PROFILE), "DRAWING")
            no_page = self._pred(30)
            no_page["source_text"].pop("page_number")
            self.assertEqual(_occurrence_page_role(no_page, self._PROFILE), "UNKNOWN")
            self.assertEqual(
                _occurrence_page_role(self._pred(30), {"abbreviation_rules": GCDC_RULES}), "UNKNOWN"
            )

    def test_flag_off_keeps_legacy_unknown_role(self) -> None:
        out, applied = self._overlay([self._pred(5, eligible=False)], enabled=False)
        self.assertEqual(len(applied), 1)
        self.assertIs(out[0]["takeoff_eligible"], False)

    def test_cross_document_occurrence_cannot_consume_profile_rule(self) -> None:
        prediction = self._pred(30)
        prediction["document_id"] = "doc-other"
        out, applied = self._overlay([prediction])
        self.assertEqual(applied, [])
        self.assertEqual(out[0]["comparison"]["match_status"], "missing_dimension_field")

    def test_mixed_schedule_page_is_not_suppressed_wholesale(self) -> None:
        profile = {**self._PROFILE, "context_pages": {"12": "SCHEDULE"}}
        out, applied = self._overlay([self._pred(12)], profile=profile)
        self.assertEqual(len(applied), 1)
        self.assertEqual(out[0]["final_label"], "HSS8X4X1/4")
        self.assertIs(out[0]["takeoff_eligible"], True)
        self.assertNotEqual(out[0].get("occurrence_scope"), "context_definition")

    def test_exact_catalog_section_outside_definition_region_is_untouched(self) -> None:
        prediction = self._pred(30)
        prediction["source_text"].update(
            {"raw": "HSS8X4X1/4", "normalized": "HSS8X4X1/4"}
        )
        prediction["comparison"]["match_status"] = "exact_match"
        out, applied = self._overlay([prediction])
        self.assertEqual(applied, [])
        self.assertIs(out[0], prediction)

    def test_takeoff_routes_exclude_context_and_schedule_definitions(self) -> None:
        context, _ = self._overlay([self._pred(5, eligible=True)])
        schedule_definition = {
            **self._pred(12, eligible=False),
            "section": "W8X21",
            "object_scope": "context_definition",
            "occurrence_scope": "schedule_definition",
            "countable_occurrence": False,
        }
        plan, _ = self._overlay([self._pred(30, eligible=True)])
        predictions = [context[0], schedule_definition, plan[0]]
        report = quantity_engine.count(predictions)
        self.assertEqual(
            {result.section: result.physical_quantity for result in report.results},
            {"HSS8X4X1/4": 1},
        )
        rows = build_takeoff_rows(predictions, quantity_report=report)
        self.assertEqual([row["Section"] for row in rows], ["HSS8X4X1/4"])


class SeparatedQuantityTests(unittest.TestCase):
    def _words(self, *texts):
        words, x = [], 0.0
        for index, text in enumerate(texts):
            words.append({"text": text, "bbox": [x, 10, x + 6 * len(text), 18], "page_number": 1,
                          "block_no": 0, "line_no": 0, "word_no": index})
            x += 6 * len(text) + 4
        return words

    def test_fused_2l_stays_double_angle(self) -> None:
        for enabled in (False, True):
            with _flags(quantity_prefix_guard_enabled=enabled):
                self.assertEqual(resolve_trusted_explicit_section("2L4X4X1/2"), "2L4X4X1/2")

    def test_separated_count_is_a_quantity_not_the_2l_family(self) -> None:
        with _flags(quantity_prefix_guard_enabled=True):
            self.assertEqual(resolve_trusted_explicit_section("2 L4X4X1/2"), "L4X4X1/2")
            self.assertEqual(resolve_trusted_explicit_section("(2) L4X4X1/2"), "L4X4X1/2")
            self.assertEqual(resolve_trusted_explicit_section("2 HSS8X8X3/8"), "HSS8X8X3/8")

    def test_hyphenated_count_is_ambiguous_and_not_locked(self) -> None:
        with _flags(quantity_prefix_guard_enabled=True):
            self.assertIsNone(resolve_trusted_explicit_section("2-L4X4X1/2"))

    def test_tokenizer_does_not_glue_count_onto_section(self) -> None:
        words = self._words("LOAD", "2", "L1x1x1/4")
        with _flags(quantity_prefix_guard_enabled=True):
            texts = [r["text"] for r in extract_engineering_token_records(words)]
        self.assertEqual(texts, ["L1x1x1/4"])
        with _flags(quantity_prefix_guard_enabled=True):
            repaired = [r["text"] for r in extract_engineering_token_records(self._words("W18", "X", "35"))]
        self.assertEqual(repaired, ["W18 X 35"])

    def test_default_off_keeps_known_legacy_defect(self) -> None:
        with _flags(quantity_prefix_guard_enabled=False):
            self.assertEqual(resolve_trusted_explicit_section("2 L4X4X1/2"), "2L4X4X1/2")
            texts = [r["text"] for r in extract_engineering_token_records(self._words("2", "L1x1x1/4"))]
        self.assertIn("2L1x1x1/4", texts)


if __name__ == "__main__":
    unittest.main()
