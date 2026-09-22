# Codebase Refactor Audit — Summary

## A. Audited Git baseline

Repository: `C:\Users\Bassam\git\ai-dynamic-regex-integration` (`origin` =
`https://github.com/ismail210/ai-dynamic-regex.git`). Branch `main`, commit
`5261ee1f1c4ccc428e28ce6c739dc145fd080b8a` — confirmed identical to `origin/main` throughout this audit (no
commits landed during the audit; local `main` never moved).

## B. Total tracked files audited

**908** (`git ls-files | wc -l` at the audited commit).

## C. Inventory coverage proof

`docs/audits/codebase-refactor/file-inventory.csv` contains exactly **908 data rows + 1 header**. Verified
programmatically: `set(csv_paths) == set(git ls-files)`, zero missing, zero extra, zero duplicate paths, every
row has exactly 18 columns. This was re-run after merging all 6 scope fragments and again after repairing 18
CSV-quoting errors in the frontend fragment (unescaped commas inside free-text notes, structurally repaired
with 100% content preserved — see the fragment's own generation notes; no data was dropped).

## D. Files by classification

| Classification | Count |
|---|---|
| runtime-backend | 168 |
| training/ML | 165 |
| test | 144 |
| fixture/sample | 134 |
| data/model artifact | 59 |
| report/audit | 51 |
| runtime-frontend | 46 |
| documentation | 40 |
| developer tooling | 28 |
| API/route | 22 |
| shared-contract/schema | 15 |
| configuration | 14 |
| build/deployment | 12 |
| legacy/dead-code candidate | 7 |
| research/reference | 1 |
| generated/cache candidate | 1 |
| UI/static asset | 1 |

(Note: 22 frontend page components were classified `API/route` by the frontend audit pass rather than
`runtime-frontend` — a labeling quirk, not a data error; they are ordinary React pages, not API route
handlers. Left as-is in the CSV rather than silently rewritten, per this audit's own "never guess to complete
the table" instruction — flagged here for transparency instead.)

## E. Files by usage status

| Usage status | Count |
|---|---|
| actively used at runtime | 276 |
| historical/archive only | 255 |
| used by tests | 161 |
| operational/manual script | 70 |
| used by developer tooling | 68 |
| documentation/reference only | 47 |
| generated but intentionally tracked | 19 |
| used at build time | 12 |

## F. Confirmed unused files

**None.** No file in the 908-file inventory met the full evidentiary bar this audit required (unreachable from
entrypoints + no static/dynamic refs + absent from build/test/tooling config + no CI/script invocation + no
runtime discovery mechanism + not a framework-convention file + git history reveals no current manual
purpose). This is a real, checked negative result — see `unused-candidates.md` §1.

## G. High-confidence unused candidates — RESOLVED

4 backend modules, all with only test-file references and no production caller (grep-verified across the
whole `backend/` tree, with one automation false-positive caught and corrected before being reported):
`services/engineering/matching_engine.py`, `services/engineering/object_confidence.py`,
`services/engineering/suggestion_engine.py`, `services/engineering/takeoff_interface.py`. At the time this
audit was written, all four were marked `proposed_action = manual decision required` (none marked
delete-candidate), since a file with any test coverage didn't meet this audit's own "confirmed unused" bar.
A dedicated follow-up phase re-derived the standard and deleted all four — see `unused-candidates.md` §2 and
`dead-module-reachability-review.md` for the full evidence and final disposition.

## H. Files requiring manual review

**14 rows** (`classification = unknown/manual-review required` or `proposed_action = manual decision
required`), plus the 7 legacy/dead-code candidates above (4 backend modules + 3 DEPRECATED shim modules that
are still actively imported). Mostly generic-stem modules where a textual reference scan risks over/under
counting, and dynamically-loaded test targets. See `unused-candidates.md` §9 for the full list and the
recommendation to run a real AST-based import-graph tool before acting on any of them.

## I. Duplicate implementations

- Backend: `multimodal/fusion_engine.py` (thin adapter) vs `multimodal/modular_fusion.py`; 3 explicit
  `DEPRECATED` shims still actively imported (`prediction/semantic_contract.py`,
  `semantic_preprocessor/{models,serialization}.py`) superseded by `services/semantic/{models,serialization}.py`;
  two training/promotion systems **documented as disagreeing with each other** in
  `docs/ml_integration/partner_vs_local_comparison.md` (pre-existing architecture conflict, not addressed by
  this cleanup); training-script generation chains (`train_label_ranker` v1→v2→v3→v4_broadened;
  `generate_label_corruption_dataset` vs `_v16`).
- Frontend: `StatsCards.jsx` / `ui/KpiCard.jsx` (real consolidation opportunity, ~55 LOC); 3 independent
  badge/chip components with the same shape, different domains (`OperationBadge.jsx`, `ui/MatchStatusBadge.jsx`,
  `ui/EntityTypeChip.jsx`, ~75 LOC opportunity).
- Tests: `test_geometry_fragment_merge.py` / `test_merge_collinear_fragments_transitive_growth.py` (real
  overlap, not true duplicates); a shared fixture class (`IsolatedApiTestCase`) living inside an ordinary test
  file and imported by 5 others, with **no `conftest.py` anywhere in `backend/tests/`**.

Full detail with LOC estimates: `refactor-opportunities.md`.

## J. Largest modules by LOC

Backend (production code): `services/prediction/orchestrator.py` 2068 (sole inference entrypoint — CLAUDE.md
protected, split target is internal-only), `multimodal/validation_engine.py` 1180,
`engineering/drawing_intelligence.py` 1007, `training_pipeline/neural_dataset.py` 938,
`semantic_preprocessor/geometry_route_association.py` 913 (shadow), `engineering/legend_profile.py` 836,
`label_reconstruction/candidates.py` 804 (shadow), `engineering/geometry_extractor.py` 796,
`semantic/models.py` 773 (schema), `training_service.py` 750.

Frontend: `pages/UnknownReviewPage.jsx` 1046 (off-nav, largest single frontend file), `pages/ValidationPage.jsx`
958 (**no dedicated test file**), `pages/SemanticReviewPage.jsx` 866, `lib/predictionContract.js` 771
(intentional single boundary), `components/pdf/PdfDocumentViewer.jsx` 682.

## K. Highest-risk modules

Of 251 rows classified `runtime-backend`/`runtime-frontend`/`shared-contract/schema`/`API/route`: 14 rated
`critical`/`very high` risk-if-changed, 57 `high`, 171 `medium`, 9 `low`. The `critical`/`very high` tier is
dominated by exactly the modules CLAUDE.md itself calls out as protected invariants:
`prediction/orchestrator.py` (sole inference entrypoint), `lib/predictionContract.js` (architecture invariant),
`label_reconstruction/candidates.py` and `multimodal/pipeline.py` (very broad internal fan-in, effectively
shared utilities despite not being formally declared contracts), plus the 3 god-page frontend files
(`UnknownReviewPage.jsx`, `ValidationPage.jsx`, `SemanticReviewPage.jsx`, `PdfDocumentViewer.jsx` — rated `very
high` risk by the frontend audit due to size + broad reuse, not fragility).

## L. Estimated safely removable LOC

Code: effectively 0 confirmed-safe LOC in this pass — nothing cleared the "confirmed unused" bar (see F). The
4 high-confidence-unused backend modules' combined LOC was not pre-summed, since none are approved for
deletion without the Phase 4 (roadmap) verification step first.

Data/generated artifacts (not code, tracked as a separate cleanup class): the `*_20260826_*` orphan snapshot
directories across 5 model families, plus ~150MB of near-duplicate binaries between flat live-aliases and
versioned model snapshots — see `unused-candidates.md` §7 and `refactor-roadmap.md` Phase 2. Not LOC-counted
(binary/large-data), but the single largest safe-cleanup opportunity by disk size in the repository.

## M. Estimated consolidatable LOC

~130 LOC on the frontend (StatsCards→KpiCard ~55, badge/chip trio ~75) with `low` risk. Backend consolidation
opportunities (3 DEPRECATED shims, fusion_engine.py) are migration-first and not LOC-estimated until caller
enumeration is done — see `refactor-opportunities.md`.

## N. Documentation/report findings

173 tracked `docs/**` files + 7 `validation/semantic_test_pdfs/` files audited. **8 authoritative docs** named
in CLAUDE.md, all untouched since the initial commit; one (`ENGINEERING_VALIDATION.md`) is orphaned from
README's own nav. A **9th de-facto canonical doc** was found (`docs/architecture/unified_semantic_contract.md`)
that should be added to both lists. ~150 of 173 files are point-in-time reports, not living docs — none
cross-referenced by the canonical 8. The most significant finding: `docs/geometry_graph_audit/
06_research_findings.md` (a prior, independent audit) already states `ARCHITECTURE.md` should be "treated as
aspirational, not authoritative" because it found dead code the architecture doc doesn't mention — corroborates
this audit's own dead-code findings from an independent source. `validation/semantic_test_pdfs/` confirmed as
an active test fixture masquerading as a docs-adjacent folder — proposed move to
`backend/tests/fixtures/semantic_test_pdfs/`. Full detail: `documentation-reorganization-plan.md`.

## O. Proposed repository structure

No runtime code moves. 12 documentation/fixture files proposed to move (6 backend-root status docs into new
`docs/reports/*` subfolders, 2 demo docs into `docs/demos/`, 1 migration note into `docs/history/`, 1 contract
doc into `docs/architecture/`, and the 7-file `validation/semantic_test_pdfs/` fixture into
`backend/tests/fixtures/`). Everything else — all of `backend/services/`, `backend/tests/`, `backend/scripts/`,
`backend/training/`, `backend/database/`, all of `frontend/`, `.claude/`, `.serena/`, and the
already-well-organized `docs/` subfolders — stays exactly where it is. Full detail:
`proposed-repository-structure.md`.

## P. Recommended refactor sequence

10 phases, ordered by risk (documentation → generated-artifact cleanup → dead-file removal → import cleanup →
utility consolidation → backend boundary cleanup → frontend consolidation → test cleanup → config consolidation
→ final verification). Phases 1, 2, 9 have zero behavior risk and can start immediately once approved; Phases
5-6 touch CLAUDE.md-protected contract/pipeline code and are sequenced last among the code-change phases with
the smallest possible commits. Full detail with per-phase scope/LOC/tests/rollback/risk: `refactor-roadmap.md`.

## Q. Tests protecting each major subsystem

- Prediction/orchestrator: the targeted 252-test production-critical suite (extraction, normalization, label
  reconstruction, exact-match locking, HSS completion, association, validation/takeoff).
- Shadow-module isolation: `test_label_reconstruction_not_wired_into_production.py`,
  `test_ml_association_not_wired_into_production.py` (import-scan guard tests, actively enforced).
- Frontend contract rendering: `predictionContract.test.js` (558 LOC), `semanticContract.test.js`,
  component-level tests for the badge/chip trio and StatsCards/KpiCard (existence not fully confirmed in this
  pass — verify before Phase 7 of the roadmap).
- 123 backend test files total, 217 frontend test files total — see `file-inventory.csv` `related_tests`
  column for the per-module mapping used throughout this audit.

## R. Current test/build baseline

Re-run on this exact commit during this audit session (not assumed from a prior session):
- Backend targeted (production-critical, 22 files): **252 passed, 1 skipped, 0 failed.**
- Frontend: **217 passed, 0 failed** (21 test files).
- Frontend production build: **passed** (`npm run build`, ~12s).
- Full backend suite (1282+ tests) and its 9 known pre-existing failures (stale fixtures in
  `test_a2_a7_human_review.py`, `test_repeated_detail_linker.py`, `test_ground_truth_evaluator_repair.py` —
  root-caused to a `ground_truth_evaluation.py` refactor during partner-merge integration, predating this
  audit) were established earlier in this session on the same commit and were **not** re-run in full during
  this specific audit pass (no code changed that would affect them) — cited from the session's own prior,
  verified run rather than re-executed, to avoid an unnecessary ~2.5-minute repeat run.
- Pyright (backend, globally-installed tool, no new dependency added): attempted, **did not complete within a
  reasonable time** on this codebase's size — informational-only, not a gate; flagged as a tooling follow-up in
  `refactor-roadmap.md` Phase 10 rather than blocking this audit.

## S. Files and directories deliberately excluded

`backend/training/documents/` and `backend/training/label_reconstruction_tmp/` (untracked contents — existence
noted, contents never opened); `docs/validation/`'s untracked `phase_c_*`/`phase_d1_*`/`phase_d2_*` files
(existence noted, contents never opened; the ~123 pre-existing **tracked** files in the same directory tree
were audited normally); the 3 dirty auxiliary worktrees (`ai-dynamic-regex`, `ai-dynamic-regex-accuracy-sprint`,
`ai-dynamic-regex-dlp`) — not entered, not audited, per explicit instruction.

## T. Preservation confirmation

- The 3 preserved untracked directories: present and untouched throughout (verified via `git status` before
  and after the audit — unchanged aside from pre-existing runtime drift from an earlier, unrelated dev-server
  session, fully explained in this session's own history and not caused by this audit).
- Stashes: both pre-existing stashes (`stash@{0}`, `stash@{1}`) untouched.
- Tags: all 7 existing tags (2 pre-consolidation, 5 archival) untouched.
- Worktrees: all 4 untouched, not entered.
- `.claude/` tooling, hooks, and rules: untouched.
- No production code file was edited, moved, renamed, or deleted. The only new files on disk are the 8 files
  in `docs/audits/codebase-refactor/` produced by this audit (this summary plus the 6 phase documents and the
  inventory CSV). *(Correction, added in the follow-up documentation-organization task: the audit produced 8
  files, not 7 as an earlier chat summary miscounted; a 9th file, `runtime-generated-drift.md`, was added in
  that follow-up task and is not part of the original audit's own file count.)*

## U. Questions requiring your decision

1. **Documentation moves** (Phase 1 of the roadmap): approve the 12-file move list in
   `proposed-repository-structure.md`?
2. **`SEMANTIC_CONTRACT.md` vs `unified_semantic_contract.md`**: these may already overlap in content — should
   they be merged (not just co-located) once moved, or kept as two distinct docs (one narrower, one broader)?
3. **Generated-artifact cleanup** (Phase 2): the `*_20260826_*` orphan snapshots across `exact_section` and
   `family_classifier` look safely archivable, but `fusion`/`geometry`/`graph` have no `active_version` field
   at all in their registries — do you want the loader-selection behavior verified (a small, scoped
   investigation) before any of those 3 families' snapshots are touched?
4. **4 high-confidence-unused backend modules** — **RESOLVED**: proceeded with the Phase 3 verification-then-
   delete sequence; all four (`matching_engine.py`, `object_confidence.py`, `suggestion_engine.py`,
   `takeoff_interface.py`) confirmed `CONFIRMED_UNUSED` and deleted. See `dead-module-reachability-review.md`.
5. **3 DEPRECATED shim modules**: approve the caller-migration plan (Phase 5), given it touches
   CLAUDE.md-protected contract-adjacent code?
6. **Two disagreeing training/promotion systems**: this audit deliberately did not propose reconciling them
   (pre-existing, documented architecture question, not a cleanup item) — do you want that raised as its own,
   separately-scoped follow-up task?
7. **Pyright**: install a project-local pinned version (not just rely on the global one) and/or run it
   incrementally/scoped rather than a full cold pass, given it didn't complete in this environment?
8. **`skills-lock.json` gap**: add entries for the `scikit-learn` and `task-observer` skills (Phase 9), or is
   that lockfile intentionally scoped to only the two `vercel-labs` skills?

## Implementation status (updated as roadmap phases land)

- **Phase 1 (documentation organization)** — DONE. 10 files moved into `docs/{reports,demos,history,architecture}/`,
  `docs/README.md` index created, `runtime-generated-drift.md` added. Commits `85b38ff`, `0c3d292` (fixture
  relocation).
- **Phase 7 (frontend consolidation)** — DONE, partially. `StatsCards`→`KpiCard`: implemented, **-8 LOC**.
  Badge/chip trio: implemented, measured at **+30 LOC**, reverted — see `refactor-opportunities.md` §2 for the
  full reasoning. Net actual: **-8 LOC**, not the originally estimated -130. Commit
  `refactor(frontend): reuse KPI card presentation`.
- **Phase 8 (test-fixture/helper cleanup)** — DONE. `IsolatedApiTestCase`/`_REDIRECTED_SETTINGS` centralized
  to `backend/tests/helpers/isolated_api.py` (5 real consumers migrated, +11 LOC, organizational only — see
  `refactor-opportunities.md` §5). Geometry-merge duplicate builder centralized to
  `backend/tests/helpers/geometry_fixtures.py` (-5 LOC net, all 8 tests kept — see §6). Targeted (252/1/0) and
  full (1282/9-known/3) suites verified unaffected; all 3 preserved training-drift files' SHA256 fingerprints
  confirmed unchanged before/after. Commits `test(api): centralize isolated API test setup`,
  `test(geometry): deduplicate fragment merge setup`.
- **Phase 2 (generated-artifact cleanup)** — DONE, forensic pass, **zero deletions**. Full retention audit at
  `model-artifact-retention-audit.md`: all 93 tracked model-related files inventoried and SHA256-verified.
  The original "~150MB duplicate" and "orphan snapshot" premises were both found to be wrong on inspection —
  real verified duplicate bytes = 11.3 MiB, and every `*_20260826_*` "orphan" contains genuinely unique,
  never-promoted candidate model data (historical evidence, not litter). The `fusion`/`geometry`/`graph`
  null-`active_version` question is fully resolved: nothing downstream ever reads these 3 families'
  registries at all (not a fallback — a permanent, by-design dead end). No `.gitignore` change made (no safe
  filename-based pattern exists). One pre-existing discrepancy flagged for your decision, not fixed: the live
  `exact_section_model.joblib` alias doesn't byte-match any of the 4 registered snapshot versions, including
  the current `active_version`.
- **Phase 5 (deprecated shim migration)** — DONE. Full forensic pass at
  `semantic-shim-and-fusion-review.md`. 2 of 3 shims (`prediction/semantic_contract.py`,
  `semantic_preprocessor/models.py`) turned out to house genuinely original content and can never be deleted
  — only their dead re-export tails (zero remaining callers, verified) were trimmed. The 3rd
  (`semantic_preprocessor/serialization.py`) was a pure re-export with no other content — migrated its 2
  callers and deleted it. Symbol identity locked with a new characterization test
  (`test_deprecated_import_compatibility.py`, 6 tests). All 32 tracked binary artifacts scanned for embedded
  shim-path strings — zero hits. Production/script LOC -44, test LOC +63. Targeted (252/1/0) and full
  (1282+6/9-known/3) suites unchanged.
- **Phase 6 (fusion-engine review)** — DONE, no code change. `fusion_engine.py` and `modular_fusion.py` proven
  to have zero functional overlap (adapter vs. algorithm, connected through `orchestrator.py`, not competing)
  — both required, neither touched.
- **Phase 3 (confirmed dead-file removal)** — DONE. Full forensic pass at
  `dead-module-reachability-review.md`. All 4 `services/engineering/` scaffolding modules
  (`matching_engine.py`, `object_confidence.py`, `suggestion_engine.py`, `takeoff_interface.py`) re-verified
  against a 15-point `CONFIRMED_UNUSED` standard (AST import graph, dynamic/CI/Docker reference search,
  43-binary + JSON artifact byte-scan, git-history intent review) — all passed, all deleted (-870 production
  LOC). Two independent prior audits (`docs/geometry_graph_audit/`, `docs/ml_association_phase/`) had already
  reached the same "dead in production" conclusion by their own grep passes. No caller migration needed (zero
  real callers). Sole test-only references trimmed/removed (-91 test LOC across 3 files); the one genuine
  product invariant a test exercised (AISC database never overrides the AI-selected section) has independent
  canonical coverage and was not lost. `services/engineering/models.py`'s `MatchStatus`/`ObjectConfidence`/
  `Suggestion` removed as directly related dead symbols (each exclusively used by one deleted module).
  Targeted suite (19/19) and full suite (1287/9-known/3, delta of exactly 1 intentionally-removed sole-purpose
  test from the prior 1288 baseline) verified; all 3 preserved training-drift files' SHA256 fingerprints
  confirmed unchanged before/after. One pre-existing, unrelated collection error flagged, not fixed:
  `tests/test_ground_truth_evaluator_repair.py` fails to import `length_to_feet` even at unmodified `HEAD`.
  Commits: `test(backend): trim engineering-scaffolding test coverage`,
  `refactor(backend): remove unused engineering scaffolding modules`,
  `docs(refactor): record dead-module reachability results`.
- **Phase 4 (generic-stem module reachability + collection-error repair)** — DONE. Full forensic pass at
  `generic-module-reachability-review.md`. All 14 "medium-confidence generic-stem" modules
  (`unused-candidates.md` §9) re-verified with one reusable AST-based whole-backend import graph — every one
  has a proven current importer (11 `ACTIVE_RUNTIME`, including direct imports from `orchestrator.py`,
  `fusion_engine.py`, `staged_pipeline.py`, `routers/learning.py`; 3 `ACTIVE_OPERATIONAL` —
  `services/ml_association/{schemas,service,validation}.py`, deliberately unwired shadow work per
  `CLAUDE.md`'s own architecture invariant, protected by `test_ml_association_not_wired_into_production.py`
  and a feature flag disabled by default). **Zero deletions, zero caller migrations, zero production LOC
  change** — a real negative result, not a shortcut (the CSV's own preliminary `keep in place`/`keep but
  document` calls for 13 of the 14 were directionally correct; this phase converted that into a verified
  conclusion). Also resolved the pre-existing `test_ground_truth_evaluator_repair.py` collection error
  flagged in Phase 3: git history proved the `length_to_feet` import targeted an implementation deliberately
  removed by merge `88222e6` (ground-truth evaluation consolidated into `canonical_takeoff_eval.py`), with
  superseding coverage already in `test_canonical_takeoff_eval.py` (12/12 passing against the real
  Burrville/GCDC workbooks present in this environment) — the obsolete file was removed, restoring full test
  collection (1299 tests, no `--ignore` needed). Two stuck background `pyright --outputjson` processes from
  the prior phase (running ~4 days, 3.5 GB RAM) were identified by exact PID/command-line match and
  terminated; the unrelated, legitimately-running `pyright-langserver` IDE processes were left untouched.
  Commits: `test(validation): restore ground-truth evaluator test collection`,
  `docs(refactor): record generic module reachability results`.
- **Phase 11 (pre-orchestrator utility/config consolidation)** — DONE. Full pass at
  `pre-orchestrator-consolidation-review.md`. All prior recorded consolidation opportunities were already
  closed; a fresh scoped search found and implemented 3 genuine production duplications (a boolean
  env-var-parsing helper, two trivial normalization wrappers, and a runtime/training-boundary label
  normalizer — each with a clear canonical owner and, where none existed before, new characterization tests)
  plus a dynamic-test-loader cleanup (corrected the audit's "7 loaders" claim to a verified 5; migrated 1 to
  a normal import, consolidated the other 4 onto one new shared `tests/helpers/script_loader.py` helper).
  **Production LOC -18, test LOC +42** (real new regression coverage, not organizational). Zero behavior,
  API, schema, route, or environment-variable changes. Targeted (224/1/0/40-subtests) and full suite verified
  unchanged in known-failure set; drift fingerprints confirmed unchanged throughout.
- **Phases 9-10** — Phase 9 (unrelated `.env.example`/`skills-lock.json` metadata task) and Phase 10 (final
  deployment-verification gate) not started.

---

Full artifacts: `file-inventory.csv`, `dependency-and-entrypoint-map.md`, `unused-candidates.md`,
`refactor-opportunities.md`, `documentation-reorganization-plan.md`, `proposed-repository-structure.md`,
`refactor-roadmap.md`, `runtime-generated-drift.md` — all under `docs/audits/codebase-refactor/`.
