# Levels Phase 2 + partner schedule work — integration and next steps

Branch `bassam/levels-elevations-phase2` = our Phase 2 (`559c7f5`) merged with
`origin/main` `55e363b` (partner `a4003ad`, `14d12d9`, `55e363b`; merge
`7016493`, no textual conflicts), followed by the integration fixes and the
column-tracing pilot. See [README.md](README.md) for Phase 2 itself.

## Test environment (why 25 failures were reported here and 0 on the partner's Mac)

Supported interpreter: `backend/venv` (README; `scripts/dev.mjs` tries it
first). Python 3.12.10, fastapi 0.139.2, pymupdf 1.28.0, pytest 9.1.1,
numpy 2.5.3. Command: `python -m pytest -q --continue-on-collection-errors`
from `backend/`.

Clean `origin/main` (`55e363b`) checkouts, same interpreter:

| Checkout / mode | Result |
|---|---|
| Windows default (`core.autocrlf=true`, cp1252) | 25 failed, 1 collection error |
| LF checkout (`git -c core.autocrlf=false worktree add`) | 11 failed |
| LF + `PYTHONUTF8=1` (what macOS/Linux give by default) | 9 failed, 1 error |

Demonstrated causes and their fixes (separate commits):

| Cause | Tests | Fix |
|---|---|---|
| SHA-pinned gold / frozen research files checked out as CRLF | 14 | `.gitattributes` `eol=lf` for exactly those text files (`dadc933`); all were already stored LF, no expected hash changed |
| `read_text()` without `encoding=` (cp1252) | 2 | explicit UTF-8 in tests (`b9e7179`) |
| path assertion with `/` | 1 | `as_posix()` (`b9e7179`) |
| A2/A7 tests read the live review files, which reviewers fill in (the committed A2 file already had 2 answers) | 6 | logic tested on a deterministic unanswered copy; live file checked as "unreviewed rows stay null" + valid (`6116e83`) |
| E5 holdout PDFs live in git-ignored `backend/uploads` | 1 | metadata stays strict; presence is a separate check that skips with the missing names (`6116e83`) |
| evaluator schema 2.0 dropped `predicted_aggregates` | 1 | same intent: `predicted_total == 0`, no extra elements (`6116e83`) |

Not fixed (product change, not a harness defect): `test_geometry_evidence_contract.py`
cannot import — `services/prediction/geometry_evidence_fixtures.py` (added
`f792d9c`) uses five names (`CompletionStatus`, `GeometryAssociationStatus`,
`GeometryRelationship`, `SemanticEvidence`, `SemanticOperationKind`) that
the unified semantic model (`ffe247b`) removed. Present on `origin/main`;
only that test imports the module, so no production impact. Porting it
means redesigning that synthetic geometry-evidence contract.

Why the partner reported 0 failures is not established from this machine;
the macOS defaults (LF, UTF-8) account for 16 of the 25.

Branch after these commits, Windows default checkout, no `PYTHONUTF8`:
**1779 passed, 0 failed, 1 error (above), 10 skipped**. Frontend: 267 tests,
build clean.

## What the integration changed, and why

1. **Our Phase 2 had changed production.** Reading tables on rotated pages
   also fed `schedule_grid`: BCPS City College (`53 - BCPS City College/ST.pdf`,
   every page `/Rotate 90`) gained LS1–LS5 in the mark map, Project Renegade
   +341 rows (1.1 s → 25.8 s), Yellow Spring +114 rows. Now
   `read_ruled_tables` reads every page as stored (exactly main) and
   `read_rotated_column_schedules` reads rotated column schedules for
   evidence only. Against `origin/main` on 15 PDFs the mark map is identical
   everywhere; the only row differences are plate metadata (item 4).
2. **One coordinate contract** (`backend/services/engineering/page_space.py`):
   stored geometry is PDF space; Drawing Summary sections convert once, at
   their boundary. This aligns Phase 1 column-schedule / definition
   highlights on rotated pages and puts sheet ids in the displayed title strip
   (Yellow Spring S0.01–S4.06; S2.09 on p13). Conversions are tested against
   PyMuPDF's rendering of 0/90/180/270.
