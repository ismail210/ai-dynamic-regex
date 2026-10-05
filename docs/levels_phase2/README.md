# Levels and elevations — Phase 2

Follow-up to the 2 Oct 2026 meeting (June, Mike), building on
[Phase 1](../column_schedule_phase1/README.md). Phase 2 reads level names and
elevations as independent evidence, ties them to the plans and schedule lines
that print them, and computes a vertical difference **only** when the evidence
establishes both ends.

Code: `backend/services/engineering/level_evidence.py` (new: parsing, plan
statements, derivations, level registry, difference); level lines, column
strokes and extents in `column_schedule.py`; rotated-page table reading in
`schedule_tables.py`; masked spot labels in `schedule_grid.py`; view
`drawing_intelligence` → `profile["levels"]` and
`profile["column_schedule"].entries[].extent / level_difference`; UI
`DrawingSummaryPanel.jsx` (section "Levels and elevations" and the
column-details "Vertical extent").

Display / evidence only. Prediction, `schedule_mark_map`, quantities (one per
prediction), locked exact matches, plate resolution and mask filtering are
unchanged; the mark map is identical to main on all 7 reference PDFs.
Cache keys bumped: `EXTRACTION_VERSION = "3.22-levels"`,
`EXTRACTOR_VERSION = "legend_extractor_v6j-levels"`.

## Reference set (visually verified)

PDFs are in `Testing Projects/` (not in git). Expected values:
`backend/tests/fixtures/column_schedule/reference_levels.json`, checked by
`tests/test_level_reference_set.py`. Crops are in `crops/`.

| Project | PDF · pages / sheets | Extracted (read) | Derived (by an explicit note) | Left unresolved / flagged |
|---|---|---|---|---|
| FEMS & OSSE | `07 - FEMS & OSSE/OSSE - ST.pdf` · p26 S602 schedules; p9–11 S121–S123 notes; p2 S001 legend | Building GCS: T.O. ROOF 69'-4", T.O. SLAB LEVEL 2 55'-10", LEVEL 1 38'-0", PARKING LOWER DECK 33'-0"; parking GCS 50'-0" / 41'-9 5/8" / 33'-0". Plan datums S121 38'-0", S122 55'-2", S123 69'-4". Legend: ( ) bottom of base plate, < > top of framing, { } top of pier, [ ] bottom of footing | — | **Conflict**: LEVEL 2 55'-10" (schedule) vs 55'-2" (S122 datum), shown side by side, neither chosen. S122 `<0'-5 1/4">` / S123 `<0'-3">` steel offsets "FROM top of slab/deck" — direction not stated → no value |
| Furley ES | `36 - Furley ES/Struct.pdf` · p7 S102A, p9 S102C, p10 S102D | Slab 14'-8" / 19'-4" (mech room) above datum | Top of steel 14'-3" (S102A, S102D) and 18'-8" (S102C mechanical room) = slab − 5" / − 8"; each keeps "unless noted (…)" with the count of local values (8 / 4 / 20) | Roof `(28.66')` values: read only where the roof-notes rule defines `( )` as top of steel from datum |
| Brandywine | `09 - Brandywine/Structural4.pdf` · p42–43 S600/S601; p11+ S120/S130/S140 | LEVEL 4 42'-0", 3 28'-0", 2 14'-0", 1 0", LOWER −5'-0"; plan slab/steel values | — | LEVEL 2/3/4 agree with S120/S130/S140. Notes "reference elevation … on sheet ____" have the sheet **blank** → flagged unresolved (S120, S130, S140, S400) |
| Burrville ES | `51 - Burrvile ES/ST-Burrville.pdf` · p28–29 S501/S502; p4 S101A, p7 S102A, p10 S103A, p13 S104 | UPPER ROOF 44'-6", MAIN ROOF 29'-0", UPPER LEVEL 14'-6", GROUND 0'-0"; datum conversions 0'-0"=97'-6", 14'-6"=112'-0", 29'-0"=126'-6", 44'-6"=142'-0" | Plan "at reference elevation" slab/deck → 0'-0", 14'-6", 29'-0", 44'-6" (all agree with the schedule) | Steel "at bottom of deck" (no deck depth stated) |
| Washington Latin | `01 - Washington Latin/New bldg - St.pdf` · p15 S202; p8–13 S100–S105 | Schedule prints SEE PLAN (masked originals not used). Plans: slab values; roof `T/DECK 372'-9"` (a masked `T/SLAB` under it is ignored) | SEE PLAN resolved to a single plan value: GROUND 299'-4", FIRST 314'-0", SECOND 330'-0", ROOF deck 372'-9". Steel = slab − 6 1/4" | THIRD (S103) and FOURTH (S104) — the plan shows 2 different values → not reduced to one |
| Fort Davis CC (negative control) | `08 - Fort Davis …/Structure - Copy1 - edit.pdf` · p15 S301 | Level names HIGH ROOF, LOW ROOF, 2ND, FOUNDATION; 2ND plan states TOS 281'-6" | — | Schedule prints **no** elevations → all levels "missing"; no differences computed |
| Yellow Spring (rotated 90°) | `00 - Yellow Spring/ST1.pdf` · p13–14 S2.09 schedule; p5, p8 plan notes | MECH. PENTHOUSE ROOF 42'-0", 3 ROOF 30'-8", 2 SECOND FLOOR AND LOW ROOF 15'-4", 1 FOUNDATION 0'-0"; slab +15'-4", penthouse slab 31'-1"; TOS / JBE / BOD prefixed values | Top of steel 14'-11" (p5) and 30'-8" (p8) = slab − 5"; second floor agrees with the schedule | Columns that run past a line are "below"/"between", never snapped |

