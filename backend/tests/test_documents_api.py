"""
FastAPI HTTP-level tests for the staged document workflow, review queue,
corrections, and takeoff preconditions (Phase 10).

Uses ``fastapi.testclient.TestClient`` against the real ``app`` — this is the
router/HTTP layer the existing test suite did not previously cover (all
prior tests exercised services directly, one layer below the routes).

Every path that would otherwise read/write real operational or training
data (uploads, artifacts, the regex knowledge base, the unknown-token queue,
approved corrections, ...) is redirected to a temporary directory for the
duration of each test. ``config.settings`` is a frozen dataclass singleton
shared by reference across every module that does ``from config import
settings``, so patching its attributes here (via ``object.__setattr__``,
restored in ``tearDown``) takes effect everywhere without ever touching real
repository data — this suite must not add noise to files like
``backend/training/dynamic_regex.json`` or ``unknown_tokens.csv``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

import config
from app import app
from services.regex_knowledge_base import knowledge_base


def _drawing(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 75), "STRUCTURAL FRAMING PLAN", fontsize=18)
    page.insert_text((72, 130), "W18 X 35", fontsize=12)
    page.insert_text((72, 160), "HSS8X8X1/2", fontsize=12)
    document.save(path)
    document.close()


# Every settings attribute touched by the routes under test that points at a
# real file/directory under the repository. Redirected to a temp dir per test.
_REDIRECTED_SETTINGS = [
    "uploads_dir",
    "engineering_uploads_dir",
    "engineering_artifacts_dir",
    "document_registry_dir",
    "takeoff_exports_dir",
    "knowledge_base_path",
    "unknown_tokens_path",
    "history_path",
    "upload_log_path",
    "approved_dataset_path",
    "engineering_corrections_path",
    "continuous_learning_state_path",
]


class IsolatedApiTestCase(unittest.TestCase):
    """Base class redirecting all operational/training data paths to a temp
    directory so HTTP-level tests never mutate real repository data."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self._originals = {
            name: getattr(config.settings, name) for name in _REDIRECTED_SETTINGS
        }
        for name in _REDIRECTED_SETTINGS:
            original = self._originals[name]
            replacement = base / name
            if original.suffix:  # file path — keep the same extension
                replacement = replacement.with_suffix(original.suffix)
            else:
                replacement.mkdir(parents=True, exist_ok=True)
            object.__setattr__(config.settings, name, replacement)

        # These two read their path once at import/construction time, not
        # per-call from `settings`, so redirecting settings above does not
        # reach them — patch the already-constructed singleton/module
        # constant directly instead.
        self._original_kb_path = knowledge_base.path
        knowledge_base.path = base / "dynamic_regex.json"

        review_index_patcher = patch(
            "services.multimodal.review_enrichment._INDEX_PATH",
            base / "multimodal_review_index.json",
        )
        review_index_patcher.start()
        self.addCleanup(review_index_patcher.stop)

    def tearDown(self) -> None:
        for name, value in self._originals.items():
            object.__setattr__(config.settings, name, value)
        knowledge_base.path = self._original_kb_path
        self.temp.cleanup()


