# Dead-Module Reachability Review — `services/engineering/` Scaffolding

Baseline: `main` @ `75aee9cae7cbea27f3c4801afc7cdcadab66e277`. Full forensic re-verification of the 4
"high-confidence unused" backend modules flagged by `unused-candidates.md` §2
(`matching_engine.py`, `object_confidence.py`, `suggestion_engine.py`, `takeoff_interface.py`), against a
strict 15-point `CONFIRMED_UNUSED` standard, before any deletion. All four passed every point. This document
is the evidence record; final dispositions are also reflected in `unused-candidates.md` §2 and
`refactor-roadmap.md` Phase 3.

## Candidate identification

| Module | Full path | LOC | Created | Last touched | Responsibility |
|---|---|---|---|---|---|
| `matching_engine.py` | `backend/services/engineering/matching_engine.py` | 302 | `b9a9268` (2026-07-31, initial commit) | never (still `b9a9268`) | Compares extracted document/graph labels + geometry against an engineering Excel JSON schedule; produces `perfect_match`/`missing_label`/`wrong_label`/... discrepancy findings. |
| `object_confidence.py` | `backend/services/engineering/object_confidence.py` | 165 | `b9a9268` | `9aff2f1` (2026-08-31, mechanical swap to shared `level_from_score` helper — no functional change) | Legacy heuristic text/geometry/matching/overall confidence scores for extracted objects. Own docstring: "Runtime prediction confidence is owned by multimodal fusion." |
| `suggestion_engine.py` | `backend/services/engineering/suggestion_engine.py` | 213 | `b9a9268` | never | "Classical ML (no LLM)" per-label suggestion generator; internally calls `orchestrator.predict_token` for its AI signal, then blends in graph-distance and Excel-schedule priors. |
| `takeoff_interface.py` | `backend/services/engineering/takeoff_interface.py` | 190 | `b9a9268` | `2911a8a` (2026-08-04 — added an explicit docstring disclaiming production status, see below) | Dataclasses (`TakeoffQuantity`, `TakeoffSummary`) + abstract exporter stubs (`ExcelTakeoffExporter`, `CsvTakeoffExporter`, both raise `NotImplementedError`) + `build_takeoff_preview()`. |

All four were present at the repository's initial commit and represent early scaffolding from before the
current production pipeline (`orchestrator.py`, `rule_engine.py`, multimodal fusion, `takeoff_exporter.py`)
was built out. Neither `matching_engine.py` nor `suggestion_engine.py` was ever touched again after the
initial commit — a strong signal of orphaned-at-birth code, not an actively maintained path.

`takeoff_interface.py`'s own docstring (added 2026-08-04, commit `2911a8a`) already states: *"Not the live
exporter. The production `POST /api/takeoff/generate` endpoint (`routers/takeoff.py`) is served by
`services.takeoff.takeoff_exporter`... Nothing here is imported by any router... this one is a forward
architecture placeholder, not a duplicate/legacy path."* — i.e. a prior engineer had already investigated and
recorded this finding in the code itself.

## AST-based import graph (Phase 3)

A temporary standard-library `ast`-based script (not added to the repo) walked every tracked `.py` file under
`backend/` and recorded every `Import`/`ImportFrom` node (including relative imports) referencing any of the
4 candidate module paths or their exported symbols.

| Module | Inbound module imports | Inbound symbol imports | Package re-exports |
|---|---|---|---|
| `matching_engine` | none | `match_extraction_to_excel` ← `tests/test_engineering_pipeline.py` only | none (`services/engineering/__init__.py` has no re-exports) |
| `object_confidence` | none | `build_object_confidences`, `score_object_bundle` ← `tests/test_engineering_pipeline.py` only | none |
| `suggestion_engine` | none | `generate_suggestions` ← `tests/test_engineering_pipeline.py`; `suggest_for_text_node` ← `tests/test_prediction_orchestrator.py` | none |
| `takeoff_interface` | none | `build_takeoff_preview` ← `tests/test_engineering_pipeline.py` only | none |

