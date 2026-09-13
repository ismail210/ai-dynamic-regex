"""Accuracy Track A1 — missing_thickness stays on compilation predictions."""

from __future__ import annotations

import unittest

from services.engineering.context_scope import partition_takeoff


def _restore_abstentions(predictions, excluded):
    """Mirror multimodal.pipeline post-partition restore (A1)."""

    abstained = [
        item
        for item in excluded
        if str(item.get("completion_status") or "") == "missing_thickness"
        and item.get("object_scope") != "non_member_dimension"
    ]
    if not abstained:
        return predictions, excluded
    kept_ids = {id(item) for item in abstained}
    return list(predictions) + abstained, [
        item for item in excluded if id(item) not in kept_ids
    ]


class CompilationSurfacePartitionTests(unittest.TestCase):
    def test_missing_thickness_restored_to_predictions(self):
        items = [
            {
                "object_id": "ok",
                "raw_text": "W16X26",
                "takeoff_eligible": True,
                "completion_status": "complete",
            },
            {
                "object_id": "inc",
                "raw_text": "L4X4",
                "takeoff_eligible": False,
                "completion_status": "missing_thickness",
                "object_scope": "member",
            },
            {
                "object_id": "leg",
                "raw_text": "ABBREV",
                "takeoff_eligible": False,
                "completion_status": "complete",
                "object_scope": "context_definition",
            },
        ]
        takeoff, excluded = partition_takeoff(items)
        surface, context = _restore_abstentions(takeoff, excluded)
        ids = {item["object_id"] for item in surface}
        self.assertIn("ok", ids)
        self.assertIn("inc", ids)
        self.assertNotIn("leg", ids)
        incomplete = next(item for item in surface if item["object_id"] == "inc")
        self.assertFalse(incomplete["takeoff_eligible"])
        self.assertEqual(incomplete["completion_status"], "missing_thickness")


if __name__ == "__main__":
    unittest.main()
