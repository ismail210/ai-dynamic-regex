"""
Regression tests for role-label contamination (accuracy sprint Phase 1C).

Section family (W / HSS / C / MC / L / WT / ST / MT / ...) must never
directly imply structural role (beam / column / brace / plate / connection).
Role may only come from explicit text keywords, geometry orientation, and
graph connectivity — ambiguous cases must resolve to "other" (unknown), never
a family-derived guess.

These tests reproduce the specific contamination the audit found:
  - ``rule_engine._infer_role`` returned non-canonical "member"/"bolt" for
    diagonal/bolt cases, which fell through to a family-shortcut table.
  - ``neural_dataset._member_role`` had its own family->role table
    (_ROLE_FROM_FAMILY) used as GraphSAGE training-label ground truth,
    contradicting its own docstring.
"""

from __future__ import annotations

import unittest

from services.engineering.rule_engine import _infer_role, evaluate_engineering_rules
from services.training_pipeline.neural_dataset import _member_role


# Same geometry/connectivity scenario applied across every family — if role
# depends on family, these will disagree with each other; they must not.
FAMILY_EXAMPLES = [
    "W14X90",
    "HSS8X8X1/2",
    "C10X20",
    "MC12X35",
    "L4X4X3/8",
    "WT7X15",
    "ST6X15.9",
    "MT5X4.5",
]


class InferRoleFamilyIndependenceTests(unittest.TestCase):
    def test_horizontal_orientation_is_beam_regardless_of_family(self):
        geometry = {"orientation": 5.0}
        graph_preview = {"structural_links": 0}
        roles = {
            family: _infer_role(family, graph_preview, geometry)
            for family in FAMILY_EXAMPLES
        }
        self.assertEqual(set(roles.values()), {"beam"}, roles)

    def test_vertical_connected_orientation_is_column_regardless_of_family(self):
        geometry = {"orientation": 85.0}
        graph_preview = {"structural_links": 1}
        roles = {
            family: _infer_role(family, graph_preview, geometry)
            for family in FAMILY_EXAMPLES
        }
        self.assertEqual(set(roles.values()), {"column"}, roles)

    def test_diagonal_connected_orientation_is_brace_regardless_of_family(self):
        geometry = {"orientation": 45.0}
        graph_preview = {"structural_links": 1}
        roles = {
            family: _infer_role(family, graph_preview, geometry)
            for family in FAMILY_EXAMPLES
        }
        self.assertEqual(set(roles.values()), {"brace"}, roles)

    def test_diagonal_unconnected_orientation_is_other_not_a_guess(self):
        """A diagonal member with no confirmed graph connectivity must not be
        guessed as brace, column, or (worst of all) a family-derived beam."""

        geometry = {"orientation": 45.0}
        graph_preview = {"structural_links": 0}
        roles = {
            family: _infer_role(family, graph_preview, geometry)
            for family in FAMILY_EXAMPLES
        }
        self.assertEqual(set(roles.values()), {"other"}, roles)

    def test_missing_orientation_signal_is_other_not_defaulted_to_beam(self):
        """No geometry at all must not silently coerce to orientation=0.0
        (which would previously default to "beam" for every family)."""

        roles = {
            family: _infer_role(family, {"structural_links": 0}, {})
            for family in FAMILY_EXAMPLES
        }
        self.assertEqual(set(roles.values()), {"other"}, roles)

    def test_explicit_text_keyword_outranks_geometry_for_every_family(self):
        geometry = {"orientation": 5.0}  # would otherwise say "beam"
        graph_preview = {"structural_links": 0}
        for family in FAMILY_EXAMPLES:
            with self.subTest(family=family):
                role = _infer_role(f"COLUMN {family}", graph_preview, geometry)
                self.assertEqual(role, "column")

    def test_bolt_keyword_maps_to_canonical_connection_role(self):
        role = _infer_role("A325 BOLT", {}, {})
        self.assertEqual(role, "connection")

    def test_evaluate_engineering_rules_always_returns_canonical_role(self):
        canonical = {"beam", "column", "brace", "plate", "connection", "other"}
        for family in FAMILY_EXAMPLES:
            with self.subTest(family=family):
                evaluation = evaluate_engineering_rules(
                    token=family,
                    predicted_shape=family,
                    geometry={"orientation": 45.0},
                    graph_preview={"structural_links": 0},
                )
                self.assertIn(evaluation.member_role, canonical)


class MemberRoleTrainingLabelTests(unittest.TestCase):
    """neural_dataset._member_role must never fall back to a family lookup."""

    def test_no_rules_role_never_falls_back_to_family(self):
        # Previously: HSS -> "column", L -> "brace", W -> "beam", etc. via
        # _ROLE_FROM_FAMILY. Now: no signal in, "other" out, for every family.
        roles = {family: _member_role(family, None) for family in FAMILY_EXAMPLES}
        self.assertEqual(set(roles.values()), {"other"}, roles)

    def test_non_canonical_rules_role_does_not_fall_back_to_family(self):
        # A stray non-canonical string (e.g. old "member"/"bolt" values, or
        # any other unexpected token) must also resolve to "other", not a
        # family guess.
        for family in FAMILY_EXAMPLES:
            with self.subTest(family=family):
                self.assertEqual(_member_role(family, "member"), "other")
                self.assertEqual(_member_role(family, "bolt"), "other")

    def test_canonical_rules_role_is_passed_through_unchanged(self):
        for family in FAMILY_EXAMPLES:
            with self.subTest(family=family):
                self.assertEqual(_member_role(family, "brace"), "brace")
                self.assertEqual(_member_role(family, "COLUMN"), "column")


if __name__ == "__main__":
    unittest.main()
