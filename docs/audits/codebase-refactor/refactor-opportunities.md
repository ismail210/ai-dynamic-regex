# Duplication and Line-Reduction Audit

Baseline: `main` @ `5261ee1f1c4ccc428e28ce6c739dc145fd080b8a`. Every opportunity below preserves current
behavior, public interfaces, and — for anything touching prediction/takeoff logic — the exact-match semantic
locking and takeoff semantics CLAUDE.md protects. None of these were implemented in this pass; this is a
proposal list only, ordered roughly by safety/confidence, not by size.

## Rejected-by-design (explicitly NOT proposed here)

Per this audit's own instructions, the following patterns were found and are **intentionally excluded** from
consolidation because collapsing them would violate a named invariant:

- `frontend/src/lib/predictionContract.js` vs `frontend/src/lib/semanticContract.js` — parallel but
  intentionally separate contract boundaries (prediction explainability vs. Semantic Review domain). CLAUDE.md
  requires both to exist independently; do not merge.
- `PredictionExplainability.jsx` / `PredictionDetailModal.jsx` sharing renderer logic — CLAUDE.md explicitly
  designates `PredictionExplainability` the single shared renderer across Review Queue, Validation, and
  Prediction Details; this is the *intended* shape, not duplication to remove.
- `services/label_reconstruction/*`, `services/ml_association/*` vs production prediction code — must stay
  separate by guard-tested design; never fold into `orchestrator.py`.
- The two disagreeing training/promotion systems (`train_model.py` family vs `train_neural_models.py` family)
  — `docs/ml_integration/partner_vs_local_comparison.md` frames this as an **unresolved architecture decision**,
  not a refactor. Reconciling them changes model-selection behavior and is out of scope for a
  behavior-preserving cleanup; flagged for a separate, explicitly-scoped decision, not bundled here.

## 1. Frontend: `StatsCards.jsx` → compose `ui/KpiCard.jsx` — **IMPLEMENTED**

> **Result** (commit `refactor(frontend): reuse KPI card presentation`): `StatsCards.jsx` now composes
> `<KpiCard>` per stat instead of inline `Card`/`CardContent`/`Typography` markup. Actual: 35 → 27 LOC
> (**-8**, not the estimated ~55 — the original estimate assumed more Card-layout boilerplate than the
> component actually had). `KpiCard.jsx` needed zero changes. Its one consumer (`ResultsBody.jsx`) required
> no changes — `StatsCards`' external prop signature (`{data}`) is unchanged. Data/label computation logic is
> byte-for-byte unchanged. `StatsCards` has zero dedicated test coverage (it is explicitly mocked to `null` in
> `AnalysisResultsPage.test.jsx`), so there was no pixel-level snapshot to preserve; its 5 stat values/labels
> and Grid responsive breakpoints (`{xs:6, sm:4, md:2.4}`, `spacing={1.5}`) were preserved exactly. Full
> 217/217 frontend suite and production build verified green after the change.

- **Affected files**: `frontend/src/components/StatsCards.jsx`, `frontend/src/components/ui/KpiCard.jsx`.
- **Current approx LOC**: StatsCards ~90 (inline Card/Typography markup for 5 stats), KpiCard ~55.
- **Estimated LOC after cleanup**: StatsCards ~35 (renders 5 `<KpiCard>` instances), KpiCard unchanged.
- **Estimated net reduction**: ~55 LOC, plus one fewer independent Card-layout implementation to keep visually
  consistent going forward.
