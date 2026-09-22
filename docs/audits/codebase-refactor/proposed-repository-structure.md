# Proposed Clean Target Structure

Baseline: `main` @ `5261ee1f1c4ccc428e28ce6c739dc145fd080b8a`. This is a proposal only — no file has been moved,
renamed, or deleted. Every move below is justified by an ownership/discoverability/boundary problem actually
found during the audit, not cosmetic symmetry. Runtime code is **not** relocated anywhere in this plan.

## Current top-level structure

```
ai-dynamic-regex-integration/
  backend/            572 tracked files (services 183, training 245, tests 123, scripts 64, database 12,
                       routers 7, validation_reports 6, root-loose 17)
  frontend/           103 tracked files (src 93, config/build 10)
  docs/               173 tracked files (validation 123 tracked + reports/audits/architecture ~50)
  .claude/            44 tracked files (skills 33, rules 4, hooks 4, agents 2, settings.json)
  validation/         7 tracked files (semantic_test_pdfs/ — a test fixture at repo root)
  .serena/            2 tracked files
  (root)              7 files: README.md, CLAUDE.md, .gitignore, .env.example, docker-compose.yml,
                       skills-lock.json, ai-dynamic-regex.code-workspace
```

## Proposed top-level structure

```
ai-dynamic-regex-integration/
  backend/
    app.py, config.py                    <- unchanged (process entrypoint + settings)
    routers/                             <- unchanged (7 routers)
    services/                            <- unchanged (183 files; internal boundaries already sound)
    database/                            <- unchanged (AISC v16 reference data)
    tests/                               <- unchanged, +conftest.py (new, see refactor-opportunities #5)
    scripts/                             <- unchanged (operational tooling)
    training/                            <- unchanged tree; only generated-artifact cleanup inside it (see roadmap)
    Dockerfile, .dockerignore, requirements*.txt, pyrightconfig.json, testing_projects_manifest.json
                                          <- stay at backend/ root (conventional tool-config / deployment locations)
    tests/fixtures/semantic_test_pdfs/   <- MOVED from root-level validation/ (coordinated, updates 4 files)
  frontend/                              <- unchanged structure throughout
  docs/
    API.md, ARCHITECTURE.md, FOLDERS.md, SERVICES.md, TRAINING.md,
    FRONTEND.md, ENGINEERING_VALIDATION.md, DEPLOYMENT.md   <- unchanged (canonical, root of docs/)
    architecture/                        <- unchanged location; +SEMANTIC_CONTRACT.md (moved from backend/ root)
    demos/                               <- NEW: ESTIMA3D_MANAGER_DEMO_FLOW.md, _PRESENTATION_SCRIPTS.md
    history/                             <- NEW: MIGRATION_NOTES_v5.2.md
    reports/                             <- NEW top-level grouping for backend-root loose status docs only:
      accuracy-track/, june-validation/, ghx/, backend/
    accuracy_work/, audits/, final_rnd_audit/, geometry_graph_audit/,
    ml_association_phase/, ml_integration/, validation/     <- unchanged locations (already well-organized)
  .claude/                               <- unchanged
  .serena/                               <- unchanged
  (root)                                 <- unchanged: README.md, CLAUDE.md, .gitignore, .env.example,
                                             docker-compose.yml, skills-lock.json,
                                             ai-dynamic-regex.code-workspace
```

## Responsibility of each proposed/changed directory

- **`backend/tests/fixtures/semantic_test_pdfs/`**: conventional location for a test fixture that is currently
  sitting at repo root as if it were documentation. Owner: backend test suite.
- **`docs/architecture/`**: single home for living architectural contract docs (`unified_semantic_contract.md`
  + the relocated `SEMANTIC_CONTRACT.md`), separate from point-in-time reports.
- **`docs/demos/`**: current, actively-used demo material that was previously orphaned from any nav — gives it
  a discoverable, stable home distinct from historical reports.
- **`docs/reports/{accuracy-track,june-validation,ghx,backend}/`**: the only genuinely new grouping — holds
  the 6 backend-root-loose dated status docs that currently have no consistent location at all (they sit
  directly in `backend/` alongside runtime code, indistinguishable from live documentation).

## Exact proposed moves

