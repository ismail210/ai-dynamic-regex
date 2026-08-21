"""
Tests for the offline catalog-swap capability added to
services.database_loader (reload_from_pairs / reload_from_aisc_v16_catalog /
reset_to_default), needed so training/eval scripts can point candidate
generation at the larger AISC v16 catalog without changing what the live
prediction path loads (still settings.database_file/database_sheet, the
2,299-row XLSX, at import time).

Every test restores the default catalog in tearDown — this module's state is
process-global, and other test files assume the production catalog is loaded.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from services import database_loader

REAL_V16_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent / "database" / "aisc_v16_label_catalog.csv"
)


class CatalogReloadTests(unittest.TestCase):
    def setUp(self):
        self._default_snapshot = database_loader.catalog_version()

    def tearDown(self):
        database_loader.reset_to_default()

    def test_production_catalog_loaded_by_default(self):
        self.assertIn("aisc-shapes-database-v160-2.xlsx", database_loader.catalog_version())
        self.assertTrue(database_loader.is_catalog_label("W12X26"))

    def test_reload_from_pairs_swaps_lookup(self):
        database_loader.reload_from_pairs(
            [("W12X26", "W"), ("HSS6X6X1/4", "HSS")], source="unit-test-pairs"
        )
        self.assertEqual(database_loader.catalog_version(), "unit-test-pairs")
        self.assertTrue(database_loader.is_catalog_label("W12X26"))
        self.assertFalse(database_loader.is_catalog_label("W44X335"))  # in old catalog, not this one

    def test_reload_rejects_empty_pairs(self):
        with self.assertRaises(ValueError):
            database_loader.reload_from_pairs([], source="empty")

    def test_reset_to_default_restores_production_catalog(self):
        database_loader.reload_from_pairs([("W12X26", "W")], source="unit-test-pairs")
        self.assertFalse(database_loader.is_catalog_label("W44X335"))
        database_loader.reset_to_default()
        self.assertEqual(database_loader.catalog_version(), self._default_snapshot)
        self.assertTrue(database_loader.is_catalog_label("W44X335"))

    def test_similarity_cache_invalidated_across_reload(self):
        # Prime the lru_cache against the default catalog, then reload to a
        # catalog that must not still answer from stale cached candidates.
        database_loader.search_similar_shapes("W12X26")
        database_loader.reload_from_pairs([("HSS6X6X1/4", "HSS")], source="unit-test-pairs")
        results = database_loader.search_similar_shapes("W12X26", minimum_score=0.1)
        self.assertTrue(all(r["shape"] == "HSS6X6X1/4" for r in results))

    def test_reload_from_aisc_v16_catalog_full(self):
        if not REAL_V16_CATALOG_PATH.exists():
            self.skipTest("aisc_v16_label_catalog.csv not generated yet")
        catalog = database_loader.reload_from_aisc_v16_catalog(REAL_V16_CATALOG_PATH)
        self.assertGreater(len(catalog), 3000)
        self.assertTrue(database_loader.is_catalog_label("W12X26"))
        self.assertIn("aisc_v16_label_catalog.csv", database_loader.catalog_version())

    def test_reload_from_aisc_v16_catalog_modern_scope_only(self):
        if not REAL_V16_CATALOG_PATH.exists():
            self.skipTest("aisc_v16_label_catalog.csv not generated yet")
        database_loader.reload_from_aisc_v16_catalog(REAL_V16_CATALOG_PATH, scope="modern")
        self.assertIn("[modern]", database_loader.catalog_version())
        loaded_types = {t for _label, t in database_loader.catalog_entries()}
        modern_families = {"W", "WT", "HSS", "L", "2L", "C", "MC", "PIPE", "MT", "ST", "HP", "M", "S"}
        self.assertTrue(loaded_types.issubset(modern_families))


if __name__ == "__main__":
    unittest.main()
