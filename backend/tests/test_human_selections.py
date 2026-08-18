"""
Focused tests for the human-review selection persistence path added on top
of the missing-thickness HSS completion workflow (services.hss_completion).

Covers: record_human_selection/get_human_selections round-trip, and that
services.staged_pipeline._apply_human_selections overlays a persisted
selection onto served predictions as the final display section without
touching original_token/normalized_text -- the behavior "refreshing the
results page must still show the human-selected section" depends on.

Isolates config.settings.human_selections_path to a temp file for every
test (same pattern as tests.test_documents_api.IsolatedApiTestCase) so this
suite never writes to real repository data.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import config
from services.human_selections import (
    get_human_selection,
    get_human_selections,
    record_human_selection,
)
from services.staged_pipeline import _apply_human_selections


class IsolatedSelectionsTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self._original_path = config.settings.human_selections_path
        object.__setattr__(
            config.settings,
            "human_selections_path",
            Path(self.temp.name) / "human_selections.json",
        )

    def tearDown(self):
        object.__setattr__(
            config.settings, "human_selections_path", self._original_path
        )
        self.temp.cleanup()


class RecordAndReadSelectionTests(IsolatedSelectionsTestCase):
    def test_round_trip(self):
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X1/2"
        )
        self.assertEqual(
            get_human_selection("doc_1", "obj_1"), "HSS10X10X1/2"
        )
        self.assertEqual(
            get_human_selections("doc_1"), {"obj_1": "HSS10X10X1/2"}
        )

    def test_latest_selection_wins(self):
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X1/2"
        )
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X3/8"
        )
        self.assertEqual(
            get_human_selection("doc_1", "obj_1"), "HSS10X10X3/8"
        )

    def test_scoped_per_document(self):
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X1/2"
        )
        self.assertIsNone(get_human_selection("doc_2", "obj_1"))

    def test_missing_fields_are_ignored(self):
        record_human_selection(document_id="", object_id="obj_1", section="HSS10X10X1/2")
        record_human_selection(document_id="doc_1", object_id="", section="HSS10X10X1/2")
        record_human_selection(document_id="doc_1", object_id="obj_1", section="")
        self.assertEqual(get_human_selections("doc_1"), {})


class ApplyHumanSelectionsOverlayTests(IsolatedSelectionsTestCase):
    def _prediction(self, object_id="obj_1", section=None):
        return {
            "object_id": object_id,
            "original_token": "HSS10x10",
            "normalized_text": "HSS10X10",
            "corrected_token": "HSS10X10",
            "section": section,
            "needs_review": True,
            "review_reason": "Wall thickness is not present in the extracted designation; select the correct catalog section.",
            "completion_status": "missing_thickness",
            "candidate_sections": [{"designation": "HSS10X10X1/2", "thickness": "1/2"}],
            "canonical": {
                "prediction": {"final_label": None},
                "comparison": {"match_status": "missing_dimension_field"},
                "needs_review": True,
                "review_reason": "Wall thickness is not present in the extracted designation; select the correct catalog section.",
            },
        }

    def test_no_selection_leaves_prediction_untouched(self):
        predictions = [self._prediction()]
        result = _apply_human_selections("doc_1", predictions)
        self.assertEqual(result[0]["section"], None)
        self.assertTrue(result[0]["needs_review"])

    def test_selection_becomes_the_display_section(self):
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X1/2"
        )
        predictions = [self._prediction()]
        result = _apply_human_selections("doc_1", predictions)[0]

        self.assertEqual(result["section"], "HSS10X10X1/2")
        self.assertEqual(result["human_selected_section"], "HSS10X10X1/2")
        self.assertEqual(result["decision_source"], "human_review")
        self.assertFalse(result["needs_review"])
        self.assertIsNone(result["review_reason"])
        self.assertEqual(
            result["canonical"]["prediction"]["final_label"], "HSS10X10X1/2"
        )
        self.assertEqual(
            result["canonical"]["comparison"]["match_status"], "human_resolved"
        )
        self.assertFalse(result["canonical"]["needs_review"])

    def test_original_and_normalized_text_never_change(self):
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X1/2"
        )
        predictions = [self._prediction()]
        result = _apply_human_selections("doc_1", predictions)[0]

        self.assertEqual(result["original_token"], "HSS10x10")
        self.assertEqual(result["normalized_text"], "HSS10X10")

    def test_selection_can_be_changed(self):
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X1/2"
        )
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X3/8"
        )
        predictions = [self._prediction()]
        result = _apply_human_selections("doc_1", predictions)[0]
        self.assertEqual(result["section"], "HSS10X10X3/8")

    def test_only_matching_object_id_is_overlaid(self):
        record_human_selection(
            document_id="doc_1", object_id="obj_1", section="HSS10X10X1/2"
        )
        predictions = [self._prediction(object_id="obj_1"), self._prediction(object_id="obj_2")]
        result = _apply_human_selections("doc_1", predictions)
        self.assertEqual(result[0]["section"], "HSS10X10X1/2")
        self.assertIsNone(result[1]["section"])


if __name__ == "__main__":
    unittest.main()
