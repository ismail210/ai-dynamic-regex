"""A-T coverage for the gated LABEL_SUBSTITUTION resolver
(services.engineering.project_rule_resolver), objective #1.

GCDC has exactly one naturally occurring bare "HSS8X4" token in the whole
document (every real W/HSS drawing-plan occurrence elsewhere already
carries a complete designation) -- and it is a `takeoff_eligible=False`
schedule/legend-adjacent object (see
StagedPipelineOverlayTests.test_takeoff_ineligible_occurrence_resolves_
identity_but_stays_ineligible for the real-shape regression). Most of this
file still exercises the resolver with a SYNTHETIC injected drawing-page
token for isolated gate coverage, using the REAL GCDC-extracted rule
``HSS8X4 -> HSS8X4X1/4``.
"""

from __future__ import annotations

import unittest

from services.engineering import project_rule_resolver as rr


def _rule(lhs, rhs, family, *, page=5, verified=True, method="deterministic",
          status="PROPOSED_INFERENCE"):
    return {
        "lhs": lhs,
        "rhs": rhs,
        "lhs_family": family,
        "rhs_family": family,
        "rhs_catalog_valid": True,
        "source_page": page,
        "source_quote": f'"{lhs.lower()}" = {rhs.lower()}',
        "source_quote_verified": verified,
        "extraction_method": method,
        "status": status,
    }


GCDC_RULES = [
    _rule("HSS8X4", "HSS8X4X1/4", "HSS"),
    _rule("W8", "W8X10", "W"),
    _rule("W12", "W12X19", "W"),
    _rule("C8", "C8X11.5", "C"),
]


_LAST_DIAG = []


def _resolve(token, **kw):
    kw.setdefault("abbreviation_rules", GCDC_RULES)
    kw.setdefault("page_role", "FRAMING_PLAN")
    _LAST_DIAG.clear()
    return rr.resolve_token(raw_token=token, diagnostics=_LAST_DIAG, **kw)


def _last_gate():
    return _LAST_DIAG[-1] if _LAST_DIAG else None


