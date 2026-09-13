"""GHX geometry evidence adapter tests, independent of live Rhino.Compute
(Section 43) -- everything here runs against a fixture-shaped capture dict.
"""
from __future__ import annotations

import unittest

from services.semantic.models import GeometryProvider
from services.semantic_preprocessor.geometry_evidence import (
    GrasshopperGeometryEvidenceProvider,
    NullGeometryEvidenceProvider,
)


def _capture(**overrides):
    base = {
        "source_definition_sha256": "35d5bb06...",
        "sheet": "S-101",
        "RH_OUT:BeamCrv": [
            {"element_id": "e1", "points": [[0, 0], [10, 0]], "length": 10.0},
            {"points": [[20, 0], [30, 0]], "length": 10.0},  # no stable id -> fingerprint
        ],
    }
    base.update(overrides)
    return base


class StableIdentityTests(unittest.TestCase):
    def test_beam_element_id_is_retained_as_source_id(self):
        provider = GrasshopperGeometryEvidenceProvider(_capture())
        evidence = provider.extract_geometry({})
        with_id = [e for e in evidence if e.source_geometry_id == "e1"]
        self.assertEqual(len(with_id), 1)
        self.assertEqual(with_id[0].geometry_id, "geom_ghx_e1")

    def test_missing_stable_id_gets_deterministic_fingerprint(self):
        provider = GrasshopperGeometryEvidenceProvider(_capture())
        evidence = provider.extract_geometry({})
        no_id = [e for e in evidence if e.source_geometry_id is None]
        self.assertEqual(len(no_id), 1)
        self.assertTrue(no_id[0].geometry_id.startswith("geom_"))

    def test_same_geometry_same_run_produces_same_id(self):
        provider_a = GrasshopperGeometryEvidenceProvider(_capture())
        provider_b = GrasshopperGeometryEvidenceProvider(_capture())
        ids_a = sorted(e.geometry_id for e in provider_a.extract_geometry({}))
        ids_b = sorted(e.geometry_id for e in provider_b.extract_geometry({}))
        self.assertEqual(ids_a, ids_b)

    def test_different_list_order_does_not_change_identity(self):
        capture = _capture()
        reordered = dict(capture)
        reordered["RH_OUT:BeamCrv"] = list(reversed(capture["RH_OUT:BeamCrv"]))
        ids_original = sorted(
            e.geometry_id for e in GrasshopperGeometryEvidenceProvider(capture).extract_geometry({})
        )
        ids_reordered = sorted(
            e.geometry_id for e in GrasshopperGeometryEvidenceProvider(reordered).extract_geometry({})
        )
        self.assertEqual(ids_original, ids_reordered)


class ProvenanceTests(unittest.TestCase):
    def test_evidence_carries_source_and_output_provenance(self):
        provider = GrasshopperGeometryEvidenceProvider(_capture())
        evidence = provider.extract_geometry({})
        for e in evidence:
            self.assertEqual(e.provider, GeometryProvider.GRASSHOPPER)
            self.assertEqual(e.source_output, "RH_OUT:BeamCrv")
            self.assertIn("rh_out", e.metadata["provenance"])


class MissingServiceTests(unittest.TestCase):
    def test_null_provider_returns_empty_without_error(self):
        provider = NullGeometryEvidenceProvider()
        self.assertEqual(provider.extract_geometry({}), [])


class UnpairedTextTests(unittest.TestCase):
    def test_no_pairing_data_returns_empty_not_fabricated(self):
        provider = GrasshopperGeometryEvidenceProvider(_capture())
        self.assertEqual(provider.paired_text_for("RH_OUT:BeamCrv"), [])


if __name__ == "__main__":
    unittest.main()
