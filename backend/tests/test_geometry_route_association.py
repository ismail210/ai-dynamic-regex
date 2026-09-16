"""Tests for the GHX-inspired geometry-association SHADOW layer (Phase C).

Covers the subset of Section 30's test list that is this module's own
responsibility: orientation-aware straight/curved routing, one-to-one
conflict resolution, primary/recovery two-pass behavior, first-class
unmatched reasons, and the invariant that this module never touches
semantic label text. Frontend overlay/persistence tests (items 11/12/14)
and the existing associate_via_nearest_geometry regression coverage (items
1/2, already covered by test_semantic_preprocessor_association.py and
test_grouping-level tests) are out of scope here.
"""
from __future__ import annotations

import unittest

from services.semantic.models import GeometryEvidence, GeometryProvider, SemanticAnnotation
from services.semantic_preprocessor.geometry_route_association import (
    AssociationConfig,
    AssociationOrigin,
    AssociationRoute,
    OrientationEvidence,
    UnmatchedReason,
    classify_orientation,
    compare_with_existing,
    evaluate_orientation_evidence,
    is_do_annotation,
    is_geometry_orientation_reliable,
    is_text_orientation_reliable,
    orientation_compatible,
    run_shadow_association,
)


def _ann(ann_id, text="W12X26", anchor=(50.0, 0.0), axis=(1.0, 0.0), page=1):
    return SemanticAnnotation(
        annotation_id=ann_id,
        original_text=text,
        primary_label=text,
        page=page,
        original_anchor=list(anchor),
        original_axis=list(axis),
    )


def _beam(gid, p0, p1, geometry_type="beam_curve"):
    orientation = None
    import math
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    if dx or dy:
        orientation = [math.degrees(math.atan2(dy, dx)) % 180.0]
    return GeometryEvidence(
        geometry_id=gid,
        provider=GeometryProvider.PDF_VECTOR,
        geometry_type=geometry_type,
        points=[list(p0), list(p1)],
        bbox=[min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1])],
        centroid=[(p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0],
        start=list(p0), end=list(p1),
        length=math.hypot(dx, dy),
        orientation=orientation,
    )


class OrientationClassificationTests(unittest.TestCase):
    def test_horizontal_and_vertical_buckets(self):
        cfg = AssociationConfig(orientation_tolerance_deg=10.0)
        self.assertEqual(classify_orientation(0.0, cfg).value, "horizontal")
        self.assertEqual(classify_orientation(179.0, cfg).value, "horizontal")
        self.assertEqual(classify_orientation(90.0, cfg).value, "vertical")

    def test_diagonal_ascending_and_descending_are_distinct(self):
        cfg = AssociationConfig(orientation_tolerance_deg=10.0)
        ascending = classify_orientation(45.0, cfg)
        descending = classify_orientation(135.0, cfg)
        self.assertEqual(ascending.value, "diagonal_at")
        self.assertEqual(descending.value, "diagonal_sc")
        self.assertNotEqual(ascending, descending)

    def test_unknown_orientation_is_always_compatible(self):
        # Section 4: absence of a signal must never silently reject a
        # candidate.
        self.assertTrue(orientation_compatible(None, classify_orientation(90.0)))
        self.assertTrue(orientation_compatible(classify_orientation(0.0), None))

    def test_positive_and_negative_diagonals_not_blindly_mixed(self):
        cfg = AssociationConfig(orientation_tolerance_deg=10.0)
        self.assertFalse(orientation_compatible(classify_orientation(45.0, cfg), classify_orientation(135.0, cfg)))


class StraightRouteTests(unittest.TestCase):
    def test_horizontal_text_prefers_horizontal_geometry(self):
        geoms = {1: [
            _beam("g_h", (0, 0), (100, 0)),
            _beam("g_v", (50, -50), (50, 50), geometry_type="beam_curve"),
        ]}
        ann = _ann("ann_1", anchor=(50, 2), axis=(1, 0))
        evidence = run_shadow_association([ann], geoms)
        self.assertEqual(evidence[0].geometry_id, "g_h")
        self.assertEqual(evidence[0].route, AssociationRoute.STRAIGHT.value)
        self.assertIn("ORIENTATION_COMPATIBLE", evidence[0].reason_codes)

    def test_vertical_text_does_not_associate_to_only_horizontal_geometry(self):
        geoms = {1: [_beam("g_h", (0, 0), (100, 0))]}
        ann = _ann("ann_1", anchor=(50, 2), axis=(0, 1))  # vertical text axis
        evidence = run_shadow_association([ann], geoms)
        self.assertEqual(evidence[0].status, "unmatched")
        self.assertEqual(evidence[0].reason_codes, [UnmatchedReason.ORIENTATION_MISMATCH.value])


