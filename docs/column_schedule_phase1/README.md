# Column schedules, grid locations and plates — Phase 1

Follow-up to the 2 Oct 2026 meeting (June, Mike). Phase 1 priority: correct
column section/type, correct grid location, correct associated base plate,
useful notes and traceable sources. Positioning, heights and 3D come later.

Code: `backend/services/engineering/column_schedule.py` (new), table detection in
`schedule_tables.py`, wiring in `schedule_grid.attach_schedule_grid`, display
view `drawing_intelligence` → `profile["column_schedule"]`, UI
`frontend/src/components/DrawingSummaryPanel.jsx` (section "Column schedule").

`document["column_schedules"]` is display / evidence only. Prediction, the
schedule mark map and quantities never read it; `schedule_mark_map` is
identical before and after this change on every reference PDF (asserted in
`tests/test_column_schedule_reference_set.py`).

## Reference set (visually inspected)

PDFs are under `Testing Projects/` (not in git; tests read
`ESTIMA3D_TESTING_PROJECTS`). Expected values live in
`backend/tests/fixtures/column_schedule/reference_set.json`; crops in `crops/`.

| Project | File | PDF page · sheet | What it shows | Variation / ambiguity |
|---|---|---|---|---|
| Fort Davis CC | `08 - Fort Davis Community Center/Structure - Copy1 - edit.pdf` | p15 · S301 "Steel and Concrete Column Location Plan and Schedule" | COLUMN SCHEDULE, marks C-1…C-7 across the top, row labels on the **right** (MARK/FLOOR, levels, BASE PLATE, ANCHOR BOLTS, REMARKS) | **Negative control**: C-2 is a mark placed on the location plan, not grid C × grid 2 (plan grids are 00–12 with leading zeros, A–I, C.7, 10.7). C-1 and C-2 share HSS10X10X5/16 but have different plates (18"x18"x3/4" vs 18"x18"x1"). |
| Brandywine K-8 | `09 - Brandywine/Structural4.pdf` | p42 · S-600, p43 · S-601 | Graphical COLUMN SCHEDULE in 4 blocks over two sheets; BP leader marks at column bases; BASE PLATE SCHEDULE on p43 | Up to 13 locations per column; `A.1'-18`, double-prime `F"-1"` (plan p11 prints grids F" and 1"); signed offsets `C-8(-4'-4")`, `C.6(1'-10")-1`; plate dims split across THICKNESS / WIDTH / LENGTH cells with a second THICKNESS under PLATE WASHER; transfer columns O'-7', Q'-7' start at an upper level with no BP. |
| Washington Latin | `01 - Washington Latin/New bldg - St.pdf` | p15 · S-202 (detail sheet p14 · S-201) | STEEL COLUMN SCHEDULE, 2 blocks | Locations printed top **and** bottom; two section tiers; BRACE FRAME COLUMN notes; base plate `D/S-201` (detail reference) or feet-inch sizes `1 1/4"x14"x1'-2"`; edited PDF: elevations `314' - 0"` etc. under white boxes with `SEE PLAN` typed over, and the original Revit location row masked under the SERVICE LOAD row. |
| FEMS & OSSE | `07 - FEMS & OSSE/OSSE - ST.pdf` | p26 · S-602-O, p25 · S-601-O | Two graphical schedules on one sheet: OSSE PARKING – GCS (3 continuation blocks, precast) and OSSE BUILDING – GCS | Decimal grids `C.1-5.1`; offset `R13(5' - 4")-RA.1`; plates only via a location-keyed BASE PLATE SCHEDULE (`C.1-8.1 | W12x53 | CBP-4`) and then the BASE PLATE TYPE SCHEDULE (WIDTH | LENGTH | THICKNESS — the opposite order to Brandywine). |
| Burrville ES ("Burvey") | `51 - Burrvile ES/ST-Burrville.pdf` | p28 · S-501, p29 · S-502 | Revit schedule continued on the next sheet | Both grids primed (`H.4'-5.8'`); plates `1"x18"x18" *` with a note marker; mixed number split across text objects (`1` + `1/4"x18"x18"`). |
| Furley ES (Grimm + Parker, `Struct.pdf`) | `36 - Furley ES/Struct.pdf` | p2 · S002 | Conventional MARK \| SIZE \| BASE PLATE table; separate BEARING PLATE SCHEDULE BP1–BP7 | BP marks are **bearing** plates here, not column base plates; BP7 "SEE S/S502"; HSS cap plate defined only by note 1 (5/8" thick, U.N.O.); `20"x14"x1-1/4"`. |

Not available: **MARS Arcadia** (only DWG files in `02 - MARS Arcadia`, no
PDF) — its overlapping-text example is not covered. **Yellow Spring S2.09**
(`00 - Yellow Spring/ST1.pdf` p13–14): pages are stored rotated 90°, so the
schedule tables are not read yet. No reference sheet has a genuinely blank
plate cell; blank / not-applicable handling is covered by synthetic tests.

## What is read now

Per schedule column: mark **or** printed location text; parsed grids (names
keep decimals, primes and leading zeros), offsets (value, sign, unit, grid;
direction left unresolved); listed-location count (evidence, never a
quantity); repeated top/bottom label; section(s) per tier — designation only
for an exact AISC catalog match, otherwise the printed text; plate as one of
`read` (dimensions as printed), `resolved` (leader mark or location table →
plate schedule, dimensions labelled by that schedule's headings), `reference`
(detail id + sheet + resolved PDF page; dimensions not read), `blank`,
`not_applicable`, `not_shown`, `unresolved`, `conflict`; plate type from the
schedule heading (base / bearing / cap); cap plates from schedule notes;
notes (BRACE FRAME COLUMN, remarks); text hidden under white masks (kept as
evidence, never used as a value); source page, sheet and box for every value.

## Next phase (mapped, not started)

1. **Levels and heights** — `levels` already keeps raw level-row labels per
   schedule. A row band pairs one line's elevation with the next line's name,
   so names and elevations are not paired yet. Needed: level names
   independent of columns, project names matched to plan titles, elevations
   beside schedule lines / symbols / plan notes, "SEE PLAN for actual level"
   (Washington Latin — the masked elevations show the original values but are
   not the visible source), datum / units / reference surface (TOS vs TOSL)
   and offsets between them, several elevations per plan, column endpoints
   between named levels, missing bottoms, unscheduled columns, tracing a
   column through successive plans. Never one "level" field per column.
2. **Calibration** — keep NTS / scale; never measure NTS schedule spacing.
3. **Bent plates** — full strings, thickness-only, dimensions from another
   section, CONT / orientation / spacing / referenced L; own schema.
4. **Mark-based location plans** (Fort Davis S301) — read tag → nearest grid
   intersection from the plan geometry; until then marks stay unresolved.
5. **Repeated appearances** across schedules, framing plans and frame
   elevations (no equal-label / equal-grid identity assumptions).
6. Rotated pages (Yellow Spring), and promotion of mark-keyed matrix marks
   (Fort Davis C-1…C-7) into `schedule_mark_map` behind a flag with a
   measured before/after takeoff — deliberately not done in Phase 1.
7. High / low beams as words or elevations (deferred by Mike).
