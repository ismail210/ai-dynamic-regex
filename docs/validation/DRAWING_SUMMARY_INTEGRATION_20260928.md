# Drawing Summary integration — 2026-09-28

Drawing Summary checkpoint `924244a83d5007a737ce0032390086fb450ec621` contains only its nine intended files, on `4f987b5`. The integration merges `origin/main` at `bd80a5097266b75cff56eae4a34960d16d49ed68` (Hiba Reda, “feat(schedule): read ruled schedule tables; fix callout fragment duplicates”). This is the only partner commit missing from the checkpoint. `origin/estima3d-integration` and the schedule integration branch were already ancestors; neither was merged again.

## Conflict resolution and combined changes

- `backend/services/engineering/schedule_grid.py`: combine the ruled reader and normalized mark keys with the existing optional duplicate-mark guard and shadow evidence. Retain the three-value schedule-title helper contract. Keep shadow “current” discovery restricted to its original marks; widened discovery remains separate.
- `backend/services/extraction_engine.py`: preserve the PDF path supplied to the ruled reader and use the new combined cache version `3.17-summary-ruled-schedules`.
- Drawing Summary excludes Revit grid-location rows from mark definitions, restricts source highlights to the ruled table bounds, and grounds the newly supported mark spellings. Legend cache version is `legend_extractor_v6e-ruled-schedules`.
- The cross-project benchmark now recognizes canonical mark aliases (`C-1` / `C1`) when determining whether the destination document defines a mark. A negative-control test still detects a resolver leaking an undefined mark.

The first Struct comparison exposed a ruled-reader compatibility regression: moving angle dimensions ahead of the ICF angle description changed CL resolutions to plates and removed 143 angle quantities. The final integration retains BP/CL rows on the existing word-cluster path, including their original row wording and N/A behavior. Ruled-only auxiliary rows do not create new production resolutions. The production `resolve_auxiliary_schedule_mark` function is AST-identical to both parents. Existing auxiliary-resolution limitations are deliberately preserved.

No prediction contract, production quantity engine, model, database, or training data was changed by this integration. The partner's committed research scripts, reports, and small render assets are retained with their commit.

## Verification

All commands use the existing backend virtualenv interpreter, with the working directory set to this worktree's `backend/`, unless stated otherwise.

| Check | Result |
| --- | --- |
| Pre-merge known-failure files: `pytest tests/test_a2_a7_human_review.py tests/test_repeated_detail_linker.py -q --tb=short` | 26 passed, 9 failed |
| Summary, legend, schedule, shadow, benchmark and BP/CL focused tests after initial integration fixes | 200 passed, 3 skipped, 61 subtests passed |
| Final BP/CL compatibility, schedule and summary regression suite: `pytest tests/test_schedule_tables.py tests/test_schedule_spatial_pipeline.py tests/test_struct_notation.py tests/test_drawing_intelligence.py -q --tb=short` | 88 passed, 1 skipped, 45 subtests passed |
| Final complete backend: `pytest -q --tb=short` | **1529 passed, 54 failed, 25 errors, 9 skipped; 466 subtests passed** |
| Partner research tests in a source snapshot of `bd80a50` | 65 passed, **45 failed, 25 errors**, 1 skipped |
| Frontend: `npm.cmd run test` | **231 passed**, 21 files |
| Frontend: `npm.cmd run build` | Passed |
| Browser smoke: desktop, mobile cards, PDF source and visible mark highlight | Passed, no browser errors |
| `git diff --check` | Passed |

The full backend suite is **not green**. The nine known failures match the pre-merge checkpoint by test identity, assertion message and full failure text. The other 45 failures and 25 errors match the partner snapshot by identity and full error text after normalizing checkout/interpreter paths. They reference absent research fixtures under `docs/validation/rd_geometry_integration/` and the absent `g9_false_association_audit.py` script. They were not relabeled as part of the nine-failure baseline, suppressed, or repaired with fabricated research data. There are no additional integration failures.

The browser smoke injected the freshly merged Struct summary into the extraction response, fetched the actual manifest and PDF from the already-running backend, and checked the source highlight after zoom/scroll completed. It did not upload, extract, analyze, or write application data. The full merged extraction and prediction path was exercised separately below.

