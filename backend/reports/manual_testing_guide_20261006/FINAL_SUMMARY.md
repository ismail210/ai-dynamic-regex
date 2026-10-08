# Final summary — 2026-10-06 extraction fixes

No commit, push, merge, rebase, or deployment was made.

## Root causes

Masonry pier rows on Furley page 2 come from the ruled **MASONRY PIER SCHEDULE**. The table is correct: WIDTH is `16"` / `24"` / `32"`, and the next column is the vertical bars. The reader treated every WIDTH heading as a plate dimension. A single inch value was enough to mark the plate present, with length and thickness empty. Footing tables were left alone, because their feet-inch sizes already stay unresolved.

ICF wrapped lines are in the ruled cell, but production uses the word cluster for BP and CL marks. The cluster kept one baseline. `#4 STIRRUPS AT 12"o.c.` and `WELDED TO PLATE` sit about 13 points below the mark, so they were dropped. Joining every following line on the page was too wide: it mixed words by horizontal position and it pulled `LINTEL SCHEDULE` and ICF notes into the row above. The join now requires the same horizontal span, a line that already has a mark, a gap no larger than the existing row gap, and it refuses a line that says SCHEDULE or NOTES. The second line is appended after the first line.

## Files changed

- `backend/services/engineering/schedule_grid.py` — pier width is not a present plate; wrapped continuation lines join only their own mark.
- `backend/services/extraction_engine.py` — extraction version `3.27-pier-wrap`, so older cached extracts are not reused by mistake.
- `backend/tests/test_schedule_tables.py` — MP16, MP24, MP24A, MP32, MP32A, and the CL6A / CL8 / CL9 wrap with CL7, CL5, and a following `LINTEL SCHEDULE` title.
- This report folder.

Quantity code, the prediction orchestrator, and prediction contracts were not edited.

## Fixes implemented

- Five masonry pier rows keep raw width and bar text, status unresolved, plate count hint 0, and they stay out of the steel mark list.
- CL6A and CL8 include `#4 STIRRUPS AT 12"o.c.` and `WELDED TO PLATE`. CL9 includes the stirrup line only. The angle stays `L5X5X3/8` where the sheet prints `5"x5"x3/8"`. CL5 and CL7 stay `N/A` and do not inherit the line above.
- CL2, CL4, and CL6 gain the printed `WELDED TO PLATE` line in the same cell. Their angle does not change.
- BP4–BP7 are unchanged.

## Left unresolved on purpose

- Brandywine `14'-0" LEVEL 1` stays split and unpaired. Pairing was not forced.
- Brandywine `A.3'-19` stays an ambiguous trace. Nearby plan text includes bubble `A.4'` and `19`, not a confirmed `A.3'`.
- OSSE T.O. SLAB LEVEL 2 stays a conflict: schedule `55' - 10"` versus plan `55'-2"`. LEVEL 1 `38'-0"` still agrees.
- Springhill M-20, N-20, and N.2-12 were rechecked. Plate text on pages 26–27 did not change. They stay grid locations.
- Pier length and thickness are not printed. They were not invented.
- Stirrup bars were not turned into quantities.
- Historical 383/414 and the 264 counted-item figure are **not reproducible**. The script, the 414-mark answer file, and the historical prediction file are not in the repo. `docs/DEPLOYMENT.md` mentions 1436 predictions and 62 quantity rows totalling 264. That is a different metric and was not used as a substitute.

## Tests

Automated, from `backend/` with `./venv/bin/python -m pytest`:

| Command | Result |
| --- | --- |
| `tests/test_schedule_tables.py tests/test_schedule_plate_headings.py tests/test_level_evidence.py -q` | **131 passed**, 41 subtests passed |
| `ESTIMA3D_TESTING_PROJECTS=reports/targeted_pdf_fixes_20261006/retest_pdf_root tests/test_level_reference_set.py -q` | **4 passed, 4 skipped**. Passed: OSSE, Yellow Spring, Washington Latin, Fort Davis. Skipped: Furley, Brandywine, Burrville, Springhill, because those fixture-relative paths are not in that folder. |
| Full `pytest -q` | **1837 passed, 20 skipped, 533 subtests passed** in 321 seconds. Skips are missing local PDFs under the default project root, missing benchmark workbooks, the optional Ollama smoke test, and one in-place geometry rewrite test. |

Frontend, from `frontend/`:

| Command | Result |
| --- | --- |
| `npm run test` | **267 passed**, 23 files, 80 seconds |
| `npm run build` | succeeded, 42 seconds |

These skips are not passes.

## Real-PDF checks

These are separate from the unit tests. They read the uploaded PDFs.

- Furley `backend/uploads/Struct.pdf` page 2. Mark list identical, 12 sections. MP status changed from present to unresolved. Width and bars unchanged. CL6A, CL8, CL9, CL2, CL4, CL6 text gained only the printed second line. CL5, CL7, BP4–BP7 unchanged. CL6A still resolves to `L5X5X3/8`. CL5, CL7, and CL9 still abstain.
- Springhill pages 26–27, Brandywine pages 42–43, and Burrville pages 28–29: section text, plate text, and plate status matched the previous extract. A first comparison flagged pairing only because this page-limited read did not reattach level bands. One Brandywine mark, `D-13(18'-2")`, appears twice in the old extract as well (`W12X40` and `W12X50`). That was not a new change.
- OSSE, Yellow Spring, Washington Latin, and Fort Davis: the reference test passed against the Desktop PDFs. That does not validate every sheet.

## Quantity safety

- Steel mark list on Furley: unchanged.
- `plate_count_per_member` for the five pier rows: was 1 because the width looked like a present plate; now 0. The function's own note says this hint is not a physical takeoff. Quantity code was not edited.
- CL rows that already had a printed angle still have the same plate hint of 1. N/A rows stay 0. No bar quantity was added.
- Prediction and Takeoff were **not** re-run. A live takeoff total was not compared. MT-15 is the manual check for that number.

## Manual sequence

1. MT-13 C1, the control row.
2. MT-01 and MT-02, the pier rows.
3. MT-03 and MT-06, wrapped lines and unresolved lintels.
4. MT-05, bearing plates.
5. MT-15, Takeoff.
6. MT-04 Springhill plates.
7. MT-07 and MT-12 Brandywine levels and `A.3'-19`.
8. MT-08 OSSE conflict.
9. MT-09, MT-10, MT-11.

## Remaining risks

- A wrapped line that is inside the row gap and inside the same columns, and that does not say NOTES or SCHEDULE, will join the mark above. That is the intended cell wrap. A future sheet with a different note in that position needs a look.
- Masonry pier fields are not on Drawing Summary. The manual field check uses `furley_page2_checked_rows.json`.
- Live Takeoff totals are unverified until MT-15 is done.
- The four reference PDFs that skipped in the default full suite still need `ESTIMA3D_TESTING_PROJECTS` pointed at a tree that contains their fixture-relative paths.

## Git working tree

Branch `main`, tracking `origin/main`, HEAD `9522744`. Nothing from this task was staged or committed. Other pre-existing local edits remain in the tree and were not reverted. See `git status --short` after this report.