class LabelSubstitutionResolverTests(unittest.TestCase):
    # A / B -- the synthetic GCDC end-to-end
    def test_A_synthetic_hss8x4_resolves_to_full_designation(self):
        out = _resolve("HSS8X4")
        self.assertIsNotNone(out)
        self.assertEqual(out["decision"], "PROJECT_RULE_RESOLVED")
        self.assertEqual(out["resolved_designation"], "HSS8X4X1/4")
        self.assertEqual(out["decision_source"], "verified_project_rule")
        self.assertEqual(out["source_page"], 5)
        self.assertEqual(out["application_policy"], "AUTO_ELIGIBLE")

    def test_B_w8_resolves_to_w8x10(self):
        self.assertEqual(_resolve("W8")["resolved_designation"], "W8X10")

    # C -- bare "8" cannot become W8X10 (token establishes no family)
    def test_C_bare_number_rejected(self):
        self.assertIsNone(_resolve("8"))
        self.assertEqual(_last_gate(), "token_unparsed_or_familyless")

    # D -- "8X4" cannot become HSS (token establishes no family)
    def test_D_dimensions_without_family_rejected(self):
        self.assertIsNone(_resolve("8X4"))
        self.assertEqual(_last_gate(), "token_unparsed_or_familyless")

    # E -- W14X61 must NOT be rewritten by a W14 rule
    def test_E_complete_designation_not_rewritten_by_shorter_lhs(self):
        rules = GCDC_RULES + [_rule("W14", "W14X22", "W")]
        self.assertIsNone(_resolve("W14X61", abbreviation_rules=rules))
        self.assertEqual(_last_gate(), "token_already_complete")

    # F -- an already-complete HSS8X4X3/8 stays unchanged
    def test_F_complete_hss_unchanged(self):
        self.assertIsNone(_resolve("HSS8X4X3/8"))
        self.assertEqual(_last_gate(), "token_already_complete")

    # G -- invalid catalog RHS rejected
    def test_G_invalid_catalog_rhs_rejected(self):
        rules = [_rule("HSS8X4", "HSS8X4X9/1", "HSS")]
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=rules))
        self.assertEqual(_last_gate(), "rhs_not_catalog_valid")

    # H -- wrong page scope rejected (LLM rule restricts to FRAMING_PLAN)
    def test_H_page_role_outside_llm_rule_scope_rejected(self):
        project_rules = [
            {
                "type": "LABEL_SUBSTITUTION",
                "trigger": "HSS8X4",
                "result": "HSS8X4X1/4",
                "scope": {"page_roles": ["FRAMING_PLAN"], "uno_applies": False},
            }
        ]
        self.assertIsNone(_resolve("HSS8X4", page_role="DETAIL", project_rules=project_rules))
        self.assertEqual(_last_gate(), "page_role_outside_rule_scope")
        # ...and the same token on a FRAMING_PLAN still resolves.
        self.assertIsNotNone(_resolve("HSS8X4", page_role="FRAMING_PLAN", project_rules=project_rules))

    # I -- a context-page occurrence is never resolved
    def test_I_context_page_occurrence_rejected(self):
        self.assertIsNone(_resolve("HSS8X4", page_role="ABBREVIATIONS"))
        self.assertEqual(_last_gate(), "context_page_occurrence")

    # I2 -- takeoff eligibility and identity resolution are orthogonal
    # (task requirement: resolving a label must never depend on, or change,
    # whether the occurrence counts toward the takeoff quantity -- a
    # schedule/legend-definition occurrence can be correctly excluded from
    # the takeoff count while its label is still fully knowable). Real-world
    # case: GCDC's only bare "HSS8X4" token is exactly this shape.
    def test_I2_takeoff_ineligible_occurrence_still_resolves_identity(self):
        decision = _resolve("HSS8X4", takeoff_eligible=False)
        self.assertIsNotNone(decision)
        self.assertEqual(decision["resolved_designation"], "HSS8X4X1/4")

    # J -- conflicting deterministic rules block auto-resolution
    def test_J_conflicting_rules_rejected(self):
        rules = [_rule("HSS8X4", "HSS8X4X1/4", "HSS"), _rule("HSS8X4", "HSS8X4X3/8", "HSS")]
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=rules))
        self.assertEqual(_last_gate(), "conflicting_deterministic_rules")

    def test_J2_conflicting_llm_result_rejected(self):
        project_rules = [
            {"type": "LABEL_SUBSTITUTION", "trigger": "HSS8X4", "result": "HSS8X4X3/8", "scope": {}}
        ]
        self.assertIsNone(_resolve("HSS8X4", project_rules=project_rules))
        self.assertEqual(_last_gate(), "llm_rule_result_conflict")

    # K -- human-reviewed result wins (resolver refuses)
    def test_K_human_reviewed_precedence(self):
        self.assertIsNone(_resolve("HSS8X4", human_reviewed=True))
        self.assertEqual(_last_gate(), "human_reviewed_precedence")

    # L -- a derived insight / non-deterministic rule can never resolve
    def test_L_non_deterministic_rule_rejected(self):
        rules = [_rule("HSS8X4", "HSS8X4X1/4", "HSS", method="llm_proposed")]
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=rules))
        self.assertEqual(_last_gate(), "rule_not_deterministic")

    # M -- unverified quote rejected
    def test_M_unverified_quote_rejected(self):
        rules = [_rule("HSS8X4", "HSS8X4X1/4", "HSS", verified=False)]
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=rules))
        self.assertEqual(_last_gate(), "quote_not_verified")

    # N -- cross-family rule can never fire (defence in depth; the
    # deterministic extractor already blocks these)
    def test_N_family_mismatch_rejected(self):
        rules = [dict(_rule("W8", "W8X10", "W"), lhs_family="W", rhs_family="W")]
        # token is HSS8X4 but only a W8 rule exists -> no LHS match
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=rules))
        self.assertEqual(_last_gate(), "no_matching_rule")


