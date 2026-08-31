"""
Prepare the AISC v16 (all-editions) label catalog from the raw shapes CSV.

Reads ``database/aisc-shapes-database-v160h(Database v16.csv`` (18,879 rows,
142 columns, spanning 12 historical AISC manual editions: Historic, ASD5-9,
LRFD1-3, 13th, 14th, 15th) and produces:

  - database/aisc_v16_full_clean.csv
        Full source table, conservatively cleaned, all editions kept.
        Only genuinely invalid/placeholder rows (blank or "----" designation
        or type) are removed.
  - database/aisc_v16_label_catalog.csv
        Minimal canonical family/designation catalog: one row per
        (family, designation) pair found consistent across every edition
        that recorded it, with provenance back to the source row.
  - database/aisc_v16_label_catalog_conflicts.csv
        (family, designation) pairs where core dimensions (A, d, W)
        disagree across editions/rows by more than the tolerance — excluded
        from the canonical catalog and reported here instead of silently
        merged or discarded.
  - database/reports/aisc_v16_dataset_audit.md
        Full audit report (families found, cleaning performed, duplicate/
        conflict resolution, family cross-check, designation-quality/parser
        compatibility, and comparison against the old 2,299-shape catalog).

Cleaning is conservative: whitespace/multiplication-sign/casing
normalization only. No digit is ever changed, guessed, or repaired, and no
row is merged or dropped on the basis of "looks similar" — we are cleaning
ground truth, not performing OCR correction.

This script does not train, tune, or touch any model, threshold, or the
production catalog (``config.settings.database_file``). It only produces
the derived files listed above.

Run: python backend/scripts/prepare_aisc_v16_catalog.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.aisc_v16_catalog import (  # noqa: E402
    MODERN_FAMILIES,
    classify_catalog_scope,
    infer_family_longest_prefix,
    load_catalog,
    lookup_key,
    normalize_designation_text,
)
from services.structural_parser import parse_section  # noqa: E402
from services.wildcard_matcher import _FAMILY_PREFIXES  # noqa: E402

DATABASE_DIR = BACKEND_DIR / "database"
RAW_CSV = DATABASE_DIR / "aisc-shapes-database-v160h(Database v16.csv"
OLD_XLSX = DATABASE_DIR / "aisc-shapes-database-v160-2.xlsx"
OLD_XLSX_SHEET = "Database v16.0"

OUT_FULL_CLEAN = DATABASE_DIR / "aisc_v16_full_clean.csv"
OUT_CATALOG = DATABASE_DIR / "aisc_v16_label_catalog.csv"
OUT_CONFLICTS = DATABASE_DIR / "aisc_v16_label_catalog_conflicts.csv"
REPORTS_DIR = DATABASE_DIR / "reports"
OUT_REPORT = REPORTS_DIR / "aisc_v16_dataset_audit.md"

# Newest published manual wins as the retained provenance row when several
# editions agree on the same (family, designation, dimensions).
EDITION_RECENCY = [
    "15th", "14th", "13th", "LRFD3", "LRFD2", "LRFD1",
    "ASD9", "ASD8", "ASD7", "ASD6", "ASD5", "Historic",
]
EDITION_RANK = {edition: rank for rank, edition in enumerate(EDITION_RECENCY)}

CORE_DIM_COLUMNS = ["A ", "d", "W"]
DIM_TOLERANCE = 0.02  # 2% relative tolerance across editions/printings

PLACEHOLDER_DESIGNATIONS = {"", "----", "-", "--", "—", "–"}


def _to_float(value):
    text = str(value).strip()
    if not text or text in PLACEHOLDER_DESIGNATIONS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(
        RAW_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False, low_memory=False
    )
    df.insert(0, "source_row_id", range(len(df)))
    return df


def clean_identity_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Edition is a categorical source label ("15th", "LRFD3", ...), not OCR
    # text to normalize for matching — only trim stray whitespace so its
    # spelling (and case) stays exactly as published, matching
    # EDITION_RECENCY below.
    df["Edition"] = df["Edition"].astype(str).str.strip()
    for column in ("Type", "Designation"):
        df[column] = df[column].map(normalize_designation_text)
    # Older editions (ASD7-ASD9, LRFD1) sometimes write a space between the
    # family code and the dimensions (e.g. "2L 6X6X1") where newer editions
    # don't ("2L6X6X1"). Space is not dimensionally meaningful and is
    # already treated as insignificant everywhere else in this codebase
    # (services.database_loader strips all spaces for its lookup key), so
    # the canonical designation is stored space-stripped too. This is
    # spelling normalization, not a numeric change.
    df["Designation"] = df["Designation"].str.replace(" ", "", regex=False)
    return df


def split_valid_invalid(df: pd.DataFrame):
    designation_blank = df["Designation"].isin(PLACEHOLDER_DESIGNATIONS)
    type_blank = df["Type"].isin(PLACEHOLDER_DESIGNATIONS)
    invalid_mask = designation_blank | type_blank
    return df.loc[~invalid_mask].copy(), df.loc[invalid_mask].copy()


def dims_consistent(rows: pd.DataFrame) -> bool:
    """True when every non-missing core-dimension value agrees within
    DIM_TOLERANCE across all rows in the group. Groups with insufficient
    numeric data to compare are treated as consistent (an exact
    Type+Designation string match is already strong evidence)."""

    for column in CORE_DIM_COLUMNS:
        if column not in rows.columns:
            continue
        values = [v for v in (_to_float(x) for x in rows[column]) if v is not None]
        if len(values) <= 1:
            continue
        lo, hi = min(values), max(values)
        if lo == 0:
            if hi != 0:
                return False
            continue
        if (hi - lo) / abs(lo) > DIM_TOLERANCE:
            return False
    return True


def build_catalog_and_conflicts(valid_df: pd.DataFrame):
    catalog_rows = []
    conflict_rows = []

    for (family, designation), rows in valid_df.groupby(
        ["Type", "Designation"], sort=False
    ):
        editions = sorted(rows["Edition"].unique().tolist())
        if dims_consistent(rows):
            ranks = rows["Edition"].map(lambda e: EDITION_RANK.get(e, len(EDITION_RANK)))
            best = rows.loc[ranks.idxmin()]
            catalog_rows.append(
                {
                    "family": family,
                    "designation": designation,
                    "source_row_id": best["source_row_id"],
                    "source_edition": best["Edition"],
                    "source_edition_count": len(editions),
                }
            )
        else:
            for _, row in rows.iterrows():
                record = {
                    "family": family,
                    "designation": designation,
                    "source_row_id": row["source_row_id"],
                    "source_edition": row["Edition"],
                }
                for column in CORE_DIM_COLUMNS:
                    record[column.strip()] = row.get(column, "")
                conflict_rows.append(record)

    catalog_df = pd.DataFrame(
        catalog_rows,
        columns=[
            "family",
            "designation",
            "source_row_id",
            "source_edition",
            "source_edition_count",
        ],
    )
    if not catalog_df.empty:
        catalog_df["catalog_scope"] = catalog_df["family"].map(classify_catalog_scope)
        catalog_df = catalog_df.sort_values(["family", "designation"]).reset_index(drop=True)

    conflicts_df = pd.DataFrame(conflict_rows)
    if not conflicts_df.empty:
        conflicts_df = conflicts_df.sort_values(
            ["family", "designation", "source_edition"]
        ).reset_index(drop=True)

    conflict_pairs = {(r["family"], r["designation"]) for r in conflict_rows}
    return catalog_df, conflicts_df, conflict_pairs


def family_cross_check(catalog_df: pd.DataFrame, known_families: set):
    mismatches = []
    unmatched = []
    for _, row in catalog_df.iterrows():
        inferred = infer_family_longest_prefix(row["designation"], known_families)
        if inferred is None:
            unmatched.append((row["family"], row["designation"]))
        elif inferred != row["family"]:
            mismatches.append((row["family"], row["designation"], inferred))
    return mismatches, unmatched


_UNUSUAL_CHAR_RE = __import__("re").compile(r"[^A-Z0-9/.\-]")


def designation_quality_audit(catalog_df: pd.DataFrame):
    designations = catalog_df["designation"].tolist()
    lengths = [len(d) for d in designations]
    stats = {
        "count": len(designations),
        "min_len": min(lengths) if lengths else 0,
        "max_len": max(lengths) if lengths else 0,
        "mean_len": (sum(lengths) / len(lengths)) if lengths else 0.0,
        "contains_space": sum(1 for d in designations if " " in d),
        "contains_slash": sum(1 for d in designations if "/" in d),
        "contains_decimal": sum(1 for d in designations if "." in d),
        "contains_hyphen": sum(1 for d in designations if "-" in d),
        "contains_paren": sum(1 for d in designations if "(" in d or ")" in d),
        "contains_comma": sum(1 for d in designations if "," in d),
        "unusual_chars": sum(1 for d in designations if _UNUSUAL_CHAR_RE.search(d)),
    }

    parser_ok_full = 0
    parser_ok_partial = 0
    parser_unsupported = []
    for designation in designations:
        parsed = parse_section(designation)
        if parsed is None:
            parser_unsupported.append(designation)
        elif parsed.depth is not None and (
            parsed.family in {"HSS", "L", "2L", "PIPE"} or parsed.weight is not None
        ):
            parser_ok_full += 1
        else:
            parser_ok_partial += 1

    return stats, parser_ok_full, parser_ok_partial, parser_unsupported


def compare_against_old_catalog(catalog_df: pd.DataFrame):
    if not OLD_XLSX.exists():
        return None
    old_df = pd.read_excel(OLD_XLSX, sheet_name=OLD_XLSX_SHEET, dtype=str)
    old_labels = {
        lookup_key(x): x for x in old_df["AISC_Manual_Label"].astype(str)
    }
    old_types = old_df["Type"].astype(str).str.strip()
    old_family_counts = Counter(old_types.tolist())

    new_keys = {lookup_key(d) for d in catalog_df["designation"]}
    old_keys = set(old_labels)

    overlap = new_keys & old_keys
    newly_added = new_keys - old_keys
    old_missing_from_new = old_keys - new_keys

    new_family_counts = Counter(catalog_df["family"].tolist())

    return {
        "old_count": len(old_keys),
        "new_count": len(new_keys),
        "overlap": len(overlap),
        "newly_added": len(newly_added),
        "old_missing_from_new": len(old_missing_from_new),
        "old_family_counts": old_family_counts,
        "new_family_counts": new_family_counts,
        "old_missing_examples": sorted(old_labels[k] for k in old_missing_from_new)[:25],
    }


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    raw_df = load_raw()
    raw_rows, raw_cols = raw_df.shape

    cleaned_df = clean_identity_columns(raw_df)
    valid_df, invalid_df = split_valid_invalid(cleaned_df)

    valid_df.to_csv(OUT_FULL_CLEAN, index=False, encoding="utf-8-sig")

    editions_found = sorted(valid_df["Edition"].unique().tolist())
    raw_family_counts = Counter(valid_df["Type"].tolist())

    catalog_df, conflicts_df, conflict_pairs = build_catalog_and_conflicts(valid_df)
    catalog_df.to_csv(OUT_CATALOG, index=False, encoding="utf-8-sig")
    conflicts_df.to_csv(OUT_CONFLICTS, index=False, encoding="utf-8-sig")

    known_families = set(raw_family_counts)
    mismatches, unmatched = family_cross_check(catalog_df, known_families)

    dq_stats, parser_full, parser_partial, parser_unsupported = designation_quality_audit(
        catalog_df
    )

    old_comparison = compare_against_old_catalog(catalog_df)

    # Self-check: the catalog we just wrote must load cleanly through the
    # validated loader contract (fails loudly if it doesn't).
    loaded = load_catalog(OUT_CATALOG)
    assert len(loaded) == len(catalog_df), "catalog loader row count mismatch"

    modern_families = set(_FAMILY_PREFIXES)
    historic_families = known_families - modern_families

    lines = []
    lines.append("# AISC v16 dataset audit (all editions)\n")
    lines.append(f"Source: `{RAW_CSV.name}`\n")

    lines.append("## A. Raw dataset size\n")
    lines.append(f"- Raw rows: {raw_rows}\n- Raw columns: {raw_cols}\n")
    lines.append(f"- Editions found ({len(editions_found)}): {', '.join(editions_found)}\n")
    lines.append(
        f"- Invalid/placeholder rows removed: {len(invalid_df)} "
        "(blank or `----` Designation/Type)\n"
    )
    lines.append(f"- Valid rows retained in full-clean table: {len(valid_df)}\n")

    lines.append("\n## B. Families found (declared `Type`, all editions)\n")
    lines.append(f"- Distinct Type codes found: {len(known_families)}\n")
    lines.append(
        f"- Modern families (recognized by current parser, {len(modern_families)}): "
        f"{', '.join(sorted(modern_families))}\n"
    )
    lines.append(
        f"- Historical/other Type codes not in current parser "
        f"({len(historic_families)}): {', '.join(sorted(historic_families))}\n"
    )
    lines.append("\n| Type | rows (all editions) |\n|---|---|\n")
    for family, count in raw_family_counts.most_common():
        lines.append(f"| {family} | {count} |\n")

    lines.append("\n## C. Cleaning performed\n")
    lines.append(
        "- Conservative only: trimmed whitespace, collapsed internal whitespace runs, "
        "unified `×`/`✕` to `X`, uppercased `Edition`/`Type`/`Designation`.\n"
        "- No digits changed, no characters guessed/repaired, no designations merged "
        "by similarity.\n"
        f"- Removed {len(invalid_df)} rows with blank or `----` placeholder "
        "Designation/Type (not real shape records).\n"
    )

    lines.append("\n## D. Duplicate/conflict findings\n")
    total_pairs = catalog_df.shape[0] + len(conflict_pairs)
    lines.append(
        f"- Distinct (Type, Designation) pairs across all editions: {total_pairs}\n"
        f"- Collapsed into one canonical catalog row (dimensions consistent across "
        f"editions within {DIM_TOLERANCE:.0%} tolerance): {len(catalog_df)}\n"
        f"- Excluded as genuine conflicts (inconsistent core dimensions for the same "
        f"Type+Designation string, e.g. abbreviated historical `2L` designations that "
        f"omit thickness): {len(conflict_pairs)} pairs "
        f"({len(conflicts_df)} underlying rows) — see "
        "`aisc_v16_label_catalog_conflicts.csv`.\n"
    )

    lines.append("\n## E. Coverage vs old catalog (2,299-shape XLSX)\n")
    if old_comparison is None:
        lines.append("- Old XLSX catalog not found; comparison skipped.\n")
    else:
        lines.append(
            f"- Old catalog unique labels: {old_comparison['old_count']}\n"
            f"- New catalog unique designations: {old_comparison['new_count']}\n"
            f"- Overlap: {old_comparison['overlap']}\n"
            f"- Newly added (in new, not in old): {old_comparison['newly_added']}\n"
            f"- Missing from new (in old, not in new): "
            f"{old_comparison['old_missing_from_new']}\n"
        )
        lines.append("\n| Type | old count | new count | diff |\n|---|---|---|---|\n")
        all_types = sorted(
            set(old_comparison["old_family_counts"]) | set(old_comparison["new_family_counts"])
        )
        for t in all_types:
            oc = old_comparison["old_family_counts"].get(t, 0)
            nc = old_comparison["new_family_counts"].get(t, 0)
            lines.append(f"| {t} | {oc} | {nc} | {nc - oc:+d} |\n")
        if old_comparison["old_missing_examples"]:
            lines.append(
                "\nSample old labels absent from the new all-editions catalog: "
                + ", ".join(old_comparison["old_missing_examples"]) + "\n"
            )

    lines.append("\n## F. Family cross-check (declared `Type` vs longest-prefix inference)\n")
    lines.append(
        f"- Catalog rows checked: {len(catalog_df)}\n"
        f"- Inference matches declared Type: {len(catalog_df) - len(mismatches) - len(unmatched)}\n"
        f"- Mismatches (inferred prefix differs from declared Type): {len(mismatches)}\n"
        f"- Unmatched (no known Type code is a leading-prefix of the designation): "
        f"{len(unmatched)}\n"
    )
    if mismatches:
        sample = mismatches[:15]
        lines.append(
            "\nSample mismatches (declared, designation, inferred): "
            + "; ".join(f"{d}/{s}→{i}" for d, s, i in sample) + "\n"
        )

    lines.append("\n## G. Designation quality / parser compatibility\n")
    lines.append(
        f"- Unique catalog designations: {dq_stats['count']}\n"
        f"- Length: min {dq_stats['min_len']}, max {dq_stats['max_len']}, "
        f"mean {dq_stats['mean_len']:.1f}\n"
        f"- Contains space: {dq_stats['contains_space']}, "
        f"slash: {dq_stats['contains_slash']}, decimal: {dq_stats['contains_decimal']}, "
        f"hyphen: {dq_stats['contains_hyphen']}, parenthesis: {dq_stats['contains_paren']}, "
        f"comma: {dq_stats['contains_comma']}, unusual chars: {dq_stats['unusual_chars']}\n"
        f"- Parser (`services.structural_parser.parse_section`) family+dims fully "
        f"extracted: {parser_full}\n"
        f"- Parser family recognized, partial dims (e.g. decimal depth truncated by "
        f"`_DEPTH_RE`): {parser_partial}\n"
        f"- `valid_source_but_parser_unsupported` (family code not in the current "
        f"13-family parser prefix list): {len(parser_unsupported)}\n"
    )
    if parser_unsupported:
        lines.append(
            "\nSample parser-unsupported designations: "
            + ", ".join(parser_unsupported[:15]) + "\n"
        )

    lines.append("\n## H. Output files\n")
    lines.append(
        f"- `{OUT_FULL_CLEAN.relative_to(BACKEND_DIR)}` ({len(valid_df)} rows, "
        f"{valid_df.shape[1]} columns)\n"
        f"- `{OUT_CATALOG.relative_to(BACKEND_DIR)}` ({len(catalog_df)} rows)\n"
        f"- `{OUT_CONFLICTS.relative_to(BACKEND_DIR)}` ({len(conflicts_df)} rows, "
        f"{len(conflict_pairs)} pairs)\n"
        f"- `{OUT_REPORT.relative_to(BACKEND_DIR)}` (this report)\n"
        f"- `services/aisc_v16_catalog.py` (new, additive catalog loader)\n"
        f"- `config.py` (additive `aisc_v16_label_catalog_path` setting only)\n"
    )

    lines.append("\n## I. Final canonical catalog size\n")
    lines.append(
        f"- {len(catalog_df)} canonical (family, designation) entries across "
        f"{catalog_df['family'].nunique()} families, all {len(editions_found)} editions.\n"
    )

    scope_counts = catalog_df["catalog_scope"].value_counts().to_dict() if not catalog_df.empty else {}
    modern_families_in_catalog = sorted(set(catalog_df.loc[catalog_df["catalog_scope"] == "modern", "family"]))
    historical_families_in_catalog = sorted(set(catalog_df.loc[catalog_df["catalog_scope"] == "historical", "family"]))
    lines.append("\n## J. Catalog scope (modern production vs historical/legacy)\n")
    lines.append(
        "Policy: `catalog_scope = modern` iff `family` is exactly one of the 13 "
        "families the current candidate generator/parser already recognize "
        f"(`services.wildcard_matcher._FAMILY_PREFIXES`); everything else is "
        "`historical`. This is a data classification only — it never merges or "
        "reinterprets a declared Type code (e.g. `ST R`/`ST S`/`ST JR` stay "
        "historical and distinct from modern `ST`).\n"
    )
    lines.append(
        f"- Modern: {scope_counts.get('modern', 0)} entries, "
        f"{len(modern_families_in_catalog)} families: "
        f"{', '.join(modern_families_in_catalog)}\n"
        f"- Historical: {scope_counts.get('historical', 0)} entries, "
        f"{len(historical_families_in_catalog)} families: "
        f"{', '.join(historical_families_in_catalog)}\n"
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("".join(lines), encoding="utf-8")

    print(f"raw: {raw_rows} rows x {raw_cols} cols; editions: {editions_found}")
    print(f"invalid rows removed: {len(invalid_df)}")
    print(f"full_clean rows: {len(valid_df)}")
    print(f"catalog rows: {len(catalog_df)}; conflict pairs: {len(conflict_pairs)}")
    print(f"report written: {OUT_REPORT}")


if __name__ == "__main__":
    main()