## Struct.pdf safety comparison

PDF SHA-256: `683e6eef0a945c9a2b2f5ce5f4706b971071fb1cf446c9206b1a5794c4e22242`.

Each comparison used fresh extraction, an isolated cold legend cache, the production multimodal pipeline with `persist=False`, and the real QuantityEngine output. Drawing Summary LLM was disabled in these subprocesses; the existing Ollama service was not restarted or reconfigured. Quarantine remained off. No Excel was supplied as an inference input.

The summary control uses the **same merged source** with only `drawing_intelligence.py`, `drawing_summary_llm.py`, `legend_profile.py`, and `legend_profile_hook.py` restored in an external source snapshot to their pre-summary `4f987b5` versions. It isolates the summary's effect from the partner's intentional extraction changes.

| Measure | Checkpoint `924244a` | Final integration | Integration without new summary |
| --- | ---: | ---: | ---: |
| Extracted tokens | 2019 | 1990 | 1990 |
| Eligible tokens | 1745 | 1730 | 1730 |
| Eligible exact sections | 1012 | 1031 | 1031 |
| Served predictions | 1433 | 1436 | 1436 |
| Physical quantity | **264** | **264** | **264** |

Final vs. checkpoint: every BP/CL resolution field is identical, and physical quantities match for **every section**. Tokens and predictions change with the partner's callout-fragment and schedule extraction changes; whole-branch token/prediction equality is not claimed.

Final vs. summary control: token keys, eligibility, exact-section counts, object types, context scope, prediction count and normalized decision digest, prediction sources, all BP/CL fields, quantity totals, per-section quantities and exclusions are all identical. Drawing Summary adds 50 definitions, 16 interpretation rules and two unresolved items without changing these production results.

## Four separate review passes

Performed by the integrating agent because the merge changes Drawing Summary's schedule input:

1. **Correctness and production safety.** Reviewed both conflict parents and downstream resolver/quantity consumers. Fixed the shadow mark-mode regression, alias benchmark false positive, and the measured BP/CL ruled-row regression. Verified duplicate-mark guards remain connected and the production auxiliary resolver is unchanged.
2. **Evidence grounding and security.** Checked evidence IDs, catalog-backed designations, nonquantity claims, deterministic failure fallback and rendering as React text. Added regression coverage for ungrounded hyphenated, underscored and newly supported mark families. No new executable content, external destination or unsafe HTML path was added.
3. **UI and provenance.** Removed grid locations from definitions and restricted highlights to their source table. Checked desktop tables, mobile cards and real PDF navigation, including the visible mark highlight. Existing frontend tests and build pass.
4. **Performance, reuse and simplicity.** Retained the shared row-splitting helper for auxiliary compatibility and shadow evidence, the existing PDF viewer with its page window, bounded summary lists, and the partner's clipped candidate-page table scan. Kept snapshot/test artifacts outside the repository. No unrelated refactor or resolver rewrite was introduced.

## Preservation and local evidence

The three pre-existing dirty files were never staged and remain byte-identical to the start of this integration:

| File under `backend/training/` | SHA-256 |
| --- | --- |
| `history.csv` | `a739031ddf333ae9dd26c6df2a234b6fb0e4716bcc22cec07cdb9582e7846905` |
| `multimodal_review_index.json` | `523f07b273db6f16ff15f1ab1b7699513dc59605ed2755f91aae1eabe15a9cea` |
| `unknown_tokens.csv` | `69c22a0016cf4b65b26a7b49833f5b7f9a7587aefd9d20802ea89961de435410` |

The original checkout remains on `700c72f` with its existing dirty/untracked files. Existing worktrees and stashes were preserved. Ollama service PID 12184 and tray PID 21944 kept their original start times; no `llama-server` child was loaded when this turn began. No running application process was stopped or restarted.

Detailed XML/JSON comparisons, logs, screenshots, source snapshots and the safety worker are saved locally under `C:/tmp/drawing-summary-integration-20260928/`. In particular: `failure-comparison.json`, `struct-comparison.json`, `browser-smoke.json`, `backend-final.xml`, `frontend-tests.json`, and `training-preservation.json`.
