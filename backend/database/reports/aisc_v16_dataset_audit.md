# AISC v16 dataset audit (all editions)
Source: `aisc-shapes-database-v160h(Database v16.csv`
## A. Raw dataset size
- Raw rows: 18879
- Raw columns: 143
- Editions found (12): 13th, 14th, 15th, ASD5, ASD6, ASD7, ASD8, ASD9, Historic, LRFD1, LRFD2, LRFD3
- Invalid/placeholder rows removed: 37 (blank or `----` Designation/Type)
- Valid rows retained in full-clean table: 18842

## B. Families found (declared `Type`, all editions)
- Distinct Type codes found: 45
- Modern families (recognized by current parser, 13): 2L, C, HP, HSS, L, M, MC, MT, PIPE, S, ST, W, WT
- Historical/other Type codes not in current parser (32): B, BCB, BJ, BL, BLB, BP, BWF, CB, G, H, I, J, JR, JRC, JRU, LWF, P, ST B, ST I, ST JR, ST M, ST R, ST S, ST WF, T FS, U, WF, WFB, WFCB, XP, XXP, Z

| Type | rows (all editions) |
|---|---|
| 2L | 3768 |
| HSS | 2502 |
| W | 2340 |
| WT | 2156 |
| L | 1428 |
| S | 939 |
| H | 651 |
| ST R | 593 |
| CB | 551 |
| WF | 465 |
| B | 382 |
| MC | 339 |
| ST WF | 281 |
| C | 270 |
| ST | 264 |
| ST S | 248 |
| G | 214 |
| PIPE | 199 |
| U | 146 |
| M | 145 |
| WFCB | 141 |
| HP | 130 |
| WFB | 127 |
| MT | 102 |
| P | 78 |
| XP | 78 |
| I | 62 |
| XXP | 42 |
| ST I | 37 |
| ST B | 33 |
| BP | 18 |
| T FS | 14 |
| Z | 13 |
| ST JR | 12 |
| JR | 12 |
| BLB | 11 |
| ST M | 9 |
| J | 8 |
| BWF | 7 |
| BJ | 7 |
| BL | 7 |
| LWF | 6 |
| JRC | 3 |
| JRU | 3 |
| BCB | 1 |

## C. Cleaning performed
- Conservative only: trimmed whitespace, collapsed internal whitespace runs, unified `×`/`✕` to `X`, uppercased `Edition`/`Type`/`Designation`.
- No digits changed, no characters guessed/repaired, no designations merged by similarity.
- Removed 37 rows with blank or `----` placeholder Designation/Type (not real shape records).

## D. Duplicate/conflict findings
- Distinct (Type, Designation) pairs across all editions: 4767
- Collapsed into one canonical catalog row (dimensions consistent across editions within 2% tolerance): 3842
- Excluded as genuine conflicts (inconsistent core dimensions for the same Type+Designation string, e.g. abbreviated historical `2L` designations that omit thickness): 925 pairs (5981 underlying rows) — see `aisc_v16_label_catalog_conflicts.csv`.

## E. Coverage vs old catalog (2,299-shape XLSX)
- Old catalog unique labels: 2299
- New catalog unique designations: 3842
- Overlap: 1717
- Newly added (in new, not in old): 2125
- Missing from new (in old, not in new): 582

| Type | old count | new count | diff |
|---|---|---|---|
| 2L | 639 | 576 | -63 |
| B | 0 | 26 | +26 |
| BCB | 0 | 1 | +1 |
| BJ | 0 | 7 | +7 |
| BLB | 0 | 1 | +1 |
| BP | 0 | 1 | +1 |
| C | 32 | 34 | +2 |
| CB | 0 | 10 | +10 |
| G | 0 | 3 | +3 |
| H | 0 | 7 | +7 |
| HP | 22 | 26 | +4 |
| HSS | 714 | 1122 | +408 |
| J | 0 | 7 | +7 |
| JR | 0 | 12 | +12 |
| JRC | 0 | 3 | +3 |
| JRU | 0 | 3 | +3 |
| L | 137 | 319 | +182 |
| LWF | 0 | 1 | +1 |
| M | 16 | 38 | +22 |
| MC | 40 | 48 | +8 |
| MT | 14 | 27 | +13 |
| P | 0 | 18 | +18 |
| PIPE | 51 | 42 | -9 |
| S | 28 | 260 | +232 |
| ST | 28 | 42 | +14 |
| ST JR | 0 | 7 | +7 |
| ST R | 0 | 192 | +192 |
| ST S | 0 | 71 | +71 |
| T FS | 0 | 8 | +8 |
| U | 0 | 5 | +5 |
| W | 289 | 491 | +202 |
| WF | 0 | 7 | +7 |
| WFB | 0 | 2 | +2 |
| WFCB | 0 | 5 | +5 |
| WT | 289 | 388 | +99 |
| XP | 0 | 18 | +18 |
| XXP | 0 | 14 | +14 |

