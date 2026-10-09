"""A re-extract must not keep a drawing summary from an older extractor."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.engineering.legend_profile import EXTRACTOR_VERSION
from services.extraction_engine import EXTRACTION_VERSION
from services.staged_pipeline import (
    legend_profile_current,
    load_cached_extraction,
    refresh_legend_profile,
)


class LegendProfileRefreshTests(unittest.TestCase):
    def test_a_current_summary_is_not_rebuilt(self):
        document = {"legend_profile": {"extractor_version": EXTRACTOR_VERSION}}
        self.assertTrue(legend_profile_current(document))
        with patch("services.engineering.legend_profile_hook.attach_legend_profile") as attach:
            self.assertFalse(refresh_legend_profile("doc_x", document))
        attach.assert_not_called()

    def test_a_stale_summary_is_rebuilt_from_the_saved_document(self):
        document = {
            "document_id": "doc_x",
            "legend_profile": {"extractor_version": "legend_extractor_v6v-grid-and-summary"},
            "engineering_tokens": [],
        }

        def _attach(saved):
            saved["legend_profile"] = {"extractor_version": EXTRACTOR_VERSION}
            return saved["legend_profile"]

        with (
            patch("services.engineering.legend_profile_hook.attach_legend_profile", side_effect=_attach) as attach,
            patch("services.staged_pipeline.write_artifact") as write_document,
            patch("services.staged_pipeline._write_extraction_view") as write_view,
        ):
            self.assertTrue(refresh_legend_profile("doc_x", document))
        attach.assert_called_once()
        write_document.assert_called_once()
        write_view.assert_called_once()
        self.assertEqual(document["legend_profile"]["extractor_version"], EXTRACTOR_VERSION)

    def test_opening_a_saved_extraction_rebuilds_a_stale_summary(self):
        view = {
            "extraction_version": EXTRACTION_VERSION,
            "legend_profile": {"extractor_version": "legend_extractor_v6v-grid-and-summary"},
        }
        document = {
            "document_id": "doc_x",
            "legend_profile": {"extractor_version": "legend_extractor_v6v-grid-and-summary"},
            "engineering_tokens": [],
        }

        def _attach(saved):
            saved["legend_profile"] = {"extractor_version": EXTRACTOR_VERSION, "drawing_intelligence": {"narrative": "rebuilt"}}
            return saved["legend_profile"]

        with (
            patch("services.staged_pipeline.read_artifact", return_value=view),
            patch("services.staged_pipeline._current_document", return_value=document),
            patch("services.engineering.legend_profile_hook.attach_legend_profile", side_effect=_attach),
            patch("services.staged_pipeline.write_artifact"),
            patch("services.staged_pipeline._write_extraction_view"),
        ):
            served = load_cached_extraction("doc_x")
        self.assertEqual(served["legend_profile"]["extractor_version"], EXTRACTOR_VERSION)
        self.assertEqual(served["legend_profile"]["drawing_intelligence"]["narrative"], "rebuilt")
