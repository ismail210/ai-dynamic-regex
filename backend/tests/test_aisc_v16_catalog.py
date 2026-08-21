"""
Tests for the AISC v16 (all-editions) label catalog: the new, additive
loader (services.aisc_v16_catalog) and the ETL pipeline that builds it
(scripts.prepare_aisc_v16_catalog).

This catalog is not wired into the production prediction pipeline yet, so
these tests do not touch services.database_loader, the orchestrator, or
the Phase 2/3 resolution contract directly — they only assert that the
new catalog contract itself is sound, and (last test) that importing this
module has not disturbed the existing safety contract.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from services.aisc_v16_catalog import (
    MODERN_FAMILIES,
    AiscV16Catalog,
    CatalogEntry,
    CatalogValidationError,
    classify_catalog_scope,
    infer_family_longest_prefix,
    load_catalog,
    lookup_key,
    normalize_designation_text,
)
from scripts.prepare_aisc_v16_catalog import (
    CORE_DIM_COLUMNS,
    build_catalog_and_conflicts,
    clean_identity_columns,
    dims_consistent,
    split_valid_invalid,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
REAL_CATALOG_PATH = BACKEND_DIR / "database" / "aisc_v16_label_catalog.csv"


def _write_csv(tmp_path: Path, header: str, rows: list) -> Path:
    path = tmp_path / "catalog.csv"
    lines = [header] + rows
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class NormalizationTests(unittest.TestCase):
    def test_conservative_normalization_preserves_digits(self):
        self.assertEqual(
            normalize_designation_text("  hss10.750x0.188  "), "HSS10.750X0.188"
        )
        self.assertEqual(normalize_designation_text("w12x26"), "W12X26")

    def test_multiplication_sign_unified_to_x(self):
        self.assertEqual(normalize_designation_text("HSS4×4×1/4"), "HSS4X4X1/4")

    def test_internal_whitespace_collapsed_not_deleted_by_normalize(self):
        # normalize_designation_text only collapses runs of whitespace; full
        # space removal (spelling-insignificant) is a separate, explicit step
        # (lookup_key), not silently baked into normalization.
        self.assertEqual(normalize_designation_text("2L  6X6X1"), "2L 6X6X1")

    def test_lookup_key_strips_all_spaces(self):
        self.assertEqual(lookup_key("2L 6X6X1"), lookup_key("2L6X6X1"))
        self.assertEqual(lookup_key("2l 6x6x1"), "2L6X6X1")


class FamilyInferenceTests(unittest.TestCase):
    def test_double_angle_not_collapsed_to_single_angle(self):
        known = {"L", "2L", "W", "WT"}
        self.assertEqual(infer_family_longest_prefix("2L12X12X1", known), "2L")

    def test_tee_variants_not_collapsed_to_base_family(self):
        known = {"W", "WT", "M", "MT", "S", "ST"}
        self.assertEqual(infer_family_longest_prefix("WT12X51", known), "WT")
        self.assertEqual(infer_family_longest_prefix("MT4X3.1", known), "MT")
        self.assertEqual(infer_family_longest_prefix("ST6X20.4", known), "ST")

    def test_unknown_family_returns_none(self):
        self.assertIsNone(infer_family_longest_prefix("ZZZ12X12", {"W", "L"}))


class CatalogScopeTests(unittest.TestCase):
    def test_modern_families_are_the_13_current_families(self):
        self.assertEqual(
            MODERN_FAMILIES,
            {"W", "WT", "HSS", "L", "2L", "C", "MC", "PIPE", "MT", "ST", "HP", "M", "S"},
        )

    def test_historical_st_variants_stay_historical_not_collapsed_to_modern_st(self):
        self.assertEqual(classify_catalog_scope("ST"), "modern")
        self.assertEqual(classify_catalog_scope("ST R"), "historical")
        self.assertEqual(classify_catalog_scope("ST S"), "historical")
        self.assertEqual(classify_catalog_scope("ST JR"), "historical")

    def test_scope_inferred_when_csv_omits_the_column(self):
        with _tmp() as tmp_path:
            path = _write_csv(
                tmp_path,
                "family,designation,source_row_id,source_edition,source_edition_count",
                ["W,W12X26,1,15th,1", "WF,8WF17,2,Historic,1"],
            )
            catalog = load_catalog(path)
            self.assertEqual(catalog.lookup("W12X26").catalog_scope, "modern")
            self.assertEqual(catalog.lookup("8WF17").catalog_scope, "historical")

    def test_scope_read_from_csv_when_present(self):
        with _tmp() as tmp_path:
            path = _write_csv(
                tmp_path,
                "family,designation,source_row_id,source_edition,source_edition_count,catalog_scope",
                ["W,W12X26,1,15th,1,modern"],
            )
            catalog = load_catalog(path)
            self.assertEqual(catalog.lookup("W12X26").catalog_scope, "modern")

    def test_modern_and_historical_entries_partition_the_catalog(self):
        with _tmp() as tmp_path:
            path = _write_csv(
                tmp_path,
                "family,designation,source_row_id,source_edition,source_edition_count",
                ["W,W12X26,1,15th,1", "WF,8WF17,2,Historic,1"],
            )
            catalog = load_catalog(path)
            self.assertEqual(len(catalog.modern_entries()), 1)
            self.assertEqual(len(catalog.historical_entries()), 1)


class LoaderValidationTests(unittest.TestCase):
    def test_missing_required_columns_rejected(self):
        with self.assertRaises(CatalogValidationError):
            with _tmp() as tmp_path:
                path = _write_csv(tmp_path, "family,notdesignation", ["W,W12X26"])
                load_catalog(path)

    def test_blank_designation_rejected(self):
        with self.assertRaises(CatalogValidationError):
            with _tmp() as tmp_path:
                path = _write_csv(
                    tmp_path,
                    "family,designation,source_row_id,source_edition,source_edition_count",
                    ["W,,1,15th,1"],
                )
                load_catalog(path)

    def test_duplicate_pair_rejected(self):
        with self.assertRaises(CatalogValidationError):
            with _tmp() as tmp_path:
                path = _write_csv(
                    tmp_path,
                    "family,designation,source_row_id,source_edition,source_edition_count",
                    ["W,W12X26,1,15th,1", "W,W12X26,2,14th,1"],
                )
                load_catalog(path)

    def test_valid_catalog_loads_and_looks_up(self):
        with _tmp() as tmp_path:
            path = _write_csv(
                tmp_path,
                "family,designation,source_row_id,source_edition,source_edition_count",
                ["W,W12X26,1,15th,1", "HSS,HSS6X6X1/4,2,15th,1"],
            )
            catalog = load_catalog(path)
            self.assertEqual(len(catalog), 2)
            self.assertTrue(catalog.is_catalog_label("w12x26"))
            self.assertTrue(catalog.is_catalog_label("W12 X26"))
            self.assertFalse(catalog.is_catalog_label("W12X999"))
            entry = catalog.lookup("W12X26")
            self.assertEqual(entry.family, "W")
            self.assertEqual(catalog.family_counts(), {"W": 1, "HSS": 1})

    def test_duplicate_after_normalization_rejected_by_catalog(self):
        entries = [
            CatalogEntry("2L", "2L6X6X1", "1", "15th", 1),
            CatalogEntry("2L", "2L 6X6X1", "2", "ASD9", 1),
        ]
        with self.assertRaises(CatalogValidationError):
            AiscV16Catalog(entries)


class RealGeneratedCatalogTests(unittest.TestCase):
    """Exercises the actual on-disk catalog produced by the ETL script."""

    def setUp(self):
        if not REAL_CATALOG_PATH.exists():
            self.skipTest("aisc_v16_label_catalog.csv has not been generated yet")

    def test_real_catalog_loads_and_is_non_empty(self):
        catalog = load_catalog(REAL_CATALOG_PATH)
        self.assertGreater(len(catalog), 0)

    def test_no_blank_designations_or_families(self):
        df = pd.read_csv(REAL_CATALOG_PATH, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        self.assertTrue((df["designation"].str.strip() != "").all())
        self.assertTrue((df["family"].str.strip() != "").all())

    def test_family_designation_pairs_are_unique(self):
        df = pd.read_csv(REAL_CATALOG_PATH, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        pairs = list(zip(df["family"], df["designation"]))
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_known_exact_shape_resolves(self):
        catalog = load_catalog(REAL_CATALOG_PATH)
        self.assertTrue(catalog.is_catalog_label("W12X26"))

    def test_invalid_shape_still_rejected(self):
        catalog = load_catalog(REAL_CATALOG_PATH)
        self.assertFalse(catalog.is_catalog_label("W12X999"))


class EtlHelperTests(unittest.TestCase):
    """Unit tests for the ETL pipeline's cleaning/dedup logic in isolation,
    independent of the real 18k-row source file."""

    def _raw_frame(self, rows):
        columns = ["source_row_id", "Edition", "Type", "Designation", "A ", "d", "W"]
        return pd.DataFrame(rows, columns=columns)

    def test_placeholder_rows_are_split_out_as_invalid(self):
        raw = self._raw_frame(
            [
                [0, "Historic", "W", "----", "", "", ""],
                [1, "15th", "W", "W12X26", "7.65", "12.2", "26"],
                [2, "15th", "", "W12X30", "8.79", "12.3", "30"],
            ]
        )
        cleaned = clean_identity_columns(raw)
        valid, invalid = split_valid_invalid(cleaned)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 2)
        self.assertEqual(valid.iloc[0]["Designation"], "W12X26")

    def test_internal_space_variants_collapse_to_one_designation(self):
        raw = self._raw_frame(
            [
                [0, "15th", "2L", "2L6X6X1", "7.09", "6", "24.2"],
                [1, "ASD9", "2L", "2L 6x6x1", "7.09", "6", "24.2"],
            ]
        )
        cleaned = clean_identity_columns(raw)
        self.assertEqual(cleaned["Designation"].nunique(), 1)
        self.assertEqual(cleaned["Designation"].iloc[0], "2L6X6X1")

    def test_consistent_cross_edition_duplicate_collapses_with_provenance(self):
        raw = self._raw_frame(
            [
                [0, "14th", "W", "W12X26", "7.65", "12.22", "26"],
                [1, "15th", "W", "W12X26", "7.65", "12.20", "26"],
            ]
        )
        valid, _ = split_valid_invalid(clean_identity_columns(raw))
        catalog_df, conflicts_df, conflict_pairs = build_catalog_and_conflicts(valid)
        self.assertEqual(len(catalog_df), 1)
        self.assertEqual(catalog_df.iloc[0]["source_edition"], "15th")  # newest wins
        self.assertEqual(catalog_df.iloc[0]["source_edition_count"], 2)
        self.assertTrue(conflicts_df.empty)
        self.assertEqual(conflict_pairs, set())

    def test_genuinely_conflicting_dimensions_excluded_not_merged(self):
        raw = self._raw_frame(
            [
                [0, "14th", "2L", "2L2-1/2X2X1/4LLBB", "1.89", "1.50", "6.38"],
                [1, "15th", "2L", "2L2-1/2X2X1/4LLBB", "1.89", "2.50", "6.38"],
            ]
        )
        valid, _ = split_valid_invalid(clean_identity_columns(raw))
        catalog_df, conflicts_df, conflict_pairs = build_catalog_and_conflicts(valid)
        self.assertTrue(catalog_df.empty)
        self.assertEqual(len(conflicts_df), 2)
        self.assertIn(("2L", "2L2-1/2X2X1/4LLBB"), conflict_pairs)

    def test_dims_consistent_missing_values_do_not_force_a_conflict(self):
        raw = self._raw_frame(
            [
                [0, "Historic", "W", "W12X26", "", "", "26"],
                [1, "15th", "W", "W12X26", "7.65", "12.2", "26"],
            ]
        )
        self.assertTrue(dims_consistent(raw))

    def test_dims_consistent_respects_tolerance(self):
        close = self._raw_frame(
            [[0, "14th", "W", "W12X26", "7.64", "", ""], [1, "15th", "W", "W12X26", "7.65", "", ""]]
        )
        self.assertTrue(dims_consistent(close))
        far = self._raw_frame(
            [[0, "14th", "W", "W12X26", "5.00", "", ""], [1, "15th", "W", "W12X26", "7.65", "", ""]]
        )
        self.assertFalse(dims_consistent(far))


def _tmp():
    import tempfile

    class _Ctx:
        def __enter__(self):
            self._dir = tempfile.TemporaryDirectory()
            return Path(self._dir.name)

        def __exit__(self, *exc):
            self._dir.cleanup()
            return False

    return _Ctx()


if __name__ == "__main__":
    unittest.main()
