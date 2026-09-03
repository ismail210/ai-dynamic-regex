"""Legend / general-note definitions must not be treated as takeoff members.

Covers checkpoint-4 objective #2: an ``HSS8x4x1/4`` printed in an
abbreviations table on page 5 is a *definition*, not a member on the
structure. It must feed the context analyzer / project-rule profile but
never appear in Results, Drawing Review, the review queue, takeoff counts,
or pricing -- while still being retained internally for provenance.

See ``services.engineering.context_scope`` and its call sites in
``extraction_engine`` / ``multimodal.pipeline`` / ``staged_pipeline``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering import context_scope as cs
from services.engineering.legend_profile import PAGE_ROLE_ABBREVIATIONS


def _doc(tokens, context_pages):
    return {
        "engineering_tokens": list(tokens),
        "legend_profile": {"context_pages": {str(k): v for k, v in context_pages.items()}},
    }


class AnnotateTakeoffScopeTests(unittest.TestCase):
    def test_token_on_abbreviations_page_is_demoted(self):
        doc = _doc(
            [{"page": 5, "text": "HSS8x4x1/4"}, {"page": 30, "text": "HSS8x4x1/2"}],
            {5: PAGE_ROLE_ABBREVIATIONS},
        )
        cs.annotate_takeoff_scope(doc)
        by_page = {t["page"]: t for t in doc["engineering_tokens"]}
        self.assertEqual(by_page[5]["object_scope"], cs.OBJECT_SCOPE_CONTEXT_DEFINITION)
        self.assertFalse(by_page[5]["takeoff_eligible"])
        self.assertTrue(by_page[5]["_skip_unknown_queue"])
        self.assertEqual(by_page[30]["object_scope"], cs.OBJECT_SCOPE_TAKEOFF)
        self.assertTrue(by_page[30]["takeoff_eligible"])

    def test_no_legend_profile_leaves_everything_takeoff_eligible(self):
        doc = {"engineering_tokens": [{"page": 1, "text": "W12X19"}]}
        summary = cs.annotate_takeoff_scope(doc)
        self.assertEqual(summary["context_definition_tokens"], 0)
        self.assertTrue(doc["engineering_tokens"][0]["takeoff_eligible"])

    def test_vision_required_context_page_does_not_demote(self):
        # VISION_REQUIRED is not a readable context role -- a scanned notes
        # page we could not classify with confidence must not silently
        # remove its tokens from takeoff.
        doc = _doc([{"page": 2, "text": "W12X19"}], {2: "VISION_REQUIRED"})
        cs.annotate_takeoff_scope(doc)
        self.assertTrue(doc["engineering_tokens"][0]["takeoff_eligible"])

    def test_reassert_demotes_synthesized_predictions_on_context_pages(self):
        # A geometry "missing label" / label-propagation prediction is
        # synthesized after the extraction-time pass and would otherwise
        # place a phantom member on a legend page.
        document = _doc([], {77: "LEGEND"})
        predictions = [
            {"object_id": "geo1", "source_text": {"page_number": 77}, "prediction_source": "Geometry"},
            {"object_id": "real1", "source_text": {"page_number": 30}, "prediction_source": "Fusion"},
            {"object_id": "already", "page_number": 77, "takeoff_eligible": False},
        ]
        demoted = cs.reassert_prediction_scope(predictions, document)
        self.assertEqual(demoted, 1)
        by_id = {p["object_id"]: p for p in predictions}
        self.assertFalse(by_id["geo1"]["takeoff_eligible"])
        self.assertNotIn("takeoff_eligible", by_id["real1"])  # untouched
        takeoff, context = cs.partition_takeoff(predictions)
        self.assertEqual({p["object_id"] for p in takeoff}, {"real1"})

    def test_partition_keeps_both_sides(self):
        items = [
            {"takeoff_eligible": True, "id": "a"},
            {"takeoff_eligible": False, "id": "b"},
            {"id": "c"},  # missing field -> eligible
        ]
        takeoff, context = cs.partition_takeoff(items)
        self.assertEqual({t["id"] for t in takeoff}, {"a", "c"})
        self.assertEqual({t["id"] for t in context}, {"b"})


class StrictClassifierRegressionTests(unittest.TestCase):
    """Section 10: a steel-heavy framing plan must NOT be demoted just
    because it is dense with W-shapes. context_scope relies on
    legend_profile.detect_context_pages, which already carries the
    ``_looks_like_drawing_page`` negative filter -- this pins that contract."""

    def test_framing_plan_dense_with_shapes_is_not_a_context_page(self):
        from services.engineering.legend_profile import detect_context_pages

        framing = (
            "LEVEL 2 FRAMING PLAN\n"
            "(E) W14x22  (N) W16x26  (E) W18x35  (N) W21x44  (E) W24x55\n"
            "(N) W12x19  (E) W10x12  HSS8x4x1/4  HSS6x6x3/8\n"
        )
        document = {
            "page_count": 1,
            "blocks": [{"page_number": 1, "text": framing}],
            "lines": [],
            "text": framing,
        }
        context_pages = detect_context_pages(document)
        self.assertNotIn(1, context_pages)
        cs_doc = {
            "engineering_tokens": [{"page": 1, "text": "HSS8x4x1/4"}],
            "legend_profile": {"context_pages": {str(k): v for k, v in context_pages.items()}},
        }
        cs.annotate_takeoff_scope(cs_doc)
        self.assertTrue(cs_doc["engineering_tokens"][0]["takeoff_eligible"])

    def test_real_abbreviations_page_is_a_context_page(self):
        from services.engineering.legend_profile import detect_context_pages

        page = (
            "ABBREVIATIONS USED ON STRUCTURAL DRAWINGS\n"
            'THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED:\n'
            '"W8" = W8x10   "W12" = W12x19   "HSS8x4" = HSS8x4x1/4\n'
        )
        document = {
            "page_count": 1,
            "blocks": [{"page_number": 1, "text": page}],
            "lines": [],
            "text": page,
        }
        context_pages = detect_context_pages(document)
        self.assertEqual(context_pages.get(1), PAGE_ROLE_ABBREVIATIONS)

    def test_new_construction_framing_plan_with_notes_keyword_stays_eligible(self):
        """The production bug this fix targets: a non-renovation framing
        plan (no (E)/(N) tags) whose sheet also carries a 'SEE GENERAL
        NOTES' keynote must keep every steel label takeoff-eligible."""

        from services.engineering.legend_profile import detect_context_pages

        sections = " ".join(
            ["W16X26", "W21X44", "W18X35", "W12X19", "HSS8X8X3/8", "W14X22",
             "W10X19", "W24X68", "W16X31", "W18X40", "W30X99", "W8X15",
             "W12X26", "W16X36", "W21X50"] * 2
        )
        framing = (
            "SECOND FLOOR FRAMING PLAN\n"
            "SEE GENERAL NOTES ON S-001.  SPECIFICATIONS SECTION 05 12 00.\n"
            + sections + "\n"
        )
        document = {
            "page_count": 1,
            "blocks": [{"page_number": 1, "text": framing}],
            "lines": [],
            "text": framing,
        }
        context_pages = detect_context_pages(document)
        self.assertNotIn(1, context_pages)

        cs_doc = {
            "engineering_tokens": [
                {"page": 1, "text": "W16X26"},
                {"page": 1, "text": "HSS8X8X3/8"},
            ],
            "legend_profile": {
                "context_pages": {str(k): v for k, v in context_pages.items()},
                "diagnostics": {"full_page_demotion_blocked_pages": []},
            },
        }
        summary = cs.annotate_takeoff_scope(cs_doc)
        self.assertTrue(all(t["takeoff_eligible"] for t in cs_doc["engineering_tokens"]))
        self.assertEqual(summary["context_definition_tokens"], 0)


