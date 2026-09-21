# Documentation Index

This index organizes `docs/` by purpose. See the root [`README.md`](../README.md) for setup/run instructions
and [`CLAUDE.md`](../CLAUDE.md) for the authoritative architecture invariants Claude Code (and human
contributors) should treat as load-bearing.

## Current canonical documentation

Read on demand; do not duplicate their content elsewhere. Kept at `docs/` root by convention.

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system architecture and diagrams
- [`FOLDERS.md`](FOLDERS.md) — repository folder map
- [`SERVICES.md`](SERVICES.md) — backend service catalog
- [`TRAINING.md`](TRAINING.md) — training and continuous-learning pipeline
- [`API.md`](API.md) — API reference
- [`FRONTEND.md`](FRONTEND.md) — frontend architecture
- [`ENGINEERING_VALIDATION.md`](ENGINEERING_VALIDATION.md) — engineering validation semantics
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — production deployment

## Architectural decisions / contracts

- [`architecture/unified_semantic_contract.md`](architecture/unified_semantic_contract.md) — the canonical v2.0
  semantic-annotation contract (`backend/services/semantic/`), implemented and live.
- [`architecture/SEMANTIC_CONTRACT.md`](architecture/SEMANTIC_CONTRACT.md) — the original v1.0 schema-only
  design record (superseded — kept for historical context; see the notice at the top of that file).

## Operational guides / demos

- [`demos/ESTIMA3D_MANAGER_DEMO_FLOW.md`](demos/ESTIMA3D_MANAGER_DEMO_FLOW.md)
- [`demos/ESTIMA3D_MANAGER_PRESENTATION_SCRIPTS.md`](demos/ESTIMA3D_MANAGER_PRESENTATION_SCRIPTS.md)

## Research / reference material

- [`final_rnd_audit/`](final_rnd_audit/) — independent R&D audit of partner-contributed neural components
- [`geometry_graph_audit/`](geometry_graph_audit/) — geometry/graph pipeline research audit
- [`ml_association_phase/`](ml_association_phase/) — `ml_association` shadow-module research (not wired into
  production; see CLAUDE.md)
- [`ml_integration/`](ml_integration/) — partner-vs-local architecture comparison and governance notes

## Audit and validation reports

- [`audits/`](audits/) — includes [`audits/codebase-refactor/`](audits/codebase-refactor/), the repository-wide
  file inventory and refactor-planning audit (start at
  [`audits/codebase-refactor/README.md`](audits/codebase-refactor/README.md))
- [`accuracy_work/`](accuracy_work/) — accuracy-sprint measurement reports
- [`reports/`](reports/) — point-in-time status/experiment reports relocated from `backend/` root:
  - `reports/accuracy-track/` — the A1–A8 semantic-compile accuracy track (Sept 2026)
  - `reports/ghx/` — GHX real-drawings geometry experiment
  - `reports/june-validation/` — June validation-batch page index
- [`validation/`](validation/) — gold-set data and phase 1–3 association-measurement reports. **Note**: this
  directory also holds a set of untracked, in-progress validation files (`phase_c_*`, `phase_d1_*`,
  `phase_d2_*`) that are intentionally not part of the tracked documentation set and are not indexed here.

## Historical / archive material

- [`history/MIGRATION_NOTES_v5.2.md`](history/MIGRATION_NOTES_v5.2.md) — v5.2.0 "AI-First Platform" migration
  notes from the original architecture, referenced by `final_rnd_audit/estima3d_workflow_evolution_report.md`
  as the starting point for the platform's evolution.

## Known gaps (not resolved by this index; tracked for follow-up)

- `backend/JUNE_PHASE3_VALIDATION_MANIFEST.json` and `backend/reports/broadened_xgb_ranker_benchmark.md` were
  **not** relocated here — both are actively read/cross-referenced by backend scripts and tracked ML training
  artifacts (not just documentation), so moving them requires a code-aware change out of scope for a
  documentation-only reorganization. See
  [`audits/codebase-refactor/README.md`](audits/codebase-refactor/README.md) §U for the full list of
  deferred/pending decisions from the refactor audit.
