# Project-rule Phase 2 — Starting State

Recorded 2026-09-23.

## Phase 1 secured in local commits (not pushed)

Branch `bassam/project-rule-intelligence`, created from `main` at
`77f0ea03692358e0718f3975156f23bd4808c31c` (so the commits are not on `main`).

| # | SHA | Subject | Paths |
|---|---|---|---|
| 1 | `fd29565` | test(project-rules): add benchmark harness and frozen baseline | `backend/scripts/evaluate_project_rules.py`, `backend/tests/test_project_rule_benchmark.py`, `backend/tests/fixtures/project_rules/synthetic_manifest.json`, `docs/project_rule_phase1/BASELINE_STATE.md`, behaviour-neutral row-helper extraction in `schedule_grid.py` |
| 2 | `92f1a9d` | feat(schedule): add structured schedule evidence in shadow mode | `schedule_grid.py` (`build_schedule_evidence`, legacy mark grammar), `config.py` (`SCHEDULE_EVIDENCE_SHADOW_ENABLED`), harness shadow pipeline, `test_schedule_evidence_shadow.py` |
| 3 | `d660ffb` | feat(schedule): widen shadow-only schedule discovery | widened mark grammar + `SCHEDULE_EVIDENCE_SHADOW_WIDENED`, widened tests, `docs/project_rule_phase1/FINAL_COMPARISON.md`, `synthetic_results/` |

Overlapping files (`schedule_grid.py`, `config.py`, the harness and shadow tests) were split by writing each intermediate state, testing it, and committing it. The final commit's tree is byte-identical to the reviewed Phase 1 working tree.

Checks before committing:

- the changed paths matched the Phase 1 report exactly;
- the 222-test targeted set passed on the final state;
- each intermediate commit's tests passed (commit 1: 33 passed; commit 2: 40 passed);
- `FINAL_COMPARISON.md` now separates code-wired behaviour, synthetic regression, unlabelled discovery, and measured accuracy (none);
- `FINAL_COMPARISON.md` states the 11 H5 mappings are not takeoff members.

## Preserved drift (never staged)

`backend/training/documents/doc_0d910a43b4a021e3.json`, `backend/training/multimodal_review_index.json`, `backend/training/upload_log.csv` (modified); 4 untracked `backend/training/documents/doc_*.json`, `backend/training/label_reconstruction_tmp/`, `docs/deep_research_project_rule_intelligence/`, 17 `docs/validation/phase_{c,d1,d2}_*` files.

## Test baseline carried into Phase 2

Targeted 222 passed / 1 skipped. Full suite 1342 passed, 9 failed (the same pre-existing 9: 8 × `test_a2_a7_human_review`, 1 × `test_repeated_detail_linker`), 4 skipped.