- **Duplication evidence**: both render a Card with a caption label + large value Typography in a grid;
  StatsCards computes 5 stats inline instead of taking the reusable KpiCard component as children (verified by
  reading both files' JSX structure, not just filename similarity).
- **Proposed design**: `StatsCards` becomes a thin composition wrapper over `KpiCard`, passing
  `{label, value, hint, link}` props per stat.
- **Behavior that must remain unchanged**: visual output (spacing, typography scale) on the Dashboard/Model
  pages where StatsCards is used.
- **Public interfaces affected**: none — `StatsCards`' own external prop signature can stay the same.
- **Related tests**: check for a `StatsCards.test.jsx` / `KpiCard.test.jsx` (not confirmed present in this
  pass — verify before implementing, add one if missing).
- **Risk level**: low.
- **Recommended implementation order**: early (Phase 7 of the roadmap) — small, isolated, good pilot for the
  frontend-consolidation phase.

## 2. Frontend: badge/chip trio → shared primitive — **EVALUATED, NOT IMPLEMENTED (reverted after measurement)**

> **Result**: implemented, measured, then deliberately reverted. `EntityTypeChip.jsx` was left separate as
> planned (custom theme-mode-aware alpha-blended `sx` palette, no MUI `color`/`variant` theming — materially
> different styling mechanism from the other two). A shared `MetaChip.jsx` primitive (31 LOC) was built and
> wired into `OperationBadge.jsx` (40→39 LOC) and `MatchStatusBadge.jsx` (70→70 LOC, net neutral — its
> Chip-wrapping boilerplate was replaced but a new `resolvedTooltip` line was added). All 13
> `MatchStatusBadge.test.jsx` assertions (including the `aria-label` check) and all other consumer tests
> passed. **Measured net LOC for this piece: 110 → 140, i.e. +30, an increase, not a reduction.** Both
> `OperationBadge` and `MatchStatusBadge` were already lean — each had only ~5-8 lines of actual Chip/Tooltip
> boilerplate — so `MetaChip`'s own necessary overhead (imports, prop documentation, conditional tooltip
> logic) cost more than the two call sites saved. Per this document's own instruction ("do not force a
> consolidation to meet the LOC estimate") and the refactor task's explicit LOC-measurement requirement, the
> `MetaChip` extraction was reverted in the same session it was built — `OperationBadge.jsx` and
> `MatchStatusBadge.jsx` are back to their original, unmodified form. **Conclusion: none of the three
> badge/chip components should be consolidated.** They are already appropriately separate, minimal
> implementations; the apparent "same shape" (enum → meta lookup → styled Chip) does not translate into
> reusable boilerplate once each component's actual icon/tooltip/accessibility/theming differences are
> accounted for.

- **Affected files**: `frontend/src/components/semantic/OperationBadge.jsx`,
  `frontend/src/components/ui/MatchStatusBadge.jsx`, `frontend/src/components/ui/EntityTypeChip.jsx`.
- **Current approx LOC**: 40 + ~60 + 71 ≈ 171 combined, each with its own `STATUS_META`-style lookup map.
- **Estimated LOC after cleanup**: a shared `ChipWithMeta` primitive (~50 LOC) + 3 thin domain-specific
  meta-map files (~15 LOC each) ≈ 95 LOC.
- **Estimated net reduction**: ~75 LOC.
- **Duplication evidence**: identical shape (label + color/icon looked up from a status/type string via a
  local map, rendered as an MUI `Chip`), three independent implementations, three different domains
  (semantic operation, prediction match status, entity type).
- **Proposed design**: extract a generic `<ChipWithMeta value={} metaMap={} />` primitive under
  `components/ui/`; each of the 3 call sites supplies its own meta map (unchanged data) instead of its own
  component.
- **Behavior that must remain unchanged**: `MatchStatusBadge` explicitly mirrors
  `backend/services/prediction/canonical_contract.py::MatchStatus` per its own doc comment — the shared
  primitive must **not** weaken or reinterpret that mapping; it only removes the duplicated Chip-rendering
  shell.
- **Public interfaces affected**: none externally (still 3 components with the same import names); the shared
  primitive is an internal implementation detail.
- **Related tests**: verify each of the 3 has (or gains) a component-level test asserting label/color mapping
  is unchanged after extraction.
- **Risk level**: low — MatchStatusBadge's contract-mirroring role means this MUST be reviewed against
  `canonical_contract.py::MatchStatus` before merging, but the change itself is a pure render-shell extraction.
- **Recommended implementation order**: after item 1, same phase.

## 3. Backend: three `DEPRECATED` shim modules still actively imported

- **Affected files**: `backend/services/prediction/semantic_contract.py`,
  `backend/services/semantic_preprocessor/models.py`, `backend/services/semantic_preprocessor/serialization.py`
  (all self-declared `DEPRECATED` in their own docstrings, superseded by `services/semantic/{models,
  serialization}.py`).
- **Current approx LOC**: not consolidated in this pass — sizes vary; treat as a migration, not a deletion.
- **Estimated LOC after cleanup**: these 3 files should shrink to pure re-export shims (a handful of lines each)
  once every internal caller is migrated to `services/semantic/*` directly, then be removed in a later, separate
  change once zero internal callers remain.
- **Estimated net reduction**: not estimated here — the safe first step is a **caller migration**, not a line
  count. Do not delete these files in the same change that migrates callers; land the migration, verify tests,
  then delete in a follow-up.
- **Duplication evidence**: self-declared in each file's own docstring; confirmed still imported by grep across
  the 204-file backend-runtime-core scope (not just referenced by tests).
