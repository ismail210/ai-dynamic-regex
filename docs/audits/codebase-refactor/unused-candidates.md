# Unused and Dead-Code Analysis

Baseline: `main` @ `5261ee1f1c4ccc428e28ce6c739dc145fd080b8a`. All candidates below were grep-verified across the
whole tracked tree (not just their own subsystem) before being listed. **None were deleted, edited, or moved —
this is a findings list only.** Nothing in this document rises to "confirmed unused" under the strict bar CLAUDE.md
and this audit's own instructions require (unreachable from entrypoints + no static/dynamic refs + absent from
build/test/tooling config + no CI/script invocation + no runtime discovery + not a framework-convention file +
git history reveals no current manual purpose). Everything found is at most **high-confidence unused** or lower.

## 1. Confirmed unused

**None.** No file in the 908-file inventory met the full evidentiary bar. This is a meaningful negative result,
not a shortcut — see the specific searches below for why each near-candidate was excluded from this tier.

## 2. High-confidence unused (backend runtime core)

All four grep-verified: only a dedicated test file imports the module anywhere in `backend/`; no router, no
other service, no script references it.

| Path | Evidence | Deletion risk | Tests required before deletion | Confidence | Recommended treatment |
|---|---|---|---|---|---|
| `backend/services/engineering/matching_engine.py` | Only `tests/test_engineering_pipeline.py` imports it anywhere in `backend/`. No production caller found. | Low-medium — isolated module, but confirm it isn't a planned extension point before removing. | Run `test_engineering_pipeline.py`; check whether removing it changes that test's assertions or just its imports. | High | manual decision required |
| `backend/services/engineering/object_confidence.py` | Only its own test imports `build_object_confidences`/`score_object_bundle`. An apparent hit in `validation_engine.py` was checked and is a **false positive** — a parameter named `object_confidences`, not an import of this module. | Low-medium | Run the owning test; confirm no dynamic/reflective call site (none found). | High | manual decision required |
| `backend/services/engineering/suggestion_engine.py` | Referenced by 2 test files only. Own docstring: "Classical ML... Does NOT use an LLM" — reads as a superseded path now that LLM-based suggestion/legend providers exist (`legend_llm_provider.py`). | Medium — verify against `orchestrator.py` before deleting; a classical fallback path being silently dropped would be a real behavior change, not just cleanup. | Run its 2 tests; grep `orchestrator.py` and callers one more time at decision time (this audit's grep was scoped to the 204-file backend-runtime-core set, not a full-repo AST pass). | Medium-high | manual decision required |
| `backend/services/engineering/takeoff_interface.py` | Self-labeled "(Future) — Architecture stubs" in its own docstring. Test-only references. | Low | Confirm no other module type-imports it as a stub interface. | High | manual decision required |

All four are classified `legacy/dead-code candidate` in the inventory CSV with `proposed_action = manual decision
required` (never `delete candidate`) — per this audit's own instruction, a file with *any* test coverage does not
meet "confirmed unused," and per the task's explicit exclusion list, "scripts without imports" and similar are
never auto-removable.

## 3. Possibly unused (documentation, zero inbound references)

Two `backend/database/reports/*.md` files: `aisc_v16_parser_fix_before_after.md`,
`aisc_v16_training_scale_estimate.md` — zero inbound references found anywhere in the tracked tree. These are
documentation, not code; "possibly unused" here means "possibly safe to archive," not "possibly safe to delete."
No deletion risk assessment applies to pure prose with no code dependency. See
`documentation-reorganization-plan.md`.

## 4. Test-only (by design, not a finding)

`backend/services/label_reconstruction/*` and `backend/services/ml_association/*` are **used only by tests and
their own guard tests, by explicit architectural intent** (CLAUDE.md, enforced by
`test_label_reconstruction_not_wired_into_production.py` / `test_ml_association_not_wired_into_production.py`).
These are correctly excluded from every "unused" tier in this document — they are actively used developer
tooling/shadow-research modules, not dead code. Do not resurrect them into production as part of this
refactor.

## 5. Developer/operations-only (not unused — confirmed active or plausibly active)

- **33 of 64 `backend/scripts/*.py`** have no doc/test/CI reference but are not stale: every one was last
  touched 2026-08-10 through 2026-09-16 (the active ML-audit sprint), and two
  (`phase_d1_orientation_forensics.py`, `phase_d2_merge_forensics.py`) directly correspond to the currently
  untracked `docs/validation/phase_d1_*`/`phase_d2_*` output files visible in `git status` — i.e. they were
  just run by a human operator. Classified `operational/manual script`, not a dead-code candidate.
- `backend/reports/broadened_xgb_ranker_benchmark.md` — 4 inbound cross-references from other tracked files;
  still an active point of reference for the label-reconstruction ranker work.
- `backend/testing_projects_manifest.json` (2779 LOC) — self-described "Read-only Phase 0B inventory" of the
  7 held-out benchmark projects; 1 inbound reference found. Likely consumed by an evaluation script; not
  independently verified per-line in this pass (flagged `medium` confidence in the CSV, not "unused").

## 6. Historical/reference-only (safe-to-archive documentation, not dead code)

See `documentation-reorganization-plan.md` for the full breakdown (~150 of 173 tracked `docs/**` files are
point-in-time reports rather than living docs). Key items:

- `backend/A1_CONTEXT_SCOPE_AUDIT.md`, `A6_COMPLETION_EVIDENCE_DESIGN.md`, `ACCURACY_TRACK_A1_A8_STATUS.md`,
  `GHX_REAL_DRAWINGS_EXPERIMENT.md`, `JUNE_STEEL_PAGE_INDEX.md`, `JUNE_PHASE3_VALIDATION_MANIFEST.json` — all
  dated 2026-09-13, completed point-in-time reports sitting at `backend/` root instead of under `docs/`.
- `backend/SEMANTIC_CONTRACT.md` was **deliberately not** flagged the same way — it documents a currently-live,
  versioned contract module (`services/prediction/semantic_contract.py`, `SEMANTIC_CONTRACT_VERSION=1.0`), not
  a dated snapshot.

## 7. Generated artifacts (superseded training snapshots — data, not code)

Cross-checked via `config.py` Settings-path tracing and every `registry.json` in `backend/training/models/`:

- Five model families (`exact_section`, `family_classifier`, `fusion`, `geometry`, `graph`) each have **4**
  dated snapshot directories, but every family's `registry.json` lists only **3** version_ids. The
  `*_20260826_*` directory is a **consistent orphan across all 5 families** — present on disk, never listed in
  any registry, never referenced by `config.py`, `backend/services`, or `backend/scripts`. High-confidence
  archive candidate (data, not code — no import/test risk).
- `fusion`, `geometry`, `graph` registries have **no `active_version` field at all**; the actually-loaded
  artifacts for those three families are separate flat files (`training/models/{family}/latest_features.json`
  etc.) parallel to the snapshot directories — meaning the snapshot dirs for those 3 families may be
  entirely decorative for current serving. **This needs verification of the loader-selection behavior for a
  null `active_version` before any deletion** — flagged medium-confidence, not archived outright in this pass.
- `label_reconstruction` is the one well-behaved family: `active_version: label_reconstruction_20260913_230531`,
  all 4 snapshots (827/828/913×2) are listed, no orphan.
- ~150MB of near-duplicate binaries (per `docs/ml_integration/partner_vs_local_comparison.md`, independently
  re-verified via `config.py` in this audit): `exact_section_model.joblib` exists identically in the flat
  live-alias (`backend/training/exact_section_model.joblib`, loaded via `settings.exact_section_model_path`)
  plus 4 versioned snapshot copies; `best_model.pkl`/`label_encoder.pkl`/`vectorizer.pkl`/
  `preprocessing_pipeline.pkl` similarly duplicated between the flat live alias and the `family_classifier`
  snapshots.
- `backend/training/experiments/{v16_ranker_optuna_20260816, v16_ranker_groupcv_20260816}/` — two distinct
  archived Aug-2026 experiment runs (not duplicates of each other; groupcv is optuna's leakage-safe successor
  and re-uses its `feature_names.json`). Both are still read by `backend/scripts/phase*.py` today — not dead,
  but frozen historical runs, archive-candidate once `phase14_final_consolidated_results.json` is captured
  elsewhere.

## 8. Duplicate implementation candidates

See `refactor-opportunities.md` for the full list with LOC estimates. Summary pointers only, to avoid
duplicating content between documents:
- Backend: `fusion_engine.py` vs `modular_fusion.py`; 3 explicit `DEPRECATED` shim modules still actively
  imported; two disagreeing training/promotion systems (documented pre-existing architecture conflict, not
  cosmetic duplication); `train_label_ranker.py` (v1/v2) → `_v3` → `_v4_broadened` generation chain;
  `generate_label_corruption_dataset.py` vs `_v16`.
- Frontend: `StatsCards.jsx` / `ui/KpiCard.jsx`; 3 independent badge/chip components
  (`OperationBadge.jsx`, `ui/MatchStatusBadge.jsx`, `ui/EntityTypeChip.jsx`).
- Test suite: `test_geometry_fragment_merge.py` / `test_merge_collinear_fragments_transitive_growth.py` (both
  exercise `geometry_normalizer.merge_collinear_fragments`, different scenarios, real consolidation candidate);
  a de facto shared fixture (`IsolatedApiTestCase` in `test_documents_api.py`) imported by 5 other test files
  with no `conftest.py` anywhere in `backend/tests/` to hold it properly.

## 9. Unknown due to dynamic behavior

14 rows across the inventory are marked `classification=unknown/manual-review required` or
`proposed_action=manual decision required` for reasons other than the dead-code candidates above — mostly
generic-stem modules (`models`, `parser`, `pipeline`, `contracts`, `schemas`, `validation`, `service`,
`normalization`) where a textual stem co-occurrence scan (not a real AST import graph) risks over- or
under-counting references, and 7 backend test files using `importlib.util.spec_from_file_location` dynamic
loading instead of static imports (their true target was read from the loader block, not inferred from a
static `import` line, and is marked `medium` confidence accordingly). A real static import-graph tool (e.g.
`pyflakes`, `modulegraph`, or an AST-based checker) is recommended before acting on any "manual decision
required" row — see `refactor-roadmap.md` Phase 4.
