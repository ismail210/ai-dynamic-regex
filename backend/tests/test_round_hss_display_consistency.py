"""Regression coverage for a real display/normalization inconsistency found
in Analysis: a round-HSS token with a protected exact catalog match (e.g.
"HSS14x0.5") had its DISPLAYED "corrected"/"normalized" text overwritten by
the fuzzy label corrector's top guess, independently of the section the
pipeline actually locked -- and that guess is not even the closest catalog
match (see the root-cause note in orchestrator.py next to the fix).

Root cause: services.prediction.orchestrator.predict_from_context computed
`corrected_text` from `suggest_token_corrections(...)`'s top candidate
regardless of `protected_exact_section`. For "HSS14X0.5",
`suggest_token_corrections` ranks "HSS16X0.5" (0.75) above the objectively
correct "HSS14.000X0.500" (0.68) -- a scoring quirk in the fuzzy corrector,
not a different physical member. `section`/`final_label` were already
correctly locked to the catalog-valid "HSS14.000X0.500" via
`protected_exact_section` (services.exact_section_predictor.
resolve_trusted_explicit_section); only the separate `corrected_text`
variable skipped that protection.

Fix: when `protected_exact_section` is set, `corrected_text` uses the
conservative, source-style `normalized` text instead of the fuzzy
suggestion -- never a differently-dimensioned catalog row.
"""

from __future__ import annotations

import unittest

from services.prediction.orchestrator import predict_token


class RoundHssCorrectedTextConsistencyTests(unittest.TestCase):
    def test_hss14x0_5_normalizes_to_source_form_not_hss16(self):
        result = predict_token(
            "HSS14x0.5", queue_unknown=False, persist_learning=False
        )
        self.assertEqual(result["section"], "HSS14.000X0.500")
        self.assertEqual(result["corrected_text"], "HSS14X0.5")
        self.assertEqual(result["corrected_token"], "HSS14X0.5")
        self.assertNotIn("16", result["corrected_text"])
        self.assertNotIn("16", result["corrected_token"])

    def test_normalized_text_and_final_section_represent_the_same_designation(self):
        """The displayed 'corrected' text and the final section must never
        name two different catalog rows -- one is the source-style spelling
        of the other, not an independent guess."""

        result = predict_token(
            "HSS14x0.5", queue_unknown=False, persist_learning=False
        )
        from services.database_loader import catalog_form

        self.assertEqual(catalog_form(result["corrected_text"]), result["section"])

    def test_hss16x0_5_is_unaffected_and_stays_hss16(self):
        result = predict_token(
            "HSS16x0.5", queue_unknown=False, persist_learning=False
        )
        self.assertEqual(result["section"], "HSS16.000X0.500")
        self.assertEqual(result["corrected_text"], "HSS16X0.5")

    def test_hss10x0_625_is_unaffected_and_stays_hss10(self):
        result = predict_token(
            "HSS10x0.625", queue_unknown=False, persist_learning=False
        )
        self.assertEqual(result["section"], "HSS10.000X0.625")
        self.assertEqual(result["corrected_text"], "HSS10X0.625")

    def test_no_diameter_or_thickness_digit_is_ever_altered(self):
        """No normalization path may change a stated dimension -- confirmed
        across several round-HSS sizes that the fuzzy corrector is known to
        rank a different-diameter candidate above."""

        cases = {
            "HSS14x0.5": ("14", "0.5"),
            "HSS16x0.5": ("16", "0.5"),
            "HSS10x0.625": ("10", "0.625"),
            "HSS18x0.375": ("18", "0.375"),
        }
        for raw, (diameter, wall) in cases.items():
            with self.subTest(raw=raw):
                result = predict_token(
                    raw, queue_unknown=False, persist_learning=False
                )
                self.assertIn(diameter, result["corrected_text"])
                self.assertIn(wall, result["corrected_text"])
                self.assertIn(diameter, result["section"])
                self.assertIn(wall, result["section"])


if __name__ == "__main__":
    unittest.main()