def _llm_rule(trigger, result, *, page=5, quote=None, status="VALIDATED", scope=None, rule_id="RULE_001"):
    return {
        "type": "LABEL_SUBSTITUTION",
        "trigger": trigger,
        "result": result,
        "source_page": page,
        "source_quote": quote or f"Shorthand {trigger} on the framing plans means {result} per project convention",
        "validation_status": status,
        "scope": scope or {"page_roles": [], "uno_applies": False},
        "id": rule_id,
    }


class LlmAssistedResolutionTests(unittest.TestCase):
    """Section 4/7/8 of the task: an LLM-sourced LABEL_SUBSTITUTION rule may
    resolve a token by itself only when NO deterministic rule exists AND it
    independently passes every safeguard here -- never trusted on its own
    say-so, regardless of what extraction-time validation already did."""

    def test_a_validated_grounded_rule_resolves_with_llm_assisted_provenance(self):
        out = _resolve("HSS8X4", abbreviation_rules=[], project_rules=[_llm_rule("HSS8X4", "HSS8X4X1/4")])
        self.assertIsNotNone(out)
        self.assertEqual(out["resolved_designation"], "HSS8X4X1/4")
        self.assertEqual(out["extraction_method"], "llm_assisted")

    def test_b_deterministic_rule_always_preferred_over_llm_rule(self):
        det = [_rule("HSS8X4", "HSS8X4X1/4", "HSS")]
        llm = [_llm_rule("HSS8X4", "HSS8X4X1/4")]
        out = _resolve("HSS8X4", abbreviation_rules=det, project_rules=llm)
        self.assertIsNotNone(out)
        self.assertEqual(out["extraction_method"], "deterministic")

    def test_c_result_not_grounded_in_quote_is_a_hallucination_and_is_rejected(self):
        # The quote never mentions the claimed result -- must not resolve.
        rule = _llm_rule("HSS8X4", "HSS8X4X3/8", quote="HSS8X4 is used extensively on this project.")
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=[], project_rules=[rule]))
        self.assertEqual(_last_gate(), "llm_rule_not_grounded")

    def test_d_catalog_invalid_destination_is_rejected(self):
        rule = _llm_rule("HSS8X4", "HSS8X4X99", quote="HSS8X4 means HSS8X4X99 on this project.")
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=[], project_rules=[rule]))
        self.assertEqual(_last_gate(), "llm_rule_not_grounded")

    def test_e_unvalidated_rule_is_rejected(self):
        rule = _llm_rule("HSS8X4", "HSS8X4X1/4", status="PROPOSED_INFERENCE")
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=[], project_rules=[rule]))

    def test_f_conflicting_llm_rules_for_same_trigger_are_rejected(self):
        rules = [_llm_rule("HSS8X4", "HSS8X4X1/4"), _llm_rule("HSS8X4", "HSS8X4X3/8", rule_id="RULE_002")]
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=[], project_rules=rules))
        self.assertEqual(_last_gate(), "conflicting_llm_rules")

    def test_g_family_mismatch_rejected(self):
        rule = _llm_rule("HSS8X4", "W8X10", quote="HSS8X4 means W8X10 on this project.")
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=[], project_rules=[rule]))

    def test_h_scope_restricted_llm_rule_respects_page_role(self):
        rule = _llm_rule("HSS8X4", "HSS8X4X1/4", scope={"page_roles": ["DETAIL"], "uno_applies": False})
        self.assertIsNone(_resolve("HSS8X4", abbreviation_rules=[], project_rules=[rule], page_role="FRAMING_PLAN"))
        self.assertEqual(_last_gate(), "page_role_outside_rule_scope")
        out = _resolve("HSS8X4", abbreviation_rules=[], project_rules=[rule], page_role="DETAIL")
        self.assertIsNotNone(out)

    def test_i_gt_workbook_presence_cannot_influence_resolution(self):
        """No-GT-leakage regression (task Section 34): resolve_token has no
        GT/benchmark parameter at all -- proof by construction that the same
        rule resolves identically regardless of any external ground truth."""
        rule = _llm_rule("HSS8X4", "HSS8X4X1/4")
        out_a = _resolve("HSS8X4", abbreviation_rules=[], project_rules=[rule])
        out_b = _resolve("HSS8X4", abbreviation_rules=[], project_rules=[rule])
        self.assertEqual(out_a, out_b)
        self.assertNotIn("ground_truth", rr.resolve_token.__code__.co_varnames)

    # O -- no rule at all
    def test_O_no_matching_rule(self):
        self.assertIsNone(_resolve("W16", abbreviation_rules=[_rule("W8", "W8X10", "W")]))
        self.assertEqual(_last_gate(), "no_matching_rule")

    # P -- normalization: lower-case / spaced token still matches
    def test_P_normalization_tolerant(self):
        self.assertEqual(_resolve("hss 8 x 4")["resolved_designation"], "HSS8X4X1/4")

    # Q -- empty token
    def test_Q_empty_token(self):
        self.assertIsNone(_resolve(""))


