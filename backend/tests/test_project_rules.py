"""Unit tests for the drawing-language rule taxonomy / compiler
(services.engineering.project_rules) -- the deterministic layer that decides
what type a model-proposed rule is and what Estima3D may do with it.
"""

from __future__ import annotations

import unittest

from services.engineering import project_rules as pr


class ApplicationPolicyTests(unittest.TestCase):
    def test_only_label_substitution_is_auto_eligible(self):
        auto = [t for t in pr.RULE_TYPES if pr.application_policy(t) == pr.POLICY_AUTO_ELIGIBLE]
        self.assertEqual(auto, [pr.LABEL_SUBSTITUTION])

    def test_inheritance_and_orientation_require_corroboration(self):
        self.assertEqual(pr.application_policy(pr.INHERITANCE_RULE), pr.POLICY_CORROBORATION_REQUIRED)
        self.assertEqual(pr.application_policy(pr.ORIENTATION_RULE), pr.POLICY_CORROBORATION_REQUIRED)

    def test_conflict_and_insight_are_never_auto(self):
        self.assertEqual(pr.application_policy(pr.CONFLICT_WARNING), pr.POLICY_NEVER_AUTO)
        self.assertEqual(pr.application_policy(pr.DERIVED_INSIGHT), pr.POLICY_NEVER_AUTO)

    def test_recognised_grammar_is_parser_assist_unknown_is_information_only(self):
        self.assertEqual(
            pr.application_policy(pr.NOTATION_GRAMMAR, pr.GRAMMAR_CAMBER_PREFIX),
            pr.POLICY_PARSER_ASSIST,
        )
        self.assertEqual(
            pr.application_policy(pr.NOTATION_GRAMMAR, pr.GRAMMAR_UNKNOWN),
            pr.POLICY_INFORMATION_ONLY,
        )
        self.assertEqual(
            pr.application_policy(pr.NOTATION_GRAMMAR, None), pr.POLICY_INFORMATION_ONLY
        )


class ClassifyGrammarTests(unittest.TestCase):
    CASES = [
        ("camber", "c=<dimension>", "c= denotes beam camber", pr.GRAMMAR_CAMBER_PREFIX),
        ("shear_stud_count", "[n]", "a bracketed value is the shear stud count", pr.GRAMMAR_STUD_COUNT_SINGLE),
        ("shear_stud_count_by_segment", "[n;n;n]", "studs split by girder segment", pr.GRAMMAR_STUD_COUNT_SEGMENTED),
        ("connection_reaction", "Rk", "R40k is the factored beam end reaction", pr.GRAMMAR_REACTION_VALUE),
        ("top_of_steel_elevation", "(elev)", "a parenthesised value is top of steel elevation", pr.GRAMMAR_TOP_OF_STEEL_ELEVATION),
        ("column_posting_load", "COL UP xxxK", "column posting load from above", pr.GRAMMAR_COLUMN_POSTING_LOAD),
        ("frame_mark", "DS", "DS marks a drag strut", pr.GRAMMAR_DRAG_STRUT_MARK),
        ("frame_mark", "MF", "MF marks a moment frame", pr.GRAMMAR_MOMENT_FRAME_MARK),
        ("frame_mark", "BF1", "BF marks a braced frame member", pr.GRAMMAR_BRACED_FRAME_MARK),
        ("member_mark", "CANT", "CANT marks a cantilever", pr.GRAMMAR_CANTILEVER_MARK),
        ("misc", "(n)", "a circled number references a typical detail", pr.GRAMMAR_UNKNOWN),
    ]

    def test_all_cases(self):
        for field, grammar, statement, expected in self.CASES:
            with self.subTest(field=field):
                self.assertEqual(
                    pr.classify_grammar(field=field, grammar=grammar, statement=statement),
                    expected,
                )


