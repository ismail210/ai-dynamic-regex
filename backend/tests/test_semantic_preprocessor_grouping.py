"""Semantic annotation grouping tests (Section 41)."""
from __future__ import annotations

import unittest

from services.semantic_preprocessor.grouping import group_primitives
from services.semantic_preprocessor.models import TextPrimitive


def _prim(pid, text, bbox, page=1, font_size=10.0, rotation=0.0):
    return TextPrimitive(
        primitive_id=pid, page=page, text=text, bbox=list(bbox),
        font_size=font_size, rotation_deg=rotation,
    )


class BracketModifierAttachmentTests(unittest.TestCase):
    def test_w8x10_plus_bracket_becomes_one_annotation(self):
        primitives = [
            _prim("p1", "W8X10", [100, 100, 140, 110]),
            _prim("p2", "[24]", [142, 100, 160, 110]),
        ]
        annotations = group_primitives(primitives, page=1)
        self.assertEqual(len(annotations), 1)
        ann = annotations[0]
        self.assertEqual(ann.primary_label, "W8X10")
        self.assertEqual(len(ann.modifiers), 1)
        self.assertEqual(ann.modifiers[0].type, "bracket_tag")
        self.assertEqual(ann.modifiers[0].value, "24")
        self.assertIn("bracket_modifier_attachment", ann.grouping_reasons)

    def test_source_fragments_preserve_each_original_bbox(self):
        primitives = [
            _prim("p1", "W8X10", [100, 100, 140, 110]),
            _prim("p2", "[24]", [142, 100, 160, 110]),
        ]
        ann = group_primitives(primitives, page=1)[0]
        self.assertEqual(len(ann.source_fragments), 2)
        by_id = {f.primitive_id: f for f in ann.source_fragments}
        self.assertEqual(by_id["p1"].bbox, [100, 100, 140, 110])
        self.assertEqual(by_id["p1"].text, "W8X10")
        self.assertEqual(by_id["p2"].bbox, [142, 100, 160, 110])
        self.assertEqual(by_id["p2"].text, "[24]")
        # The union must not have overwritten the individual fragment boxes.
        self.assertNotEqual(by_id["p1"].bbox, ann.semantic_bbox)
        self.assertEqual(set(ann.source_fragment_ids), {"p1", "p2"})


class SameBaselineChainMergeTests(unittest.TestCase):
    def test_split_characters_merge_into_one_label(self):
        primitives = [
            _prim("p1", "W", [100, 100, 108, 110]),
            _prim("p2", "8", [108, 100, 114, 110]),
            _prim("p3", "X", [114, 100, 122, 110]),
            _prim("p4", "10", [122, 100, 134, 110]),
        ]
        annotations = group_primitives(primitives, page=1)
        self.assertEqual(len(annotations), 1)
        ann = annotations[0]
        self.assertEqual(ann.primary_label, "W8X10")
        # Adjacent glyph splits (near-zero gap) stay compact in original_text.
        self.assertEqual(ann.original_text, "W8X10")
        self.assertIn("same_baseline_merge", ann.grouping_reasons)
        self.assertEqual(len(ann.source_fragment_ids), 4)

    def test_intentionally_spaced_words_keep_spaces_in_original(self):
        primitives = [
            _prim("p1", "W", [100, 100, 108, 110]),
            _prim("p2", "8", [112, 100, 118, 110]),   # gap 4pt > 0.2*10
            _prim("p3", "X", [122, 100, 130, 110]),
            _prim("p4", "10", [134, 100, 146, 110]),
        ]
        ann = group_primitives(primitives, page=1)[0]
        self.assertEqual(ann.primary_label, "W8X10")
        self.assertEqual(ann.original_text, "W 8 X 10")
        self.assertIn("same_baseline_merge", ann.grouping_reasons)

    def test_semantic_bbox_is_union_not_a_replacement(self):
        primitives = [
            _prim("p1", "W", [100, 100, 108, 110]),
            _prim("p2", "8", [108, 100, 114, 112]),
        ]
        annotations = group_primitives(primitives, page=1)
        ann = annotations[0]
        self.assertEqual(ann.semantic_bbox, [100, 100, 114, 112])


class CrossLineContinuationTests(unittest.TestCase):
    def test_split_hss_over_two_lines_merges_with_inserted_separator(self):
        primitives = [
            _prim("p1", "HSS8X8", [100, 100, 140, 110]),
            _prim("p2", "3/8", [100, 111, 115, 121]),
        ]
        annotations = group_primitives(primitives, page=1)
        self.assertEqual(len(annotations), 1)
        ann = annotations[0]
        self.assertEqual(ann.primary_label, "HSS8X8X3/8")
        self.assertIn("split_structural_label_merge", ann.grouping_reasons)


class NoFalseMergeTests(unittest.TestCase):
    def test_unrelated_nearby_note_does_not_merge(self):
        primitives = [
            _prim("p1", "W8X10", [100, 100, 140, 110]),
            _prim("p2", "SEE NOTE 4", [500, 100, 560, 110]),  # far away, same line
        ]
        annotations = group_primitives(primitives, page=1)
        self.assertEqual(len(annotations), 2)
        labels = {a.primary_label for a in annotations}
        self.assertEqual(labels, {"W8X10", "SEE NOTE 4"})

    def test_unrelated_text_on_line_below_does_not_merge(self):
        primitives = [
            _prim("p1", "HSS8X8X3/8", [100, 100, 160, 110]),  # already complete
            _prim("p2", "TYP.", [100, 111, 120, 121]),
        ]
        annotations = group_primitives(primitives, page=1)
        # Already-complete HSS must not go through continuation merging.
        labels = [a.primary_label for a in annotations]
        self.assertIn("HSS8X8X3/8", labels)
        self.assertIn("TYP.", labels)


if __name__ == "__main__":
    unittest.main()