class PipelineIntegrationTests(unittest.TestCase):
    """End to end through extract_engineering_document: a synthetic PDF with
    an abbreviations page and a framing page. The abbreviations-page steel
    string is retained on the document but flagged takeoff_eligible=False."""

    def _pdf(self, pages):
        tmp = Path(tempfile.mkdtemp()) / "drawing.pdf"
        doc = fitz.open()
        for text in pages:
            page = doc.new_page(width=612, height=792)
            page.insert_text((60, 80), text, fontsize=11)
        doc.save(tmp)
        doc.close()
        return tmp

    def test_extraction_engine_attaches_scope_summary_and_flags(self):
        from services.extraction_engine import extract_engineering_document

        pdf = self._pdf(
            [
                "STRUCTURAL GENERAL NOTES\nABBREVIATIONS USED ON STRUCTURAL DRAWINGS\n"
                'THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED ON THE FRAMING PLANS:\n'
                '"W12" = W12X19\n"HSS8X4" = HSS8X4X1/4\n',
                "SECOND FLOOR FRAMING PLAN\nW12X19  W16X26  HSS8X4X1/4  W14X22  W18X35\n",
            ]
        )
        document = extract_engineering_document(pdf, document_id="ctx_scope_it")

        # The scope pass always runs and always reports.
        summary = document.get("context_scope_summary") or {}
        self.assertIn("context_definition_tokens", summary)
        self.assertIn("takeoff_tokens", summary)

        # Every token carries the two fields, and no token was removed.
        tokens = document["engineering_tokens"]
        self.assertEqual(
            summary["context_definition_tokens"] + summary["takeoff_tokens"],
            len(tokens),
        )
        for token in tokens:
            self.assertIn(token.get("object_scope"), {cs.OBJECT_SCOPE_TAKEOFF, cs.OBJECT_SCOPE_CONTEXT_DEFINITION})
            page = int(token.get("page") or 0)
            demoted = page in set(summary.get("context_definition_pages") or [])
            self.assertEqual(token.get("takeoff_eligible"), not demoted)

        # M: a demoted token is still in engineering_tokens (never deleted).
        # K / L: partition_takeoff is what every served surface filters on.
        takeoff, context = cs.partition_takeoff(tokens)
        self.assertEqual(len(takeoff) + len(context), len(tokens))


if __name__ == "__main__":
    unittest.main()