No router, service, script, or other production module imports any of the 4 modules or their symbols.
`services/engineering/__init__.py` is a single docstring with zero re-exports.

## Dynamic / configuration / operational references (Phase 4)

Whole-repository text search (not limited to `.py`) for each filename and module path found 18 files total.
After inspection, every hit outside the 4 source files and their 2 owning test files was one of:

- **A false positive** — `services/engineering/validation_engine.py` lines 44/216 reference a parameter named
  `object_confidences`, not an import of `object_confidence.py` (confirmed by the original `unused-candidates.md`
  audit and re-verified here).
- **A stale explanatory comment** — `tests/test_documents_api.py:91` referenced `takeoff_interface.py` in a
  comment explaining why the live-exporter regression test exists; updated as part of this phase since it now
  names a deleted file (see Related Cleanup below).
- **Documentation** — `docs/ENGINEERING_VALIDATION.md`, `docs/geometry_graph_audit/*`,
  `docs/ml_association_phase/repository_evidence.md`, and this audit's own `unused-candidates.md`, all
  descriptive prose, not executable references.

No `importlib`/`__import__`/reflection usage, no plugin/decorator registration, no FastAPI dependency or route
registration, no CLI/console-script entrypoint, no environment-variable-selected class, no CI workflow (this
repo has no `.github/`), and no Dockerfile/`docker-compose.yml` reference any of the 4 modules — confirmed by
direct inspection of `backend/Dockerfile`, `frontend/Dockerfile`, and `docker-compose.yml`.