class ReadTimeOverlayTests(unittest.TestCase):
    """The synthetic drawing-page occurrence, end to end through
    staged_pipeline._apply_project_rule_resolution."""

    def _pred(self, raw, status="missing_dimension_field", object_id="tok1"):
        return {
            "object_id": object_id,
            "source_text": {"raw": raw, "normalized": raw, "page_number": 30},
            "comparison": {"match_status": status},
            "prediction": {"final_label": None},
            "canonical": {
                "comparison": {"match_status": status},
                "prediction": {"final_label": None},
            },
            "needs_review": True,
            "takeoff_eligible": True,
        }

    def _overlay(self, predictions, reviewed_ids=None):
        from services.staged_pipeline import _apply_project_rule_resolution

        return _apply_project_rule_resolution(
            predictions,
            {"abbreviation_rules": GCDC_RULES, "project_rules": []},
            reviewed_ids or set(),
        )

    def test_synthetic_hss8x4_resolved_end_to_end(self):
        out, applied = self._overlay([self._pred("HSS8X4")])
        self.assertEqual(len(applied), 1)
        pred = out[0]
        self.assertEqual(pred["comparison"]["match_status"], "project_rule_resolved")
        self.assertEqual(pred["canonical"]["comparison"]["match_status"], "project_rule_resolved")
        self.assertEqual(pred["final_label"], "HSS8X4X1/4")
        self.assertEqual(pred["canonical"]["prediction"]["final_label"], "HSS8X4X1/4")
        self.assertFalse(pred["needs_review"])
        self.assertEqual(pred["project_rule_resolution"]["decision_source"], "verified_project_rule")
        # raw OCR provenance is preserved
        self.assertEqual(pred["source_text"]["raw"], "HSS8X4")

    def test_resolved_prediction_gets_high_semantic_confidence(self):
        """A verified project rule is High/Verified by construction -- the
        Confidence column must not keep showing the stale near-zero fusion
        score from before the rule was consulted."""

        out, _ = self._overlay([self._pred("HSS8X4")])
        pred = out[0]
        self.assertEqual(pred["confidence"], 1.0)
        self.assertEqual(pred["confidence_basis"], "verified_project_rule")
        self.assertEqual(pred["review_status"], "auto_accepted")
        self.assertEqual(pred["canonical"]["prediction"]["final_confidence"], 1.0)
        self.assertTrue(pred["canonical"]["prediction"]["confidence_is_calibrated"])

    def test_already_exact_prediction_untouched(self):
        out, applied = self._overlay([self._pred("HSS8X4X1/2", status="exact_match")])
        self.assertEqual(applied, [])
        self.assertEqual(out[0]["comparison"]["match_status"], "exact_match")

    def test_human_reviewed_object_skipped(self):
        out, applied = self._overlay([self._pred("HSS8X4")], reviewed_ids={"tok1"})
        self.assertEqual(applied, [])
        self.assertEqual(out[0]["comparison"]["match_status"], "missing_dimension_field")

    def test_no_abbreviation_rules_is_a_noop(self):
        from services.staged_pipeline import _apply_project_rule_resolution

        preds = [self._pred("HSS8X4")]
        out, applied = _apply_project_rule_resolution(preds, {"abbreviation_rules": []}, set())
        self.assertEqual(applied, [])
        self.assertIs(out, preds)

    def test_takeoff_ineligible_occurrence_resolves_identity_but_stays_ineligible(self):
        """Real GCDC shape (task Section 12): the only bare HSS8X4 token in
        that project is a takeoff_eligible=False schedule/legend-adjacent
        object. Its label must resolve while takeoff_eligible itself, which
        governs quantity, is left completely untouched."""

        pred = self._pred("HSS8X4")
        pred["takeoff_eligible"] = False
        out, applied = self._overlay([pred])
        self.assertEqual(len(applied), 1)
        self.assertEqual(out[0]["final_label"], "HSS8X4X1/4")
        self.assertFalse(out[0]["needs_review"])
        self.assertIs(out[0]["takeoff_eligible"], False)

    def test_resolved_prediction_clears_stale_candidate_sections(self):
        """Section 27: a resolved row must not still look like it needs a
        7-option picker. Regression for a real bug found while implementing
        this fix -- clearing candidate_sections alone re-triggers
        enrich_missing_thickness_hss_predictions's own re-derivation when the
        result is projected a second time; see hss_review_enrichment's
        project_rule_resolution skip-check, exercised together with this."""

        pred = self._pred("HSS8X4")
        pred["candidate_sections"] = [{"designation": "HSS8X4X1/4"}, {"designation": "HSS8X4X3/8"}]
        pred["completion_status"] = "missing_thickness"
        out, _ = self._overlay([pred])
        self.assertEqual(out[0]["candidate_sections"], [])
        self.assertNotIn("completion_status", out[0])

    def test_resolved_prediction_clears_canonical_needs_review(self):
        """predictionContract.js reads `canonical.needs_review ?? result.
        needs_review` -- a stale True on the canonical copy would shadow the
        corrected top-level value and keep the picker eligible client-side."""

        pred = self._pred("HSS8X4")
        pred["canonical"]["needs_review"] = True
        out, _ = self._overlay([pred])
        self.assertFalse(out[0]["canonical"]["needs_review"])

    def test_resolved_prediction_replaces_stale_fusion_explanation(self):
        """Section 29: the "why selected" explanation must state the real
        reasoning for a project-rule resolution, never a leftover
        statistical-fusion narrative from before the rule was consulted."""

        pred = self._pred("HSS8X4")
        pred["explanation"] = {
            "reasons": ["Fallback attention selected HSS8X4X1/2 with score 0.358"],
        }
        out, _ = self._overlay([pred])
        why = out[0]["explanation"]["why_selected"]
        self.assertTrue(any("Verified project rule" in reason for reason in why))
        # source_page comes from the matched RULE (where the legend states
        # the substitution, page 5 in GCDC_RULES) -- not from the
        # occurrence's own page_number (30), which is just where this
        # particular token sits on the drawing.
        self.assertTrue(any("p. 5" in reason for reason in why))
        self.assertFalse(any("Fallback attention" in reason for reason in why))


