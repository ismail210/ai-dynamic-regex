"""Corrected PDF export + Accept / Accept-All must change real PDF bytes."""
from __future__ import annotations

import hashlib

import fitz

import config
from services.document_registry import document_source, register_document
from services.semantic.corrected_pdf import (
    build_corrected_pdf,
    corrected_pdf_path,
    list_accepted_text_corrections,
)
from tests.helpers.isolated_api import IsolatedApiTestCase


def _drawing(path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 75), "STRUCTURAL FRAMING PLAN", fontsize=14)
    page.insert_text((72, 130), "W18X4O", fontsize=12)
    page.insert_text((72, 160), "W24X68", fontsize=12)
    page.insert_text((72, 190), "W16X2O", fontsize=12)
    document.save(path)
    document.close()


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CorrectedPdfExportTests(IsolatedApiTestCase):
    def _register_and_process(self):
        path = config.settings.uploads_dir / "drawing.pdf"
        _drawing(path)
        manifest = register_document(path, original_name="drawing.pdf")
        document_id = manifest["document_id"]
        self.client.post(f"/api/documents/{document_id}/semantic")
        return document_id

    def _get_ann(self, document_id, original):
        body = self.client.get(f"/api/documents/{document_id}/semantic").json()
        return next(a for a in body["document"]["annotations"] if a["original_text"] == original)

    def test_download_requires_accepted_corrections(self):
        document_id = self._register_and_process()
        response = self.client.get(f"/api/documents/{document_id}/semantic/corrected-pdf")
        self.assertEqual(response.status_code, 400)

    def test_accept_syncs_corrected_pdf_in_review_response_and_preserves_original(self):
        document_id = self._register_and_process()
        source = document_source(document_id)
        original_hash = _sha256(source)

        ann = self._get_ann(document_id, "W18X4O")
        top = ann["repair_candidates"][0]["candidate_text"]
        accept = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "accept", "candidate_text": top},
        )
        self.assertEqual(accept.status_code, 200)
        body = accept.json()
        self.assertEqual(body["annotation"]["effective_text"], top)
        self.assertTrue(body["corrected_pdf"]["available"])
        self.assertNotEqual(body["corrected_pdf"]["revision"], "none")
        self.assertIn("corrected-pdf?v=", body["corrected_pdf"]["url"])
        self.assertGreaterEqual(body["summary"]["accepted_correction_count"], 1)

        # Original upload immutable
        self.assertEqual(_sha256(source), original_hash)
        src_doc = fitz.open(source)
        self.assertIn("W18X4O", src_doc[0].get_text())
        src_doc.close()

        # Artifact on disk contains the new text
        path = corrected_pdf_path(document_id)
        self.assertTrue(path.exists())
        corrected = fitz.open(path)
        text = corrected[0].get_text()
        self.assertIn(top, text)
        self.assertIn("W24X68", text)
        corrected.close()
        self.assertNotEqual(_sha256(path), original_hash)

        # Viewer endpoint serves the same corrected bytes (cache-bust query ok)
        response = self.client.get(
            f"/api/documents/{document_id}/semantic/corrected-pdf",
            params={"v": body["corrected_pdf"]["revision"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("no-store", response.headers.get("cache-control", ""))
        out = fitz.open(stream=response.content, filetype="pdf")
        self.assertIn(top, out[0].get_text())
        out.close()

    def test_accept_then_download_includes_corrected_text_and_preserves_pages(self):
        document_id = self._register_and_process()
        ann = self._get_ann(document_id, "W18X4O")
        top = ann["repair_candidates"][0]["candidate_text"]
        accept = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "accept", "candidate_text": top},
        )
        self.assertEqual(accept.status_code, 200)

        response = self.client.get(f"/api/documents/{document_id}/semantic/corrected-pdf")
        self.assertEqual(response.status_code, 200)

        src = config.settings.uploads_dir / "drawing.pdf"
        src_doc = fitz.open(src)
        self.assertEqual(src_doc.page_count, 1)
        self.assertIn("W18X4O", src_doc[0].get_text())
        src_doc.close()

        out = fitz.open(stream=response.content, filetype="pdf")
        self.assertEqual(out.page_count, 1)
        text = out[0].get_text()
        self.assertIn(top, text)
        self.assertIn("W24X68", text)
        out.close()

    def test_reject_does_not_count_toward_export(self):
        document_id = self._register_and_process()
        ann = self._get_ann(document_id, "W18X4O")
        self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "reject"},
        )
        body = self.client.get(f"/api/documents/{document_id}/semantic").json()
        self.assertEqual(list_accepted_text_corrections(body["document"]), [])

    def test_manual_edit_accept_is_authoritative_and_keeps_raw(self):
        document_id = self._register_and_process()
        ann = self._get_ann(document_id, "W18X4O")
        response = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "edit", "edited_text": "W18X36"},
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["annotation"]
        self.assertEqual(updated["effective_text"], "W18X36")
        self.assertEqual(updated["original_text"], "W18X4O")
        self.assertEqual(updated["review_status"], "human_accepted")
        self.assertTrue(any(h.get("action") == "edit" for h in updated["review"]["history"]))
        self.assertTrue(response.json()["corrected_pdf"]["available"])

        rebuilt = build_corrected_pdf(
            document_id,
            self.client.get(f"/api/documents/{document_id}/semantic").json()["document"],
        )
        doc = fitz.open(rebuilt)
        self.assertIn("W18X36", doc[0].get_text())
        doc.close()

    def test_accept_all_applies_all_eligible_once_and_skips_rejected(self):
        document_id = self._register_and_process()
        source = document_source(document_id)
        original_hash = _sha256(source)

        bad1 = self._get_ann(document_id, "W18X4O")
        bad2 = self._get_ann(document_id, "W16X2O")
        clean = self._get_ann(document_id, "W24X68")

        # Reject one eligible case — Accept All must leave it rejected.
        reject = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{bad2['annotation_id']}/review",
            json={"action": "reject"},
        )
        self.assertEqual(reject.status_code, 200)

        result = self.client.post(f"/api/documents/{document_id}/semantic/corrections/accept-all")
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertGreaterEqual(body["accepted_count"], 1)
        self.assertIn(bad1["annotation_id"], body["accepted_annotation_ids"])
        self.assertNotIn(bad2["annotation_id"], body["accepted_annotation_ids"])
        self.assertNotIn(clean["annotation_id"], body["accepted_annotation_ids"])
        self.assertTrue(body["corrected_pdf"]["available"])

        # Individual history events (not one collapsed event)
        doc = body["document"]
        ann1 = next(a for a in doc["annotations"] if a["annotation_id"] == bad1["annotation_id"])
        self.assertEqual(ann1["review_status"], "human_accepted")
        self.assertTrue(any(h.get("action") == "accept" for h in ann1["review"]["history"]))
        self.assertTrue(any(h.get("bulk") == "accept_all" for h in ann1["review"]["history"]))

        ann2 = next(a for a in doc["annotations"] if a["annotation_id"] == bad2["annotation_id"])
        self.assertEqual(ann2["review_status"], "human_rejected")

        self.assertEqual(_sha256(source), original_hash)
        path = corrected_pdf_path(document_id)
        self.assertTrue(path.exists())
        text = fitz.open(path)[0].get_text()
        self.assertIn(ann1["effective_text"], text)
        self.assertNotEqual(_sha256(path), original_hash)

    def test_second_accept_does_not_leave_stale_pdf(self):
        document_id = self._register_and_process()
        ann = self._get_ann(document_id, "W18X4O")
        top = ann["repair_candidates"][0]["candidate_text"]
        first = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "accept", "candidate_text": top},
        )
        rev1 = first.json()["corrected_pdf"]["revision"]

        # Manual edit to a different value — revision and bytes must change.
        second = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "edit", "edited_text": "W18X50"},
        )
        self.assertEqual(second.status_code, 200)
        rev2 = second.json()["corrected_pdf"]["revision"]
        self.assertNotEqual(rev1, rev2)
        text = fitz.open(corrected_pdf_path(document_id))[0].get_text()
        self.assertIn("W18X50", text)


