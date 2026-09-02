"""The CV encoder only runs when the index can produce member roles.

A section-labelled (schema 1.0) index resolves every crop to role ``other``,
so encoding against it dominates analyze wall-clock while returning a
constant. These tests pin the gate that skips it.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import joblib
import numpy as np

from services.multimodal import geometry_ai


def _write_index(path: Path, payload: dict) -> None:
    joblib.dump(payload, path)


def _legacy_payload(count: int = 4) -> dict:
    return {
        "schema_version": "1.0",
        "encoder": "mobilenet_v3_small_imagenet",
        "embedding_dimension": 128,
        "embeddings": np.ones((count, 128), dtype=np.float32),
        "labels": ["W10X15", "HSS6X6X3/8", "W12X19", "L4X4X1/4"][:count],
    }


def _role_payload(count: int = 4) -> dict:
    roles = ["beam", "column", "brace", "plate"][:count]
    orientations = ["horizontal", "vertical", "diagonal", "horizontal"][:count]
    return {
        "schema_version": "2.0",
        "encoder": "mobilenet_v3_small_imagenet",
        "embedding_dimension": 128,
        "embeddings": np.ones((count, 128), dtype=np.float32),
        "labels": [
            f"{role}:{orientation}"
            for role, orientation in zip(roles, orientations)
        ],
        "roles": roles,
        "orientations": orientations,
    }


class GeometryIndexGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.index_path = Path(self._tempdir.name) / "geometry_index.joblib"
        patcher = mock.patch.object(
            geometry_ai,
            "settings",
            SimpleNamespace(geometry_embedding_index_path=self.index_path),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        geometry_ai.reset_index_cache()
        self.addCleanup(geometry_ai.reset_index_cache)
        self._tempdir_cleanup = self._tempdir.cleanup
        self.addCleanup(self._tempdir_cleanup)

    def test_legacy_section_index_is_rejected(self) -> None:
        _write_index(self.index_path, _legacy_payload())
        self.assertIsNone(geometry_ai._load_index())
        self.assertFalse(geometry_ai.geometry_index_ready())

    def test_role_labelled_index_is_accepted(self) -> None:
        _write_index(self.index_path, _role_payload())
        self.assertIsNotNone(geometry_ai._load_index())
        self.assertTrue(geometry_ai.geometry_index_ready())

    def test_missing_index_is_not_ready(self) -> None:
        self.assertFalse(geometry_ai.geometry_index_ready())

    def test_legacy_index_skips_encoding_entirely(self) -> None:
        _write_index(self.index_path, _legacy_payload())
        geometry = {
            "objects": [
                {"bbox": [0.0, 0.0, 40.0, 4.0], "page_number": 1}
                for _ in range(25)
            ]
        }
        with mock.patch.object(
            geometry_ai, "encode_images", side_effect=AssertionError
        ) as encoder:
            enriched = geometry_ai.enrich_geometry_embeddings(
                "unused.pdf", geometry
            )
        encoder.assert_not_called()
        report = enriched["geometry_ai"]
        self.assertFalse(report["available"])
        self.assertEqual(report["fallback"], "vector_geometry")
        self.assertEqual(report["skipped_objects"], 25)
        self.assertIn("schema 1.0", report["reason"])

    def test_skipped_objects_keep_no_embedding(self) -> None:
        """Fusion falls back to proximity only while the embedding is absent."""

        _write_index(self.index_path, _legacy_payload())
        objects = [{"bbox": [0.0, 0.0, 40.0, 4.0], "page_number": 1}]
        geometry_ai.enrich_geometry_embeddings("unused.pdf", {"objects": objects})
        self.assertNotIn("geometry_embedding", objects[0])
        self.assertNotIn("geometry_role", objects[0])


if __name__ == "__main__":
    unittest.main()
