# Quantity / prediction regression — Sheet Index Phase 1

**Result: no change.** On all 8 benchmark PDFs every recorded output is
identical before and after Phase 1. The only difference is the new
`sheet_index` key in the Drawing Intelligence profile.

## What was run

`quantity_regression.py` runs the production path on each PDF:

1. `extract_engineering_document`
2. `run_multimodal_pipeline(persist=False)`
3. `QuantityEngine().count`
4. `build_takeoff_rows`

The legend-profile cache points at a fresh temporary directory, so every
profile is rebuilt and nothing is replayed from `backend/training/legend_profiles`
or written to it.

- **before:** current code with the one new call (`sheet_index(document)`)
  stubbed out. `drawing_intelligence.py` had no other uncommitted changes, so
  this is the pre-Phase-1 code.
- **after:** current code.

Compared per document:

- quantity rows (section, quantity, method) and quantity total
- `schedule_mark_map`
- schedule-grid rows (mark, section, size, plate, plate status, level)
- prediction digest (object id, section, takeoff eligibility, scope, source) and prediction count
- engineering token count
- every Drawing Intelligence profile key except `sheet_index` (one digest), plus
  separate digests of `levels`, `column_schedule` and `definitions`
- a hash of every file under `backend/training/`, taken before and after each run

## Result (`diff before after`)

| Project | Predictions | Takeoff rows | Quantity total | Schedule rows | Result |
|---|---|---|---|---|---|
| Furley | 1420 | 10 | 264 | 50 | IDENTICAL |
| Burrville | 864 | 0 | 0 | 131 | IDENTICAL |
| Brandywine | 1651 | 0 | 0 | 112 | IDENTICAL |
| Springhill | 804 | 0 | 0 | 145 | IDENTICAL |
| OSSE | 300 | 0 | 0 | 55 | IDENTICAL |
| Yellow Spring | 1028 | 0 | 0 | 0 | IDENTICAL |
| Washington Latin | 574 | 0 | 0 | 95 | IDENTICAL |
| Fort Davis | 254 | 0 | 0 | 19 | IDENTICAL |

`sheet_index` is absent before and present after on all 8. Neither run
changed any file under `backend/training/`.

## Pre-existing observations (not caused by Phase 1)

- Only Furley produces takeoff quantity rows (264, which matches
  `docs/DEPLOYMENT.md`, "quantity rows totalling 264"). The other 7 return 0
  rows both before and after. Earlier reports already note that their
  schedules are keyed by grid location and produce no mark-map entries. So for
  those 7, the quantity total is a weak regression signal; the prediction,
  schedule and profile digests are the meaningful checks there.
- Furley produces 1420 predictions; `docs/DEPLOYMENT.md` says 1436. The gap is
  the same before and after.

## Profile cache (why `EXTRACTOR_VERSION` was bumped)

The first baseline (`regression_original_code.json`) ran with the real
on-disk cache. Two consequences:

- That run wrote 6 **new** gitignored cache files to
  `backend/training/legend_profiles/` and modified no existing file.
- For 2 of the 8 documents (Furley, Brandywine) it replayed profiles cached
  earlier today by older code. Those are the only 2 documents whose profile
  digest differs from the fresh runs.

The "after" run against the same cache (`regression_after_cached.json`) then
replayed cached profiles **without** `sheet_index`. That is the same thing that
would happen in production. Every earlier additive profile key (v6f–v6l) bumped
`EXTRACTOR_VERSION` for this reason, so Phase 1 bumps it to
`legend_extractor_v6m-sheet-index`. That changes the cache key only; no
extraction logic changes.

Files: `regression_before.json/.log`, `regression_after.json/.log`
(the authoritative pair), `regression_original_code.*`, `regression_after_cached.*`.
