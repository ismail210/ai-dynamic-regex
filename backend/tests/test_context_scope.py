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
            summary["context_definition_tokens"]
            + summary.get("detail_reference_tokens", 0)
            + summary["takeoff_tokens"],
            len(tokens),
        )
        for token in tokens:
            self.assertIn(
                token.get("object_scope"),
                {
                    cs.OBJECT_SCOPE_TAKEOFF,
                    cs.OBJECT_SCOPE_CONTEXT_DEFINITION,
                    cs.OBJECT_SCOPE_DETAIL_REFERENCE,
                    cs.OBJECT_SCOPE_NON_MEMBER_DIMENSION,
                },
            )
            page = int(token.get("page") or 0)
            demoted = cs.is_clip_fabrication_token(token) or (
                (
                    page in set(summary.get("context_definition_pages") or [])
                    or page in set(summary.get("typical_detail_pages") or [])
                )
                and not cs.is_specified_typical_member_token(token)
            )
            self.assertEqual(token.get("takeoff_eligible"), not demoted)

        # M: a demoted token is still in engineering_tokens (never deleted).
        # K / L: partition_takeoff is what every served surface filters on.
        takeoff, context = cs.partition_takeoff(tokens)
        self.assertEqual(len(takeoff) + len(context), len(tokens))


