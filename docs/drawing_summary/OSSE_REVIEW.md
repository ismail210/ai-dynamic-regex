# Drawing Summary review — OSSE (October 2026)

Branch `bassam/drawing-summary-osse`, from `9522744`. Primary drawing:
`07 - FEMS & OSSE/OSSE - ST.pdf` (26 pages). Display and evidence only —
prediction, the schedule mark map, exact catalog locks, QuantityEngine and
deduplication are unchanged (verified on 15 sets, below).

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