- **Proposed design**: (a) enumerate every internal import of the 3 shim modules, (b) redirect each to
  `services/semantic/{models,serialization}.py`'s equivalent symbol, (c) once zero internal imports remain,
  reduce the shim files to a deprecation-only re-export (for any external/old import paths that must keep
  working) or remove them entirely if nothing outside the repo depends on the old path.
- **Behavior that must remain unchanged**: the v2 explainability contract shape (CLAUDE.md) must render
  identically after migration — this is exactly the kind of change CLAUDE.md's "do not fork its shape" rule is
  about, so migrate call sites one at a time with tests green after each.
- **Public interfaces affected**: internal import paths only, if no external consumer exists; treat as
  contract-adjacent and get explicit sign-off before removing (not just consolidating) per CLAUDE.md's
  "Preserve public API / contract shapes unless the task is explicitly changing them."
- **Related tests**: the semantic-contract-shape tests referenced in CLAUDE.md's architecture-invariants
  section (Review Queue / Validation / Prediction Details rendering).
- **Risk level**: medium — touches a protected contract; sequence carefully, small commits, test after each.
- **Recommended implementation order**: mid-roadmap (Phase 5), after simpler wins are proven safe.

## 4. Backend: `fusion_engine.py` thin-adapter vs `modular_fusion.py`

- **Affected files**: `backend/services/multimodal/fusion_engine.py`, `backend/services/multimodal/modular_fusion.py`.
- **Duplication evidence**: `fusion_engine.py` is self-documented (per `.claude/rules/backend.md`) as a thin
  adapter over the real fusion logic in `modular_fusion.py`.
- **Proposed design**: not a merge candidate as-is (the adapter may exist deliberately for a narrower call
  contract) — flagged as `manual decision required`; the first step is confirming with `.claude/rules/backend.md`
  and orchestrator.py's actual call sites whether the adapter layer is still earning its keep, before any code
  change.
- **Risk level**: medium (touches the fusion stage of the prediction pipeline).
- **Recommended implementation order**: late (Phase 6), after the shim migration above establishes a safe
  pattern for this kind of adapter consolidation.

## 5. Backend tests: shared fixture with no `conftest.py` — **IMPLEMENTED**

> **Result** (commit `test(api): centralize isolated API test setup`): `IsolatedApiTestCase` and
> `_REDIRECTED_SETTINGS` moved verbatim (identical setUp/tearDown order, identical redirected-path list,
> identical addCleanup/patch semantics) to new `backend/tests/helpers/isolated_api.py`. A plain module under
> `tests/helpers/` was chosen over `conftest.py`, per this audit's own Phase-1 guidance: the existing pattern
> is unittest.TestCase **subclassing** (`class Foo(IsolatedApiTestCase)`), not pytest fixture injection —
> `conftest.py` fixtures would have required rewriting every consumer's class structure, a much larger and
> riskier change than "centralize the shared setup." 5 real consumers found and migrated (not the 4 initially
> visible from grepping only `IsolatedApiTestCase` imports — `test_test_isolation.py` separately imports
> `_REDIRECTED_SETTINGS` directly, and has its own static guard test (`DocumentsApiRedirectListTests`)
> asserting specific entries stay in that list, protecting against a real historical training-data leak bug).
> `test_documents_api.py` now contains only its own 3 test classes and its own local `_drawing()` fixture
> builder. All 76 tests across the 6 directly-affected files pass; full targeted (252/1/0) and full suite
> (1282/9-known/3, identical to baseline) both verified. Net LOC: +11 across the 5 touched files (73 lines
> moved out of `test_documents_api.py`, 89 lines in the new standalone module with its own complete docstring)
> — this phase was about ownership/discoverability, not size; there was only ever one copy of this code, just
> an awkward location, not true duplication.

- **Affected files**: `backend/tests/test_documents_api.py` (defines `IsolatedApiTestCase` +
  `_REDIRECTED_SETTINGS`), imported by `test_human_review_selection_api.py`, `test_semantic_api.py`,
  `test_semantic_api_repair_review.py`, `test_semantic_corrected_pdf.py`, `test_test_isolation.py` (5 files).
- **Duplication evidence**: **no `conftest.py` exists anywhere in `backend/tests/`** — confirmed by directory
  listing — so 5 unrelated test files import test infrastructure from what looks like an ordinary test module.