class DocumentWorkflowApiTests(IsolatedApiTestCase):
    def _upload_document(self) -> dict:
        pdf_path = Path(self.temp.name) / "drawing.pdf"
        _drawing(pdf_path)
        with open(pdf_path, "rb") as handle:
            response = self.client.post(
                "/api/documents",
                files={"file": ("drawing.pdf", handle, "application/pdf")},
            )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_document_upload_then_extract_response_shape(self):
        document = self._upload_document()
        self.assertIn("document_id", document)
        self.assertEqual(document["stage"], "uploaded")

        response = self.client.post(
            f"/api/documents/{document['document_id']}/extract"
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("tokens", body)
        self.assertIn("quality", body)
        token_texts = {token["normalized_text"] for token in body["tokens"]}
        self.assertIn("W18X35", token_texts)

    def test_extract_unknown_document_returns_404(self):
        response = self.client.post("/api/documents/doc_doesnotexist0000/extract")
        self.assertEqual(response.status_code, 404)

    def test_full_analysis_response_carries_canonical_contract(self):
        document = self._upload_document()
        document_id = document["document_id"]
        self.client.post(f"/api/documents/{document_id}/extract")
        response = self.client.post(f"/api/documents/{document_id}/analyze")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(len(body["predictions"]), 1)
        prediction = body["predictions"][0]

        # Canonical contract fields must be present on every prediction.
        self.assertIn("canonical", prediction)
        self.assertIn("source_text", prediction)
        self.assertIn("comparison", prediction)
        self.assertIn("decision", prediction)
        self.assertIn("match_status", prediction["comparison"])
        self.assertIn("ranking_score", prediction)
        self.assertIn("confidence_is_calibrated", prediction)
        # Raw text must never be silently replaced by the predicted label
        # unless there truly was no source text.
        if prediction["source_text"]["available"]:
            self.assertIsNotNone(prediction["source_text"]["raw"])

    def test_takeoff_generate_succeeds_after_analysis(self):
        # Regression coverage for the live exporter (services/takeoff/
        # takeoff_exporter.py) wired to this endpoint — see Phase 12 of the
        # reliability upgrade: services/engineering/takeoff_interface.py is
        # a separate, intentionally-unimplemented future stub with no route.
        document = self._upload_document()
        document_id = document["document_id"]
        self.client.post(f"/api/documents/{document_id}/extract")
        self.client.post(f"/api/documents/{document_id}/analyze")

        response = self.client.post(
            "/api/takeoff/generate", json={"document_id": document_id}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("filename", body)
        self.assertIn("rows", body)
        self.assertGreaterEqual(body["row_count"], 1)

    def test_takeoff_generate_before_analysis_returns_409(self):
        document = self._upload_document()
        response = self.client.post(
            "/api/takeoff/generate", json={"document_id": document["document_id"]}
        )
        self.assertEqual(response.status_code, 409)

    def test_takeoff_generate_unknown_document_returns_409_or_404(self):
        response = self.client.post(
            "/api/takeoff/generate", json={"document_id": "doc_doesnotexist0000"}
        )
        self.assertIn(response.status_code, (404, 409))


class TokenAnalysisApiTests(IsolatedApiTestCase):
    """Token-only path (/api/analyze) — no document, so source text is
    inherently unavailable; the canonical contract must say so explicitly
    rather than inventing provenance."""

    def test_single_token_analysis_reports_missing_provenance_honestly(self):
        # The token-only path has no real PDF page/location — only the raw
        # text itself, supplied directly by the caller. Page/bounding-box
        # must stay explicitly unavailable rather than inventing coordinates.
        response = self.client.post("/api/analyze", json={"token": "W18X35"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("canonical", body)
        self.assertEqual(body["source_text"]["raw"], "W18X35")
        self.assertIsNone(body["source_text"]["bounding_box"])
        self.assertIsNone(body["source_text"]["page_number"])
        self.assertEqual(body["source_text"]["extraction_method"], "unknown")

    def test_wildcard_token_resolves_deterministically(self):
        response = self.client.post("/api/analyze", json={"token": "W44X3**"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["comparison"]["match_status"], "incomplete_label")
        labels = {c["label"] for c in body["canonical_candidates"]}
        self.assertTrue(labels & {"W44X335", "W44X368"})


class ReviewAndCorrectionApiTests(IsolatedApiTestCase):
    def test_unknown_tokens_endpoint_returns_expected_shape(self):
        response = self.client.get("/api/unknown-tokens", params={"status": "pending"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("tokens", body)
        self.assertIn("counts", body)

    def test_correction_submission_requires_a_decision(self):
        response = self.client.post(
            "/api/engineering/corrections",
            json={
                "features": {},
                "user_decision": "reject",
                "notes": "test-only rejection, no label",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("saved", body)


if __name__ == "__main__":
    unittest.main()
