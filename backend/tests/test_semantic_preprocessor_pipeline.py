"""End-to-end SemanticPreprocessor pipeline tests.

The single most important test in this file is
``test_ghx_agreement_never_completes_a_label_without_source_verified_rule``
(Section 45's mandatory case): Grasshopper's own model can say whatever it
wants about a beam's size -- it must never be allowed to silently promote
``W8`` to ``W8X10`` in the semantic layer. Only a source_verified Drawing
Language Profile rule may do that.
"""
from __future__ import annotations

import unittest

from services.semantic_preprocessor.geometry_evidence import GrasshopperGeometryEvidenceProvider
from services.semantic_preprocessor.models import (
    OP_COMPLETION,
    OP_NONE,
    REVIEW_AUTO_ACCEPTED,
    REVIEW_PENDING,
    TextPrimitive,
)
from services.semantic_preprocessor.pipeline import process_primitives


def _prim(pid, text, bbox, page=1, font_size=10.0):
    return TextPrimitive(primitive_id=pid, page=page, text=text, bbox=list(bbox), font_size=font_size)


class PipelineRunsWithoutGrasshopperTests(unittest.TestCase):
    def test_semantic_pipeline_succeeds_with_no_geometry_provider(self):
        primitives = [_prim("p1", "HSS 8X8X0.375", [0, 0, 60, 10])]
        document = process_primitives(primitives, document_id="doc1")
        self.assertEqual(len(document.annotations), 1)
        ann = document.annotations[0]
        self.assertEqual(ann.correction.canonical, "HSS8X8X3/8")
        self.assertEqual(ann.review_status, REVIEW_AUTO_ACCEPTED)
        self.assertEqual(document.grasshopper_geometry, [])


class GhxNeverCompletesALabelTests(unittest.TestCase):
    def test_ghx_agreement_never_completes_a_label_without_source_verified_rule(self):
        # PDF says "W8" (incomplete). GHX's own model happens to have a
        # beam it calls "W8X10" at the same paired location. There is no
        # drawing-language rule at all. The annotation's label must stay
        # exactly "W8" -- GHX's text becomes a diagnostic discrepancy, never
        # a rewrite.
        primitives = [_prim("p1", "W8", [0, 0, 20, 10])]
        provider = GrasshopperGeometryEvidenceProvider({
            "source_definition_sha256": "sha",
            "sheet": "S-1",
            "RH_OUT:BeamCrv": [{"element_id": "e1", "points": [[0, 0], [10, 0]], "length": 10.0}],
        })
        ghx_pairs = [{"text": "W8", "geometry_id": "geom_ghx_e1", "full_text": "W8X10"}]

        document = process_primitives(
            primitives, document_id="doc1",
            geometry_provider=provider, ghx_text_pairs=ghx_pairs,
            drawing_language_rules=[],  # no evidence at all
        )
        ann = document.annotations[0]
        self.assertEqual(ann.correction.canonical, "W8")
        self.assertNotEqual(ann.correction.operation, OP_COMPLETION)
        # The discrepancy must still be visible somewhere for a human/QA pass.
        self.assertEqual(len(document.diagnostics["ghx_text_discrepancies"]), 1)
        self.assertEqual(document.diagnostics["ghx_text_discrepancies"][0]["ghx_text"], "W8X10")

    def test_source_verified_rule_does_allow_completion(self):
        primitives = [_prim("p1", "W8", [0, 0, 20, 10])]
        rules = [{
            "rule_id": "r1", "trigger": "W8", "result": "W8X10",
            "rule_status": "source_verified", "scope": {"pages": [1]},
            "source_evidence": [{"page": 1, "quote": "W8 = W8X10"}], "confidence": 0.95,
        }]
        document = process_primitives(primitives, document_id="doc1", drawing_language_rules=rules)
        ann = document.annotations[0]
        self.assertEqual(ann.correction.operation, OP_COMPLETION)
        self.assertEqual(ann.correction.canonical, "W8X10")
        self.assertEqual(ann.review_status, REVIEW_AUTO_ACCEPTED)

    def test_conflicting_rules_force_review_not_a_guess(self):
        primitives = [_prim("p1", "W8", [0, 0, 20, 10])]
        rules = [
            {"rule_id": "r1", "trigger": "W8", "result": "W8X10", "rule_status": "source_verified",
             "scope": {"pages": [1]}, "source_evidence": [], "confidence": 0.9},
            {"rule_id": "r2", "trigger": "W8", "result": "W8X15", "rule_status": "source_verified",
             "scope": {"pages": [1]}, "source_evidence": [], "confidence": 0.9},
        ]
        document = process_primitives(primitives, document_id="doc1", drawing_language_rules=rules)
        ann = document.annotations[0]
        self.assertEqual(ann.correction.operation, OP_NONE)
        self.assertEqual(ann.correction.canonical, "W8")
        self.assertNotEqual(ann.review_status, REVIEW_AUTO_ACCEPTED)


class GeometryEnrichmentTests(unittest.TestCase):
    def test_geometry_evidence_enriches_but_never_overrides_text(self):
        primitives = [_prim("p1", "W8X10", [0, 0, 40, 10])]
        provider = GrasshopperGeometryEvidenceProvider({
            "source_definition_sha256": "sha",
            "sheet": "S-1",
            "RH_OUT:BeamCrv": [{"element_id": "e1", "points": [[0, 0], [10, 0]], "length": 10.0}],
        })
        ghx_pairs = [{"text": "W8X10", "geometry_id": "geom_ghx_e1"}]
        document = process_primitives(
            primitives, document_id="doc1", geometry_provider=provider, ghx_text_pairs=ghx_pairs,
        )
        ann = document.annotations[0]
        self.assertEqual(ann.correction.canonical, "W8X10")
        self.assertEqual(len(ann.geometry_associations), 1)
        self.assertEqual(ann.geometry_associations[0].geometry_id, "geom_ghx_e1")


class UnresolvedIncompleteLabelStaysPendingTests(unittest.TestCase):
    def test_no_evidence_at_all_stays_pending_not_rewritten(self):
        primitives = [_prim("p1", "W8", [0, 0, 20, 10])]
        document = process_primitives(primitives, document_id="doc1")
        ann = document.annotations[0]
        self.assertEqual(ann.correction.canonical, "W8")
        self.assertEqual(ann.review_status, REVIEW_PENDING)


if __name__ == "__main__":
    unittest.main()
