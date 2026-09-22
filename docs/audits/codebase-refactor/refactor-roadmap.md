# Refactor Implementation Roadmap

Baseline: `main` @ `5261ee1f1c4ccc428e28ce6c739dc145fd080b8a`. Nothing in this roadmap has been implemented —
this is the proposed sequence for a **future, separately-approved** implementation pass. Each phase is scoped to
be independently reviewable and revertible. Behavior-preserving cleanup (Phases 1-9) is kept strictly separate
from any future product change (none proposed here).

---

### Phase 1 — Documentation and report organization
- **Scope**: `git mv` the 6 backend-root dated status docs into `docs/reports/*`, the 2 demo docs into
  `docs/demos/`, `MIGRATION_NOTES_v5.2.md` into `docs/history/`, and `backend/SEMANTIC_CONTRACT.md` into
  `docs/architecture/` (after a content-diff against `unified_semantic_contract.md`).
- **Exact candidate files**: see `proposed-repository-structure.md` "Exact proposed moves" table (12 files).
- **Expected benefit**: discoverable, non-conflicting documentation layout; fixes the README/CLAUDE.md
  authoritative-docs nav gap for `ENGINEERING_VALIDATION.md` and `unified_semantic_contract.md`.
- **Estimated LOC change**: 0 (pure moves) + a handful of updated cross-reference lines (~5-10 lines across 4-5
  files).
- **Required tests**: none functionally required (no code touched); sanity-check that no doc-link-checker or
  script hardcodes the old paths (grep before and after).
- **Rollback point**: tag before this phase; `git mv` moves are trivially revertible individually.
- **Risk level**: very low.
- **Behavior changes**: none.
- **Recommended commit boundaries**: one commit for the `docs/reports/*` moves, one for `demos/`+`history/`,
  one for the `SEMANTIC_CONTRACT.md` move (separate because it needs the content-diff decision first).

### Phase 2 — Generated/artifact cleanup and gitignore corrections — **DONE (forensic pass; no deletions)**
- **Scope**: resolve the `*_20260826_*` orphan snapshot directories across the 5 model families; resolve the
  originally-estimated ~150MB of near-duplicate binaries.
- **Actual result**: full retention audit performed
  (`docs/audits/codebase-refactor/model-artifact-retention-audit.md`), every claim re-verified with actual
  SHA256 hashes and static loader-tracing (not just registry-recorded checksums). **Two premises were wrong**:
  the "orphan" snapshots contain genuinely unique, non-duplicate, checksummed model data (never-promoted
  "candidate" training runs — real historical evidence), and real verified duplicate bytes total 11.3 MiB, not
  ~150MB (`exact_section`'s 4 copies, the bulk of the original estimate, are each a distinct trained model).
  The `fusion`/`geometry`/`graph` null-`active_version` question is fully resolved: `get_active_model()` is
  never called for these 3 families anywhere in the codebase, and their promotion mapping is a literal empty
  dict — null means "nothing downstream ever reads this," not a fallback of any kind. **Zero files met the
  DELETE_NOW bar. Zero files deleted.** No `.gitignore` change made (no safe pattern exists that
  distinguishes promoted from unpromoted snapshots by filename alone — see the audit's Phase 9 section for
  the recommended process-level policy instead).
- **Exact candidate files evaluated**: `backend/training/models/{exact_section,family_classifier,fusion,
  geometry,graph}/*_20260826_*/**`; `backend/training/{best_model.pkl,label_encoder.pkl,vectorizer.pkl,
  preprocessing_pipeline.pkl,exact_section_model.joblib}` vs. their versioned-snapshot counterparts — all 93
  tracked model-related files inventoried.
- **Required tests**: `test_continuous_learning_pipeline.py` (10/10, isolated registry probe), targeted suite
  (252/1/0, unchanged), full suite (1282/9-known/3, unchanged) — all run, all green.
- **Rollback point**: N/A — no destructive action taken.
- **Risk level**: realized as zero (no changes made to any model artifact, registry, or loader).
  specifically — flagged explicitly in `unused-candidates.md` §7 as unresolved).
- **Behavior changes**: none, if the loader-behavior verification above is done first; do not proceed on those
  3 families without it.
- **Recommended commit boundaries**: one commit per model family, so a bad assumption about one family doesn't
  block the other four.

