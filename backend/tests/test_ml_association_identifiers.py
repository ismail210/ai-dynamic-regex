"""Category 3: stable association candidate (and other) IDs."""

from __future__ import annotations

import unittest

from services.ml_association import identifiers


class IdentifierDeterminismTests(unittest.TestCase):
    def test_association_candidate_id_is_stable(self) -> None:
        a = identifiers.association_candidate_id("token_p1_0", "geom_abc", "v1")
        b = identifiers.association_candidate_id("token_p1_0", "geom_abc", "v1")
        self.assertEqual(a, b)

    def test_association_candidate_id_differs_by_geometry(self) -> None:
        a = identifiers.association_candidate_id("token_p1_0", "geom_abc", "v1")
        b = identifiers.association_candidate_id("token_p1_0", "geom_def", "v1")
        self.assertNotEqual(a, b)

    def test_association_candidate_id_differs_by_generator_version(self) -> None:
        a = identifiers.association_candidate_id("token_p1_0", "geom_abc", "v1")
        b = identifiers.association_candidate_id("token_p1_0", "geom_abc", "v2")
        self.assertNotEqual(
            a, b, "a candidate-generator bugfix must produce distinguishable IDs"
        )

    def test_association_candidate_id_no_match_placeholder_is_stable_and_distinct(self) -> None:
        no_match_a = identifiers.association_candidate_id("token_p1_0", None, "v1")
        no_match_b = identifiers.association_candidate_id("token_p1_0", None, "v1")
        real = identifiers.association_candidate_id("token_p1_0", "geom_abc", "v1")
        self.assertEqual(no_match_a, no_match_b)
        self.assertNotEqual(no_match_a, real)

    def test_group_id_excludes_candidate_set_from_its_identity(self) -> None:
        # Same label + generator version -> same group_id regardless of
        # what candidates happen to accompany it (see identifiers.py's
        # docstring for why this is deliberate).
        a = identifiers.group_id("token_p1_0", "v1")
        b = identifiers.group_id("token_p1_0", "v1")
        self.assertEqual(a, b)

    def test_page_id_is_stable_and_scoped_to_document(self) -> None:
        a = identifiers.page_id("doc_1", 1)
        b = identifiers.page_id("doc_2", 1)
        self.assertNotEqual(a, b)
        self.assertEqual(identifiers.page_id("doc_1", 1), identifiers.page_id("doc_1", 1))

    def test_outcome_id_is_stable_for_identical_review_event(self) -> None:
        a = identifiers.outcome_id("group_1", "alice", "2026-01-01T00:00:00Z")
        b = identifiers.outcome_id("group_1", "alice", "2026-01-01T00:00:00Z")
        self.assertEqual(a, b)

    def test_outcome_id_differs_for_a_correction(self) -> None:
        original = identifiers.outcome_id("group_1", "alice", "2026-01-01T00:00:00Z")
        correction = identifiers.outcome_id(
            "group_1", "alice", "2026-01-02T00:00:00Z", supersedes_outcome_id=original
        )
        self.assertNotEqual(original, correction)

    def test_ids_never_look_like_uuid4(self) -> None:
        # Regression guard for the exact defect Phase 1 fixed in
        # geometry_extractor/graph_builder -- this package must not
        # reintroduce uuid.uuid4()-based identifiers.
        candidate_id = identifiers.association_candidate_id("token_p1_0", "geom_abc", "v1")
        self.assertTrue(candidate_id.startswith("assoc_"))
        # A uuid4 hex has dashes in canonical form; our IDs never do.
        self.assertNotIn("-", candidate_id)


if __name__ == "__main__":
    unittest.main()
