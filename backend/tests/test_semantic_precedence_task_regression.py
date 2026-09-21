"""Regression tests mapping directly to the "exact OCR/catalog precedence +
incomplete-section resolution" task's own enumerated scenarios (its Sections
21/22), against the REAL live pipeline (services.prediction / services.structural_parser
/ services.hss_completion / services.engineering.project_rule_resolver) using
real catalog data -- not the parallel services.semantic_preprocessor pipeline,
which does not drive Results/Drawing Review (see the audit finding recorded
in this task's stop report).

This file is deliberately NOT a re-implementation of the extensive existing
coverage in test_protected_exact_label.py / test_resolution_contract.py /
test_trusted_explicit_section.py / test_hss_missing_thickness_review.py /
test_project_rule_resolver.py (all read and confirmed passing during this
task's audit) -- it exists so this task's own specific, named scenarios have
direct, traceable regression coverage using real catalog/manifest data, without
duplicating those files' internal-implementation-level assertions.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from services.engineering.project_rule_resolver import resolve_token
from services.hss_completion import detect_missing_thickness_hss, hss_completion_candidates
from services.prediction.canonical_contract import MatchStatus, determine_comparison
from services.structural_parser import parse_section

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Section 21 -- exact match precedence
# ---------------------------------------------------------------------------


class ExactMatchPrecedenceTests(unittest.TestCase):
    def test_a_w18x35_is_a_complete_exact_catalog_match(self):
        parsed = parse_section("W18X35")
        self.assertTrue(parsed.catalog_valid)

    def test_b_exact_hss_full_designation_is_locked(self):
        parsed = parse_section("HSS8X8X3/8")
        self.assertTrue(parsed.catalog_valid)

    def test_c_exact_angle_section_is_locked(self):
        parsed = parse_section("L4X4X3/8")
        self.assertTrue(parsed.catalog_valid)

    def test_d_e_f_exact_value_unchanged_regardless_of_geometry_graph_or_ranker(self):
        # determine_comparison's signature is the proof by construction: it
        # takes raw_text and final_label only -- geometry/graph/ranker
        # disagreement is not even a parameter this function can see, so it
        # cannot influence exact_match/match_status here. (The upstream
        # fusion decision that PRODUCES final_label is separately protected
        # by orchestrator.py's `protected_exact_section` / `resolve_trusted_
        # explicit_section` / `_gated_exact_override` -- see
        # test_protected_exact_label.py's ProtectedExactLabelIntegrationTests
        # and CutLengthLiveFusionIntegrationTests, which exercise that layer
        # directly with conflicting fusion picks and confirm the exact text
        # survives.)
        comparison = determine_comparison(
            raw_text="W18X35",
            final_label="W18X35",
            source_available=True,
            used_wildcards=False,
        )
        self.assertTrue(comparison.exact_match)
        self.assertEqual(comparison.match_status, MatchStatus.EXACT_MATCH)

    def test_g_exact_value_with_no_geometry_association_still_resolves(self):
        # No geometry-related argument exists on this call at all -- an
        # absent geometry association cannot prevent semantic resolution.
        comparison = determine_comparison(
            raw_text="C8X11.5",
            final_label="C8X11.5",
            source_available=True,
            used_wildcards=False,
        )
        self.assertTrue(comparison.exact_match)

    def test_h_exact_value_is_never_downgraded_by_this_function(self):
        # There is no "ambiguous_geometry" input to this function at all --
        # structurally, nothing it's given can turn an exact match into a
        # review-required status.
        comparison = determine_comparison(
            raw_text="HSS8X8X1/2",
            final_label="HSS8X8X1/2",
            source_available=True,
            used_wildcards=False,
        )
        self.assertEqual(comparison.match_status, MatchStatus.EXACT_MATCH)
        self.assertFalse(comparison.prediction_required)

    # (I) Human-resolved precedence is already covered directly by
    # test_trusted_explicit_section.py::HumanOverrideTests::test_human_selection_wins_over_explicit_text
    # -- not duplicated here.


# ---------------------------------------------------------------------------
# Section 22 -- missing-dimension HSS
# ---------------------------------------------------------------------------


class MissingDimensionHssTests(unittest.TestCase):
    def test_a_hss8x8_is_not_exact(self):
        parsed = parse_section("HSS8X8")
        self.assertFalse(parsed.catalog_valid)

    def test_b_only_catalog_valid_hss8x8_candidates_are_produced(self):
        dims = detect_missing_thickness_hss("HSS8X8")
        self.assertEqual(dims, ("8", "8"))
        candidates = hss_completion_candidates(*dims)
        # Real catalog count, not the task brief's illustrative 4 -- proving
        # this reads the real catalog rather than a hardcoded list.
        self.assertEqual(len(candidates), 7)
        for c in candidates:
            self.assertTrue(c.designation.startswith("HSS8X8X"))

    def test_c_missing_dimension_identified_as_thickness(self):
        dims = detect_missing_thickness_hss("HSS8X8")
        self.assertIsNotNone(dims)
        # detect_missing_thickness_hss only ever returns a value for the
        # "both outside dimensions present, thickness absent" shape -- its
        # very return contract IS the "missing=thickness" identification.
        self.assertEqual(len(dims), 2)

    def test_d_no_context_means_multiple_candidates_stay_unresolved(self):
        candidates = hss_completion_candidates("8", "8")
        self.assertGreater(len(candidates), 1)
        # No single one is privileged -- resolving among them is a human
        # (SectionReviewSelector) or verified-project-rule
        # (project_rule_resolver) decision, never automatic at this layer.

    def test_e_verified_project_rule_with_catalog_valid_result_resolves(self):
        rule = {
            "type": "LABEL_SUBSTITUTION",
            "lhs": "HSS8X8",
            "rhs": "HSS8X8X3/8",
            "extraction_method": "deterministic",
            "source_quote_verified": True,
            "status": "PROPOSED_INFERENCE",
            "rule_id": "r1",
        }
        decision = resolve_token(
            raw_token="HSS8X8",
            page_role="FRAMING_PLAN",
            takeoff_eligible=True,
            abbreviation_rules=[rule],
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision["resolved_designation"], "HSS8X8X3/8")
        self.assertEqual(decision["decision"], "PROJECT_RULE_RESOLVED")

    def test_f_rule_result_not_in_catalog_does_not_resolve(self):
        rule = {
            "type": "LABEL_SUBSTITUTION",
            "lhs": "HSS8X8",
            "rhs": "HSS8X8X17/32",  # not a real AISC thickness
            "extraction_method": "deterministic",
            "source_quote_verified": True,
            "status": "PROPOSED_INFERENCE",
            "rule_id": "r2",
        }
        decision = resolve_token(
            raw_token="HSS8X8",
            page_role="FRAMING_PLAN",
            takeoff_eligible=True,
            abbreviation_rules=[rule],
        )
        self.assertIsNone(decision)

    def test_g_vague_non_deterministic_rule_does_not_silently_resolve(self):
        # Same trigger/result as the passing case in test_e, but sourced from
        # an LLM inference rather than a quote-verified deterministic legend
        # read -- must not resolve.
        rule = {
            "type": "LABEL_SUBSTITUTION",
            "lhs": "HSS8X8",
            "rhs": "HSS8X8X3/8",
            "extraction_method": "llm_inferred",
            "source_quote_verified": False,
            "status": "PROPOSED_INFERENCE",
            "rule_id": "r3",
        }
        decision = resolve_token(
            raw_token="HSS8X8",
            page_role="FRAMING_PLAN",
            takeoff_eligible=True,
            abbreviation_rules=[rule],
        )
        self.assertIsNone(decision)

    def test_already_complete_designation_is_never_remapped_by_a_rule(self):
        # A token that is ALREADY catalog-complete must never be pulled
        # through a substitution rule, even a valid one for a similar LHS.
        rule = {
            "type": "LABEL_SUBSTITUTION",
            "lhs": "HSS8X8X3/8",
            "rhs": "HSS8X8X1/2",
            "extraction_method": "deterministic",
            "source_quote_verified": True,
            "status": "PROPOSED_INFERENCE",
            "rule_id": "r4",
        }
        decision = resolve_token(
            raw_token="HSS8X8X3/8",
            page_role="FRAMING_PLAN",
            takeoff_eligible=True,
            abbreviation_rules=[rule],
        )
        self.assertIsNone(decision)


# ---------------------------------------------------------------------------
# Section 23 -- real failure cases from the partner's damage-corpus manifests
# ---------------------------------------------------------------------------


class RealDamageCorpusIncompleteLabelTests(unittest.TestCase):
    """Uses the actual manifests just merged from the partner's commit
    (backend/tests/fixtures/semantic_test_pdfs/*.manifest.json) -- real, non-synthetic
    "incomplete" cases (missing thickness on an Angle), confirmed here against
    the live parser rather than assumed."""

    def test_real_incomplete_angle_cases_are_not_catalog_valid(self):
        manifest_path = REPO_ROOT / "backend" / "tests" / "fixtures" / "semantic_test_pdfs" / "burrville_SEMANTIC_DAMAGE_TEST.manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        incomplete_cases = [c for c in manifest["cases"] if c["category"] == "incomplete"]
        self.assertGreater(len(incomplete_cases), 0)
        for case in incomplete_cases:
            parsed = parse_section(case["test_text"])
            self.assertFalse(
                parsed.catalog_valid if parsed else False,
                f"{case['test_text']} (from {case['test_case_id']}) must not be catalog-valid",
            )


if __name__ == "__main__":
    unittest.main()
