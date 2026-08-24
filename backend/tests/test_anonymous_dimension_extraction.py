"""Tests for anonymous dimension extraction."""

from __future__ import annotations

import unittest

from services.annotation.parser import interpret_annotation
from services.engineering_object_filter import classify_engineering_object
from services.token_extractor import extract_engineering_tokens


class AnonymousDimensionExtractionTests(unittest.TestCase):
    def test_bare_thickness_extracted(self):
        tokens = extract_engineering_tokens('Plate callout 3/8" near beam')
        self.assertIn('3/8"', tokens)

    def test_anonymous_compound_extracted(self):
        tokens = extract_engineering_tokens("Gusset 6x4x5/16 at connection")
        self.assertTrue(any("6X4X5/16" in token for token in tokens))

    def test_classified_as_anonymous_dimension(self):
        token = {
            "text": '3/8"',
            "raw_text": '3/8"',
            "normalized_text": '3/8"',
            "page": 1,
            "bbox": [0, 0, 10, 10],
            "context": {"neighbor_text": ["CONNECTION"], "line_text": "DETAIL 3"},
        }
        self.assertEqual(classify_engineering_object(token), "anonymous_dimension")

    def test_bare_compound_stays_dimension_not_plate(self):
        parsed = interpret_annotation(
            raw_text="6x4x5/16",
            normalized_text="6X4X5/16",
            page_context="CONNECTION DETAIL",
        )
        self.assertEqual(parsed.annotation_type, "DIMENSION")
        self.assertFalse(parsed.structure_confirmed)


if __name__ == "__main__":
    unittest.main()
