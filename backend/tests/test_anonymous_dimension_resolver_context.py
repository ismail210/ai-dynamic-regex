"""Tests for resolver scoring with new context evidence fields."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_resolver():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "annotation"
        / "anonymous_dimension_resolver.py"
    )
    spec = importlib.util.spec_from_file_location(
        "anonymous_dimension_resolver_under_test", module_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_resolver = _load_resolver()
resolve_anonymous_dimension = _resolver.resolve_anonymous_dimension


def _evidence(**overrides):
    base = {
        "thickness_value": '3/8"',
        "nearby_text": ["SHEAR CONNECTION DETAIL"],
        "nearby_tokens": [{"text": "HSS8X8", "object_type": "column_or_brace"}],
        "nearby_structural_count": 1,
        "leader": {"present": True},
        "region_kind": "connection_detail",
        "in_notes_region": False,
        "in_title_block": False,
        "layout_dimension_is_non_steel": False,
        "evidence_summary": "leader path detected",
    }
    base.update(overrides)
    return base


class AnonymousDimensionResolverContextTests(unittest.TestCase):
    def test_title_block_forces_abstain(self):
        result = resolve_anonymous_dimension(
            _evidence(in_title_block=True, leader={"present": False}),
            raw_text='3/8"',
        )
        self.assertTrue(result["abstain"])
        self.assertIsNone(result["recommended"])

    def test_layout_dimension_forces_abstain(self):
        result = resolve_anonymous_dimension(
            _evidence(
                layout_dimension_is_non_steel=True,
                linked_layout_dimension_text='4"',
                leader={"present": False},
            ),
            raw_text='4"',
        )
        self.assertTrue(result["abstain"])

    def test_promotion_requires_structural_context(self):
        result = resolve_anonymous_dimension(
            _evidence(
                leader={"present": False},
                nearby_structural_count=0,
                region_kind="unknown",
                nearby_text=[],
            ),
            raw_text='3/8"',
        )
        self.assertTrue(result["abstain"])
        self.assertIsNone(result["recommended"])

    def test_promotion_with_leader_and_structural_context(self):
        result = resolve_anonymous_dimension(
            _evidence(nearby_text=['3/8" BENT PL']),
            raw_text='3/8"',
        )
        self.assertFalse(result["abstain"])
        self.assertIsNotNone(result["recommended"])


if __name__ == "__main__":
    unittest.main()
