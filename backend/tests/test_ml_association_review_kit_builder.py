"""Regression tests for the local-only review-kit HTML generator.

Uses synthetic label-group data only -- never real project content, so
this test never needs to touch the ignored, confidential pilot
directory. Verifies the review kit's core correctness properties: valid
HTML (no f-string brace-escaping artifacts), the bias-reduction display
ordering is independent of production rank, and the heuristic reveal
panel is present but not shown by default.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_ml_association_review_kit.py"
_spec = importlib.util.spec_from_file_location("build_ml_association_review_kit", _MODULE_PATH)
kit = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = kit
_spec.loader.exec_module(kit)  # type: ignore[union-attr]


def _synthetic_payload():
    return {
        "export_schema_version": "2.0",
        "heuristic_selection_candidate_id": "assoc_bbb",
        "group": {
            "group_id": "group_test123",
            "project_id": "project_999",
            "document_id": "doc_999",
            "page_id": "page_999",
            "page_number": 1,
            "text_entity_id": "token_1",
            "label": {"raw_text": "W12X26", "normalized_text": None, "label_type": "beam"},
            "nearby_label_ids": ["token_2", "token_3"],
            "extraction_diagnostics": {
                "geometry": {"drawing_cap_applied": True},
                "graph": {"geometry_pairwise_window_triggered": True},
            },
            "candidates": [
                {
                    "association_candidate_id": "assoc_aaa",
                    "is_no_match_placeholder": False,
                    "geometry": {"geometry_kind": "line", "geometry_bbox": [0, 0, 10, 10]},
                    "relationship": {
                        "leader_support_evidence": False,
                        "centroid_distance": 5.0,
                        "graph_degree": 2,
                    },
                    "heuristic": {"current_heuristic_selected": False},
                },
                {
                    "association_candidate_id": "assoc_bbb",
                    "is_no_match_placeholder": False,
                    "geometry": {"geometry_kind": "leader", "geometry_bbox": [1, 1, 11, 11]},
                    "relationship": {
                        "leader_support_evidence": True,
                        "centroid_distance": 3.0,
                        "graph_degree": 1,
                    },
                    "heuristic": {"current_heuristic_selected": True},
                },
                {
                    "association_candidate_id": "assoc_no_match",
                    "is_no_match_placeholder": True,
                    "geometry": None,
                    "relationship": {},
                    "heuristic": {"current_heuristic_selected": False},
                },
            ],
        },
    }


class ReviewKitBuilderTests(unittest.TestCase):
    def test_group_page_has_no_fstring_brace_artifacts(self) -> None:
        page = kit._render_group_page(_synthetic_payload(), "group_test123.svg", {})
        self.assertNotIn("{{", page)
        self.assertNotIn("}}", page)

    def test_group_page_contains_every_enum_option(self) -> None:
        page = kit._render_group_page(_synthetic_payload(), "group_test123.svg", {})
        for value, _ in kit.REVIEW_LABEL_OPTIONS:
            self.assertIn(f'value="{value}"', page)
        for value in kit.CALLOUT_SCOPE_OPTIONS:
            self.assertIn(f'value="{value}"', page)

    def test_heuristic_selection_is_not_visible_by_default(self) -> None:
        page = kit._render_group_page(_synthetic_payload(), "group_test123.svg", {})
        # The reveal panel must exist but be hidden (display:none) until the
        # reviewer explicitly clicks the reveal button.
        self.assertIn('id="heuristic-reveal"', page)
        self.assertIn("display: none", page)

    def test_display_order_is_independent_of_production_rank(self) -> None:
        # The candidates list is already in production-preferred order
        # (assoc_bbb, the heuristic pick, listed second in the fixture but
        # is the "best" by construction). The rendered page must not
        # necessarily preserve that order -- it uses a hash-based key.
        order_a = kit._display_order_key("assoc_aaa", "group_test123")
        order_b = kit._display_order_key("assoc_bbb", "group_test123")
        order_c = kit._display_order_key("assoc_no_match", "group_test123")
        # Deterministic: same inputs always produce the same order.
        self.assertEqual(order_a, kit._display_order_key("assoc_aaa", "group_test123"))
        # Different group -> different order (no fixed global bias).
        self.assertNotEqual(order_a, kit._display_order_key("assoc_aaa", "group_other"))
        self.assertEqual(len({order_a, order_b, order_c}), 3)

    def test_placeholder_candidate_is_rendered_as_no_valid_target(self) -> None:
        page = kit._render_group_page(_synthetic_payload(), "group_test123.svg", {})
        self.assertIn("NO VALID TARGET", page)

    def test_index_page_lists_every_row(self) -> None:
        rows = [
            {"project_id": "project_999", "page_number": 1, "label_raw_text": "W12X26",
             "candidate_count": 2, "has_leader_evidence": True, "group_id": "group_test123"},
            {"project_id": "project_998", "page_number": 2, "label_raw_text": "W8X10",
             "candidate_count": 1, "has_leader_evidence": False, "group_id": "group_test456"},
        ]
        index_html = kit._render_index(rows)
        self.assertIn("group_test123.html", index_html)
        self.assertIn("group_test456.html", index_html)
        self.assertIn("2 label groups", index_html)


if __name__ == "__main__":
    unittest.main()