MARS Arcadia has no PDF (DWG only), so it is not covered.

## Vertical differences (column schedule)

The schedule's horizontal level lines are read with their name (just above)
and elevation (just below). Each column's drawn vertical stroke is classified
at its top and bottom as `at` (within 3 pt of a line), `between` (with a
"drawn just below / above X" hint within 8 pt), `above` or `below`. A
**level-to-level difference** is shown only when both ends are `at` lines with
parseable elevations. It is the difference between two printed level
elevations and is **not** a column length. Row spacing and NTS geometry are
never used.

| Document | Entries with an extent | Computed | Example |
|---|---|---|---|
| OSSE | 100 | 2 | C.8-8.9: T.O. ROOF 69'-4" − T.O. SLAB LEVEL 1 38'-0" = 31'-4"; D.3-11 (parking) 17'-0" |
| Yellow Spring | 135 | 1 | P-21 W8X24: 3 ROOF 30'-8" − 2 SECOND 15'-4" = 15'-4" (`crops/yellowspring_p13_P-21_line_to_line.png`) |
| Brandywine / Burrville / WL / Fort Davis | 105 / 120 / 42 / 7 | 0 | strokes end off the lines, or the lines print SEE PLAN / no elevation |

## Before / after (main 1ee323b → this branch)

| | Before | After |
|---|---|---|
| Level name ↔ elevation | raw row labels, not paired | paired per drawn line (7 documents) |
| Plan elevations | none | read / derived / unresolved with rule, inputs, scope, exceptions |
| Schedule ↔ plan link | none | by level key (ordinal, kind); agrees / differs / conflict exposed |
| SEE PLAN | not resolved | resolved only to one distinct plan value |
| Column vertical extent | none | at / between / above / below per end; difference only at/at |
| Yellow Spring S2.09 | not read (rotated) | read on the displayed page; highlights aligned |
| Mark map / quantities | — | unchanged (identical on all 7 PDFs) |

## Parsing rules

Feet-inches, mixed fractions, decimal feet (two decimals required, so the grid
`8.1'` is not an elevation), explicit signs, values split across spans,
typographic quotes. Parentheses/brackets keep their meaning as an enclosure and
never make a value negative. Bracketed values are read only where that sheet's
note or the project legend defines the bracket; TOS has no universal meaning.
Slab, deck and steel are separate surfaces; steel is derived only inside the
offset note's own block/heading scope, and the "unless noted" exceptions on that
sheet are counted and shown.

## UI

Upload & Extract → Extract drawing → Drawing Summary → **Levels and
elevations**: one table per schedule (level, printed elevation, status,
matching plans with agrees/differs, source buttons), "Elevations stated on
plans" (surface, value, how it is established, derived inputs, exceptions),
datum relations and project notations. Column schedule → Show details →
"Vertical extent drawn in the schedule".

## Limitations

- Rotated sheets: sheet ids (S2.09) and plan titles are split into vertical
  text runs, so YS sheet ids are missing and titles truncate ("ROOF FRAMING
  PLAN" for the second-floor plan). Phase 1 word boxes on rotated pages stay
  in unrotated coordinates (pre-existing).
- Malformed values such as `TOS (+30'-8)` (no inch mark) are not read.
- Level ↔ plan matching uses names only; plans with no ordinal/kind in the
  title are not matched.
- Most drawn column strokes do not start and end exactly on level lines, so
  few differences are computable from schedules alone.

## Next priority

Trace each column through the plans (grid location on each framing plan)
to establish start/end levels where the schedule's drawn extent does not;
read rotated sheet ids/titles; read malformed values with a flagged status.