class NoGroundTruthLeakageTests(unittest.TestCase):
    """Task Section 34 (critical constraint): project-rule resolution must
    use ONLY PDF evidence + Drawing Intelligence/legend profile + the AISC
    catalog -- never Excel ground truth, benchmark discrepancy, or expected-
    section frequency. Proven two ways: by signature (no GT-shaped
    parameter exists anywhere on the resolution call chain to leak through)
    and by behavior (the identical inputs produce the identical decision
    regardless of any GT-shaped extra data present in the surrounding
    document)."""

    def test_resolve_token_signature_has_no_ground_truth_parameter(self):
        import inspect

        params = set(inspect.signature(rr.resolve_token).parameters)
        for leaky_name in ("ground_truth", "expected_excel", "gt", "excel_path", "benchmark"):
            self.assertNotIn(leaky_name, params)

    def test_apply_project_rule_resolution_signature_has_no_ground_truth_parameter(self):
        import inspect

        from services.staged_pipeline import _apply_project_rule_resolution

        params = set(inspect.signature(_apply_project_rule_resolution).parameters)
        for leaky_name in ("ground_truth", "expected_excel", "gt", "excel_path", "benchmark"):
            self.assertNotIn(leaky_name, params)

    def test_same_document_resolves_identically_with_or_without_gt_shaped_data_present(self):
        """A `document`/`legend_profile` dict carrying an unrelated
        `expected_excel` key (as a real analyzed-with-GT document does, see
        services.staged_pipeline._analysis_metadata's own `expected_excel`
        exclusion list) must not change the resolution in any way -- the
        resolver only ever reads `abbreviation_rules`/`project_rules` off
        the profile it is handed."""

        from services.staged_pipeline import _apply_project_rule_resolution

        def _pred():
            return {
                "object_id": "tok1",
                "source_text": {"raw": "HSS8X4", "normalized": "HSS8X4", "page_number": 30},
                "comparison": {"match_status": "missing_dimension_field"},
                "prediction": {"final_label": None},
                "canonical": {
                    "comparison": {"match_status": "missing_dimension_field"},
                    "prediction": {"final_label": None},
                },
                "needs_review": True,
                "takeoff_eligible": True,
            }

        profile_without_gt = {"abbreviation_rules": GCDC_RULES, "project_rules": []}
        profile_with_gt_shaped_noise = {
            "abbreviation_rules": GCDC_RULES,
            "project_rules": [],
            # Not a real field on legend_profile -- injected here only to
            # prove the resolver ignores anything GT-shaped even if present.
            "expected_excel_ground_truth": {"HSS8X4": "HSS8X4X3/8"},
        }

        out_a, applied_a = _apply_project_rule_resolution(
            [_pred()], profile_without_gt, set()
        )
        out_b, applied_b = _apply_project_rule_resolution(
            [_pred()], profile_with_gt_shaped_noise, set()
        )
        self.assertEqual(out_a[0]["final_label"], out_b[0]["final_label"])
        self.assertEqual(out_a[0]["final_label"], "HSS8X4X1/4")
        self.assertEqual(applied_a, applied_b)


