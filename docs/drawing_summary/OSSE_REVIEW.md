# Drawing Summary review — OSSE (October 2026)

Branch `bassam/drawing-summary-osse`, from `9522744`. Primary drawing:
`07 - FEMS & OSSE/OSSE - ST.pdf` (26 pages). Display and evidence only —
prediction, the schedule mark map, exact catalog locks, QuantityEngine and
deduplication are unchanged (verified on 15 sets, below).

## Completion of the interrupted refinement - 2026-10-07

Starting feature and incoming main: `e32cc5ba6f872d98b752d0b54026e23512c86f7e`.
The implementation below was uncommitted when resumed. No new partner commits
were found in the initial or pre-publication fetch. Earlier dated sections remain historical;
this section supersedes their coverage and verification results.

Claude completed the display tables, assignment reconciliation, support links,
multi-source review, Locate service, directory, report route and model packet.
Four saved reviewer transcripts contained no final findings. The completion
review examined reuse, clarity, efficiency and responsibility boundaries directly.
Corrections made during that review:

- Locate request caches belong to the current profile; re-extraction refreshes
  results for the same document. Failed requests remain retryable.
- Crop rendering uses rotated display coordinates directly, rejects non-finite
  or empty bounds, and caps width and height at 1200 pixels. Rendering is in
  `services/pdf_pages.py`; the router retains document-access checks.
- Preview images use the authenticated API client and release blob URLs.
  Preview failure retains the Open plan action.
- Two offsets solve perpendicular distances for skew grids. Nearly parallel
  grids remain unresolved.
- Assignment-table scope requires matches to exactly one schedule; repeated
  locations across schedules cannot choose a building by majority or order.
- Search includes location, section, plate and support labels across all column groups.
- RC1 section dimensions exclude tie size/spacing; equal 24-inch dimensions agree.
- Inventory grounding allows printed-record counts, rejects member counts and
  unsupported totals, and accepts properly bracketed known fact IDs. Precast
  facts cannot call C1 steel. Cross-source disagreement cannot become conflict
  inside the schedule.
- The HSS elevation explanation remains unresolved after source review below.

## Coverage, plan locations and Level 2 evidence — 2026-10-07

Continues `e32cc5b` (published main) on this feature branch. Read directly from
`OSSE - ST.pdf` and the supplied `output.pdf` (a 21-page, image-only print of
the previous summary) and screen crops of S601, S602 and the Level 2
comparison. Display and evidence only: the production mark map, row selection,
exact catalog locks, QuantityEngine, prediction and deduplication are unchanged
(15-drawing comparison below).

### Source inventory (S601 p. 25, S602 p. 26) and what the summary does with it

