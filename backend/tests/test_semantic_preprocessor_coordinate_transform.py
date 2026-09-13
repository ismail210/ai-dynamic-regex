"""Coordinate calibration tests (Section 44)."""
from __future__ import annotations

import math
import unittest

from services.semantic_preprocessor.coordinate_transform import (
    PointCorrespondence,
    apply_transform,
    fit_similarity_transform,
    invert_transform,
)


def _synthetic_correspondences(scale=2.0, rotation_deg=15.0, tx=50.0, ty=-30.0, flip_y=True, n=20):
    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    correspondences = []
    for i in range(n):
        sx, sy = float(i * 3), float((i % 5) * 7)
        eff_sy = -sy if flip_y else sy
        tx_pt = scale * (sx * cos_t - eff_sy * sin_t) + tx
        ty_pt = scale * (sx * sin_t + eff_sy * cos_t) + ty
        correspondences.append(PointCorrespondence(source=(sx, sy), target=(tx_pt, ty_pt)))
    return correspondences


class SimilarityFitTests(unittest.TestCase):
    def test_recovers_known_transform_with_near_zero_residual(self):
        correspondences = _synthetic_correspondences()
        transform = fit_similarity_transform(
            correspondences, transform_id="t1", source_frame="pdf_page_1",
            target_frame="rhino_plan", flip_y=True,
        )
        self.assertTrue(transform.valid)
        self.assertAlmostEqual(transform.scale_x, 2.0, places=3)
        self.assertLess(transform.residual_max, 1e-6)

    def test_round_trip_apply_then_invert(self):
        correspondences = _synthetic_correspondences()
        transform = fit_similarity_transform(
            correspondences, transform_id="t1", source_frame="pdf_page_1",
            target_frame="rhino_plan", flip_y=True,
        )
        original = (12.5, -4.0)
        forward = apply_transform(transform, original)
        back = invert_transform(transform, forward)
        self.assertAlmostEqual(back[0], original[0], places=4)
        self.assertAlmostEqual(back[1], original[1], places=4)

    def test_too_few_points_is_invalid(self):
        transform = fit_similarity_transform(
            [PointCorrespondence((0, 0), (0, 0)), PointCorrespondence((1, 1), (1, 1))],
            transform_id="t2", source_frame="a", target_frame="b",
        )
        self.assertFalse(transform.valid)
        self.assertEqual(transform.invalid_reason, "fewer_than_3_correspondences")

    def test_noisy_correspondences_fail_validity_gate_not_a_bigger_threshold(self):
        # Small n so the corrupted point's residual is guaranteed to land in
        # the P95 tail (n=4 -> P95 index is the max) rather than depending
        # on how a large clean sample happens to sort.
        correspondences = _synthetic_correspondences(n=4)
        noisy = correspondences[:-1] + [
            PointCorrespondence(source=correspondences[-1].source, target=(9999.0, 9999.0))
        ]
        transform = fit_similarity_transform(
            noisy, transform_id="t3", source_frame="pdf_page_1", target_frame="rhino_plan", flip_y=True,
        )
        self.assertFalse(transform.valid)
        self.assertEqual(transform.invalid_reason, "residual_p95_exceeds_threshold")

    def test_apply_refuses_on_invalid_transform(self):
        transform = fit_similarity_transform(
            [PointCorrespondence((0, 0), (0, 0)), PointCorrespondence((1, 1), (1, 1))],
            transform_id="t2", source_frame="a", target_frame="b",
        )
        with self.assertRaises(ValueError):
            apply_transform(transform, (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
