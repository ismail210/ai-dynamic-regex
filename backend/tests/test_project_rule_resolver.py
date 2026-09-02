"""A-T coverage for the gated LABEL_SUBSTITUTION resolver
(services.engineering.project_rule_resolver), objective #1.

GCDC has no naturally occurring bare abbreviation token on a drawing page
(every real W/HSS occurrence already carries a complete designation), so
the end-to-end case is exercised with the REAL GCDC-extracted rule
``HSS8X4 -> HSS8X4X1/4`` and a SYNTHETIC injected drawing-page token.
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
        self.assertIsNone(_resolve("HSS8X4", takeoff_eligible=False))
        self.assertEqual(_last_gate(), "not_takeoff_eligible")

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


if __name__ == "__main__":
    unittest.main()