Sample old labels absent from the new all-editions catalog: 2L2-1/2X1-1/2X1/4LLBB, 2L2-1/2X1-1/2X1/4X3/4LLBB, 2L2-1/2X1-1/2X1/4X3/8LLBB, 2L2-1/2X1-1/2X3/16LLBB, 2L2-1/2X1-1/2X3/16X3/4LLBB, 2L2-1/2X1-1/2X3/16X3/8LLBB, 2L2-1/2X2X1/4LLBB, 2L2-1/2X2X1/4X3/4LLBB, 2L2-1/2X2X1/4X3/8LLBB, 2L2-1/2X2X3/16LLBB, 2L2-1/2X2X3/16X3/4LLBB, 2L2-1/2X2X3/16X3/8LLBB, 2L2-1/2X2X3/8LLBB, 2L2-1/2X2X3/8X3/4LLBB, 2L2-1/2X2X3/8X3/8LLBB, 2L2-1/2X2X5/16LLBB, 2L2-1/2X2X5/16X3/4LLBB, 2L2-1/2X2X5/16X3/8LLBB, 2L2X2X1/8, 2L2X2X1/8X3/4, 2L2X2X1/8X3/8, 2L3-1/2X2-1/2X1/2LLBB, 2L3-1/2X2-1/2X1/2X3/4LLBB, 2L3-1/2X2-1/2X1/2X3/8LLBB, 2L3-1/2X2-1/2X1/4LLBB

## F. Family cross-check (declared `Type` vs longest-prefix inference)
- Catalog rows checked: 3842
- Inference matches declared Type: 3541
- Mismatches (inferred prefix differs from declared Type): 16
- Unmatched (no known Type code is a leading-prefix of the designation): 285

Sample mismatches (declared, designation, inferred): B/12BL,B12L→BL; J/JR10→JR; J/JR11→JR; J/JR12→JR; J/JR6→JR; J/JR7→JR; J/JR8→JR; J/JR9→JR; WF/8WFB8A→WFB; WFB/12WF,B14C→WF; WFB/16WF,CB162→WF; WFCB/21WF,CB21→WF; WFCB/21WF,CB21A→WF; WFCB/24WF,CB244→WF; WFCB/27WF,CB27→WF

## G. Designation quality / parser compatibility
- Unique catalog designations: 3842
- Length: min 1, max 26, mean 10.6
- Contains space: 0, slash: 1056, decimal: 1914, hyphen: 403, parenthesis: 0, comma: 16, unusual chars: 16
- Parser (`services.section_parser.parse_section`) family+dims fully extracted: 3403
- Parser family recognized, partial dims (e.g. decimal depth truncated by `_DEPTH_RE`): 291
- `valid_source_but_parser_unsupported` (family code not in the current 13-family parser prefix list): 148

Sample parser-unsupported designations: 12BL,B12L, 6B,B6B, B108, B14X4, B21, B23, B25, B31, B32, B34, B35, B37, B38, B39N, B41

## H. Output files
- `database\aisc_v16_full_clean.csv` (18842 rows, 143 columns)
- `database\aisc_v16_label_catalog.csv` (3842 rows)
- `database\aisc_v16_label_catalog_conflicts.csv` (5981 rows, 925 pairs)
- `database\reports\aisc_v16_dataset_audit.md` (this report)
- `services/aisc_v16_catalog.py` (new, additive catalog loader)
- `config.py` (additive `aisc_v16_label_catalog_path` setting only)

## I. Final canonical catalog size
- 3842 canonical (family, designation) entries across 37 families, all 12 editions.

## J. Catalog scope (modern production vs historical/legacy)
Policy: `catalog_scope = modern` iff `family` is exactly one of the 13 families the current candidate generator/parser already recognize (`services.wildcard_matcher._FAMILY_PREFIXES`); everything else is `historical`. This is a data classification only — it never merges or reinterprets a declared Type code (e.g. `ST R`/`ST S`/`ST JR` stay historical and distinct from modern `ST`).
- Modern: 3413 entries, 13 families: 2L, C, HP, HSS, L, M, MC, MT, PIPE, S, ST, W, WT
- Historical: 429 entries, 24 families: B, BCB, BJ, BLB, BP, CB, G, H, J, JR, JRC, JRU, LWF, P, ST JR, ST R, ST S, T FS, U, WF, WFB, WFCB, XP, XXP
