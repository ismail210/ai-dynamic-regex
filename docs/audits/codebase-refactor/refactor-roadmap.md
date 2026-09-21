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

### Phase 2 — Generated/artifact cleanup and gitignore corrections
- **Scope**: resolve the `*_20260826_*` orphan snapshot directories across the 5 model families (archive or
  document why they're intentionally kept off-registry); resolve the ~150MB of near-duplicate binaries between
  flat live-aliases and versioned snapshots (either gitignore the versioned copies if the flat alias is truly
  sufficient, or document why both must stay tracked).
- **Exact candidate files**: `backend/training/models/{exact_section,family_classifier,fusion,geometry,graph}/
  *_20260826_*/**`; `backend/training/{best_model.pkl,label_encoder.pkl,vectorizer.pkl,
  preprocessing_pipeline.pkl,exact_section_model.joblib}` vs. their versioned-snapshot counterparts.
- **Expected benefit**: meaningfully smaller repo, less confusion about which model artifact is "live."
- **Estimated LOC change**: N/A (binary/data cleanup, not code) — could remove tens of MB from the tracked tree.
- **Required tests**: full backend suite (to confirm nothing silently depended on an orphan snapshot path) +
  manual verification that `config.py`'s `settings.*_path` fields still resolve correctly after any change.
- **Rollback point**: tag before this phase; this is the highest-value-per-risk phase but touches binary
  artifacts, so a clean rollback tag matters more here than in Phase 1.
- **Risk level**: low-medium (binary artifacts are easy to accidentally need later; verify `fusion`/`geometry`/
  `graph`'s null-`active_version` loader behavior **before** removing anything from those 3 families
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

### Phase 5 — Duplicate utility consolidation
- **Scope**: the 3 `DEPRECATED` shim modules (`prediction/semantic_contract.py`,
  `semantic_preprocessor/{models,serialization}.py`) — migrate internal callers to `services/semantic/
  {models,serialization}.py`, then shrink or remove the shims.
- **Exact candidate files**: see `refactor-opportunities.md` item 3 for the full plan.
- **Expected benefit**: removes 3 deprecated code paths once callers are migrated; reduces risk of new code
  accidentally depending on the deprecated shape.
- **Estimated LOC change**: not estimated until caller enumeration is done (first step of this phase).
- **Required tests**: the semantic-contract-shape tests CLAUDE.md's architecture-invariants section names
  (Review Queue / Validation / Prediction Details rendering) — must pass identically before and after each
  caller migration.
- **Rollback point**: tag before this phase; migrate one caller at a time so a bad migration is a one-file
  revert, not a phase-wide one.
- **Risk level**: medium — this is CLAUDE.md-protected contract-adjacent code.
- **Behavior changes**: none intended; this is the phase most likely to reveal a hidden behavior difference
  between old and new contract shapes, so treat any test change as a stop-and-investigate signal, not a test
  update.
- **Recommended commit boundaries**: one commit per caller migrated, final commit removes/shrinks the shim only
  after zero internal callers remain.

### Phase 6 — Backend module-boundary cleanup
- **Scope**: `fusion_engine.py` vs `modular_fusion.py` review (confirm/resolve the thin-adapter question);
  the coordinated `validation/semantic_test_pdfs/` → `backend/tests/fixtures/semantic_test_pdfs/` move and its
  4 reference updates.
- **Exact candidate files**: `backend/services/multimodal/fusion_engine.py`,
  `backend/services/multimodal/modular_fusion.py`; `validation/semantic_test_pdfs/**` and its 4 referencing
  files (`test_semantic_damage_manifests.py`, `test_semantic_precedence_task_regression.py`,
  `build_semantic_damage_test_pdfs.py`, `validate_demo_correction_flow.py`).
- **Expected benefit**: clearer module ownership; fixture in its conventional location.
- **Estimated LOC change**: path-string changes only for the fixture move (~4-8 lines across 4 files); the
  fusion_engine review's LOC impact depends on its outcome (manual decision required, not pre-committed here).
- **Required tests**: the 2 directly-affected test files, plus a full backend run to catch any other
  path-relative assumption this audit's grep missed.
- **Rollback point**: tag before this phase.
- **Risk level**: medium (touches the prediction pipeline's fusion stage and a path used by both backend and
  frontend fixtures).
- **Behavior changes**: none intended.
- **Recommended commit boundaries**: fixture move as its own commit (small, mechanical); fusion_engine.py
  decision as a separate commit only after the manual review concludes.

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

### Phase 8 — Test-fixture and helper cleanup
- **Scope**: extract `IsolatedApiTestCase` + `_REDIRECTED_SETTINGS` from `test_documents_api.py` into a new
  `backend/tests/conftest.py`; reduce setup duplication between `test_geometry_fragment_merge.py` and
  `test_merge_collinear_fragments_transitive_growth.py`.
- **Exact candidate files**: see `refactor-opportunities.md` items 5-6.
- **Expected benefit**: discoverable shared test infrastructure; less duplicated fixture-construction code.
- **Estimated LOC change**: near-zero net (organizational), minus ~20-40 LOC of duplicated setup.
- **Required tests**: the 6 files touched by the conftest extraction; the 2 geometry-merge test files.
- **Rollback point**: tag before this phase.
- **Risk level**: low.
- **Behavior changes**: none.
- **Recommended commit boundaries**: conftest extraction as one commit, geometry-merge setup dedup as another
  — independent of each other.

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
