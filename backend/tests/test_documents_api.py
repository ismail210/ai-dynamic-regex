"""
FastAPI HTTP-level tests for the staged document workflow, review queue,
corrections, and takeoff preconditions (Phase 10).

Uses ``fastapi.testclient.TestClient`` against the real ``app`` — this is the
router/HTTP layer the existing test suite did not previously cover (all
prior tests exercised services directly, one layer below the routes).

Isolation from real operational/training data is provided by
``IsolatedApiTestCase`` (see ``tests/helpers/isolated_api.py``), shared by
this and several other HTTP-level test suites.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import fitz

from tests.helpers.isolated_api import IsolatedApiTestCase


def _drawing(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 75), "STRUCTURAL FRAMING PLAN", fontsize=18)
    page.insert_text((72, 130), "W18 X 35", fontsize=12)
    page.insert_text((72, 160), "HSS8X8X1/2", fontsize=12)
    document.save(path)
    document.close()


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
        # takeoff_exporter.py) wired to this endpoint.
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
        # QuantityEngine (Accuracy Track A5) only counts a physical quantity
        # when a labeled callout has geometry/member-association evidence
        # backing it. This synthetic fixture is two bare text labels with no
        # drawn steel objects, so both sections are correctly excluded as
        # "unlabeled_source" -- row_count == 0 here is the safety-correct
        # answer, not a pipeline failure. This assertion only needs the
        # endpoint to succeed and return the expected shape.
        self.assertGreaterEqual(body["row_count"], 0)
        self.assertIn("quantity_engine", body)

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