3. **Level evidence** reads notes as displayed; `NOTES` is a word (Yellow
   Spring note 4 "c=0 DENOTES CAMBER" is not a heading); wrapped plan titles
   are joined ("PARTIAL FLOOR AND / ROOF FRAMING PLAN" on S2.01).
4. **Headed plate dimensions** (plate schedules only): feet-inch cells under
   THICKNESS / WIDTH / LENGTH are recognised with the printed text kept and
   `dimension_inches` beside it; PLATE WASHER / ANCHOR groups are not plate
   dimensions (same rule as the Drawing Summary plate table); a heading printed
   twice without groups stays unresolved. Brandywine S601 p43 BP1–BP9:
   `unresolved` → `present` (BP1 1 1/4" × 1'-6" × 1'-6"; before, the washer's
   1/4" was taken as the thickness). Columns under another part's group
   (PLATE WASHER, ANCHOR ROD, COLUMN WELD) are `plate_accessories`, so BP1's
   `plate_text` is the plate's own cells `1 1/4" 1'-6" 1'-6"` (was the washer
   Ø `2 3/4"`); OSSE S601 p25 `SIZE WIDTH` is the width (CBP-2 12" × 18" ×
   3/4", `plate_text` `12" 18" 3/4"`; before, width was empty and 12" was
   `size_text`). Footing / pier / wall rows and row selection are unchanged.
5. **Level bands: printed parts + explicit pairing.** A Revit band label is
   "elevation of the line above + name of the line below" (verified on the
   rendered schedules): Springhill S501 p26 `14' - 0" FIRST FLOOR` (118 rows)
   = SECOND FLOOR's elevation + FIRST FLOOR's name; Burrville S501 p28
   `29' - 0" UPPER LEVEL` (117 rows) = MAIN ROOF's + UPPER LEVEL's. Rows now
   carry `level_band` (see migration below); the canonical `level_band.level`
   is set only when one drawn line prints both parts.
6. **Malformed values.** `TOS (+30'-8)` (Yellow Spring S2.04 p8 ×9, S2.05 p9
   ×3) is shown as printed with a flagged 30'-8" candidate, never a value. The
   `TOS (…)` abbreviation is defined on S2.01 and applied to other sheets only
   because no sheet defines it differently; the defining sheet is shown.

Cache keys: `EXTRACTION_VERSION = 3.24-level-bands`,
`EXTRACTOR_VERSION = legend_extractor_v6l-level-bands` (the partner's
schedule-grid change had not bumped either).

Production against `origin/main` on the 15 reference PDFs: the mark map is
identical on all 15; marks, sections and `catalog_valid` are identical row by
row. Intentional metadata changes only: 473 grid-location rows replace the
three flat level fields with `level_band`; 18 plate-schedule rows (OSSE
CBP ×9, Brandywine BP ×9) get corrected plate text / dimensions / accessories.

## Migration for schedule-row consumers (`schedule_grid` rows)

| Before (`55e363b`) | Now | Meaning |
|---|---|---|
| `level` | `level` (unchanged) | the printed band label, raw |
| `level_elevation_text` | `level_band.printed_elevation` | elevation text printed in the band |
| `level_name` | `level_band.printed_name` | name text printed in the band |
| `level_elevation_status` | `level_band.prefix_status` | `present` / `absent` / `unresolved` leading feet-inch prefix |
| — | `level_band.pairing` | `unresolved` (no drawn-line evidence), `unpaired` (parts belong to different lines), `paired` (one line prints both), `ambiguous` (reads more than one way; `candidates`) |
| — | `level_band.elevation_of` / `name_of` | the level line each printed part belongs to: `{text, level, elevation_text, page, bbox}` |
| — | `level_band.level` | canonical level `{name, elevation_text}` — **only** when `paired`; never pair `printed_elevation` with `printed_name` yourself |
| `plate_text` (plate schedules) | `plate_text` | the plate's own cells in printed order (no accessory text) |
| — | `plate_accessories` | `[{part, heading, role, text}]` for washer / anchor rod / weld columns |
| — | `parsed_plate.dimension_inches` | numeric inches per role beside the printed `dimensions` (plate schedules only) |

The flat level fields were removed because nothing outside `schedule_grid`
read them; keeping them would invite the wrong pair.

## Column tracing pilot

`GET /api/documents/{id}/column-trace?location=&schedule=`, or **Show
details → Look for this column on the plans** in Drawing Summary. Evidence
only, computed on request (≈1 s OSSE, ≈3 s Yellow Spring).

| Column (schedule) | Levels spanned (schedule extent) | Plans and what is at the grid intersection |
|---|---|---|
| OSSE C.8-8.9 W10X33 (S602 p26, BUILDING GCS) | T.O. ROOF 69'-4" → T.O. SLAB LEVEL 1 38'-0", both ends on lines | S123 p11 (scope: datum note — OFFICE ROOF 69'-4"): symbol, nearby 69'-9" box (meaning not stated); S122 p10 (scope: sheet family "OSSE FACILITY"): symbol; S121 p9 (scope: datum — FIRST FLOOR 38'-0"): symbol, pier P1, footing F4.0B [28'-6"]; **S101 p5 excluded**: "OSSE PARKING FOUNDATION AND FIRST FLOOR PLAN" is the parking building despite the shared "FIRST FLOOR" |
| Yellow Spring P-21 W8X24 (S2.09 p13, rotated) | 3 ROOF 30'-8" → 2 SECOND FLOOR AND LOW ROOF 15'-4" | S2.01 p5: no symbol detected; "POST UP" leader ends at the column → supports the bottom end; S2.04 p8: symbol, grids cross twice (both listed); S2.05/S2.06: grid lines not found |