class CurvedRouteTests(unittest.TestCase):
    def test_curved_geometry_does_not_require_orientation_match(self):
        # A vertical-axis label near a "curved_beam"-typed geometry (whose
        # own orientation vector is diagonal) must still associate --
        # Section 11: no global orientation gate for curved members.
        curved = _beam("g_curve", (0, 0), (60, 40), geometry_type="curved_beam")
        geoms = {1: [curved]}
        ann = _ann("ann_1", anchor=(30, 21), axis=(0, 1))
        evidence = run_shadow_association([ann], geoms)
        self.assertEqual(evidence[0].geometry_id, "g_curve")
        self.assertEqual(evidence[0].route, AssociationRoute.CURVED.value)
        self.assertNotIn("ORIENTATION_MISMATCH", evidence[0].reason_codes)


class ConflictResolutionTests(unittest.TestCase):
    def test_two_labels_competing_for_one_geometry_resolve_deterministically(self):
        geoms = {1: [_beam("g_1", (0, 0), (100, 0))]}
        near = _ann("ann_near", anchor=(50, 1))
        far = _ann("ann_far", anchor=(50, 15))
        evidence = run_shadow_association([near, far], geoms)
        by_id = {e.source_text_id: e for e in evidence}
        self.assertEqual(by_id["ann_near"].geometry_id, "g_1")
        self.assertEqual(by_id["ann_near"].status, "associated")
        self.assertIsNone(by_id["ann_far"].geometry_id)
        self.assertEqual(by_id["ann_far"].status, "unmatched")

    def test_one_label_does_not_silently_claim_multiple_members(self):
        # Second beam far enough away to avoid the ambiguity-tie gate --
        # this test is about the single-geometry_id structural invariant,
        # not tie handling (see UnmatchedStateTests for ties).
        geoms = {1: [_beam("g_1", (0, 0), (100, 0)), _beam("g_2", (0, 50), (100, 50))]}
        ann = _ann("ann_1", anchor=(50, 2))
        evidence = run_shadow_association([ann], geoms)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].geometry_id, "g_1")


class RecoveryTests(unittest.TestCase):
    def test_primary_failure_enters_recovery_and_is_tagged(self):
        cfg = AssociationConfig(
            straight_primary_max_distance_pt=5.0,
            straight_recovery_max_distance_pt=50.0,
        )
        geoms = {1: [_beam("g_1", (0, 0), (100, 0))]}
        ann = _ann("ann_1", anchor=(50, 20))  # outside primary gate, inside recovery gate
        evidence = run_shadow_association([ann], geoms, config=cfg)
        self.assertEqual(evidence[0].status, "associated")
        self.assertEqual(evidence[0].association_origin, AssociationOrigin.RECOVERY.value)
        self.assertIn("RECOVERED_WIDER_GATE", evidence[0].reason_codes)

    def test_recovery_never_steals_a_primary_claim(self):
        cfg = AssociationConfig(
            straight_primary_max_distance_pt=5.0,
            straight_recovery_max_distance_pt=50.0,
        )
        geoms = {1: [_beam("g_1", (0, 0), (100, 0))]}
        primary_winner = _ann("ann_primary", anchor=(50, 1))  # within primary gate
        recovery_hopeful = _ann("ann_recovery", anchor=(50, 20))  # only within recovery gate
        evidence = run_shadow_association([primary_winner, recovery_hopeful], geoms, config=cfg)
        by_id = {e.source_text_id: e for e in evidence}
        self.assertEqual(by_id["ann_primary"].association_origin, AssociationOrigin.PRIMARY.value)
        self.assertEqual(by_id["ann_primary"].geometry_id, "g_1")
        # The only geometry on the page is already claimed by the primary
        # pass, so recovery must NOT also hand it to the second label.
        self.assertEqual(by_id["ann_recovery"].status, "unmatched")
        self.assertEqual(by_id["ann_recovery"].reason_codes, [UnmatchedReason.GEOMETRY_ALREADY_CLAIMED.value])