- **Proposed design**: extract `IsolatedApiTestCase` + `_REDIRECTED_SETTINGS` into `backend/tests/conftest.py`
  (or `backend/tests/_helpers.py` if pytest fixture semantics aren't wanted); update the 5 importers plus
  `test_documents_api.py` itself to import from the new location.
- **Estimated net reduction**: near-zero LOC change, but removes a confusing "test file imports from another
  test file" pattern and gives future test authors a discoverable place to look.
- **Behavior that must remain unchanged**: test isolation semantics (settings redirection) must be identical.
- **Related tests**: all 6 files listed above — run the full set after the extraction.
- **Risk level**: low.
- **Recommended implementation order**: Phase 8 of the roadmap (test-fixture cleanup) — independent of the
  production-code phases, can happen any time.

## 6. Backend tests: near-duplicate geometry-merge test pair — **IMPLEMENTED (setup only, as scoped)**

> **Result** (commit `test(geometry): deduplicate fragment merge setup`): the byte-identical private `_line()`
> fragment-builder defined independently in both files was extracted to
> `backend/tests/helpers/geometry_fixtures.py` as `line_fragment()`, imported back under the original `_line`
> alias in both files (`from tests.helpers.geometry_fixtures import line_fragment as _line`) to keep every
> call site unchanged. **All 8 tests in both files were kept — none merged or removed.** Confirmed each covers
> a genuinely distinct scenario: `test_geometry_fragment_merge.py` (5 tests) covers ordinary short-chain
> merging, non-collinear/non-line-kind exclusion, scale-derived tolerance (a different function,
> `fragment_gap_pdf_points`), and PDF-integration via `extract_geometry`; `test_merge_collinear_fragments_
> transitive_growth.py` (3 tests) is a diagnostic-only regression file (per its own docstring, tied to
> `docs/validation/phase_d2_merge_forensics.md`) proving union-find transitive closure has no cap on cluster
> size, using exactly-at-tolerance gaps rather than the other file's small margins. No two tests share
> equivalent inputs+assertions, so per this document's own removal criteria, none qualified for merging.
> Net LOC: -12 and -12 on the two test files (-24 total, real duplication removed), +19 for the new shared
> helper — **-5 net**, close to the low end of the original ~20-40 estimate once the "genuinely shared" bar
> was applied strictly (only the builder was shared; nothing else was).

- **Affected files**: `backend/tests/test_geometry_fragment_merge.py`,
  `backend/tests/test_merge_collinear_fragments_transitive_growth.py` — both exercise
  `services.engineering.geometry_normalizer.merge_collinear_fragments`.
- **Duplication evidence**: verified by reading test method names, not just imports — not true duplicates
  (general merge cases vs. one specific transitive-chain-growth regression case), but overlapping setup.
- **Proposed design**: consolidate shared fixture/setup helpers into one shared function or fixture; keep both
  test files (the transitive-growth one guards a specific regression and should stay named/discoverable
  separately) but stop duplicating the fragment-construction boilerplate between them.
- **Estimated net reduction**: modest (~20-40 LOC of setup duplication).
- **Risk level**: low.
- **Recommended implementation order**: Phase 8, alongside item 5.

## 7. Backend training: duplicate/superseded generations (data-file consolidation, not code)

Already detailed in `unused-candidates.md` §7 — the `*_20260826_*` orphan snapshot across all 5 model families,
and the ~150MB of near-duplicate binaries between flat live-aliases and versioned snapshots. This is a
**generated-artifact cleanup**, not a code refactor; tracked separately in `refactor-roadmap.md` Phase 2, not
bundled with the code-duplication items above since the risk profile and reversal method (re-download/re-train
vs. `git revert`) are completely different.

## Summary table

| # | Item | Est. LOC reduction | Risk | Order |
|---|---|---|---|---|
| 1 | StatsCards → KpiCard composition | ~55 | low | early |
| 2 | Badge/chip trio → shared primitive | ~75 | low | early |
| 3 | 3 DEPRECATED shim modules → migrate callers | not estimated (migration first) | medium | mid |
| 4 | fusion_engine.py vs modular_fusion.py | manual decision required | medium | late |
| 5 | Shared test fixture → conftest.py | ~0 (organizational) | low | test-cleanup phase |
| 6 | Geometry-merge test setup dedup | ~20-40 | low | test-cleanup phase |
| 7 | Superseded training snapshots/binaries | large (data, not code) | low (data-only) | generated-artifact phase |

No item in this list optimizes for raw line count alone; every proposal above preserves the module boundary,
public interface, and safety/validation logic it touches, per this audit's explicit rejection criteria.