class TypicalDetailAndClipScopeTests(unittest.TestCase):
    def _title_blocks(self, page, title, *, x=2736.0, y=1838.0):
        return [
            {
                "page_number": page,
                "bbox": [x, y, x + 80, y + 10],
                "text": "DRAWING TITLE:",
            },
            {
                "page_number": page,
                "bbox": [x, y + 14, x + 200, y + 40],
                "text": title,
            },
        ]

    def test_typical_details_page_is_not_a_rolled_member(self):
        doc = {
            "engineering_tokens": [
                {"page": 18, "text": "W12X230", "raw_text": "W12X230"},
                {"page": 7, "text": "W12X16", "raw_text": "W12X16"},
            ],
            "title_blocks": (
                self._title_blocks(18, "TYPICAL DETAILS")
                + self._title_blocks(7, "UPPER FLOOR FRAMING PLAN PART A")
            ),
        }
        summary = cs.annotate_takeoff_scope(doc)
        self.assertEqual(summary["typical_detail_pages"], [18])
        by_page = {t["page"]: t for t in doc["engineering_tokens"]}
        self.assertEqual(by_page[18]["object_scope"], cs.OBJECT_SCOPE_DETAIL_REFERENCE)
        self.assertFalse(by_page[18]["takeoff_eligible"])
        self.assertEqual(by_page[7]["object_scope"], cs.OBJECT_SCOPE_TAKEOFF)
        self.assertTrue(by_page[7]["takeoff_eligible"])

    def test_typical_framing_plan_stays_eligible(self):
        doc = {
            "engineering_tokens": [{"page": 18, "text": "W16X26", "raw_text": "W16X26"}],
            "title_blocks": self._title_blocks(18, "TYPICAL FRAMING PLAN - LEVEL 06-10"),
        }
        cs.annotate_takeoff_scope(doc)
        self.assertTrue(doc["engineering_tokens"][0]["takeoff_eligible"])
        self.assertEqual(doc["engineering_tokens"][0]["object_scope"], cs.OBJECT_SCOPE_TAKEOFF)

    def test_steel_sections_and_details_stay_eligible(self):
        doc = {
            "engineering_tokens": [
                {"page": 36, "text": "HSS6X4X3/8", "raw_text": "HSS6X4X3/8"}
            ],
            "title_blocks": self._title_blocks(36, "STEEL SECTIONS AND DETAILS"),
        }
        cs.annotate_takeoff_scope(doc)
        self.assertTrue(doc["engineering_tokens"][0]["takeoff_eligible"])

    def test_clip_fabrication_length_is_not_a_member(self):
        doc = {
            "engineering_tokens": [
                {"page": 9, "text": "L3x3x1/4x0'-3\"", "raw_text": "L3x3x1/4x0'-3\""},
                {"page": 9, "text": "L4X4X3/8", "raw_text": "L4X4X3/8"},
            ],
            "title_blocks": self._title_blocks(9, "SECOND FLOOR FRAMING PLAN"),
        }
        cs.annotate_takeoff_scope(doc)
        by_raw = {t["raw_text"]: t for t in doc["engineering_tokens"]}
        self.assertFalse(by_raw["L3x3x1/4x0'-3\""]["takeoff_eligible"])
        self.assertEqual(
            by_raw["L3x3x1/4x0'-3\""]["object_scope"],
            cs.OBJECT_SCOPE_DETAIL_REFERENCE,
        )
        self.assertTrue(by_raw["L4X4X3/8"]["takeoff_eligible"])

    def test_see_framing_plan_note_does_not_save_a_typical_details_sheet(self):
        doc = {
            "engineering_tokens": [{"page": 16, "text": "C8x11.5", "raw_text": "C8x11.5"}],
            "title_blocks": self._title_blocks(16, "TYPICAL DETAILS")
            + [
                {
                    "page_number": 16,
                    "bbox": [2141.0, 1687.0, 2275.0, 1700.0],
                    "text": "SEE ROOF FRAMING PLAN",
                }
            ],
        }
        cs.annotate_takeoff_scope(doc)
        self.assertFalse(doc["engineering_tokens"][0]["takeoff_eligible"])

    def test_reassert_demotes_typical_details_and_clip_predictions(self):
        document = {
            "engineering_tokens": [],
            "title_blocks": self._title_blocks(28, "TYPICAL STEEL DETAILS"),
        }
        predictions = [
            {
                "object_id": "detail",
                "source_text": {"page_number": 28},
                "raw_text": "L4x4x3/8",
            },
            {
                "object_id": "clip",
                "source_text": {"page_number": 5},
                "raw_text": "L4X4X3/8X0'-8\"",
            },
            {
                "object_id": "member",
                "source_text": {"page_number": 5},
                "raw_text": "W12X19",
            },
        ]
        demoted = cs.reassert_prediction_scope(predictions, document)
        self.assertEqual(demoted, 2)
        by_id = {p["object_id"]: p for p in predictions}
        self.assertFalse(by_id["detail"]["takeoff_eligible"])
        self.assertFalse(by_id["clip"]["takeoff_eligible"])
        self.assertNotIn("takeoff_eligible", by_id["member"])

    def test_title_block_typical_details_without_drawing_title_label(self):
        doc = {
            "engineering_tokens": [
                {"page": 6, "text": "L3X2X3/16", "raw_text": "L3X2X3/16"},
                {"page": 13, "text": "W18X35", "raw_text": "W18X35"},
            ],
            "title_blocks": [
                {
                    "page_number": 6,
                    "bbox": [2700, 1800, 2900, 1840],
                    "text": "TYPICAL DETAILS -\nSTEEL",
                },
                {
                    "page_number": 13,
                    "bbox": [2700, 1800, 2900, 1840],
                    "text": "LEVEL 00/FOUNDATION PLAN",
                },
            ],
        }
        summary = cs.annotate_takeoff_scope(doc)
        self.assertEqual(summary["typical_detail_pages"], [6])
        by_page = {t["page"]: t for t in doc["engineering_tokens"]}
        self.assertFalse(by_page[6]["takeoff_eligible"])
        self.assertTrue(by_page[13]["takeoff_eligible"])

    def test_typical_edge_angle_stamp_stays_takeoff_eligible(self):
        doc = {
            "engineering_tokens": [
                {
                    "page": 18,
                    "text": "L4X4X1/4",
                    "raw_text": "L4X4X1/4",
                    "normalized_text": "L4X4X1/4",
                    "context": {"line_text": "SEE PLAN TYP L4X4X1/4 TYP", "neighbor_text": []},
                },
                {
                    "page": 18,
                    "text": "W12X230",
                    "raw_text": "W12X230",
                    "normalized_text": "W12X230",
                    "context": {"line_text": "W12X230", "neighbor_text": []},
                },
            ],
            "title_blocks": self._title_blocks(18, "TYPICAL DETAILS"),
        }
        cs.annotate_takeoff_scope(doc)
        by_text = {t["text"]: t for t in doc["engineering_tokens"]}
        self.assertTrue(by_text["L4X4X1/4"]["takeoff_eligible"])
        self.assertFalse(by_text["W12X230"]["takeoff_eligible"])

    def test_inch_clip_length_is_not_a_member(self):
        doc = {
            "engineering_tokens": [
                {
                    "page": 9,
                    "text": 'L4x3x1/4x6"',
                    "raw_text": 'L4x3x1/4x6"',
                    "normalized_text": "L4X3X1/4",
                }
            ],
            "title_blocks": self._title_blocks(9, "SECOND FLOOR FRAMING PLAN"),
        }
        cs.annotate_takeoff_scope(doc)
        self.assertFalse(doc["engineering_tokens"][0]["takeoff_eligible"])


if __name__ == "__main__":
    unittest.main()
