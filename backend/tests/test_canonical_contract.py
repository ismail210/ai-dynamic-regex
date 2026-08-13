"""Canonical prediction contract tests (Phase 1/2/7, Phase 10 fixtures 1-7)."""

from __future__ import annotations

import unittest

from services.prediction.canonical_contract import (
    MatchStatus,
    build_canonical_prediction,
)


def _build(**overrides):
    defaults = dict(
        object_id="token_1",
        document_id="doc_123",
        raw_text="W18X35",
        normalized_text="W18X35",
        page_number=12,
        bounding_box=[10.0, 20.0, 100.0, 40.0],
        block_number=1,
        line_number=2,
        word_number=None,
        extraction_method="pdf_text",
        source_available=True,
        final_label="W18X35",
        family="W",
        ranking_score=0.91,
        final_confidence=None,
        confidence_is_calibrated=False,
        used_text=True,
        used_geometry=True,
        used_graph=True,
        used_engineering_rules=True,
        used_catalog=True,
        candidates=[],
        evidence={"text": 0.9},
        catalog_version="aisc-shapes-database-v160-2.xlsx#Database v16.0",
        review_status="auto_accepted",
        near_tie=False,
        used_wildcards=False,
    )
    defaults.update(overrides)
    return build_canonical_prediction(**defaults)


class MatchStatusTests(unittest.TestCase):
    def test_exact_match(self):
        result = _build(raw_text="W18X35", final_label="W18X35")
        self.assertEqual(result.comparison.match_status, MatchStatus.EXACT_MATCH)
        self.assertTrue(result.comparison.exact_match)
        self.assertFalse(result.needs_review)

    def test_normalized_match(self):
        result = _build(raw_text="W18 x 35", final_label="W18X35")
        self.assertEqual(result.comparison.match_status, MatchStatus.NORMALIZED_MATCH)
        self.assertFalse(result.comparison.exact_match)
        self.assertTrue(result.comparison.normalized_match)
        self.assertFalse(result.needs_review)

    def test_corrected_prediction(self):
        result = _build(
            raw_text="W18X3S", final_label="W18X35", review_status="pending_review"
        )
        self.assertEqual(
            result.comparison.match_status, MatchStatus.CORRECTED_PREDICTION
        )
        self.assertTrue(result.needs_review)
        self.assertIn("differs from predicted label", result.review_reason)

    def test_incomplete_label_wildcard(self):
        result = _build(
            raw_text="W44X3**",
            final_label="W44X335",
            used_wildcards=True,
            review_status="pending_review",
        )
        self.assertEqual(result.comparison.match_status, MatchStatus.INCOMPLETE_LABEL)
        self.assertTrue(result.needs_review)

    def test_geometry_only_when_source_text_missing_but_predicted(self):
        result = _build(
            raw_text="",
            source_available=False,
            final_label="W18X35",
            used_text=False,
        )
        self.assertEqual(result.comparison.match_status, MatchStatus.GEOMETRY_ONLY)
        self.assertFalse(result.source_text.available)
        self.assertTrue(result.needs_review)

    def test_source_text_not_found_when_nothing_resolved(self):
        result = _build(
            raw_text="",
            source_available=False,
            final_label=None,
            used_text=False,
        )
        self.assertEqual(
            result.comparison.match_status, MatchStatus.SOURCE_TEXT_NOT_FOUND
        )

    def test_unresolved_when_text_present_but_no_prediction(self):
        result = _build(raw_text="W18X35", final_label=None)
        self.assertEqual(result.comparison.match_status, MatchStatus.UNRESOLVED)


class ProvenanceTests(unittest.TestCase):
    def test_raw_is_never_overwritten_by_prediction(self):
        # "W18X3S" -> "W18X35" is a corrected (not exact/normalized) match --
        # per the resolution contract, final_label is None here (a corrected
        # guess must never be presented as a resolved answer; see
        # ResolutionContractTests below). The provenance guarantee this test
        # protects is narrower and still holds regardless: raw stays exactly
        # what was extracted, never silently coerced into whatever the
        # caller passed as a candidate label.
        result = _build(raw_text="W18X3S", final_label="W18X35")
        self.assertEqual(result.source_text.raw, "W18X3S")
        self.assertNotEqual(result.source_text.raw, "W18X35")

    def test_raw_is_preserved_for_an_accepted_exact_match_too(self):
        result = _build(raw_text="W18X35", final_label="W18X35")
        self.assertEqual(result.source_text.raw, "W18X35")
        self.assertEqual(result.prediction.final_label, "W18X35")

    def test_bounding_box_and_page_carried_through(self):
        result = _build(page_number=7, bounding_box=[1.0, 2.0, 3.0, 4.0])
        self.assertEqual(result.source_text.page_number, 7)
        self.assertEqual(result.source_text.bounding_box, [1.0, 2.0, 3.0, 4.0])

    def test_unavailable_provenance_is_explicit_not_invented(self):
        result = _build(
            raw_text="",
            source_available=False,
            page_number=None,
            bounding_box=None,
            final_label=None,
        )
        self.assertFalse(result.source_text.available)
        self.assertIsNone(result.source_text.page_number)
        self.assertIsNone(result.source_text.bounding_box)


class ConfidenceConsistencyTests(unittest.TestCase):
    def test_uncalibrated_confidence_is_null_not_fabricated(self):
        result = _build(final_confidence=None, confidence_is_calibrated=False)
        self.assertIsNone(result.prediction.final_confidence)
        self.assertFalse(result.prediction.confidence_is_calibrated)
        self.assertGreater(result.prediction.ranking_score, 0)

    def test_calibrated_confidence_is_distinguishable_from_ranking_score(self):
        result = _build(
            ranking_score=0.91, final_confidence=0.77, confidence_is_calibrated=True
        )
        self.assertEqual(result.prediction.ranking_score, 0.91)
        self.assertEqual(result.prediction.final_confidence, 0.77)
        self.assertTrue(result.prediction.confidence_is_calibrated)


class ReviewAndSerializationTests(unittest.TestCase):
    def test_near_tie_forces_review(self):
        result = _build(near_tie=True, review_status="auto_accepted")
        self.assertTrue(result.needs_review)
        self.assertIn("near-tied", result.review_reason)

    def test_serialization_round_trip(self):
        result = _build()
        payload = result.model_dump(mode="json")
        self.assertIn("source_text", payload)
        self.assertIn("prediction", payload)
        self.assertIn("comparison", payload)
        self.assertIn("decision", payload)
        self.assertIn("candidates", payload)
        self.assertEqual(payload["comparison"]["match_status"], "exact_match")

    def test_decision_source_reflects_used_signals(self):
        result = _build(
            used_text=True,
            used_geometry=False,
            used_graph=False,
            used_engineering_rules=False,
        )
        self.assertEqual(result.decision.source, "text")
        self.assertTrue(result.decision.used_text)
        self.assertFalse(result.decision.used_geometry)


if __name__ == "__main__":
    unittest.main()
