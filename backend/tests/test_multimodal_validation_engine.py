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

    def test_repeated_valid_section_no_duplicate_warning(self):
        """A section legitimately used by several independent members (e.g.
        beam 1, beam 2, beam 3 all W16X26) must not be flagged just because
        the designation string repeats."""

        predictions = []
        for i in range(3):
            pred = _prediction(
                section="W16X26", family="W", confidence=0.92, original="W16X26"
            )
            pred["object_id"] = f"obj-{i}"
            pred["component_id"] = f"cmp-{i}"
            predictions.append(pred)

        report = validate_multimodal_predictions(predictions)

        types = {item["type"] for item in report["actionable_issues"]}
        self.assertNotIn("duplicate_members", types)
        for token in report["tokens"]:
            self.assertNotIn("duplicate_members", token["detected_issues"])
            self.assertEqual(token["status"], "PASS")
        # Occurrence count stays visible as data, just not as a warning.
        self.assertEqual(
            [token["predicted_quantity"] for token in report["tokens"]], [3, 3, 3]
        )

    def test_many_repeated_valid_sections_no_hidden_threshold(self):
        """No artificial cap on how many members may share a designation."""

        predictions = []
        for i in range(20):
            pred = _prediction(
                section="W16X26", family="W", confidence=0.92, original="W16X26"
            )
            pred["object_id"] = f"obj-{i}"
            pred["component_id"] = f"cmp-{i}"
            predictions.append(pred)

        report = validate_multimodal_predictions(predictions)

        types = {item["type"] for item in report["actionable_issues"]}
        self.assertNotIn("duplicate_members", types)
        self.assertTrue(all(token["status"] == "PASS" for token in report["tokens"]))

    def test_repeated_different_valid_section_no_duplicate_warning(self):
        predictions = []
        for i in range(4):
            pred = _prediction(
                section="HSS6X6X1/4",
                family="HSS",
                confidence=0.9,
                original="HSS6X6X1/4",
            )
            pred["object_id"] = f"obj-hss-{i}"
            pred["component_id"] = f"cmp-hss-{i}"
            predictions.append(pred)

        report = validate_multimodal_predictions(predictions)

        types = {item["type"] for item in report["actionable_issues"]}
        self.assertNotIn("duplicate_members", types)

    def test_repeated_section_with_real_conflict_still_flagged(self):
        """Repetition-based warnings are gone, but genuine per-token evidence
        conflicts (here: geometry disagreement) must still surface."""

        predictions = []
        for i in range(3):
            pred = _prediction(
                section="W16X26",
                family="W",
                confidence=0.5,
                original="W16X26",
                geometry_similarity=0.1,
                issues=["geometry_conflict"],
            )
            pred["object_id"] = f"obj-conf-{i}"
            pred["component_id"] = f"cmp-conf-{i}"
            predictions.append(pred)

        report = validate_multimodal_predictions(predictions)

        types = {item["type"] for item in report["actionable_issues"]}
        self.assertNotIn("duplicate_members", types)
        self.assertIn("geometry_consistency", types)
        self.assertTrue(
            any(token["status"] in {"WARNING", "FAIL"} for token in report["tokens"])
        )

    def test_repeated_invalid_catalog_section_still_protected(self):
        """Duplicate-handling changes must not launder an invalid designation
        into something that looks valid."""

        from services.database_loader import is_catalog_label

        self.assertFalse(is_catalog_label("W12X999"))

        predictions = []
        for i in range(3):
            pred = _prediction(
                section="W12X999",
                family="HSS",
                original="W12X999",
                corrected="W12X999",
                confidence=0.8,
            )
            pred["object_id"] = f"obj-bad-{i}"
            pred["component_id"] = f"cmp-bad-{i}"
            predictions.append(pred)

        report = validate_multimodal_predictions(predictions)

        types = {item["type"] for item in report["actionable_issues"]}
        self.assertIn("impossible_members", types)
        self.assertNotIn("duplicate_members", types)

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
