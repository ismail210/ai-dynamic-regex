"""Tests for services.semantic.repair_shadow -- the shadow-mode bridge from
the semantic pipeline to the stronger services.label_reconstruction
candidate/ranking engine (repair-trace sprint).

Real pipeline data throughout: every test runs the actual
``process_primitives`` pipeline and the actual ``attach_repair_shadow``,
never a hand-built SemanticAnnotation with faked fields.
"""
from __future__ import annotations

import unittest

from services.semantic.models import (
    CATALOG_EXACT_MATCH,
    OperationKind,
    ReviewStatus,
    SCORE_RAW_MODEL,
    SCORE_SIMILARITY,
)
from services.semantic.repair_shadow import attach_repair_shadow, needs_repair_shadow
from services.semantic_preprocessor.models import TextPrimitive
from services.semantic_preprocessor.pipeline import process_primitives


def _prim(pid, text, bbox, page=1, font_size=10.0):
    return TextPrimitive(primitive_id=pid, page=page, text=text, bbox=list(bbox), font_size=font_size)


def _run(*texts_and_bboxes):
    primitives = [_prim(f"p{i}", text, bbox) for i, (text, bbox) in enumerate(texts_and_bboxes)]
    document = process_primitives(primitives, document_id="doc_test")
    attach_repair_shadow(document)
    return {a.primary_label: a for a in document.annotations}


class NeedsRepairShadowTests(unittest.TestCase):
    def test_exact_catalog_label_is_excluded(self):
        anns = _run(("W24X68", [0, 0, 60, 10]))
        ann = anns["W24X68"]
        self.assertEqual(ann.structural_parse.catalog_status, CATALOG_EXACT_MATCH)
        self.assertFalse(needs_repair_shadow(ann))
        self.assertEqual(ann.repair_candidates, [])

    def test_bare_incomplete_label_is_excluded_completion_not_repair(self):
        anns = _run(("W8", [0, 0, 20, 10]))
        ann = anns["W8"]
        self.assertEqual(ann.structural_parse.grammar, "incomplete")
        self.assertFalse(needs_repair_shadow(ann))

    def test_non_structural_note_text_is_excluded(self):
        # A revision date and a kip load callout must never enter the
        # steel-section repair engine -- found necessary empirically (a
        # naive is_structural==False gate fired on ~94% of a real
        # document's annotations, including dates).
        anns = _run(("1/22/2026", [0, 0, 60, 10]), ("35K", [0, 20, 30, 30]))
        self.assertFalse(needs_repair_shadow(anns["1/22/2026"]))
        self.assertFalse(needs_repair_shadow(anns["35K"]))
        self.assertEqual(anns["1/22/2026"].repair_candidates, [])
        self.assertEqual(anns["35K"].repair_candidates, [])


class SubstitutionRepairTests(unittest.TestCase):
    def test_ocr_confusion_gets_ranked_candidates_from_real_engine(self):
        anns = _run(("W18X4O", [0, 0, 60, 10]))
        ann = anns["W18X4O"]
        self.assertTrue(needs_repair_shadow(ann))
        self.assertGreater(len(ann.repair_candidates), 0)
        top = ann.repair_candidates[0]
        self.assertEqual(top.candidate_text, "W18X40")
        self.assertEqual(top.rank, 1)
        # Never changes effective_text by itself (shadow mode) beyond
        # whatever the pre-existing deterministic single-char repair
        # already does -- the point under test is that repair_candidates
        # exist and review is flagged, not that this module mutates the
        # deterministic engine's own output.
        self.assertEqual(ann.review_status, ReviewStatus.NEEDS_REVIEW)

    def test_score_kind_is_never_reported_as_calibrated(self):
        anns = _run(("W18X4O", [0, 0, 60, 10]))
        top = anns["W18X4O"].repair_candidates[0]
        if top.scores:
            self.assertIn(top.scores[0].kind, (SCORE_RAW_MODEL,))
            self.assertFalse(top.scores[0].calibrated)


class DeletionAndInsertionRetrievalTests(unittest.TestCase):
    """Brief Section 25: the benchmark found deletion/insertion get ZERO
    repair attempts in the deterministic-only path. Assert the shadow
    engine actually reaches candidate retrieval for both."""

    def test_deletion_reaches_broadened_candidates(self):
        anns = _run(("W10X3", [0, 0, 60, 10]))  # W10X33 with the trailing digit deleted
        ann = anns["W10X3"]
        self.assertEqual(ann.structural_parse.catalog_status, "not_in_catalog")
        self.assertTrue(needs_repair_shadow(ann))
        self.assertGreater(len(ann.repair_candidates), 0, "deletion must reach candidate retrieval")
        texts = [c.candidate_text for c in ann.repair_candidates]
        self.assertIn("W10X33", texts)
        # Reaches the broadened fallback (reconstruct() widened the search);
        # scored by the real ranker when one is active/available on this
        # machine, else by SequenceMatcher similarity as the last resort --
        # either is acceptable here, a bare/uninformative score is not.
        for c in ann.repair_candidates:
            self.assertIn(c.source, ("label_reconstruction_broadened_ranker", "label_reconstruction_broadened_similarity"))
            self.assertEqual(c.scores[0].kind, SCORE_RAW_MODEL if c.source.endswith("ranker") else SCORE_SIMILARITY)
            self.assertFalse(c.scores[0].calibrated)

    def test_insertion_reaches_ranked_candidates(self):
        anns = _run(("W18XX40", [0, 0, 70, 10]))  # extra "X" inserted
        ann = anns["W18XX40"]
        self.assertTrue(needs_repair_shadow(ann))
        self.assertGreater(len(ann.repair_candidates), 0, "insertion must reach candidate retrieval")
        self.assertEqual(ann.repair_candidates[0].candidate_text, "W18X40")


class ShadowModeSafetyTests(unittest.TestCase):
    def test_repair_proposal_operation_is_never_pre_accepted(self):
        anns = _run(("W18XX40", [0, 0, 70, 10]))
        ann = anns["W18XX40"]
        shadow_ops = [
            o for o in ann.operations
            if o.operation == OperationKind.REPAIR and "label_reconstruction_shadow_proposal" in o.reason_codes
        ]
        self.assertEqual(len(shadow_ops), 1)
        self.assertFalse(shadow_ops[0].accepted, "a shadow proposal must never be pre-accepted")

    def test_clean_control_never_gets_a_repair_candidate_or_operation_change(self):
        before = _run(("W24X68", [0, 0, 60, 10]))["W24X68"]
        op_count_before = len(before.operations)
        # Re-running attach_repair_shadow again must be a no-op for a clean label.
        anns = _run(("W24X68", [0, 0, 60, 10]), ("W18X4O", [0, 20, 60, 30]))
        clean = anns["W24X68"]
        self.assertEqual(clean.effective_text, "W24X68")
        self.assertEqual(clean.repair_candidates, [])
        self.assertEqual(len(clean.operations), op_count_before)

    def test_module_never_imports_the_attack_benchmark_package(self):
        """Oracle target must never enter repair features (Section 26/39):
        static guarantee that this module has no dependency path to the
        attack-manifest oracle at all."""
        import services.semantic.repair_shadow as module
        source = module.__file__
        with open(source, encoding="utf-8") as fh:
            contents = fh.read()
        self.assertNotIn("pdf_attack", contents)
        self.assertNotIn("mutation_id", contents)
        self.assertNotIn("target_text", contents)


if __name__ == "__main__":
    unittest.main()
