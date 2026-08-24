"""Tests for legend detection and document_prior application."""

from __future__ import annotations

import unittest

from services.annotation.parser import interpret_annotation
from services.annotation.taxonomy import AnnotationType
from services.engineering.document_prior import (
    apply_prior_to_candidates,
    attach_document_prior,
    build_document_prior,
    detect_legend_pages,
    plate_context_from_prior,
    score_legend_page,
)
from services.exact_section_predictor import ExactSectionCandidate


class DocumentPriorDetectionTests(unittest.TestCase):
    def test_detects_legend_page(self) -> None:
        document = {
            "page_count": 5,
            "blocks": [
                {
                    "page_number": 1,
                    "text": "GENERAL NOTES\nLEGEND\nL = ANGLE\nPL = PLATE\nBP = BENT PLATE",
                },
                {"page_number": 2, "text": "FRAMING PLAN"},
            ],
        }
        pages = detect_legend_pages(document)
        self.assertIn(1, pages)
        self.assertNotIn(2, pages)

    def test_detects_legend_page_beyond_first_six(self) -> None:
        blocks = [{"page_number": n, "text": f"DETAIL {n}\nBEAM MARKS"} for n in range(1, 11)]
        blocks.append(
            {
                "page_number": 11,
                "text": "STRUCTURAL LEGEND\nPL = PLATE\nL = ANGLE\nBM = BEAM\nCOL = COLUMN",
            }
        )
        document = {"page_count": 11, "blocks": blocks}
        pages = detect_legend_pages(document)
        self.assertIn(11, pages)

    def test_plan_page_with_isolated_plate_word_is_not_legend(self) -> None:
        score = score_legend_page("FRAMING PLAN\nTYP BEAM\nPLATE GIRDER AT GRID A")
        self.assertLess(score, 4.0)

    def test_builds_abbreviations_and_typical_sections(self) -> None:
        document = {
            "page_count": 3,
            "blocks": [
                {
                    "page_number": 1,
                    "text": (
                        "ABBREVIATIONS\n"
                        "L = ANGLE\n"
                        "PL = PLATE\n"
                        "BP = BENT PLATE\n"
                        "TYPICAL BEAM W18X35\n"
                        "B1 W18X35\n"
                        "ASTM A992"
                    ),
                }
            ],
        }
        prior = build_document_prior(document)
        self.assertEqual(prior["version"], "document_prior_v2")
        self.assertTrue(prior["enabled"])
        self.assertEqual(prior["abbreviations"]["L"], "angle")
        self.assertEqual(prior["abbreviations"]["PL"], "plate")
        self.assertTrue(prior["confirms_plate_abbreviation"])
        self.assertTrue(prior["confirms_bent_plate_abbreviation"])
        self.assertTrue(prior["confirms_plates"])
        self.assertIn("W18X35", prior["typical_sections"])
        self.assertIn("L", prior["allowed_families"])
        self.assertIn("A992", prior["material_grades"])

    def test_attach_document_prior_stores_on_document(self) -> None:
        document = {
            "page_count": 1,
            "blocks": [{"page_number": 1, "text": "LEGEND\nPL = PLATE"}],
        }
        prior = attach_document_prior(document)
        self.assertIn("document_prior", document)
        self.assertTrue(prior["enabled"])


class DocumentPriorBoostTests(unittest.TestCase):
    def test_boosts_typical_section_without_penalizing_unknown_family(self) -> None:
        prior = {
            "enabled": True,
            "typical_sections": ["W18X35"],
            "allowed_families": ["W"],
            "mark_map": {},
        }
        candidates = [
            ExactSectionCandidate(
                shape="W18X35",
                confidence=0.55,
                text_similarity=0.6,
                evidence={"text": 0.6},
            ),
            ExactSectionCandidate(
                shape="HSS6X6X1/2",
                confidence=0.58,
                text_similarity=0.58,
                evidence={"text": 0.58},
            ),
        ]
        boosted = apply_prior_to_candidates(
            candidates,
            prior,
            token_text="W18X3",
        )
        self.assertEqual(boosted[0].shape, "W18X35")
        self.assertGreater(boosted[0].confidence, 0.55)
        hss = next(item for item in boosted if item.shape == "HSS6X6X1/2")
        self.assertEqual(hss.confidence, 0.58)

    def test_non_typical_local_section_is_not_penalized(self) -> None:
        prior = {
            "enabled": True,
            "typical_sections": ["W24X55"],
            "allowed_families": ["W"],
            "mark_map": {},
        }
        candidates = [
            ExactSectionCandidate(
                shape="W27X84",
                confidence=0.62,
                text_similarity=0.62,
                evidence={"text": 0.62},
            ),
            ExactSectionCandidate(
                shape="W24X55",
                confidence=0.60,
                text_similarity=0.60,
                evidence={"text": 0.60},
            ),
        ]
        boosted = apply_prior_to_candidates(
            candidates,
            prior,
            token_text="W27X84",
        )
        self.assertEqual(boosted[0].shape, "W27X84")
        self.assertGreaterEqual(boosted[0].confidence, 0.62)


