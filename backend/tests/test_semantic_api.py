"""HTTP-level tests for the semantic preprocessor API (routers/semantic.py).

Reuses ``IsolatedApiTestCase`` from ``test_documents_api`` so this suite
never touches real repository data (uploads/artifacts/document registry).
"""
from __future__ import annotations

import fitz

import config
from services.document_registry import register_document
from tests.test_documents_api import IsolatedApiTestCase


def _demo_drawing(path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 75), "GENERAL NOTES", fontsize=14)
    page.insert_text((72, 100), '"W8" = W8x10', fontsize=10)
    page.insert_text((72, 200), "W8", fontsize=12)  # bare shorthand elsewhere
    page.insert_text((72, 230), "HSS 8X8X1/2", fontsize=12)  # spacing normalization case
    document.save(path)
    document.close()


class SemanticApiTests(IsolatedApiTestCase):
    def _register(self):
        # document_source() only allows paths under settings.uploads_dir /
        # engineering_uploads_dir -- both redirected to a temp dir by
        # IsolatedApiTestCase.setUp -- so the fixture PDF must live there.
        path = config.settings.uploads_dir / "drawing.pdf"
        _demo_drawing(path)
        manifest = register_document(path, original_name="drawing.pdf")
        return manifest["document_id"]

    def test_process_then_get_round_trips(self):
        document_id = self._register()
        response = self.client.post(f"/api/documents/{document_id}/semantic")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("document", body)
        self.assertIn("summary", body)
        self.assertGreater(body["summary"]["annotation_count"], 0)

        get_response = self.client.get(f"/api/documents/{document_id}/semantic")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(
            get_response.json()["document"]["document_id"],
            body["document"]["document_id"],
        )

    def test_completion_from_real_note_reaches_the_api(self):
        document_id = self._register()
        self.client.post(f"/api/documents/{document_id}/semantic")
        result = self.client.get(f"/api/documents/{document_id}/semantic").json()
        annotations = result["document"]["annotations"]
        w8 = next(a for a in annotations if a["primary_label"] == "W8")
        self.assertEqual(w8["correction"]["operation"], "completion")
        self.assertEqual(w8["correction"]["canonical"], "W8X10")

    def test_unprocessed_document_returns_not_ready(self):
        """Empty cache is a normal state — must be HTTP 200, not 404.

        Semantic Review GETs on every page load; a 404 here only spams the
        browser console and looks like a failure to the user.
        """
        document_id = self._register()
        response = self.client.get(f"/api/documents/{document_id}/semantic")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["document"])
        self.assertIsNone(body["summary"])
        self.assertEqual(body["status"], "not_ready")

    def test_unknown_document_semantic_get_is_404(self):
        response = self.client.get("/api/documents/doc_doesnotexist00000000/semantic")
        self.assertEqual(response.status_code, 404)

    def test_review_accept_updates_status(self):
        document_id = self._register()
        self.client.post(f"/api/documents/{document_id}/semantic")
        result = self.client.get(f"/api/documents/{document_id}/semantic").json()
        annotation_id = result["document"]["annotations"][0]["annotation_id"]

        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{annotation_id}/review",
            json={"action": "accept"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["annotation"]["review_status"], "human_accepted")

        # Persisted -- a fresh GET reflects the change.
        refreshed = self.client.get(f"/api/documents/{document_id}/semantic").json()
        updated = next(
            a for a in refreshed["document"]["annotations"] if a["annotation_id"] == annotation_id
        )
        self.assertEqual(updated["review_status"], "human_accepted")

    def test_reject_reverts_to_original_text(self):
        document_id = self._register()
        self.client.post(f"/api/documents/{document_id}/semantic")
        result = self.client.get(f"/api/documents/{document_id}/semantic").json()
        w8 = next(a for a in result["document"]["annotations"] if a["primary_label"] == "W8")

        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{w8['annotation_id']}/review",
            json={"action": "reject"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()["annotation"]
        self.assertEqual(body["correction"]["canonical"], "W8")
        # A human explicitly reviewed and rejected this -- distinct from
        # "needs_review" (nobody has looked yet). The rejected proposal
        # itself is preserved in `operations`, not deleted (Section 45).
        self.assertEqual(body["review_status"], "human_rejected")
        self.assertTrue(any(not o["accepted"] for o in body["operations"]))

    def test_review_unknown_annotation_is_404(self):
        document_id = self._register()
        self.client.post(f"/api/documents/{document_id}/semantic")
        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/does-not-exist/review",
            json={"action": "accept"},
        )
        self.assertEqual(response.status_code, 404)

    def test_missing_document_semantic_process_is_404(self):
        response = self.client.post("/api/documents/doc_doesnotexist00000000/semantic")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    import unittest
    unittest.main()
