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

Clean `origin/main` checkouts, same interpreter:

| Checkout / mode | Result |
|---|---|
| Windows default (`core.autocrlf=true`, cp1252) | 25 failed, 1 collection error |
| LF checkout (`git -c core.autocrlf=false worktree add`) | 11 failed |
| LF + `PYTHONUTF8=1` (what macOS/Linux give by default) | **9 failed, 1 error** |

* 14 failures: SHA-pinned gold files (`docs/validation/...gold_outcomes.jsonl`,
  accuracy gold) are rewritten to CRLF on checkout; the committed blobs match
  the expected SHAs. The repo has no `.gitattributes`.
* 2 failures: `read_text()` without `encoding=` (cp1252 on Windows).
* Remaining 9 + 1, on any machine from the committed tree:
  `test_geometry_evidence_contract.py` imports `CompletionStatus`, which the
  tracked `semantic_contract` shim removed; `a2_human_review_70.json` has 2
  answered rows while its 6 tests expect none; a test needs an untracked
  upload (`uploads/ST - Springhill Lake__…pdf`); a path test expects `/`
  separators; `test_repeated_detail_linker` reads a `predicted_aggregates`
  key `evaluate_against_excel` does not return. The partner's 0-failure run
  must come from local working-copy state that is not in git.

Integrated branch, same mode: **1756 passed, the same 9 failed + 1 error**
(origin/main: 1691 passed). Frontend: 267 tests, build clean.

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
   1/4" was taken as the thickness). OSSE CBP-1…9 only gain `dimension_inches`.
   Footing / pier / wall rows, `plate_text`, `size_text` and row selection are
   unchanged. Still open (partner path): Brandywine BP rows keep `plate_text`
   = the washer Ø (`2 3/4"`), and OSSE CBP width is consumed as the SIZE column.
5. **Partner level labels explained, not changed.** A Revit band label is
   "elevation of the line above + name of the line below": Springhill
   `14' - 0" FIRST FLOOR` (118 rows) spans SECOND FLOOR 14'-0" → FIRST FLOOR
   0'-0"; Burrville `29' - 0" UPPER LEVEL` (117 rows) spans MAIN ROOF → UPPER
   LEVEL 14'-6". `level_elevation_text` and `level_name` therefore name two
   different levels; `levels.level_bands` records this with the row count.
6. **Malformed values.** `TOS (+30'-8)` (Yellow Spring S2.04 p8 ×9, S2.05 p9
   ×3) is shown as printed with a flagged 30'-8" candidate, never a value. The
   `TOS (…)` abbreviation is defined on S2.01 and applied to other sheets only
   because no sheet defines it differently; the defining sheet is shown.

Cache keys: `EXTRACTION_VERSION = 3.23-page-space`,
`EXTRACTOR_VERSION = legend_extractor_v6k-page-space` (the partner's
schedule-grid change had not bumped either).

## Column tracing pilot

`GET /api/documents/{id}/column-trace?location=&schedule=`, or **Show
details → Look for this column on the plans** in Drawing Summary. Evidence
only, computed on request (≈1 s OSSE, ≈3 s Yellow Spring).

| Column (schedule) | Levels spanned (schedule extent) | Plans and what is at the grid intersection |
|---|---|---|
| OSSE C.8-8.9 W10X33 (S602 p26, BUILDING GCS) | T.O. ROOF 69'-4" → T.O. SLAB LEVEL 1 38'-0", both ends on lines | S123 p11 (matched: its note names OFFICE ROOF at 69'-4"): symbol, nearby 69'-9" box (meaning not stated); S122 p10: symbol; S121 p9: symbol, pier P1, footing F4.0B [28'-6"]; S101 p5: grids not found |
| Yellow Spring P-21 W8X24 (S2.09 p13, rotated) | 3 ROOF 30'-8" → 2 SECOND FLOOR AND LOW ROOF 15'-4" | S2.01 p5: no symbol detected; "POST UP" leader ends at the column → supports the bottom end; S2.04 p8: symbol, grids cross twice (both listed); S2.05/S2.06: grid lines not found |

Crops: `crops/trace_*.png`. Never assumed: equal sections or equal grid names
across buildings identify a column; the lowest plan is the foundation; no
symbol means absent; observed floors are one fabrication piece. Offsets are
not applied (plan scale not read); a plan page matched to several levels is
labelled so.

## Next phase

1. Plan scale + offsets so offset locations (`R13(5' - 4")-RA.1`) get a
   position; detect column marks / continuation notes ("COLUMN BELOW") per
   level and feed them into end states.
2. Disambiguate plan ↔ level by building scope (OSSE BUILDING vs PARKING)
   and sheet references printed on the schedule.
3. With the partner: whether `level_name` / `level_elevation_text` should
   carry the band reading; the washer Ø in `plate_text`; the OSSE WIDTH/SIZE
   column; `.gitattributes` for gold files and `encoding=` in tests.
