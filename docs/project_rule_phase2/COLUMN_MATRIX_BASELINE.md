# Column-Schedule Matrix — Baseline (before any matrix parser)

Recorded 2026-09-23 on `bassam/project-rule-intelligence` with default flags. Read-only measurement.

## Current behaviour on the three development pages

| Page | Page role (legend_profile) | Legacy `schedule_grid` regions | Shadow `build_schedule_evidence` (widened) regions | Engineering tokens on the page | Section-label proposals in the package | Proposals also emitted as raw engineering tokens |
|---|---|---|---|---|---|---|
| Burrville p.28 | DRAWING | 0 | 0 | 139 | 61 (+3 empty locations) | 59 |
| GCDC p.77 | DRAWING | 0 | 0 | 328 | 102 | 102 |
| Springhill p.26 | DRAWING | 0 | 0 | 187 | 64 | 58 |

The repeated or second schedule sheets (Burrville p.29, GCDC p.78, Springhill p.27) are also `DRAWING` pages.

What this means:

- **Neither schedule path recognises the matrices.** They have no MARK/SIZE header, and the section is a rotated label placed between level datums.
- **Production still sees the labels as ordinary section tokens on a drawing page.** Nearly every schedule label (59/61, 102/102, 58/64) reaches extraction as a normal engineering token. Nothing marks them as schedule definitions, and `context_scope` leaves drawing-page tokens takeoff-eligible by default. The takeoff therefore counts one label instance per printed schedule label: no level-segment semantics, no location identity, and no deduplication across the repeated or wing sheets. This matches the earlier real-takeoff audit finding that Burrville W10X33 was overcounted (158 vs 81). This is pre-existing behaviour and is **not changed** here.
- Schedule parsing costs about 0.3–0.6 ms per page, so runtime is not a constraint.

## Proposal statistics (the package prefill, not gold)

| Page | Tables | Locations | Section proposals | Catalog-valid | Level intervals seen |
|---|---|---|---|---|---|
| Burrville p.28 | 2 | 64 | 61 | 61 | UPPER LEVEL→MAIN ROOF (60), GROUND→UPPER LEVEL (1) |
| GCDC p.77 | 1 | 54 | 102 | 102 | GROUND→SECOND (52), SECOND→OFFICE ROOF (48), ROOF→T.O. PARAPET (2) |
| Springhill p.26 | 2 | 64 | 64 | 64 | FIRST→SECOND FLOOR (64) |

These are **label positions**, not member extents. On the Burrville and Springhill S-501 layout, each label sits in one interval while the drawn column usually spans several levels (e.g. Springhill B-7 `W12X65` runs from FIRST FLOOR to about ROOF). Member extent is a reviewer field (`level_normalized`). A heuristic "line-extent" hint was tried and removed: it was unreliable on these pages.

## Exclusion examples (H5)

| Page | Records | Class | Lifecycle (printed) | `count_candidate` |
|---|---|---|---|---|
| p.7 (S-100) | 11 | existing_member_schedule | existing | false |
| p.8 (S-101) | 11 (repeat of p.7) | existing_member_schedule | existing | false |
| p.23 (S-800) | 10 | reinforcement_schedule | reinforcing | false |

## Status

- Reviewer gold: **none approved**. All 262 package records have both `extraction_review_status` and `physical_review_status` set to `PENDING_REVIEW`; the 230 development records therefore keep matrix-to-member parsing blocked.
- No parser accuracy is claimed against prefilled data.
