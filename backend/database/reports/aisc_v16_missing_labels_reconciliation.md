# AISC v16 old-catalog gap reconciliation
Old catalog: 2299 labels. New canonical catalog: 3842 entries. Missing from new: 582.

## Reason breakdown
| Reason | Count |
|---|---|
| excluded_conflict | 374 |
| missing_from_raw_source | 208 |

### Sample: excluded_conflict
- `PIPE` / `Pipe1/2XS`
- `2L` / `2L3-1/2X3X1/4LLBB`
- `2L` / `2L8X6X1/2X3/8LLBB`
- `L` / `L6X4X9/16`
- `2L` / `2L6X3-1/2X1/2LLBB`
- `2L` / `2L8X6X1X3/8LLBB`
- `2L` / `2L4X3-1/2X5/16X3/8LLBB`
- `L` / `L5X3X1/2`
- `2L` / `2L3-1/2X2-1/2X1/2X3/8LLBB`
- `2L` / `2L6X4X7/8X3/4LLBB`
- `HSS` / `HSS16X12X5/8`
- `2L` / `2L8X6X1LLBB`
- `2L` / `2L8X4X3/4X3/4LLBB`
- `2L` / `2L5X3X3/8X3/4LLBB`
- `2L` / `2L3-1/2X3X1/4X3/4LLBB`

### Sample: missing_from_raw_source
- `HSS` / `HSS14X12X5/8`
- `HSS` / `HSS22X16X5/16`
- `HSS` / `HSS22X16X3/4`
- `HSS` / `HSS14X8X3/8`
- `HSS` / `HSS18X18X5/16`
- `HSS` / `HSS22.000X0.500`
- `HSS` / `HSS12.000X0.250`
- `HSS` / `HSS24X14X3/4`
- `HSS` / `HSS18X10X1/2`
- `HSS` / `HSS16X6X1/2`
- `HSS` / `HSS18.000X0.875`
- `HSS` / `HSS4X1-1/2X3/16`
- `HSS` / `HSS18X8X3/8`
- `HSS` / `HSS16.000X0.750`
- `HSS` / `HSS4X1-1/2X1/8`

## Master catalog proposal
Controlled union, not a blind merge: the new canonical catalog (3842 entries) plus only the old entries classified `missing_from_raw_source` (208 entries) — nothing in the new source contradicts these, so they are safe to carry forward with explicit `provenance=old_xlsx_v16_gap`. `excluded_conflict` (374) and `formatting_difference` (0) entries are NOT auto-added — they are ambiguous (conflicting source data) or likely duplicates under a different spelling (already represented), and are left for human review instead of being silently merged or guessed.

**Final proposed master catalog size: 4050 entries** (3842 from the new source + 208 old-only gaps).

Written to `database\aisc_v16_master_catalog.csv`.
