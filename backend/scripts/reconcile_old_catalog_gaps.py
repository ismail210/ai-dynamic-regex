"""
Reconcile the 582 old-catalog labels absent from the new AISC v16
all-editions canonical catalog (see prepare_aisc_v16_catalog.py).

For each old label missing from `aisc_v16_label_catalog.csv`, classify why:

  - excluded_conflict           the (Type, Designation) pair exists in the
                                 new source but was excluded as a genuine
                                 cross-edition dimensional conflict (see
                                 aisc_v16_label_catalog_conflicts.csv)
  - formatting_difference       a designation with the same family and a
                                 very similar (but not identical) spelling
                                 exists in the new full-clean source —
                                 likely the same shape, different formatting
  - missing_from_raw_source     no matching or similar designation exists
                                 anywhere in the new source at all (any
                                 edition) — a genuine coverage gap
  - other                       matched by designation text alone under a
                                 different declared family (rare)

Then proposes a master supported lookup catalog: the new canonical catalog
plus only the `missing_from_raw_source` old entries (safe to add — nothing
in the new source contradicts them), each tagged with explicit provenance
(`provenance=old_xlsx_v16_gap`). `excluded_conflict` and
`formatting_difference` entries are NOT auto-added — they are reported for
human review instead of silently merged or guessed.

Does not modify aisc_v16_label_catalog.csv. Writes:
  - database/aisc_v16_master_catalog.csv
  - database/reports/aisc_v16_missing_labels_reconciliation.md

Run: python backend/scripts/reconcile_old_catalog_gaps.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.aisc_v16_catalog import lookup_key  # noqa: E402

DATABASE_DIR = BACKEND_DIR / "database"
OLD_XLSX = DATABASE_DIR / "aisc-shapes-database-v160-2.xlsx"
OLD_XLSX_SHEET = "Database v16.0"
FULL_CLEAN = DATABASE_DIR / "aisc_v16_full_clean.csv"
CATALOG = DATABASE_DIR / "aisc_v16_label_catalog.csv"
CONFLICTS = DATABASE_DIR / "aisc_v16_label_catalog_conflicts.csv"

OUT_MASTER = DATABASE_DIR / "aisc_v16_master_catalog.csv"
REPORTS_DIR = DATABASE_DIR / "reports"
OUT_REPORT = REPORTS_DIR / "aisc_v16_missing_labels_reconciliation.md"

_NUMBER_TOKEN_RE = re.compile(r"\d+-\d+/\d+|\d+/\d+|\d+\.\d+|\d+")


def _numeric_signature(text: str):
    """Ordered tuple of every number in ``text`` as a float (mixed fractions
    like ``1-1/2`` -> 1.5). Used to tell true formatting variants (same
    numbers, different punctuation/delimiters) apart from a different shape
    that merely looks similar as a string — string similarity alone is not
    trustworthy here (e.g. ``HSS22X18X5/8`` vs ``HSS20X18X5/8`` score high on
    edit distance but are different physical shapes)."""

    values = []
    for token in _NUMBER_TOKEN_RE.findall(text):
        if "-" in token:
            whole, frac = token.split("-", 1)
            num, den = frac.split("/")
            values.append(float(whole) + float(num) / float(den))
        elif "/" in token:
            num, den = token.split("/")
            values.append(float(num) / float(den))
        else:
            values.append(float(token))
    return tuple(values)


def classify(old_family: str, old_key: str, old_designation: str, full_clean_keys_by_family, conflict_keys):
    if (old_family, old_key) in conflict_keys:
        return "excluded_conflict", None

    same_family_keys = full_clean_keys_by_family.get(old_family, [])
    old_signature = _numeric_signature(old_designation)
    for candidate_key in same_family_keys:
        if candidate_key == old_key:
            # Present in raw source under this family but not in the final
            # catalog nor the conflicts file -> shouldn't happen (catalog +
            # conflicts partition every valid pair); treat defensively.
            return "other", candidate_key
        candidate_signature = _numeric_signature(candidate_key)
        if candidate_signature and candidate_signature == old_signature:
            # Same family, identical numeric content, different spelling
            # (delimiter/decimal-vs-fraction/etc.) -> a true formatting
            # variant of an entry the new catalog already has, not a gap.
            return "formatting_difference", candidate_key

    return "missing_from_raw_source", None


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    old_df = pd.read_excel(OLD_XLSX, sheet_name=OLD_XLSX_SHEET, dtype=str)
    old_rows = [
        {
            "family": str(t).strip(),
            "designation": str(label).strip(),
            "key": lookup_key(label),
        }
        for label, t in zip(old_df["AISC_Manual_Label"], old_df["Type"])
    ]
    old_by_key = {r["key"]: r for r in old_rows}

    catalog_df = pd.read_csv(CATALOG, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    catalog_keys = {lookup_key(d) for d in catalog_df["designation"]}

    full_clean_df = pd.read_csv(FULL_CLEAN, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    full_clean_keys_by_family: dict = {}
    for family, designation in zip(full_clean_df["Type"], full_clean_df["Designation"]):
        full_clean_keys_by_family.setdefault(family, set()).add(lookup_key(designation))
    full_clean_keys_by_family = {k: sorted(v) for k, v in full_clean_keys_by_family.items()}

    conflicts_df = pd.read_csv(CONFLICTS, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    conflict_keys = {
        (family, lookup_key(designation))
        for family, designation in zip(conflicts_df["family"], conflicts_df["designation"])
    }

    missing_keys = set(old_by_key) - catalog_keys

    classified = []
    for key in missing_keys:
        old_row = old_by_key[key]
        reason, near_match = classify(
            old_row["family"], key, old_row["designation"], full_clean_keys_by_family, conflict_keys
        )
        classified.append(
            {
                "family": old_row["family"],
                "designation": old_row["designation"],
                "reason": reason,
                "near_match_in_new_source": near_match or "",
            }
        )

    reason_counts = Counter(r["reason"] for r in classified)

    # --- Master catalog proposal -------------------------------------------------
    master_rows = []
    for _, row in catalog_df.iterrows():
        master_rows.append(dict(row) | {"provenance": "new_csv_v16"})

    safe_additions = [r for r in classified if r["reason"] == "missing_from_raw_source"]
    for r in safe_additions:
        master_rows.append(
            {
                "family": r["family"],
                "designation": r["designation"],
                "source_row_id": "",
                "source_edition": "",
                "source_edition_count": 1,
                "catalog_scope": "",
                "provenance": "old_xlsx_v16_gap",
            }
        )

    master_df = pd.DataFrame(master_rows)
    from services.aisc_v16_catalog import classify_catalog_scope

    blank_scope = master_df["catalog_scope"].isin(["", None]) | master_df["catalog_scope"].isna()
    master_df.loc[blank_scope, "catalog_scope"] = master_df.loc[blank_scope, "family"].map(
        classify_catalog_scope
    )
    master_df = master_df.sort_values(["family", "designation"]).reset_index(drop=True)
    master_df.to_csv(OUT_MASTER, index=False, encoding="utf-8-sig")

    # --- Report --------------------------------------------------------------
    lines = []
    lines.append("# AISC v16 old-catalog gap reconciliation\n")
    lines.append(
        f"Old catalog: {len(old_rows)} labels. New canonical catalog: "
        f"{len(catalog_keys)} entries. Missing from new: {len(missing_keys)}.\n"
    )
    lines.append("\n## Reason breakdown\n")
    lines.append("| Reason | Count |\n|---|---|\n")
    for reason, count in reason_counts.most_common():
        lines.append(f"| {reason} | {count} |\n")

    for reason in ("excluded_conflict", "formatting_difference", "missing_from_raw_source", "other"):
        sample = [r for r in classified if r["reason"] == reason][:15]
        if not sample:
            continue
        lines.append(f"\n### Sample: {reason}\n")
        for r in sample:
            extra = f" (near match in new source: `{r['near_match_in_new_source']}`)" if r["near_match_in_new_source"] else ""
            lines.append(f"- `{r['family']}` / `{r['designation']}`{extra}\n")

    lines.append("\n## Master catalog proposal\n")
    lines.append(
        "Controlled union, not a blind merge: the new canonical catalog "
        f"({len(catalog_df)} entries) plus only the old entries classified "
        f"`missing_from_raw_source` ({len(safe_additions)} entries) — nothing in the "
        "new source contradicts these, so they are safe to carry forward with "
        "explicit `provenance=old_xlsx_v16_gap`. `excluded_conflict` "
        f"({reason_counts.get('excluded_conflict', 0)}) and `formatting_difference` "
        f"({reason_counts.get('formatting_difference', 0)}) entries are NOT auto-added — "
        "they are ambiguous (conflicting source data) or likely duplicates under a "
        "different spelling (already represented), and are left for human review "
        "instead of being silently merged or guessed.\n"
    )
    lines.append(
        f"\n**Final proposed master catalog size: {len(master_df)} entries** "
        f"({len(catalog_df)} from the new source + {len(safe_additions)} old-only gaps).\n"
    )
    lines.append(f"\nWritten to `{OUT_MASTER.relative_to(BACKEND_DIR)}`.\n")

    OUT_REPORT.write_text("".join(lines), encoding="utf-8")

    print(f"missing from new catalog: {len(missing_keys)}")
    for reason, count in reason_counts.most_common():
        print(f"  {reason}: {count}")
    print(f"master catalog size: {len(master_df)}")
    print(f"report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
