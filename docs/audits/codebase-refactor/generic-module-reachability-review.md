# Generic-Stem Module Reachability Review

Baseline: `main` @ `58821a1de9b19bdf0fa092a0d791c0b0676ce081`. Full forensic re-verification of the 14
"medium-confidence generic-stem modules" identified by `unused-candidates.md` §9, using one reusable
AST-based whole-backend import graph, plus a companion investigation and repair of the pre-existing
`test_ground_truth_evaluator_repair.py` collection error. **Result: zero deletions.** All 14 candidates have
proven production or explicitly-documented operational callers; none meets `CONFIRMED_UNUSED`.

## Discrepancy note (Phase 1)

`unused-candidates.md` §9's prose describes "14 rows... mostly generic-stem modules (`models`, `parser`,
`pipeline`, `contracts`, `schemas`, `validation`, `service`, `normalization`)... and 7 backend test files
using `importlib.util.spec_from_file_location`." Filtering `file-inventory.csv` literally by
`proposed_action == "manual decision required"` returns a *different* 14-row set (`.claude/skills/
task-observer/SKILL.md`, `ai-dynamic-regex.code-workspace`, the 4 `services/engineering/` modules already
deleted in the prior phase, the 3 semantic shims already resolved in an earlier phase, 3 test files including
the `length_to_feet` collection-error file, `train_neural_models.py`, `skills-lock.json`) — none of which
matches the "generic-stem" description, and most of which are already resolved or aren't Python modules at
all.

The evidence-backed current set is instead every CSV row whose basename (minus extension) is one of the 8
named stems **and** whose `confidence_level` reads `"medium (generic module name — textual co-occurrence
reference count may overcount; not a verified import graph)"` — this is an exact match for §9's prose and
returns exactly 14 rows, listed below. Both interpretations independently agree the CSV had already resolved
13 of these 14 to `proposed_action = keep in place` / `keep but document` (only `semantic_preprocessor/
models.py` still said `manual decision required`, and that was already resolved in an earlier phase — kept,
dead tail trimmed). This phase re-verified all 14 with a real AST import graph rather than trusting the
CSV's preliminary textual-co-occurrence call.

