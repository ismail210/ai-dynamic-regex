"""
Regression tests for test-isolation fixes.

Pre-training audit finding: running the full backend suite mutated real
training/correction files on disk --

  * ``training/engineering_corrections.jsonl`` -- ``test_engineering_pipeline
    .py::test_correction_sample`` called ``record_correction()`` with no
    path isolation at all.
  * ``training/annotation_edge_cases.jsonl`` -- ``test_documents_api.py``'s
    ``IsolatedApiTestCase`` redirects most settings paths but was missing
    ``annotation_edge_cases_path`` from its list.
  * ``training/multimodal_review_index.json`` -- ``run_multimodal_pipeline
    (pdf, persist=False)`` called ``index_predictions(...)`` unconditionally,
    ignoring ``persist=False``.

Each left synthetic rows in real training data (49 in
engineering_corrections.jsonl, 13 in annotation_edge_cases.jsonl,
accumulated across many past runs; both cleaned up as part of this fix).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from services.multimodal.pipeline import run_multimodal_pipeline
from tests.test_documents_api import _REDIRECTED_SETTINGS


def _drawing(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 75), "STRUCTURAL FRAMING PLAN", fontsize=18)
    page.insert_text((72, 130), "W18 X 35", fontsize=12)
    document.save(path)
    document.close()


class PersistFalseSkipsReviewIndexTests(unittest.TestCase):
    """services.multimodal.pipeline.run_multimodal_pipeline's persist=False
    must mean no side effects -- including the review index, which
    previously wrote unconditionally."""

    def test_persist_false_does_not_index_predictions(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "drawing.pdf"
            _drawing(pdf)
            with patch(
                "services.multimodal.pipeline.index_predictions"
            ) as mock_index:
                run_multimodal_pipeline(pdf, persist=False)
            mock_index.assert_not_called()

    def test_persist_true_still_indexes_predictions(self):
        """Control: persist=True must still index (the flag actually gates
        behavior, it isn't just dead code removed)."""

        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "drawing.pdf"
            _drawing(pdf)
            with patch(
                "services.multimodal.pipeline.index_predictions"
            ) as mock_index, patch(
                "services.multimodal.pipeline.prune_documents"
            ):
                run_multimodal_pipeline(pdf, persist=True)
            mock_index.assert_called_once()


class DocumentsApiRedirectListTests(unittest.TestCase):
    """Static guard: annotation_edge_cases_path must stay in the redirected
    settings list so ReviewAndCorrectionApiTests never leaks to the real
    training/annotation_edge_cases.jsonl again."""

    def test_annotation_edge_cases_path_is_redirected(self):
        self.assertIn("annotation_edge_cases_path", _REDIRECTED_SETTINGS)

    def test_engineering_corrections_path_is_redirected(self):
        self.assertIn("engineering_corrections_path", _REDIRECTED_SETTINGS)


class EngineeringPipelineCorrectionIsolationTests(unittest.TestCase):
    """Functional proof: running test_engineering_pipeline.py's correction
    test does not touch the real engineering_corrections.jsonl."""

    def test_correction_sample_does_not_touch_real_file(self):
        import config

        real_path = config.settings.engineering_corrections_path
        real_path.parent.mkdir(parents=True, exist_ok=True)
        if not real_path.exists():
            real_path.write_text("", encoding="utf-8")
        before = real_path.read_bytes()

        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(
            "tests.test_engineering_pipeline.EngineeringPipelineUnitTests.test_correction_sample"
        )
        result = unittest.TextTestRunner(verbosity=0).run(suite)
        self.assertTrue(result.wasSuccessful())

        after = real_path.read_bytes()
        self.assertEqual(before, after, "real engineering_corrections.jsonl was mutated")


if __name__ == "__main__":
    unittest.main()
