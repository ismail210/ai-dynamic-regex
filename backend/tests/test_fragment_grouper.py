"""Accuracy Track A3 — rotation / bracket-aware fragment grouping."""

from __future__ import annotations

import unittest

from services.annotation.fragment_grouper import group_annotation_fragments


def _frag(text, *, page=1, bbox=None, rotation=0.0, font_size=10.0):
    return {
        "text": text,
        "page": page,
        "bbox": bbox or [0, 0, 10, 10],
        "rotation": rotation,
        "font_size": font_size,
    }


class FragmentGrouperTests(unittest.TestCase):
    def test_merges_family_dim_separator_tokens(self):
        fragments = [
            _frag("W", bbox=[0, 0, 8, 10]),
            _frag("12", bbox=[10, 0, 22, 10]),
            _frag("x", bbox=[24, 0, 30, 10]),
            _frag("26", bbox=[32, 0, 46, 10]),
        ]
        groups = group_annotation_fragments(fragments)
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0]["was_merged"])
        self.assertEqual(groups[0]["text"].upper().replace(" ", ""), "W12X26")

    def test_strips_outer_brackets_before_join(self):
        fragments = [
            _frag("(W)", bbox=[0, 0, 10, 10]),
            _frag("8", bbox=[12, 0, 20, 10]),
            _frag("x", bbox=[22, 0, 28, 10]),
            _frag("10", bbox=[30, 0, 42, 10]),
        ]
        groups = group_annotation_fragments(fragments)
        self.assertEqual(len(groups), 1)
        self.assertIn("W", groups[0]["text"].upper())
        self.assertNotIn("(", groups[0]["text"])

    def test_rotated_callouts_tolerate_larger_gap(self):
        fragments = [
            _frag("L", bbox=[0, 0, 8, 10], rotation=90.0),
            _frag("4", bbox=[0, 40, 8, 50], rotation=90.0),
            _frag("x", bbox=[0, 55, 8, 65], rotation=90.0),
            _frag("4", bbox=[0, 70, 8, 80], rotation=90.0),
        ]
        groups = group_annotation_fragments(fragments, max_gap=28.0)
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0]["was_merged"])

    def test_does_not_invent_thickness_on_incomplete_l(self):
        fragments = [
            _frag("L", bbox=[0, 0, 8, 10]),
            _frag("4", bbox=[10, 0, 18, 10]),
            _frag("x", bbox=[20, 0, 26, 10]),
            _frag("4", bbox=[28, 0, 36, 10]),
        ]
        groups = group_annotation_fragments(fragments)
        self.assertEqual(len(groups), 1)
        compact = groups[0]["text"].upper().replace(" ", "")
        self.assertEqual(compact, "L4X4")
        self.assertEqual(compact.count("X"), 1)


if __name__ == "__main__":
    unittest.main()
