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
symbol means absent; observed floors are one fabrication piece. Offsets are
not applied (plan scale not read); a plan page matched to several levels is
labelled so.

Building / area scope (`view_scope.py`): per view (plan title under the
view, else the title-block title next to "Title:"); a schedule is compared on
the words that distinguish it from the set's other column schedules
(BUILDING vs PARKING, not the shared OSSE). `conflicting` views are listed as
"not this building"; `consistent`, `supported_by_datum`,
`consistent_by_sheet_family` and `single_schedule` count; anything else is an
unresolved candidate. The FEMS logistics set (`42 - Logistics Building/ST.pdf`,
sheets `-L`) is another document; nothing is matched across documents.