class ServedAnalysisStatusTagsRegressionTests(unittest.TestCase):
    """Real bug found via the live UI: `run_analysis_stage`'s cache-hit
    early-return (POST /api/documents/{id}/analyze -- the only call the
    frontend's AnalyzeLauncher actually makes) returned
    ``load_cached_analysis()``'s dict directly, never routing it through
    ``analysis_response()`` -- the one place ``status_tags`` gets attached
    (services.prediction.status_classification.classify_prediction_status).
    Every served prediction therefore had `status_tags: null`, even though
    project-rule resolution itself was already correct. This test exercises
    the FINAL served shape end-to-end: project-rule resolution ->
    analysis_response's status-tag classification -> the served row, using
    the exact composition ``run_analysis_stage`` now performs."""

    def test_final_served_row_has_section_match_status_and_status_tags_together(self):
        from services.staged_pipeline import analysis_response

        predictions = [
            {
                "object_id": "schedule_1",
                "source_text": {"raw": "HSS8X4", "normalized": "HSS8X4", "page_number": 5},
                "raw_text": "HSS8X4",
                "normalized_text": "HSS8X4",
                "comparison": {"match_status": "missing_dimension_field"},
                "prediction": {"final_label": None},
                "canonical": {
                    "comparison": {"match_status": "missing_dimension_field"},
                    "prediction": {"final_label": None},
                    "needs_review": True,
                },
                "needs_review": True,
                "takeoff_eligible": False,
            }
        ]
        legend_profile = {"abbreviation_rules": GCDC_RULES, "project_rules": []}

        # Step 1: the read-time overlay this task's earlier fix added.
        from services.staged_pipeline import _apply_project_rule_resolution

        resolved, rule_resolutions = _apply_project_rule_resolution(
            predictions, legend_profile, set()
        )
        self.assertEqual(len(rule_resolutions), 1)

        # Step 2: the FINAL API projection -- the exact function
        # run_analysis_stage's cache-hit branch now calls (it did not
        # before this fix).
        served = analysis_response(
            {"predictions": resolved, "cached": True}
        )["predictions"]

        row = served[0]
        self.assertEqual(row["section"], "HSS8X4X1/4")
        self.assertEqual(row["comparison"]["match_status"], "project_rule_resolved")
        self.assertFalse(row["needs_review"])
        self.assertIn("project_rule", row["status_tags"])
        # Section 11: identity resolved, quantity/eligibility untouched.
        self.assertIs(row["takeoff_eligible"], False)
        # High/Verified confidence, never the stale near-zero fusion score.
        self.assertEqual(row["confidence"], 1.0)


