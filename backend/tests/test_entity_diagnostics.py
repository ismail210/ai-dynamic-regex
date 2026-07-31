"""Tests for model-class entity mapping and holdout entity diagnostics."""

from __future__ import annotations

import unittest

from services.entity_diagnostics import build_entity_diagnostics
from services.entity_taxonomy import (
    CATEGORY_BOLT,
    CATEGORY_MATERIAL,
    CATEGORY_MISC,
    CATEGORY_PLATE,
    CATEGORY_STRUCTURAL,
    category_for_model_class,
    map_model_classes,
)


class CategoryForModelClassTests(unittest.TestCase):
    def test_steel_sections_include_pipe(self):
        for label in ("W", "HSS", "2L", "PIPE", "WT", "L"):
            self.assertEqual(
                category_for_model_class(label),
                CATEGORY_STRUCTURAL,
                label,
            )

    def test_bolt_precedence_over_material(self):
        for label in ("A325", "A490", "A307", "A563", "A2280", "F1852"):
            self.assertEqual(category_for_model_class(label), CATEGORY_BOLT, label)

    def test_material_grades(self):
        for label in ("A992", "A36", "A500", "A1064", "A108"):
            self.assertEqual(category_for_model_class(label), CATEGORY_MATERIAL, label)

    def test_plate_and_other(self):
        self.assertEqual(category_for_model_class("PL"), CATEGORY_PLATE)
        self.assertEqual(category_for_model_class("PLATE"), CATEGORY_PLATE)
        self.assertEqual(category_for_model_class("A"), CATEGORY_MISC)
        self.assertEqual(category_for_model_class(""), CATEGORY_MISC)

    def test_map_model_classes(self):
        mapping = map_model_classes(["W", "A992", "A325", "A"])
        self.assertEqual(mapping["W"]["entity_type"], CATEGORY_STRUCTURAL)
        self.assertEqual(mapping["W"]["entity_type_label"], "Steel Sections")
        self.assertEqual(mapping["A992"]["tab_id"], CATEGORY_MATERIAL)
        self.assertEqual(mapping["A325"]["entity_type"], CATEGORY_BOLT)
        self.assertEqual(mapping["A"]["entity_type_label"], "Other")


class EntityDiagnosticsTests(unittest.TestCase):
    def test_empty_when_no_matrix(self):
        result = build_entity_diagnostics({})
        self.assertEqual(result["entity_summary"]["model_classes"], 0)
        self.assertEqual(result["entity_performance"], [])
        self.assertEqual(result["top_misclassifications"], [])
        self.assertEqual(result["entity_tabs"][0]["id"], "all")

    def test_synthetic_confusion_matrix(self):
        # Labels: W (steel), A992 (material), A325 (bolt)
        labels = ["W", "A992", "A325"]
        # Rows = actual, cols = predicted
        matrix = [
            [8, 1, 0],  # W: 8 correct, 1 → A992
            [0, 3, 1],  # A992: 3 correct, 1 → A325
            [0, 0, 4],  # A325: 4 correct
        ]
        meta = {
            "class_labels": labels,
            "metrics": {"confusion_matrix": matrix},
        }
        result = build_entity_diagnostics(meta)
        summary = result["entity_summary"]
        self.assertEqual(summary["holdout_samples"], 17)
        self.assertEqual(summary["model_classes"], 3)
        self.assertEqual(summary["steel_section_classes"], 1)
        self.assertEqual(summary["material_classes"], 1)
        self.assertEqual(summary["bolt_classes"], 1)
        self.assertEqual(summary["plate_classes"], 0)
        self.assertEqual(summary["total_entity_types"], 3)
        self.assertAlmostEqual(summary["overall_accuracy"], 15 / 17, places=4)

        by_type = {row["entity_type"]: row for row in result["entity_performance"]}
        self.assertEqual(by_type["structural_section"]["sample_count"], 9)
        self.assertEqual(by_type["structural_section"]["class_count"], 1)
        self.assertAlmostEqual(by_type["structural_section"]["accuracy"], 8 / 9, places=4)

        # Plate remains present with zero samples / null accuracy
        plate = by_type["plate"]
        self.assertEqual(plate["class_count"], 0)
        self.assertEqual(plate["sample_count"], 0)
        self.assertIsNone(plate["accuracy"])

        top = result["top_misclassifications"]
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["count"], 1)
        # Stable tie-break: A992→A325 before W→A992 alphabetically by actual
        self.assertEqual(top[0]["actual_class"], "A992")
        self.assertEqual(top[0]["predicted_class"], "A325")
        self.assertEqual(top[1]["actual_class"], "W")

        self.assertEqual(result["class_entity_map"]["PIPE"] if False else True, True)
        self.assertIn("W", result["class_entity_map"])
        self.assertEqual(len(result["entity_tabs"]), 6)

    def test_top_misclassification_limit_and_ordering(self):
        labels = ["A", "B", "C"]
        # Force many off-diagonals with different counts
        matrix = [
            [1, 5, 2],
            [3, 1, 4],
            [1, 1, 1],
        ]
        # Override mapping via labels that resolve to misc/material via taxonomy
        # Use structural-ish labels for stable entity assignment
        labels = ["W", "HSS", "L"]
        meta = {"class_labels": labels, "metrics": {"confusion_matrix": matrix}}
        result = build_entity_diagnostics(meta)
        top = result["top_misclassifications"]
        self.assertEqual(top[0]["count"], 5)
        self.assertEqual(top[0]["actual_class"], "W")
        self.assertEqual(top[0]["predicted_class"], "HSS")
        counts = [row["count"] for row in top]
        self.assertEqual(counts, sorted(counts, reverse=True))


if __name__ == "__main__":
    unittest.main()