Crops: `crops/trace_*.png`. Never assumed: equal sections or equal grid names
across buildings identify a column; the lowest plan is the foundation; no
symbol means absent; observed floors are one fabrication piece. A plan page
matched to several levels is labelled so. Offsets: see milestone B below.

Building / area scope (`view_scope.py`): per view (plan title under the
view, else the title-block title next to "Title:"); a schedule is compared on
the words that distinguish it from the set's other column schedules
(BUILDING vs PARKING, not the shared OSSE). `conflicting` views are listed as
"not this building"; `consistent`, `supported_by_datum`,
`consistent_by_sheet_family` and `single_schedule` count; anything else is an
unresolved candidate. The FEMS logistics set (`42 - Logistics Building/ST.pdf`,
sheets `-L`) is another document; nothing is matched across documents.

## Milestone B — view scale, offsets, continuation notes (pilot, evidence only)

Nothing here feeds prediction, the mark map, quantities or takeoff; the trace
is computed on request and extraction is unchanged (no cache version bump).

**View scale** (`view_scale.py`, per view, never per sheet):

| Status | Meaning | May place an offset |
|---|---|---|
| `validated` | scale printed under the view title agrees (±2 %) with ≥3 printed grid dimensions | yes |
| `calibrated` | no printed scale; ≥3 grid bays agree (±1 %) on points per inch | yes |
| `printed` | printed under the title, nothing to check it against | candidate only |
| `conflicting` | printed and measured disagree | no |
| `nts` | NTS printed under the title | no |
| `unresolved` | neither; the title-block scale (`drawing_scale`) is recorded and never used alone. Also when the sheet repeats a grid name in one direction (several views) and no scale is printed for the view | no |

Conversion: `points = |printed inches| × points_per_inch`; one real inch at
1/8" = 1'-0" is 0.75 PDF pt (72 / 96). Rotation preserves distances, so the
value holds on rotated pages. Calibration = perpendicular distance between two
adjacent parallel grid lines / the full feet-inch dimension printed between
them (`12'-0"`; a primed label such as `7'` is not a dimension).

Brandywine: S120/S130/S140 print `1" = 20'-0"` under the overall-plan titles
while every title block says `1/8" = 1'-0"` → `printed` (the title-block
value is reported, not used). Area plans S121/S131/S141, S123/S133, S124 →
`validated` by 13–14 bays at 0.75 pt/in.

