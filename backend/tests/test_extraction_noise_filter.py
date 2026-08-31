"""Tests for extraction noise filtering."""

from __future__ import annotations

import unittest

from services.engineering.extraction_noise_filter import (
    dedupe_engineering_tokens,
    dedupe_semantic_members,
    is_extraction_noise_token,
    is_standalone_reference_label,
    is_weak_anonymous_dimension,
    token_in_title_block,
)
from services.engineering_object_filter import classify_engineering_object, filter_engineering_objects


class ExtractionNoiseFilterTests(unittest.TestCase):
    def test_standalone_grade_is_noise(self):
        self.assertTrue(is_standalone_reference_label("A992"))
        token = {"text": "A992", "normalized_text": "A992", "context": {}}
        self.assertTrue(is_extraction_noise_token(token))

    def test_grade_near_bolts_kept(self):
        token = {
            "text": "A992",
            "normalized_text": "A992",
            "context": {"line_text": "BOLTS ASTM A992"},
        }
        self.assertFalse(is_extraction_noise_token(token))

    def test_title_block_token_dropped(self):
        token = {
            "text": "S-101",
            "normalized_text": "S-101",
            "page": 1,
            "bbox": [10, 10, 50, 30],
            "context": {},
        }
        document = {
            "title_blocks": [
                {"page_number": 1, "bbox": [0, 0, 100, 100]},
            ]
        }
        self.assertTrue(token_in_title_block(token, document["title_blocks"]))
        self.assertTrue(is_extraction_noise_token(token, document=document))

    def test_anonymous_in_general_notes_dropped(self):
        token = {
            "text": '3/8"',
            "normalized_text": '3/8"',
            "engineering_object_type": "anonymous_dimension",
            "context": {"line_text": "GENERAL NOTES: all steel per AISC"},
        }
        self.assertTrue(is_weak_anonymous_dimension(token))
        self.assertTrue(
            is_extraction_noise_token(token, object_type="anonymous_dimension")
        )

    def test_anonymous_near_connection_kept(self):
        token = {
            "text": '3/8"',
            "normalized_text": '3/8"',
            "engineering_object_type": "anonymous_dimension",
            "context": {
                "line_text": "SHEAR CONNECTION DETAIL",
                "neighbor_text": ["HSS8X8", "CONN"],
            },
        }
        self.assertFalse(is_weak_anonymous_dimension(token))
        self.assertFalse(
            is_extraction_noise_token(token, object_type="anonymous_dimension")
        )

    def test_anonymous_near_angle_word_kept(self):
        """Regression: a damaged/OCR-fragmented angle label (missing its 'L'
        prefix) sitting right next to the word ANGLE was previously
        discarded as a bare anonymous dimension because ANGLE/L vocabulary
        was missing from the structural-context whitelist."""

        token = {
            "text": "2X4X1/4",
            "normalized_text": "2X4X1/4",
            "engineering_object_type": "anonymous_dimension",
            "context": {"line_text": '2"X4"X1/4" ANGLE'},
        }
        self.assertFalse(is_weak_anonymous_dimension(token))
        self.assertFalse(
            is_extraction_noise_token(token, object_type="anonymous_dimension")
        )

    def test_anonymous_near_angle_word_prefix_kept(self):
        token = {
            "text": "4X3X1/4",
            "normalized_text": "4X3X1/4",
            "engineering_object_type": "anonymous_dimension",
            "context": {"line_text": "ANGLE 3X3X1/4"},
        }
        self.assertFalse(is_weak_anonymous_dimension(token))

    def test_anonymous_near_bare_l_kept(self):
        token = {
            "text": "3X3X3/8",
            "normalized_text": "3X3X3/8",
            "engineering_object_type": "anonymous_dimension",
            "context": {"line_text": "L 3X3X3/8 TYP"},
        }
        self.assertFalse(is_weak_anonymous_dimension(token))

    def test_ordinary_anonymous_dimension_without_structural_context_still_dropped(self):
        """Precision check: the angle-vocabulary fix must not over-rescue --
        an anonymous dimension with no nearby structural context at all
        (no ANGLE, no other family word) must still be discarded."""

        token = {
            "text": "4X4",
            "normalized_text": "4X4",
            "engineering_object_type": "anonymous_dimension",
            "context": {},
        }
        self.assertTrue(is_weak_anonymous_dimension(token))

    def test_dedupe_removes_duplicate_hss(self):
        tokens = [
            {
                "page": 1,
                "text": "HSS8X8",
                "normalized_text": "HSS8X8",
                "bbox": [10, 10, 50, 20],
            },
            {
                "page": 1,
                "text": "HSS8X8",
                "normalized_text": "HSS8X8",
                "bbox": [10, 10, 50, 20],
            },
        ]
        self.assertEqual(len(dedupe_engineering_tokens(tokens)), 1)

    def test_steel_sections_still_classified(self):
        token = {
            "text": "W16X26",
            "normalized_text": "W16X26",
            "context": {"line_text": "BEAM SCHEDULE"},
        }
        self.assertEqual(classify_engineering_object(token), "steel_section")

    def test_anonymous_orphan_without_context_dropped(self):
        token = {
            "text": '3/8"',
            "normalized_text": '3/8"',
            "engineering_object_type": "anonymous_dimension",
            "context": {"line_text": "TYP", "neighbor_text": []},
        }
        self.assertTrue(is_weak_anonymous_dimension(token))
        self.assertTrue(
            is_extraction_noise_token(token, object_type="anonymous_dimension")
        )

    def test_anonymous_fraction_in_detail_kept(self):
        token = {
            "text": '3/8"',
            "normalized_text": '3/8"',
            "engineering_object_type": "anonymous_dimension",
            "layout_dimension_id": "dim_p3_1",
            "context": {"line_text": "DETAIL 3"},
        }
        self.assertFalse(is_weak_anonymous_dimension(token))

    def test_semantic_dedup_collapses_repeated_hss(self):
        tokens = [
            {
                "page": 2,
                "text": "HSS8X8",
                "normalized_text": "HSS8X8",
                "engineering_object_type": "column_or_brace",
                "confidence": 0.9,
                "bbox": [10, 10, 50, 20],
            },
            {
                "page": 2,
                "text": "HSS8X8",
                "normalized_text": "HSS8X8",
                "engineering_object_type": "column_or_brace",
                "confidence": 0.7,
                "bbox": [100, 100, 140, 110],
            },
        ]
        result = dedupe_semantic_members(tokens)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["repeat_count"], 2)
        self.assertEqual(len(result[0]["duplicate_bboxes"]), 1)

    def test_filter_pipeline_drops_noise(self):
        tokens = [
            {
                "text": "A992",
                "normalized_text": "A992",
                "context": {},
            },
            {
                "text": "HSS8X8",
                "normalized_text": "HSS8X8",
                "context": {"neighbor_text": ["POST"]},
            },
        ]
        result = filter_engineering_objects(tokens)
        labels = [t["normalized_text"] for t in result]
        self.assertNotIn("A992", labels)
        self.assertIn("HSS8X8", labels)


if __name__ == "__main__":
    unittest.main()
