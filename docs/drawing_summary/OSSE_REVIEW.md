# Drawing Summary review — OSSE (October 2026)

Branch `bassam/drawing-summary-osse`, from `9522744`. Primary drawing:
`07 - FEMS & OSSE/OSSE - ST.pdf` (26 pages). Display and evidence only —
prediction, the schedule mark map, exact catalog locks, QuantityEngine and
deduplication are unchanged (verified on 15 sets, below).

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
* Key labels are read from the raw text layer, not `visible_phrases` (which
  needs the slower full drawing pass); a masked key label would still count.
* Grounding is still pattern-based on the model's wording, scoped by the
  cited fact's type; rendering every value from the fact (model returns ids +
  wording only) would remove most of the patterns.
* Project-scope words for level names come from schedule captions plus words
  shared by three or more sheet titles; `ScopeResolver` could expose its
  resolved terms instead.