| Source group | Kind | Printed | Before | Now | Layer of the gap |
|---|---|---|---|---|---|
| OSSE BUILDING - GCS (S602) | graphical schedule, location definitions | 26 entries | 26 shown after an 8-row preview | 26 shown whole | UI preview |
| OSSE PARKING - GCS (S602) | graphical schedule, 3 printed parts | 74 entries (71 C1, 3 RC1) | in a collapsed group, 8-row preview "Show all 74" | in the columns section, "Showing 8 of 74 printed entries — the search covers all of them" | UI filtering |
| BASE PLATE SCHEDULE (S601) | location → section / plate assignment table | 29 rows: 22 are building GCS locations, 7 HSS locations no schedule prints | read (all 29 rows); 22 used to link plates, 7 not displayed | 7 shown as "locations not in a column schedule" with their section, plate and source; no levels | display model |
| BASE PLATE TYPE SCHEDULE (S601) | dimensional definitions | 9 marks | assigned marks only | all 9, CBP-7 / CBP-8 / CBP-9 listed as not assigned to a listed location | display model |
| R13(5′-4″)-RA.1/.2, R14-RA.1/.2 (S602) | building GCS entries | 4 × W8X31 | "Not shown in this schedule" | "No plate is printed for this column, and no row of BASE PLATE SCHEDULE (S601, 29 location rows) lists this location"; Locate shows S104's stair/elevator part plans with P4 / F4.0 / F8.0 printed at the columns | evidence scope |
| P1 - 18 x 20 (S602 at C.8-8.9) | label in the column's drawn extent | 1 | dropped by the reader | kept as a support label; linked to S601 PIER SCHEDULE P1 (18″ × 24″); sizes differ → review item, both kept | PDF reading (classification) |
| CONCRETE SCHEDULE (S601) | RC1 definition (24″ × 24″, 12-#7, #3@12″ O.C.) | 1 row | not read (mark `RC1 - 24" x 24"` is not a production mark) | display-only table; the 3 RC1 parking entries link to it | classification |
| FOOTING SCHEDULE (S601) | footing definitions | 20 rows | read, every row dropped (marks such as `F3.0`), table absent | display-only table, rows shown as printed | classification |
| SLAB/DECK, MAT FOUNDATION (S601) | slab / deck and mat definitions | 7 / 2 rows | header (MARK + TOTAL DEPTH / THICKNESS) never searched | display-only reader; S5.25 = total depth 5¼″, 3.25″ concrete on 2″ deck | PDF reading |
| Walls, retaining walls, piers, beams (S601) | definitions | as printed | shown | unchanged (slabs and decks now a separate group) | — |
| Development / lap-splice length tables (S601) | reference data, no marks | 5 tables | not read | not read (no marks to define); listed here only | out of scope |
| S502 p. 19 / S503 p. 20 | references to schedules ("SEE SCHEDULE") | — | legacy list called them "Column schedule (p. 19)", "Beam / framing schedule (p. 20)" | a column / beam schedule is claimed only for a page whose table was read; p. 19/20 are references | narrative |
| S001 framing key example | legend example | 1 | correct | unchanged | — |

Reconciliation (printed records, not installed members): 26 building GCS
entries = 22 with an S601 location row + 4 R-grid W8X31 with none; S601's 29
rows = 22 building GCS locations + 7 HSS locations (C.1(-6")-7.3,
C.1(-6")-7.5, C.4(1' - 7 3/8")-7.5(-2' - 4 1/2"), C.4(1' - 7 3/8")-7.7(1' - 0 1/2"),
C.5-7(6"), D2.5-6.2, D2.5-8.05).

### Level 2 — every printed source, nothing chosen

| Source | Value | What it covers |
|---|---|---|
| S602 column schedule, T.O. SLAB LEVEL 2 | 55′-10″ | the schedule's level line |
| S122 sheet note 1 | 55′-2″ | the floor's datum statement, no area named |
| S122 local annotation (boxed, beside slab tag S5.25) | 55′-10″ | one place on the plan (bay C.6–C.7 / 7.7–8.05) |
| S421 section 1 (called out on S122 at C.5 / 5.1) | T.O. SLAB LEVEL 2, EL. 55′-10″ | slab edge at the west façade |
| S421 section 3 (called out on S122 at C / 7.1–7.3) | T.O. SLAB, EL. 55′-10″ | precast double-tee edge: its own local condition |
| S601 SLAB/DECK S5.25 | total depth 5¼″ (3.25″ concrete on 2″ deck) | the slab type tagged at the local annotation |

Check of printed numbers (calculated; it does not decide which governs): with
S122 note 2's 5¼″ top-of-steel offset, 55′-10″ − 5¼″ = 55′-4¾″, printed as
T.O. STEEL LEVEL 2 on S221 (building elevations, ×4), S103 (×3) and S421
section 9; 55′-2″ − 5¼″ = 54′-8¾″ was not found among the extracted level markers. The S122 HSS6X4X1/4 horizontal callout at 55 feet 2-3/4 inches references
section 9/S421. That section identifies an HSS6X4X1/4 horizontal outrigger
between grids 6.2 and 6.3 and prints T.O. STEEL LEVEL 2 at 55 feet 4-3/4 inches.
Review of both rendered sources does **not** establish different members or
precisely which surface the bracketed value governs. The 2-inch relationship
remains unresolved. The earlier draft's claim of a different surface with no
conflict is withdrawn. No centerline, offset or datum conversion is inferred.

Alternative explanations:

| Explanation | Evidence |
|---|---|
| Different local slab elevations | unresolved — no step, depression or raised-slab note near the local annotation; section 8 (raised slab at stair) is a separate condition |
| Different physical surfaces | not supported — note, schedule and sections all name the top of slab |
| Different datum systems | not supported — the same datum notes agree with the schedule for Level 1 (S121, 38′-0″) and Roof (S123, 69′-4″) |
| The general note does not govern a local condition | unresolved — the note names no area; the 55′-10″ values are printed at particular places |
| An inconsistent annotation | unresolved — 55′-2″ appears only in the general note; printing a value more often does not make it govern |

No revision explanation is established by this review. The summary states: "Level 2 elevation requires
review: the general datum note states 55′-2″, while the column schedule, a
local slab annotation and a section state 55′-10″. Their applicable areas have
not been fully reconciled." Every item opens its own highlighted source.

### Locate on plan

`GET /api/documents/{id}/locate?location=&schedule=` finds every plan view
printing both grid labels, reads the literal axes (C.1-5.1 is where the axis
labelled C.1 crosses the axis labelled 5.1; S122 dimensions C to C.1 as
3′-4⅞″ — a decimal is part of the grid name, never an offset), looks for the
column symbol at the crossing and places a printed offset perpendicular to
its own grid only at a validated / calibrated view scale (both axes' offsets:
all four sign combinations, placed only when exactly one holds a column).
States: column symbol identified · grid intersection identified, column not
confirmed · several candidates · offset direction or scale unresolved ·
relevant plan not found. Views titled for another building / area are listed
apart, never dropped. Table-only locations are scoped by the schedule that
shares the table's other rows (22 of 29 → OSSE BUILDING - GCS).

| Location | Default view | Result |
|---|---|---|
| C.1-5.1 | S121 | column symbol at the C.1 × 5.1 crossing (also S122, S123) |
| C.1(-6")-7.3 | S121 | column at the 6″ offset from C.1 (calibrated scale) |
| C.4(1' - 7 3/8")-7.5(-2' - 4 1/2") | S121 | column at one of four offset positions (S121, S122); S123 unresolved |
| D2.5-6.2 | S121 | column symbol (D2.5 is a printed grid next to D.2) |
| R14-RA.1 | S104 part plans | column symbol on several part plans, scope not established; P4 / F8.0 printed at the column |
| R13(5′-4″)-RA.1 | S104 | offset unresolved (S104 mixes view scales) |

### Model evidence

Representative columns were grouped by section + plate across all schedules
and the largest groups won, so early C locations filled the six slots and
table-only posts, missing plates and offsets never appeared. Now: complete
`I#` coverage counts per schedule / table first; examples grouped within each
schedule, chosen to cover each schedule, each section family, a table-only
location, an unresolved / not-shown plate and an offset location (8 max); the
Level 2 fact carries every source. Grounding now also rejects placing a
disagreement inside the schedule ("the schedule has conflicting elevations").


### Final verification of the completed source

- Backend: `python -m pytest tests --continue-on-collection-errors -q`:
  **1,855 passed, 10 skipped, 529 subtests passed, 1 collection error; exit 1**.
  `test_geometry_evidence_contract.py` cannot import `CompletionStatus` from
  `services.prediction.semantic_contract`. Running that file against current
  incoming baseline `e32cc5b` reproduces the identical error (collection exit 2).
  No new test failure remains. This gate includes the real-PDF reference sets,
  schedule/level/Locate tests, semantic and quantity regressions.
- Focused summary/quantity checks passed 80 tests before the final additional
  RC1 regression; that regression is included in the complete gate above.
- Frontend: **303 passed, exit 0**. Production build: **exit 0**, existing
  chunk-size warnings only. Changed JSX ESLint is clean; Ruff baseline comparison
  found no new findings (902 existing findings versus 918 on baseline files).
  `git diff --check` is clean. No repository lint config was added.
- Fifteen-drawing comparison: no differences in `schedule_mark_map`, production
  schedule rows, or raw column entries. Only display `cells` and `supports` are
  excluded. The recovered baseline command confirms main `e32cc5b`, clean
  backend diff and exit 0. The final comparison was rerun after the shared-reader,
  scope and skew-offset fixes. The subsequent RC1 change only compares display
  definition sizes and cannot affect those compared fields. See
  [machine-readable results](verification_20261007.json).
- Fresh OSSE summary construction: **3.319 seconds**. Isolated
  HTTP-layer Locate for C.1-5.1: **7.551 seconds cold; 0.011 seconds
  warm**. These measurements ran after the full suite and before model testing.
  They include actual geometry and route serialization, without changing live caches.
- Browser: fresh OSSE, Yellow Spring and Brandywine extractions through the
  final cache contract. C.1-5.1 highlights the literal S121 intersection; other
  plans can be selected. HSS assignment-only rows retain unknown levels and
  Locate works. R14/R13 candidates are on S104; R13 offsets remain unresolved.
  P1, RC1, general/local/schedule and section sources open the indicated pages.
  RC1's 24-inch dimensions agree; tie spacing is not a section dimension.
  Yellow Spring A-24 aligns on rotated p.13. Brandywine multi-location actions
  remain separate and E-8's negative offset is placed toward grid 7.
  An intercepted Locate failure displays an error, succeeds after reopening,
  and Escape returns keyboard focus. Interception was removed. No screenshot
  transforms or source-layout overrides were used.
- Reports regenerated from the final profile/code: **12 full-evidence pages**
  and **5 concise pages**, visually inspected. Full HTML tables contain exactly
  74 parking, 26 building and 7 assignment-only records. Concise mode states
  that 74 parking records and the rows of 11 supporting schedules are omitted.
  No navigation, clipped columns or installed-quantity labels appear in print.
- Summary LLM remains off in the UI (`llm_used=false`). Scripted model validation
  is separate evidence: one final Ollama run accepted its overview, three known
  fact IDs and one cross-source caution in 22.313 seconds, with no dropped claims
  or model error. Bracketed known IDs normalized correctly. This did not change
  the UI setting.

Final screenshots: [directory](screens/v3_scope_directory.png),
[level review](screens/v3_level2_review.png),
[assignment-only HSS](screens/v3_table_only_hss.png),
[parking preview](screens/v3_parking_preview.png).

Backups, logs, final API responses, source inspections and generated PDFs remain
outside the repository in the task's dated verification directory. The original
OSSE PDF and Claude audit directory are retained. Only intended source, tests,
small reference fixtures, documentation and screenshots are committed; runtime
training/document files, virtual environments and shared caches are excluded.

## Completed refinement — 2026-10-06

Continues the published `f0900c6` work on this feature branch; main remains
`9522744`. The earlier sections below describe that published checkpoint.
This section supersedes its masking limitation and verification numbers.

The rendered S601 beam header was checked before accepting the fixture:
**TOP BARS spans L.E. BARS and F.L. BARS only. R.E. BARS is printed under
STIRRUPS**, alongside SIZE, TYPE, SPACING and END. This is an unusual source
layout, preserved without engineering reinterpretation or expanded abbreviations.
See [the rendered source crop](crops/s601_beam_header_verified.png).

Resolved in this refinement:

- Framing-key labels reuse mask visibility and paint order. Opaque later white
  fills hide text; earlier backgrounds and transparent fills do not. Visible
  replacements, including multiple lines, establish their own meaning; partial
  labels stay unresolved. Normal line stacking keeps its original lower gap
  bound. Hidden wording is diagnostic, never an accepted LLM definition.
- Display heading paths follow merged-cell spans. Wall-footing TOP/BOTTOM and
  LONG/SHORT WAY remain separate. Trailing REMARKS require a matching heading,
  the nearest bounded right edge and both row rules; cross-row or neighbouring
  text is excluded. Highlight bounds include associated remarks.
- W23 shows 23″ width and SEE SECTION FOR REINFORCEMENT; both reinforcement
  cells stay blank. Beam coverage is **6 printed / 1 interpreted / 5 additional
  printed rows**. CB16X32 retains separate width, depth, bottom bars, top bars,
  stirrup fields and blank remarks. The five precast rows remain outside
  production steel definitions.
- Orientation is two sentences. Attention precedes steel columns, levels,
  notation, then supporting groups by purpose. Shared dimension roles replace
  repeated row explanations; Notes is omitted when empty. At 100% browser zoom
  (`visualViewport.scale=1`, device pixel ratio 1), main table values compute
  to 14px. Typography changes are local to the summary.
- The 8″ Level 2 conflict keeps 55′-10″/S602 and 55′-2″/S122. Roof evidence
  retains OFFICE. The unresolved 5¼″ from slab and 3″ from deck notes are linked
  to Level 2 and Roof respectively, without choosing above/below or calculating
  steel elevations.
- Search preserves printed grid IDs and expanded entries. CBP-3 and CBP-5 stay
  distinct despite equal dimensions. Plate dialogs list linked locations as
  references, not installed counts. Source tabs distinguish page **and bounds**;
  trace sources also carry location identity. Selecting another location clears
  old sources and invalidates late responses, including after unmount.

### Current verification

- Focused readers/evidence: 96 passed, 34 subtests. Real-drawing references and
  production guards: 154 passed, 46 subtests (exact locks, quantity safety,
  tracing, scale and level evidence).
- Frontend: 292 passed across 25 files; production build succeeds. Existing Vite
  large-chunk warning remains. Focused ESLint (recommended correctness rules,
  JSX-use tracking, React hooks) reports no errors or warnings on changed JSX.
- Ruff under the existing environment configuration: 765 findings in the changed
  Python files versus 778 at `f0900c6`; no findings on added/changed lines after
  review. Existing typing modernization, import-order, closure and style debt
  was not blanket-disabled or swept into this task.
- Full backend gate (`python -m pytest -q --continue-on-collection-errors`):
  **1828 passed, 10 skipped, 527 subtests passed, 23 warnings, one collection
  error**, in 333.12 s; actual pytest **exit 1**. Main's
  `test_geometry_evidence_contract.py` independently reproduces the missing
  `CompletionStatus` import (that single-file run exits 2). No test failures.
- All 15 PDFs: `schedule_mark_map`, complete production rows excluding only
  display `cells`, and column entry IDs/sections/plate statuses match `9522744`.
  Allowed changes are heading paths, remarks, display bounds, coverage, non-steel
  display definitions, and supported links for unresolved notes. Prediction and
  quantity paths have no code changes and retain regression coverage.

| Sequential 15-PDF stages | Main `9522744` | Refined feature |
|---|---:|---:|
| PDF extraction | 64.90 s | 65.74 s |
| Schedule grid | 128.44 s | 132.21 s |
| Summary construction | 21.49 s | 31.53 s |

Same interpreter, source files and comparison script; baseline and feature ran
sequentially on a shared development machine. These are observed timings, not
isolated benchmarks. Framing-key-only comparison against `f0900c6` reused the
same open PDF pages, one cold plus three warm reads: OSSE warm median
0.143 → 0.201 s; BCPS 0.720 → 1.030 s. Mask-aware visibility adds measurable
cost. There is no additional model call.

Fresh UI uploads/extractions use `3.26-summary-coverage`, paired 5184 → 8034,
and `/api/dev/identity` confirms this task worktree. Browser checks cover OSSE
coverage/blank cells, conflict comparison, source tabs, plates and tracing;
Yellow Spring rotated sources; and Brandywine multiple locations and offsets.
Escape restores focus to the launching source button; the comparison opens
with keyboard Enter. Light desktop and dark 800px layouts were inspected.
The settled [Yellow Spring highlight](screens/refined_yellow_rotated.png) lands
on A-24 on rotated PDF p. 13; the [Brandywine offset](screens/refined_brandy_offset.png)
lands on the column toward grid 7 on S121/p. 12. Browser error logs are empty.

| Before | Refined |
|---|---|
| [Original orientation](screens/before_top.png) | [Short orientation and attention](screens/refined_top.png) |
| [Previous narrow view](screens/after_narrow_800.png) | [Narrow dark layout](screens/refined_narrow_dark.png) |
| [Previous details](screens/after_details.png) | [Exact plate-source highlight and tabs](screens/refined_plate_source.png) |

Remaining limits: coverage counts extracted marked rows, not every possible
printed row or installed items. A wholly unrecognized table is not promoted by
this display layer. Remarks without sufficient row ruling remain unavailable.
The five precast beam rows need source review; blank reinforcement is unknown.
Mask interpretation depends on PDF text and paint geometry. Existing limits on
leaderless keys, building scope, wrapped location offsets, and phone-width app
navigation remain. No fabricated pieces, member lengths or installed stud/plate
counts are inferred. Model grounding/fallback and whole-fact omitted counts
remain tested; no new live model output is required for this deterministic UI.

Run this branch's preview from the repository root:

```powershell
node scripts/dev.mjs --frontend-port 5184 --backend-port 8034 --python <path-to-supported-python.exe>
```

Use Upload & Extract, then Drawing Summary. Existing uploads must be extracted
with the new cache version. Usual 5173/8000 services, Ollama and main are unchanged.
The preserved untracked OSSE document was copied outside the repository before
fresh extraction; verification logs and that copy remain in the local
`aidr-summary-verification-20261006` sibling directory, outside version control.

## What reproduced, and where it came from

Reproduced on a fresh extraction through the API (`summary_api
drawing_intelligence_v2`, cache `FRESH_DETERMINISTIC_RUN`, extractor
`legend_extractor_v6l-level-bands`) and in the browser
(`screens/before_top.png`, `screens/before_full.png`).

| Problem | Layer | Root cause |
|---|---|---|
| `C.1(-6")-7.3`, `C.1(-6")-7.5`, `C.5-7(6")` (S601) and `R13(5' - 4")-RA.1/RA.2` (S602) listed as "bottom of base plate" values | evidence classification | `plan_values` read every enclosed value on a page with the legend's `(##' - ##")` rule by shape alone; a bracket glued to a grid is that grid's offset |
| S001 key example `W18X40 [35] c=1 1/4" <+12'-3">` counted as a plan observation | evidence classification | the legend's own example was read like a plan value |
| T.O. ROOF: "No plan with a matching title states an elevation" although S123 states the office-roof datum 69'-4" | cross-reference matching | level keys had to be identical; `OFFICE ROOF` / `OSSE FACILITY ROOF PLAN` never equalled `T.O. ROOF` |
| T.O. SLAB LEVEL 1 "also titled on S101" (parking) | cross-reference matching | `… AND FIRST FLOOR PLAN` split dropped the PARKING qualifier; no building scope was applied |
| "Numbers in brackets … no note … defines them" | evidence classification | only sentence notes were searched; the S001 graphical key was not read |
| "The set distinguishes existing and new framing" | narrative | 9 generic "existing" words (soils, slabs, surfaces) + the abbreviation list's DEMO entry passed the threshold; no framing is tagged new |
| First screen dominated by concrete walls/piers/footings; parking listed with steel; "printed size, not a catalog section" for C1 | UI rendering | definitions grouped by component in extraction order; no material grouping |
| W1 `#4@12" O.C. E.F. #4@12" O.C. E.F.` (vertical and horizontal fused) | extraction (display) | ruled-table rows kept only the joined size text |
| LLM packet: 25 concrete definitions, no column / plate / level facts, cut mid-record | evidence contract | `evidence_packet` had no column or level facts and truncated with `[:max_chars]` |

## What changed

Interpretation (backend):

* `level_evidence.grid_location_offset` — an enclosed value touching a grid
  that parses as a grid intersection (`column_schedule.parse_grid_location`)
  is a location offset: kept with grid, signed value and printed text in
  `levels.location_offsets`, excluded from elevations. Standalone
  `(98' - 6")` is still an elevation.
* Legend examples inside a framing key's region → `levels.legend_examples`.
* Level matching reuses the tracing scope contract (`view_scope.ScopeResolver`):
  supported / candidate / excluded scope; qualifiers kept (`OFFICE`), set-wide
  project words (OSSE, FACILITY, schedule captions) treated as scope; a
  qualified name links only when the schedule has one level of that kind;
  surfaces compared like for like (slab / deck / steel); equal elevations
  never link anything alone. Empty states say what was (not) checked.
* `framing_key.py` — reads graphical keys from leader geometry: each callout
  part means the printed label its leader ends at. Placeholders (`[X]`) are
  read; parts without a leader stay undecoded; disagreeing keys are a conflict.
* `column_schedule` — a schedule note's material applies to the label family
  it names (`ALL C_ COLUMNS ARE PRECAST` → `C1`, `24"x24"`); other labels
  (`RC1`) get nothing. Schedules grouped steel / concrete.
* `schedule_grid` — non-steel ruled rows carry display-only `cells`
  (heading, group, text); `size_text` and the mark map are unchanged.
* Renovation claim needs framing named both existing and new (or `(E)/(N)`
  members), with pages.
* `summary_facts` — typed, sourced facts with stable ids: `X` conflicts
  (both values + both sources), `K` linked levels, `C` representative column
  → plate relationships (one per distinct section + plate; "a selection, not
  the schedule"), `M` materials, `G` grid-offset notation. The packet is
  built from whole facts and says how many were left out.
* `drawing_summary_llm` grounding also checks dimensions and elevations by
  value, grid locations, cut-off values, unbalanced brackets, and rejects
  resolving a conflict, calling a level difference a length, "installed"
  counts, confirmed placement, precast called steel, and a conflict placed
  inside one source.

Presentation (frontend): `lib/dimensions.js` (symbols, exact fractions,
spoken labels, Width × Length × Thickness), `drawingSummary/visuals.jsx`
(evidence chain, schematic level diagram, conflict comparison, plain
statuses), reading order A–F, side-by-side source comparison, labelled
concrete cells, parking under supporting schedules. MUI v9 ignores system
props, so `display` / margins on Typography now go through `sx`.

## OSSE after (sources)

| Item | Result | Source |
|---|---|---|
| T.O. ROOF 69'-4" | linked to S123 "top of office roof slab 69'-4"" (qualifier OFFICE shown), agrees; S102 (parking) excluded | `crops/s123_office_roof_datum.png`, S602 p. 26 |
| T.O. SLAB LEVEL 2 | **sources disagree**: schedule 55'-10" (S602 p. 26) / S122 plan note 55'-2" (p. 10), difference 8"; nothing chosen | `crops/s602_level2_schedule.png`, `crops/s122_second_floor_datum.png` |
| T.O. SLAB LEVEL 1 38'-0" | linked to S121, agrees; S101 (OSSE PARKING FOUNDATION AND FIRST FLOOR) excluded | S121 p. 9 |
| Grid offsets | C.1(-6")-7.3, C.1(-6")-7.5, C.5-7(6") (S601 p. 25); R13(5' - 4")-RA.1/RA.2 (S602 p. 26) — locations, not elevations | `crops/s601_location_offsets.png` |
| Framing key S001 | [35] = "# OF SHEAR STUDS. SEE TYPICAL DETAIL"; c=1 1/4" = CAMBER; <+12'-3"> = TOP OF STEEL ELEVATION RELATIVE TO DATUM; no bracket warning | `crops/s001_framing_key.png` |
| C.8-8.9 | W10X33; base plate CBP-2 Width 12″ · Length 18″ · Thickness ¾″ (S601 location table → BASE PLATE TYPE SCHEDULE); Level 1 → Roof, elevation difference 31′-4″ (calculated), fabricated length unconfirmed | `screens/after_details.png` |
| Parking | OSSE PARKING - GCS: 71 entries "Precast concrete · C1 / 24″ × 24″"; 3 RC1 entries printed text only | `screens/after_parking.png` |
| W1 | Width 12″ · Reinforcement·Vertical #4@12" O.C. E.F. · Reinforcement·Horizontal #4@12" O.C. E.F. | `crops/s601_concrete_wall_schedule.png`, `screens/after_walls.png` |
| Overview | no "existing and new framing" claim (basis: existing construction mentioned, framing not named both ways) | — |

Browser (5184 → 8034, `/api/dev/identity` = aidr-summary-osse,
`drawing_intelligence_v3`), 1440 CSS px and 800 CSS px wide, light and dark:
"View plate dimensions" opens S601 p. 25 with the box exactly on
`CBP-2 | 12" | 18" | 3/4"` (PyMuPDF text in the box); "Compare side by side"
opens S602 p. 26 and S122 p. 10, each with its own box; the conflict's
schedule source opens from the keyboard (Tab/Enter). Yellow Spring A-24 on
rotated p. 13 highlights the printed A-24 cell; 12 flagged elevations listed.
Brandywine C-4 +12 offers 13 separate tracing buttons; C-8(-4'-4") placed on
S121/S131/S141, candidate on S120/S130/S140.

## Optional LLM (Ollama llama3.1:8b, local)

Packet: 5,952 chars, whole facts, "16 further facts left out for length".
Final run (12.2 s): accepted C1, K1, M1, R1 notes; rejected G1 (restates its
fact), D2 (fragment `#4@12`), X1 (value cut off: `(55' - 10`), and the
overview ("The column schedule has conflicting values…" — the conflict is
between the schedule and a plan note), so the deterministic overview stands.
Deterministic output is complete with the model disabled.

## Verification

* Backend gate (backend/venv, Python 3.12.10): 1815 passed, 10 skipped,
  1 collection error — `test_geometry_evidence_contract` (imports
  `CompletionStatus`, removed upstream; same on `9522744`). Baseline 1795.
* Frontend: 287 passed; production build clean.
* 15 sets, `9522744` vs branch: `schedule_mark_map`, schedule rows (minus
  `cells`) and column entries identical on all 15.
* Performance (same machine, sequential, in-process stages over the 15 sets;
  traces repeated 3×):

  | | `9522744` | branch |
  |---|---|---|
  | PDF extraction (15 sets) | 47.6 s | 45.0 s |
  | schedule grid (15 sets) | 95.8 s | 89.4 s |
  | drawing summary build (15 sets) | 15.9 s | 20.0 s (+0.27 s / set; framing-key reading and scope resolution) |
  | OSSE cold extraction via API (forced) | — | 10.6 s |
  | trace C.8-8.9 (OSSE) | 1.36 / 1.40 / 1.25 s | 1.41 / 1.42 / 1.27 s |
  | trace C-8(-4'-4") (Brandywine) | 3.91 / 3.48 / 3.49 s | 3.84 / 3.38 / 3.39 s |

  The framing key opens only pages that print a key heading, and reads their
  vector paths only when an example callout is found (`get_cdrawings`). No
  extra LLM call is made: the summary model runs once per summary cache key,
  only when `DRAWING_SUMMARY_LLM_ENABLED`.

## Limitations

* Location offsets wrapped across text lines (S601 `C.4(1' - 7 3/8")-7.5(-2' - 4 1/2")`)
  are not listed as offsets (they were never misread as elevations; the
  column schedule parses them).
* Reading a framing key needs drawn leaders; a key drawn as text only stays
  undecoded (warning kept).
* Level association across buildings relies on sheet / view titles and datum
  notes; a set without them leaves levels "No linked plan evidence yet".
* The app shell keeps its sidebar at phone width (pre-existing); the summary
  itself was checked at 800 CSS px.
* Stud counts, high/low beams, fabricated pieces and member lengths are not
  inferred.

Follow-ups noted in review, deliberately not done here:

* Framing keys are read while the summary is built (re-opening the PDF for
  key-heading pages only); moving the read into the extraction pass would
  store them on the document like the column schedules.
* `framing_key._leaders` and `column_trace._leader_ends` both follow
  leaders; merging them would change tracing behaviour, so they stay apart.
* Resolved in the completed refinement: key labels now use `visible_phrases`;
  hidden/partial labels cannot establish meaning. The measured cost is above.
* Grounding is still pattern-based on the model's wording, scoped by the
  cited fact's type; rendering every value from the fact (model returns ids +
  wording only) would remove most of the patterns.
* Project-scope words for level names come from schedule captions plus words
  shared by three or more sheet titles; `ScopeResolver` could expose its
  resolved terms instead.
