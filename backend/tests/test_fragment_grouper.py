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


class ExactSectionBesideScheduleMarkTests(unittest.TestCase):
    """A catalog-exact label stays locked next to a BP/CL/C/L schedule mark."""

    def _texts(self, fragments):
        return [group["text"] for group in group_annotation_fragments(fragments)]

    def test_doc187_page3_w14x90_above_bp3(self):
        # Real geometry: H5 Herndon (DOC-187) p3, W14x90 stacked over BP3.
        texts = self._texts(
            [
                _frag("W14x90", page=3, bbox=[2363.3, 180.1, 2398.6, 189.7]),
                _frag("BP3", page=3, bbox=[2363.3, 191.0, 2380.0, 200.6]),
            ]
        )
        self.assertEqual(texts, ["W14x90", "BP3"])

    def test_struct_style_sections_beside_each_mark_family(self):
        for section, mark in (
            ("L5X5X3/8", "CL2"),
            ("HSS6X6X1/2", "C1"),
            ("W8X21", "L1"),
            ("C8X11.5", "C1"),
            ("W14X90", "BP3"),
        ):
            for first, second in ((section, mark), (mark, section)):
                with self.subTest(first=first, second=second):
                    # Stacked like DOC-187: within the grouper's merge distance.
                    texts = self._texts(
                        [
                            _frag(first, bbox=[0, 0, 40, 10]),
                            _frag(second, bbox=[0, 12, 40, 22]),
                        ]
                    )
                    self.assertEqual(texts, [first, second])

    def test_punctuation_damaged_mark_does_not_absorb_exact_section(self):
        texts = self._texts(
            [_frag("W12X16", bbox=[0, 0, 36, 10]), _frag("BP4,", bbox=[0, 12, 20, 22])]
        )
        self.assertEqual(texts, ["W12X16", "BP4,"])

    def test_ordinary_section_shards_still_merge(self):
        fragments = [
            _frag("C", bbox=[0, 0, 8, 10]),
            _frag("8", bbox=[10, 0, 18, 10]),
            _frag("x", bbox=[20, 0, 26, 10]),
            _frag("11.5", bbox=[28, 0, 44, 10]),
        ]
        groups = group_annotation_fragments(fragments)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["text"].upper().replace(" ", ""), "C8X11.5")

    def test_incomplete_hss_is_not_completed(self):
        from services.exact_section_predictor import catalog_valid_exact_section

        texts = self._texts(
            [_frag("HSS8X8", bbox=[0, 0, 36, 10]), _frag("BP1", bbox=[0, 12, 16, 22])]
        )
        self.assertNotIn("HSS8X8X", " ".join(texts).upper())
        self.assertIsNone(catalog_valid_exact_section("HSS8X8"))


if __name__ == "__main__":
    unittest.main()
