# Commands

Host: macOS. Backend interpreter: `backend/venv/bin/python`. No environment variables were set over the defaults below. Outputs were written only under `backend/reports/targeted_pdf_fixes_20261006/`. `extract_document_structure` was called without `persist_json`, so it did not write a document JSON into uploads or training.

## Version and flags

Recorded in `run_config.json` at the start of the re-extract:

- `EXTRACTION_VERSION` = `3.26-cell-text-levels` (`backend/services/extraction_engine.py`)
- `schedule_grid_enabled` = true
- `schedule_ruled_tables_enabled` = true
- `schedule_mark_map_enabled` = true
- `schedule_mark_conflict_guard_enabled` = false
- `schedule_evidence_shadow_enabled` = false

The constant before this task, on the dirty tree, was `3.25-level-bands-locations`. Committed `main` is `3.24-level-bands`.

## Re-extract

From `backend/`:

```text
./venv/bin/python -u reports/targeted_pdf_fixes_20261006/reextract.py
```

Inputs:

- `uploads/Struct.pdf`
- `uploads/ST - Springhill Lake__f6ddc4a7e233.pdf`
- `uploads/Structural4__3aa51f661bdf.pdf`
- `uploads/Burrville ES - ST.pdf`

Outputs: `extract_struct.json`, `extract_springhill.json`, `extract_brandywine.json`, `extract_burrville.json`, `column_trace_brandywine.json`, `renders/springhill_p27_plate_cells.png`, `renders/struct_p2_bearing_plate.png`, `renders/struct_p2_icf_lintel.png`. Runtime about 155 seconds.

## Extra column traces

A second in-memory Brandywine extract called `trace_column` on the first schedule entries that have two grids, stopping at the first entry with plan candidates (`A.3'-19`). Output: `column_trace_attempts.json`, `column_trace_hit.json`, and `renders/trace_*.png`.

## Tests

```text
cd backend && ./venv/bin/python -m pytest tests/test_schedule_tables.py tests/test_level_evidence.py tests/test_column_schedule.py tests/test_level_reference_set.py -q --tb=line
```

`160 passed, 8 skipped, 41 subtests`.

```text
cd backend && ./venv/bin/python -m pytest -q --tb=line
```

`1835 passed, 20 skipped, 533 subtests` in 230 seconds.

```text
cd frontend && npm run test
```

`267 passed`.

## Not run

The historical 383/414 evaluation. Its script and expected answers were not found. Prediction and the quantity engine were not run.
