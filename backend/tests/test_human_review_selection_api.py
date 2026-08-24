"""
HTTP-level regression coverage for the human-review resolution path used by
Drawing Review and the Results/Corrections candidate picker: a reviewer
selecting a catalog-valid completion for a missing-thickness HSS label must
become the canonical resolved section everywhere the analysis is re-served,
while the raw drawing text stays available as separate provenance.

Complements backend/tests/test_human_selections.py (which exercises
services.staged_pipeline._apply_human_selections directly) by going through
the real HTTP router stack -- POST /api/engineering/corrections, then a
fresh GET /api/documents/{id}/analysis, exactly like a page refresh -- so a
wiring break between the router and the overlay would fail here even if the
service-level unit test still passed.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from tests.test_documents_api import IsolatedApiTestCase


def _hss_drawing(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 75), "STRUCTURAL FRAMING PLAN", fontsize=18)
    # Outside dimensions are known (8x8); wall thickness is not present --
    # this is the exact "missing_dimension_field" shape services.hss_completion
    # exists for, not a corrupted/wildcard read.
    page.insert_text((72, 130), "HSS8X8", fontsize=12)
    page.insert_text((72, 160), "HSS8X8", fontsize=12)
    document.save(path)
    document.close()


class HumanReviewSelectionApiTests(IsolatedApiTestCase):
    def _analyze_hss_document(self) -> dict:
        pdf_path = Path(self.temp.name) / "hss_drawing.pdf"
        _hss_drawing(pdf_path)
        with open(pdf_path, "rb") as handle:
            upload = self.client.post(
                "/api/documents",
                files={"file": ("hss_drawing.pdf", handle, "application/pdf")},
            )
        self.assertEqual(upload.status_code, 201)
        document_id = upload.json()["document_id"]
        self.client.post(f"/api/documents/{document_id}/extract")
        response = self.client.post(f"/api/documents/{document_id}/analyze")
        self.assertEqual(response.status_code, 200)
        return {"document_id": document_id, "body": response.json()}

    def _missing_dimension_predictions(self, body: dict) -> list[dict]:
        return [
            prediction
            for prediction in body["predictions"]
            if prediction.get("candidate_sections")
        ]

    def test_human_selection_persists_as_resolved_section_across_refetch(self):
        analyzed = self._analyze_hss_document()
        document_id = analyzed["document_id"]
        pending = self._missing_dimension_predictions(analyzed["body"])
        if not pending:
            self.skipTest(
                "AISC database in this environment has no HSS8X8 completions "
                "to select from; nothing to exercise."
            )
        target = pending[0]
        object_id = target["object_id"]
        raw_text = target["source_text"]["raw"]
        chosen = target["candidate_sections"][0]["designation"]

        # Before selection: genuinely unresolved.
        self.assertTrue(target["needs_review"])
        self.assertEqual(
            target["canonical"]["comparison"]["match_status"], "missing_dimension_field"
        )

        correction = self.client.post(
            "/api/engineering/corrections",
            json={
                "document_id": document_id,
                "object_id": object_id,
                "correct_label": chosen,
                "user_decision": "human_review_selection",
                "prediction": target,
                "notes": "test: reviewer selected a candidate",
            },
        )
        self.assertEqual(correction.status_code, 200)

        # Test A: a fresh GET (a page refresh) must serve the resolved
        # section, not the pre-review candidate list state.
        refetched = self.client.get(f"/api/documents/{document_id}/analysis")
        self.assertEqual(refetched.status_code, 200)
        resolved = next(
            p for p in refetched.json()["predictions"] if p["object_id"] == object_id
        )
        self.assertEqual(resolved["section"], chosen)
        self.assertEqual(resolved["human_selected_section"], chosen)
        self.assertEqual(resolved["decision_source"], "human_review")
        self.assertFalse(resolved["needs_review"])
        self.assertEqual(
            resolved["canonical"]["prediction"]["final_label"], chosen
        )
        self.assertEqual(
            resolved["canonical"]["comparison"]["match_status"], "human_resolved"
        )

        # The raw drawing text is provenance, never overwritten by the
        # reviewer's choice.
        self.assertEqual(resolved["source_text"]["raw"], raw_text)
        self.assertNotEqual(raw_text, chosen)

        # Test E: repeating the GET (simulating reopening Drawing Review)
        # must keep returning the same resolved state, not just once.
        refetched_again = self.client.get(f"/api/documents/{document_id}/analysis")
        resolved_again = next(
            p
            for p in refetched_again.json()["predictions"]
            if p["object_id"] == object_id
        )
        self.assertEqual(resolved_again["section"], chosen)
        self.assertEqual(resolved_again["decision_source"], "human_review")

    def test_duplicate_source_text_resolves_the_selected_object_only(self):
        # Test D: two independent objects share the exact same raw OCR text
        # ("HSS8X8" appears twice in the fixture drawing) -- selecting a
        # candidate for one must never resolve the other by text-matching.
        analyzed = self._analyze_hss_document()
        document_id = analyzed["document_id"]
        pending = self._missing_dimension_predictions(analyzed["body"])
        if len(pending) < 2:
            self.skipTest("Fixture did not produce two independent HSS8X8 objects.")
        first, second = pending[0], pending[1]
        self.assertNotEqual(first["object_id"], second["object_id"])
        self.assertEqual(
            first["source_text"]["raw"], second["source_text"]["raw"]
        )
        chosen = first["candidate_sections"][0]["designation"]

        response = self.client.post(
            "/api/engineering/corrections",
            json={
                "document_id": document_id,
                "object_id": first["object_id"],
                "correct_label": chosen,
                "user_decision": "human_review_selection",
                "prediction": first,
            },
        )
        self.assertEqual(response.status_code, 200)

        refetched = self.client.get(f"/api/documents/{document_id}/analysis").json()
        by_id = {p["object_id"]: p for p in refetched["predictions"]}
        self.assertEqual(by_id[first["object_id"]]["decision_source"], "human_review")
        self.assertNotEqual(by_id[second["object_id"]].get("decision_source"), "human_review")
        self.assertTrue(by_id[second["object_id"]]["needs_review"])

    def test_response_returns_the_resolved_prediction_immediately(self):
        # The frontend must not have to reconstruct canonical fields from
        # "success: true" -- the response carries the already-overlaid
        # record for the object just resolved.
        analyzed = self._analyze_hss_document()
        document_id = analyzed["document_id"]
        pending = self._missing_dimension_predictions(analyzed["body"])
        if not pending:
            self.skipTest("No HSS8X8 completions available in this environment.")
        target = pending[0]
        chosen = target["candidate_sections"][0]["designation"]

        response = self.client.post(
            "/api/engineering/corrections",
            json={
                "document_id": document_id,
                "object_id": target["object_id"],
                "correct_label": chosen,
                "user_decision": "human_review_selection",
                "prediction": target,
            },
        )
        self.assertEqual(response.status_code, 200)
        resolved = response.json()["resolved_prediction"]
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["section"], chosen)
        self.assertEqual(resolved["human_selected_section"], chosen)
        self.assertEqual(resolved["decision_source"], "human_review")
        self.assertEqual(
            resolved["canonical"]["comparison"]["match_status"], "human_resolved"
        )
        # Raw text on the immediate response, same guarantee as the refetch.
        self.assertEqual(resolved["source_text"]["raw"], target["source_text"]["raw"])

    def test_manual_other_correction_with_a_valid_catalog_section_is_canonicalized(self):
        # Test: "Other" -> valid catalog designation -> canonical spelling
        # saved, even when the reviewer typed it in a different case.
        analyzed = self._analyze_hss_document()
        document_id = analyzed["document_id"]
        pending = self._missing_dimension_predictions(analyzed["body"])
        if not pending:
            self.skipTest("No HSS8X8 completions available in this environment.")
        target = pending[0]
        # A real catalog section for this dimension pair that is NOT one of
        # the generated candidates, typed lowercase -- proves this goes
        # through catalog validation/canonicalization, not a pass-through
        # of whatever the candidate list already offered.
        manual_value = "hss8x8x5/8"

        response = self.client.post(
            "/api/engineering/corrections",
            json={
                "document_id": document_id,
                "object_id": target["object_id"],
                "correct_label": manual_value,
                "user_decision": "human_review_selection",
                "prediction": target,
                "notes": "test: reviewer entered a manual correction",
            },
        )
        self.assertEqual(response.status_code, 200)
        resolved = response.json()["resolved_prediction"]
        self.assertEqual(resolved["section"], "HSS8X8X5/8")
        self.assertEqual(resolved["human_selected_section"], "HSS8X8X5/8")

        refetched = self.client.get(f"/api/documents/{document_id}/analysis").json()
        stored = next(
            p for p in refetched["predictions"] if p["object_id"] == target["object_id"]
        )
        self.assertEqual(stored["section"], "HSS8X8X5/8")

    def test_invalid_manual_correction_is_rejected_and_never_persisted(self):
        # Test: invalid catalog designation -> rejected, not silently
        # accepted as if it were a real AISC section.
        analyzed = self._analyze_hss_document()
        document_id = analyzed["document_id"]
        pending = self._missing_dimension_predictions(analyzed["body"])
        if not pending:
            self.skipTest("No HSS8X8 completions available in this environment.")
        target = pending[0]

        response = self.client.post(
            "/api/engineering/corrections",
            json={
                "document_id": document_id,
                "object_id": target["object_id"],
                "correct_label": "HSS8X8XBANANA",
                "user_decision": "human_review_selection",
                "prediction": target,
            },
        )
        self.assertEqual(response.status_code, 422)

        # Nothing was persisted -- the object is still exactly as unresolved
        # as before the rejected attempt.
        refetched = self.client.get(f"/api/documents/{document_id}/analysis").json()
        stored = next(
            p for p in refetched["predictions"] if p["object_id"] == target["object_id"]
        )
        self.assertTrue(stored["needs_review"])
        self.assertNotEqual(stored.get("decision_source"), "human_review")

    def test_a_prior_selection_can_be_changed(self):
        # Test: choice A -> choice B -> B persisted (not locked after the
        # first human decision).
        analyzed = self._analyze_hss_document()
        document_id = analyzed["document_id"]
        pending = self._missing_dimension_predictions(analyzed["body"])
        if not pending:
            self.skipTest("No HSS8X8 completions available in this environment.")
        target = pending[0]
        candidates = [c["designation"] for c in target["candidate_sections"]]
        if len(candidates) < 2:
            self.skipTest("Need at least two candidates to exercise changing a decision.")
        first_choice, second_choice = candidates[0], candidates[1]

        for choice in (first_choice, second_choice):
            response = self.client.post(
                "/api/engineering/corrections",
                json={
                    "document_id": document_id,
                    "object_id": target["object_id"],
                    "correct_label": choice,
                    "user_decision": "human_review_selection",
                    "prediction": target,
                },
            )
            self.assertEqual(response.status_code, 200)

        refetched = self.client.get(f"/api/documents/{document_id}/analysis").json()
        stored = next(
            p for p in refetched["predictions"] if p["object_id"] == target["object_id"]
        )
        self.assertEqual(stored["section"], second_choice)
        self.assertEqual(stored["human_selected_section"], second_choice)