class UnmatchedStateTests(unittest.TestCase):
    def test_no_local_geometry_at_all(self):
        ann = _ann("ann_1", anchor=(5000, 5000))
        geoms = {1: [_beam("g_1", (0, 0), (100, 0))]}
        evidence = run_shadow_association([ann], geoms, config=AssociationConfig(
            straight_primary_max_distance_pt=10.0, straight_recovery_max_distance_pt=10.0,
        ))
        self.assertEqual(evidence[0].reason_codes, [UnmatchedReason.NO_LOCAL_GEOMETRY.value])

    def test_too_close_to_call_is_reported_as_multiple_valid_candidates(self):
        # Two beams within the ambiguity margin of each other from the
        # label's anchor -- must surface as an explicit tie, never a guess.
        geoms = {1: [_beam("g_1", (0, 0), (100, 0)), _beam("g_2", (0, 5), (100, 5))]}
        ann = _ann("ann_1", anchor=(50, 2))
        evidence = run_shadow_association([ann], geoms)
        self.assertIsNone(evidence[0].geometry_id)
        self.assertEqual(evidence[0].reason_codes, [UnmatchedReason.MULTIPLE_VALID_CANDIDATES.value])

    def test_unsupported_geometry_type_reported_explicitly(self):
        weird = GeometryEvidence(
            geometry_id="g_weird", provider=GeometryProvider.PDF_VECTOR,
            geometry_type="detail_callout", centroid=[50, 0], bbox=[45, -2, 55, 2],
        )
        ann = _ann("ann_1", anchor=(50, 1))
        evidence = run_shadow_association([ann], {1: [weird]})
        self.assertEqual(evidence[0].reason_codes, [UnmatchedReason.UNSUPPORTED_GEOMETRY.value])

    def test_annotation_without_original_anchor_is_skipped_not_guessed(self):
        ann = SemanticAnnotation(annotation_id="ann_1", original_text="W8X10", page=1, original_anchor=None)
        evidence = run_shadow_association([ann], {1: [_beam("g_1", (0, 0), (100, 0))]})
        self.assertEqual(evidence, [])


class DoRouteTests(unittest.TestCase):
    def test_do_annotation_detected_and_routed(self):
        self.assertTrue(is_do_annotation(_ann("a", text="DO")))
        self.assertFalse(is_do_annotation(_ann("a", text="DO18")))  # a real label, not the DO convention

        geoms = {1: [_beam("g_1", (0, 0), (100, 0))]}
        ann = _ann("ann_1", text="DO", anchor=(50, 2))
        evidence = run_shadow_association([ann], geoms)
        self.assertEqual(evidence[0].route, AssociationRoute.SPECIAL_DO.value)
        self.assertIn("DO_ANNOTATION_PATTERN", evidence[0].reason_codes)


class LabelIntegrityTests(unittest.TestCase):
    def test_shadow_association_never_touches_annotation_text(self):
        # This module must never rewrite a label -- it only ever reads
        # original_text/original_anchor/original_axis and returns evidence.
        ann = _ann("ann_1", text="W18X35", anchor=(50, 2))
        before = (ann.original_text, ann.primary_label, ann.effective_text)
        geoms = {1: [_beam("g_1", (0, 0), (100, 0))]}
        run_shadow_association([ann], geoms)
        after = (ann.original_text, ann.primary_label, ann.effective_text)
        self.assertEqual(before, after)


class ShadowComparisonTests(unittest.TestCase):
    def test_compare_with_existing_reports_agreement_and_disagreement(self):
        geoms = {1: [_beam("g_1", (0, 0), (100, 0))]}
        ann = _ann("ann_1", anchor=(50, 2))
        evidence = run_shadow_association([ann], geoms)
        agree_report = compare_with_existing(evidence, {"ann_1": "g_1"})
        self.assertEqual(agree_report["agree"], 1)
        self.assertEqual(agree_report["disagree"], 0)

        disagree_report = compare_with_existing(evidence, {"ann_1": "g_other"})
        self.assertEqual(disagree_report["disagree"], 1)
        self.assertEqual(disagree_report["agree"], 0)


class AxialAngleEquivalenceTests(unittest.TestCase):
    """Phase D1 Section 3/18: exact requested pairs, modulo-180 not 360."""

    def setUp(self):
        self.cfg = AssociationConfig(orientation_tolerance_deg=10.0)

    def _cls(self, angle):
        return classify_orientation(angle, self.cfg)

    def test_0_vs_180(self):
        self.assertEqual(self._cls(0), self._cls(180))

    def test_1_vs_179(self):
        self.assertEqual(self._cls(1), self._cls(179))

    def test_90_vs_270(self):
        self.assertEqual(self._cls(90), self._cls(270))

    def test_45_vs_225(self):
        self.assertEqual(self._cls(45), self._cls(225))

    def test_45_vs_135_are_distinct_diagonals(self):
        # NOT axially equivalent -- ascending vs descending diagonal.
        self.assertNotEqual(self._cls(45), self._cls(135))

    def test_negative_1_vs_179(self):
        self.assertEqual(self._cls(-1), self._cls(179))

    def test_normalization_is_modulo_180_not_360(self):
        # A 360-modulo bug would put 190 far from 10; axially they are the
        # same line direction (190 = 10 + 180).
        self.assertEqual(self._cls(10), self._cls(190))