**A second, unrelated data-quality bug was found and is worth recording**: several of these 14 rows'
`important_inbound_references` CSV columns are byte-identical across unrelated rows (e.g. `services/
engineering/models.py`, `services/semantic/models.py`, and `services/semantic_preprocessor/models.py` all
list the exact same 5 references, none of which are these files' true importers). This is exactly the kind
of over/under-counting risk the "medium confidence" label warns about, and is why this phase did not rely on
that column at all.

## The 14 candidates

| Path | Module path | Current LOC | Confidence (from audit) |
|---|---|---|---|
| `backend/services/annotation/parser.py` | `services.annotation.parser` | 374 | medium (generic name) |
| `backend/services/annotation/service.py` | `services.annotation.service` | 237 | medium (generic name) |
| `backend/services/engineering/models.py` | `services.engineering.models` | 114 | medium (generic name) |
| `backend/services/ml_association/schemas.py` | `services.ml_association.schemas` | 301 | medium (generic name) |
| `backend/services/ml_association/service.py` | `services.ml_association.service` | 123 | medium (generic name) |
| `backend/services/ml_association/validation.py` | `services.ml_association.validation` | 267 | medium (generic name) |
| `backend/services/multimodal/contracts.py` | `services.multimodal.contracts` | 233 | medium (generic name) |
| `backend/services/multimodal/pipeline.py` | `services.multimodal.pipeline` | 642 | medium (generic name) |
| `backend/services/normalization.py` | `services.normalization` | 89 | medium (generic name) |
| `backend/services/semantic/models.py` | `services.semantic.models` | 773 | medium (generic name) |
| `backend/services/semantic_preprocessor/models.py` | `services.semantic_preprocessor.models` | 71 | medium (generic name) — already resolved (kept, trimmed) in `semantic-shim-and-fusion-review.md` |
| `backend/services/semantic_preprocessor/normalization.py` | `services.semantic_preprocessor.normalization` | 204 | medium (generic name) |
| `backend/services/semantic_preprocessor/pipeline.py` | `services.semantic_preprocessor.pipeline` | 206 | medium (generic name) |
| `backend/services/training_pipeline/contracts.py` | `services.training_pipeline.contracts` | 114 | medium (generic name) |

Total: 3,748 LOC across the 14 files (`engineering/models.py` and `semantic_preprocessor/models.py` already
reflect the earlier phases' trims).

## Collection-error repair (Phase 2)

See commit `230decb` for the full evidence. Summary: `tests/test_ground_truth_evaluator_repair.py` imported
`length_to_feet` from `services.takeoff.ground_truth_evaluation`, which does not exist there. Git history
(`git log -S "def length_to_feet"`, `git show 88222e6 --stat`) proves this was a **deliberate removal**, not
a regression: merge `88222e6` ("Integrate Bassam takeoff validation/dedup...") replaced the old
`ground_truth_evaluation.py`/`ground_truth_excel.py` implementation (which had `length_to_feet`, per-item
`tons`/`weight_plf`/`overall_weight_tons`, `connection_items`/`plate_items` buckets, `section_rollups`) with
a thin wrapper around the new `services.takeoff.canonical_takeoff_eval.py` — "the single shared
implementation" now used by both the production `validate_takeoff` path and the research benchmark harness
(per that module's own docstring). `af743be`, immediately after, restored only a thin
`_aggregate_ground_truth` compatibility shim for `multimodal_pipeline` imports; `length_to_feet` and the rest
of the old schema were never brought back, and the test was never migrated.

No canonical replacement for `length_to_feet` exists (imperial length strings are now stored raw, unconverted
— a deliberate simplification, not a rename) — Outcome A (import swap) was not available. The file's other
assertions (`report["metrics"]["tonnage"]["gt_tons"]`, `report["metrics"]["section"]["true_positive"]`,
`gt["connection_items"]`, `gt["plate_items"]`, `occurrences[].weight_plf`) target a schema the current
`parse_workbook_ground_truth`/`evaluate_against_excel` do not produce at all — confirmed by reading both
functions' current return statements in full. Rewriting them (Outcome B) would have substantially duplicated
existing coverage rather than closing a real gap: `tests/test_canonical_takeoff_eval.py` already covers
canonical section resolution, primary/connection/plates/out-of-scope scope classification,
`caught = min(predicted, ground_truth)` capping, abstention/plate/catalog-invalid exclusion, and two
`HarnessProductionParityTests` that run the real Burrville and GCDC workbooks present in this environment
through both the wrapper and the canonical implementation and assert they produce identical numbers — 12/12
passing, none skipped, confirmed before the repair.

**Outcome chosen: file removed entirely** (the closest fit to Outcome C, applied at whole-file granularity
because every test method in the file depended on the removed schema — there was no fragment of "meaningful
repair coverage" left to retain in this specific file once the target implementation was gone). Zero
production code was changed. Commit `230decb`.

Collection before: `test_ground_truth_evaluator_repair.py` errored, blocking `pytest -q` collection entirely
(required `--ignore=...` as a workaround in the prior phase). Collection after: 1299 tests collected cleanly,
no errors, no `--ignore` needed.

## Background-shell closure (Phase 0)

Two background shells from the prior phase were inspected:

1. **Whole-repository grep** (`bk4qb1qk1`) — already completed before this phase started (notification
   received mid-session in the prior phase); output reviewed, confirmed read-only, confirmed it surfaced 2
   stale README sections that were fixed in commit `58821a1` at the end of the prior phase.
2. **`pyright --outputjson`** (`bcol3jfxq`) — found genuinely stuck: process tree traced via
   `Get-CimInstance Win32_Process` to a bash → bash → sh → node chain running the exact backgrounded command,
   **running since 2026-09-18 15:05:54 — roughly 4 days**, consuming 3.5 GB RAM. A second, orphaned instance
   of the same command (identical creation timestamp, identical command line, parent process already exited)
   was also found and terminated. Both were confirmed read-only (`git status` before/after was byte-identical)
   and terminated by exact PID only — the unrelated, legitimately-running `pyright-langserver.exe` /
   `pyright-langserver.cmd` processes (live IDE diagnostics, several instances, oldest since 2026-09-18) were
   left untouched.

Pyright never produced usable JSON output before being killed (stuck for 4 days, presumably hung on this
large codebase's full-project analysis). Per this task's own fallback instruction ("If Pyright failed
operationally... record the tool failure and continue using import, compile, graph, and test evidence"),
this phase relied on `py_compile`, `import app`, and the harness's live per-edit Pyright diagnostics instead
— no repository-wide Pyright JSON baseline was produced this phase.

## AST-based import graph (Phase 3)

A single, reusable, temporary standard-library `ast` script (not added to the repo) walked every tracked
`.py` file under `backend/` once and recorded, for all 14 candidates simultaneously: plain `import x`
statements, `from x import y` statements (including relative-import resolution), and — after an initial pass
under-counted one real case — `from <parent package> import <leaf module>` statements (the common
"import a submodule as a package attribute" idiom), plus scans of every `__init__.py` for re-exports of any
candidate.

| Candidate | Distinct importing files | Production (non-test/script) importers |
|---|---|---|
| `annotation/parser.py` | 11 | `services/annotation/service.py`, `services/annotation/understandability.py`, `services/engineering_object_filter.py`, `services/label_reconstruction/candidates.py`, **`services/prediction/orchestrator.py`** |
| `annotation/service.py` | 2 | `services/annotation/__init__.py`, **`services/prediction/orchestrator.py`** |
| `engineering/models.py` | 2 | `services/engineering/geometry_extractor.py`, `services/engineering/graph_builder.py` |
| `ml_association/schemas.py` | 12 | 7 files inside `services/ml_association/` itself (its own subsystem) |
| `ml_association/service.py` | 2 | none via plain import — reached via `from services.ml_association import service` from `scripts/import_review_decisions.py` and the guard test |
| `ml_association/validation.py` | 1 | `services/ml_association/review_import.py` |
| `multimodal/contracts.py` | 1 | **`services/multimodal/fusion_engine.py`** (proven production in the prior phase's fusion-engine review) |
| `multimodal/pipeline.py` | 6 | `services/multimodal/__init__.py`, **`services/staged_pipeline.py`**, `services/takeoff/takeoff_validation.py` |
| `normalization.py` | 4 | `services/prediction/canonical_contract.py`, `services/prediction/section_canonicalize.py`, `services/semantic_preprocessor/normalization.py` |
| `semantic/models.py` | 29 | 15 production files incl. `services/prediction/drawing_semantics.py`, `services/prediction/semantic_contract.py`, `services/semantic_document_service.py` |
| `semantic_preprocessor/models.py` | 9 | `services/semantic_preprocessor/{extraction,grouping,pipeline}.py` (already-resolved shim, see prior phase) |
| `semantic_preprocessor/normalization.py` | 4 | `services/semantic/corrected_pdf.py`, `services/semantic_document_service.py`, `services/semantic_preprocessor/pipeline.py` |
| `semantic_preprocessor/pipeline.py` | 6 | `services/semantic_document_service.py` |
| `training_pipeline/contracts.py` | 3 | **`routers/learning.py`**, `services/training_pipeline/{dataset_registry,model_registry}.py` |

Every one of the 14 has at least one real, current inbound reference (range: 1–174). None is unreachable at
the plain static-import level.

## Dynamic / non-Python references (Phase 4/6)

A repository-wide grep for `importlib`/dynamic loading of any of the 14 module paths found exactly one hit
— `tests/test_ml_association_review_kit_builder.py`'s `importlib.util.spec_from_file_location`, which loads
`scripts/build_ml_association_review_kit.py` by file path (a script, not one of the 14 candidates directly).
No CI workflow (no `.github/` in this repo), no Dockerfile/`docker-compose.yml` reference, no
environment-variable-selected class, and no decorator/route registration references any of the 14.

## Artifact/serialization (Phase 7)

Reused the same 43-binary-artifact scan methodology from the prior phase: zero of the 14 candidates' module
paths appear in any tracked `.joblib`/`.pkl`/`.pt`/`.ubj`/`.onnx` file. Not relevant to the final decision
(all 14 are retained for reachability reasons, not compatibility reasons), but confirms none are additionally
`COMPATIBILITY_REQUIRED`.

## Git-history and architecture-invariant findings (Phase 8)

The 3 `ml_association/*` candidates (`schemas.py`, `service.py`, `validation.py`) are explicitly named in
`CLAUDE.md`'s architecture invariants: *"`backend/services/label_reconstruction/` and
`backend/services/ml_association/` are shadow work and are **not wired into production**. Guard tests
(`test_*_not_wired_into_production.py`) enforce this — do not wire them in."* This phase read
`tests/test_ml_association_not_wired_into_production.py` in full: it is a real, currently-passing structural
guard (`_PRODUCTION_MODULES` source-text scan + attribute-binding scan across `services.multimodal.pipeline`,
`services.prediction.orchestrator`, `app`, `routers.documents`, etc.) plus a companion
`FeatureFlagDisabledByDefaultTests` class proving `ml_association` is real, feature-flagged, operational
functionality (`service.build_dataset`, `service.export_groups`, `service.submit_review`,
`service.latest_outcomes`, `service.outcome_history` — each raising `FeatureDisabledError` while
`settings.ml_association_dataset_enabled` is `False`, the default) rather than inert dead code.
`config.py` itself documents the same intent: *"Disabled by default. This gates every ml_association service
entry."* This is a documented, current, deliberate architectural decision — not an unresolved question — and
rules out `CONFIRMED_UNUSED` decisively (condition 5: "no CLI, CI, deployment, or operational workflow
requires it" fails — `scripts/import_review_decisions.py` and `scripts/build_ml_association_review_kit.py`
are real operational tooling for the human-review workflow) independent of the import-count evidence.

The remaining 11 candidates required no deep git-history excavation: each has at least one direct import from
a file already independently proven production-critical in this or an earlier phase of this refactor
(`orchestrator.py` — the sole recognized inference entrypoint per `CLAUDE.md`; `fusion_engine.py` and
`staged_pipeline.py` — proven production in `dead-module-reachability-review.md`'s and
`semantic-shim-and-fusion-review.md`'s fusion-engine analysis; `routers/learning.py`; `semantic_document_service.py`).

## Final classification (Phase 10)

| Module | Classification | Reason |
|---|---|---|
| `annotation/parser.py` | ACTIVE_RUNTIME | imported by `orchestrator.py` |
| `annotation/service.py` | ACTIVE_RUNTIME | imported by `orchestrator.py` |
| `engineering/models.py` | ACTIVE_RUNTIME | imported by `geometry_extractor.py`, `graph_builder.py` |
| `ml_association/schemas.py` | ACTIVE_OPERATIONAL | feature-flagged shadow work, guard-tested, real script/service consumers |
| `ml_association/service.py` | ACTIVE_OPERATIONAL | same — the guarded facade itself |
| `ml_association/validation.py` | ACTIVE_OPERATIONAL | same subsystem, imported by `review_import.py` |
| `multimodal/contracts.py` | ACTIVE_RUNTIME | imported by `fusion_engine.py` |
| `multimodal/pipeline.py` | ACTIVE_RUNTIME | imported by `staged_pipeline.py`, `takeoff_validation.py` |
| `normalization.py` | ACTIVE_RUNTIME | imported by `canonical_contract.py`, `section_canonicalize.py` |
| `semantic/models.py` | ACTIVE_RUNTIME | 15 production importers, the canonical semantic model |
| `semantic_preprocessor/models.py` | ACTIVE_RUNTIME (already resolved) | see `semantic-shim-and-fusion-review.md` |
| `semantic_preprocessor/normalization.py` | ACTIVE_RUNTIME | imported by `corrected_pdf.py`, `semantic_document_service.py` |
| `semantic_preprocessor/pipeline.py` | ACTIVE_RUNTIME | imported by `semantic_document_service.py` |
| `training_pipeline/contracts.py` | ACTIVE_RUNTIME | imported by `routers/learning.py` |

**Zero of the 14 meet `CONFIRMED_UNUSED`.** All fail at minimum condition 1 (unreachable from production
entrypoints); the `ml_association` trio additionally fails condition 5 (operational workflow requires it) and
is protected by an explicit, current architecture invariant. No deletions, no caller migrations, no test
changes, and no production code changes were made to any of the 14 in this phase.

## Regression testing (Phase 16)

- Collection-error repair + directly affected tests: `tests/test_canonical_takeoff_eval.py`,
  `tests/test_takeoff_platform.py`, `tests/test_schedule_spatial_pipeline.py`,
  `tests/test_member_resolution.py` — **46 passed, 1 skipped, 0 failed**.
- Established targeted suite (semantic contract/compatibility, HSS completion, human selections, orchestrator
  policy, engineering pipeline, documents API, canonical contract, semantic precedence, canonical takeoff
  eval, ml_association guard): **116 passed, 8 subtests passed, 0 failed**.
- Full backend suite: **1287 passed, 9 failed, 3 skipped, 349 subtests passed** (1299 collected total, no
  `--ignore` needed — up from the prior phase's 1287/9/3 obtained only via `--ignore` of the now-removed
  collection-error file). All 9 failures are the exact same pre-existing set by name and message
  (`test_a2_a7_human_review.py` × 8, `test_repeated_detail_linker.py` × 1) — confirmed unrelated to this
  phase (none import any of the 14 candidates or the removed test file). **Zero new failures.**
- Import/startup sanity: `import app` succeeds, 15 routes register (unchanged from the prior phase).

## Measurement (Phase 18)

- 14 candidates expected, 14 found (after resolving the §9-prose vs. literal-CSV-filter discrepancy above).
- Modules deleted: **0**. Modules retained: **14** (11 `ACTIVE_RUNTIME`, 3 `ACTIVE_OPERATIONAL`).
- Callers migrated: 0 (none needed — all already correctly wired).
- Production LOC before/after this phase: unchanged (3,748 LOC across the 14 files, no edits).
- Test LOC: −203 (the removed collection-error file); no other test files touched.
- Collection error resolved: yes (commit `230decb`).
- Modules that looked plausible for deletion but proved necessary: all 14, by design of this phase's
  evidence-first methodology — none were ever misclassified as likely-dead; the CSV's own preliminary calls
  (`keep in place` / `keep but document` for 13 of 14) were already directionally correct, and this phase
  converted that preliminary textual-co-occurrence call into a verified AST-graph-backed one.
