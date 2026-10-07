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

    def test_core_section_strips_spacing_suffix_and_separators(self):
        cases = {
            "L3x3x1/4@8'": "L3X3X1/4",
            "L3x3x1/4 @ 8'": "L3X3X1/4",
            "L3x3x1/4@8',": "L3X3X1/4",
            "L6x6x1/2@2'-0\"": "L6X6X1/2",
            "L3x3x1/4@4'-0\" O.C.": "L3X3X1/4",
            "2L4x4x1/4@16\"": "2L4X4X1/4",
            "L3X3X5/16,": "L3X3X5/16",
            "L6x6x5/16;": "L6X6X5/16",
            # Incomplete stays incomplete -- no thickness appears.
            "L4x4@8'": "L4X4",
            "2L4x4@16\"": "2L4X4",
            "L4x4,": "L4X4",
            # An inch mark is not a list separator; it is left alone.
            'L5x5x5/16"': 'L5X5X5/16"',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(core_section_token(raw), expected)

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

    def test_inch_angle_does_not_leave_a_fragment_member(self):
        """Struct S-sheet legend: one angle, not angle + ``1/2"`` plate."""

        texts = ['6"x3', '1/2"x3/8"', "CONTINUOUS", "ANGLE", "(LLV)", "WELDED"]
        words = [
            {
                "text": text,
                "bbox": [10 + 40 * i, 10, 46 + 40 * i, 20],
                "page_number": 11,
                "block_no": 1,
                "line_no": 1,
                "word_no": i,
                "object_id": f"w{i}",
            }
            for i, text in enumerate(texts)
        ]
        labels = [r["normalized_text"] for r in extract_engineering_token_records(words)]
        self.assertEqual(labels, ["L6X3-1/2X3/8"])

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