**Independent corroboration**: two earlier, unrelated audits already reached the same conclusion by their own
grep passes. `docs/geometry_graph_audit/00_executive_summary.md` finding #2: *"Four of ten graph/matching
modules are dead code in production (`matching_engine.py`, `suggestion_engine.py`, `validation_engine.py`,
`object_confidence.py`) — feature-complete, only reachable from tests."* Its `algorithm_registry.csv` and
`09_open_questions.md` record the same per-module "DEAD - not imported outside tests" status and note *"no
TODO, feature flag, or config switch referencing them was found either."* `docs/ml_association_phase/
repository_evidence.md` explicitly declined to re-investigate, citing this same prior finding as already
settled. (`validation_engine.py` itself is **not** one of this task's 4 named candidates and was left
untouched — see Related/Out-of-Scope Findings below.)

## Artifact and serialization compatibility (Phase 5)

All 43 tracked binary model artifacts (`.joblib`/`.pkl`/`.pt`/`.ubj`/`.onnx`) under the repository were
byte-scanned for the literal strings `services.engineering.{matching_engine,object_confidence,
suggestion_engine,takeoff_interface}` and their `backend.`-prefixed forms — **zero hits**. All tracked `.json`
files were searched for the same strings — **zero hits** (unlike the earlier semantic-shim review, there was
no residual descriptive-field hit here either). No `pyrightconfig.json`/`.toml`/`.cfg`/`.ini` packaging or
tooling config references any of the 4 modules. Conclusion: none of the 4 are `COMPATIBILITY_REQUIRED`.

## Git-history intent findings (Phase 6)

`git log --all --oneline --grep=` for all 4 module names (case-insensitive) across every branch returned no
commits — no commit message anywhere in this repository's history discusses adding, removing, deprecating, or
replacing any of these 4 files. Combined with the "created at initial commit, essentially never touched again"
finding above, and `takeoff_interface.py`'s own self-documenting docstring, this is orphaned scaffolding from
before the current pipeline existed, not an intentionally staged extension point with an unresolved reason to
retain it.

## Canonical replacements (Phase 7)

| Candidate | Relationship | Canonical module | Equivalent? |
|---|---|---|---|
| `matching_engine.py` | No replacement exists — no live "extracted vs. Excel schedule diff" path is wired into the pipeline at all. `rule_engine.py` (imported by nothing here either, but *is* the module `.claude/rules/extraction.md` names as the live "compatibility findings" source) produces a structurally distinct signal: per-token structural-plausibility scoring fed into multimodal fusion, not an Excel-vs-extraction discrepancy report. | none | not applicable — distinct responsibility, not a duplicate |
| `object_confidence.py` | Superseded by design, per its own docstring | multimodal fusion confidence (`services/multimodal/`) | not applicable — the module explicitly disclaims itself as the current confidence owner |
| `suggestion_engine.py` | Calls into the canonical path itself (`orchestrator.predict_token`) rather than being superseded by it | `services/prediction/orchestrator.py` (already the sole recognized inference entrypoint per CLAUDE.md) | not applicable — `suggestion_engine.py` was already just an unused, unreachable wrapper around the real production call |
| `takeoff_interface.py` | Explicitly superseded, per its own docstring | `services/takeoff/takeoff_exporter.py` (`generate_takeoff_excel`/`build_takeoff_rows`, live behind `POST /api/takeoff/generate`) | not applicable — `takeoff_interface.py`'s exporters were never implemented (`raise NotImplementedError`); there is no behavior to compare |

No caller migration was performed for any of the 4 — none had a real (non-test) caller to migrate.

## Test-reference interpretation (Phase 8)

| Candidate test reference | Meaningful behavior tested | Canonical equivalent test | Action |
|---|---|---|---|
| `test_engineering_pipeline.py::test_excel_loader_and_matching` — `match_extraction_to_excel` half | Only `matching_engine.py`'s own output shape (`findings`/`summary` keys present) | none — no product invariant depends on this | Removed; the `load_engineering_excel` half of this test (genuinely active, `routers/engineering.py` production code) was preserved and the test renamed to `test_excel_loader`. |
| `test_engineering_pipeline.py::test_validation_confidence_suggestions_takeoff` — `build_object_confidences`/`generate_suggestions`/`build_takeoff_preview`/`score_object_bundle` | Only each deleted module's own internal scoring/shape logic | none | Removed. The test's `validate_extraction` call (`services/engineering/validation_engine.py` — **not** a named candidate, out of scope) was preserved by calling it without the now-unavailable `object_confidences` argument, which is optional; test renamed to `test_validation_report`. |
| `test_prediction_orchestrator.py::SuggestionEnginePolicyTests::test_suggestion_uses_ai_not_database_shape` | Whether `suggest_for_text_node` surfaces the AI section rather than a database-matched one | `test_prediction_orchestrator.py::OrchestratorPolicyTests::test_database_hit_does_not_override_ai_section` — tests the same product invariant (AISC database never overrides the AI-selected section) **directly against `orchestrator.predict_token`**, independent of `suggestion_engine.py` | Test class removed entirely — sole purpose was exercising the now-deleted module; the underlying invariant remains fully covered. |

No test deletion here creates a coverage gap: every assertion removed was either testing a deleted module's
own internal-only behavior, or (for the one genuine product-invariant test) had independent coverage that
does not go through any of the 4 deleted modules.

## Final classification (Phase 9)

All four: **CONFIRMED_UNUSED**. Evidence against each of the 15 points:

1. Unreachable from all production entrypoints — confirmed (no router/pipeline import).
2. No static runtime caller — confirmed (AST graph, Phase 3 above).
3. No dynamic/string/configuration caller — confirmed (Phase 4 above).
4. No package re-export dependency — confirmed (`services/engineering/__init__.py`).
5. No CLI/CI/deployment/operational-script caller — confirmed (no `.github/`, Dockerfiles clean, `scripts/` clean).
6. No retained artifact depends on its module path — confirmed (43-binary + JSON byte-scan, Phase 5).
7. No compatibility contract requires it — same evidence as #6.
8. Test-only references protect only the obsolete implementation — confirmed per-test in Phase 8, except the
   one genuine invariant, which has independent canonical coverage.
9. A current canonical implementation covers any still-required behavior — confirmed (Phase 7 table).
10. Deletion does not change package initialization — confirmed (no `__init__.py` re-exports touched).
11. Deletion does not change registration side effects — confirmed (no decorators/registries in any of the 4).
12. Relevant tests pass without it — confirmed (Phase 16 below).
13. Git history provides no unresolved reason to retain it — confirmed (Phase 6 above).
14. Recoverable through ordinary Git history — yes, plain `git rm`, no history rewrite.
15. Evidence confidence — High for all four.

## Modules deleted

- `backend/services/engineering/matching_engine.py` (302 LOC)
- `backend/services/engineering/object_confidence.py` (165 LOC)
- `backend/services/engineering/suggestion_engine.py` (213 LOC)
- `backend/services/engineering/takeoff_interface.py` (190 LOC)

Total: 870 production LOC removed.

## Related symbol/import cleanup

`services/engineering/models.py`'s `MatchStatus`, `ObjectConfidence`, and `Suggestion` dataclasses/enum were
each imported exclusively by one of the 4 deleted modules (verified via repo-wide grep for
`from services.engineering.models import`) — removed as directly related dead symbols, along with the
`field` import (no longer used) and the `Dict` import (no longer used). `GeometryKind`, `NodeKind`,
`RelationKind`, `BBox`, the module-level `to_dict()` helper, and `dataclasses_is_dataclass()` all remain —
either genuinely used by active modules (`geometry_extractor.py`, `graph_builder.py`) or pre-existing and
unrelated to the 4 candidates (see Pre-Existing Issues below).

`tests/test_documents_api.py:89-92`'s comment referencing `takeoff_interface.py` by name was updated to no
longer cite a now-deleted file, while preserving its explanation of why the live-exporter regression test
exists.

## Out-of-scope finding (not acted on)

`services/engineering/validation_engine.py` (a distinct module from `services/multimodal/validation_engine.py`)
was flagged dead by the same prior `docs/geometry_graph_audit/` audit this task drew its 4 candidates from —
but it was **not** one of the 4 modules named in this task's scope, so it was left untouched. Its sole test
coverage (inside `test_engineering_pipeline.py`, now `test_validation_report`) was deliberately preserved
during this phase's test edits. A future phase could apply the same 15-point standard to it if requested.

## Regression testing (Phase 16)

- Directly affected tests: `tests/test_engineering_pipeline.py`, `tests/test_prediction_orchestrator.py`,
  `tests/test_documents_api.py` — **19 passed, 0 failed**.
- Import/startup sanity: `python -m py_compile` on all edited files — clean; `import app` — succeeds, FastAPI
  app registers 15 routes with no error.
- Full backend suite (`python -m pytest -q`, excluding the pre-existing collection error below):
  **1287 passed, 9 failed, 3 skipped, 349 subtests passed** (from a prior established baseline of 1288
  passed / 9 known failures / 3 skipped — the delta is exactly the 1 sole-purpose test intentionally removed
  in Phase 8 above). The 9 failures are byte-for-byte the same pre-existing, unrelated set
  (`test_a2_a7_human_review.py` × 8, `test_repeated_detail_linker.py` × 1) — none import any of the 4 deleted
  modules or the removed `models.py` symbols; confirmed unrelated by name and by grep. **Zero new failures.**

## Pre-existing issues observed (not caused by, and not fixed in, this phase)

- `backend/tests/test_ground_truth_evaluator_repair.py` fails to *collect* at all — `ImportError: cannot
  import name 'length_to_feet' from 'services.takeoff.ground_truth_evaluation'`. Confirmed present verbatim at
  `HEAD` (`75aee9c`) before this phase's changes via `git show HEAD:...`; neither file was touched by this
  phase. This blocks a plain `pytest -q` from collecting anything — the full-suite numbers above were obtained
  with `--ignore=tests/test_ground_truth_evaluator_repair.py`. Left untouched — unrelated to and out of scope
  for this dead-module review.
- `services/engineering/models.py`'s `Optional` import was already unused before this phase (never referenced
  in the file body at `HEAD`, only in the import line) — left untouched per this phase's "only remove imports
  made unused by this phase" scope.
