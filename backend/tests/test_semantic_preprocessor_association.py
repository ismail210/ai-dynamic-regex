"""Evidence fusion tests (Section 45)."""
from __future__ import annotations

import unittest

from services.semantic.models import (
    EvidenceRecord,
    EvidenceStrength,
    EvidenceType,
    GeometryAssociation,
    GeometryEvidence,
    GeometryProvider,
    ReviewStatus,
    ScoreValue,
    SemanticAnnotation,
)
from services.semantic_preprocessor.association import (
    REASON_AMBIGUOUS_MULTIPLE_BEAMS,
    REASON_GHX_EXISTING_PAIR,
    REASON_GHX_PDF_DISAGREEMENT,
    REASON_NEAREST_STRUCTURAL_CURVE,
    associate_via_ghx_pairing,
    associate_via_nearest_geometry,
    fuse_candidates,
)


def _annotation(label="W8X10", anchor=(5.0, 5.0)):
    return SemanticAnnotation(
        annotation_id="ann_1", page=1, original_text=label,
        primary_label=label, original_anchor=list(anchor),
    )


def _geom(gid, geometry_type="beam_curve", centroid=(5.0, 5.0)):
    return GeometryEvidence(
        geometry_id=gid, provider=GeometryProvider.GRASSHOPPER,
        geometry_type=geometry_type, centroid=list(centroid),
    )


def _candidate(geometry_id, score, reasons):
    return GeometryAssociation(
        geometry_id=geometry_id,
        provider=GeometryProvider.GRASSHOPPER,
        score=ScoreValue(value=score) if score is not None else None,
        evidence=[
            EvidenceRecord(
                evidence_id="e", evidence_type=EvidenceType.GRASSHOPPER_GEOMETRY,
                source="test", strength=EvidenceStrength.EXPLICIT,
            )
        ],
        reason_codes=list(reasons),
    )


class GhxPairingTests(unittest.TestCase):
    def test_matching_text_produces_ghx_candidate(self):
        annotation = _annotation("W8X10")
        pairs = [{"text": "W8X10", "geometry_id": "geom_1"}]
        candidate, discrepancy = associate_via_ghx_pairing(annotation, pairs)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.geometry_id, "geom_1")
        self.assertIn(REASON_GHX_EXISTING_PAIR, candidate.reason_codes)
        self.assertIsNone(discrepancy)

    def test_ghx_text_mismatch_is_surfaced_as_discrepancy_not_silent(self):
        annotation = _annotation("W8")  # PDF says W8
        pairs = [{"text": "W8", "geometry_id": "geom_1", "full_text": "W8X10"}]
        candidate, discrepancy = associate_via_ghx_pairing(annotation, pairs)
        self.assertIsNotNone(candidate)
        self.assertEqual(discrepancy, "W8X10")


class NearestGeometryFallbackTests(unittest.TestCase):
    def test_nearest_structural_curve_is_used_when_unambiguous(self):
        annotation = _annotation(anchor=(0.0, 0.0))
        geometry = [_geom("near", centroid=(1.0, 0.0)), _geom("far", centroid=(100.0, 0.0))]
        candidate = associate_via_nearest_geometry(annotation, geometry, transform=None)
        self.assertEqual(candidate.geometry_id, "near")
        self.assertIn(REASON_NEAREST_STRUCTURAL_CURVE, candidate.reason_codes)

    def test_two_equally_plausible_beams_abstain(self):
        annotation = _annotation(anchor=(0.0, 0.0))
        geometry = [_geom("a", centroid=(1.0, 0.0)), _geom("b", centroid=(1.01, 0.0))]
        candidate = associate_via_nearest_geometry(annotation, geometry, transform=None)
        self.assertIn(REASON_AMBIGUOUS_MULTIPLE_BEAMS, candidate.reason_codes)
        self.assertEqual(candidate.review_status, ReviewStatus.NEEDS_REVIEW)

    def test_no_anchor_no_candidate(self):
        annotation = SemanticAnnotation(annotation_id="a", page=1, original_text="W8X10")
        geometry = [_geom("a")]
        self.assertIsNone(associate_via_nearest_geometry(annotation, geometry, transform=None))


class FusionTests(unittest.TestCase):
    def test_agreement_merges_evidence(self):
        ghx = _candidate("geom_1", 0.9, [REASON_GHX_EXISTING_PAIR])
        pdf = _candidate("geom_1", None, [REASON_NEAREST_STRUCTURAL_CURVE])
        fused = fuse_candidates(ghx, pdf)
        self.assertEqual(len(fused), 1)
        self.assertEqual(fused[0].geometry_id, "geom_1")

    def test_disagreement_flags_review_both_sides(self):
        ghx = _candidate("geom_1", 0.9, [REASON_GHX_EXISTING_PAIR])
        pdf = _candidate("geom_2", None, [REASON_NEAREST_STRUCTURAL_CURVE])
        fused = fuse_candidates(ghx, pdf)
        self.assertEqual(len(fused), 2)
        for c in fused:
            self.assertEqual(c.review_status, ReviewStatus.NEEDS_REVIEW)
            self.assertIn(REASON_GHX_PDF_DISAGREEMENT, c.reason_codes)

    def test_only_one_source_passes_through_as_pending(self):
        ghx = _candidate("geom_1", 0.9, [REASON_GHX_EXISTING_PAIR])
        fused = fuse_candidates(ghx, None)
        self.assertEqual(fused, [ghx])
        self.assertEqual(fused[0].review_status, ReviewStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