### Phase 3 — Confirmed dead-file removal — **DONE**
- **Scope**: per `unused-candidates.md`, re-verify the 4 `legacy/dead-code candidate` backend modules
  (`matching_engine.py`, `object_confidence.py`, `suggestion_engine.py`, `takeoff_interface.py`) against a
  full AST-based import graph + dynamic/config/CI reference search + artifact byte-scan, then delete those
  that reach `CONFIRMED_UNUSED`.
- **Actual result**: full forensic pass (`docs/audits/codebase-refactor/dead-module-reachability-review.md`).
  All four passed every point of the 15-point `CONFIRMED_UNUSED` standard — zero production callers, zero
  dynamic/CI/Docker/artifact references, no package re-exports, no unresolved git-history reason to retain.
  All four deleted (870 LOC total). Their sole test-only references were trimmed or removed: 2 test methods
  narrowed to drop the deleted-module assertions while keeping their still-live coverage
  (`load_engineering_excel`, `validate_extraction`), and one sole-purpose test class
  (`SuggestionEnginePolicyTests`) removed outright since the invariant it exercised
  (AISC database never overrides the AI-selected section) is independently covered by
  `OrchestratorPolicyTests::test_database_hit_does_not_override_ai_section`. `services/engineering/models.py`'s
  `MatchStatus`/`ObjectConfidence`/`Suggestion` classes — each imported exclusively by one of the four deleted
  modules — were removed as directly related dead symbols. No caller migration was needed (none had a real
  non-test caller). Full evidence, commit references, and LOC accounting in that review doc.

### Phase 4 — Unused symbol and import cleanup — **DONE (14 generic-stem modules); 7 dynamically-loaded test targets not addressed**
- **Scope**: run a real static import-graph tool across `backend/` to replace this audit's textual
  stem-co-occurrence heuristic with verified results, specifically for the 14 rows marked
  `unknown/manual-review required` / generic-stem modules (`models`, `parser`, `pipeline`, `contracts`,
  `schemas`, `validation`, `service`, `normalization`) and the 7 dynamically-loaded test targets.
- **Actual result**: full forensic pass (`docs/audits/codebase-refactor/generic-module-reachability-review.md`).
  A single reusable, temporary standard-library AST script (not a repo dependency, per this phase's own "do
  not install a new global dependency" constraint) built one whole-backend import graph and queried it for
  all 14 candidates. Every one of the 14 has a proven current importer — 11 `ACTIVE_RUNTIME` (direct imports
  from `orchestrator.py`, `fusion_engine.py`, `staged_pipeline.py`, `routers/learning.py`, and others), 3
  `ACTIVE_OPERATIONAL` (`services/ml_association/{schemas,service,validation}.py` — deliberately unwired
  shadow work per `CLAUDE.md`'s own architecture invariant, protected by
  `test_ml_association_not_wired_into_production.py` and a feature flag disabled by default). **Zero
  deletions, zero caller migrations, zero production LOC changes.** A companion investigation resolved the
  pre-existing `test_ground_truth_evaluator_repair.py` collection error (`ImportError: length_to_feet`) —
  proven via git history to be a deliberate removal (merge `88222e6` consolidated two ground-truth-evaluation
  implementations into `canonical_takeoff_eval.py`, dropping the old imperial-length/tonnage schema this test
  targeted), with superseding coverage already in `test_canonical_takeoff_eval.py` (12/12 passing against
  real Burrville/GCDC workbooks) — the obsolete test file was removed (commit `230decb`), restoring full test
  collection (1299 tests, no `--ignore` needed). The 7 `importlib.util.spec_from_file_location`
  dynamically-loaded test targets were not part of this phase's scope (they load scripts by file path, not
  the 14 module candidates) and remain a follow-up item if ever prioritized.
- **Risk level**: low (tooling-driven, verifiable) — realized as expected; no regressions.
- **Behavior changes**: none.

### Phase 5 — Duplicate utility consolidation — **DONE**
- **Scope**: the 3 `DEPRECATED` shim modules (`prediction/semantic_contract.py`,
  `semantic_preprocessor/{models,serialization}.py`) — migrate internal callers to `services/semantic/
  {models,serialization}.py`, then shrink or remove the shims.
