"""Phase D2 Part B (Section 15): deterministic proof that
``merge_collinear_fragments`` performs TRANSITIVE (union-find) merging, so a
chain A-B-C-D can become one merged member even when the endpoints (A and D)
are far apart and would never themselves be considered collinear/abutting.

This is diagnostic only -- it demonstrates existing, unmodified behavior. No
production code is changed by this test file; see
docs/validation/phase_d2_merge_forensics.md for the full audit and
recommended (not-yet-implemented) fix directions.
"""
from __future__ import annotations

import unittest

from services.engineering.geometry_normalizer import merge_collinear_fragments
from tests.helpers.geometry_fixtures import line_fragment as _line


class TransitiveMergeGrowthTests(unittest.TestCase):
    def test_a_and_d_are_never_directly_mergeable_alone(self):
        # A ends at x=40, D starts at x=144 -- a 104pt gap, far beyond the
        # 8pt default tolerance. Confirms the "shouldn't reasonably merge"
        # premise before showing the chain merges them anyway.
        a = _line(1, 0, 0, 40, 0, "A")
        d = _line(1, 144, 0, 184, 0, "D")
        merged, stats = merge_collinear_fragments([a, d], gap=8.0)
        self.assertEqual(stats["clusters_merged"], 0)
        self.assertEqual(len(merged), 2)

    def test_transitive_chain_merges_far_apart_endpoints(self):
        # A-B, B-C, C-D each within the 8pt gap tolerance individually.
        # Union-find's transitive closure puts ALL FOUR in one cluster,
        # even though A and D alone (previous test) never would merge.
        a = _line(1, 0, 0, 40, 0, "A")
        b = _line(1, 48, 0, 88, 0, "B")
        c = _line(1, 96, 0, 136, 0, "C")
        d = _line(1, 144, 0, 184, 0, "D")
        merged, stats = merge_collinear_fragments([a, b, c, d], gap=8.0)

        self.assertEqual(stats["clusters_merged"], 1)
        self.assertEqual(len(merged), 1)
        result = merged[0]
        self.assertEqual(result["merged_from"], ["A", "B", "C", "D"])
        # The merged member now spans the full 0-184 range -- 184pt total,
        # roughly 4.6x any single fragment's own 40pt length -- purely from
        # chained short hops, with no cap on total accumulated span.
        self.assertGreaterEqual(result["length"], 180.0)
        self.assertEqual(result["bbox"][0], 0.0)
        self.assertEqual(result["bbox"][2], 184.0)

    def test_growth_ratio_is_unbounded_by_fragment_count(self):
        # Extend the chain to 10 fragments -- there is no cap in
        # merge_collinear_fragments on cluster size or total merged length;
        # the same 8pt-per-hop tolerance produces an arbitrarily long
        # single "member" as more collinear fragments are added.
        fragments = []
        x = 0.0
        for i in range(10):
            fragments.append(_line(1, x, 0, x + 40, 0, f"F{i}"))
            x += 48.0  # 40pt fragment + 8pt gap, repeated
        merged, stats = merge_collinear_fragments(fragments, gap=8.0)
        self.assertEqual(stats["clusters_merged"], 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["merged_from"]), 10)
        # 10 fragments x 40pt + 9 gaps x 8pt = 472pt from 40pt-long pieces --
        # an 11.8x growth ratio relative to any single source fragment.
        self.assertGreaterEqual(merged[0]["length"], 460.0)


if __name__ == "__main__":
    unittest.main()
