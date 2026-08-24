"""Tests for feet-inch and layout dimension filtering."""

from __future__ import annotations

import unittest

from services.engineering.feet_inch_filter import (
    is_feet_inch_layout_dimension,
    is_non_steel_layout_dimension,
    is_non_steel_layout_token,
)
from services.engineering_object_filter import classify_engineering_object
from services.token_extractor import extract_engineering_tokens


class FeetInchFilterTests(unittest.TestCase):
    def test_compound_footing_not_extracted(self):
        text = "(E) 7'-6\"x7'-6\"x1'-6\" near HSS8x8 POST"
        self.assertTrue(is_feet_inch_layout_dimension(text))
        tokens = extract_engineering_tokens(text)
        self.assertIn("HSS8X8", tokens)
        self.assertNotIn('6"', tokens)
        self.assertNotIn("6", tokens)

    def test_layout_inch_numbers_not_extracted(self):
        for sample in ('4"', '6"', '8"', '12"', '15"', '22"'):
            with self.subTest(sample=sample):
                self.assertTrue(is_non_steel_layout_dimension(sample))
                self.assertNotIn(sample, extract_engineering_tokens(sample))

    def test_bare_footing_line_classified_none(self):
        token = {
            "text": '6"',
            "raw_text": '6"',
            "normalized_text": '6"',
            "page": 7,
            "bbox": [0, 0, 10, 10],
            "context": {
                "line_text": "(E) 7'-6\"x7'-6\"x1'-6\"",
                "neighbor_text": ["HSS8X8", "POST"],
            },
        }
        self.assertTrue(is_non_steel_layout_token(token))
        self.assertIsNone(classify_engineering_object(token))

    def test_steel_fractions_still_extracted(self):
        for sample in ('3/8"', '5/16"', '1/2"', '1/4"'):
            with self.subTest(sample=sample):
                self.assertFalse(is_non_steel_layout_dimension(sample))
                self.assertIn(sample, extract_engineering_tokens(f'Gusset {sample}'))

    def test_tick_fractions_filtered(self):
        self.assertTrue(is_non_steel_layout_dimension('3/64"'))
        self.assertNotIn('3/64"', extract_engineering_tokens('3/64"'))

    def test_steel_compound_still_extracted(self):
        tokens = extract_engineering_tokens("Gusset 6x4x5/16")
        self.assertTrue(any("6X4X5/16" in token for token in tokens))

    def test_bent_plate_still_extracted(self):
        tokens = extract_engineering_tokens('3/8" BENT PL')
        self.assertTrue(any("BENTPL" in token for token in tokens))

    def test_hss_and_w_shapes_unaffected(self):
        for sample in ("HSS8X8X1/2", "W16X26", "L4X4X3/8", "PL 3/8"):
            tokens = extract_engineering_tokens(sample)
            self.assertTrue(tokens, msg=sample)


if __name__ == "__main__":
    unittest.main()
