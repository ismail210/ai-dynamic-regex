# Parser fix: before vs after

Two concrete gaps were fixed in `services/wildcard_matcher.py` (consumed by
`services/structural_parser.py`, which imports `_DEPTH_RE`/`_WEIGHT_RE`/
`_FAMILY_PREFIXES` from it directly):

## 1. Decimal HSS/PIPE depth/weight truncation

`_DEPTH_RE`/`_WEIGHT_RE` matched digits only (`^(\d+)` / `X(\d+)`), so round
HSS/PIPE designations that store diameter/wall thickness as decimals (e.g.
`HSS10.750X0.188`) had their depth/weight silently truncated at the decimal
point (`depth=10.0` instead of `10.75`, `weight=0.0` instead of `0.188`).
Fixed to `^(\d+(?:\.\d+)?)` / `X(\d+(?:\.\d+)?)`.

This was not just a new-catalog issue — **189 entries already in the
production XLSX catalog** (round HSS, e.g. `HSS28.000X1.000`) hit this path.

**Measured effect on the new AISC v16 canonical catalog** (3,842 entries,
1,440 containing a decimal number anywhere):

| | Count |
|---|---|
| Designations where the old integer-only regex would have produced a wrong depth and/or weight | 283 |
| Of those, now parsed with the exact correct depth/weight | 283 |
| Remaining mismatches | 0 |

(Methodology: for every catalog designation containing a decimal, the
depth/weight the *old* regex would have produced was recomputed and compared
against what the *new* regex produces; `parse_section`'s actual output was
then checked against the new-regex expectation. All 283 previously-wrong
cases are now exactly correct; nothing regressed on the 1,157
decimal-containing designations that were already correct via the 3-field
`_HSS_THICKNESS_RE`/`_ANGLE_THICKNESS_RE` path, which already handled
decimals.)

Regression tests: `tests/test_section_parser.py`
(`test_round_hss_decimal_depth_and_weight_not_truncated`, using the real
catalog label `HSS28.000X1.000`, plus `HSS10.750X0.188`/`PIPE10.750X0.188`),
`tests/test_wildcard_matcher.py::test_round_hss_decimal_depth_reason_not_truncated`.

## 2. Family-prefix recognition made catalog-driven, not a hardcoded list

Before: `_FAMILY_PREFIXES` was an identical hardcoded 13-family literal set,
independently duplicated in `wildcard_matcher.py` AND
`label_reconstruction/corruption.py` — nothing enforced the two stayed in
sync (flagged as a real risk during the architecture audit for this phase).

After: both modules import one definition from the new
`services/family_codes.py` (`MODERN_FAMILY_CODES`, `longest_prefix_first`,
`split_family` — zero dependencies, pure text logic). `wildcard_matcher`
additionally derives `_FAMILY_PREFIXES` from whatever catalog is currently
loaded (`services.database_loader.catalog_entries()`), unioned with the
13-family floor so recognition never regresses below current behavior, via
`wildcard_matcher.refresh_family_prefixes()` — callable after
`database_loader.reload_from_pairs`/`reload_from_aisc_v16_catalog` in
offline training/eval contexts. Longest-prefix-first ordering (already
correct in the original code) continues to keep `2L` from collapsing into
`L`, `WT`/`MT`/`ST` from collapsing into `W`/`M`/`S`, etc. — this now applies
automatically to *any* distinct family code the loaded catalog contains
(e.g. `WFB`/`WFCB` vs `WF`, `ST R`/`ST S`/`ST JR` vs `ST`), not just the 13
hardcoded ones.

**Scope note:** this fixes family-prefix *recognition* (splitting a label
into `(family, remainder)` correctly) for any family present in the loaded
catalog. It does not add full structural-field grammars for the 24
historical families in `structural_parser.parse_fields` (that assigns each
family a field-count grammar — depth×weight, HSS-rect, leg-leg-thickness,
etc. — real per-family engineering work, not a config change). Those 148
designations remain `valid_source_but_parser_unsupported` (see
`aisc_v16_dataset_audit.md` §G) and are explicitly out of scope for "fix the
two concrete parser gaps" — flagged here for a future phase, not silently
dropped or guessed at.

Regression tests: `tests/test_wildcard_matcher.py::FamilyCodesSharedSourceTests`
(shared-source ordering/splitting, catalog-driven refresh, floor never
dropped), full backend suite green (412 passed, 1 pre-existing skip) after
both changes, confirming the Phase 2/3 resolution-contract safety tests are
unaffected.