| From | To | Reason |
|---|---|---|
| `backend/A1_CONTEXT_SCOPE_AUDIT.md` | `docs/reports/accuracy-track/A1_CONTEXT_SCOPE_AUDIT.md` | dated report, not runtime-adjacent doc |
| `backend/A6_COMPLETION_EVIDENCE_DESIGN.md` | `docs/reports/accuracy-track/A6_COMPLETION_EVIDENCE_DESIGN.md` | same series |
| `backend/ACCURACY_TRACK_A1_A8_STATUS.md` | `docs/reports/accuracy-track/ACCURACY_TRACK_A1_A8_STATUS.md` | same series |
| `backend/GHX_REAL_DRAWINGS_EXPERIMENT.md` | `docs/reports/ghx/GHX_REAL_DRAWINGS_EXPERIMENT.md` | R&D write-up |
| `backend/ghx_real_drawings_phase0d_evidence.json` | `docs/reports/ghx/ghx_real_drawings_phase0d_evidence.json` | companion data file |
| `backend/JUNE_STEEL_PAGE_INDEX.md` | `docs/reports/june-validation/JUNE_STEEL_PAGE_INDEX.md` | dated validation series |
| `backend/JUNE_PHASE3_VALIDATION_MANIFEST.json` | `docs/reports/june-validation/JUNE_PHASE3_VALIDATION_MANIFEST.json` | same series |
| `backend/reports/broadened_xgb_ranker_benchmark.md` | `docs/reports/backend/broadened_xgb_ranker_benchmark.md` | consolidate the single-file `backend/reports/` dir; **4 inbound cross-references must be updated** |
| `backend/SEMANTIC_CONTRACT.md` | `docs/architecture/SEMANTIC_CONTRACT.md` | discoverability; **content-diff against `unified_semantic_contract.md` first** |
| `docs/ESTIMA3D_MANAGER_DEMO_FLOW.md` | `docs/demos/ESTIMA3D_MANAGER_DEMO_FLOW.md` | orphaned current material, needs a home |
| `docs/ESTIMA3D_MANAGER_PRESENTATION_SCRIPTS.md` | `docs/demos/ESTIMA3D_MANAGER_PRESENTATION_SCRIPTS.md` | same |
| `docs/MIGRATION_NOTES_v5.2.md` | `docs/history/MIGRATION_NOTES_v5.2.md` | historical, not a live doc |
| `validation/semantic_test_pdfs/` (7 files) | `backend/tests/fixtures/semantic_test_pdfs/` | test fixture belongs under the test tree; **4 referencing files' `REPO_ROOT`-relative paths must be updated in the same change** |

No other file in the 908-file inventory is proposed to move. Everything else — all of `backend/services/`,
`backend/tests/` (besides the fixture above), `backend/scripts/`, `backend/training/`, `backend/database/`,
all of `frontend/`, `.claude/`, `.serena/`, root-level files, and the already-organized `docs/` subfolders
(`accuracy_work/`, `audits/`, `final_rnd_audit/`, `geometry_graph_audit/`, `ml_association_phase/`,
`ml_integration/`, `validation/`) — stays exactly where it is.

## Exact consolidations

See `refactor-opportunities.md` for the full list (StatsCards→KpiCard, badge/chip trio, 3 DEPRECATED shims,
fusion_engine.py review, shared test fixture extraction, geometry-merge test setup dedup). None of these are
directory moves — they are in-place code consolidations.

## Exact delete candidates

**None proposed in this phase.** Per `unused-candidates.md`, nothing met the "confirmed unused" bar. The 4
`legacy/dead-code candidate` backend modules and the orphaned `*_20260826_*` training snapshots are flagged
`manual decision required` / archive-candidate, not delete-candidate — a human decision point, not an automatic
action.

## Exact archive candidates

The 6 backend-root dated status docs above (moved into `docs/reports/*`, which functions as the archive tier
for this repo rather than a separate `archive/` top-level directory — consistent with keeping directory depth
shallow, per this audit's own instruction). The orphaned `*_20260826_*` training snapshot directories across
all 5 model families (data, not documentation — see `unused-candidates.md` §7). The two
`backend/database/reports/*.md` files with zero inbound references.

## Required import/reference updates (if these moves are implemented)

1. `validation/semantic_test_pdfs/` move: update `REPO_ROOT`-relative path construction in
   `backend/tests/test_semantic_damage_manifests.py`, `backend/tests/test_semantic_precedence_task_regression.py`,
   `backend/scripts/build_semantic_damage_test_pdfs.py`, `backend/scripts/validate_demo_correction_flow.py`.
   Frontend's `frontend/src/fixtures/semanticDamage/*.manifest.json` are a separate, already-frontend-local
   copy — unaffected by this move, but should be checked for staleness against the moved backend fixture in
   the same change.
2. `backend/reports/broadened_xgb_ranker_benchmark.md` move: update the 4 files that cross-reference it (grep
   for the filename at implementation time to get the exact list).
3. `backend/SEMANTIC_CONTRACT.md` move: update its 1 known inbound cross-reference.
4. All other moves (dated status docs with 0-1 inbound refs) require no or trivial reference updates.

## Test implications

None of the proposed moves touch test *logic* — only the fixture-path move (#1 above) requires test-file edits,
and those edits are path-string changes only, not behavioral. Re-run the full backend suite and the 2 directly
affected test files after that specific move.

## Deployment implications

None. No proposed move touches `Dockerfile`, `docker-compose.yml`, `requirements*.txt`, `package.json`, or any
file `docker build`/`docker-compose` reads. Deployment-critical files stay exactly where they are.

## Git-history preservation method

Use `git mv` for every move (not delete+recreate) so `git log --follow` continues to work on each file's
history. Land moves in small, single-purpose commits (one subsystem's worth at a time — e.g. all 6 backend-root
docs in one commit, the fixture move in its own commit) so each is independently revertible.

## Migration sequence

See `refactor-roadmap.md` Phase 1 (documentation moves — no code risk, do first) and Phase 6/7 (the coordinated
fixture move, bundled with its required reference updates — do after the documentation-only moves are proven
safe).
