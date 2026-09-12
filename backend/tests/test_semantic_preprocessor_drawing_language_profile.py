"""Drawing Language Profile resolver tests (Section 29)."""
from __future__ import annotations

import unittest

from services.semantic_preprocessor.drawing_language_profile import resolve_completion


def _rule(trigger, result, status, pages=None):
    return {
        "rule_id": f"{trigger}-{result}-{status}",
        "trigger": trigger,
        "result": result,
        "rule_status": status,
        "scope": {"pages": pages or []},
        "source_evidence": [{"page": (pages or [1])[0], "quote": f"{trigger} = {result}"}],
        "confidence": 0.95,
    }


class SourceVerifiedCompletionTests(unittest.TestCase):
    def test_source_verified_rule_allows_completion(self):
        rules = [_rule("W8", "W8X10", "source_verified", pages=[2])]
        resolution = resolve_completion("W8", page=2, rules=rules)
        self.assertTrue(resolution.allowed)
        self.assertEqual(resolution.canonical, "W8X10")

    def test_proposed_inference_alone_never_completes(self):
        rules = [_rule("W8", "W8X10", "proposed_inference", pages=[2])]
        resolution = resolve_completion("W8", page=2, rules=rules)
        self.assertFalse(resolution.allowed)
        self.assertIsNone(resolution.canonical)

    def test_no_rule_found_abstains(self):
        resolution = resolve_completion("W8", page=2, rules=[])
        self.assertFalse(resolution.allowed)


class ConflictHandlingTests(unittest.TestCase):
    def test_conflicting_source_verified_rules_abstain(self):
        rules = [
            _rule("W8", "W8X10", "source_verified", pages=[2]),
            _rule("W8", "W8X15", "source_verified", pages=[2]),
        ]
        resolution = resolve_completion("W8", page=2, rules=rules)
        self.assertFalse(resolution.allowed)
        self.assertEqual(resolution.reason, "conflicting_source_verified_rules")

    def test_page_scoped_rule_wins_over_project_wide_rule(self):
        rules = [
            _rule("W8", "W8X10", "source_verified", pages=[]),  # project-wide
            _rule("W8", "W8X15", "source_verified", pages=[18]),  # local override
        ]
        resolution = resolve_completion("W8", page=18, rules=rules)
        self.assertTrue(resolution.allowed)
        self.assertEqual(resolution.canonical, "W8X15")

    def test_project_wide_rule_used_off_the_scoped_page(self):
        rules = [
            _rule("W8", "W8X10", "source_verified", pages=[]),
            _rule("W8", "W8X15", "source_verified", pages=[18]),
        ]
        resolution = resolve_completion("W8", page=5, rules=rules)
        self.assertTrue(resolution.allowed)
        self.assertEqual(resolution.canonical, "W8X10")


if __name__ == "__main__":
    unittest.main()
