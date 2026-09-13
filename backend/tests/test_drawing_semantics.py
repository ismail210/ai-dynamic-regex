"""Accuracy Track A8 — drawing_semantics.json read-model emitter."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.prediction.drawing_semantics import (
    DRAWING_SEMANTICS_SCHEMA,
    build_drawing_semantics,
    validate_drawing_semantics,
    write_drawing_semantics,
)


class DrawingSemanticsTests(unittest.TestCase):
    def test_build_includes_predictions_and_context(self):
        payload = build_drawing_semantics(
            document_id="doc_test",
            source_file="test.pdf",
            predictions=[
                {
                    "object_id": "p1",
                    "raw_text": "W16X26",
                    "normalized_text": "W16X26",
                    "section": "W16X26",
                    "completion_status": "complete",
                    "takeoff_eligible": True,
                }
            ],
            context_definitions=[
                {
                    "object_id": "c1",
                    "raw_text": "L4X4",
                    "normalized_text": "L4X4",
                    "completion_status": "missing_thickness",
                    "takeoff_eligible": False,
                    "object_scope": "context_definition",
                }
            ],
        )
        self.assertEqual(payload["schema"], DRAWING_SEMANTICS_SCHEMA)
        self.assertEqual(payload["annotation_count"], 2)
        self.assertEqual(validate_drawing_semantics(payload), [])
        self.assertFalse(payload["policy"]["incomplete_l_auto_complete"])

    def test_validate_rejects_bad_schema(self):
        errors = validate_drawing_semantics({"schema": "nope", "annotations": []})
        self.assertIn("missing_or_wrong_schema", errors)
        self.assertIn("missing_document_id", errors)

    def test_write_roundtrip(self):
        payload = build_drawing_semantics(
            document_id="doc_x",
            source_file="x.pdf",
            predictions=[
                {
                    "raw_text": "HSS6X6X3/8",
                    "normalized_text": "HSS6X6X3/8",
                    "completion_status": "complete",
                }
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write_drawing_semantics(Path(tmp) / "drawing_semantics.json", payload)
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn("drawing_semantics_v2", text)


if __name__ == "__main__":
    unittest.main()
