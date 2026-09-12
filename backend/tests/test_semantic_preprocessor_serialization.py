"""drawing_semantics.json sidecar serialization tests (Section 38/46)."""
from __future__ import annotations

import json
import unittest

from services.semantic_preprocessor.models import TextPrimitive
from services.semantic_preprocessor.pipeline import process_primitives
from services.semantic_preprocessor.serialization import to_dict, to_json


class RoundTripTests(unittest.TestCase):
    def test_json_round_trip_matches_to_dict(self):
        primitives = [
            TextPrimitive(primitive_id="p1", page=1, text="HSS 8X8X0.375", bbox=[0, 0, 60, 10], font_size=10.0),
        ]
        document = process_primitives(primitives, document_id="doc1")
        as_dict = to_dict(document)
        round_tripped = json.loads(to_json(document))
        self.assertEqual(as_dict, round_tripped)

    def test_schema_version_present(self):
        document = process_primitives([], document_id="doc1")
        payload = to_dict(document)
        self.assertIn("schema_version", payload)
        self.assertTrue(payload["schema_version"])


if __name__ == "__main__":
    unittest.main()
