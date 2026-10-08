# Targeted PDF fixes — 2026-10-06

Working tree stayed on `main` at `9522744`. Nothing was committed, pushed, or deployed. The original audit in `backend/reports/manual_pdf_validation_20261006/` was not modified.

Extraction version for this run: `3.26-cell-text-levels`. Schedule grid, ruled tables, and the mark map are on. The mark-conflict guard and the schedule-evidence shadow are off.

## Fixed and verified on the real PDFs

- Springhill Lake structural, schedule page 27. Cells M-20, N-20, and N.2-12 no longer return the interleaved string `11"x"1x188"x"1x188" "**`. The text layer has two overlapping copies of `1"x18"x18"` plus note stars. The reader now keeps one copy. Parsed plate: `1"`, `18"`, `18"`, notes `**`. Status `present`. These rows stay grid locations and stay out of `schedule_mark_map`.
- Furley `Struct.pdf` page 2. BP4 is `6"x8"x3/4"`. BP5 is `6"x10"x1"`. BP6 is `4"x10"x1 1/4"`. BP7 is `7"x9"x3/4"` with remarks `SEE S/S502`. Inspection-table sentences are no longer in those cells. The rendered bearing-plate schedule matches those strings. BP and CL marks stay out of the mark map. C1–C6 and L1–L4 are unchanged.
- Brandywine `14'-0" LEVEL 1` now splits into printed elevation `14'-0"` and printed name `LEVEL 1`. Pairing stays `unpaired`: the drawn lines say that elevation belongs to LEVEL 2 and the name belongs to LEVEL 1. Burrville `29' - 0" UPPER LEVEL` and Springhill `14' - 0" FIRST FLOOR` already split and remain `unpaired` for the same reason.

## Still open

- Furley masonry-pier rows MP16, MP24, MP24A, MP32, and MP32A still store a single width (`16"`, `24"`, `32"`) as `plate_text`. That was already true before this task. It was not the confirmed defect and was not changed.
- ICF lintel cells that wrap onto a second line (CL6A, CL8, CL9 stirrup lines) still keep only the baseline that holds the mark. That limit was already present. The first line now excludes the inspection table.
- Column tracing ran on Brandywine S600 location `A.3'-19`. Plan candidates were found. The crops do not confirm grid `A.3'`. See `COLUMN_TRACING_RESULTS.md`.
- The historical 383/414 mark count and 264 counted items are `NOT REPRODUCIBLE`. The script, expected answers, and historical predictions for that definition are not in the repo.

## Retested after the PDFs were downloaded

OSSE, Yellow Spring, Washington Latin, and Fort Davis are in `/Users/hibareda/Desktop/Testing Projects/`. The reference-level test passed for all four. Details are in `RETEST_FOUR_PROJECTS.md`.

## Tests

Backend: `1835 passed, 20 skipped, 533 subtests`. Frontend: `267 passed`. No frontend source was changed.

## Main risk

The three Springhill cells changed from `unresolved` garbage to a real plate reading. They are schedule evidence on grid locations, not new mark-map entries, and this task did not change the quantity engine. A later takeoff that consumes `parsed_plate` will see the printed size instead of an unreadable string.