class OrientationReliabilityTests(unittest.TestCase):
    """Phase D1 Section 4/16 finding: exact-zero text rotation is a known
    extraction-bug default (services.pdf_parser._span_rotation reads the
    wrong dict key), so it must not be trusted as true horizontal."""

    def test_missing_text_rotation_is_unreliable(self):
        self.assertFalse(is_text_orientation_reliable(None))

    def test_exact_zero_text_rotation_is_unreliable(self):
        self.assertFalse(is_text_orientation_reliable(0.0))
        self.assertFalse(is_text_orientation_reliable(180.0))

    def test_nonzero_text_rotation_is_reliable(self):
        self.assertTrue(is_text_orientation_reliable(37.0))
        self.assertTrue(is_text_orientation_reliable(90.0))

    def test_geometry_orientation_reliable_whenever_present(self):
        self.assertTrue(is_geometry_orientation_reliable(0.0))
        self.assertTrue(is_geometry_orientation_reliable(42.0))
        self.assertFalse(is_geometry_orientation_reliable(None))


class ThreeStateOrientationPolicyTests(unittest.TestCase):
    def test_reliable_and_compatible_is_match(self):
        h = classify_orientation(0.0)
        self.assertEqual(
            evaluate_orientation_evidence(h, True, h, True), OrientationEvidence.MATCH
        )

    def test_reliable_and_incompatible_is_conflict(self):
        h = classify_orientation(0.0)
        v = classify_orientation(90.0)
        self.assertEqual(
            evaluate_orientation_evidence(h, True, v, True), OrientationEvidence.CONFLICT
        )

    def test_missing_text_rotation_is_unknown_not_conflict(self):
        v = classify_orientation(90.0)
        self.assertEqual(
            evaluate_orientation_evidence(None, False, v, True), OrientationEvidence.UNKNOWN
        )

    def test_missing_geometry_rotation_is_unknown_not_conflict(self):
        h = classify_orientation(0.0)
        self.assertEqual(
            evaluate_orientation_evidence(h, True, None, False), OrientationEvidence.UNKNOWN
        )

    def test_unreliable_zero_text_rotation_is_unknown_even_if_classes_match(self):
        # This is the Burrville-specific finding: a suspicious exact-zero
        # reading must not silently count as a confident MATCH.
        h = classify_orientation(0.0)
        self.assertEqual(
            evaluate_orientation_evidence(h, False, h, True), OrientationEvidence.UNKNOWN
        )

    def test_three_state_policy_keeps_unknown_candidate_eligible_in_ranking(self):
        # End-to-end: with use_three_state_orientation on, a candidate whose
        # text orientation reads as an unreliable exact-zero must still be
        # associated (tagged UNKNOWN), not rejected as if it conflicted.
        cfg = AssociationConfig(use_three_state_orientation=True)
        geoms = {1: [_beam("g_diag", (0, 0), (100, 40))]}  # non-horizontal geometry
        ann = _ann("ann_1", anchor=(50, 22), axis=(1, 0))  # exact-zero text rotation
        evidence = run_shadow_association([ann], geoms, config=cfg)
        self.assertEqual(evidence[0].status, "associated")
        self.assertIn("ORIENTATION_UNKNOWN", evidence[0].reason_codes)

    def test_hard_gate_still_default_and_unchanged(self):
        # use_three_state_orientation defaults False -- Phase C behavior is
        # byte-for-byte unchanged unless a caller opts in.
        geoms = {1: [_beam("g_diag", (0, 0), (100, 40))]}
        ann = _ann("ann_1", anchor=(50, 22), axis=(1, 0))
        evidence = run_shadow_association([ann], geoms)  # default config
        self.assertEqual(evidence[0].status, "unmatched")
        self.assertEqual(evidence[0].reason_codes, [UnmatchedReason.ORIENTATION_MISMATCH.value])


if __name__ == "__main__":
    unittest.main()
