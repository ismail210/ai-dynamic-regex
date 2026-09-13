"""Deterministic engineering token extraction, especially L-family callouts."""

from __future__ import annotations

import unittest

from services.engineering_object_filter import classify_engineering_object
from services.token_extractor import (
    core_section_token,
    extract_engineering_token_records,
    extract_engineering_tokens,
)


class AngleTokenExtractionTests(unittest.TestCase):
    def test_full_angle_is_not_truncated_before_fraction(self):
        self.assertEqual(extract_engineering_tokens("L4X4X1/4"), ["L4X4X1/4"])
        self.assertEqual(extract_engineering_tokens("L4x3x1/4x6\""), ["L4X3X1/4X6\""])
        self.assertEqual(
            extract_engineering_tokens("L4X4X3/8X0'-8\""),
            ["L4X4X3/8X0'-8\""],
        )

    def test_mixed_number_legs_are_preserved(self):
        self.assertEqual(extract_engineering_tokens("L4X3-1/2X3/8"), ["L4X3-1/2X3/8"])
        self.assertEqual(extract_engineering_tokens("L4X31/2X3/8"), ["L4X31/2X3/8"])
        self.assertEqual(extract_engineering_tokens("L4X3 1/2X3/8"), ["L4X31/2X3/8"])

    def test_core_section_strips_shop_length(self):
        self.assertEqual(core_section_token("L4X4X3/8X0'-8\""), "L4X4X3/8")
        self.assertEqual(core_section_token('L4x3x1/4x6"'), "L4X3X1/4")
        self.assertEqual(core_section_token("L4X4X1/4"), "L4X4X1/4")

    def test_records_normalize_to_catalog_core(self):
        words = [
            {
                "text": "L4x3x1/4x6\"",
                "bbox": [10, 10, 80, 20],
                "page_number": 1,
                "block_no": 1,
                "line_no": 1,
                "word_no": 0,
                "object_id": "w0",
            }
        ]
        records = extract_engineering_token_records(words)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["normalized_text"], "L4X3X1/4")
        self.assertIn("6", records[0]["raw_text"])

    def test_parenthesized_new_steel_window(self):
        words = [
            {
                "text": "(N)",
                "bbox": [10, 10, 30, 20],
                "page_number": 1,
                "block_no": 1,
                "line_no": 1,
                "word_no": 0,
                "object_id": "w0",
            },
            {
                "text": "HSS8x8x3/8",
                "bbox": [32, 10, 90, 20],
                "page_number": 1,
                "block_no": 1,
                "line_no": 1,
                "word_no": 1,
                "object_id": "w1",
            },
        ]
        records = extract_engineering_token_records(words)
        labels = {record["normalized_text"] for record in records}
        self.assertIn("HSS8X8X3/8", labels)

    def test_catalog_section_survives_general_notes_keyword(self):
        token = {
            "text": "HSS8X8X3/8",
            "normalized_text": "HSS8X8X3/8",
            "context": {
                "line_text": "(N) HSS8x8x3/8 POST UP",
                "block_text": "ROOF DIAPHRAGM PRICING NOTES: GENERAL NOTES BELOW",
            },
        }
        self.assertEqual(classify_engineering_object(token), "column_or_brace")


if __name__ == "__main__":
    unittest.main()