- **Actual result**: full forensic pass
  (`docs/audits/codebase-refactor/semantic-shim-and-fusion-review.md`). Two of the three shims turned out to
  house genuinely original, irreplaceable content (`semantic_contract.py`'s `example_*` functions;
  `semantic_preprocessor/models.py`'s `TextPrimitive`) and **can never be deleted** — only their dead
  re-export tails were trimmed once every real caller (5 files) was migrated to the canonical
  `services.semantic.*` modules. The third shim, `semantic_preprocessor/serialization.py`, was a pure 2-symbol
  re-export with zero non-re-export content — its 2 callers were migrated and it was deleted.
- **Symbol identity verified**, not assumed: new `tests/test_deprecated_import_compatibility.py` asserts
  `old_shim.Symbol is canonical.Symbol` for every symbol either remaining shim still re-exports (5 assertions,
  all pass).
- **Artifact/pickle compatibility**: all 32 tracked binary model files scanned byte-for-byte for the 3 shims'
  module-path strings — zero hits. One JSON report field found referencing the old path descriptively (never
  read back programmatically) — left untouched as a preserved historical report.
- **Production/script LOC**: **-44**. **Test LOC**: **+63** (one new characterization file only).
- **Required tests**: all semantic/fusion/HSS/human-review/orchestrator-adjacent tests (263 in the combined
  relevant set), the targeted suite (252/1/0), and the full suite (1282+6 new/9 known-pre-existing/3 skipped)
  — all run, all green, both after the migration and after the deletion.
- **Rollback point**: pre-phase `main` tip (`339429f`).
- **Risk level**: realized as low — no behavior changed anywhere; only import sources and dead-code removal.
- **Commit boundaries used**: characterization tests, import migration, shim deletion, and documentation as
  4 separate commits (see the phase's own commit list).

### Phase 6 — Backend module-boundary cleanup — **PARTIALLY DONE**
- **Scope**: `fusion_engine.py` vs `modular_fusion.py` review (confirm/resolve the thin-adapter question);
  the coordinated `validation/semantic_test_pdfs/` → `backend/tests/fixtures/semantic_test_pdfs/` move and its
  4 reference updates.
- **Fixture move**: already completed in an earlier phase (`test(fixtures): relocate semantic PDF fixtures`,
  commit `0c3d292`) — not repeated here.
- **`fusion_engine.py` vs `modular_fusion.py` — resolved, no code change**: traced exactly via
  `orchestrator.py`'s own imports. `orchestrator.py` calls `modular_fusion.py::unified_multimodal_fusion.predict()`
  directly; `fusion_engine.py`'s `WeightedFusionEngine.predict()` calls `orchestrator.py::predict_from_context()`
  (not `modular_fusion.py`) and reshapes its result into an older dataclass contract that
  `services/multimodal/pipeline.py` (the real caller) expects. **Zero functional overlap** — a 3-layer chain,
  not two competing implementations. Both files are independently required; both are already explicitly
  recognized as production code in the `_PRODUCTION_MODULES` guard-test lists. No consolidation performed, no
  differential testing applicable (the two functions do not accept comparable inputs). See the full
  reachability matrix in `semantic-shim-and-fusion-review.md`.
- **Risk level**: realized as zero (no code changed).

### Phase 7 — Frontend component/hook consolidation — **DONE (partially; see result)**
- **Scope**: `StatsCards.jsx` → compose `KpiCard.jsx`; badge/chip trio → shared `ChipWithMeta` primitive.
- **Exact candidate files**: see `refactor-opportunities.md` items 1-2.
- **Expected benefit** (original estimate): ~130 LOC net reduction, one fewer place to keep 3
  visually-similar chip styles in sync.
- **Estimated LOC change** (original estimate): -55 (StatsCards), -75 (badge/chip trio) ≈ -130 total.
- **Actual result**: `StatsCards.jsx` implemented and kept, **-8 LOC** (35→27). Badge/chip trio implemented,
  measured at **+30 LOC** (not a reduction — `MetaChip`'s own overhead exceeded what 2 already-lean call
  sites saved), and **reverted** in the same pass; `EntityTypeChip` was correctly identified up front as
  needing to stay separate (custom theming mechanism). See `refactor-opportunities.md` items 1-2 for full
  detail and the measured-vs-estimated reasoning. **Net actual LOC for this phase: -8, not -130.**
- **Required tests**: existing component tests for all 5 affected files (`StatsCards`, `KpiCard`,
  `OperationBadge`, `MatchStatusBadge`, `EntityTypeChip`) plus the frontend full suite (217 tests) and the
  4 pages that render them (Dashboard, ModelPage, SemanticReviewPage, wherever MatchStatusBadge renders) —
  all run, all green, both during implementation and after the badge/chip revert.
- **Rollback point**: the pre-phase commit (`0c3d292`, tag-equivalent since it's the prior pushed `main` tip).
- **Risk level**: low, with one exception — `MatchStatusBadge` mirrors
  `canonical_contract.py::MatchStatus`; the shared-primitive attempt was verified against all 13
  `MatchStatusBadge.test.jsx` assertions (including `aria-label`) before being reverted for LOC reasons, not
  a correctness reason.
- **Behavior changes**: none — `StatsCards`' data/label logic and Grid layout are byte-identical to before;
  the reverted badge/chip files are byte-identical to their pre-phase state.
- **Commit boundaries actually used**: one commit for `StatsCards`/`KpiCard`
  (`refactor(frontend): reuse KPI card presentation`); no badge/chip commit was created since that work was
  reverted before staging.

### Phase 8 — Test-fixture and helper cleanup — **DONE**
- **Scope**: extract `IsolatedApiTestCase` + `_REDIRECTED_SETTINGS` from `test_documents_api.py`; reduce setup
  duplication between `test_geometry_fragment_merge.py` and `test_merge_collinear_fragments_transitive_growth.py`.
- **Exact candidate files**: see `refactor-opportunities.md` items 5-6.
- **Actual location chosen**: `backend/tests/helpers/isolated_api.py` and
  `backend/tests/helpers/geometry_fixtures.py` — a plain module, **not** `conftest.py`. `IsolatedApiTestCase`
  is a subclassing base class (5 real consumers do `class Foo(IsolatedApiTestCase)`), which is a fundamentally
  different pattern from pytest fixture injection; moving it into `conftest.py` would have forced a much
  larger rewrite of all 5 consumers for no isolation-guarantee benefit.
- **Actual benefit**: discoverable shared test infrastructure (no test file importing from another test file
  anymore); real duplication removed from the geometry pair (single `line_fragment()` builder, was defined
  twice, byte-identical).
- **Actual LOC change**: +11 across the 5 IsolatedApiTestCase-related files (organizational, as estimated —
  there was only ever one copy of that code, so no reduction was ever available there); **-5** for the
  geometry pair (real duplication removed, close to the low end of the ~20-40 estimate once "genuinely
  shared" was applied strictly — only the builder function qualified, not any test logic).
- **Required tests**: all 6 IsolatedApiTestCase-related files (76 tests) + both geometry files (8 tests) — all
  run, all green. Targeted suite (252/1/0) and full suite (1282/9-known/3, all 9 failures pre-existing and
  identically reproduced) also verified unaffected.
- **Rollback point**: pre-phase `main` tip (`6aa5ee8`).
- **Risk level**: low, realized as low — zero test-count change, zero assertion change, isolation guarantee
  proven intact via file-fingerprint comparison before/after.
- **Behavior changes**: none.
- **Commit boundaries used**: `test(api): centralize isolated API test setup`,
  `test(geometry): deduplicate fragment merge setup`, `docs(refactor): record backend test cleanup`.

### Phase 9 — Configuration consolidation
- **Scope**: audit `.env.example` against actual `config.py` `Settings` fields for completeness (no gaps
  found in this pass, but not exhaustively cross-checked field-by-field); confirm `skills-lock.json` accounts
  for every externally-sourced skill (gap found: `scikit-learn` and `task-observer` skills are externally
  licensed but have no `skills-lock.json` entry, unlike `deploy-to-vercel`/`web-design-guidelines`).
- **Exact candidate files**: `.env.example`, `skills-lock.json`, `.claude/skills/{scikit-learn,task-observer}/`.
- **Expected benefit**: consistent provenance tracking for all externally-sourced tooling.
- **Estimated LOC change**: a few added lines in `skills-lock.json`.
- **Required tests**: none (metadata-only change).
- **Rollback point**: tag before this phase.
- **Risk level**: very low.
- **Behavior changes**: none.
- **Recommended commit boundaries**: one commit.

### Phase 10 — Final regression and deployment verification
- **Scope**: full backend suite, full frontend suite, frontend production build, backend import/startup
  sanity, deployment-readiness checklist (matching this audit's own Phase 8 baseline) re-run after Phases 1-9
  land, on the accumulated diff.
- **Exact candidate files**: N/A — this is a verification phase, not a file-change phase.
- **Expected benefit**: proves the entire behavior-preserving cleanup sequence actually preserved behavior.
- **Estimated LOC change**: 0.
- **Required tests**: backend targeted (252/1/0 baseline) + full suite (1282/9-known-failures/3-skipped
  baseline, 9 pre-existing) + frontend (217/217 baseline) + frontend build + Pyright (attempted in this audit,
  did not complete in reasonable time — recommend a scoped/incremental Pyright run rather than a full
  cold-cache pass, or an explicit longer timeout, as a tooling follow-up).
- **Rollback point**: this phase IS the gate before merging the whole sequence to a shared branch.
- **Risk level**: N/A (verification only).
- **Behavior changes**: this phase's entire purpose is confirming there are none beyond what each prior
  phase's own test run already showed.
- **Recommended commit boundaries**: no new commits; this is a CI/manual verification pass over the
  accumulated Phase 1-9 commits before requesting final review.

### Phase 11 — Pre-orchestrator utility/config consolidation — **DONE**
- **Scope**: final consolidation pass before any `prediction/orchestrator.py` decomposition work — genuinely
  duplicated utilities/parsing/formatting/configuration-reading, plus the dynamic test-loader count from
  `unused-candidates.md` §9.
- **Actual result**: full pass at `pre-orchestrator-consolidation-review.md`. All prior recorded opportunities
  were already closed (nothing left to re-evaluate); a fresh scoped search found exactly 3 genuine production
  duplications, all implemented: a byte-identical boolean env-var parser
  (`multimodal/feature_providers.py::_ablation_active` / `multimodal/pipeline.py::_ablate`, consolidated onto
  `feature_providers.py`), two trivial wrapper functions around an already-directly-imported canonical
  normalizer (`multimodal/schedule_ingestion.py`/`spatial_association.py::_norm`, both removed), and a
  byte-identical label-normalization helper duplicated across the runtime/training boundary
  (`takeoff/takeoff_validation.py`/`training_pipeline/neural_dataset.py::_norm`, consolidated onto a new
  public `takeoff_validation.normalize_takeoff_label`). The dynamic-test-loader count was corrected from the
  audit's claimed 7 to a verified 5; one (`test_anonymous_dimension_resolver_context.py`) had no isolation
  purpose and was migrated to a normal package import; the other 4 (all loading non-package `scripts/*.py`
  files, which genuinely have no other way to be imported) were consolidated onto one new shared
  `tests/helpers/script_loader.py` helper. 9 new characterization tests added (zero prior coverage existed
  for either consolidated production function). Net: production LOC **-18**, test LOC **+42** (net new
  regression coverage, not organizational bloat). Targeted (224/1/0/40-subtests) and full suite both verified
  unchanged in known-failure set; all 3 preserved training-drift files' SHA256 fingerprints confirmed
  unchanged throughout.
- **Risk level**: realized as low — zero behavior change, zero public API/schema/route/env-var change.

---

## Cross-phase notes

- Phases 1, 2, 9 have no code-behavior risk and can be done in any order, first.
- Phases 3 and 4 are both done (see above) — each used its own dedicated, disjoint-scope AST script rather
  than a shared general-purpose tool; Phase 3 found 4 confirmed-unused modules and deleted them, Phase 4
  found all 14 of its candidates still genuinely reachable and deleted none.
- Phases 5, 6 are the highest-risk (contract-adjacent, prediction-pipeline-adjacent) — do them after 1-4 have
  built confidence in the process, and land them in the smallest possible commits.
- Phases 7, 8 are independent of everything else and of each other — can be parallelized across sessions/PRs.
- Phase 10 is mandatory before any of Phases 1-9's changes reach a shared/deployment branch.
