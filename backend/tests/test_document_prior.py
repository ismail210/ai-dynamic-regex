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
        self.assertTrue(prior["enabled"])
        self.assertEqual(prior["abbreviations"]["L"], "angle")
        self.assertEqual(prior["abbreviations"]["PL"], "plate")
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
    def test_boosts_typical_section_and_penalizes_out_of_vocab_family(self) -> None:
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
        self.assertLess(hss.confidence, 0.58)


class DocumentPriorPlateRoutingTests(unittest.TestCase):
    def test_plate_routing_uses_legend_context(self) -> None:
        prior = {
            "enabled": True,
            "abbreviations": {"PL": "plate", "BP": "bent_plate"},
            "plate_terms": ["PL", "BP"],
            "confirms_plates": True,
        }
        parsed = interpret_annotation(
            raw_text="PL 1/2 x 6 x 12",
            document_prior=prior,
            page_context="LEGEND_CONFIRMS_PLATES",
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertTrue(parsed.structure_confirmed)

    def test_plate_context_helper(self) -> None:
        prior = {
            "enabled": True,
            "abbreviations": {"BP": "bent_plate"},
            "plate_terms": ["BP"],
            "confirms_plates": True,
        }
        hints = plate_context_from_prior(
            prior,
            normalized="BP 3/8 x 4",
            compact="BP3/8X4",
        )
        self.assertTrue(hints["supports_bent_plate"])


if __name__ == "__main__":
    unittest.main()
