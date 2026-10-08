# Regression tests

## Added in `backend/tests/test_schedule_tables.py`

Plate cells:

- Two overlapping copies of `1"x18"x18"` plus `**`, using the Springhill cell rectangle, become `1"x18"x18" **` with dimensions `1"`, `18"`, `18"` and notes `**`. The interleaved extract stays `unresolved`.
- One word inside a cell does not replace a malformed extract.
- Two separate `N/A` words that do not overlap both stay.

Furley-style contamination:

- Inspection words on the same baseline, left of MARK, stay out of BP4–BP7 and CL5.
- BP4 is `6"x8"x3/4"`. BP7 keeps remarks `SEE S/S502`.
- CL1 still resolves to `L5X5X3/8`. CL5 stays unresolved and abstains.
- BP and CL stay out of `schedule_mark_map`.

Levels:

- Compact `14'-0" LEVEL 1`, spaced `14' - 0" FIRST FLOOR`, negative `-5'-0"`, zero `0'-0"`, and `13'-6 3/4"`.
- Incomplete and non-elevation strings do not split.
- Same printed line pairs only when one drawn line prints both parts.
- Separate lines in one block stay `unpaired`. Neighboring lines on different blocks stay `unresolved`.

The existing compact-label assertion that expected `42'-0" LEVEL 3` to stay one unsplit name was updated. That assertion was the bug. The raw label is unchanged. The printed parts now split, and pairing stays unresolved when the drawn lines are not applied. The geometric `level_span` assertion on that test is unchanged.

## Commands and results

From `backend/`, using `./venv/bin/python`:

```text
python -m pytest tests/test_schedule_tables.py tests/test_level_evidence.py tests/test_column_schedule.py tests/test_level_reference_set.py -q --tb=line
```

`160 passed, 8 skipped, 41 subtests`. The 8 skips are the reference-PDF tests whose drawings are not on disk.

```text
python -m pytest -q --tb=line
```

`1835 passed, 20 skipped, 533 subtests` in 230 seconds. No failures.

From `frontend/`:

```text
npm run test
```

`23 files, 267 tests passed`. No frontend source was edited, so the production build was not re-run.

`test_level_reference_set.py` skips are pre-existing missing PDFs, not failures from this change.
