"""Tests for anonymous dimension contextual resolver."""

from __future__ import annotations

import unittest

from services.annotation.anonymous_dimension_resolver import resolve_anonymous_dimension


def _evidence(**overrides):
    base = {
        "thickness_value": '3/8"',
        "leader": {"present": False},
        "target_geometry": [],
        "nearby_text": [],
        "nearby_tokens": [],
        "region_kind": "unknown",
        "in_notes_region": False,
        "dlp_hints": {"supports_plate": False, "supports_bent_plate": False},
    }
    base.update(overrides)
    return base


class AnonymousDimensionResolverTests(unittest.TestCase):
    def test_abstains_without_context(self):
        result = resolve_anonymous_dimension(_evidence(), raw_text='3/8"')
        self.assertTrue(result["abstain"])
        self.assertIsNone(result["recommended"])
        self.assertTrue(
            any(c["type"] == "DIMENSION" for c in result["semantic_candidates"])
        )

    def test_promotes_bent_plate_with_strong_evidence(self):
        result = resolve_anonymous_dimension(
            _evidence(
                leader={"present": True},
                target_geometry=[{"plate_like": True, "geometry_id": "g1"}],
                nearby_text=["BENT PL", "CONNECTION"],
                region_kind="connection_detail",
            ),
            raw_text='3/8"',
        )
        self.assertFalse(result["abstain"])
        self.assertEqual(result["recommended"]["type"], "BENT_PLATE")

    def test_legend_only_does_not_promote_plate(self):
        result = resolve_anonymous_dimension(
            _evidence(dlp_hints={"supports_plate": True, "supports_bent_plate": False}),
            raw_text='1/2"',
        )
        self.assertTrue(result["abstain"])

    def test_notes_region_forces_abstain(self):
        result = resolve_anonymous_dimension(
            _evidence(in_notes_region=True, region_kind="notes"),
            raw_text='3/8"',
        )
        self.assertTrue(result["abstain"])
        top = result["semantic_candidates"][0]
        self.assertEqual(top["type"], "DIMENSION")


if __name__ == "__main__":
    unittest.main()
