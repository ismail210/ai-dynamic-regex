# Regression — sheet navigation and engineering intelligence

Compared with `backend/reports/drawing_summary_engineering_audit_20261007/profile_digest.json`, which was extracted before this change. Fresh extract on 7 October 2026, caches under `/tmp/ei_sheet_nav_legend` and `/tmp/ei_sheet_nav_art`. Repository training caches were not written.

## Counters that must not move

| Project | Family hits before | After | Column entries | Mark map |
| --- | --- | --- | --- | --- |
| Burrville | W 801, HSS 83, L 60, C 5, 2L 2, WT 1 | same | 121 = 121 | 0 = 0 |
| OSSE | W 280, HSS 155, L 29, C 8 | same | 100 = 100 | 0 = 0 |
| Struct.pdf | W 991, L 106, HSS 59, C 20, WT 1 | same | 6 = 6 | 12 = 12 |
| Brandywine | W 1588, HSS 118, L 55, C 13, WT 1 | same | 105 = 105 | 0 = 0 |

Family hits are text occurrences, not takeoff quantities. They are the check that this display change did not retokenize the sheets.

## What the orientation sentence did change

| Project | Before | After |
| --- | --- | --- |
| Burrville | `29-page structural set with a steel column schedule on S501` | `29-page structural set (issue: 50% DESIGN DEVELOPMENT) with a steel column schedule on S-501` |
| OSSE | `(permit set, numbered revision)` and `S602` | `(issue: Permit Submission)` and `S-602-O` |
| Struct.pdf | `(bid set)` and `S002` | `(issue: BID SET)` and `S002` |
| Brandywine | `(permit set)` and `S600` | `(issue: 65% DESIGN DEVELOPMENT)` and `S-600` |

## Intelligence-layer extract

A second extract on 7 October 2026 used caches `/tmp/ei_v6q_legend2` and `/tmp/ei_v6q_art2` after the sheet-token and bare-view fixes. Repository training caches were not written. `families_match` is true on all four projects. Column entries stay 121, 100, 6, 105. Mark maps stay 0, 0, 12, 0. `false_sheets` is empty: `W/ SPEC` and `T/ SLAB` are not sheet ids. OSSE still stores both Level 2 values. `N/S502` is `target_sheet_only`. `4/S-401` is `target_missing`.

## Quantity engine

`QuantityEngine`, the prediction orchestrator, schedule parsers, and the mark-map builder were not edited. Quantity totals were not regenerated. The upstream counters above did not move, so there is no new total to publish.

## Tests

- `python -m pytest tests/test_sheet_navigation.py tests/test_drawing_intelligence.py tests/test_sheet_index.py -q` — 66 passed (sheet-navigation checkpoint)
- `python -m pytest tests/test_intelligence_layer.py tests/test_drawing_intelligence.py tests/test_sheet_navigation.py -q` — 60 passed after the sheet-token and bare-view fixes
- `python -m pytest tests/test_intelligence_layer.py -q` — 10 passed
- `vitest` on `SheetIndex.test.jsx`, `DrawingSummaryPanel.test.jsx`, `DrawingSummaryPanel.osse.test.jsx` — 67 passed
- `vitest` on `EngineeringIntelligence.test.jsx` — 1 passed, after the conflict chip was moved out of a paragraph
- `vite build` — succeeded

The full backend suite was not run. The running app was not clicked. Blast radius is the drawing-intelligence profile and the summary panel.
