# Project-Level Evaluation Split Policy (Phase 2.6)

Frozen **before** any real ground-truth review data exists and **before** any model training begins, specifically so no split can be chosen (or later adjusted) based on which assignment produces better-looking numbers. This is the same discipline `phase3_readiness_decision.md` and the deep-research report both flag as the #1 leakage risk in `evaluate_pipeline.py`'s existing accuracy numbers: splitting at the row/group level instead of the project level lets the same drawing's visual conventions, label style, and geometry patterns leak between train and test.

## The core rule

**The project is the only unit a split may be defined over.** A `project_id` belongs to exactly one of {`train`, `test`} (see below for why there is no separate fixed `val` bucket at this project count). No `group_id`, `document_id`, `page_id`, or `geometry_id` may ever be evaluated for train/test membership individually — its membership is entirely determined by looking up its `project_id`. Any future evaluation or training script must group-split by `project_id`, never row-shuffle-split.

## Why not a fixed 70/15/15 split

This phase has exactly **7 real projects** (`real_project_inventory.md`). A probabilistic hash-bucket assignment targeting 70/15/15 ratios only converges to those ratios at much larger project counts — at N=7 it produces arbitrarily skewed results (a real trial run of the obvious hash-mod-100 approach produced 3 train / 3 val / 1 test, which is unusable). Forcing a 3-way split onto 7 data points either starves one bucket or makes val/test statistically meaningless. Standard practice for this data regime is **leave-one-group-out (grouped) cross-validation within the training pool**, with one project permanently held out as a true test set — not a fixed val bucket.

## Frozen assignment

**Test project (held out, frozen): `project_007`.**

Selected deterministically, not by hand-picking: `sha1("estima3d_ml_association_split_v1|" + project_id)`, taking the first 8 hex characters as an integer mod 100. `project_007` has the lowest value (7) among the 7 current project IDs:

| project_id | hash bucket (0-99) |
|---|---|
| project_007 | 7 |
| project_006 | 24 |
| project_001 | 41 |
| project_002 | 76 |
| project_004 | 79 |
| project_003 | 84 |
| project_005 | 97 |

`project_007` is reasonably represented in the current review batch (15/108 groups, 13.9% — `human_review_batch_manifest.json`), so held-out test performance will not be measured on a near-empty sample.

**Train pool: `project_001`, `project_002`, `project_003`, `project_004`, `project_005`, `project_006`** (the remaining 6). Any model selection, hyperparameter tuning, or threshold calibration in Phase 3+/4+ must use **grouped leave-one-project-out cross-validation within this pool only** (6 folds, one project held out per fold) — never a fixed internal val project, for the same small-N reason above.

## The inviolable rule going forward

`project_007`'s data must never be inspected, feature-engineered against, tuned against, or used to inform any modeling or heuristic-repair decision before a final, dated evaluation checkpoint is run and recorded. This includes:
- Manually reading `project_007` review outcomes while designing a candidate generator/ranker feature.
- Adjusting the dense-page cap, leader-resolution logic, or any other production heuristic specifically because it performs worse on `project_007`.
- Re-running "final" evaluation more than once and reporting only the better result.

A violation of this rule invalidates the frozen-baseline comparison for all of Phase 3+, not just the affected metric.

## Growth policy — onboarding new real projects

As new real projects are added beyond these 7:
1. **`project_007` remains the test project permanently.** It is never reassigned, expanded, or swapped for a "better" held-out set without an explicit, dated addendum to this document stating the reason (e.g., "project_007 was found to be corrupted/mislabeled on 2026-XX-XX") — never silently, and never because of an evaluation-number outcome.
2. Every new project's `train`/`test` bucket is computed with the same deterministic formula above (`sha1(salt|project_id) mod 100`). Once the project pool grows large enough (informally, once there are enough projects for the 70/15/15-style thresholds to hold statistically — roughly 20+), this policy should be revisited to introduce a proper fixed `val` bucket via the same range-based thresholding (`< 70` train, `70-84` val, `>= 85` test) instead of leave-one-project-out CV. That revision itself requires an addendum here, not a silent change.
3. Until that revision happens, every new project not equal to `project_007` joins the train/grouped-CV pool by default.

## Relationship to the double-review subset

The double-review subset (`double_review_subset.md`) is an **orthogonal concern** — it exists to measure inter-rater agreement on the review process itself, not to evaluate a model. It deliberately spans both the train pool and the frozen test project (`project_007` contributes 9 of the 37 double-reviewed groups). This is intentional and does not violate the split policy: double review never feeds back into model training or tuning, it only characterizes how reliable the ground-truth labels themselves are.

## Where the real project identities live

This document, like every other tracked file in this phase, refers only to sanitized IDs (`project_001`...`project_007`). The mapping from these IDs to real client/project names lives only in the git-ignored `backend/training/ml_association/real_project_pilot/working_notes/project_id_mapping.json` (verified git-ignored before creation, per Phase 2.5's confidentiality guardrails) and is never referenced from a tracked file.
