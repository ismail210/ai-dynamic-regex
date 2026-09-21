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

### Phase 3 — Confirmed dead-file removal
- **Scope**: per `unused-candidates.md`, **nothing currently qualifies** as confirmed-unused. This phase is a
  placeholder that only activates if a deeper, AST-based import-graph pass (recommended in Phase 4 below)
  upgrades one of the 4 `legacy/dead-code candidate` backend modules from "high-confidence unused" to
  "confirmed unused."
- **Exact candidate files**: `backend/services/engineering/{matching_engine.py, object_confidence.py,
  suggestion_engine.py, takeoff_interface.py}` — pending the Phase 4 verification, not pre-approved for
  deletion here.
- **Expected benefit**: ~4 files, low LOC impact; the value here is clarity, not size.
- **Estimated LOC change**: unknown until each file's actual size is confirmed at decision time.
- **Required tests**: each file's owning test(s) must be explicitly deleted or re-targeted in the same commit
  as the source file — never leave a test importing a deleted module.
- **Rollback point**: tag before this phase.
- **Risk level**: low individually, but gated on Phase 4's tooling result — do not skip the verification step.
- **Behavior changes**: none expected (these are confirmed to have zero production callers), but
  `suggestion_engine.py` specifically needs the orchestrator.py cross-check called out in
  `unused-candidates.md` before deletion, since it may be a classical-ML fallback path.
- **Recommended commit boundaries**: one file per commit (4 commits), each removing the source file and its
  dedicated test together.

### Phase 4 — Unused symbol and import cleanup
- **Scope**: run a real static import-graph tool (`pyflakes`, `modulegraph`, or an AST-based checker — not
  installed in this environment; see `README.md`'s optional-tooling note) across `backend/` to replace this
  audit's textual stem-co-occurrence heuristic with verified results, specifically for the 14 rows marked
  `unknown/manual-review required` / generic-stem modules (`models`, `parser`, `pipeline`, `contracts`,
  `schemas`, `validation`, `service`, `normalization`) and the 7 dynamically-loaded test targets.
- **Exact candidate files**: the 14 rows flagged in `unused-candidates.md` §9; cross-reference against
  `file-inventory.csv`'s `confidence_level` column for exact list.
- **Expected benefit**: converts "medium confidence" findings to verified ones before Phase 3/5/6 rely on them.
- **Estimated LOC change**: 0 (this phase is tooling + verification, not code changes) beyond whatever unused
  imports the tool itself surfaces (typically small, single-line removals).
- **Required tests**: full backend suite after any import removal.
- **Rollback point**: tag before this phase.
- **Risk level**: low (tooling-driven, verifiable).
- **Behavior changes**: none.
- **Recommended commit boundaries**: one commit per subsystem the tool flags, not one giant commit.

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

---

## Cross-phase notes

- Phases 1, 2, 9 have no code-behavior risk and can be done in any order, first.
- Phases 3, 4 must happen in that relative order (4 before 3) since Phase 3 is gated on Phase 4's tooling
  verification.
- Phases 5, 6 are the highest-risk (contract-adjacent, prediction-pipeline-adjacent) — do them after 1-4 have
  built confidence in the process, and land them in the smallest possible commits.
- Phases 7, 8 are independent of everything else and of each other — can be parallelized across sessions/PRs.
- Phase 10 is mandatory before any of Phases 1-9's changes reach a shared/deployment branch.