class ValidateRuleTests(unittest.TestCase):
    SOURCE = '[PAGE 5]\n"W8" = W8x10   c = 1-1/4" INDICATES CAMBER.   HSS LONG SIDE VERTICAL UNO.\n'

    def _verify(self, text, quote):
        return quote.lower() in text.lower()

    def _coherent(self, statement, quote):
        # coherence is exercised at the provider level (test_legend_profile);
        # here we isolate the taxonomy/compiler.
        return True

    def _v(self, raw, next_id=1):
        return pr.validate_rule(
            raw,
            source_text=self.SOURCE,
            verify_quote=self._verify,
            statement_supported_by_quote=self._coherent,
            next_id=next_id,
        )

    def test_ids_are_assigned_sequentially(self):
        r1 = self._v(
            {"type": "ORIENTATION_RULE", "statement": "HSS installs long side vertical UNO.",
             "source_page": 5, "source_quote": "HSS LONG SIDE VERTICAL UNO."},
            next_id=3,
        )
        self.assertEqual(r1["id"], "RULE_003")
        self.assertEqual(r1["validation_status"], pr.VALIDATION_STATUS_VALIDATED)

    def test_scope_defaults_and_normalisation(self):
        r = self._v(
            {"type": "LABEL_SUBSTITUTION", "statement": "W8 means W8x10.", "trigger": "W8",
             "result": "W8X10", "scope": {"page_roles": ["framing_plan"], "uno_applies": True},
             "source_page": 5, "source_quote": '"W8" = W8x10'}
        )
        self.assertEqual(r["scope"], {"page_roles": ["FRAMING_PLAN"], "uno_applies": True})

    def test_derived_insight_type_is_not_a_rule(self):
        self.assertIsNone(
            self._v({"type": "DERIVED_INSIGHT", "statement": "x", "source_page": 5,
                     "source_quote": '"W8" = W8x10'})
        )

    def test_missing_quote_rejected(self):
        self.assertIsNone(
            self._v({"type": "SCOPE_RULE", "statement": "fabricator supplies embeds", "source_page": 5})
        )

    def test_admin_boilerplate_rejected(self):
        self.assertIsNone(
            self._v(
                {
                    "type": "ATTRIBUTE_DEFAULT",
                    "statement": "The structural drawings are not issued for bid unless the sheet says ISSUED FOR BID.",
                    "source_page": 5,
                    "source_quote": "HSS LONG SIDE VERTICAL UNO.",
                }
            )
        )

    def test_circular_restatement_rejected(self):
        # "W12x53 indicates a W12x53 steel shape" with a bare-token quote.
        src = "[PAGE 5]\n W12x53 \n"
        r = pr.validate_rule(
            {"type": "NOTATION_GRAMMAR", "statement": "W12x53 indicates a W12x53 steel shape.",
             "source_page": 5, "source_quote": "W12x53"},
            source_text=src, verify_quote=lambda t, q: q.lower() in t.lower(),
            statement_supported_by_quote=lambda s, q: True, next_id=1,
        )
        self.assertIsNone(r)

    def test_attribute_default_without_material_signal_rejected(self):
        self.assertIsNone(
            self._v(
                {
                    "type": "ATTRIBUTE_DEFAULT",
                    "statement": "The project uses composite floor decks throughout.",
                    "source_page": 5,
                    "source_quote": "HSS LONG SIDE VERTICAL UNO.",
                }
            )
        )

    def test_attribute_default_with_grade_kept(self):
        r = self._v(
            {
                "type": "ATTRIBUTE_DEFAULT",
                "statement": "Square and rectangular HSS conform to ASTM A500 Grade C.",
                "source_page": 5,
                "source_quote": "HSS LONG SIDE VERTICAL UNO.",
            }
        )
        self.assertIsNotNone(r)
        self.assertEqual(r["application_policy"], pr.POLICY_ATTRIBUTE_ONLY)


class BuildDrawingLanguageTests(unittest.TestCase):
    def test_bullets_are_bounded_and_deduped(self):
        rules = [
            {"type": pr.NOTATION_GRAMMAR, "grammar_type": pr.GRAMMAR_CAMBER_PREFIX},
            {"type": pr.NOTATION_GRAMMAR, "grammar_type": pr.GRAMMAR_CAMBER_PREFIX},  # dup
            {"type": pr.NOTATION_GRAMMAR, "grammar_type": pr.GRAMMAR_STUD_COUNT_SEGMENTED},
            {"type": pr.INHERITANCE_RULE, "trigger": "CANT", "relation": "adjacent_backspan_beam"},
        ]
        abbr = [{"lhs_family": "W"}, {"lhs_family": "HSS"}]
        bullets = pr.build_drawing_language(rules=rules, abbreviation_rules=abbr)
        self.assertLessEqual(len(bullets), 8)
        self.assertEqual(len(bullets), len(set(bullets)))
        joined = " ".join(bullets).lower()
        self.assertIn("camber", joined)
        self.assertIn("segment", joined)
        self.assertIn("backspan", joined)
        self.assertIn("member labels on the framing plans", joined)

    def test_empty_when_no_rules(self):
        self.assertEqual(pr.build_drawing_language(rules=[], abbreviation_rules=[]), [])


if __name__ == "__main__":
    unittest.main()
