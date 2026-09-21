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

## 1. Frontend: `StatsCards.jsx` → compose `ui/KpiCard.jsx`

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

## 2. Frontend: badge/chip trio → shared primitive

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

## 5. Backend tests: shared fixture with no `conftest.py`

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

## 6. Backend tests: near-duplicate geometry-merge test pair

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
