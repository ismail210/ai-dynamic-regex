"""HTTP-level tests for the repair-trace review flow (Accept / Reject /
Choose alternate) added to routers/semantic.py's review-action endpoint.

Reuses ``IsolatedApiTestCase`` (see test_semantic_api.py) so this suite
never touches real repository data.
"""
from __future__ import annotations

import fitz

import config
from services.document_registry import register_document
from tests.test_documents_api import IsolatedApiTestCase


def _drawing_with_corrupted_label(path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 75), "STRUCTURAL FRAMING PLAN", fontsize=14)
    page.insert_text((72, 130), "W18X4O", fontsize=12)  # O/0 confusion -- deterministic + shadow both fire
    page.insert_text((72, 160), "W24X68", fontsize=12)  # clean control -- must never change
    document.save(path)
    document.close()


class RepairReviewApiTests(IsolatedApiTestCase):
    def _register_and_process(self):
        path = config.settings.uploads_dir / "drawing.pdf"
        _drawing_with_corrupted_label(path)
        manifest = register_document(path, original_name="drawing.pdf")
        document_id = manifest["document_id"]
        self.client.post(f"/api/documents/{document_id}/semantic")
        return document_id

    def _get_annotation(self, document_id, primary_label):
        body = self.client.get(f"/api/documents/{document_id}/semantic").json()
        return next(a for a in body["document"]["annotations"] if a["original_text"] == primary_label)

    def test_repair_candidates_are_attached_via_the_api(self):
        document_id = self._register_and_process()
        ann = self._get_annotation(document_id, "W18X4O")
        self.assertIn("repair_candidates", ann)
        self.assertGreater(len(ann["repair_candidates"]), 0)
        self.assertEqual(ann["repair_candidates"][0]["candidate_text"], "W18X40")
        self.assertEqual(ann["review_status"], "needs_review")

    def test_clean_control_has_no_repair_candidates_and_is_unchanged(self):
        document_id = self._register_and_process()
        clean = self._get_annotation(document_id, "W24X68")
        self.assertEqual(clean["repair_candidates"], [])
        self.assertEqual(clean["effective_text"], "W24X68")

    def test_accept_top_candidate_updates_effective_text_and_preserves_original(self):
        document_id = self._register_and_process()
        ann = self._get_annotation(document_id, "W18X4O")
        top_candidate = ann["repair_candidates"][0]["candidate_text"]

        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "accept", "candidate_text": top_candidate},
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["annotation"]
        self.assertEqual(updated["effective_text"], top_candidate)
        self.assertEqual(updated["original_text"], "W18X4O")
        self.assertEqual(updated["review_status"], "human_accepted")

    def test_bare_accept_without_candidate_applies_top_repair(self):
        """Accept with no candidate_text must still change effective_text."""
        document_id = self._register_and_process()
        ann = self._get_annotation(document_id, "W18X4O")
        top_candidate = ann["repair_candidates"][0]["candidate_text"]

        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "accept"},
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["annotation"]
        self.assertEqual(updated["effective_text"], top_candidate)
        self.assertEqual(updated["original_text"], "W18X4O")
        self.assertEqual(updated["review_status"], "human_accepted")
        self.assertGreaterEqual(response.json()["summary"]["accepted_correction_count"], 1)

    def test_reject_reverts_effective_text_to_original_but_keeps_history(self):
        document_id = self._register_and_process()
        ann = self._get_annotation(document_id, "W18X4O")
        op_count_before = len(ann["operations"])

        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "reject"},
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["annotation"]
        self.assertEqual(updated["effective_text"], "W18X4O", "reject must revert to the original observed text")
        self.assertEqual(updated["review_status"], "human_rejected")
        # History is preserved, not deleted (Section 45).
        self.assertEqual(len(updated["operations"]), op_count_before)
        self.assertTrue(all(not o["accepted"] for o in updated["operations"] if o["operation"] == "repair"))

    def test_choose_alternate_candidate_updates_effective_text(self):
        document_id = self._register_and_process()
        ann = self._get_annotation(document_id, "W18X4O")
        self.assertGreaterEqual(len(ann["repair_candidates"]), 2, "need at least 2 candidates for this test")
        alternate = ann["repair_candidates"][1]["candidate_text"]

        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "accept", "candidate_text": alternate},
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["annotation"]
        self.assertEqual(updated["effective_text"], alternate)
        self.assertEqual(updated["original_text"], "W18X4O")

    def test_unknown_candidate_text_is_rejected_with_400(self):
        document_id = self._register_and_process()
        ann = self._get_annotation(document_id, "W18X4O")
        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "accept", "candidate_text": "NOT_A_REAL_CANDIDATE"},
        )
        self.assertEqual(response.status_code, 400)