class ValidationSyncTests(unittest.TestCase):
    """A verified project-rule resolution must flip the whole-document
    validation pass's per-token entry to PASS too -- that pass runs on the
    pre-resolution fusion output and is not itself re-run by the overlay, so
    without this sync the Validation column would keep showing FAIL (with
    stale low-confidence/geometry-conflict issues) for an already-resolved,
    high-confidence row."""

    def test_resolved_object_validation_entry_becomes_pass(self):
        from services.staged_pipeline import _sync_validation_with_rule_resolutions

        predictions = [{"object_id": "schedule_1", "component_id": "Component_1"}]
        rule_resolutions = [
            {"object_id": "schedule_1", "resolved_designation": "HSS8X4X1/4"}
        ]
        validation = {
            "tokens": [
                {
                    "component_id": "Component_1",
                    "status": "FAIL",
                    "confidence": 0.0,
                    "section": "HSS8X4X1/2",
                    "predicted_shape": "HSS8X4X1/2",
                    "detected_issues": ["prediction_confidence"],
                    "issues": [{"type": "prediction_confidence"}],
                    "reasons": ["Prediction confidence is critically low (0%)"],
                    "correction_suggestions": [{"section": "HSS8X8"}],
                },
                {"component_id": "Component_other", "status": "PASS"},
            ]
        }

        synced = _sync_validation_with_rule_resolutions(
            validation, predictions, rule_resolutions
        )
        token = next(t for t in synced["tokens"] if t["component_id"] == "Component_1")
        self.assertEqual(token["status"], "PASS")
        self.assertEqual(token["confidence"], 1.0)
        self.assertEqual(token["section"], "HSS8X4X1/4")
        self.assertEqual(token["predicted_shape"], "HSS8X4X1/4")
        self.assertEqual(token["detected_issues"], [])
        self.assertEqual(token["issues"], [])
        self.assertEqual(token["reasons"], [])
        self.assertEqual(token["correction_suggestions"], [])
        # Untouched object's token is not accidentally patched.
        other = next(t for t in synced["tokens"] if t["component_id"] == "Component_other")
        self.assertEqual(other["status"], "PASS")

    def test_no_resolutions_returns_validation_unchanged(self):
        from services.staged_pipeline import _sync_validation_with_rule_resolutions

        validation = {"tokens": [{"component_id": "c1", "status": "FAIL"}]}
        result = _sync_validation_with_rule_resolutions(validation, [], [])
        self.assertEqual(result, validation)

    def test_missing_validation_is_a_noop(self):
        from services.staged_pipeline import _sync_validation_with_rule_resolutions

        self.assertIsNone(_sync_validation_with_rule_resolutions(None, [], []))


if __name__ == "__main__":
    unittest.main()