class CorrectedPdfFractionAndPlacementTests(IsolatedApiTestCase):
    def test_list_accepted_includes_spacing_normalization(self):
        corrections = list_accepted_text_corrections(
            {
                "annotations": [
                    {
                        "annotation_id": "a_space",
                        "page": 1,
                        "original_text": "W 18 X 46",
                        "effective_text": "W18X46",
                        "review_status": "auto_accepted",
                        "semantic_bbox": [72.0, 120.0, 200.0, 134.0],
                    }
                ]
            }
        )
        self.assertEqual(len(corrections), 1)
        self.assertEqual(corrections[0]["effective_text"], "W18X46")
        self.assertEqual(corrections[0]["original_text"], "W 18 X 46")

    def test_process_writes_spacing_into_corrected_pdf(self):
        path = config.settings.uploads_dir / "spacing_norm.pdf"
        document = fitz.open()
        page = document.new_page(width=612, height=792)
        page.insert_text((100, 200), "W 18 X 46", fontsize=12)
        page.insert_text((100, 240), "W12X26", fontsize=12)
        document.save(path)
        document.close()

        manifest = register_document(path, original_name="spacing_norm.pdf")
        document_id = manifest["document_id"]
        processed = self.client.post(f"/api/documents/{document_id}/semantic")
        self.assertEqual(processed.status_code, 200)
        body = processed.json()
        # Process must not block on PDF rebuild; accepted spacing is counted.
        self.assertGreaterEqual(body["summary"]["accepted_correction_count"], 1)

        # Download/export builds the derived PDF on demand (and TestClient
        # may also have flushed the background warm task).
        response = self.client.get(f"/api/documents/{document_id}/semantic/corrected-pdf")
        self.assertEqual(response.status_code, 200)
        out_path = corrected_pdf_path(document_id)
        self.assertTrue(out_path.exists())
        text = fitz.open(out_path)[0].get_text()
        self.assertIn("W18X46", text)
        source = document_source(document_id)
        self.assertNotEqual(_sha256(out_path), _sha256(source))
        self.assertIn("W 18 X 46", fitz.open(source)[0].get_text())

    def test_list_accepted_formats_decimal_third_dimension(self):
        corrections = list_accepted_text_corrections(
            {
                "annotations": [
                    {
                        "annotation_id": "a_angle",
                        "page": 1,
                        "original_text": "L4X4X0.375",
                        "effective_text": "L4X4X0.375",
                        "review_status": "human_accepted",
                        "semantic_bbox": [72.0, 120.0, 160.0, 134.0],
                    }
                ]
            }
        )
        self.assertEqual(len(corrections), 1)
        self.assertEqual(corrections[0]["effective_text"], "L4X4X3/8")

    def test_accept_writes_fractional_third_dimension_not_decimal(self):
        path = config.settings.uploads_dir / "angle_decimal.pdf"
        document = fitz.open()
        page = document.new_page(width=612, height=792)
        page.insert_text((100, 200), "L4X4X0.375", fontsize=12)
        page.insert_text((100, 240), "W12X26", fontsize=12)
        document.save(path)
        document.close()

        manifest = register_document(path, original_name="angle_decimal.pdf")
        document_id = manifest["document_id"]
        self.client.post(f"/api/documents/{document_id}/semantic")

        body = self.client.get(f"/api/documents/{document_id}/semantic").json()
        ann = next(a for a in body["document"]["annotations"] if a["original_text"] == "L4X4X0.375")

        # Force human accept with decimal input — PDF must store the fraction.
        accept = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "edit", "edited_text": "L4X4X0.375"},
        )
        self.assertEqual(accept.status_code, 200)
        self.assertEqual(accept.json()["annotation"]["effective_text"], "L4X4X3/8")

        source = document_source(document_id)
        original_hash = _sha256(source)
        out_path = corrected_pdf_path(document_id)
        self.assertTrue(out_path.exists())
        text = fitz.open(out_path)[0].get_text()
        self.assertIn("L4X4X3/8", text)
        # Authoritative written correction is fractional (list_accepted formats too).
        applied = list_accepted_text_corrections(
            self.client.get(f"/api/documents/{document_id}/semantic").json()["document"]
        )
        self.assertTrue(any(c["effective_text"] == "L4X4X3/8" for c in applied))
        self.assertFalse(any("0.375" in (c["effective_text"] or "") for c in applied))
        self.assertEqual(_sha256(source), original_hash)

    def test_replacement_cover_tracks_measured_text_width(self):
        """Shorter corrected text must not leave a large empty white pad."""
        from services.semantic.corrected_pdf import _fit_font_size, _replace_label

        doc = fitz.open()
        page = doc.new_page(width=400, height=200)
        bbox = [50.0, 80.0, 150.0, 94.0]
        page.insert_text((50, 92), "W18X4O", fontsize=11)
        original_w = bbox[2] - bbox[0]
        fs, text_w = _fit_font_size("W18X40", original_w, bbox[3] - bbox[1])
        self.assertLessEqual(text_w, original_w + 1.0)
        _replace_label(page, bbox, "W18X40")
        text = page.get_text()
        self.assertIn("W18X40", text)
        self.assertGreater(fs, 4.0)
        doc.close()

    def test_incomplete_l4x4_accept_does_not_invent_thickness_in_pdf(self):
        path = config.settings.uploads_dir / "incomplete_l.pdf"
        document = fitz.open()
        page = document.new_page(width=612, height=792)
        page.insert_text((72, 120), "L4X4", fontsize=12)
        document.save(path)
        document.close()

        manifest = register_document(path, original_name="incomplete_l.pdf")
        document_id = manifest["document_id"]
        self.client.post(f"/api/documents/{document_id}/semantic")
        body = self.client.get(f"/api/documents/{document_id}/semantic").json()
        ann = next(a for a in body["document"]["annotations"] if a["original_text"] == "L4X4")
        edit = self.client.patch(
            f"/api/documents/{document_id}/semantic/annotations/{ann['annotation_id']}/review",
            json={"action": "edit", "edited_text": "L4X4"},
        )
        self.assertEqual(edit.status_code, 200)
        self.assertEqual(edit.json()["annotation"]["effective_text"], "L4X4")
        self.assertFalse(edit.json()["corrected_pdf"]["available"])
