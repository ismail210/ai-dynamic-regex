"""Multimodal validation issue taxonomy and database-independence tests."""

from __future__ import annotations

import unittest

from services.multimodal.validation_engine import validate_multimodal_predictions


def _prediction(
    *,
    section="W18X35",
    family="W",
    confidence=0.9,
    database_match=False,
    extraction_status="VALID",
    extraction_confidence=0.9,
    geometry_available=True,
    geometry_similarity=0.8,
    graph_degree=2,
    graph_consistency=0.8,
    rule_score=0.9,
    issues=None,
    original="W18X35",
    corrected=None,
    alternatives=None,
    length=120.0,
):
    return {
        "object_id": f"obj-{section}",
        "component_id": f"cmp-{section}",
        "original_token": original,
        "corrected_token": corrected or section,
        "family": family,
        "section": section,
        "predicted_shape": section,
        "entity_type": "structural",
        "confidence": confidence,
        "database_match": database_match,
        "alternatives": alternatives or [],
        "evidence": {
            "text": 0.4,
            "geometry": geometry_similarity * 0.3,
            "graph": graph_consistency * 0.15,
            "engineering_rules": rule_score * 0.05,
            "database": 0.0,
        },
        "explanation": {
            "reasons": ["AI prediction"],
            "text_similarity": 0.9,
            "geometry_similarity": geometry_similarity,
            "graph_consistency": graph_consistency,
            "contribution_percentages": {
                "text": 48,
                "geometry": 30,
                "graph": 17,
                "engineering_rules": 5,
                "database": 0,
            },
        },
        "geometry_preview": {"kind": "line", "length": length, "bbox": [0, 0, 10, 10]},
        "graph_preview": {"degree": graph_degree, "structural_links": 1},
        "features": {
            "text": {
                "extraction_status": extraction_status,
                "extraction_confidence": extraction_confidence,
            },
            "geometry": {
                "available": geometry_available,
                "similarity": geometry_similarity,
                "object": {"length": length},
            },
            "graph": {
                "degree": graph_degree,
                "graph_consistency": graph_consistency,
            },
            "engineering_rules": {"score": rule_score, "findings": [], "member_role": "beam"},
            "fusion": {"detected_issues": issues or []},
        },
    }


class MultimodalValidationTests(unittest.TestCase):
    def test_database_miss_does_not_fail_high_confidence(self):
        report = validate_multimodal_predictions(
            [_prediction(database_match=False, confidence=0.92)]
        )
        self.assertEqual(report["tokens"][0]["status"], "PASS")
        fail_types = {
            item["type"]
            for item in report["actionable_issues"]
            if item["severity"] == "FAIL"
        }
        self.assertNotIn("unknown_labels", fail_types)
        self.assertTrue(report["policy"]["database_alone_never_fails"])

    def test_extraction_and_geometry_issues_are_structured(self):
        report = validate_multimodal_predictions(
            [
                _prediction(
                    extraction_status="BROKEN",
                    extraction_confidence=0.4,
                    geometry_similarity=0.1,
                    confidence=0.5,
                    original="W18X3S",
                    corrected="W18X35",
                    alternatives=[{"shape": "W18X35", "confidence": 0.8}],
                    issues=["geometry_conflict", "low_extraction_confidence"],
                )
            ],
            extraction={
                "quality": {"status": "SUSPICIOUS", "score": 0.5},
                "dimensions": [],
            },
        )
        types = {item["type"] for item in report["actionable_issues"]}
        self.assertIn("extraction_quality", types)
        self.assertIn("geometry_consistency", types)
        issue = next(
            item
            for item in report["actionable_issues"]
            if item["type"] == "extraction_quality" and item.get("component_id")
        )
        self.assertIn(issue["severity"], {"WARNING", "FAIL"})
        self.assertTrue(issue["why"])
        self.assertTrue(issue["evidence"])
        self.assertTrue(issue["suggested_correction"])

    def test_quantity_missing_and_incorrect(self):
        report = validate_multimodal_predictions(
            [_prediction(section="W18X35")],
            expected_excel={
                "items": [
                    {"shape": "W18X35", "quantity": 3},
                    {"shape": "HSS6X6X1/2", "quantity": 2},
                ]
            },
        )
        types = {item["type"] for item in report["actionable_issues"]}
        self.assertIn("missing_members", types)
        self.assertIn("incorrect_quantities", types)
        missing = next(
            item
            for item in report["actionable_issues"]
            if item["type"] == "missing_members"
        )
        self.assertEqual(missing["severity"], "FAIL")
        self.assertEqual(missing["suggested_correction"]["section"], "HSS6X6X1/2")

    def test_impossible_member_and_wrong_section_name(self):
        report = validate_multimodal_predictions(
            [
                _prediction(
                    section="HSS6X6X1/2",
                    family="W",
                    original="WF18X35",
                    corrected="HSS6X6X1/2",
                    confidence=0.8,
                    alternatives=[{"shape": "W18X35", "confidence": 0.85}],
                )
            ]
        )
        types = {item["type"] for item in report["actionable_issues"]}
        self.assertIn("impossible_members", types)
        self.assertIn("wrong_section_names", types)
        for item in report["actionable_issues"]:
            self.assertIn("why", item)
            self.assertIn("evidence", item)
            self.assertFalse(item["database_decides"])


if __name__ == "__main__":
    unittest.main()