**Offsets.** Grid lines are found as general lines (`n·p = c`, any angle;
Brandywine's slanted grids), crossings by intersection. A printed offset is
measured perpendicular to its own grid on both sides; the printed sign is not
taken as a screen direction. A side is named by the next parallel grid it
heads toward. Status: `placed` (column drawn on exactly one side, scale
validated/calibrated), `candidate` (same, scale only printed),
`unresolved_direction` (drawn on both or neither side), `unresolved_scale`,
`unresolved_two_offsets` (both grids carry an offset). A level counts as
observed for an offset location only when the offset is `placed`.

| Location | Result | Crop |
|---|---|---|
| Brandywine C-8(-4'-4") | placed on S121/S131/S141 toward grid 7 (39 pt = 52" × 0.75); candidate on S120/S130/S140 (1"=20' printed only) | `crops/B_C8_S121_placed.png` (red = placed, blue = crossing) |
| Brandywine K.2'-13'(-9'-4") | placed on S123/S133 toward grid 12'. The symbol at the crossing itself is the schedule's separate K.2'-13' location; each trace attributes only its own symbol | `crops/B_K2_13_S123_placed.png` |
| Brandywine T.2'-7'(3'-8") | placed on S124 toward grid 8'; the plan's own 3'-8" dimension confirms it; candidate on S120 | `crops/B_T2_7_S124_placed.png` |

Browser check (5183/8033): S121 "Toward grid 7 (column drawn)" opens PDF p. 12
with the red box at (0.6652, 0.4628) of the page; the API box is (0.6653, 0.4634).

**Ends and continuation notes.** End states still come only from the
schedule's level lines. A note whose leader ends at the column (for an offset
column: at the placed side) is listed under `directional_evidence` with its
direction (UP/ABOVE/OVER = up; DOWN/BELOW/UNDER, TOP OF COL, T.O. COL = down).
It supports an end only on that end's own level and in its own direction.
Brandywine O'-7': bottom LEVEL 2 established, "S124 COL UP" listed as upward
continuation, top unresolved (no stop is invented) — `crops/B_O7_S124_col_up.png`.
One logical stack per location; splices / fabricated pieces are not inferred.

Multi-location schedule entries (Brandywine lists up to 13 locations in one
column) are traced one location at a time from Drawing Summary.

Tests: `tests/test_view_scale.py` (printed/NTS/title-block/validated/
conflicting/calibrated/several views/slanted/rotation; synthetic plans for
placed, both sides, neither side, printed-only candidate, no scale; slanted
crossings) and the Brandywine traces in `test_level_reference_set.py`.

## Drawing Summary review (OSSE, October 2026)

Full write-up: `docs/drawing_summary/OSSE_REVIEW.md`. Contract changes for
partners (all additive; `summary_api` is now `drawing_intelligence_v3`, and
`EXTRACTION_VERSION` / `EXTRACTOR_VERSION` were bumped so caches rebuild):

| Field | Change |
|---|---|
| `levels.noted_on_plans` | no longer includes grid-location offsets (`C.1(-6")-7.3`) or a legend's own example |
| `levels.location_offsets` (new) | `{location, grid, offset{raw, inches}, text, context, page, sheet, bbox}` |
| `levels.legend_examples` (new) | values inside a framing key's own example |
| `levels.schedule_levels[]` | `association` (`linked` / `checked_no_value` / `unresolved`), `association_note`, `surface`, `excluded_scope[]`; each `plan_matches[]` gains `association` (`supported` / `candidate`), `scope`, `name_relation`, `plan_qualifiers`, and values gain `inches`, `name`, `compared` |
| `interpretation_rules[]` | a `notation key` rule (`kind: framing_key`) with `parts[]` read from the key's leaders |
| `unresolved[]` | `undefined_bracket_tag` only when no note and no framing key defines the bracket; `conflicting_bracket_definition` when keys disagree |
| `column_schedule.schedules[]` | `material_group` (`steel` / `concrete` / `unclassified`), `entry_count` |
| `column_schedule.entries[]` | `material` (`{status: read, material, mark, size, source}` from a schedule note, or `{status: catalog section, material: steel}`) |
| `definitions[]` | `schedule_title`; non-steel ruled rows carry `cells[] {heading, group, text}` |
| `schedule_grid` rows (non-steel kinds) | display-only `cells[]`; `size_text`, marks and the mark map are unchanged |
| `existing_new` | `is_renovation` needs framing named both existing and new (or `(E)`/`(N)` members); `basis`, `pages` |
| `facts[]` (new) | typed, sourced facts `X`/`K`/`C`/`M`/`G` for the optional summary model |

### Completed summary refinement (2026-10-06)

Cache versions: `3.26-summary-coverage` and
`legend_extractor_v6n-summary-coverage`. The API remains
`drawing_intelligence_v3`. These additions are display evidence:

| Field | Meaning |
|---|---|
| Ruled table `header_paths[column]` | Printed parent-to-leaf headings, reconstructed from actual merged-cell spans; existing production `header` remains unchanged |
| Ruled table `trailing_column` | REMARKS only when its header, nearest right edge, and each row's top/bottom rules establish the association; `cells` and optional per-row `bboxes` |
| Grid/display `cells[]` | `{heading, group, path, text, bbox?}`; a blank stays empty. Old profiles fall back to their existing heading/group labels |
| Grid `printed_rows`, `unread_rows[]` | Number of extracted body rows with a printed mark, plus source rows rejected by production mark selection; never installed quantities or production definitions |
| Summary `supporting_schedules[]` | `{title, kind, page, sheet, bbox, printed_rows, extracted_rows, unread_rows}`. `extracted_rows` counts displayed interpreted definitions. Unknown printed totals remain unknown |
| Summary `definitions[].reference` | Printed referral wording, such as W23's SEE SECTION; no reinforcement is inferred |
| Unresolved `levels.plan_elevations[].levels` | Supported schedule-level references `{schedule_id, name}` linked through that plan, without calculating an elevation or choosing an offset direction |
| Framing-key `parts[]` | Hidden/partially hidden labels remain unresolved; `hidden_text` is diagnostic only. Only visible definitions enter accepted rule text and the LLM facts packet |

Display row/source bounds include bounded trailing remarks. The raw production
row fields, row selection, mark map, quantity engine, prediction and exact locks
are unchanged. OSSE's five precast beam rows remain supporting evidence only.
The rendered S601 source actually groups R.E. BARS beneath STIRRUPS; TOP BARS
covers L.E. and F.L. only. The fixture preserves this unusual printed hierarchy.

Source tabs use page, bounds, mark/id and selected location as identity. Same-page
assignment and dimension regions remain distinct. Tracing one location clears
previous plan sources; stale responses and responses after unmount are ignored.
Offset sides retain their own boxes. Existing page rotation conversion is reused.


### Drawing Summary completion (2026-10-07)

This work continues `e32cc5b` on `bassam/drawing-summary-osse`; publication is
feature-only. See `docs/drawing_summary/OSSE_REVIEW.md` for evidence and results.

Cache contracts: extraction `3.29-summary-locate-review`, legend profile
`legend_extractor_v6s-summary-locate-review`; summary API remains
`drawing_intelligence_v3`. Re-extract via the existing extraction route to
refresh both contracts; no cache-directory deletion is needed.

New display data: `display_schedule_grid`, column `supports` and `definition`,
assignment-only schedules (`source: location_table`, explicit unknown extent),
per-schedule `coverage`, `location_tables`, `plate_tables[].unused_marks`, and
`level_reviews` with separately sourced observations and unresolved explanations.
These fields never enter production mark resolution or installed quantities.

`GET /api/documents/{id}/locate?location=...&schedule=...` is level independent.
It reuses existing axis, symbol, scope and scale readers. The bounded backend
context cache is keyed by document artifact modification time and extraction
version. Cached geometry contains values, not live PDF pages or documents.
The frontend cache is scoped to the current profile and refreshes after a new
extraction response, including the same document id.

`GET /api/documents/{id}/page-crop?page=...&x0=...&y0=...&x1=...&y1=...&width=...`
uses one-based pages and display-space coordinates. Empty/non-finite regions
return 422, unknown documents/pages 404; output dimensions are bounded to
1200px. Both new routes use existing access middleware and registered-document
resolution. Preview blobs are fetched with authorization and released on cleanup.

The standalone summary report route offers concise/full modes independent of
accordion state. Concise mode states its omissions; full mode lists all display
entries. Neither mode calls printed-record counts installed quantities.