class DocumentPriorPlateRoutingTests(unittest.TestCase):
    def test_plate_routing_uses_legend_context(self) -> None:
        prior = {
            "enabled": True,
            "abbreviations": {"PL": "plate", "BP": "bent_plate"},
            "plate_terms": ["PL", "BP"],
            "confirms_plate_abbreviation": True,
            "confirms_bent_plate_abbreviation": True,
            "confirms_plates": True,
        }
        parsed = interpret_annotation(
            raw_text="PL 1/2 x 6 x 12",
            document_prior=prior,
            page_context="LEGEND_CONFIRMS_PLATES",
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertTrue(parsed.structure_confirmed)

    def test_plate_context_helper_bp_local(self) -> None:
        prior = {
            "enabled": True,
            "abbreviations": {"BP": "bent_plate"},
            "plate_terms": ["BP"],
            "confirms_bent_plate_abbreviation": True,
            "confirms_plates": True,
        }
        hints = plate_context_from_prior(
            prior,
            normalized="BP 3/8 x 4",
            compact="BP3/8X4",
        )
        self.assertTrue(hints["supports_bent_plate"])
        self.assertTrue(hints["supports_plate"])


class DocumentPriorV2RegressionTests(unittest.TestCase):
    def _prior(self, **overrides: object) -> dict:
        base = {
            "enabled": True,
            "abbreviations": {},
            "plate_terms": [],
            "confirms_plate_abbreviation": False,
            "confirms_bent_plate_abbreviation": False,
            "confirms_plates": False,
        }
        base.update(overrides)
        return base

    def test_case1_pl_abbrev_local_pl(self) -> None:
        prior = self._prior(
            abbreviations={"PL": "plate"},
            confirms_plate_abbreviation=True,
            confirms_plates=True,
        )
        hints = plate_context_from_prior(prior, normalized="PL 3/8", compact="PL3/8")
        self.assertTrue(hints["supports_plate"])
        self.assertFalse(hints["supports_bent_plate"])

    def test_case2_bp_abbrev_local_bp(self) -> None:
        prior = self._prior(
            abbreviations={"BP": "bent_plate"},
            confirms_bent_plate_abbreviation=True,
            confirms_plates=True,
        )
        hints = plate_context_from_prior(prior, normalized="BP 3/8", compact="BP3/8")
        self.assertTrue(hints["supports_plate"])
        self.assertTrue(hints["supports_bent_plate"])

    def test_case3_bp_abbrev_local_pl_only(self) -> None:
        prior = self._prior(
            abbreviations={"BP": "bent_plate"},
            confirms_bent_plate_abbreviation=True,
            confirms_plates=True,
        )
        hints = plate_context_from_prior(prior, normalized="PL 3/8", compact="PL3/8")
        self.assertTrue(hints["supports_plate"])
        self.assertFalse(hints["supports_bent_plate"])

    def test_case4_plate_girder_vocabulary_without_pl_abbrev(self) -> None:
        document = {
            "page_count": 1,
            "blocks": [{"page_number": 1, "text": "GENERAL NOTES\nPLATE GIRDER TYP DETAIL"}],
        }
        prior = build_document_prior(document)
        self.assertTrue(prior["mentions_plate_vocabulary"])
        self.assertFalse(prior["confirms_plate_abbreviation"])
        self.assertFalse(prior["confirms_plates"])

    def test_case5_non_typical_local_section_not_penalized(self) -> None:
        prior = {
            "enabled": True,
            "typical_sections": ["W24X55"],
            "allowed_families": ["W"],
            "mark_map": {},
        }
        candidate = ExactSectionCandidate(
            shape="W27X84",
            confidence=0.70,
            text_similarity=0.70,
            evidence={"text": 0.70},
        )
        boosted = apply_prior_to_candidates(
            [candidate],
            prior,
            token_text="W27X84",
        )[0]
        self.assertEqual(boosted.confidence, 0.70)

    def test_case6_unknown_hss_family_not_penalized(self) -> None:
        prior = {
            "enabled": True,
            "typical_sections": [],
            "allowed_families": ["W", "L"],
            "mark_map": {},
        }
        w = ExactSectionCandidate(shape="W16X26", confidence=0.55, text_similarity=0.55, evidence={})
        hss = ExactSectionCandidate(
            shape="HSS6X6X3/8", confidence=0.58, text_similarity=0.58, evidence={}
        )
        boosted = apply_prior_to_candidates([w, hss], prior, token_text="HSS6X6")
        hss_result = next(item for item in boosted if item.shape == "HSS6X6X3/8")
        self.assertEqual(hss_result.confidence, 0.58)

    def test_case7_legend_text_does_not_become_takeoff_tokens(self) -> None:
        document = {
            "page_count": 1,
            "blocks": [
                {
                    "page_number": 1,
                    "text": "LEGEND\nPL = PLATE\nPL 3/8\" TYP",
                }
            ],
            "engineering_tokens": [],
        }
        attach_document_prior(document)
        self.assertEqual(document.get("engineering_tokens"), [])
        self.assertTrue(document["document_prior"]["confirms_plate_abbreviation"])

    def test_case8_local_bent_pl_callout(self) -> None:
        parsed = interpret_annotation(raw_text='BENT PL 1/2"')
        self.assertEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)

    def test_case9_dimension_only_not_bent_plate(self) -> None:
        prior = self._prior(
            abbreviations={"BP": "bent_plate"},
            confirms_bent_plate_abbreviation=True,
            confirms_plates=True,
        )
        hints = plate_context_from_prior(prior, normalized='1/2"', compact='1/2"')
        self.assertFalse(hints["supports_plate"])
        self.assertFalse(hints["supports_bent_plate"])

    def test_case10_mark_map_supports_member_mark(self) -> None:
        prior = {
            "enabled": True,
            "typical_sections": [],
            "allowed_families": ["W"],
            "mark_map": {"BM3": "W27X84"},
        }
        candidate = ExactSectionCandidate(
            shape="W27X84",
            confidence=0.50,
            text_similarity=0.50,
            evidence={"text": 0.50},
        )
        other = ExactSectionCandidate(
            shape="W30X90",
            confidence=0.52,
            text_similarity=0.52,
            evidence={"text": 0.52},
        )
        boosted = apply_prior_to_candidates(
            [other, candidate],
            prior,
            token_text="BM3",
        )
        self.assertEqual(boosted[0].shape, "W27X84")
        self.assertGreater(boosted[0].confidence, 0.50)

    def test_case11_local_explicit_section_overrides_mark_map(self) -> None:
        prior = {
            "enabled": True,
            "typical_sections": [],
            "allowed_families": ["W"],
            "mark_map": {"BM3": "W27X84"},
        }
        candidate = ExactSectionCandidate(
            shape="W27X84",
            confidence=0.50,
            text_similarity=0.50,
            evidence={"text": 0.50},
        )
        local = ExactSectionCandidate(
            shape="W30X90",
            confidence=0.51,
            text_similarity=0.51,
            evidence={"text": 0.51},
        )
        boosted = apply_prior_to_candidates(
            [candidate, local],
            prior,
            token_text="BM3 W30X90",
        )
        w30 = next(item for item in boosted if item.shape == "W30X90")
        w27 = next(item for item in boosted if item.shape == "W27X84")
        self.assertEqual(w30.confidence, 0.51)
        self.assertEqual(w27.confidence, 0.50)


if __name__ == "__main__":
    unittest.main()
