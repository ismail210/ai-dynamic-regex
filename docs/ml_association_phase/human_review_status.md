# Human Review Status (Phase 2.6)

Supersedes `real_project_annotation_status.md` (Phase 2.5)'s "no groups reviewed" status with the current, rebalanced batch and the now-built review infrastructure. Companion documents: `human_review_batch_manifest.json` (which groups, how selected), `human_review_protocol.md` (how to review), `double_review_subset.md` (which 37 groups get a second independent reviewer), `project_split_policy.md` (frozen train/test project assignment for later model evaluation).

## Status: infrastructure complete, reviews not yet performed

Everything needed to perform and import a real human review is built, tested, and ready:

| Deliverable | Status |
|---|---|
| Rebalanced 108-group review batch (no project over-represented beyond 15.7%) | Done — `human_review_batch_manifest.json` |
| Offline, bias-reduced HTML review kit (108 group pages + index, randomized candidate order, hidden heuristic reveal) | Done — `backend/scripts/build_ml_association_review_kit.py`, generates into git-ignored `training/ml_association/real_project_pilot/review_kit/` |
| Reviewer protocol (mechanics: build, open, decide, save, collect, import) | Done — `human_review_protocol.md` |
| Decision-file batch importer with strict schema/semantic validation | Done — `backend/scripts/import_review_decisions.py`, regression-tested (`backend/tests/test_import_review_decisions.py`) |
| Deterministic double-review stratified subset (37/108 groups, 34.3%) | Done — `double_review_subset.md`, `backend/scripts/select_double_review_subset.py` |
| Frozen project-level train/test split policy | Done — `project_split_policy.md` (test: `project_007`; train pool: the other 6, leave-one-project-out grouped CV) |

**Zero groups have been reviewed.** `outcome_store.latest_outcomes()` returns an empty dict for all 108 groups. No `ReviewedOutcome` rows exist anywhere in this repository (real or synthetic — the append-only outcome store used for real data, `training/ml_association/real_project_pilot/working_notes/outcomes.jsonl`, does not yet exist as a file).

## Reviewer arrangement

Per an explicit decision on 2026-08-06: the actual structural-engineering review will be performed by a separate reviewer external to this working session (not the operator of this tool, not fabricated by the AI assistant performing this phase — consistent with this phase's top-level constraint not to infer or fabricate structural ground truth). Handoff logistics (getting the git-ignored `review_kit/` directory and source PDFs to that reviewer, and getting `*.decision.json` files back) are the project owner's responsibility — this tool never transmits confidential project data anywhere itself.

## What remains blocked until real review data exists

Every one of the following Phase 2.6 spec items requires real `ReviewedOutcome` rows and cannot be produced without them (producing them without real data would mean inferring or fabricating structural ground truth, which this phase explicitly forbids):

- Import and validate real review outcomes (Step 6)
- Real ground-truth metrics: recall@1/3/5/10, heuristic top-1 accuracy/MRR, error rates by project/page-type/family, no-match accuracy, multi-target P/R/F1 (Step 7)
- Analysis of the pilot's 28.8% leader-selected-as-target finding against real reviewed truth (Step 8) — currently that finding rests only on the mechanism-level observation that production selected a leader stroke as its own final pick; whether that pick was ever also structurally *correct* by coincidence, and how often the experimental leader-resolved alternative is the human-confirmed right answer, both require real review.
- Reviewed error taxonomy (`reviewed_error_taxonomy.md`, Step 9) — distinct from the existing `real_project_error_taxonomy.md`, which documents *pipeline mechanism* defects found by direct inspection, not reviewer-confirmed association errors.
- Reviewer agreement analysis (`reviewer_agreement.md`) — needs both reviewers' outcomes on the 37-group double-review subset.
- An updated `phase3_readiness_decision.md` reflecting real reviewed-batch results.
- Final-report items dependent on any of the above.

## What is NOT blocked

Everything listed as "Done" above is complete now, independent of reviewer availability, and does not need to be redone once review data arrives — the importer, validator, split policy, and double-review subset all operate on real reviewer output as soon as it exists, with no further code changes anticipated.

## Recommended order once review begins

1. Review the 37-group double-review subset first (or interleave it), since agreement measurement depends on having both reviewers' independent decisions before any single-reviewer group is treated as final for metrics purposes.
2. Within that, prioritize the 31 leader-evidence double-review groups — they most directly test the pilot's headline finding.
3. Import incrementally (`import_review_decisions.py` can be re-run any time; it is additive/idempotent per file) rather than waiting for all 108 to finish, so partial metrics can be sanity-checked early.
