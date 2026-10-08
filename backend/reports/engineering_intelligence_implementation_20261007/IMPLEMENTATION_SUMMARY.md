# Implementation summary — 7 October 2026

Checkpoint only. Phases 1 and 2 of the engineering-intelligence sequence are in the Drawing Summary. Phases 3 through 15 are not built.

## Phase 1 — Sheet index on the summary

The title-block sheet index was already produced and visually checked (56/56 in the Phase 1 manual audit). The summary did not show it.

The summary now lists every sheet: id, printed title, role, issue date, scale, revision rows, and PDF page. The sheet id is the title-block id, so OSSE keeps `S-122-O` and `S-602-O`. A view control opens that page on the title-block box.

The orientation sentence quotes the title-block issue. It no longer takes the issue from a stamp search that treated Brandywine `FTG PERMIT` as “permit set”.

| Project | Orientation before | Orientation after |
| --- | --- | --- |
| Burrville | no issue; column schedule `S501` | issue `50% DESIGN DEVELOPMENT`; `S-501` |
| OSSE | “permit set, numbered revision”; `S602` | issue `Permit Submission`; `S-602-O` |
| Struct.pdf | “bid set”; `S002` | issue `BID SET`; `S002` |
| Brandywine | “permit set”; `S600` | issue `65% DESIGN DEVELOPMENT`; `S-600` |

`FTG PERMIT` stays on the revision row.

## Phase 2 — Sheet role from the printed title

Each sheet gets a role from its sheet title only. Page-body keywords are not used. A title that names two drawing types stays `review`. A title that names no type stays `review`. A feet-inch string is not a role.

On the 122 sheets of these four sets, 120 roles are `read` and 2 are `review` (both OSSE): `DESIGN TABLES`, and `NORTH STAIR & ELEVATOR PLANS AND ELEVATIONS`.

The old page-keyword makeup sentence is not shown when a sheet index exists. The old `page_categories` field is still stored. It is not the navigation.

When a set has plan elevations and no schedule level list, those elevations are in the main summary. That is Struct.pdf. They are labeled as local plan notes, not as a building-level register.

## Phases 3–16 — additive intelligence layer

`drawing_intelligence.engineering_intelligence` (version `engineering_intelligence_v1`) is new. Cache version is `legend_extractor_v6q-engineering-intelligence`. A v6p profile is not reused. Old cache files were not deleted.

What is extracted, and what it is not:

| Layer | What is stored | What it refuses to do |
| --- | --- | --- |
| Views | A whole line that is a view title. `SECTION A` counts. A bare `SECTION` counts only with a scale under it. If the sheet has no viewport title, one `sheet_title` view records the sheet title | A keyword inside a sentence is not a view. The box is the title line, `boundary_status` `title_only`, not a claimed view extent |
| References | `D/S401`, `N/S502`, `4/S-401-O`, `SEE PLAN`, `SEE SECTION` | `W/ SPEC` and `T/ SLAB` are not sheets. `4/S-401` is `target_missing` and is not rewritten as `S-401-O`. `N/S502` is `target_sheet_only` because view N is not a printed title on S502 |
| Relationships | Sheet→view, reference→target, mark text→definition | An unresolved edge does not change a quantity |
| Grids | Short letter or number on a plan sheet, status `candidate`, capped | `4'-6"` is a dimension. Candidates are not confirmed bubbles |
| Levels | Existing schedule levels. A differing plan value stays a conflict | No winning elevation is chosen |
| Occurrences | Whole-word mark hits off the definition sheet. `quantity` is null | A hit count is not a takeoff count. The definition sheet itself is not an occurrence |
| Objects and schedules | Pointers to the existing definition and schedule readers | Those readers were not replaced |
| Incomplete labels | `L4X4` stays `review_required` with no resolved thickness | Thickness is not invented |
| Dimensions | A whole line that contains feet or inches | A bare number is not a dimension and not a grid id by itself unless it is a plan-sheet candidate |
| Notes | Numbered lines on a general-notes sheet | Note text is not a scope or quantity decision |
| Scope flags | existing, demolition, alternate, future, temporary | Nothing is removed from the set |
| Warnings | Level conflict, ambiguous sheet, unresolved reference, incomplete label, defined-but-not-seen | Conflicts stay open |

## Not claimed

Geometry is not member identity. Family hit counts are not quantities. There is no ML model.


## Cache

`EXTRACTOR_VERSION` is `legend_extractor_v6q-engineering-intelligence`. `drawing_intelligence` stays `drawing_intelligence_v3`. The new object is `engineering_intelligence`.

## Quantity policy

Unchanged. This checkpoint does not call `QuantityEngine` differently, does not edit predictions, and does not edit schedule parsing. See `REGRESSION_REPORT.md`.
